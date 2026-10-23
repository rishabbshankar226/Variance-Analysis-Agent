"""Unreleased 1.8 schema: fictional HALV.FAKE metrics and complete provenance."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
import pytest

from variance_agent import analyze_rows, build_audit_record
from variance_agent.audit import payload_sha256
from test_multi_audience_measures import config, metric


def test_new_schema_is_closed_and_every_new_fact_changes_identity():
    result = analyze_rows([metric("Count", "100", "110")], config())
    record = build_audit_record(result)
    path = Path(__file__).resolve().parents[1] / "schemas/audit-1.8.schema.json"
    schema = json.loads(path.read_text())
    validator = Draft202012Validator(schema)
    validator.validate(record)
    assert payload_sha256(record) == record["payload_sha256"]
    for target in (record, record["audience"], record["measure_rows"][0]):
        changed = deepcopy(record)
        if target is record:
            changed["unknown"] = True
        elif target is record["audience"]:
            changed["audience"]["unknown"] = True
        else:
            changed["measure_rows"][0]["unknown"] = True
        with pytest.raises(ValidationError, match="Additional properties"):
            validator.validate(changed)
    changed = build_audit_record(analyze_rows([metric("Count", "100", "110", better="Lower")], config()))
    assert changed["analysis_fingerprint"] != record["analysis_fingerprint"]
    cutoff = build_audit_record(analyze_rows([metric("Count", "100", "110")],
                                           replace(config(), count_threshold=Decimal("9"))))
    assert cutoff["provenance"]["configuration_sha256"] != record["provenance"]["configuration_sha256"]
