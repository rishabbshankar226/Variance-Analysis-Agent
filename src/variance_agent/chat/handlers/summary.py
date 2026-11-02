"""The analysis summary and a filing's own totals.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from variance_agent.audience import is_audience_result
from variance_agent.measures import currency_row
from variance_agent.models import MeasureKind
from variance_agent.comparison import comparison_heading, display_outcome, extended_heading
from variance_agent.measures import format_measure
from variance_agent.models import AnalysisResult, LineType
from variance_agent.numeric import financial_context
from variance_agent.report import render_markdown
from ..responses import (
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
from ..views import figure, figures_view, pair
from ._common import _heading, _noun, _plain_heading, _tone


def _basis_summary(result: AnalysisResult) -> Response:
    """A limit, benchmark or target comparison: the report's own table, with no budget totals (Decision 39)."""
    from ...report import basis_table
    cfg = result.config
    columns, rows, counts = basis_table(result)
    table = [dict(zip(columns, cells, strict=True)) for cells in rows]
    figures = ([figure(word, count) for word, count in
                (part.rstrip(".").split(" ", 1)[::-1] for part in counts.split(", "))] if counts is not None else [])
    view = figures_view(
        f"{cfg.period} against {comparison_heading(cfg.comparison_basis, cfg.comparison_label)}",
        context=[pair("Currency", cfg.currency)] if any(currency_row(row) for row in result.rows) else [],
        figures=figures,
        sections=[("How the file was read", [pair(*note.split(": ", 1)) if ": " in note else pair("Note", note)
                                             for note in result.warnings])] if result.warnings else (),
        table_title="Lines, by severity" if cfg.comparison_basis.value == "limit" else "Lines",
    )
    return Response(text=render_markdown(result), table=table, chips=["Export report", "Export audit"],
                    phase=Phase.EXPLORING, view=view)


def _audience_summary(result: AnalysisResult) -> Response:
    """A comparison set: the report as text, and the same rows as a results view and one table."""
    if any(row.basis_details is not None for row in result.rows):
        return _basis_summary(result)
    cfg = result.config
    heading = extended_heading(cfg)
    money = [row for row in result.rows if currency_row(row)]
    complete = (all(row.line_type is not LineType.UNCLASSIFIED for row in money)
                and any(row.line_type is LineType.REVENUE for row in money)
                and any(row.line_type is LineType.EXPENSE for row in money))
    figures: list[dict[str, object]] = []
    notes: list[str] = []
    if complete:
        for label, total in (("Revenue", result.revenue), ("Expenses", result.expenses)):
            figures.append(figure(label, format_money(total.actual, cfg.currency),
                                  f"{heading} {format_money(total.budget, cfg.currency)}",
                                  f"Variance {format_money(total.variance_dollars, cfg.currency)}, "
                                  f"{format_pct(total.budget, total.variance_dollars, total.percent_label)}",
                                  status_label(total.status)))
        with financial_context():
            net = result.revenue.variance_dollars - result.expenses.variance_dollars
        figures.append(figure("Net operating variance", format_money(net, cfg.currency), tone=_tone(net)))
    else:
        notes.append("Currency totals are incomplete; net operating impact is unavailable.")
    segmented = any(row.segment_declared for row in result.rows)
    table: list[dict[str, str]] = []
    for row in result.rows:
        variance = row.variance_bps if row.measure is MeasureKind.PERCENT else row.variance_dollars
        assert variance is not None
        record = {"Line Item": row.line_item}
        if segmented:
            record["Segment"] = row.segment
        record.update({"Measure": str(row.measure), heading: format_measure(row.budget, row.measure, cfg.currency),
                       "Actual": format_measure(row.actual, row.measure, cfg.currency),
                       "Variance": format_measure(variance, row.measure, cfg.currency, variance=True),
                       "Var (%)": format_pct(row.budget, row.variance_dollars, row.percent_label),
                       "Status": display_outcome(row, cfg.comparison_basis), "Material": "Yes" if row.material else "No"})
        table.append(record)
        detail = row.comparison_details
        for position in (detail.guidance_position, detail.consensus_range_position) if detail is not None else ():
            if position:
                notes.append(f"{row.line_item}: {position}.")
    view = figures_view(
        f"{cfg.period} against {heading}",
        context=[pair("Currency", cfg.currency)],
        figures=figures,
        sections=[("How the file was read", [pair(*note.split(": ", 1)) if ": " in note else pair("Note", note)
                                             for note in result.warnings])] if result.warnings else (),
        notes=notes,
        table_title=f"{len(table)} line{'s' if len(table) != 1 else ''}, each in its own unit",
    )
    return Response(text=render_markdown(result), table=table, chips=["Summary", "Export Excel", "Export audit"],
                    phase=Phase.EXPLORING, view=view)


