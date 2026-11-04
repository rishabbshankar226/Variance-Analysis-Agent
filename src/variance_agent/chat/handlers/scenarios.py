"""Waterfall, what-if, sensitivity and run rate.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

import re
from decimal import Decimal, Inexact, InvalidOperation
from typing import NamedTuple
from variance_agent.currencies import CURRENCY_SYMBOLS
from variance_agent.models import AnalysisConfig, AnalysisResult, AnalyzedRow, LineType
from variance_agent.numeric import financial_context, ratio
from variance_agent.parsing import parse_decimal
from ..intent import ParsedIntent, find_line_item, normalize_for_routing
from ..responses import Response, format_money, report_places, safe_inline, status_cell
from ..session import Phase, Session
from ..views import figure, figures_view, pair
from ._common import (
    _fu,
    _fu_between,
    _heading,
    _is_budget,
    _noun,
    _pct_change,
    _pct_text,
    _plain_heading,
    _tone,
    _unclassified_note,
    _with_unclassified_note,
)
from ._items import _resolve_item_query


def _handle_waterfall(session: Session) -> Response:
    """Generate a step-by-step P&L bridge / waterfall walk reconciling budget to actual profit."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    with financial_context():
        budget_rev = result.revenue.budget
        budget_exp = result.expenses.budget
        budget_profit = budget_rev - budget_exp

        actual_rev = result.revenue.actual
        actual_exp = result.expenses.actual
        actual_profit = actual_rev - actual_exp

        net_var = actual_profit - budget_profit
        rev_impact = actual_rev - budget_rev
        exp_impact = budget_exp - actual_exp

        # Collect individual line items contributing to the bridge
        bridge_items: list[tuple[AnalyzedRow, Decimal]] = []
        for row in result.rows:
            if row.excluded_from_aggregation:
                continue
            if row.line_type == LineType.REVENUE:
                impact = row.actual - row.budget
            elif row.line_type == LineType.EXPENSE:
                impact = row.budget - row.actual
            else:
                # Unclassified rows sit outside the category totals, so they cannot move the bridge.
                impact = Decimal(0)
            bridge_items.append((row, impact))

        # Sort items by magnitude of profit impact (largest drivers first)
        bridge_items.sort(key=lambda item: abs(item[1]), reverse=True)

    table_rows: list[dict[str, str]] = [
        {
            "Line Item": f"1. {_heading(cfg)} Operating Profit",
            "Type": "Baseline",
            _heading(cfg): format_money(budget_profit, cur, places),
            "Actual": format_money(budget_profit, cur, places),
            f"Var ({sym})": format_money(Decimal(0), cur, places),
            f"Profit Impact ({sym})": format_money(Decimal(0), cur, places),
            "Status": "Neutral",
        }
    ]

    for row, impact in bridge_items:
        table_rows.append({
            "Line Item": safe_inline(row.line_item),
            "Type": str(row.line_type),
            _heading(cfg): format_money(row.budget, cur, places),
            "Actual": format_money(row.actual, cur, places),
            f"Var ({sym})": format_money(row.variance_dollars, cur, places),
            f"Profit Impact ({sym})": format_money(impact, cur, places),
            "Status": (status_cell(row.status) if row.line_type == LineType.UNCLASSIFIED
                       else "F" if impact > 0 else ("U" if impact < 0 else "Neutral")),
        })

    table_rows.append({
        "Line Item": "Actual Operating Profit",
        "Type": "Summary",
        _heading(cfg): format_money(budget_profit, cur, places),
        "Actual": format_money(actual_profit, cur, places),
        f"Var ({sym})": format_money(net_var, cur, places),
        f"Profit Impact ({sym})": format_money(net_var, cur, places),
        "Status": "F" if net_var > 0 else ("U" if net_var < 0 else "Neutral"),
    })

    session.last_table_items = [row.line_item for row, _ in bridge_items]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    status_text = "favorable beat" if net_var > 0 else ("unfavorable shortfall" if net_var < 0 else "neutral")
    rev_status = "beat" if rev_impact > 0 else ("shortfall" if rev_impact < 0 else "flat")
    exp_status = "savings" if exp_impact > 0 else ("overrun" if exp_impact < 0 else "on track")

    text = (
        f"**P&L Variance Bridge (Waterfall Walk)**\n\n"
        f"Reconciling baseline {_heading(cfg)} Operating Profit to Actual Operating Profit for **{safe_inline(session.period or '')}**:\n\n"
        f"• **{_heading(cfg)} Operating Profit**: {format_money(budget_profit, cur, places)}\n"
        f"• **Revenue Bridge Impact**: {format_money(rev_impact, cur, places)} ({rev_status})\n"
        f"• **Expense Bridge Impact**: {format_money(exp_impact, cur, places)} ({exp_status})\n"
        f"• **Actual Operating Profit**: {format_money(actual_profit, cur, places)}\n"
        f"• **Net Profit Variance**: {format_money(net_var, cur, places)} ({status_text})\n\n"
        "Each line item's contribution to operating profit is displayed in the bridge table below "
        "(positive values expand profit; negative values contract profit):"
    )
    unclassified = [row for row, _ in bridge_items if row.line_type == LineType.UNCLASSIFIED]
    if unclassified:
        text += (
            f"\n\n{len(unclassified)} unclassified line item{'s are' if len(unclassified) != 1 else ' is'} "
            "excluded from operating profit and shown with zero impact until classified."
        )

    chips = []
    if session.last_table_items:
        chips.append(f"Why {session.last_table_items[0]}?")
    chips.extend(["Biggest risks", "Biggest wins", "Export CSV", "Summary"])

    return Response(text=text, table=table_rows, chips=chips, phase=Phase.EXPLORING)


