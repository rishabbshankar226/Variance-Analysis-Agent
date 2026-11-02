"""Help, reset and the views of the results.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from variance_agent.models import AnalysisConfig, LineType, Status
from ..intent import ParsedIntent
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
    type_label,
)
from ..session import Phase, Session
from ._common import _detail_rows, _heading, _is_budget, _noun
from ._thresholds import _parse_partial_threshold_text
from .summary import _build_analysis_summary, _report_text
from .run import _run_analysis


def _action_plan(cfg: AnalysisConfig) -> str:
    """'the action plan' on Budget runs; elsewhere 'plan' would read as the comparison."""
    return "the action plan" if _is_budget(cfg) else "the response"


def _handle_help(session: Session) -> Response:
    """What the tool does and everything you can ask it."""
    text = (
        "**What you can ask**\n\n"
        "I compare each line's Actual against your budget, forecast or prior period, flag the gaps "
        "big enough to matter, and say whether each one helped or hurt profit. Every figure comes from "
        "exact, repeatable calculations, never estimates. It is built for FP&A analysts, controllers and "
        "anyone preparing a month-end or quarter-end variance review.\n\n"
        "**Analysis**\n"
        "• `memo` / `briefing`: a management briefing on the period, with a download\n"
        "• `waterfall` / `bridge`: the walk from budget to actual operating profit, step by step\n"
        "• `what if [line] [+/-X% or $Y]`: profit and margin if one line changes\n"
        "• `sensitivity`: operating profit under five revenue and expense swings\n"
        "• `run rate` / `project year end`: the annualised pace and a latest-estimate projection\n"
        "• `drivers` / `driver summary`: which lines have driver data, and whether it reconciles\n"
        "• `biggest risks`: the largest material unfavorable variances\n"
        "• `biggest wins`: the largest favorable variances\n"
        "• `revenue status`: revenue against budget, line by line\n"
        "• `expense status`: expenses against budget, and the largest overspends\n"
        "• `burn rate` / `budget utilization`: the share of the expense budget spent\n"
        "• `variance concentration` / `pareto`: the share of the total variance in the top three lines\n"
        "• `unbudgeted spend`: lines with spending and no budget\n"
        "• `cost savings`: expense lines below budget\n"
        "• `revenue misses`: revenue lines below budget\n"
        "• `highest percent`: the largest variances in percentage terms\n"
        "• `compare [line] vs [line]`: two lines side by side, actual against budget, or revenue against expenses\n"
        "• `sheets` / `sheet <name>`: list and switch Excel worksheets or PDF statements\n"
        "• `metrics`: line counts, the material share and the mix of lines\n\n"
        "**Concepts, any time**\n"
        "• `what is materiality?`: the dollar-or-percent test for what needs explaining\n"
        "• `favorable vs unfavorable`: why a revenue gain and an expense saving are both favorable\n"
        "• `what is net impact?`: how net operating impact is worked out\n"
        "• `budget vs forecast`: how a budget and a latest estimate differ\n"
        "• `timing vs permanent`: variances that reverse and variances that last\n"
        "• `operating leverage`: fixed and variable costs, and drop-through\n"
        "• `what are financial kpis?`: the measures a variance review reports\n"
        "• `what is driver decomposition?`: splitting a variance into price and volume\n"
        "• `audit trail`: what the audit file records, including source fingerprints\n\n"
        "**Exploring the results**\n"
        "• `summary`: the headline figures and net operating impact\n"
        "• `material`: every material variance\n"
        "• `unfavorable` / `favorable`: one status only\n"
        "• `revenue` / `expenses`: one type only\n"
        "• `top 3`: the largest variances by amount\n"
        "• `totals`: revenue and expense totals\n"
        "• `warnings`: data quality notes\n"
        "• `recommendations`: suggested next steps for the largest variances\n\n"
        "**One line in detail**\n"
        "• `why [line]`: what drove one line's variance\n"
        "• `detail [line]`: everything recorded for one line\n"
        "• `threshold $X or Y%`: run again with different materiality thresholds\n\n"
        "**Export and session**\n"
        "• `export report`: download the Markdown report\n"
        "• `export excel`: download the Excel workbook\n"
        "• `export csv`: download every row as CSV\n"
        "• `export audit`: download the audit file (JSON)\n"
        "• `report`: show the full report here\n"
        "• `new`: start over with a new file\n"
        "• `help`: show this list"
    )
    # Result questions only once there is a result; before that, offer what works without a file.
    chips = (["Summary", "Biggest risks", "Biggest wins", "Material"] if session.result is not None
             else ["Supported file formats", "What is materiality?", "Budget vs forecast"])
    return Response(
        text=text,
        chips=chips,
        phase=session.phase,
    )


def _handle_reset(session: Session) -> Response:
    """Reset the session for a new analysis."""
    session.reset()
    return Response(
        text="Session cleared. Upload a new file to begin.",
        phase=Phase.AWAITING_FILE,
    )


def _handle_summary(session: Session) -> Response:
    """Show executive summary."""
    return _build_analysis_summary(session)


def _handle_material(session: Session) -> Response:
    """Show all material variances."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    if not result.material_rows:
        return Response(
            text="No line item exceeded either configured materiality threshold.",
            chips=["Summary", "Show all revenue", "Show all expenses"],
            phase=Phase.EXPLORING,
        )

    session.last_table_items = [row.line_item for row in result.material_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [
        row_to_table_dict(row, cfg.currency, places, _heading(cfg))
        for row in result.material_rows
    ]

    chips = []
    if result.material_rows:
        chips.append(f"Why {result.material_rows[0].line_item}?")
    chips.extend(["Unfavorable", "Favorable", "Export report"])

    return Response(
        text=f"**Material Variances** (Threshold: {format_threshold_amount(cfg.dollar_threshold, cfg.currency)}"
             f" or {format_threshold_pct(cfg.percent_threshold)})",
        table=table,
        chips=chips,
        phase=Phase.EXPLORING,
    )


def _handle_filter_status(session: Session, status: Status) -> Response:
    """Filter rows by favorable/unfavorable status."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    filtered = [row for row in _detail_rows(result) if row.status == status]
    label = status_label(status)

    if not filtered:
        return Response(
            text=f"No {label.lower()} variances found.",
            chips=["Material", "Summary"],
            phase=Phase.EXPLORING,
        )

    # Sort by absolute variance descending
    filtered.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    session.last_table_items = [row.line_item for row in filtered]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in filtered]

    chips = [f"Why {filtered[0].line_item}?"]
    if status == Status.UNFAVORABLE:
        chips.append("Favorable")
    else:
        chips.append("Unfavorable")
    chips.append("Material")

    return Response(
        text=f"**{label} Variances** ({len(filtered)} item{'s' if len(filtered) != 1 else ''})",
        table=table,
        chips=chips,
        phase=Phase.EXPLORING,
    )


def _handle_filter_type(session: Session, line_type: LineType) -> Response:
    """Filter rows by Revenue/Expense/Unclassified type."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    filtered = [row for row in _detail_rows(result) if row.line_type == line_type]

    if not filtered:
        return Response(
            text=f"No {type_label(line_type)} rows found.",
            chips=["Material", "Summary"],
            phase=Phase.EXPLORING,
        )

    filtered.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    session.last_table_items = [row.line_item for row in filtered]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in filtered]

    return Response(
        text=f"**{type_label(line_type)} Items** ({len(filtered)} row{'s' if len(filtered) != 1 else ''})",
        table=table,
        chips=["Material", "Summary", "Export report"],
        phase=Phase.EXPLORING,
    )


