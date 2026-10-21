"""Tests for Audit Schema 1.7: records how a PDF statement was read."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from tests.comparison_helpers import ROWS, B, P, cfg
from variance_agent.analysis import analyze_rows
from variance_agent.audit import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    build_audit_record,
)

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
DOCUMENT = {
    "kind": "pdf",
    "statement": "Consolidated Statements of Operations (p. 4)",
    "pages": [4],
    "reader_notes": ["Read column 'Year Ended December 31, 2025' as FY2025"],
}


def _validator(version: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS_DIR / f"audit-{version}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_17_is_current() -> None:
    assert CURRENT_SCHEMA_VERSION == "1.7"
    assert "1.6" in SUPPORTED_SCHEMA_VERSIONS


def test_17_records_the_pdf_document_and_validates() -> None:
    record = build_audit_record(analyze_rows(ROWS, cfg(P, label="FY2024")),
                                schema_version="1.7", source_document=DOCUMENT)
    assert record["source"]["document"] == DOCUMENT  # type: ignore[index]
    _validator("1.7").validate(record)


def test_17_without_a_document_records_null() -> None:
    record = build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version="1.7")
    assert record["source"]["document"] is None  # type: ignore[index]
    _validator("1.7").validate(record)


def test_17_includes_16_content() -> None:
    record = build_audit_record(analyze_rows(ROWS, cfg(P, label="FY2024")), schema_version="1.7")
    assert record["comparison"] == {"basis": "prior_period", "label": "FY2024"}
    for key in ("transformations", "provenance", "payload_sha256"):
        assert key in record


def test_document_changes_the_fingerprint() -> None:
    plain = build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version="1.7")
    pdf = build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version="1.7",
                             source_document=DOCUMENT)
    assert plain["analysis_fingerprint"] != pdf["analysis_fingerprint"]


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6"])
def test_old_schema_refused_for_pdf_input(version: str) -> None:
    with pytest.raises(ValueError, match="use --audit-schema-version 1.7 for PDF input"):
        build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version=version,
                           source_document=DOCUMENT)


def test_17_schema_rejects_unknown_document_fields() -> None:
    record = build_audit_record(analyze_rows(ROWS, cfg(B)), schema_version="1.7",
                                source_document=DOCUMENT)
    record["source"]["document"]["ocr"] = True  # type: ignore[index]
    with pytest.raises(ValidationError):
        _validator("1.7").validate(record)
