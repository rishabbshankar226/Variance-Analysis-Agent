"""Exports: report, audit, CSV, workbook and the saved layout mapping.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal
from pathlib import Path
from variance_agent.parsing import normalize_row
from variance_agent.audit import build_audit_record, serialize_audit_json, sha256_bytes
from variance_agent.comparison import comparison_heading
from variance_agent.limits import display_text
from variance_agent.models import ComparisonBasis
from variance_agent.output import write_text_outputs
from variance_agent.intake import audit_transformations
from variance_agent.mapping import LayoutMapping, compute_layout_fingerprint, save_mapping
from variance_agent.xlsx import render_xlsx
from ..intent import ParsedIntent
from ..responses import Response, format_money, format_pct, report_places, safe_inline
from ..session import Phase, Session
from ._common import _period_slug
from .summary import _report_text


# ---------------------------------------------------------------------------
# Exploring phase handlers
# ---------------------------------------------------------------------------


def _saved_comparison_basis(session: Session) -> ComparisonBasis | None:
    """The basis a saved mapping replays: an explicit choice, else a detected non-Budget basis."""
    if session.compare_to is not None:
        return session.compare_to
    intake_res = session.intake_result
    if intake_res is not None and intake_res.comparison_basis is not ComparisonBasis.BUDGET:
        return intake_res.comparison_basis
    return None


def _layout_mapping_for(session: Session) -> LayoutMapping:
    """The layout mapping that replays the session's confirmed layout choices."""
    intake_res = session.intake_result
    col_mapping: dict[str, str] = {}
    header_row = 1
    unit_scale = None
    flip_signs = False
    hidden_rows: str | None = None
    excluded_totals: list[str] = []
    fingerprint = ""

    if intake_res is not None:
        header_row = intake_res.header_row_number
        col_mapping = {role.value: name for role, name in intake_res.column_mapping.items()}
        if intake_res.detected_unit_multiplier != Decimal("1"):
            unit_scale = str(intake_res.detected_unit_multiplier)
        flip_signs = intake_res.detected_signed_ledger
        excluded_totals = list(intake_res.detected_totals)
        hidden_rows = intake_res.hidden_rows_choice
        if intake_res.raw_headers:
            fingerprint = compute_layout_fingerprint(intake_res.raw_headers)

    classification_rules: dict[str, object] | None = None
    if session.type_map:
        classification_rules = {
            "keywords": {k: v.value.capitalize() for k, v in session.type_map.items()}
        }

    return LayoutMapping(
        mapping_version="1.5",
        layout_fingerprint=fingerprint,
        header_row_number=header_row,
        sheet_name=session.worksheet,
        column_mapping=col_mapping,
        unit_scale=unit_scale,
        flip_signs=flip_signs,
        treat_blank_budgets_as_zero=True,
        exclude_totals=excluded_totals,
        period_column_selection=session.period,
        classification_rules=classification_rules,
        comparison_basis=_saved_comparison_basis(session),
        comparison_bases=session.comparison_bases if len(session.comparison_bases) > 1 else (),
        measure_options={key: str(value) for key in ("per_share_threshold", "count_threshold", "bps_threshold", "percent_values")
                         if (value := getattr(session, key)) is not None} or None,
        better_directions={str(row.get("line_item", "")): str(row["better"])
                           for raw in session.parsed_rows or [] if (row := normalize_row(raw)).get("better")},
        hidden_rows=hidden_rows,
    )


def _handle_save_mapping(session: Session) -> Response:
    """Export confirmed layout choices as a JSON mapping file."""
    mapping = _layout_mapping_for(session)
    session.layout_mapping = mapping
    mapping_json = save_mapping(mapping)
    return Response(
        text=(
            "**Layout Mapping Saved**\n\n"
            "Here are your confirmed layout settings. Save them as a file to reuse in future months; on the "
            "command line, that file is the optional `--mapping` setting:\n\n"
            f"```json\n{mapping_json}\n```"
        ),
        chips=["Summary", "Export report", "Show unfavorable"],
        phase=Phase.EXPLORING,
    )


def _export_response(
    session: Session, intent: ParsedIntent, content: str | bytes, filename: str, *,
    written: str, ready: str, retry_chip: str, written_chips: list[str], ready_chips: list[str],
) -> Response:
    """Write an export to the path the user named, or hand it over as a download.

    A path is only honoured where the deployment allows it (not on the hosted server).
    """
    path = _export_path(intent)
    if path and not session.path_exports_enabled:
        return _path_export_disabled(path, intent)
    if path:
        try:
            target = Path(path).expanduser()  # "~" is the home folder, as in a shell (X25)
            write_text_outputs({target: content})
            return Response(
                text=f"{written} written to `{safe_inline(str(target) if path.startswith('~') else path)}`.",
                chips=written_chips,
                phase=Phase.EXPLORING,
            )
        except (ValueError, OSError, RuntimeError) as exc:  # RuntimeError: no home folder to expand "~" to
            return Response(
                text=f"Could not write to '{safe_inline(path)}': {display_text(str(exc))}",
                chips=[retry_chip],
                phase=Phase.EXPLORING,
                level="error",
            )
    return Response(
        text=ready,
        download={filename: content},
        chips=ready_chips,
        phase=Phase.EXPLORING,
    )


_PATH_CHARACTERS = re.compile(r"[/\\.~]")


