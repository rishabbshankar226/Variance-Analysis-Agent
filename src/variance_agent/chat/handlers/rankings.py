"""Risks, wins, concentration and comparisons between lines.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from decimal import Decimal, Inexact
from variance_agent.currencies import CURRENCY_SYMBOLS
from variance_agent.models import LineType, Status
from variance_agent.numeric import financial_context, ratio
from ..intent import ParsedIntent, find_line_item
from ..responses import (
    NOT_YET_LABELED_PHRASE,
    Response,
    format_money,
    format_pct,
    format_threshold_amount,
    format_threshold_pct,
    report_places,
    row_to_table_dict,
    safe_inline,
    status_label,
)
from ..session import Phase, Session
from ..views import figures_view, pair
from ._common import (
    _detail_rows,
    _fu,
    _heading,
    _is_budget,
    _noun,
    _pct_text,
    _plain_heading,
    _variance_percent,
    _with_unclassified_note,
)
from ._items import _resolve_item_query


def _handle_biggest_risks(session: Session) -> Response:
    """Identify the top material unfavorable variances and mitigation paths."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    unfavorable = [
        row for row in result.material_rows if row.status == Status.UNFAVORABLE
    ]
    session.last_table_items = [row.line_item for row in unfavorable]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not unfavorable:
        return Response(
            text="**No Material Risks Detected**\n\n"
                 "There are zero material unfavorable variances exceeding your thresholds "
                 f"({format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or "
                 f"{format_threshold_pct(cfg.percent_threshold)}). "
                 + ("All revenue targets and expense allocations " if _is_budget(cfg)
                    else "All revenue and expense lines ")
                 + f"performed within {_noun(cfg)} tolerance.",
            chips=["Summary", "Biggest wins", "Show all material"],
            phase=Phase.EXPLORING,
        )

    lines = [
        f"**Top Financial Risks ({len(unfavorable)} material unfavorable item{'s' if len(unfavorable) != 1 else ''})**\n\n"
        f"These line items represent the most significant negative deviations from {_noun(cfg)}:\n"
    ]

    for i, row in enumerate(unfavorable[:3], start=1):
        driver_status = "No driver breakdown"
        if row.driver_evidence is not None:
            driver_status = "Supported causal model" if row.driver_evidence.reconciles else "Hypothesis (unreconciled)"

        type_label = "Revenue shortfall" if row.line_type == LineType.REVENUE else "Cost overrun"
        lines.append(
            f"**{i}. {safe_inline(row.line_item)}** ({type_label})\n"
            f"• Actual: {format_money(row.actual, cfg.currency, places)} vs. {_heading(cfg)}: "
            f"{format_money(row.budget, cfg.currency, places)}\n"
            f"• Variance: **{format_money(row.variance_dollars, cfg.currency, places)}** "
            f"({format_pct(row.budget, row.variance_dollars, row.percent_label)})\n"
            f"• Evidence: *{driver_status}*\n"
        )

    lines.append(
        f"The largest is **{safe_inline(unfavorable[0].line_item)}**. "
        f"Ask `why {safe_inline(unfavorable[0].line_item)}` to see what drove it."
    )

    chips = [f"Why {unfavorable[0].line_item}?"]
    if len(unfavorable) > 1:
        chips.append(f"Why {unfavorable[1].line_item}?")
    chips.extend(["Drivers", "Summary"])

    shown = unfavorable[:3]
    count = f"{len(unfavorable)} material unfavorable variance{'s' if len(unfavorable) != 1 else ''}"
    view = figures_view(
        "Top financial risks",
        context=[pair("Compared with", _plain_heading(cfg))],
        notes=[f"The largest is {unfavorable[0].line_item}. Ask \u201cwhy {unfavorable[0].line_item}\u201d to see what drove it."],
        table_title=count.capitalize() + (f", the largest {len(shown)} shown" if len(unfavorable) > len(shown) else ""),
    )
    table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in shown]
    return Response(text="\n".join(lines), table=table, chips=chips, phase=Phase.EXPLORING, view=view)


