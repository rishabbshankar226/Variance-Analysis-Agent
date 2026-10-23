"""Fictional Halvorsen Instruments (HALV.FAKE): explicit non-money metrics."""
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
import hashlib
from pathlib import Path

import pytest

from variance_agent import AnalysisConfig, analyze_rows, build_audit_record
from variance_agent.analysis import verify_result
from variance_agent.audience import AudienceConfig
from variance_agent.models import MeasureKind, Status
from variance_agent.report import render_markdown
from variance_agent.parsing import load_file
from variance_agent.xlsx import render_xlsx


def config(**changes):
    values = dict(period="3Q26", dollar_threshold=Decimal("10"), percent_threshold=Decimal("0.02"),
                  per_share_threshold=Decimal("0.01"), count_threshold=Decimal("1000"), bps_threshold=Decimal("25"))
    return AudienceConfig(**(values | changes))


def metric(kind, budget, actual, better="Higher", **fields):
    return {"Line Item": "Fictional KPI", "Measure": kind, "Budget": budget, "Actual": actual,
            "Better": better, **fields}


@pytest.mark.parametrize("step,expected", [("-0.000001", False), ("0", False), ("0.000001", True)])
@pytest.mark.parametrize("kind,baseline,cutoff", [("Per Share", "1", "0.01"), ("Count", "10000", "1000"),
                                                ("Percent", "40", "0.25")])
def test_strict_absolute_cutoffs_are_straddled(kind, baseline, cutoff, step, expected):
    actual = Decimal(baseline) + Decimal(cutoff) + Decimal(step)
    cfg = config(percent_threshold=Decimal("100"), percent_values="points")
    row = analyze_rows([metric(kind, baseline, str(actual))], cfg).rows[0]
    assert row.material is expected


@pytest.mark.parametrize("kind,flag", [("Per Share", "per_share_threshold"), ("Count", "count_threshold"),
                                     ("Percent", "bps_threshold")])
def test_each_new_kind_requires_its_absolute_cutoff(kind, flag):
    with pytest.raises(ValueError, match=flag.replace("_", "-")):
        analyze_rows([metric(kind, "1", "2")], config(**{flag: None}, percent_values="points"))


def test_percent_is_points_and_exact_basis_points_not_percent_of_percent():
    result = analyze_rows([metric("Percent", "41.2%", "40.6%")], config())
    row = result.rows[0]
    assert row.measure is MeasureKind.PERCENT
    assert Fraction(row.variance_bps) == (Fraction("40.6") - Fraction("41.2")) * 100
    assert row.variance_percent is None and row.percent_label == "N/A (rate)"
    assert row.status is Status.UNFAVORABLE and row.material
    assert "-60 bps" in render_markdown(result)
    assert "$40.60" not in render_markdown(result)


def test_percent_fraction_requires_an_explicit_scale_and_can_match_points():
    rows = [metric("Percent", "0.412", "0.406")]
    with pytest.raises(ValueError, match="Fictional KPI.*percent-values"):
        analyze_rows(rows, config())
    assert analyze_rows(rows, config(percent_values="fractions")).rows[0].variance_bps == Decimal("-60")


@pytest.mark.parametrize("kind", ["Percent", "Count"])
def test_direction_is_required_for_rates_and_counts(kind):
    with pytest.raises(ValueError, match="Fictional KPI.*Higher or Lower"):
        analyze_rows([metric(kind, "1", "2", better="")], config(percent_values="points"))


def test_per_share_default_is_visible_and_keeps_real_type_out_of_money_totals():
    rows = [metric("Per Share", "0.84", "0.91", better="", Type="Revenue")]
    result = analyze_rows(rows, config())
    row = result.rows[0]
    assert row.status is Status.FAVORABLE and row.direction_source == "default_higher"
    assert result.revenue.actual == Decimal("0")
    assert "$0.07/sh" in render_markdown(result)
    assert any("Higher" in note for note in result.warnings)
    record = build_audit_record(result)
    assert record["schema_version"] == "1.8"
    assert record["measure_rows"][0]["measure"] == "Per Share"
    assert record["inferences"]


