"""Human-reviewed financial reports and the published audit wire contract."""

import copy
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from variance_agent.analysis import analyze_rows
from variance_agent.audit import SUPPORTED_SCHEMA_VERSIONS, build_audit_record, serialize_audit_json
from variance_agent.models import AnalysisConfig
from variance_agent.report import render_markdown

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "contracts"
CASES = ("complete", "incomplete", "zero_budget", "no_material", "summary")


def fixture_result(name):
    path = FIXTURES / f"{name}.input.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = payload["config"]
    return path, analyze_rows(payload["rows"], AnalysisConfig(
        config["period"], Decimal(config["dollar_threshold"]),
        Decimal(config["percent_threshold"]),
    ))


def audit_validator(version="1.0"):
    path = ROOT / "schemas" / f"audit-{version}.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize("name", CASES)
def test_markdown_matches_reviewed_golden(name):
    _, result = fixture_result(name)
    assert render_markdown(result) == (FIXTURES / f"{name}.report.md").read_text("utf-8")


@pytest.mark.parametrize("name", CASES)
def test_audit_matches_reviewed_golden_and_published_schema(name):
    path, result = fixture_result(name)
    record = build_audit_record(result, source_name=path.name,
                              source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                              schema_version="1.0")
    expected = (FIXTURES / f"{name}.audit.json").read_text("utf-8")
    assert serialize_audit_json(record) == expected
    audit_validator().validate(record)


@pytest.mark.parametrize("name", CASES)
def test_current_audit_schema_accepts_engine_output(name):
    _, result = fixture_result(name)
    record = build_audit_record(result)
    audit_validator(record["schema_version"]).validate(record)


@pytest.mark.parametrize("version", SUPPORTED_SCHEMA_VERSIONS)
@pytest.mark.parametrize("name", CASES)
def test_each_selectable_wire_version_matches_its_immutable_schema(name, version):
    _, result = fixture_result(name)
    audit_validator(version).validate(build_audit_record(result, schema_version=version))


@pytest.mark.parametrize("mutation", (
    lambda r: r.pop("trust_contract"),
    lambda r: r.update(schema_version="99.0"),
    lambda r: r["source"].update(sha256="not-a-hash"),
    lambda r: r["totals"]["revenue"].update(actual=1320.0),
    lambda r: r["totals"]["revenue"].update(actual="NaN"),
    lambda r: r["material_variances"][0].update(status="Good"),
    lambda r: r["material_variances"][0]["driver"].update(evidence_status="certain"),
    lambda r: r["trust_contract"].update(source_derived_strings_are_data_only=False),
))
def test_schema_rejects_invalid_consumer_records(mutation):
    record = json.loads((FIXTURES / "complete.audit.json").read_text("utf-8"))
    changed = copy.deepcopy(record)
    mutation(changed)
    with pytest.raises(ValidationError):
        audit_validator().validate(changed)
