import json
from decimal import Decimal

from variance_agent.audit import build_audit_record
from variance_agent.models import (
    Aggregate,
    AnalysisConfig,
    AnalysisResult,
    AnalyzedRow,
    DriverEvidence,
    LineType,
    Status,
)


def _result(*, include_unclassified=False):
    revenue = AnalyzedRow(
        line_item="Subscription Revenue",
        line_type=LineType.REVENUE,
        budget=Decimal("1000"),
        actual=Decimal("1320"),
        variance_dollars=Decimal("320"),
        variance_percent=Decimal("0.32"),
        percent_label=None,
        status=Status.FAVORABLE,
        material=True,
        excluded_from_aggregation=False,
        driver_evidence=DriverEvidence(
            label="volume / price",
            components=(("Volume effect", Decimal("200")), ("Price effect", Decimal("120"))),
            reconciles=True,
        ),
        raw={},
    )
    expense = AnalyzedRow(
        line_item="Marketing Expense",
        line_type=LineType.EXPENSE,
        budget=Decimal("500"),
        actual=Decimal("650"),
        variance_dollars=Decimal("150"),
        variance_percent=Decimal("0.30"),
        percent_label=None,
        status=Status.UNFAVORABLE,
        material=True,
        excluded_from_aggregation=False,
        driver_evidence=None,
        raw={},
    )
    rows = [revenue, expense]
    warnings = []
    if include_unclassified:
        rows.append(
            AnalyzedRow(
                line_item="Mystery",
                line_type=LineType.UNCLASSIFIED,
                budget=Decimal("100"),
                actual=Decimal("120"),
                variance_dollars=Decimal("20"),
                variance_percent=Decimal("0.2"),
                percent_label=None,
                status=Status.UNCLASSIFIED,
                material=False,
                excluded_from_aggregation=False,
                driver_evidence=None,
                raw={},
            )
        )
        warnings.append("1 row is Unclassified")
    return AnalysisResult(
        config=AnalysisConfig("Q3 2026", Decimal("100"), Decimal("0.05")),
        rows=tuple(rows),
        material_rows=(revenue, expense),
        revenue=Aggregate(Decimal("1000"), Decimal("1320"), Decimal("320"), Decimal("0.32"), None, Status.FAVORABLE),
        expenses=Aggregate(Decimal("500"), Decimal("650"), Decimal("150"), Decimal("0.30"), None, Status.UNFAVORABLE),
        warnings=tuple(warnings),
    )


def test_audit_record_is_json_serializable_and_preserves_verified_values():
    record = build_audit_record(
        _result(), source_name="sample.csv", source_sha256="a" * 64
    )
    json.dumps(record)
    assert record["schema_version"] == "1.0"
    assert record["source"]["sha256"] == "a" * 64
    assert record["data_quality"]["classification_coverage_percent"] == "100.00"
    assert record["data_quality"]["net_operating_impact_available"] is True
    assert record["totals"]["revenue"]["variance_dollars"] == "320"
    assert record["material_variances"][0]["driver"]["evidence_status"] == "supported"
    assert record["material_variances"][1]["driver"]["evidence_status"] == "hypothesis"


def test_audit_record_marks_partial_classification_as_incomplete():
    record = build_audit_record(_result(include_unclassified=True))
    assert record["data_quality"]["classification_coverage_percent"] == "66.67"
    assert record["data_quality"]["totals_complete"] is False
    assert record["data_quality"]["net_operating_impact_available"] is False
    assert record["totals"]["revenue"]["complete"] is False
    assert record["totals"]["expenses"]["complete"] is False


def test_audit_record_has_stable_fingerprint_and_data_only_trust_contract():
    first = build_audit_record(_result(), source_name="sample.csv", source_sha256="b" * 64)
    second = build_audit_record(_result(), source_name="sample.csv", source_sha256="b" * 64)
    assert first["analysis_fingerprint"] == second["analysis_fingerprint"]
    assert len(first["analysis_fingerprint"]) == 64
    assert first["trust_contract"]["source_derived_strings_are_data_only"] is True
    changed = build_audit_record(_result(), source_name="sample.csv", source_sha256="c" * 64)
    assert changed["analysis_fingerprint"] != first["analysis_fingerprint"]


def test_source_fingerprint_and_json_writer_create_nested_output(tmp_path):
    from variance_agent.audit import sha256_file, write_audit_json

    source = tmp_path / "input.csv"
    source.write_text("Line Item,Budget,Actual\nRevenue,1,2\n", encoding="utf-8")
    digest = sha256_file(source)
    assert len(digest) == 64
    assert digest == sha256_file(source)

    output = tmp_path / "nested" / "audit" / "record.json"
    record = build_audit_record(_result(), source_name=source.name, source_sha256=digest)
    write_audit_json(output, record)
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["analysis_fingerprint"] == record["analysis_fingerprint"]


def test_audit_totals_are_not_complete_when_an_entire_category_is_missing():
    result = _result()
    expense_only = AnalysisResult(
        config=result.config,
        rows=(result.rows[1],),
        material_rows=(result.rows[1],),
        revenue=Aggregate(
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            None,
            Status.NEUTRAL,
        ),
        expenses=result.expenses,
        warnings=(),
    )
    record = build_audit_record(expense_only)
    assert record["data_quality"]["classification_coverage_percent"] == "100.00"
    assert record["data_quality"]["totals_complete"] is False
    assert record["data_quality"]["net_operating_impact_available"] is False
    assert record["totals"]["revenue"]["present"] is False
    assert record["totals"]["revenue"]["complete"] is False