def _what_if_amount(intent: ParsedIntent, target_clean: str, sym: str) -> Response | tuple[Decimal, bool, bool]:
    """The scenario's amount, whether it is a percentage and whether it lowers the target; or the reply refusing it."""
    raw_amount = intent.captures.get("amount", "").strip()
    direction = (intent.captures.get("direction") or "").lower()
    suffix = (intent.captures.get("suffix") or "").lower()

    if not raw_amount:
        return Response(
            text="Please specify a simulation amount or percentage (e.g., `what if revenue drops 5%?` or `what if marketing increases "
                 "$20,000?`).",
            chips=["What if revenue drops 5%?", "What if expenses increase 10%?", "Sensitivity analysis"],
            phase=Phase.EXPLORING,
        )

    # Determine sign from the verb stem so every inflection (drop/drops/dropped, fall/falls, ...) agrees
    is_negative = (
        direction.startswith(("drop", "decreas", "fall", "cut", "reduc", "shrink", "lower", "down", "-"))
        or suffix in ("lower", "down", "less")
        or raw_amount.startswith("-")
    )

    amount_clean = raw_amount.lstrip("+-").strip()
    is_percent = "%" in amount_clean
    amount_num_str = (amount_clean.replace("%", "").replace(sym, "").replace("$", "").replace("€", "").replace("£", "")
                      .replace(",", "").strip())

    multiplier = Decimal(1)
    if not is_percent:
        if amount_num_str.lower().endswith("k"):
            multiplier = Decimal(1000)
            amount_num_str = amount_num_str[:-1].strip()
        elif amount_num_str.lower().endswith("m"):
            multiplier = Decimal(1000000)
            amount_num_str = amount_num_str[:-1].strip()
        elif amount_num_str.lower().endswith("b"):
            multiplier = Decimal(1000000000)
            amount_num_str = amount_num_str[:-1].strip()

    try:
        amount_dec = parse_decimal(amount_num_str, field="amount", line_item="what_if") * multiplier
    except (ValueError, InvalidOperation):
        return Response(
            text=f"Could not parse numeric amount from '{safe_inline(raw_amount)}'.",
            chips=["What if revenue drops 5%?", "Sensitivity analysis"],
            phase=Phase.EXPLORING,
        )

    if amount_dec < 0:
        amount_dec = abs(amount_dec)
        is_negative = True

    if is_negative and is_percent and amount_dec > Decimal(100):
        return Response(
            text=f"A drop of more than 100% would take {safe_inline(target_clean)} below zero, "
                 "which is not a meaningful scenario. Try a smaller percentage or a dollar amount.",
            chips=["What if revenue drops 5%?", "What if expenses drop 10%?", "Sensitivity analysis"],
            phase=Phase.EXPLORING,
        )
    return amount_dec, is_percent, is_negative


