"""The executive memo, driver summary, TL;DR and profitability.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from decimal import Decimal, Inexact
from typing import NamedTuple
from variance_agent.currencies import CURRENCY_SYMBOLS
from variance_agent.models import AnalysisConfig, AnalysisResult, AnalyzedRow, LineType, Status
from variance_agent.numeric import financial_context, ratio
from ..responses import (
    Response,
    format_money,
    format_pct,
    format_threshold_amount,
    format_threshold_pct,
    report_places,
    safe_inline,
)
from ..session import Phase, Session
from ..views import figure, figures_view
from ._common import (
    _detail_rows,
    _heading,
    _in_line,
    _is_budget,
    _noun,
    _pct_change,
    _pct_text,
    _period_slug,
    _planned,
    _unclassified_note,
    _variance_percent,
    _with_unclassified_note,
)


class _MemoFigures(NamedTuple):
    """The memo's revenue, expense, profit and margin figures, computed in the financial context."""

    rev_budget: Decimal
    rev_actual: Decimal
    rev_var: Decimal
    rev_pct: Decimal | None
    exp_budget: Decimal
    exp_actual: Decimal
    exp_var: Decimal
    exp_pct: Decimal | None
    budget_profit: Decimal
    actual_profit: Decimal
    net_impact: Decimal
    net_pct: Decimal | None
    budget_margin: Decimal | None
    actual_margin: Decimal | None
    margin_delta: Decimal | None


def _memo_figures(result: AnalysisResult) -> _MemoFigures:
    with financial_context() as context:
        context.traps[Inexact] = False
        rev_budget = result.revenue.budget
        rev_actual = result.revenue.actual
        rev_var = rev_actual - rev_budget
        rev_pct = _variance_percent(rev_var, rev_budget)

        exp_budget = result.expenses.budget
        exp_actual = result.expenses.actual
        exp_var = exp_actual - exp_budget
        exp_pct = _variance_percent(exp_var, exp_budget)

        budget_profit = rev_budget - exp_budget
        actual_profit = rev_actual - exp_actual
        net_impact = actual_profit - budget_profit
        net_pct = (ratio(net_impact, abs(budget_profit)) * Decimal(100)) if budget_profit != 0 else None

        budget_margin = (ratio(budget_profit, rev_budget) * Decimal(100)) if rev_budget != 0 else None
        actual_margin = (ratio(actual_profit, rev_actual) * Decimal(100)) if rev_actual != 0 else None
        margin_delta = _pct_change(actual_margin, budget_margin)

    return _MemoFigures(rev_budget, rev_actual, rev_var, rev_pct, exp_budget, exp_actual, exp_var, exp_pct, budget_profit,
                        actual_profit, net_impact, net_pct, budget_margin, actual_margin, margin_delta)


