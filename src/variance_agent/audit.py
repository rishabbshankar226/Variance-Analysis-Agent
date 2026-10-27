from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from .models import Aggregate, AnalysisConfig, AnalysisResult, AnalyzedRow, ComparisonBasis, ComparisonDetails, LineType
from .audience import AudienceConfig, is_audience_result, effective_layout, effective_per_share_lines
from .measures import currency_row, metric_inferences
from .comparison import display_outcome, extended_heading
from .output import write_text_outputs
from .numeric import NUMERIC_POLICY_ID, financial_context, ratio
from .analysis import CLASSIFICATION_POLICY_ID, DRIVER_POLICY_ID, verify_result
from .json_types import JSONObject, JSONValue
from .limits import validate_text
from .version import __version__

CURRENT_SCHEMA_VERSION = "1.7"
SUPPORTED_SCHEMA_VERSIONS = ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9")


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def payload_sha256(record: Mapping[str, object]) -> str:
    """Public integrity recipe: omit only the digest itself; this is not authentication."""
    return sha256_bytes(_canonical({key:value for key,value in record.items()
                                   if key != "payload_sha256"}))


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _json_value(value: object) -> JSONValue:
    """Narrow an arbitrary value to JSONValue (unknown types are stringified)."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _json_list(value: object) -> list[JSONValue]:
    return [_json_value(item) for item in value] if isinstance(value, (list, tuple)) else []


def _json_object(value: object) -> JSONObject:
    return {str(key): _json_value(item) for key, item in value.items()} if isinstance(value, dict) else {}


def _as_int(value: object) -> int:
    return value if isinstance(value, int) else int(str(value))


def _aggregate_record(aggregate: Aggregate, *, present: bool, complete: bool) -> JSONObject:
    return {
        "present": present,
        "complete": complete,
        "budget": _decimal(aggregate.budget),
        "actual": _decimal(aggregate.actual),
        "variance_dollars": _decimal(aggregate.variance_dollars),
        "variance_percent": _decimal(aggregate.variance_percent),
        "percent_label": aggregate.percent_label,
        "status": str(aggregate.status),
    }


def _driver_record(row: AnalyzedRow, *, include_diagnostics: bool = False) -> JSONObject:
    evidence = row.driver_evidence
    record: JSONObject
    if evidence is None:
        record = {
            "evidence_status": "hypothesis",
            "model": None,
            "reconciles": False,
            "components": [],
        }
    else:
        record = {
            "evidence_status": "supported" if evidence.reconciles else "hypothesis",
            "model": evidence.label,
            "reconciles": evidence.reconciles,
            "components": [
                {"name": name, "amount": _decimal(amount)}
                for name, amount in evidence.components
            ],
        }
    if include_diagnostics:
        verification = evidence.reconciliation if evidence is not None else None
        record["reconciliation"] = None if verification is None else {
            "modeled_budget": _decimal(verification.modeled_budget),
            "modeled_actual": _decimal(verification.modeled_actual),
            "budget_residual": _decimal(verification.budget_residual),
            "actual_residual": _decimal(verification.actual_residual),
            "component_residual": _decimal(verification.component_residual),
            "amount_tolerance": _decimal(verification.amount_tolerance),
            "variance_tolerance": _decimal(verification.variance_tolerance),
            "failure_reasons": list(verification.failure_reasons),
        }
    return record


def _row_record(row: AnalyzedRow, *, include_diagnostics: bool = False) -> JSONObject:
    record: JSONObject = {
        "line_item": row.line_item,
        "type": str(row.line_type),
        "budget": _decimal(row.budget),
        "actual": _decimal(row.actual),
        "variance_dollars": _decimal(row.variance_dollars),
        "variance_percent": _decimal(row.variance_percent),
        "percent_label": row.percent_label,
        "status": str(row.status),
        "material": row.material,
        "excluded_from_aggregation": row.excluded_from_aggregation,
        "driver": _driver_record(row, include_diagnostics=include_diagnostics),
    }
    if include_diagnostics:
        record.update(classification_source=row.classification_source,
                      summary_source=row.summary_source, materiality_reason=row.materiality_reason)
    return record


def _summary_record(row: AnalyzedRow) -> JSONObject:
    verification = row.summary_verification
    if verification is None:
        raise ValueError("Summary verification is unavailable.")
    return {
        "line_item": row.line_item, "type": str(row.line_type),
        "summary_source": row.summary_source, "outcome": verification.outcome,
        "detail_count": verification.detail_count,
        "budget_residual": _decimal(verification.budget_residual),
        "actual_residual": _decimal(verification.actual_residual),
        "tolerance": _decimal(verification.tolerance),
    }


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def serialize_audit_json(record: Mapping[str, object]) -> str:
    return json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def write_audit_json(path: str | Path, record: Mapping[str, object]) -> None:
    write_text_outputs({Path(path): serialize_audit_json(record)})


@financial_context()
def _document_record(document: Mapping[str, object] | None) -> JSONObject | None:
    """Validate how a PDF statement was read: its name, pages and the reader's notes.

    Audit 1.9 also records an EDGAR-style statement sheet: its statement, sheet and notes.
    """
    if document is None:
        return None
    kind, statement = document.get("kind"), document.get("statement")
    pages, notes = document.get("pages"), document.get("reader_notes")
    if kind == "ixbrl":
        validate_text(statement, field="source_document statement", nonblank=True)
        lines = document.get("lines")
        if not isinstance(notes, (list, tuple)) or not isinstance(lines, (list, tuple)):
            raise ValueError("source_document reader_notes and lines must be lists.")
        record: JSONObject = {"kind": "ixbrl", "statement": str(statement),
                              "reader_notes": [validate_text(note, field="source_document reader note") for note in notes],
                              "lines": [_json_value(line) for line in lines]}
        if "statement_kind" in document:  # a balance sheet or cash flow statement and its identity (PLAN.md R9)
            if document["statement_kind"] not in {"balance_sheet", "cash_flow"}:
                raise ValueError("source_document statement_kind must be balance_sheet or cash_flow.")
            identities = document.get("identities")
            if not isinstance(identities, (list, tuple)):
                raise ValueError("source_document identities must be a list.")
            record.update(statement_kind=str(document["statement_kind"]),
                          identities=[_json_value(identity) for identity in identities])
        return record
    if kind == "edgar_xlsx":
        validate_text(statement, field="source_document statement", nonblank=True)
        sheet = document.get("sheet")
        validate_text(sheet, field="source_document sheet", nonblank=True)
        if not isinstance(notes, (list, tuple)):
            raise ValueError("source_document reader_notes must be a list of text.")
        return {"kind": "edgar_xlsx", "statement": str(statement), "sheet": str(sheet),
                "reader_notes": [validate_text(note, field="source_document reader note") for note in notes]}
    if kind != "pdf":
        raise ValueError("source_document kind must be 'pdf'.")
    validate_text(statement, field="source_document statement", nonblank=True)
    if not isinstance(pages, (list, tuple)) or not pages or not all(
            isinstance(page, int) and not isinstance(page, bool) and page > 0 for page in pages):
        raise ValueError("source_document pages must be a nonempty list of page numbers.")
    if not isinstance(notes, (list, tuple)):
        raise ValueError("source_document reader_notes must be a list of text.")
    return {
        "kind": "pdf",
        "statement": str(statement),
        "pages": [int(page) for page in pages],
        "reader_notes": [validate_text(note, field="source_document reader note") for note in notes],
    }


@financial_context()
def build_audit_record(
    result: AnalysisResult,
    *,
    source_name: str | None = None,
    source_sha256: str | None = None,
    schema_version: str | None = None,
    type_map_sha256: str | None = None,
    source_worksheet: str | None = None,
    transformations: Mapping[str, object] | None = None,
    source_document: Mapping[str, object] | None = None,
) -> JSONObject:
    """Build a JSON-safe, versioned record of deterministic analysis facts.

    Raw source rows are excluded. Downstream report consumers receive verified
    facts and selected source metadata; source text remains untrusted data.
    """
    verify_result(result)
    extended = is_audience_result(result)
    # A workbook examination finding or an EDGAR-style statement sheet is recorded only by 1.9.
    workbook = transformations.get("workbook") if transformations is not None else None
    needs_19 = workbook is not None or (source_document is not None and source_document.get("kind") in {"edgar_xlsx", "ixbrl"})
    if schema_version is None:
        schema_version = "1.9" if needs_19 else "1.8" if extended else CURRENT_SCHEMA_VERSION
    if extended and schema_version not in {"1.8", "1.9"}:
        raise ValueError("Audit schema 1.8 is required to record measure and direction choices.")
    if needs_19 and schema_version != "1.9":
        raise ValueError(f"Audit schema {schema_version} cannot record what the workbook examination found; "
                         "use --audit-schema-version 1.9.")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported audit schema version {schema_version!r}.")
    if schema_version == "1.0" and result.config.currency != "USD":
        raise ValueError("Audit schema 1.0 supports USD only; select a newer audit schema.")
    if source_document is not None and schema_version not in {"1.7", "1.8", "1.9"}:
        raise ValueError(
            f"Audit schema {schema_version} cannot record how a PDF statement was read; "
            "use --audit-schema-version 1.7 for PDF input."
        )
    if schema_version not in {"1.6", "1.7", "1.8", "1.9"} and result.config.comparison_basis != ComparisonBasis.BUDGET:
        raise ValueError(
            f"Audit schema {schema_version} records the comparison amount as a budget; "
            "use --audit-schema-version 1.6 for forecast or prior-period comparisons."
        )
    if source_name is not None:
        validate_text(source_name, field="source_name")
    if source_sha256 is not None and (not isinstance(source_sha256, str)
                                      or not _SHA256_RE.fullmatch(source_sha256)):
        raise ValueError("source_sha256 must be a 64-character hexadecimal SHA-256 digest.")
    if type_map_sha256 is not None and (not isinstance(type_map_sha256, str)
                                        or not _SHA256_RE.fullmatch(type_map_sha256)):
        raise ValueError("type_map_sha256 must be a 64-character hexadecimal SHA-256 digest.")
    if source_worksheet is not None and (not isinstance(source_worksheet, str) or not source_worksheet):
        raise ValueError("source_worksheet must be a nonempty worksheet name or null.")
    if source_worksheet is not None:
        validate_text(source_worksheet, field="source_worksheet", nonblank=True)
    include_diagnostics = schema_version in {"1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}

    quality_rows = tuple(row for row in result.rows if currency_row(row))
    row_count = len(quality_rows)
    unclassified_count = sum(row.line_type == LineType.UNCLASSIFIED for row in quality_rows)
    classified_count = row_count - unclassified_count
    classification_coverage = (
        ratio(Decimal(classified_count) * Decimal("100"), Decimal(row_count))
        if row_count
        else Decimal("0")
    )
    has_revenue = any(
        row.line_type == LineType.REVENUE and not row.excluded_from_aggregation and currency_row(row)
        for row in result.rows
    )
    has_expenses = any(
        row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation and currency_row(row)
        for row in result.rows
    )
    totals_complete = (unclassified_count == 0 and has_revenue and has_expenses
                       and not any(row.segment for row in result.rows))
    net_operating_available = totals_complete
    supported_driver_count = sum(
        bool(row.driver_evidence and row.driver_evidence.reconciles)
        for row in result.material_rows
    )

    source: JSONObject = {
        "name": source_name,
        "sha256": source_sha256.lower() if source_sha256 is not None else None,
    }
    data_quality: JSONObject = {
        "row_count": row_count,
        "classified_count": classified_count,
        "unclassified_count": unclassified_count,
        "classification_coverage_percent": f"{classification_coverage:.2f}",
        "excluded_summary_count": sum(row.excluded_from_aggregation for row in result.rows),
        "material_variance_count": len(result.material_rows),
        "supported_driver_count": supported_driver_count,
        "hypothesis_driver_count": len(result.material_rows) - supported_driver_count,
        "totals_complete": totals_complete,
        "net_operating_impact_available": net_operating_available,
        "warnings": list(result.warnings),
    }
    record: JSONObject = {
        "schema_version": schema_version,
        "period": result.config.period,
        "source": source,
        "materiality": {
            "dollar_threshold": _decimal(result.config.dollar_threshold),
            "percent_threshold": _decimal(result.config.percent_threshold),
            "comparison": "strictly_greater_than",
            "logic": "absolute_dollar_or_absolute_percent",
        },
        "data_quality": data_quality,
        # A balance sheet or cash flow comparison has no totals: a zero would trace to no stored value.
        "totals": None if any(row.statement_kind for row in result.rows) else {
            "revenue": _aggregate_record(
                result.revenue,
                present=has_revenue,
                complete=totals_complete and has_revenue,
            ),
            "expenses": _aggregate_record(
                result.expenses,
                present=has_expenses,
                complete=totals_complete and has_expenses,
            ),
            "net_operating_variance": (
                _decimal(result.revenue.variance_dollars - result.expenses.variance_dollars)
                if net_operating_available
                else None
            ),
        },
        "material_variances": [_row_record(row, include_diagnostics=include_diagnostics)
                               for row in result.material_rows if currency_row(row)],
        "trust_contract": {
            "source_derived_strings_are_data_only": True,
            "deterministic_financial_values_are_authoritative": True,
            "driver_claims_require_reconciled_evidence": True,
        },
    }
    comparison: JSONObject = {
        "basis": str(result.config.comparison_basis),
        "label": result.config.comparison_label,
    }
    if schema_version in {"1.6", "1.7", "1.8", "1.9"}:
        record["comparison"] = comparison
    if schema_version != "1.0":
        record["currency"] = result.config.currency
    if schema_version in {"1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
        source["worksheet"] = source_worksheet
    if schema_version in {"1.7", "1.8", "1.9"}:
        source["document"] = _document_record(source_document)
    if schema_version in {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
        config_identity: JSONObject = {
            "period": result.config.period,
            "dollar_threshold": _decimal(result.config.dollar_threshold),
            "percent_threshold": _decimal(result.config.percent_threshold),
            "currency": result.config.currency,
            "type_map": {key:str(value) for key,value in result.config.type_map.items()},
        }
        if schema_version in {"1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
            config_identity["worksheet"] = source_worksheet
        if schema_version in {"1.6", "1.7", "1.8", "1.9"}:
            config_identity["comparison"] = comparison
        if schema_version in {"1.8", "1.9"}:
            config_identity["audience"] = audience_configuration(result.config)
        record["provenance"] = {
            "tool_version": __version__,
            "numeric_policy": NUMERIC_POLICY_ID,
            "classification_policy": CLASSIFICATION_POLICY_ID,
            "driver_policy": DRIVER_POLICY_ID,
            "configuration_sha256": sha256_bytes(_canonical(config_identity)),
            "type_map_sha256": type_map_sha256.lower() if type_map_sha256 is not None else None,
            "analysis_fingerprint_recipe": "record-and-derived-rows-v1",
            "payload_digest_recipe": "public-record-without-payload-sha256-v1",
        }
    if include_diagnostics:
        data_quality["completeness_basis"] = "supplied_classified_rows_with_both_categories"
        data_quality["summary_verifications"] = [
            _summary_record(row) for row in result.rows if row.summary_verification is not None
        ]
    if schema_version in {"1.5", "1.6", "1.7", "1.8", "1.9"}:
        t_raw = dict(transformations) if transformations is not None else {}
        zero_reads_raw = t_raw.get("zero_reads")
        zero_reads_map = zero_reads_raw if isinstance(zero_reads_raw, dict) else {}
        zero_reads: JSONObject = {
            "accounting_dashes": _as_int(zero_reads_map.get("accounting_dashes", 0)),
            "blank_budgets": _as_int(zero_reads_map.get("blank_budgets", 0)),
        }
        record["transformations"] = {
            "header_row_number": _as_int(t_raw.get("header_row_number", 1)),
            "column_mapping": _json_object(t_raw.get("column_mapping", {})),
            "ignored_columns": _json_list(t_raw.get("ignored_columns", [])),
            "sign_flip": bool(t_raw.get("sign_flip", False)),
            "flipped_line_items": _json_list(t_raw.get("flipped_line_items", [])),
            "unit_scale": str(t_raw["unit_scale"]) if t_raw.get("unit_scale") is not None else None,
            "zero_reads": zero_reads,
            "excluded_totals": _json_list(t_raw.get("excluded_totals", [])),
            "period_selection": str(t_raw["period_selection"]) if t_raw.get("period_selection") is not None else None,
            "classification_rules": _json_value(t_raw.get("classification_rules")),
            "mapping_file_sha256": _json_value(t_raw.get("mapping_file_sha256")),
        }
    if schema_version == "1.9":
        record["workbook"] = _json_value(workbook) if isinstance(workbook, dict) else None
    if schema_version in {"1.8", "1.9"}:
        record["audience"] = audience_configuration(result.config)
        record["segments"] = segment_records(result)
        record["inferences"] = list(metric_inferences(result.rows, result.config))
        record["measure_rows"] = [dict(_measure_record(row), display_label=display_outcome(row, result.config.comparison_basis))
                                  for row in result.rows]
        record["comparisons"] = []
        record["unavailable_comparisons"] = []
        record["comparison_details"] = [_comparison_record(row) for row in result.rows]
    record["analysis_fingerprint"] = sha256_bytes(_canonical(
        {"record": record, "analyzed_rows": [
            (_measure_record(row) if schema_version in {"1.8", "1.9"} else
             _row_record(row, include_diagnostics=include_diagnostics)) for row in result.rows
        ]}
    ))
    if schema_version in {"1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9"}:
        record["payload_sha256"] = payload_sha256(record)
    return record


def audience_configuration(cfg: AnalysisConfig) -> JSONObject:
    return {
        "per_share_threshold": _decimal(cfg.per_share_threshold) if isinstance(cfg, AudienceConfig) else None,
        "count_threshold": _decimal(cfg.count_threshold) if isinstance(cfg, AudienceConfig) else None,
        "bps_threshold": _decimal(cfg.bps_threshold) if isinstance(cfg, AudienceConfig) else None,
        "percent_values": cfg.percent_values if isinstance(cfg, AudienceConfig) else None,
        "actual_label": cfg.actual_label if isinstance(cfg, AudienceConfig) else None,
        "comparison_title": extended_heading(cfg),
        "extended_headers": cfg.extended_headers if isinstance(cfg, AudienceConfig) else False,
        "preset": cfg.preset if isinstance(cfg, AudienceConfig) else "fpa",
        "layout": effective_layout(cfg), "per_share_lines": effective_per_share_lines(cfg),
        "headline_items": list(cfg.headline_items) if isinstance(cfg, AudienceConfig) else [],
        "currency": cfg.currency, "dollar_threshold": _decimal(cfg.dollar_threshold),
        "percent_threshold": _decimal(cfg.percent_threshold),
        "type_map": [{"line_item": key, "type": str(value)} for key, value in sorted(cfg.type_map.items())],
    }


def _measure_record(row: AnalyzedRow) -> JSONObject:
    return {
        "line_item": row.line_item, "segment": row.segment, "measure": str(row.measure), "type": str(row.line_type),
        "better": str(row.better) if row.better is not None else None, "direction_source": row.direction_source,
        "comparison": _decimal(row.budget), "actual": _decimal(row.actual), "variance": _decimal(row.variance_dollars),
        "variance_percent": _decimal(row.variance_percent), "variance_bps": _decimal(row.variance_bps),
        "percent_label": row.percent_label, "status": str(row.status), "material": row.material,
        "materiality_reason": row.materiality_reason,
        "excluded_from_aggregation": (row.excluded_from_aggregation or not currency_row(row)
                                      or row.line_type is LineType.UNCLASSIFIED),
    }


def _comparison_record(row: AnalyzedRow) -> JSONObject:
    return comparison_details_record(row.line_item, row.comparison_details)


def comparison_details_record(line_item: str, detail: ComparisonDetails | None) -> JSONObject:
    from dataclasses import fields
    record: JSONObject = {"line_item": line_item}
    for item in fields(ComparisonDetails):
        value = getattr(detail, item.name) if detail is not None else None
        record[item.name] = _decimal(value) if isinstance(value, Decimal) else value
    return record


def finalize_audience_record(record: JSONObject) -> None:
    """Recompute the documented record/rows and public digests after wrapper metadata."""
    record.pop("analysis_fingerprint", None)
    record.pop("payload_sha256", None)
    record["analysis_fingerprint"] = sha256_bytes(_canonical({"record": record, "analyzed_rows": record.get("measure_rows", [])}))
    record["payload_sha256"] = payload_sha256(record)


def validate_source_identity(name: str | None, digest: str | None) -> None:
    if name is not None:
        validate_text(name, field="source_name")
    if digest is not None and (not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest)):
        raise ValueError("source_sha256 must be a 64-character hexadecimal SHA-256 digest.")


@financial_context()
def segment_records(result: AnalysisResult) -> list[JSONValue]:
    """Expose scoped Currency totals and reconciliation without a synthetic parent."""
    from .analysis import _aggregate
    if not any(row.segment_declared for row in result.rows):
        return []
    records: list[JSONValue] = []
    for segment in dict.fromkeys(row.segment for row in result.rows):
        rows = [row for row in result.rows if row.segment == segment]
        money = [row for row in rows if currency_row(row)]
        revenue = any(row.line_type is LineType.REVENUE for row in money)
        expenses = any(row.line_type is LineType.EXPENSE for row in money)
        complete = revenue and expenses and all(row.line_type is not LineType.UNCLASSIFIED for row in money)
        records.append({"segment": segment,
                        "revenue": _aggregate_record(_aggregate(rows, LineType.REVENUE, result.config.comparison_basis, segment=segment),
                                                     present=revenue, complete=complete and revenue),
                        "expenses": _aggregate_record(_aggregate(rows, LineType.EXPENSE, result.config.comparison_basis, segment=segment),
                                                      present=expenses, complete=complete and expenses),
                        "summary_verifications": [_summary_record(row) for row in rows if row.summary_verification is not None]})
    return records