def _what_if_target(
    session: Session, result: AnalysisResult, target_clean: str,
) -> Response | tuple[bool, bool, AnalyzedRow | None]:
    """Whether the target is total revenue or total expenses, else its line; or the reply refusing it."""
    # Identify target: aggregate revenue, aggregate expense, or specific line item
    is_rev_agg = target_clean.lower() in ("revenue", "revenues", "sales", "topline", "top line")
    is_exp_agg = target_clean.lower() in ("expense", "expenses", "costs", "spend", "opex")

    matched_row: AnalyzedRow | None = None
    if not is_rev_agg and not is_exp_agg:
        line_items = [r.line_item for r in result.rows]
        resolved = _resolve_item_query(target_clean, session)
        matches = find_line_item(resolved, line_items)
        if matches:
            for r in result.rows:
                if r.line_item == matches[0]:
                    matched_row = r
                    break
        if matched_row is None:
            return Response(
                text=f"Could not identify target '{safe_inline(target_clean)}'. "
                     "You can simulate `revenue`, `expenses`, or a specific line item from your data.",
                chips=["What if revenue drops 5%?", "What if expenses increase 10%?", "Summary"],
                phase=Phase.EXPLORING,
            )

    if matched_row is not None and matched_row.line_type == LineType.UNCLASSIFIED:
        return Response(
            text=f"**{safe_inline(matched_row.line_item)}** is not classified as Revenue or Expense, so I "
                 "cannot tell whether a change helps or hurts profit. Classify it first: type `new`, "
                 "upload the file again and label it when asked, or add a Type column to your file.",
            chips=["What if revenue drops 5%?", "What if expenses increase 10%?", "Summary"],
            phase=Phase.EXPLORING,
        )
    return is_rev_agg, is_exp_agg, matched_row


class _Simulation(NamedTuple):
    """The what-if scenario's baseline and simulated figures, computed in the financial context."""

    base_rev: Decimal
    base_exp: Decimal
    base_profit: Decimal
    budget_rev: Decimal
    budget_exp: Decimal
    budget_profit: Decimal
    target_label: str
    target_type: str
    target_budget: Decimal
    target_is_rev: bool
    base_val: Decimal
    delta: Decimal
    sim_rev: Decimal
    sim_exp: Decimal
    sim_val: Decimal
    sim_profit: Decimal
    profit_delta: Decimal
    sim_vs_budget: Decimal
    base_margin: Decimal | None
    sim_margin: Decimal | None
    margin_delta: Decimal | None


