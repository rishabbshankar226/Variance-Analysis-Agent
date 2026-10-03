import hashlib
import json
from decimal import Decimal

import pytest

import variance_agent.cli as cli
from variance_agent import __version__
from variance_agent.analysis import analyze_rows
from variance_agent.audit import CURRENT_SCHEMA_VERSION, build_audit_record, payload_sha256
from variance_agent.models import AnalysisConfig, LineType


def result(type_map=None):
    return analyze_rows([{"Line Item":"Sales", "Budget":"10", "Actual":"12"}],
                        AnalysisConfig("Q3", Decimal("1"), Decimal(".05"), type_map or {}))


def test_current_record_contains_versioned_policy_and_recomputable_payload_identity():
    record = build_audit_record(result())
    assert record["schema_version"] == CURRENT_SCHEMA_VERSION
    assert record["provenance"]["tool_version"] == __version__
    assert record["provenance"]["analysis_fingerprint_recipe"] == "record-and-derived-rows-v1"
    assert record["provenance"]["type_map_sha256"] is None
    payload = {key:value for key,value in record.items() if key != "payload_sha256"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False).encode("utf-8")
    assert record["payload_sha256"] == hashlib.sha256(canonical).hexdigest()


def test_effective_type_map_changes_identity_even_when_financial_values_match():
    inferred = build_audit_record(result())
    mapped = build_audit_record(result({"Sales":LineType.REVENUE}))
    assert inferred["totals"] == mapped["totals"]
    assert (inferred["provenance"]["configuration_sha256"]
            != mapped["provenance"]["configuration_sha256"])
    assert inferred["analysis_fingerprint"] != mapped["analysis_fingerprint"]


def test_cli_hashes_the_exact_bytes_analyzed_during_source_and_map_replacement(tmp_path, monkeypatch):
    source, mapping, audit = tmp_path/"source.csv", tmp_path/"map.json", tmp_path/"audit.json"
    original = b"Line Item,Budget,Actual\nSales,10,12\n"
    replacement = b"Line Item,Budget,Actual\nSales,10,99\n"
    original_map = b'{"Sales":"Revenue"}'
    source.write_bytes(original)
    mapping.write_bytes(original_map)
    # Model an A->B->A producer replacement at the parser boundary. The result
    # must identify the bytes actually parsed, not a separate observation of A.
    if hasattr(cli, "load_input"):
        parse = cli.load_input
        def replace_after_capture(data, suffix, **kwargs):
            source.write_bytes(replacement)
            mapping.write_bytes(b'{"Sales":"Expense"}')
            return parse(data, suffix, **kwargs)
        monkeypatch.setattr(cli, "load_input", replace_after_capture)
    else:
        parse = cli.load_file
        def replace_between_observations(path):
            source.write_bytes(replacement)
            rows = parse(path)
            source.write_bytes(original)
            return rows
        monkeypatch.setattr(cli, "load_file", replace_between_observations)
    assert cli.main([str(source), "--period", "Q3", "--dollar-threshold", "1",
                     "--percent-threshold", "5", "--type-map", str(mapping),
                     "--audit-json", str(audit)]) == 0
    record = json.loads(audit.read_text())
    assert record["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert record["totals"]["revenue"]["actual"] == "12"
    assert record["provenance"]["type_map_sha256"] == hashlib.sha256(original_map).hexdigest()


def test_type_map_digest_is_validated():
    with pytest.raises(ValueError, match="type_map_sha256"):
        build_audit_record(result(), type_map_sha256="bad")


@pytest.mark.parametrize("version", ["1.0", "1.1"])
def test_archived_output_versions_do_not_acquire_new_provenance_fields(version):
    record = build_audit_record(result(), schema_version=version)
    assert "provenance" not in record
    assert "payload_sha256" not in record


def test_public_digest_survives_json_roundtrip_and_detects_changed_facts():
    record = build_audit_record(result(), source_name="finance € ledger.csv")
    loaded = json.loads(json.dumps(record))
    assert payload_sha256(loaded) == loaded["payload_sha256"]
    loaded["material_variances"][0]["actual"] = "99"
    assert payload_sha256(loaded) != loaded["payload_sha256"]


def test_effective_map_identity_does_not_depend_on_dictionary_order():
    first = build_audit_record(result({"Sales":LineType.REVENUE, "Other":LineType.EXPENSE}))
    second = build_audit_record(result({"Other":LineType.EXPENSE, "Sales":LineType.REVENUE}))
    assert first == second
