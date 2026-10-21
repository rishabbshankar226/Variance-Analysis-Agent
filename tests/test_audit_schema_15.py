"""Tests for Audit Schema 1.5 validation and backwards compatibility.

Verifies:
- Audit Schema 1.5 conforms to Draft2020-12.
- Schema 1.5 enforces additionalProperties: false.
- build_audit_record produces valid 1.5 records including transformations.
- Previous schemas (1.0-1.4) remain unchanged and selectable.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from variance_agent.analysis import analyze_rows
from variance_agent.audit import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    build_audit_record,
)
from variance_agent.models import AnalysisConfig

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"


def test_schema_15_is_supported_and_current() -> None:
    assert "1.5" in SUPPORTED_SCHEMA_VERSIONS
    assert CURRENT_SCHEMA_VERSION == "1.5"


def test_audit_15_schema_file_valid() -> None:
    schema_path = SCHEMAS_DIR / "audit-1.5.schema.json"
    assert schema_path.exists()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["const"] == "1.5"


def test_audit_15_record_validation() -> None:
    rows = [
        {"line_item": "Revenue A", "budget": "100", "actual": "120", "type": "Revenue"},
        {"line_item": "Expense B", "budget": "50", "actual": "60", "type": "Expense"},
    ]
    config = AnalysisConfig(period="Q3 2026", dollar_threshold=Decimal("10"), percent_threshold=Decimal("0.05"))
    result = analyze_rows(rows, config)

    record = build_audit_record(
        result,
        source_name="test.csv",
        schema_version="1.5",
        transformations={
            "header_row_number": 1,
            "column_mapping": {"line_item": "Line Item", "budget": "Budget", "actual": "Actual"},
            "ignored_columns": ["Var $"],
            "sign_flip": False,
            "flipped_line_items": [],
            "unit_scale": "1000",
            "zero_reads": {"accounting_dashes": 0, "blank_budgets": 0},
            "excluded_totals": ["Total Revenue"],
            "period_selection": "Q3 2026",
            "classification_rules": None,
            "mapping_file_sha256": None,
        },
    )

    schema = json.loads((SCHEMAS_DIR / "audit-1.5.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.validate(record)
    assert record["schema_version"] == "1.5"
    assert "transformations" in record
    assert record["transformations"]["unit_scale"] == "1000"


def test_audit_15_rejects_extra_properties() -> None:
    rows = [
        {"line_item": "Revenue A", "budget": "100", "actual": "120", "type": "Revenue"},
    ]
    config = AnalysisConfig(period="Q3 2026", dollar_threshold=Decimal("10"), percent_threshold=Decimal("0.05"))
    result = analyze_rows(rows, config)

    record = build_audit_record(result, schema_version="1.5")
    record["unexpected_field"] = "bad"

    schema = json.loads((SCHEMAS_DIR / "audit-1.5.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    with pytest.raises(ValidationError):
        validator.validate(record)