def _simulate(
    result: AnalysisResult, matched_row: AnalyzedRow | None, *, is_rev_agg: bool, is_exp_agg: bool, amount_dec: Decimal,
    is_percent: bool, is_negative: bool,
) -> _Simulation:
    """Apply the change to its target and recompute revenue, expenses, profit and margin."""
    with financial_context() as context:
        context.traps[Inexact] = False
        base_rev = result.revenue.actual
        base_exp = result.expenses.actual
        base_profit = base_rev - base_exp
        budget_rev = result.revenue.budget
        budget_exp = result.expenses.budget
        budget_profit = budget_rev - budget_exp

        if is_rev_agg:
            target_label = "Total Revenue"
            target_type = "Aggregate Revenue"
            target_budget = budget_rev
            target_is_rev = True
            base_val = base_rev
            delta = (base_rev * ratio(amount_dec, Decimal(100))) if is_percent else amount_dec
            if is_negative:
                delta = -delta
            sim_rev = base_rev + delta
            sim_exp = base_exp
            sim_val = sim_rev
        elif is_exp_agg:
            target_label = "Total Expenses"
            target_type = "Aggregate Expense"
            target_budget = budget_exp
            target_is_rev = False
            base_val = base_exp
            delta = (base_exp * ratio(amount_dec, Decimal(100))) if is_percent else amount_dec
            if is_negative:
                delta = -delta
            sim_rev = base_rev
            sim_exp = base_exp + delta
            sim_val = sim_exp
        else:
            assert matched_row is not None
            target_label = safe_inline(matched_row.line_item)
            target_type = str(matched_row.line_type)
            target_budget = matched_row.budget
            target_is_rev = (matched_row.line_type == LineType.REVENUE)
            base_val = matched_row.actual
            delta = (base_val * ratio(amount_dec, Decimal(100))) if is_percent else amount_dec
            if is_negative:
                delta = -delta
            sim_val = base_val + delta

            if matched_row.line_type == LineType.REVENUE:
                sim_rev = base_rev + delta
                sim_exp = base_exp
            else:  # an Expense: _what_if_target answers an Unclassified line before any simulation
                sim_rev = base_rev
                sim_exp = base_exp + delta

        sim_profit = sim_rev - sim_exp
        profit_delta = sim_profit - base_profit
        sim_vs_budget = sim_profit - budget_profit

        base_margin = (ratio(base_profit, base_rev) * Decimal(100)) if base_rev != 0 else None
        sim_margin = (ratio(sim_profit, sim_rev) * Decimal(100)) if sim_rev != 0 else None
        margin_delta = _pct_change(sim_margin, base_margin)

    return _Simulation(base_rev, base_exp, base_profit, budget_rev, budget_exp, budget_profit, target_label, target_type,
                       target_budget, target_is_rev, base_val, delta, sim_rev, sim_exp, sim_val, sim_profit, profit_delta,
                       sim_vs_budget, base_margin, sim_margin, margin_delta)


def _what_if_text(
    cfg: AnalysisConfig, sim: _Simulation, change_desc: str, profit_status: str, budget_status: str, places: int,
) -> str:
    """The scenario's parameters and its projected operating profit impact, as the reply text."""
    cur = cfg.currency
    return (
        f"**Scenario Analysis (\"What-If\" Simulation)**\n\n"
        f"**Simulation Parameters:**\n"
        f"• {'Target' if _is_budget(cfg) else 'Line'}: **{sim.target_label}** ({sim.target_type})\n"
        f"• Baseline Actual: {format_money(sim.base_val, cur, places)}\n"
        f"• Simulated Change: **{change_desc}**\n"
        f"• Simulated {'Target ' if _is_budget(cfg) else ''}Value: **{format_money(sim.sim_val, cur, places)}**\n\n"
        f"**Projected Operating Profit Impact:**\n"
        f"• **Baseline Operating Profit**: {format_money(sim.base_profit, cur, places)}\n"
        f"• **Simulated Operating Profit**: **{format_money(sim.sim_profit, cur, places)}**\n"
        f"• **Profit Delta vs. Baseline**: **{format_money(sim.profit_delta, cur, places)}** ({profit_status})\n"
        f"• **Simulated Operating Margin**: **{_pct_text(sim.sim_margin)}** (vs. {_pct_text(sim.base_margin)} baseline, "
        f"{_pct_text(sim.margin_delta, '+.1f', ' pts')})\n"
        f"• **Simulated vs. {_heading(cfg)}**: **{format_money(sim.sim_vs_budget, cur, places)}** ({budget_status} vs. "
        f"{'planned' if _is_budget(cfg) else _noun(cfg)} profit of {format_money(sim.budget_profit, cur, places)})\n"
    )