def _memo_overview(
    result: AnalysisResult, figs: _MemoFigures, places: int, *, top_rev_beat: AnalyzedRow | None,
    top_rev_miss: AnalyzedRow | None,
) -> list[str]:
    """The memo's heading, executive summary and top-line (revenue) section."""
    cfg = result.config
    cur = cfg.currency
    status_word = "beat" if figs.net_impact >= 0 else "shortfall"
    sign_word = "moved" if figs.margin_delta is None else "expanded" if figs.margin_delta > 0 else "contracted"

    # Same fact-gated builder as the CLI --commentary report, so both surfaces agree;
    # it names the comparison basis (budget, forecast or prior period).
    from deterministic_conditioning.variance_bridge import generate_verified_commentary
    narrative_takeaway = safe_inline(generate_verified_commentary(result)[0])

    memo_lines = [
        "# Executive Management Briefing & Variance Commentary",
        f"**Reporting Period:** {cfg.period}  ",
        f"**Currency:** {cfg.currency}  ",
        f"**Materiality Thresholds:** {format_threshold_amount(cfg.dollar_threshold, cur)} or "
        f"{format_threshold_pct(cfg.percent_threshold)}  \n",
        "---",
        "### 1. Executive Summary",
        f"**Strategic Takeaway:** {narrative_takeaway}\n",
        *([f"{_unclassified_note(result)}\n"] if _unclassified_note(result) else []),
        f"For **{cfg.period}**, Operating Profit finished at **{format_money(figs.actual_profit, cur, places)}**, "
        + ("**in line with**" if figs.net_impact == 0 else
           f"representing a **{format_money(abs(figs.net_impact), cur, places)} {status_word}** ({_pct_text(figs.net_pct, '+.1f')}) "
           "against")
        + f" the {'planned budget' if _is_budget(cfg) else _noun(cfg)} of **{format_money(figs.budget_profit, cur, places)}**. "
        + (f"Operating margin **held** at **{_pct_text(figs.actual_margin)}** ({_pct_text(figs.margin_delta, '+.1f', ' pts')}).\n"
           if figs.margin_delta == 0 else
           f"Operating margin **{sign_word}** from {_pct_text(figs.budget_margin)} to **{_pct_text(figs.actual_margin)}** "
           f"({_pct_text(figs.margin_delta, '+.1f', ' pts')}).\n"),
        "### 2. Top-Line Performance (Revenue)",
        f"Total Revenue concluded at **{format_money(figs.rev_actual, cur, places)}** vs. {_heading(cfg)} of "
        f"**{format_money(figs.rev_budget, cur, places)}** "
        f"({format_money(figs.rev_var, cur, places)}, {_pct_text(figs.rev_pct, '+.1f')}, "
        f"{'in line' if figs.rev_var == 0 else 'Favorable' if figs.rev_var > 0 else 'Unfavorable'}).",
    ]

    if top_rev_beat:
        memo_lines.append(f"• **Key Outperformer:** **{safe_inline(top_rev_beat.line_item)}** generated "
                          f"{format_money(top_rev_beat.actual, cur, places)} (+{format_money(top_rev_beat.variance_dollars, cur, places)} "
                          f"above {_noun(cfg)}).")
    if top_rev_miss:
        memo_lines.append(f"• **Primary Drag:** **{safe_inline(top_rev_miss.line_item)}** delivered "
                          f"{format_money(top_rev_miss.actual, cur, places)} ({format_money(top_rev_miss.variance_dollars, cur, places)} "
                          f"miss vs. {_noun(cfg)}).")
    return memo_lines


def _add_memo_costs_and_governance(
    memo_lines: list[str], result: AnalysisResult, figs: _MemoFigures, places: int, *, top_exp_over: AnalyzedRow | None,
    top_exp_save: AnalyzedRow | None,
) -> None:
    """Add the memo's cost (expenses) and governance sections, and the action items' heading."""
    cfg = result.config
    cur = cfg.currency

    # Reconciled driver count
    reconciled_count = sum(1 for r in result.material_rows if r.driver_evidence and r.driver_evidence.reconciles)

    memo_lines.extend([
        "\n### 3. Cost Discipline & Overruns (Expenses)",
        f"Total Operating Expenses ended at **{format_money(figs.exp_actual, cur, places)}** vs. {_heading(cfg)} of "
        f"**{format_money(figs.exp_budget, cur, places)}** "
        f"({format_money(figs.exp_var, cur, places)}, {_pct_text(figs.exp_pct, '+.1f')}, "
        f"{'in line' if figs.exp_var == 0 else 'Unfavorable' if figs.exp_var > 0 else 'Favorable'}).",
    ])

    if top_exp_over:
        memo_lines.append(f"• **Primary Cost Risk:** **{safe_inline(top_exp_over.line_item)}** overspent by "
                          f"{format_money(top_exp_over.variance_dollars, cur, places)} "
                          f"({'+' if top_exp_over.variance_percent is not None else ''}"
                          f"{format_pct(top_exp_over.budget, top_exp_over.variance_dollars, top_exp_over.percent_label)}).")
    if top_exp_save:
        memo_lines.append(f"• **Key Cost Savings:** **{safe_inline(top_exp_save.line_item)}** saved "
                          f"{format_money(abs(top_exp_save.variance_dollars), cur, places)} vs. "
                          f"{'allocated budget' if _is_budget(cfg) else _noun(cfg)}.")

    memo_lines.extend([
        "\n### 4. Governance & Material Variances",
        f"• **{len(result.material_rows)}** line items breached the materiality hurdle "
        f"({format_threshold_amount(cfg.dollar_threshold, cur)} or {format_threshold_pct(cfg.percent_threshold)}).",
        f"• **Net Flow-Through:** {format_money(figs.net_impact, cur, places)} retained in net operating profit.",
        f"• **Driver Evidence Coverage:** {reconciled_count} of {len(result.material_rows)} material items verified by mathematical driver "
        "decomposition.",
        "\n### 5. Prioritized Management Action Items",
    ])