def _handle_top_n(session: Session, intent: ParsedIntent) -> Response:
    """Show top N variances by absolute amount."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    count = int(intent.captures.get("count", "5"))
    if count < 1:
        return Response(
            text="Please ask for at least 1 line, for example `top 3`.",
            chips=["Top 3", "Top 5", "Summary"],
            phase=Phase.EXPLORING,
        )

    kind = intent.captures.get("kind", "").lower()
    line_type = (
        LineType.EXPENSE if kind.startswith(("expense", "cost"))
        else LineType.REVENUE if kind.startswith(("revenue", "sales", "income"))
        else None
    )
    rows = [row for row in _detail_rows(result) if line_type is None or row.line_type == line_type]
    if not rows:
        return Response(
            text=f"No {line_type.value if line_type else 'line item'} rows found.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )
    count = min(count, len(rows))

    sorted_rows = sorted(rows, key=lambda r: abs(r.variance_dollars), reverse=True)
    top = sorted_rows[:count]
    session.last_table_items = [row.line_item for row in top]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in top]

    return Response(
        text=f"**Top {count} {line_type.value + ' ' if line_type else ''}Variances by Absolute Amount**",
        table=table,
        chips=[f"Why {top[0].line_item}?", "Material", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_set_threshold(session: Session, intent: ParsedIntent) -> Response:
    """Re-run analysis with new materiality thresholds (supports partial adjustments)."""
    spec = intent.captures.get("spec", "")
    parsed = _parse_partial_threshold_text(spec)
    dollar_part, pct_part = parsed
    if dollar_part is None and pct_part is None:
        return Response(
            text="I couldn't parse those thresholds. Use: `threshold $10,000 or 5%`, "
                 "or adjust one: `threshold $25,000` or `threshold 8%`",
            chips=["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%"],
            phase=Phase.EXPLORING,
        )

    dollar = dollar_part if dollar_part is not None else session.dollar_threshold
    pct_ratio = pct_part if pct_part is not None else session.percent_threshold
    if dollar is None or pct_ratio is None:
        return Response(
            text="Materiality thresholds are not fully specified. Please enter both: `$10,000 or 5%`",
            chips=["$5,000 or 3%", "$10,000 or 5%"],
            phase=Phase.EXPLORING,
        )

    old_material = set(
        row.line_item for row in (session.result.material_rows if session.result else ())
    )

    session.dollar_threshold = dollar
    session.percent_threshold = pct_ratio

    response = _run_analysis(session)

    # Report what changed
    if session.result is not None:
        new_material = set(row.line_item for row in session.result.material_rows)
        entered = new_material - old_material
        exited = old_material - new_material

        changes = []
        if entered:
            changes.append("**Newly material:** " + ", ".join(safe_inline(i) for i in sorted(entered)))
        if exited:
            changes.append("**No longer material:** " + ", ".join(safe_inline(i) for i in sorted(exited)))
        if changes:
            response = replace(response, text=response.text + "\n\n" + "\n".join(changes))

    return response


def _handle_warnings(session: Session) -> Response:
    """Show data quality warnings."""
    result = session.result
    assert result is not None

    if not result.warnings:
        return Response(
            text="No data quality warnings.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )

    lines = ["**Data Quality Warnings:**\n"]
    for warning in result.warnings:  # the engine's words, with its term for an unlabeled line made plain (X27)
        lines.append(f"• {safe_inline(warning.replace('Unclassified', NOT_YET_LABELED_PHRASE))}")

    return Response(
        text="\n".join(lines),
        chips=["Summary", "Material"],
        phase=Phase.EXPLORING,
    )


def _handle_recommendations(session: Session) -> Response:
    """Show strategic recommendations based on material variances."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    lines = ["**Strategic Recommendations**\n"]

    # Mitigation (largest unfavorable)
    unfavorable = next(
        (row for row in result.material_rows if row.status == Status.UNFAVORABLE), None,
    )
    if unfavorable:
        evidence = unfavorable.driver_evidence
        if evidence and evidence.reconciles:
            largest_component = max(evidence.components, key=lambda pair: abs(pair[1]))
            if largest_component[0] == "Unexplained residual":
                lines.append(
                    f"• **Mitigation:** Reconcile the unexplained residual for "
                    f"{safe_inline(unfavorable.line_item)} before assigning a cause-specific action."
                )
            else:
                lines.append(
                    f"• **Mitigation:** Focus {_action_plan(cfg)} for {safe_inline(unfavorable.line_item)} "
                    f"on its {safe_inline(largest_component[0].lower())} "
                    f"({format_money(largest_component[1], cfg.currency, places)}), "
                    f"the largest reconciled component."
                )
        else:
            lines.append(
                f"• **Mitigation:** {safe_inline(unfavorable.line_item)} is the largest material "
                f"unfavorable variance, but the dataset does not support a causal corrective action; "
                f"obtain the missing operating driver data first."
            )
    else:
        lines.append("• **Mitigation:** No material unfavorable variance is available.")

    # Optimization (largest favorable)
    favorable = next(
        (row for row in result.material_rows if row.status == Status.FAVORABLE), None,
    )
    if favorable:
        evidence = favorable.driver_evidence
        if evidence and evidence.reconciles:
            largest_component = max(evidence.components, key=lambda pair: abs(pair[1]))
            lines.append(
                f"• **Optimization:** Focus {_action_plan(cfg)} for {safe_inline(favorable.line_item)} "
                f"on its {safe_inline(largest_component[0].lower())} "
                f"({format_money(largest_component[1], cfg.currency, places)}), "
                f"the largest reconciled component."
            )
        else:
            lines.append(
                f"• **Optimization:** {safe_inline(favorable.line_item)} is the largest material "
                f"favorable variance; obtain driver data to validate the cause."
            )
    else:
        lines.append("• **Optimization:** No material favorable variance is available.")

    # Data request
    missing_drivers = [
        safe_inline(row.line_item)
        for row in result.material_rows
        if not (row.driver_evidence and row.driver_evidence.reconciles)
    ]
    if missing_drivers:
        lines.append(
            f"• **Data Request:** Provide reconciled operating driver metrics for: "
            f"{', '.join(missing_drivers)}."
        )
    else:
        lines.append(
            "• **Data Request:** No additional driver data is required for the analyzed "
            "top material variances."
        )

    return Response(
        text="\n".join(lines),
        chips=["Summary", "Material", "Export report"],
        phase=Phase.EXPLORING,
    )