def _export_path(intent: ParsedIntent) -> str | None:
    """The file path an export asked for, if the words after 'export report' are one.

    "download report now" names no file; a path has a separator, an extension or a '~'.
    """
    path = intent.captures.get("path", "").strip().strip("'\"`")
    return path if path and _PATH_CHARACTERS.search(path) else None


def _path_export_disabled(path: str, intent: ParsedIntent) -> Response:
    """Refuse a server-side write on hosted deployments and point to the download."""
    chip = {
        "export_audit": "Export audit", "export_csv": "Export csv", "export_xlsx": "Export excel",
    }.get(
        intent.intent_id, "Export report"
    )
    return Response(
        text=(f"Saving to `{safe_inline(path)}` is turned off on this hosted version. "
              f"Use **{chip}** to download the file instead."),
        chips=[chip],
        phase=Phase.EXPLORING,
        level="error",
    )


def _handle_export_report(session: Session, intent: ParsedIntent) -> Response:
    """Generate the Markdown report for download."""
    result = session.result
    assert result is not None

    report = _report_text(session)
    period_slug = _period_slug(result.config.period)
    filename = f"variance_report_{period_slug}.md"

    return _export_response(
        session, intent, report, filename,
        written="Report", ready="Markdown report ready for download.", retry_chip="Export report",
        written_chips=["Export audit", "Summary"], ready_chips=["Export excel", "Export audit", "Summary"],
    )


def _handle_export_audit(session: Session, intent: ParsedIntent) -> Response:
    """Generate the audit JSON for download."""
    result = session.result
    assert result is not None

    source_hash = sha256_bytes(session.source_bytes) if session.source_bytes else None
    transformations: dict[str, object] | None = None
    if session.intake_result is not None:
        # A mapping saved for an earlier file, sheet or comparison no longer describes this audit.
        saved = session.layout_mapping
        mapping = saved if saved is not None and saved == _layout_mapping_for(session) else None
        transformations = audit_transformations(session.intake_result, mapping)
    record = build_audit_record(
        result,
        source_name=session.source_name,
        source_sha256=source_hash,
        source_worksheet=session.worksheet,
        transformations=transformations,
        source_document=(session.intake_result.source_document()
                         if session.intake_result is not None else None),
    )
    audit_json = serialize_audit_json(record)
    period_slug = _period_slug(result.config.period)
    filename = f"variance_audit_{period_slug}.json"

    return _export_response(
        session, intent, audit_json, filename,
        written="Audit JSON", ready="Audit JSON ready for download.", retry_chip="Export audit",
        written_chips=["Export report", "Summary"], ready_chips=["Export report", "Summary"],
    )


_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _csv_text(value: str) -> str:
    """Keep a text cell from being run as a formula when the CSV is opened in a spreadsheet.

    Applied to label cells only; the numeric columns are written as numbers ('-100' stays one).
    """
    return f"'{value}" if value.startswith(_FORMULA_STARTS) else value


def _handle_export_csv(session: Session, intent: ParsedIntent) -> Response:
    """Generate RFC 4180 compliant CSV export of the analysis data rows."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([
        "Line Item",
        "Type",
        f"{comparison_heading(cfg.comparison_basis, cfg.comparison_label)} ({cfg.currency})",
        f"Actual ({cfg.currency})",
        f"Variance ({cfg.currency})",
        "Variance (%)",
        "Status",
        "Material",
        "Excluded From Aggregation",
        "Classification Source",
        "Driver Evidence",
    ])

    for row in result.rows:
        driver_desc = ""
        if row.driver_evidence:
            comp_str = "; ".join(
                f"{k}: {format_money(v, cfg.currency, places)}"
                for k, v in row.driver_evidence.components
            )
            rec_str = "Reconciles" if row.driver_evidence.reconciles else "Unreconciled"
            driver_desc = f"{row.driver_evidence.label} ({rec_str}): {comp_str}"

        writer.writerow([
            _csv_text(row.line_item),
            row.line_type.value,
            str(row.budget),
            str(row.actual),
            str(row.variance_dollars),
            format_pct(row.budget, row.variance_dollars, row.percent_label),
            row.status.value,
            "Yes" if row.material else "No",
            "Yes" if row.excluded_from_aggregation else "No",
            _csv_text(row.classification_source),
            _csv_text(driver_desc),
        ])

    csv_text = output.getvalue()
    period_slug = _period_slug(result.config.period)
    filename = f"variance_data_{period_slug}.csv"

    return _export_response(
        session, intent, csv_text, filename,
        written="Analysis CSV", ready="Analysis CSV ready for download.", retry_chip="Export csv",
        written_chips=["Export report", "Export audit", "Summary"], ready_chips=["Export excel", "Export report", "Summary"],
    )


def _handle_export_xlsx(session: Session, intent: ParsedIntent) -> Response:
    """Generate the formatted Excel workbook for download."""
    result = session.result
    assert result is not None

    workbook = render_xlsx(result)
    period_slug = _period_slug(result.config.period)
    filename = f"variance_workbook_{period_slug}.xlsx"

    return _export_response(
        session, intent, workbook, filename,
        written="Excel workbook", ready=("Excel workbook ready for download: Summary, Material Variances, "
              "Root Causes & Actions, and All Rows sheets."), retry_chip="Export excel",
        written_chips=["Export report", "Export audit", "Summary"], ready_chips=["Export report", "Export audit", "Summary"],
    )
