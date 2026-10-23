"""Confirmed earnings review; budget uploads keep the legacy state machine."""
from __future__ import annotations

from pathlib import Path

from variance_agent.comparison import basis_noun, comparison_heading, parse_compare_to
from variance_agent.comparisons import (TableAnalysis, analyze_comparisons, build_comparison_audit,
                                       read_comparison_input, render_comparisons, detect_comparison_bases)
from variance_agent.audit import serialize_audit_json, sha256_bytes
from variance_agent.intake import IntakeResult
from variance_agent.models import AnalysisConfig, ComparisonBasis
from variance_agent.parsing import normalize_row
from variance_agent.report import _safe_inline
from variance_agent.audience import audience_config
from dataclasses import replace
from variance_agent.earnings import display_rows
from variance_agent.models import MeasureKind
from variance_agent.xlsx import render_comparison_xlsx
from .responses import Response
from .session import Phase, Session


def offer_review(session: Session, data: bytes, filename: str) -> Response | None:
    try:
        rows, headers, worksheet, notes = read_comparison_input(data, Path(filename).suffix, filename=filename, assisted=True)
    except (ValueError, OSError, RuntimeError):
        return None
    bases = detect_comparison_bases(headers)
    if ComparisonBasis.BUDGET in bases or not any(b in {ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE,
                                                       ComparisonBasis.GUIDANCE} for b in bases):
        return None
    session.reset()
    session.source_bytes, session.source_name, session.source_suffix = data, filename, Path(filename).suffix
    session.parsed_rows = [normalize_row(row) for row in rows]
    session.earnings_headers, session.earnings_choices, session.earnings_notes = headers, bases, notes
    session.worksheet = worksheet
    session.phase = Phase.AWAITING_EARNINGS_REVIEW
    return Response(text="This file includes supplied earnings comparisons. Would you like an earnings review? "
                         "I compare the numbers you supply and make no estimates.",
                    chips=["Review earnings", "Upload a different file"], phase=session.phase)


def handle_review_choice(session: Session, text: str) -> Response:
    lower = text.strip().casefold()
    if session.phase is Phase.AWAITING_EARNINGS_REVIEW:
        if lower not in {"review earnings", "yes", "confirm"}:
            return Response(text="Choose Review earnings to use these supplied comparisons.",
                            chips=["Review earnings", "Upload a different file"], phase=session.phase)
        session.earnings_mode = True
        if len(session.earnings_choices) == 1:
            return confirm_layout(session, session.earnings_choices)
        session.phase = Phase.AWAITING_COMPARISON_CHOICE
    if lower == "compare against all of them":
        return confirm_layout(session, session.earnings_choices)
    if lower.startswith("compare to "):
        value = lower[len("compare to "):]
        value = {"prior period": "prior-period", "prior year": "prior-period"}.get(value, value)
        try:
            basis = parse_compare_to(value)
        except ValueError:
            basis = None
        if basis in session.earnings_choices:
            assert basis is not None
            return confirm_layout(session, (basis,))
    chips = ["Compare to " + basis_noun(basis) for basis in session.earnings_choices]
    chips.append("Compare against all of them")
    return Response(text="Which supplied comparison should Actual be compared against?", chips=chips, phase=session.phase)


def confirm_layout(session: Session, bases: tuple[ComparisonBasis, ...]) -> Response:
    session.comparison_bases = bases
    session.intake_result = IntakeResult(rows=session.parsed_rows or [], comparison_basis=bases[0])
    session.phase = Phase.AWAITING_INTAKE_CONFIRMATION
    lines = ["Here's how I read your file:", "", "- Compare Actual against: " +
             ", ".join(comparison_heading(b, None) for b in bases) + ".", "- Source columns: " +
             ", ".join(_safe_inline(h) for h in session.earnings_headers) + "."]
    for raw in session.parsed_rows or []:
        row = normalize_row(raw)
        from variance_agent.segments import SEGMENT_KEYS
        for column in SEGMENT_KEYS:
            if column in row:
                lines.append(f"- Read {_safe_inline(column)} as Segment {_safe_inline(row[column])} (one flat dimension).")
        if row.get("measure"):
            lines.append(f"- {_safe_inline(row.get('line_item', 'Row'))}: Measure {_safe_inline(row['measure'])}.")
    candidates = [str(row.get("line_item", "")) for row in session.parsed_rows or []
                  if "revenue" in str(row.get("line_item", "")).casefold() or "eps" in str(row.get("line_item", "")).casefold()
                  or "margin" in str(row.get("line_item", "")).casefold()]
    lines.append("- Earnings headline rows: " + ", ".join(_safe_inline(name) for name in candidates) + ".")
    lines.extend("- " + _safe_inline(note) for note in session.earnings_notes)
    lines.extend(["", "Does this look right?"])
    return Response(text="\n".join(lines), chips=["Looks right", "Change something"], phase=session.phase)