def _handle_totals(session: Session) -> Response:
    """Show Revenue and Expense aggregate totals."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    lines = ["**Aggregate Totals**\n"]

    has_revenue = any(
        row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
        for row in result.rows
    )
    has_expenses = any(
        row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
        for row in result.rows
    )

    if has_revenue:
        rev = result.revenue
        lines.append(
            f"• **Revenue:** {format_money(rev.actual, cfg.currency, places)} actual vs. "
            f"{format_money(rev.budget, cfg.currency, places)} {_noun(cfg)} = "
            f"{format_money(rev.variance_dollars, cfg.currency, places)} "
            f"({format_pct(rev.budget, rev.variance_dollars, rev.percent_label)}, "
            f"{status_label(rev.status)})"
        )
    else:
        lines.append("• **Revenue:** N/A (no Revenue rows)")

    if has_expenses:
        exp = result.expenses
        lines.append(
            f"• **Expenses:** {format_money(exp.actual, cfg.currency, places)} actual vs. "
            f"{format_money(exp.budget, cfg.currency, places)} {_noun(cfg)} = "
            f"{format_money(exp.variance_dollars, cfg.currency, places)} "
            f"({format_pct(exp.budget, exp.variance_dollars, exp.percent_label)}, "
            f"{status_label(exp.status)})"
        )
    else:
        lines.append("• **Expenses:** N/A (no Expense rows)")

    return Response(
        text="\n".join(lines),
        chips=["Summary", "Material", "Net impact"],
        phase=Phase.EXPLORING,
    )


def _handle_full_report(session: Session) -> Response:
    """Show the full Markdown report inline."""
    result = session.result
    assert result is not None

    report = _report_text(session)
    return Response(
        text=report,
        chips=["Export report", "Export excel", "Export audit"],
        phase=Phase.EXPLORING,
    )
