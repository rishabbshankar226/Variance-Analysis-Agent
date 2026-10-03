from decimal import Decimal

import pytest

from variance_agent.analysis import analyze_rows
from variance_agent.audit import build_audit_record
from variance_agent.models import AnalysisConfig, LineType


CONFIG = AnalysisConfig("Q3", Decimal("10"), Decimal(".05"))


@pytest.mark.parametrize("row,mapping,source", [
    ({"Type":"Expense"}, {"Sales":LineType.REVENUE}, "type_map"),
    ({"Type":"Revenue"}, {}, "explicit_type"),
    ({"Type":"unknown"}, {}, "unrecognized_type"),
    ({}, {}, "label_inference"),
])
def test_classification_decision_is_exposed_at_its_actual_precedence(row, mapping, source):
    result = analyze_rows([{"Line Item":"Sales", "Budget":"100", "Actual":"132"} | row],
                          AnalysisConfig("Q3", Decimal("10"), Decimal(".05"), mapping))
    record = build_audit_record(result)
    assert record["material_variances"][0]["classification_source"] == source
    assert record["material_variances"][0]["materiality_reason"] == "absolute_amount"


def test_supported_driver_exposes_exact_residuals_and_applied_tolerances():
    row = {"Line Item":"Sales", "Budget":"100", "Actual":"132",
           "Budget Units":"10", "Actual Units":"12", "Budget Price":"10", "Actual Price":"11"}
    record = build_audit_record(analyze_rows([row], CONFIG))
    evidence = record["material_variances"][0]["driver"]
    assert evidence["evidence_status"] == "supported"
    assert evidence["reconciliation"] == {
        "modeled_budget":"100", "modeled_actual":"132", "budget_residual":"0",
        "actual_residual":"0", "component_residual":"0", "amount_tolerance":"0.01",
        "variance_tolerance":"0.01", "failure_reasons":[],
    }


def test_failed_first_complete_driver_keeps_hypothesis_with_failure_reasons():
    row = {"Line Item":"Sales", "Budget":"100", "Actual":"132",
           "Budget Units":"10", "Actual Units":"12", "Budget Price":"9", "Actual Price":"9"}
    driver = build_audit_record(analyze_rows([row], CONFIG))["material_variances"][0]["driver"]
    assert driver["model"] == "units / price"
    assert driver["evidence_status"] == "hypothesis"
    assert driver["reconciliation"]["budget_residual"] == "-10"
    assert driver["reconciliation"]["actual_residual"] == "-24"
    assert driver["reconciliation"]["component_residual"] == "-14"
    assert driver["reconciliation"]["failure_reasons"] == [
        "budget_outside_tolerance", "actual_outside_tolerance", "components_outside_tolerance"]


def test_reconciled_excluded_summary_has_reviewable_evidence():
    rows = [{"Line Item":"Sales", "Budget":"100", "Actual":"120"},
            {"Line Item":"Total Revenue", "Budget":"100", "Actual":"120"},
            {"Line Item":"Rent Expense", "Budget":"50", "Actual":"60"}]
    result = analyze_rows(rows, CONFIG)
    assert result.revenue.actual == Decimal("120")
    summaries = build_audit_record(result)["data_quality"]["summary_verifications"]
    assert len(summaries) == 1
    assert summaries[0] == {
        "line_item":"Total Revenue", "type":"Revenue", "summary_source":"inferred_summary",
        "outcome":"reconciled_and_excluded", "detail_count":1,
        "budget_residual":"0", "actual_residual":"0", "tolerance":"0.01",
    }


def test_standalone_summary_is_included_and_not_claimed_reconciled():
    record = build_audit_record(analyze_rows([
        {"Line Item":"Total Revenue", "Budget":"100", "Actual":"120"}], CONFIG))
    summary = record["data_quality"]["summary_verifications"][0]
    assert summary["outcome"] == "included_standalone"
    assert summary["budget_residual"] is None
    assert summary["detail_count"] == 0


def test_materiality_reason_records_the_comparison_that_triggered_selection():
    config = AnalysisConfig("Q3", Decimal("1000"), Decimal(".05"))
    record = build_audit_record(analyze_rows([
        {"Line Item":"Sales", "Budget":"100", "Actual":"106"}], config))
    assert record["material_variances"][0]["materiality_reason"] == "absolute_percent"


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2"])
def test_older_wire_formats_do_not_acquire_diagnostics(version):
    record = build_audit_record(analyze_rows([
        {"Line Item":"Sales", "Budget":"100", "Actual":"132"}], CONFIG), schema_version=version)
    assert "classification_source" not in record["material_variances"][0]
    assert "reconciliation" not in record["material_variances"][0]["driver"]
    assert "summary_verifications" not in record["data_quality"]


def test_optional_hypothesis_diagnostics_do_not_add_precision_failures():
    row = {"Line Item":"Sales", "Budget":"100", "Actual":"120",
           "Budget Units":"-1", "Actual Units":"1",
           "Budget Price":"2", "Actual Price":"9" * 50}
    driver = build_audit_record(analyze_rows([row], CONFIG))["material_variances"][0]["driver"]
    assert driver["evidence_status"] == "hypothesis"
    assert driver["reconciliation"]["component_residual"] is None
    assert "components_residual_unavailable" in driver["reconciliation"]["failure_reasons"]


def test_materiality_diagnostics_preserve_amount_comparison_short_circuit():
    config = AnalysisConfig("Q3", Decimal("1"), Decimal("1e999"))
    record = build_audit_record(analyze_rows([
        {"Line Item":"Sales", "Budget":"1e100", "Actual":"1.1e100"}], config))
    assert record["material_variances"][0]["materiality_reason"] == "absolute_amount"