def _what_if_table(
    cfg: AnalysisConfig, sim: _Simulation, matched_row: AnalyzedRow | None, places: int,
) -> list[dict[str, str]]:
    """The scenario line by line: the target line, if one, then revenue, expenses and operating profit."""
    cur = cfg.currency
    target_row = [] if matched_row is None else [
        {
            "Metric": sim.target_label,
            _heading(cfg): format_money(sim.target_budget, cur, places),
            "Baseline Actual": format_money(sim.base_val, cur, places),
            "Simulated Scenario": format_money(sim.sim_val, cur, places),
            "Delta vs Baseline": format_money(sim.delta, cur, places),
            "Status": _fu(sim.delta, higher_is_better=sim.target_is_rev),
        },
    ]
    # Aggregate targets are already the Total Revenue / Total Expenses rows below.
    return target_row + [
        {
            "Metric": "Total Revenue",
            _heading(cfg): format_money(sim.budget_rev, cur, places),
            "Baseline Actual": format_money(sim.base_rev, cur, places),
            "Simulated Scenario": format_money(sim.sim_rev, cur, places),
            "Delta vs Baseline": format_money(sim.sim_rev - sim.base_rev, cur, places),
            "Status": _fu_between(sim.sim_rev, sim.base_rev),
        },
        {
            "Metric": "Total Expenses",
            _heading(cfg): format_money(sim.budget_exp, cur, places),
            "Baseline Actual": format_money(sim.base_exp, cur, places),
            "Simulated Scenario": format_money(sim.sim_exp, cur, places),
            "Delta vs Baseline": format_money(sim.sim_exp - sim.base_exp, cur, places),
            "Status": _fu_between(sim.sim_exp, sim.base_exp, higher_is_better=False),
        },
        {
            "Metric": "Operating Profit",
            _heading(cfg): format_money(sim.budget_profit, cur, places),
            "Baseline Actual": format_money(sim.base_profit, cur, places),
            "Simulated Scenario": format_money(sim.sim_profit, cur, places),
            "Delta vs Baseline": format_money(sim.profit_delta, cur, places),
            "Status": _fu(sim.profit_delta),
        },
    ]


def _what_if_view(
    result: AnalysisResult, sim: _Simulation, matched_row: AnalyzedRow | None, change_desc: str, profit_status: str,
    budget_status: str, places: int,
) -> dict[str, object]:
    """The scenario's figures view: the target, then operating profit, margin and the comparison."""
    cfg = result.config
    cur = cfg.currency
    raw_label = matched_row.line_item if matched_row is not None else sim.target_label
    heading = _plain_heading(cfg)
    return figures_view(
        f"Scenario: {raw_label} {change_desc}",
        context=[pair("Line" if not _is_budget(cfg) else "Target", f"{raw_label} ({sim.target_type})"),
                 pair("Baseline actual", format_money(sim.base_val, cur, places)),
                 pair("Simulated value", format_money(sim.sim_val, cur, places))],
        figures=[
            figure("Operating profit", format_money(sim.sim_profit, cur, places),
                   f"Baseline {format_money(sim.base_profit, cur, places)}",
                   f"{format_money(sim.profit_delta, cur, places)} vs. baseline ({profit_status})", tone=_tone(sim.profit_delta)),
            figure("Operating margin", _pct_text(sim.sim_margin), f"Baseline {_pct_text(sim.base_margin)}",
                   _pct_text(sim.margin_delta, "+.1f", " pts")),
            figure(f"Against {heading.lower() if _is_budget(cfg) else heading}", format_money(sim.sim_vs_budget, cur, places),
                   f"{heading} profit {format_money(sim.budget_profit, cur, places)}", budget_status.capitalize(),
                   tone=_tone(sim.sim_vs_budget)),
        ],
        notes=[note for note in (_unclassified_note(result).replace("unclassified line item",
                                                                    "line item not yet labeled revenue or expense"),)
               if note],
        table_title="The scenario line by line",
    )