_STATEMENT_CHIPS = ["Export report", "Export audit"]
_STATEMENT_WORKBOOK = ("A workbook isn't available for this comparison yet. The report and the audit file are; type "
                       "`export report` or `export audit`.")


def _statement_checks(session: Session) -> list[str]:
    """The identity and change notes of a balance sheet or cash flow read (PLAN.md R7), or none."""
    if session.result is None or not any(row.statement_kind for row in session.result.rows):
        return []
    return list(session.intake_result.statement_checks) if session.intake_result is not None else []


def _report_text(session: Session) -> str:
    assert session.result is not None
    checks = _statement_checks(session)
    appendix = list(session.intake_result.report_appendix) if session.intake_result is not None else []
    headline = session.intake_result.filing_headline if session.intake_result is not None else None
    if checks or appendix or headline is not None:
        return render_markdown(session.result, statement_checks=checks or None, appendix=appendix or None,
                               filing_headline=headline)
    return render_markdown(session.result)


def _build_analysis_summary(session: Session) -> Response:
    """Build the initial analysis summary after successful analysis."""
    if session.earnings_mode and session.table_analysis is not None:
        from ..earnings import summary
        return summary(session)
    result = session.result
    assert result is not None
    if is_audience_result(result):
        return _audience_summary(result)
    if any(row.statement_kind or row.basis_details is not None or row.classification_source == "metric"
           for row in result.rows):
        # A balance sheet, cash flow, limit, benchmark, target or metric comparison has no revenue or expense totals.
        return Response(text=_report_text(session), chips=list(_STATEMENT_CHIPS), phase=Phase.EXPLORING)
    if session.intake_result is not None and session.intake_result.filing_headline is not None:
        return _filing_summary(session, session.intake_result.filing_headline)
    cfg = result.config
    places = report_places(result)

    lines = [
        "**Analysis Complete**\n",
        f"**Period:** {safe_inline(cfg.period)}",
        f"**Currency:** {cfg.currency}",
        f"**Thresholds:** {format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or "
        f"{format_threshold_pct(cfg.percent_threshold)}\n",
    ]
    heading = _plain_heading(cfg)
    figures: list[dict[str, object]] = []
    notes: list[str] = []

    # Revenue summary
    has_revenue = any(
        row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
        for row in result.rows
    )
    has_expenses = any(
        row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
        for row in result.rows
    )
    classification_incomplete = any(
        row.line_type == LineType.UNCLASSIFIED for row in result.rows
    )

    for label, total, present, missing in (
        ("Revenue", result.revenue, has_revenue, "no Revenue rows"),
        ("Expenses", result.expenses, has_expenses, "no Expense rows"),
    ):
        if present and not classification_incomplete:
            actual = format_money(total.actual, cfg.currency, places)
            compared = format_money(total.budget, cfg.currency, places)
            variance = format_money(total.variance_dollars, cfg.currency, places)
            pct = format_pct(total.budget, total.variance_dollars, total.percent_label)
            word = status_label(total.status)
            lines.append(f"**Total {label}:** {actual} vs. {compared} ({variance}, {pct}, {word})")
            figures.append(figure(label, actual, f"{heading} {compared}", f"Variance {variance}, {pct}", word))
        else:
            reason = "classification incomplete" if classification_incomplete else missing
            lines.append(f"**Total {label}:** N/A ({reason})")
            figures.append(figure(label, "N/A", reason.capitalize()))

    # Net operating impact
    if not classification_incomplete and has_revenue and has_expenses:
        with financial_context():
            net_impact = result.revenue.variance_dollars - result.expenses.variance_dollars
        direction = "above" if net_impact > 0 else "below" if net_impact < 0 else "in line with"
        net_text = format_money(net_impact, cfg.currency, places)
        lines.append(f"\n**Net Operating Impact:** {net_text}, {direction} {_noun(cfg)}")
        figures.append(figure("Net operating impact", net_text, f"{direction.capitalize()} {_noun(cfg)}",
                              tone=_tone(net_impact)))
    else:
        lines.append("\n**Net Operating Impact:** N/A")
        figures.append(figure("Net operating impact", "N/A"))

    material_count = len(result.material_rows)
    material_text = f"{material_count} material variance{'s' if material_count != 1 else ''}"
    lines.append(f"\n**{material_count}** material variance{'s' if material_count != 1 else ''} found.")

    if classification_incomplete:
        notes.append("Totals wait until every line is labeled revenue or expense.")
    if result.warnings:
        warned = f"{len(result.warnings)} data quality warning{'s' if len(result.warnings) != 1 else ''}."
        lines.append(f"\n{warned}")
        notes.append(warned)

    text = "\n".join(lines)

    # Build table of material variances
    table = None
    if result.material_rows:
        session.last_table_items = [r.line_item for r in result.material_rows]
        session.last_focused_item = session.last_table_items[0]
        table = [
            row_to_table_dict(row, cfg.currency, places, _heading(cfg))
            for row in result.material_rows
        ]
    view = figures_view(
        f"{cfg.period} against {_noun(cfg)}",
        context=[pair("Currency", cfg.currency),
                 pair("Material at", f"{format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or "
                                     f"{format_threshold_pct(cfg.percent_threshold)}"),
                 pair("Lines read", str(len(result.rows)))],
        figures=figures, notes=notes,
        table_title=material_text.capitalize() if table else f"No {material_text[2:]}" if material_count == 0 else None,
    )

    # Suggest useful next actions
    chips = []
    if result.material_rows:
        first_item = result.material_rows[0].line_item
        chips.append(f"Why {first_item}?")
    chips.extend(["Show unfavorable", "Summary", "Export report", "Save layout mapping"])
    if result.warnings:
        chips.append("Warnings")

    return Response(text=text, table=table, chips=chips, phase=Phase.EXPLORING, view=view)