def _add_memo_actions(
    memo_lines: list[str], result: AnalysisResult, *, top_exp_over: AnalyzedRow | None, top_rev_beat: AnalyzedRow | None,
) -> None:
    """Add the memo's three prioritized management action items."""
    cfg = result.config
    if top_exp_over:
        memo_lines.append(f"1. **Cost Remediation:** Initiate immediate operational review on **{safe_inline(top_exp_over.line_item)}** to "
                          "stabilize cost trajectory.")
    else:
        memo_lines.append("1. **Cost Discipline:** Maintain expense ceiling caps across all departmental allocations.")

    if top_rev_beat:
        memo_lines.append("2. **Revenue Scaling:** Protect and expand pipeline investments supporting "
                          f"**{safe_inline(top_rev_beat.line_item)}**.")
    else:
        memo_lines.append(
            "2. **Sales Acceleration:** Formulate commercial recovery plans targeting lagging revenue lines."
            if _is_budget(cfg)
            else "2. **Sales Acceleration:** Formulate commercial recovery actions for lagging revenue lines."
        )

    missing = [safe_inline(r.line_item) for r in result.material_rows if not (r.driver_evidence and r.driver_evidence.reconciles)]
    if missing:
        memo_lines.append(f"3. **Data Governance:** Procure granular driver components (rate/volume/mix) for {', '.join(missing[:3])}.")
    else:
        memo_lines.append("3. **Audit Verification:** All material drivers mathematically reconciled and signed off.")


def _memo_table(cfg: AnalysisConfig, figs: _MemoFigures, places: int) -> list[dict[str, str]]:
    """The memo's overview table: revenue, expenses and operating profit against the comparison."""
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")
    return [
        {
            "Section": "1. Top-Line (Revenue)",
            _heading(cfg): format_money(figs.rev_budget, cur, places),
            "Actual": format_money(figs.rev_actual, cur, places),
            f"Variance ({sym})": format_money(figs.rev_var, cur, places),
            "Outcome": "In line" if figs.rev_var == 0 else "Beat" if figs.rev_var > 0 else "Miss",
        },
        {
            "Section": "2. Cost (Expenses)",
            _heading(cfg): format_money(figs.exp_budget, cur, places),
            "Actual": format_money(figs.exp_actual, cur, places),
            f"Variance ({sym})": format_money(figs.exp_var, cur, places),
            "Outcome": "In line" if figs.exp_var == 0 else "Overrun" if figs.exp_var > 0 else "Savings",
        },
        {
            "Section": "3. Bottom-Line (Operating Profit)",
            _heading(cfg): format_money(figs.budget_profit, cur, places),
            "Actual": format_money(figs.actual_profit, cur, places),
            f"Variance ({sym})": format_money(figs.net_impact, cur, places),
            "Outcome": "Neutral" if figs.net_impact == 0 else "Favorable" if figs.net_impact > 0 else "Unfavorable",
        },
    ]