def _handle_what_if(session: Session, intent: ParsedIntent) -> Response:
    """Simulate scenario impact on revenue, expenses, and operating profit."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    raw_target = intent.captures.get("target", "").strip()
    target_clean = re.sub(r"^(?:our|the|line\s+item)\s+", "", raw_target, flags=re.IGNORECASE).strip()
    amount = _what_if_amount(intent, target_clean, sym)
    if isinstance(amount, Response):
        return amount
    amount_dec, is_percent, is_negative = amount

    target = _what_if_target(session, result, target_clean)
    if isinstance(target, Response):
        return target
    is_rev_agg, is_exp_agg, matched_row = target

    sim = _simulate(result, matched_row, is_rev_agg=is_rev_agg, is_exp_agg=is_exp_agg, amount_dec=amount_dec,
                    is_percent=is_percent, is_negative=is_negative)

    # These run outside the financial context, as they did before the split.
    sign_str = "-" if sim.delta < 0 else "+"
    change_desc = f"{sign_str}{amount_dec:.1f}%" if is_percent else f"{sign_str}{sym}{abs(sim.delta):,.2f}"
    profit_status = "expansion" if sim.profit_delta > 0 else ("contraction" if sim.profit_delta < 0 else "neutral")
    budget_status = "beat" if sim.sim_vs_budget > 0 else ("shortfall" if sim.sim_vs_budget < 0 else "on track")

    text = _what_if_text(cfg, sim, change_desc, profit_status, budget_status, places)
    table = _what_if_table(cfg, sim, matched_row, places)
    chips = ["Sensitivity analysis", "Run rate", "Waterfall", "What if expenses drop 5%?"]
    view = _what_if_view(result, sim, matched_row, change_desc, profit_status, budget_status, places)
    return Response(text=_with_unclassified_note(text, result), table=table, chips=chips, phase=Phase.EXPLORING,
                    view=view)


def _handle_sensitivity(session: Session) -> Response:
    """Generate a multi-scenario sensitivity matrix across revenue and expense deviations."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    with financial_context() as context:
        context.traps[Inexact] = False
        base_rev = result.revenue.actual
        base_exp = result.expenses.actual
        base_profit = base_rev - base_exp
        budget_profit = result.revenue.budget - result.expenses.budget

        scenarios = [
            ("Severe Downside (-10% Rev, +5% Exp)", Decimal("-0.10"), Decimal("0.05")),
            ("Moderate Downside (-5% Rev, +2% Exp)", Decimal("-0.05"), Decimal("0.02")),
            ("Baseline Actuals (Current)", Decimal("0.00"), Decimal("0.00")),
            ("Moderate Upside (+5% Rev, -2% Exp)", Decimal("0.05"), Decimal("-0.02")),
            ("Strong Upside (+10% Rev, -5% Exp)", Decimal("0.10"), Decimal("-0.05")),
        ]

        table_rows: list[dict[str, str]] = []
        for name, rev_pct, exp_pct in scenarios:
            s_rev = base_rev * (Decimal(1) + rev_pct)
            s_exp = base_exp * (Decimal(1) + exp_pct)
            s_profit = s_rev - s_exp
            s_var_budget = s_profit - budget_profit
            s_margin = (ratio(s_profit, s_rev) * Decimal(100)) if s_rev != 0 else None
            status = _fu(s_var_budget)

            table_rows.append({
                "Scenario": name,
                "Revenue": format_money(s_rev, cur, places),
                "Expenses": format_money(s_exp, cur, places),
                "Operating Profit": format_money(s_profit, cur, places),
                f"Var vs {_heading(cfg)} ({sym})": format_money(s_var_budget, cur, places),
                "Operating Margin": _pct_text(s_margin),
                "Status": status,
            })

    text = (
        f"**Financial Sensitivity & Scenario Matrix**\n\n"
        f"Evaluating operating profit resilience against volume and cost stress testing "
        f"for **{safe_inline(session.period or '')}**:\n\n"
        f"• **Baseline Operating Profit**: {format_money(base_profit, cur, places)}\n"
        f"• **{'Planned Budget' if _is_budget(cfg) else _heading(cfg)} Profit**: {format_money(budget_profit, cur, places)}\n"
        f"• **Stress Range**: From **{table_rows[0]['Operating Profit']}** (Severe Downside) "
        f"to **{table_rows[-1]['Operating Profit']}** (Strong Upside).\n\n"
        "Explore individual scenarios with `what if revenue drops 5%?` or `what if expenses increase 10%?`."
    )

    chips = ["What if revenue drops 5%?", "What if expenses increase 5%?", "Run rate", "Waterfall"]
    return Response(text=_with_unclassified_note(text, result), table=table_rows, chips=chips, phase=Phase.EXPLORING)


_UNRECOGNISED_PERIOD = "Quarterly (3 months assumed)"


_MONTH_NUMBERS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_NAME = re.compile(r"\b(" + "|".join(sorted(_MONTH_NUMBERS, key=len, reverse=True)) + r")\b")
_QUARTER = re.compile(r"(?<![a-z\d])q([1-4])(?!\d)")
_HALF = re.compile(r"(?<![a-z\d])h([12])(?!\d)")