def explicit_comparison(session: Session, basis: ComparisonBasis) -> Response:
    if session.source_bytes is None or session.source_name is None:
        session.compare_to = basis
        return Response(text=f"Upload the file to compare against supplied {basis_noun(basis)}.", phase=session.phase)
    rows, headers, worksheet, notes = read_comparison_input(session.source_bytes, Path(session.source_name).suffix,
                                                           filename=session.source_name, assisted=True, sheet=session.sheet)
    session.earnings_mode = True
    session.parsed_rows = [normalize_row(row) for row in rows]
    session.earnings_headers, session.earnings_choices, session.earnings_notes = headers, detect_comparison_bases(headers), notes
    session.worksheet = worksheet
    return confirm_layout(session, (basis,))


def analyze_review(session: Session, config: AnalysisConfig) -> TableAnalysis:
    assert session.parsed_rows is not None
    config = replace(audience_config(config), preset="earnings")
    return analyze_comparisons(session.parsed_rows, config, session.comparison_bases, raw_headers=session.earnings_headers)


def summary(session: Session) -> Response:
    assert session.table_analysis is not None
    table = session.table_analysis
    titles = ", ".join(comparison_heading(comparison.basis, comparison.label) for comparison in table.comparisons)
    return Response(text=f"Earnings review: Actual compared with supplied {titles}. I make no estimates.",
                    table=display_rows(table), chips=["Summary", "Export report", "Export audit", "Export Excel"], phase=Phase.EXPLORING)


def explore(session: Session, intent_id: str, captures: dict[str, str]) -> Response:
    assert session.table_analysis is not None
    from .handlers import _export_response, _period_slug
    from .intent import ParsedIntent
    table = session.table_analysis
    if intent_id not in {"export_report", "export_audit", "export_xlsx"}:
        return summary(session)
    stem = _period_slug(table.config.period)
    data: str | bytes
    if intent_id == "export_audit":
        record = build_comparison_audit(table, source_name=session.source_name, source_worksheet=session.worksheet,
                                        source_sha256=sha256_bytes(session.source_bytes) if session.source_bytes is not None else None)
        data = serialize_audit_json(record)
        filename, label, chip = f"comparison_audit_{stem}.json", "Audit", "Export audit"
    elif intent_id == "export_xlsx":
        data = render_comparison_xlsx(table)
        filename, label, chip = f"comparison_workbook_{stem}.xlsx", "Workbook", "Export Excel"
    else:
        data = render_comparisons(table)
        filename, label, chip = f"comparison_report_{stem}.md", "Report", "Export report"
    return _export_response(session, ParsedIntent(intent_id, captures), data, filename,
                            written=label, ready=label + " ready for download.", retry_chip=chip,
                            written_chips=["Summary"], ready_chips=["Summary"])


def handle_question(session: Session, intent_id: str) -> Response:
    if session.earnings_mode and session.table_analysis is not None:
        rows = display_rows(session.table_analysis)
        if intent_id == "earnings_margins":
            rows = [row for row in rows if row["Measure"] == "Percent"]
        return Response(text="Compared with the supplied numbers. I make no estimates.", table=rows or None,
                        chips=["Summary", "Export report"], phase=session.phase)
    if intent_id == "earnings_margins":
        if session.result is not None:
            from .responses import row_to_table_dict
            rows = [row_to_table_dict(row, session.currency) for row in session.result.rows if row.measure is MeasureKind.PERCENT]
            if rows:
                return Response(text="Supplied rate changes in basis points.", table=rows, phase=session.phase)
        return Response(text="Upload supplied rate rows with Measure Percent and choose whether Higher or Lower is better.",
                        phase=session.phase)
    if session.earnings_mode:
        return Response(text="Finish confirming the file and your thresholds to compare the supplied numbers.", phase=session.phase)
    return explicit_comparison(session, ComparisonBasis.GUIDANCE if intent_id == "earnings_guidance" else ComparisonBasis.CONSENSUS)


def review_upload(session: Session, data: bytes, filename: str, basis: ComparisonBasis, sheet: str | None) -> Response:
    try:
        rows, headers, worksheet, notes = read_comparison_input(data, Path(filename).suffix, filename=filename,
                                                               assisted=True, sheet=sheet)
    except (ValueError, OSError, RuntimeError):
        return Response(text="I could not read a supported financial table in this file. Upload a CSV, JSON or Excel table "
                             "with a line item, Actual and your supplied comparison.", phase=session.phase)
    session.reset()
    session.source_bytes, session.source_name, session.source_suffix = data, filename, Path(filename).suffix
    session.sheet, session.worksheet = sheet, worksheet
    session.earnings_mode, session.compare_to = True, basis
    session.parsed_rows = [normalize_row(row) for row in rows]
    session.earnings_headers, session.earnings_choices, session.earnings_notes = headers, detect_comparison_bases(headers), notes
    return confirm_layout(session, (basis,))
