"""Revenue, expense and budget status questions.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from variance_agent.models import ComparisonBasis, LineType, Status
from variance_agent.numeric import financial_context, ratio
from ..responses import (
    NOT_YET_LABELED,
    Response,
    format_money,
    format_pct,
    report_places,
    safe_inline,
    status_label,
    type_label,
)
from ..session import Phase, Session
from ._common import _detail_rows, _heading, _in_line, _is_budget, _noun, _planned, _with_unclassified_note


@dataclass(frozen=True)
class _UnbudgetedWording:
    heading: str
    empty_state: str
    intro: str  # '{zero}' is the zero amount in the report money format
    note: str
    revenue_heading: str
    revenue_intro: str  # '{zero}' as above


_UNBUDGETED_WORDING: dict[ComparisonBasis, _UnbudgetedWording] = {
    ComparisonBasis.BUDGET: _UnbudgetedWording(
        heading="Unbudgeted Spending",
        empty_state="All accounts with actual activity had an approved baseline budget.",
        intro="These line items had zero approved budget ({zero}) but incurred realized expenditures:",
        note="These lines had spending with no budget allocated to them.",
        revenue_heading="Unbudgeted revenue",
        revenue_intro="earned with a zero plan ({zero}); favorable, but confirm it belongs in this period:",
    ),
    ComparisonBasis.FORECAST: _UnbudgetedWording(
        heading="Spending Not in Forecast",
        empty_state="All accounts with actual activity had a forecast amount.",
        intro="These line items had a zero forecast ({zero}) but incurred realized expenditures:",
        note="These lines had spending the latest forecast did not include.",
        revenue_heading="Revenue not in forecast",
        revenue_intro="earned with a zero forecast ({zero}); favorable, but confirm it belongs in this period:",
    ),
    ComparisonBasis.PRIOR_PERIOD: _UnbudgetedWording(
        heading="New Spending This Period",
        empty_state="All accounts with actual activity also had activity in the prior period.",
        intro="These line items had zero activity ({zero}) in the prior period but incurred realized expenditures:",
        note="These lines had spending with none in the prior period; the file does not say whether it is one-off or recurring.",
        revenue_heading="New revenue this period",
        revenue_intro="earned with no prior-period activity ({zero}); favorable, but confirm it belongs in this period:",
    ),
}


def _handle_revenue_status(session: Session) -> Response:
    """Analyze revenue performance against budget target."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    revenue_rows = [
        r for r in _detail_rows(result)
        if r.line_type == LineType.REVENUE and not r.excluded_from_aggregation
    ]
    session.last_table_items = [row.line_item for row in revenue_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not revenue_rows:
        return Response(
            text="No classified Revenue rows exist in this dataset.",
            chips=["Summary", "Expenses"],
            phase=Phase.EXPLORING,
        )

    if any(r.line_type == LineType.UNCLASSIFIED for r in result.rows):
        return Response(
            text="Total revenue cannot be certified because there are still unclassified line items. Classify them first.",
            chips=[NOT_YET_LABELED, "Summary"],
            phase=Phase.EXPLORING,
            level="error",
        )

    rev = result.revenue
    beat = rev.actual >= rev.budget
    diff = rev.actual - rev.budget

    pct_text = format_pct(rev.budget, rev.variance_dollars, rev.percent_label)
    if beat:
        achieved = "Revenue Target Achieved" if _is_budget(cfg) else f"Revenue Ahead of {_heading(cfg)}"
        verdict = f"**{achieved}: Beat {_heading(cfg)} by {format_money(diff, cfg.currency, places)} ({pct_text})**"
    else:
        missed = "Revenue Target Missed" if _is_budget(cfg) else f"Revenue Behind {_heading(cfg)}"
        verdict = f"**{missed}: Shortfall of {format_money(abs(diff), cfg.currency, places)} ({pct_text})**"

    lines = [
        verdict + "\n",
        f"• **{_planned(cfg)} Revenue:** {format_money(rev.budget, cfg.currency, places)}",
        f"• **Actual Revenue:** {format_money(rev.actual, cfg.currency, places)}",
    ]
    if rev.budget > 0:
        rate = ratio(rev.actual, rev.budget) * Decimal("100")
        lines.append(f"• **Achievement Rate:** {rate:.1f}% of {_noun(cfg)}")
    elif rev.budget < 0:
        lines.append(f"• **Achievement Rate:** N/A (the {_noun(cfg)} is negative, so a ratio is not meaningful)")
    lines.append(f"• **Status:** {status_label(rev.status)}\n")
    lines.append("**Revenue Breakdown:**")

    for row in revenue_rows:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** {format_money(row.actual, cfg.currency, places)} vs. "
            f"{format_money(row.budget, cfg.currency, places)} "
            f"({format_money(row.variance_dollars, cfg.currency, places)}, {status_label(row.status)})"
        )

    chips = ["Expenses", "Summary", "Show all revenue"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_expense_status(session: Session) -> Response:
    """Analyze expense performance against budget allocation."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    expense_rows = [
        r for r in _detail_rows(result)
        if r.line_type == LineType.EXPENSE and not r.excluded_from_aggregation
    ]
    session.last_table_items = [row.line_item for row in expense_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not expense_rows:
        return Response(
            text="No classified Expense rows exist in this dataset.",
            chips=["Summary", "Revenue"],
            phase=Phase.EXPLORING,
        )

    if any(r.line_type == LineType.UNCLASSIFIED for r in result.rows):
        return Response(
            text="Total expenses cannot be certified because there are still unclassified line items.",
            chips=[NOT_YET_LABELED, "Summary"],
            phase=Phase.EXPLORING,
            level="error",
        )

    exp = result.expenses
    under_budget = exp.actual <= exp.budget
    diff = exp.actual - exp.budget

    if under_budget:
        verdict = (f"**Expenses Remained Under {_heading(cfg)}: Saved {format_money(abs(diff), cfg.currency, places)} "
                   f"({format_pct(exp.budget, exp.variance_dollars, exp.percent_label)})**")
    else:
        verdict = (f"**Expenses Exceeded {_heading(cfg)}: Overspend of {format_money(diff, cfg.currency, places)} "
                   f"({format_pct(exp.budget, exp.variance_dollars, exp.percent_label)})**")

    lines = [
        verdict + "\n",
        f"• **{_planned(cfg)} Expenses:** {format_money(exp.budget, cfg.currency, places)}",
        f"• **Actual Expenses:** {format_money(exp.actual, cfg.currency, places)}",
    ]
    utilization = "Budget Utilization" if _is_budget(cfg) else f"Spend vs. {_heading(cfg)}"
    if exp.budget > 0:
        burn = ratio(exp.actual, exp.budget) * Decimal("100")
        lines.append(f"• **{utilization}:** {burn:.1f}%")
    elif exp.budget < 0:
        lines.append(f"• **{utilization}:** N/A (the {_noun(cfg)} is negative, so a ratio is not meaningful)")
    lines.append(f"• **Status:** {status_label(exp.status)}\n")

    overspent = sorted(
        (r for r in expense_rows if r.actual > r.budget),
        key=lambda r: r.variance_dollars, reverse=True,
    )
    if overspent:
        over_heading = "Over-Budget Accounts" if _is_budget(cfg) else f"Accounts Over {_heading(cfg)}"
        lines.append(f"**{over_heading}:**")
        for row in overspent[:5]:
            lines.append(
                f"• **{safe_inline(row.line_item)}:** {format_money(row.variance_dollars, cfg.currency, places)} over "
                f"({format_pct(row.budget, row.variance_dollars, row.percent_label)})"
            )
    else:
        lines.append(
            "All expense accounts operated at or below planned budgets."
            if _is_budget(cfg)
            else f"All expense accounts operated at or below the {_noun(cfg)}."
        )

    chips = ["Revenue", "Summary", "Biggest risks"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_budget_utilization(session: Session) -> Response:
    """Compute overall budget execution and spend velocity."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    noun = _noun(cfg)
    if _is_budget(cfg):
        title = "Budget Execution & Utilization Metrics"
        utilization = "Expense Budget Utilization"
        zero_note = "zero budgeted expenses"
    else:
        title = f"Spend vs. {_heading(cfg)} Metrics"
        utilization = f"Expense Spend vs. {_heading(cfg)}"
        zero_note = f"zero {noun} expenses"
    lines = [f"**{title}**\n"]

    if result.expenses.budget < 0:
        lines.append(f"• **{utilization}:** N/A (negative {noun} expenses; a utilization ratio is not meaningful)")
    elif result.expenses.budget != 0:
        util = ratio(result.expenses.actual, result.expenses.budget) * Decimal("100")
        diff = result.expenses.actual - result.expenses.budget
        status_text = (f"over {noun} by {format_money(diff, cfg.currency, places)}" if diff > 0
                       else f"under {noun} by {format_money(abs(diff), cfg.currency, places)}")
        lines.append(f"• **{utilization}:** **{util:.1f}%** ({status_text})")
    else:
        lines.append(f"• **{utilization}:** N/A ({zero_note})")

    if result.revenue.budget > 0:
        achieve = ratio(result.revenue.actual, result.revenue.budget) * Decimal("100")
        diff = result.revenue.actual - result.revenue.budget
        status_text = (_in_line(cfg) if diff == 0 else f"beat by {format_money(diff, cfg.currency, places)}" if diff > 0
                       else f"shortfall of {format_money(abs(diff), cfg.currency, places)}")
        achievement = "Revenue Target Achievement" if _is_budget(cfg) else f"Revenue vs. {_heading(cfg)}"
        lines.append(f"• **{achievement}:** **{achieve:.1f}%** ({status_text})")

    has_rev = any(r.line_type == LineType.REVENUE and not r.excluded_from_aggregation for r in result.rows)
    has_exp = any(r.line_type == LineType.EXPENSE and not r.excluded_from_aggregation for r in result.rows)
    classification_incomplete = any(r.line_type == LineType.UNCLASSIFIED for r in result.rows)

    if has_rev and has_exp and not classification_incomplete:
        impact = result.revenue.variance_dollars - result.expenses.variance_dollars
        direction = f"above {noun}" if impact > 0 else f"below {noun}" if impact < 0 else f"in line with {noun}"
        lines.append(
            f"• **Net Operating Impact:** {format_money(impact, cfg.currency, places)} ({direction})"
        )

    chips = ["Summary", "Biggest risks", "Biggest wins"]
    return Response(text=_with_unclassified_note("\n".join(lines), result), chips=chips, phase=Phase.EXPLORING)


def _handle_unbudgeted(session: Session) -> Response:
    """Identify accounts that incurred actual spending with zero approved budget."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    unbudgeted = [r for r in _detail_rows(result) if r.budget == Decimal(0) and r.actual > Decimal(0)]
    session.last_table_items = [row.line_item for row in unbudgeted]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    wording = _UNBUDGETED_WORDING[cfg.comparison_basis]
    if not unbudgeted:
        return Response(
            text=f"**No {wording.heading}:** {wording.empty_state}",
            chips=["Summary", "Material", "Expense status"],
            phase=Phase.EXPLORING,
        )

    zero = format_money(Decimal(0), cfg.currency, places)
    spending = [row for row in unbudgeted if row.line_type != LineType.REVENUE]
    revenue = [row for row in unbudgeted if row.line_type == LineType.REVENUE]
    lines: list[str] = []
    if spending:
        lines.append(
            f"**{wording.heading} Detected ({len(spending)} account{'s' if len(spending) != 1 else ''})**\n\n"
            f"{wording.intro.format(zero=zero)}\n"
        )
        for row in spending:
            lines.append(
                f"• **{safe_inline(row.line_item)}:** {format_money(row.actual, cfg.currency, places)} realized "
                f"({status_label(row.status)}, Type: {type_label(row.line_type)})"
            )
        lines.append(f"\n**Note:** {wording.note}")
    if revenue and not spending and not _is_budget(cfg):
        # Forecast/Prior Period: say plainly there is no such spending before listing revenue.
        lines.append(f"**No {wording.heading}.**\n")
    if revenue:
        lines.append(
            f"{chr(10) if spending else ''}**{wording.revenue_heading} ({len(revenue)} line{'s' if len(revenue) != 1 else ''}):** "
            f"{wording.revenue_intro.format(zero=zero)}\n"
        )
        for row in revenue:
            lines.append(f"• **{safe_inline(row.line_item)}:** {format_money(row.actual, cfg.currency, places)} earned")

    chips = [f"Why {unbudgeted[0].line_item}?", "Summary", "Warnings"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_cost_savings(session: Session) -> Response:
    """Show expense lines that preserved budget through favorable underspending."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    savings_rows = [
        r for r in _detail_rows(result)
        if r.line_type == LineType.EXPENSE and r.status == Status.FAVORABLE
    ]
    session.last_table_items = [row.line_item for row in savings_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not savings_rows:
        return Response(
            text=(
                "**No Cost Savings:** No expense accounts operated below their budgeted allocation."
                if _is_budget(cfg)
                else f"**No Cost Savings:** No expense accounts operated below the {_noun(cfg)}."
            ),
            chips=["Summary", "Expense status", "Biggest risks"],
            phase=Phase.EXPLORING,
        )

    savings_rows.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    with financial_context():
        total_savings = sum((abs(r.variance_dollars) for r in savings_rows), Decimal(0))

    lines = [
        f"**Expense Savings & Underspend Summary (Total: {format_money(total_savings, cfg.currency, places)})**\n\n"
        "These expense categories operated below approved spending limits, preserving cash and operating margin:\n"
    ]

    for row in savings_rows[:5]:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** Saved {format_money(abs(row.variance_dollars), cfg.currency, places)} "
            f"(Actual: {format_money(row.actual, cfg.currency, places)} vs. {_heading(cfg)}: "
            f"{format_money(row.budget, cfg.currency, places)}, "
            f"{format_pct(row.budget, row.variance_dollars, row.percent_label)})"
        )

    lines.append(
        "\n**Note:** An underspend can be a lasting saving or an invoice that arrives in a later period; the figures alone do not say "
        "which."
    )

    chips = [f"Why {savings_rows[0].line_item}?", "Expenses", "Summary"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_revenue_misses(session: Session) -> Response:
    """Highlight revenue accounts that failed to meet their targets."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    miss_rows = [
        r for r in _detail_rows(result)
        if r.line_type == LineType.REVENUE and r.status == Status.UNFAVORABLE
    ]
    session.last_table_items = [row.line_item for row in miss_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not miss_rows:
        return Response(
            text=(
                "**No Revenue Misses:** All revenue accounts met or exceeded planned targets."
                if _is_budget(cfg)
                else f"**No Revenue Misses:** All revenue accounts met or exceeded the {_noun(cfg)}."
            ),
            chips=["Summary", "Revenue status", "Biggest wins"],
            phase=Phase.EXPLORING,
        )

    miss_rows.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    with financial_context():
        total_shortfall = sum((abs(r.variance_dollars) for r in miss_rows), Decimal(0))

    lines = [
        f"**Revenue Shortfall & Misses (Total: {format_money(total_shortfall, cfg.currency, places)})**\n\n"
        + ("These revenue lines failed to reach approved baseline targets:\n" if _is_budget(cfg)
           else f"These revenue lines fell short of the {_noun(cfg)}:\n")
    ]

    for row in miss_rows[:5]:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** Shortfall of {format_money(abs(row.variance_dollars), cfg.currency, places)} "
            f"(Actual: {format_money(row.actual, cfg.currency, places)} vs. {_heading(cfg)}: "
            f"{format_money(row.budget, cfg.currency, places)}, "
            f"{format_pct(row.budget, row.variance_dollars, row.percent_label)})"
        )

    lines.append(
        "\n**Note:** `why [line]` splits a shortfall into volume and price when the file has those columns."
    )

    chips = [f"Why {miss_rows[0].line_item}?", "Revenue status", "Summary"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)