def _detect_period_elapsed_months(period: str) -> tuple[int, str]:
    """Detect elapsed months and period label from session period text.

    The period names the end of the year-to-date span: a quarter or half by its number, a
    month (or the last month of a range such as 'Jan-Jun 2026') by its position in the year.
    """
    p = normalize_for_routing(period).lower()
    quarter = _QUARTER.search(p)
    if quarter:
        number = int(quarter.group(1))
        if number == 4:
            return 12, "Full Year (12 months)"
        return 3 * number, f"Q{number} ({3 * number} months elapsed)"
    half = _HALF.search(p)
    if half or "first half" in p or "second half" in p:
        if (half is not None and half.group(1) == "2") or "second half" in p:
            return 12, "H2 (12 months)"
        return 6, "H1 (6 months elapsed)"
    if re.search(r"\b(?:fy|fiscal\s+year|year)\s+end", p):
        return 12, "Full Year (12 months)"

    month_hits = _MONTH_NAME.findall(p)
    if month_hits:
        m_name = month_hits[-1]
        m_num = _MONTH_NUMBERS[m_name]
        return m_num, f"{m_name.capitalize()} ({m_num} month{'s' if m_num != 1 else ''} elapsed)"

    if re.search(r"\bfy|full\s+year|annual", p):
        return 12, "Full Year (12 months)"

    m_match = re.search(r"\bm(?:onth)?\s*([1-9]|1[0-2])\b", p)
    if m_match:
        m_num = int(m_match.group(1))
        return m_num, f"Month {m_num} ({m_num} month{'s' if m_num != 1 else ''} elapsed)"

    return 3, _UNRECOGNISED_PERIOD