_FILING_TOTALS_NOTE = ("For a filing I show its own printed totals, each from its XBRL fact, rather than totals added up "
                       "from its lines.")
# Questions whose answers rest on revenue, expense or profit totals added up from the lines (Decision 39).
_COMPUTED_TOTALS = {"summary", "totals", "waterfall", "what_if", "sensitivity", "run_rate", "revenue_status",
                    "expense_status", "budget_utilization", "profitability", "tldr", "executive_memo"}


def _filing_summary(session: Session, headline: dict[str, object]) -> Response:
    """A filing's income statement: its own printed totals, never computed ones (Decision 39)."""
    from ...report import _filing_headline_lines
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    heading = _plain_heading(cfg)
    items, notes = headline.get("items"), headline.get("notes")
    assert isinstance(items, list) and isinstance(notes, list)
    unit = str(headline.get("unit") or "")
    lines = ["**Analysis Complete**\n", f"**Period:** {safe_inline(cfg.period)}", f"**Currency:** {cfg.currency}",
             *([f"Units: {safe_inline(unit)}"] if unit else []),
             f"**Thresholds:** {format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or "
             f"{format_threshold_pct(cfg.percent_threshold)}\n"]
    figures: list[dict[str, object]] = []
    bullets = _filing_headline_lines({"items": items, "notes": []}, cfg.currency, places)[:len(items)]  # not its closing sentence
    for bullet, item in zip(bullets, items, strict=True):
        assert isinstance(item, dict)
        name, _, rest = bullet.removeprefix("- ").partition(": ")
        lines.append(f"**{name}:** {rest}")
        actual, _, after = rest.partition(" vs. ")
        compared, _, change = after.partition(" (")
        figures.append(figure(str(item["line_item"]), actual, f"{heading} {compared}", f"Change {change.rstrip(')')}"))
    lines.extend(safe_inline(str(note)) for note in notes)
    ltm = any(isinstance(item, dict) and "ltm" in item for item in items)
    totals_note = (_FILING_TOTALS_NOTE.replace("its own printed totals, each from its XBRL fact",
                                               "LTM of the filing's own printed totals, each built from its XBRL facts")
                   if ltm else _FILING_TOTALS_NOTE)
    lines.append(totals_note)
    material_count = len(result.material_rows)
    material_text = f"{material_count} material variance{'s' if material_count != 1 else ''}"
    lines.append(f"\n**{material_count}** material variance{'s' if material_count != 1 else ''} found.")
    table = None
    if result.material_rows:
        session.last_table_items = [r.line_item for r in result.material_rows]
        session.last_focused_item = session.last_table_items[0]
        table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in result.material_rows]
    view = figures_view(
        f"{cfg.period} against {_noun(cfg)}",
        context=[pair("Currency", cfg.currency),
                 pair("Material at", f"{format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or "
                                     f"{format_threshold_pct(cfg.percent_threshold)}"),
                 pair("Lines read", str(len(result.rows)))],
        figures=figures, notes=[*([f"Units: {unit}"] if unit else []), *(str(note) for note in notes), totals_note],
        table_title=material_text.capitalize() if table else f"No {material_text[2:]}",
    )
    chips = [f"Why {result.material_rows[0].line_item}?"] if result.material_rows else []
    chips.extend(["Show unfavorable", "Export report", "Export audit"])
    return Response(text="\n".join(lines), table=table, chips=chips, phase=Phase.EXPLORING, view=view)