def test_non_money_does_not_make_complete_currency_totals_incomplete():
    rows = [{"Line Item": "Revenue", "Type": "Revenue", "Budget": "100", "Actual": "110"},
            {"Line Item": "Expense", "Type": "Expense", "Budget": "40", "Actual": "42"},
            metric("Count", "10", "11")]
    result = analyze_rows(rows, config())
    record = build_audit_record(result)
    assert record["totals"]["net_operating_variance"] == "8"
    assert record["data_quality"]["totals_complete"] is True


def test_currency_type_wins_and_a_conflicting_direction_is_rejected():
    with pytest.raises(ValueError, match="Fictional KPI.*contradicts.*Expense"):
        analyze_rows([metric("Currency", "10", "11", Type="Expense")], config())
    row = analyze_rows([metric("Currency", "10", "11", better="Lower", Type="Expense")], config()).rows[0]
    assert row.status is Status.UNFAVORABLE


def test_better_can_score_a_nonadditive_currency_profit_line():
    result = analyze_rows([metric("Currency", "100", "110", **{"Line Item": "EBITDA"})], config())
    assert result.rows[0].status is Status.FAVORABLE
    assert result.revenue.actual == 0 and result.expenses.actual == 0


@pytest.mark.parametrize("field,value", [("Actual", 1.1), ("Budget", True)])
def test_new_metrics_refuse_float_or_boolean_amounts(field, value):
    with pytest.raises(ValueError, match="Fictional KPI.*(float|boolean)"):
        analyze_rows([metric("Count", "1", "2", **{field: value})], config())


def test_output_boundary_rejects_forged_basis_points():
    result = analyze_rows([metric("Percent", "41.2%", "40.6%")], config())
    forged = replace(result, rows=(replace(result.rows[0], variance_bps=Decimal("-59")),))
    with pytest.raises(RuntimeError, match="basis.point.*mismatch"):
        verify_result(forged)


def test_legacy_sample_workbook_and_report_are_byte_identical():
    root = Path(__file__).resolve().parents[1]
    result = analyze_rows(load_file(root / "examples/sample_variance.csv"),
                          AnalysisConfig("Q3 2026", Decimal("10000"), Decimal("0.05")))
    assert hashlib.sha256(render_xlsx(result)).hexdigest() == "11db3182fb2f5b377e7973016e9b51fc0780e96fd80d6b3471e1c6633025ee43"
    assert hashlib.sha256(render_markdown(result).encode()).hexdigest() == (
        "63f5d2d61de895f715d8270d948fb1b6d54208fa582f461c95a4e49b637d8587")
    assert build_audit_record(result)["schema_version"] == "1.7"


def test_legacy_schema_cannot_silently_drop_new_measure_facts():
    result = analyze_rows([metric("Count", "10", "11")], config())
    with pytest.raises(ValueError, match="1.8"):
        build_audit_record(result, schema_version="1.7")


def test_output_boundary_rejects_a_forged_direction_even_with_matching_status():
    result = analyze_rows([metric("Count", "10", "11")], config())
    from variance_agent.models import BetterDirection
    forged_row = replace(result.rows[0], better=BetterDirection.LOWER, status=Status.UNFAVORABLE)
    forged = replace(result, rows=(forged_row,), material_rows=(forged_row,))
    with pytest.raises(RuntimeError, match="direction.*mismatch"):
        verify_result(forged)


def test_existing_public_constructors_and_functions_keep_their_parameters():
    from inspect import signature
    from variance_agent import AnalysisResult
    assert list(signature(AnalysisConfig).parameters) == [
        "period", "dollar_threshold", "percent_threshold", "type_map", "currency", "comparison_basis", "comparison_label"]
    assert list(signature(AnalysisResult).parameters) == ["config", "rows", "material_rows", "revenue", "expenses", "warnings"]
    assert list(signature(analyze_rows).parameters) == ["rows", "config"]
    assert list(signature(build_audit_record).parameters) == [
        "result", "source_name", "source_sha256", "schema_version", "type_map_sha256", "source_worksheet", "transformations",
        "source_document"]