def _handle_biggest_wins(session: Session) -> Response:
    """Highlight the largest material favorable variances."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    favorable = [
        row for row in result.material_rows if row.status == Status.FAVORABLE
    ]
    session.last_table_items = [row.line_item for row in favorable]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not favorable:
        return Response(
            text="**No Material Favorable Variances**\n\n"
                 "No line items exceeded the favorable materiality thresholds. "
                 "Check `summary` or lower thresholds with `threshold $X or Y%` to explore smaller variances.",
            chips=["Summary", "Biggest risks", "Material"],
            phase=Phase.EXPLORING,
        )

    lines = [
        f"**Top Positive Performers ({len(favorable)} material favorable item{'s' if len(favorable) != 1 else ''})**\n\n"
        "These line items drove the strongest positive operating performance:\n"
    ]

    for i, row in enumerate(favorable[:3], start=1):
        nature = "Revenue beat" if row.line_type == LineType.REVENUE else "Cost savings / underspend"
        lines.append(
            f"**{i}. {safe_inline(row.line_item)}** ({nature})\n"
            f"• Actual: {format_money(row.actual, cfg.currency, places)} vs. {_heading(cfg)}: "
            f"{format_money(row.budget, cfg.currency, places)}\n"
            f"• Favorable Variance: **{format_money(row.variance_dollars, cfg.currency, places)}** "
            f"({format_pct(row.budget, row.variance_dollars, row.percent_label)})\n"
        )

    lines.append(f"**Note:** An expense below {_noun(cfg)} can be a lasting saving or spending that moves to a later period; the figures "
                 "alone do not say which.")

    chips = [f"Why {favorable[0].line_item}?", "Summary", "Biggest risks"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_top_percent(session: Session) -> Response:
    """Show line items sorted by largest percentage variance."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    pct_rows = [r for r in _detail_rows(result) if r.variance_percent is not None]
    if not pct_rows:
        return Response(
            text=(
                "No line items with non-zero budgets were found."
                if _is_budget(cfg)
                else f"No line items with a non-zero {_noun(cfg)} were found."
            ),
            chips=["Summary"],
            phase=Phase.EXPLORING,
        )

    pct_rows.sort(key=lambda r: abs(r.variance_percent or Decimal(0)), reverse=True)
    session.last_table_items = [row.line_item for row in pct_rows[:5]]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [
        row_to_table_dict(row, cfg.currency, places, _heading(cfg))
        for row in pct_rows[:5]
    ]

    return Response(
        text="**Top Line Items by Percentage Variance** (Largest relative swings):\n",
        table=table,
        chips=["Material", "Top 3 by dollars", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_metrics_count(session: Session) -> Response:
    """Return a quantitative breakdown of line items and materiality."""
    result = session.result
    assert result is not None

    rows = _detail_rows(result)
    total_rows = len(rows)
    mat_rows = len(result.material_rows)
    mat_pct = (mat_rows / total_rows * 100) if total_rows > 0 else 0

    f_count = sum(1 for r in rows if r.status == Status.FAVORABLE)
    u_count = sum(1 for r in rows if r.status == Status.UNFAVORABLE)
    n_count = sum(1 for r in rows if r.status == Status.NEUTRAL)

    rev_count = sum(1 for r in rows if r.line_type == LineType.REVENUE)
    exp_count = sum(1 for r in rows if r.line_type == LineType.EXPENSE)
    unc_count = sum(1 for r in rows if r.line_type == LineType.UNCLASSIFIED)

    lines = [
        "**Portfolio Metrics Breakdown**\n",
        f"• **Total Line Items:** {total_rows}",
        f"• **Material Variances:** {mat_rows} ({mat_pct:.1f}% of total items)",
        f"• **Direction:** {f_count} Favorable, {u_count} Unfavorable, {n_count} Neutral",
        f"• **Classification:** {rev_count} Revenue, {exp_count} Expense, {unc_count} {NOT_YET_LABELED_PHRASE}",
        f"• **Data Warnings:** {len(result.warnings)} issue{'s' if len(result.warnings) != 1 else ''}",
    ]

    chips = ["Material", "Summary", "Biggest risks"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_compare(session: Session, intent: ParsedIntent) -> Response:
    """Compare two line items side-by-side."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    line_items = [r.line_item for r in result.rows]

    name1 = intent.captures.get("item1", "").strip().strip("'\"?")
    name2 = intent.captures.get("item2", "").strip().strip("'\"?")
    name1_lower = name1.lower()
    name2_lower = name2.lower()

    # Macro Case 1: Actual vs Budget
    actual_terms = {"actual", "actuals", "act"}
    budget_terms = {"budget", "budgeted", "plan", "target", "targets", "bgt"}
    if (name1_lower in actual_terms and name2_lower in budget_terms) or (name1_lower in budget_terms and name2_lower in actual_terms):
        with financial_context() as context:
            context.traps[Inexact] = False
            base_profit = result.revenue.budget - result.expenses.budget
            actual_profit = result.revenue.actual - result.expenses.actual
            net_impact = actual_profit - base_profit
            rev_var = result.revenue.actual - result.revenue.budget
            exp_var = result.expenses.actual - result.expenses.budget
            sym = CURRENCY_SYMBOLS.get(cfg.currency, "$")

            macro_table = [
                {
                    "Metric": "Total Revenue",
                    _heading(cfg): format_money(result.revenue.budget, cfg.currency, places),
                    "Actual": format_money(result.revenue.actual, cfg.currency, places),
                    f"Variance ({sym})": format_money(rev_var, cfg.currency, places),
                    "Variance (%)": _pct_text(_variance_percent(rev_var, result.revenue.budget), "+.1f"),
                    "Status": _fu(rev_var),
                },
                {
                    "Metric": "Total Expenses",
                    _heading(cfg): format_money(result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(result.expenses.actual, cfg.currency, places),
                    f"Variance ({sym})": format_money(exp_var, cfg.currency, places),
                    "Variance (%)": _pct_text(_variance_percent(exp_var, result.expenses.budget), "+.1f"),
                    "Status": _fu(exp_var, higher_is_better=False),
                },
                {
                    "Metric": "Operating Profit",
                    _heading(cfg): format_money(base_profit, cfg.currency, places),
                    "Actual": format_money(actual_profit, cfg.currency, places),
                    f"Variance ({sym})": format_money(net_impact, cfg.currency, places),
                    "Variance (%)": f"{(ratio(net_impact, abs(base_profit)) * 100):+.1f}%" if base_profit != 0 else "N/A",
                    "Status": _fu(net_impact),
                },
            ]
        status_word = "beat" if net_impact >= 0 else "shortfall"
        target = "budget target" if _is_budget(cfg) else _noun(cfg)
        return Response(
            text=_with_unclassified_note(
                f"**Executive Macro Comparison: Actual vs. {_heading(cfg)}**\n\n"
                f"Operating profit finished at **{format_money(actual_profit, cfg.currency, places)}**, "
                + ("**in line with**" if net_impact == 0 else
                   f"representing a **{format_money(abs(net_impact), cfg.currency, places)} {status_word}** against")
                + f" the {target} of {format_money(base_profit, cfg.currency, places)}.", result),
            table=macro_table,
            chips=["Waterfall", "Run rate", "Sensitivity", "Summary"],
            phase=Phase.EXPLORING,
        )

    # Macro Case 2: Revenue vs Expenses
    rev_terms = {"revenue", "revenues", "sales", "topline", "top line", "rev"}
    exp_terms = {"expense", "expenses", "cost", "costs", "spend", "opex", "exp"}
    if (name1_lower in rev_terms and name2_lower in exp_terms) or (name1_lower in exp_terms and name2_lower in rev_terms):
        with financial_context() as context:
            context.traps[Inexact] = False
            actual_profit = result.revenue.actual - result.expenses.actual
            margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else None
            cost_ratio = (ratio(result.expenses.actual, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else None

            macro_table = [
                {
                    "Category": "Total Revenue",
                    _heading(cfg): format_money(result.revenue.budget, cfg.currency, places),
                    "Actual": format_money(result.revenue.actual, cfg.currency, places),
                    "Operating Flow": "Top-Line Inflow",
                    "% of Revenue": "100.0%" if result.revenue.actual != 0 else "N/A",
                },
                {
                    "Category": "Total Expenses",
                    _heading(cfg): format_money(result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(result.expenses.actual, cfg.currency, places),
                    "Operating Flow": "Operating Outflow",
                    "% of Revenue": _pct_text(cost_ratio),
                },
                {
                    "Category": "Operating Profit",
                    _heading(cfg): format_money(result.revenue.budget - result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(actual_profit, cfg.currency, places),
                    "Operating Flow": "Net Retained Margin",
                    "% of Revenue": _pct_text(margin),
                },
            ]
        return Response(
            text=_with_unclassified_note(
                f"**Macro Financial Comparison: Revenue vs. Expenses**\n\n"
                f"Actual Revenue of **{format_money(result.revenue.actual, cfg.currency, places)}** offset by Operating Expenses of "
                f"**{format_money(result.expenses.actual, cfg.currency, places)}** yields an **Operating Profit of "
                f"{format_money(actual_profit, cfg.currency, places)}** "
                f"({_pct_text(margin)} operating margin; cost-to-income ratio of {_pct_text(cost_ratio)}).", result),
            table=macro_table,
            chips=["Waterfall", "Run rate", "Sensitivity", "Summary"],
            phase=Phase.EXPLORING,
        )

    matches1 = find_line_item(_resolve_item_query(name1, session), line_items)
    matches2 = find_line_item(_resolve_item_query(name2, session), line_items)

    if not matches1:
        return Response(
            text=f"Could not find a line item matching '{safe_inline(name1)}'.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )
    if not matches2:
        return Response(
            text=f"Could not find a line item matching '{safe_inline(name2)}'.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )

    if len(matches1) > 1:
        return Response(
            text=f"Multiple matches for '{safe_inline(name1)}': {', '.join(matches1)}. Please be more specific.",
            chips=["Summary"],
            phase=Phase.EXPLORING,
        )
    if len(matches2) > 1:
        return Response(
            text=f"Multiple matches for '{safe_inline(name2)}': {', '.join(matches2)}. Please be more specific.",
            chips=["Summary"],
            phase=Phase.EXPLORING,
        )

    row1 = next(r for r in result.rows if r.line_item == matches1[0])
    row2 = next(r for r in result.rows if r.line_item == matches2[0])
    session.last_table_items = [row1.line_item, row2.line_item]
    session.last_focused_item = row1.line_item

    if row1.line_item == row2.line_item:
        table = [row_to_table_dict(row1, cfg.currency, places, _heading(cfg))]
        return Response(
            text=f"Comparing '**{safe_inline(row1.line_item)}**' against itself. Account details:",
            table=table,
            chips=[f"Why {row1.line_item}?", "Summary"],
            phase=Phase.EXPLORING,
        )

    table = [
        row_to_table_dict(row1, cfg.currency, places, _heading(cfg)),
        row_to_table_dict(row2, cfg.currency, places, _heading(cfg)),
    ]

    diff_var = abs(row1.variance_dollars) - abs(row2.variance_dollars)
    if diff_var > 0:
        lead = (f"**{safe_inline(row1.line_item)}** has the larger absolute variance swing by "
                f"{format_money(diff_var, cfg.currency, places)}.")
    elif diff_var < 0:
        lead = (f"**{safe_inline(row2.line_item)}** has the larger absolute variance swing by "
                f"{format_money(abs(diff_var), cfg.currency, places)}.")
    else:
        lead = "Both line items have identical absolute variance swings."

    return Response(
        text=f"**Side-by-Side Comparison: {safe_inline(row1.line_item)} vs. {safe_inline(row2.line_item)}**\n\n{lead}",
        table=table,
        chips=[f"Why {row1.line_item}?", f"Why {row2.line_item}?", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_concentration(session: Session) -> Response:
    """Analyze variance concentration using Pareto distribution (80/20 rule)."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    with financial_context():
        total_abs_var = sum((abs(r.variance_dollars) for r in _detail_rows(result)), Decimal(0))

    if total_abs_var == Decimal(0):
        return Response(
            text=f"**Zero Variance Volatility:** All line items performed exactly to {_noun(cfg)}.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )

    # Sort rows by absolute variance descending
    sorted_rows = sorted(_detail_rows(result), key=lambda r: abs(r.variance_dollars), reverse=True)
    top_3 = sorted_rows[:3]
    session.last_table_items = [row.line_item for row in top_3]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    with financial_context():
        top_3_abs = sum((abs(r.variance_dollars) for r in top_3), Decimal(0))
        top_3_pct = ratio(top_3_abs, total_abs_var) * Decimal("100")

    lines = [
        "**Variance Concentration Analysis (Pareto Distribution)**\n",
        f"• **Total Portfolio Absolute Variance:** {format_money(total_abs_var, cfg.currency, places)}",
        f"• **Top 3 Concentration:** **{top_3_pct:.1f}%** of all variance volatility is driven by just 3 line items:\n",
    ]

    for i, row in enumerate(top_3, start=1):
        with financial_context():
            row_share = ratio(abs(row.variance_dollars), total_abs_var) * Decimal("100")
        lines.append(
            f"  {i}. **{safe_inline(row.line_item)}:** {format_money(row.variance_dollars, cfg.currency, places)} "
            f"({row_share:.1f}% of total volatility, {status_label(row.status)})"
        )

    if top_3_pct >= Decimal("70"):
        insight = (
            "\n**High concentration.** These three lines account for "
            f"{top_3_pct:.1f}% of the total variance."
        )
    else:
        insight = (
            "\n**Spread out.** The variance is spread across many lines rather than held in a few."
        )
    lines.append(insight)

    chips = [f"Why {top_3[0].line_item}?", "Biggest risks", "Summary"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)
