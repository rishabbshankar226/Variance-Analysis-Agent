from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import Aggregate, AnalysisResult, AnalyzedRow, LineType
from .output import write_text_outputs
from .numeric import NUMERIC_POLICY_ID, financial_context, ratio
from .analysis import CLASSIFICATION_POLICY_ID, DRIVER_POLICY_ID
from .version import __version__

CURRENT_SCHEMA_VERSION = "1.4"
SUPPORTED_SCHEMA_VERSIONS = ("1.0", "1.1", "1.2", "1.3", "1.4")


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def payload_sha256(record: dict[str, Any]) -> str:
    """Public integrity recipe: omit only the digest itself; this is not authentication."""
    return sha256_bytes(_canonical({key:value for key,value in record.items()
                                   if key != "payload_sha256"}))


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _aggregate_record(aggregate: Aggregate, *, present: bool, complete: bool) -> dict[str, Any]:
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


def _driver_record(row: AnalyzedRow, *, include_diagnostics: bool = False) -> dict[str, Any]:
    evidence = row.driver_evidence
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


def _row_record(row: AnalyzedRow, *, include_diagnostics: bool = False) -> dict[str, Any]:
    record = {
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


def _summary_record(row: AnalyzedRow) -> dict[str, Any]:
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


def serialize_audit_json(record: dict[str, Any]) -> str:
    return json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def write_audit_json(path: str | Path, record: dict[str, Any]) -> None:
    write_text_outputs({Path(path): serialize_audit_json(record)})


@financial_context()
def build_audit_record(
    result: AnalysisResult,
    *,
    source_name: str | None = None,
    source_sha256: str | None = None,
    schema_version: str | None = None,
    type_map_sha256: str | None = None,
    source_worksheet: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe, versioned record of deterministic analysis facts.

    Raw source rows are excluded. Downstream report consumers receive verified
    facts and selected source metadata; source text remains untrusted data.
    """
    schema_version = CURRENT_SCHEMA_VERSION if schema_version is None else schema_version
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported audit schema version {schema_version!r}.")
    if schema_version == "1.0" and result.config.currency != "USD":
        raise ValueError("Audit schema 1.0 supports USD only; select a newer audit schema.")
    if source_sha256 is not None and not _SHA256_RE.fullmatch(source_sha256):
        raise ValueError("source_sha256 must be a 64-character hexadecimal SHA-256 digest.")
    if type_map_sha256 is not None and not _SHA256_RE.fullmatch(type_map_sha256):
        raise ValueError("type_map_sha256 must be a 64-character hexadecimal SHA-256 digest.")
    if source_worksheet is not None and (not isinstance(source_worksheet, str) or not source_worksheet):
        raise ValueError("source_worksheet must be a nonempty worksheet name or null.")
    include_diagnostics = schema_version in {"1.3", "1.4"}

    row_count = len(result.rows)
    unclassified_count = sum(row.line_type == LineType.UNCLASSIFIED for row in result.rows)
    classified_count = row_count - unclassified_count
    classification_coverage = (
        ratio(Decimal(classified_count) * Decimal("100"), Decimal(row_count))
        if row_count
        else Decimal("0")
    )
    has_revenue = any(
        row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
        for row in result.rows
    )
    has_expenses = any(
        row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
        for row in result.rows
    )
    totals_complete = unclassified_count == 0 and has_revenue and has_expenses
    net_operating_available = totals_complete
    supported_driver_count = sum(
        bool(row.driver_evidence and row.driver_evidence.reconciles)
        for row in result.material_rows
    )

    record = {
        "schema_version": schema_version,
        "period": result.config.period,
        "source": {
            "name": source_name,
            "sha256": source_sha256.lower() if source_sha256 is not None else None,
        },
        "materiality": {
            "dollar_threshold": _decimal(result.config.dollar_threshold),
            "percent_threshold": _decimal(result.config.percent_threshold),
            "comparison": "strictly_greater_than",
            "logic": "absolute_dollar_or_absolute_percent",
        },
        "data_quality": {
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
        },
        "totals": {
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
                               for row in result.material_rows],
        "trust_contract": {
            "source_derived_strings_are_data_only": True,
            "deterministic_financial_values_are_authoritative": True,
            "driver_claims_require_reconciled_evidence": True,
        },
    }
    if schema_version != "1.0":
        record["currency"] = result.config.currency
    if schema_version == "1.4":
        record["source"]["worksheet"] = source_worksheet
    if schema_version in {"1.2", "1.3", "1.4"}:
        config_identity = {
            "period": result.config.period,
            "dollar_threshold": _decimal(result.config.dollar_threshold),
            "percent_threshold": _decimal(result.config.percent_threshold),
            "currency": result.config.currency,
            "type_map": {key:str(value) for key,value in result.config.type_map.items()},
        }
        if schema_version == "1.4":
            config_identity["worksheet"] = source_worksheet
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
        record["data_quality"]["completeness_basis"] = "supplied_classified_rows_with_both_categories"
        record["data_quality"]["summary_verifications"] = [
            _summary_record(row) for row in result.rows if row.summary_verification is not None
        ]
    record["analysis_fingerprint"] = sha256_bytes(_canonical(
        {"record": record, "analyzed_rows": [
            _row_record(row, include_diagnostics=include_diagnostics) for row in result.rows
        ]}
    ))
    if schema_version in {"1.2", "1.3", "1.4"}:
        record["payload_sha256"] = payload_sha256(record)
    return record