def _handle_executive_memo(session: Session) -> Response:
    """Generate an executive-ready variance briefing memo suitable for CFO and board reporting."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    figs = _memo_figures(result)

    # Find top revenue driver & drag
    rev_rows = [r for r in _detail_rows(result) if r.line_type == LineType.REVENUE]
    top_rev_beat = max((r for r in rev_rows if r.variance_dollars > 0), key=lambda r: r.variance_dollars, default=None)
    top_rev_miss = min((r for r in rev_rows if r.variance_dollars < 0), key=lambda r: r.variance_dollars, default=None)

    # Find largest cost overrun & largest saving
    exp_rows = [r for r in _detail_rows(result) if r.line_type == LineType.EXPENSE]
    top_exp_over = max((r for r in exp_rows if r.variance_dollars > 0), key=lambda r: r.variance_dollars, default=None)
    top_exp_save = min((r for r in exp_rows if r.variance_dollars < 0), key=lambda r: r.variance_dollars, default=None)

    memo_lines = _memo_overview(result, figs, places, top_rev_beat=top_rev_beat, top_rev_miss=top_rev_miss)
    _add_memo_costs_and_governance(memo_lines, result, figs, places, top_exp_over=top_exp_over, top_exp_save=top_exp_save)
    _add_memo_actions(memo_lines, result, top_exp_over=top_exp_over, top_rev_beat=top_rev_beat)

    memo_text = "\n".join(memo_lines)
    period_slug = _period_slug(cfg.period)
    filename = f"executive_memo_{period_slug}.md"

    return Response(
        text=memo_text,
        table=_memo_table(cfg, figs, places),
        chips=["Waterfall", "Export report", "Export csv", "Summary"],
        download={filename: memo_text},
        phase=Phase.EXPLORING,
    )


def _handle_driver_summary(session: Session) -> Response:
    """Provide an overview of all causal driver decompositions in the dataset."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency

    rows_with_drivers = [r for r in result.rows if r.driver_evidence is not None]
    rows_reconciled = [r for r in rows_with_drivers if r.driver_evidence and r.driver_evidence.reconciles]

    table_data: list[dict[str, str]] = []
    for r in result.rows:
        if r.driver_evidence is not None:
            ev = r.driver_evidence
            status_str = "Reconciled" if ev.reconciles else "Not reconciled"
            model_label = ev.label
            comps = ", ".join(f"{k}: {format_money(v, cur, places)}" for k, v in ev.components)
        else:
            status_str = "No driver data"
            model_label = "None"
            comps = "—"

        table_data.append({
            "Line Item": safe_inline(r.line_item),
            "Variance": format_money(r.variance_dollars, cur, places),
            "Model": model_label,
            "Reconciliation": status_str,
            "Driver Components": comps,
        })

    coverage_pct = ((ratio(Decimal(len(rows_reconciled)), Decimal(len(result.material_rows))) * Decimal(100))
                    if result.material_rows else Decimal(100))

    with_data = f"{len(rows_with_drivers)} with driver data"
    text = (
        f"**Causal Driver Models Overview**\n\n"
        f"• **Lines with a reconciled driver model:** **{len(rows_reconciled)}** of **{len(result.rows)}** "
        f"({with_data}).\n"
        f"• **Material variances covered:** **{coverage_pct:.1f}%** have a reconciled driver breakdown.\n\n"
        f"A driver model splits a variance from {_noun(cfg)} into its causes, such as price and volume, "
        "or rate and volume."
    )
    view = figures_view(
        "Driver data",
        figures=[figure("Reconciled driver models", f"{len(rows_reconciled)} of {len(result.rows)}", with_data.capitalize()),
                 figure("Material variances covered", f"{coverage_pct:.1f}%")],
        notes=[f"A driver model splits a variance from {_noun(cfg)} into its causes, such as price and volume, "
               "or rate and volume."],
        table_title="Driver data by line",
    )

    chips = ["Waterfall", "Biggest risks", "Summary", "Export report"]
    return Response(text=text, table=table_data, chips=chips, phase=Phase.EXPLORING, view=view)


