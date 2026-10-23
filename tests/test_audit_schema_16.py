"""Tests for Audit Schema 1.6: records the comparison basis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from tests.comparison_helpers import ROWS, B, F, P, cfg
from variance_agent.analysis import analyze_rows
from variance_agent.audit import (
    SUPPORTED_SCHEMA_VERSIONS,
    build_audit_record,
)
from variance_agent.models import ComparisonBasis

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"


def _validator(version: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS_DIR / f"audit-{version}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_16_is_current() -> None:
    assert "1.6" in SUPPORTED_SCHEMA_VERSIONS
    assert "1.5" in SUPPORTED_SCHEMA_VERSIONS


@pytest.mark.parametrize("basis", (B, F, P))
def test_16_records_comparison_and_validates(basis: ComparisonBasis) -> None:
    record = build_audit_record(analyze_rows(ROWS, cfg(basis, label="FY2024")), schema_version="1.6")
    assert record["comparison"] == {"basis": basis.value, "label": "FY2024"}
    _validator("1.6").validate(record)


def test_16_includes_15_content() -> None:
    record = build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version="1.6")
    assert "transformations" in record
    assert "provenance" in record
    assert "worksheet" in record["source"]  # type: ignore[operator]
    assert "completeness_basis" in record["data_quality"]  # type: ignore[operator]


def test_basis_changes_fingerprint_and_config_hash() -> None:
    a = build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version="1.6")
    b = build_audit_record(analyze_rows(ROWS, cfg(P)), schema_version="1.6")
    assert a["analysis_fingerprint"] != b["analysis_fingerprint"]
    assert a["provenance"]["configuration_sha256"] != b["provenance"]["configuration_sha256"]  # type: ignore[index]


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2", "1.3", "1.4", "1.5"])
def test_old_schema_refused_for_non_budget(version: str) -> None:
    with pytest.raises(ValueError, match="use --audit-schema-version 1.6"):
        build_audit_record(analyze_rows(ROWS, cfg(F)), schema_version=version)


def test_old_schema_still_allowed_for_budget() -> None:
    build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version="1.5")


def test_16_schema_rejects_unknown_basis() -> None:
    record = build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version="1.6")
    record["comparison"]["basis"] = "stretch_target"  # type: ignore[index]
    with pytest.raises(ValidationError):
        _validator("1.6").validate(record)
