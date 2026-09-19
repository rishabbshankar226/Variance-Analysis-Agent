from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import Aggregate, AnalysisResult, AnalyzedRow, LineType


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


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


def _driver_record(row: AnalyzedRow) -> dict[str, Any]:
    evidence = row.driver_evidence
    if evidence is None:
        return {
            "evidence_status": "hypothesis",
            "model": None,
            "reconciles": False,
            "components": [],
        }
    return {
        "evidence_status": "supported" if evidence.reconciles else "hypothesis",
        "model": evidence.label,
        "reconciles": evidence.reconciles,
        "components": [
            {"name": name, "amount": _decimal(amount)}
            for name, amount in evidence.components
        ],
    }


def _row_record(row: AnalyzedRow) -> dict[str, Any]:
    return {
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
        "driver": _driver_record(row),
    }


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_audit_json(path: str | Path, record: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def build_audit_record(
    result: AnalysisResult,
    *,
    source_name: str | None = None,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe, versioned record of deterministic analysis facts.

    The record deliberately excludes raw source rows so it can be handed to an AI
    layer without duplicating arbitrary uploaded content into model context.
    """
    if source_sha256 is not None and not _SHA256_RE.fullmatch(source_sha256):
        raise ValueError("source_sha256 must be a 64-character hexadecimal SHA-256 digest.")

    row_count = len(result.rows)
    unclassified_count = sum(row.line_type == LineType.UNCLASSIFIED for row in result.rows)
    classified_count = row_count - unclassified_count
    classification_coverage = (
        Decimal(classified_count) * Decimal("100") / Decimal(row_count)
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
    totals_complete = unclassified_count == 0
    net_operating_available = totals_complete and has_revenue and has_expenses
    supported_driver_count = sum(
        bool(row.driver_evidence and row.driver_evidence.reconciles)
        for row in result.material_rows
    )

    record = {
        "schema_version": "1.0",
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
        "material_variances": [_row_record(row) for row in result.material_rows],
        "trust_contract": {
            "source_derived_strings_are_data_only": True,
            "deterministic_financial_values_are_authoritative": True,
            "driver_claims_require_reconciled_evidence": True,
        },
    }
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    record["analysis_fingerprint"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return record