def _handle_tldr(session: Session) -> Response:
    """Provide a punchy, conversational 2-sentence executive takeaway."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency

    with financial_context() as context:
        context.traps[Inexact] = False
        rev_var = result.revenue.actual - result.revenue.budget
        exp_var = result.expenses.actual - result.expenses.budget
        actual_profit = result.revenue.actual - result.expenses.actual
        budget_profit = result.revenue.budget - result.expenses.budget
        net_impact = actual_profit - budget_profit
        impact_pct = (ratio(net_impact, abs(budget_profit)) * Decimal(100)) if budget_profit != 0 else None
        margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else None

    basis = "plan" if _is_budget(cfg) else f"the {_noun(cfg)}"
    # A zero difference is neither a beat nor a saving: say it is on plan.
    if net_impact == 0:
        outcome = (f"exactly matching {'the planned budget' if _is_budget(cfg) else _noun(cfg)} "
                   f"of {format_money(budget_profit, cur, places)}")
    else:
        beat_word = "beat" if net_impact > 0 else "shortfall"
        outcome = (f"delivering a **{format_money(abs(net_impact), cur, places)} {beat_word}** "
                   f"({_pct_text(impact_pct, '+.1f')} vs. {'planned budget' if _is_budget(cfg) else _noun(cfg)} "
                   f"of {format_money(budget_profit, cur, places)})")
    if rev_var == 0:
        revenue_clause = f"Top-line revenue came in exactly on {basis}"
    else:
        rev_word = "outperformed" if rev_var > 0 else "underperformed"
        revenue_clause = f"Top-line revenue {rev_word} {basis} by {format_money(abs(rev_var), cur, places)}"
    if exp_var == 0:
        expense_clause = f"operating expenses came in exactly on {basis}"
    else:
        exp_word = "generated savings of" if exp_var < 0 else "overspent by"
        expense_clause = f"operating expenses {exp_word} {format_money(abs(exp_var), cur, places)}"

    # Identify top accounts
    rev_rows = [r for r in _detail_rows(result) if r.line_type == LineType.REVENUE]
    exp_rows = [r for r in _detail_rows(result) if r.line_type == LineType.EXPENSE]
    top_rev = max(rev_rows, key=lambda r: abs(r.variance_dollars), default=None)
    top_exp = max(exp_rows, key=lambda r: abs(r.variance_dollars), default=None)

    def described(row: AnalyzedRow) -> str:
        if row.status == Status.NEUTRAL:
            on_basis = "on budget" if _is_budget(cfg) else f"in line with the {_noun(cfg)}"
            return f"**{safe_inline(row.line_item)}** ({on_basis})"
        if row.line_type == LineType.REVENUE:
            word = "beat" if row.variance_dollars > 0 else "miss"
        else:
            word = "overrun" if row.variance_dollars > 0 else "saving"
        return f"**{safe_inline(row.line_item)}** ({word} of {format_money(abs(row.variance_dollars), cur, places)})"

    driver_context = ""
    if top_rev and top_exp:
        driver_context = (f" The largest revenue swing was {described(top_rev)}; "
                          f"the largest expense swing was {described(top_exp)}.")
    note = _unclassified_note(result)
    if note:
        driver_context += f"\n\n{note}"

    text = (
        f"**The Executive TL;DR for {cfg.period}:**\n\n"
        f"Operating Profit finished at **{format_money(actual_profit, cur, places)}**, {outcome} "
        f"with operating margin standing at **{_pct_text(margin)}**. "
        f"{revenue_clause}, while {expense_clause}.{driver_context}"
    )

    chips = ["Executive memo", "Waterfall", "Sensitivity", "Summary"]
    return Response(text=text, chips=chips, phase=Phase.EXPLORING)


def _handle_profitability(session: Session) -> Response:
    """Deliver a clear, conversational evaluation of bottom-line profitability and black vs. red standing."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    with financial_context() as context:
        context.traps[Inexact] = False
        actual_profit = result.revenue.actual - result.expenses.actual
        budget_profit = result.revenue.budget - result.expenses.budget
        net_impact = actual_profit - budget_profit
        actual_margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else None
        budget_margin = (ratio(budget_profit, result.revenue.budget) * Decimal(100)) if result.revenue.budget != 0 else None
        margin_delta = _pct_change(actual_margin, budget_margin)

    is_black = actual_profit >= 0
    stance = "firmly **in the black** (profitable)" if is_black else "currently **in the red** (operating loss)"
    status = _in_line(cfg) if net_impact == 0 else "favorable beat" if net_impact > 0 else "unfavorable shortfall"

    text = (
        f"**Profitability Standing: {cfg.period}**\n\n"
        f"Operations are {stance}!\n\n"
        f"• **Actual Operating Profit:** **{format_money(actual_profit, cur, places)}** (operating margin: "
        f"**{_pct_text(actual_margin)}**)\n"
        f"• **{_planned(cfg)} Operating Profit:** {format_money(budget_profit, cur, places)} "
        f"({'Planned' if _is_budget(cfg) else _heading(cfg)} margin: {_pct_text(budget_margin)})\n"
        f"• **Variance vs. {_heading(cfg)}:** **{format_money(net_impact, cur, places)}** ({status}; margin change: "
        f"{_pct_text(margin_delta, '+.1f', ' pts')})\n\n"
        f"Operating profit reflects gross commercial revenues ({format_money(result.revenue.actual, cur, places)}) "
        f"less total operating expenses ({format_money(result.expenses.actual, cur, places)})."
    )

    table = [
        {
            "Metric": "Total Revenue",
            _heading(cfg): format_money(result.revenue.budget, cur, places),
            "Actual": format_money(result.revenue.actual, cur, places),
            f"Variance ({sym})": format_money(result.revenue.actual - result.revenue.budget, cur, places),
            "Flow": "Inflow",
        },
        {
            "Metric": "Total Expenses",
            _heading(cfg): format_money(result.expenses.budget, cur, places),
            "Actual": format_money(result.expenses.actual, cur, places),
            f"Variance ({sym})": format_money(result.expenses.actual - result.expenses.budget, cur, places),
            "Flow": "Outflow",
        },
        {
            "Metric": "Operating Profit",
            _heading(cfg): format_money(budget_profit, cur, places),
            "Actual": format_money(actual_profit, cur, places),
            f"Variance ({sym})": format_money(net_impact, cur, places),
            "Flow": "Retained Margin",
        },
    ]

    chips = ["Waterfall", "Run rate", "Executive memo", "Summary"]
    return Response(text=_with_unclassified_note(text, result), table=table, chips=chips, phase=Phase.EXPLORING)