def _handle_run_rate(session: Session, intent: ParsedIntent) -> Response:
    """Project annualized run-rate and corporate Latest Estimate (LE) year-end outcomes."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    elapsed, period_label = _detect_period_elapsed_months(session.period or "")
    remaining = 12 - elapsed

    with financial_context() as context:
        context.traps[Inexact] = False
        actual_rev = result.revenue.actual
        actual_exp = result.expenses.actual
        actual_profit = actual_rev - actual_exp

        budget_rev = result.revenue.budget
        budget_exp = result.expenses.budget
        budget_profit = budget_rev - budget_exp

        multiplier = ratio(Decimal(12), Decimal(elapsed))

        # 1. Pace-based annualized run-rate
        rr_rev = actual_rev * multiplier
        rr_exp = actual_exp * multiplier
        rr_profit = rr_rev - rr_exp
        annual_budget_profit = budget_profit * multiplier
        rr_var = (actual_profit - budget_profit) * multiplier  # = rr_profit - annual_budget_profit, exactly
        rr_margin = (ratio(rr_profit, rr_rev) * Decimal(100)) if rr_rev != 0 else None

        # 2. Corporate FP&A Latest Estimate (LE = Actuals to Date + Remaining Budget)
        remaining_budget_rev = budget_rev * ratio(Decimal(remaining), Decimal(elapsed))
        remaining_budget_exp = budget_exp * ratio(Decimal(remaining), Decimal(elapsed))
        le_rev = actual_rev + remaining_budget_rev
        le_exp = actual_exp + remaining_budget_exp
        le_profit = le_rev - le_exp
        le_var = actual_profit - budget_profit  # = le_profit - annual_budget_profit, since remaining/elapsed + 1 = multiplier
        le_margin = (ratio(le_profit, le_rev) * Decimal(100)) if le_rev != 0 else None

    rr_status = "beat" if rr_var >= 0 else "shortfall"
    le_status = "favorable beat" if le_var >= 0 else "unfavorable shortfall"

    remaining_label = "Remaining Plan" if _is_budget(cfg) else f"Remaining {_heading(cfg)}"
    text = (
        f"**Run-Rate & Full-Year (FY) Projections**\n\n"
        f"**Period Basis:** **{period_label}** ({elapsed} of 12 months elapsed; {remaining} months remaining in fiscal year).\n"
        f"*Assumption: the figures are year-to-date through this period, so they are annualized over {elapsed} months.*\n"
        + (f"Period '{safe_inline(session.period or '')}' was not recognised, so {elapsed} elapsed months are assumed; "
           "name it like `Q3 2026`, `H1 2026`, `FY2026` or `October 2026` for an exact basis.\n"
           if period_label == _UNRECOGNISED_PERIOD else "")
        + "\n"
        f"• **Annualized Operating Profit (Run-Rate)**: **{format_money(rr_profit, cur, places)}**\n"
        f"  *If current operational velocity continues for the full year, profit is projected at {format_money(rr_profit, cur, places)} "
        + (f"(in line with annual {_noun(cfg)} of {format_money(annual_budget_profit, cur, places)}).*\n\n" if rr_var == 0 else
           f"({format_money(rr_var, cur, places)} {rr_status} vs. annual {_noun(cfg)} of "
           f"{format_money(annual_budget_profit, cur, places)}).*\n\n")
        +
        f"• **Corporate Latest Estimate (LE = Actuals + {remaining_label})**: **{format_money(le_profit, cur, places)}**\n"
        f"  *Assuming remaining {remaining} months perform strictly to {_noun(cfg)}, full-year profit finishes at "
        f"{format_money(le_profit, cur, places)} "
        + (f"(in line with {'plan' if _is_budget(cfg) else _noun(cfg)}).*\n\n" if le_var == 0 else
           f"({format_money(le_var, cur, places)} {le_status} vs. {'plan' if _is_budget(cfg) else _noun(cfg)}).*\n\n")
        +
        f"• **Annualized Revenue Run-Rate**: {format_money(rr_rev, cur, places)} (Operating Margin: {_pct_text(rr_margin)})\n"
        f"• **Annualized Expense Run-Rate**: {format_money(rr_exp, cur, places)}"
    )

    table = [
        {
            "Projection Model": f"Actuals to Date ({safe_inline(session.period or '')})",
            "Revenue": format_money(actual_rev, cur, places),
            "Expenses": format_money(actual_exp, cur, places),
            "Operating Profit": format_money(actual_profit, cur, places),
            f"Var vs {_heading(cfg)} ({sym})": format_money(actual_profit - budget_profit, cur, places),
            "Operating Margin": f"{(ratio(actual_profit, actual_rev) * 100):.1f}%" if actual_rev != 0 else "N/A",
            "Status": _fu(actual_profit - budget_profit),
        },
        {
            "Projection Model": "Annualized Run-Rate (Current Pace)",
            "Revenue": format_money(rr_rev, cur, places),
            "Expenses": format_money(rr_exp, cur, places),
            "Operating Profit": format_money(rr_profit, cur, places),
            f"Var vs {_heading(cfg)} ({sym})": format_money(rr_var, cur, places),
            "Operating Margin": _pct_text(rr_margin),
            "Status": _fu(rr_var),
        },
        {
            "Projection Model": f"Latest Estimate (LE: Actuals + {remaining_label})",
            "Revenue": format_money(le_rev, cur, places),
            "Expenses": format_money(le_exp, cur, places),
            "Operating Profit": format_money(le_profit, cur, places),
            f"Var vs {_heading(cfg)} ({sym})": format_money(le_var, cur, places),
            "Operating Margin": _pct_text(le_margin),
            "Status": _fu(le_var),
        },
        {
            "Projection Model": f"Full-Year Baseline {_heading(cfg)}",
            "Revenue": format_money(budget_rev * multiplier, cur, places),
            "Expenses": format_money(budget_exp * multiplier, cur, places),
            "Operating Profit": format_money(annual_budget_profit, cur, places),
            f"Var vs {_heading(cfg)} ({sym})": format_money(Decimal(0), cur, places),
            "Operating Margin": (f"{(ratio(annual_budget_profit, budget_rev * multiplier) * 100):.1f}%"
                                 if (budget_rev * multiplier) != 0 else "N/A"),
            "Status": "Neutral",
        },
    ]

    chips = ["Sensitivity analysis", "What if revenue drops 5%?", "Waterfall", "Summary"]
    return Response(text=_with_unclassified_note(text, result), table=table, chips=chips, phase=Phase.EXPLORING)
