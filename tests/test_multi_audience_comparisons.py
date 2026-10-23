"""Fictional HALV.FAKE and BRWB.FAKE: supplied comparisons, never estimates."""
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from variance_agent import analyze_rows, build_audit_record
from variance_agent.comparisons import analyze_comparisons, display_outcome
from variance_agent.models import ComparisonBasis as Basis
from variance_agent.parsing import load_file
from variance_agent.report import render_markdown
from test_multi_audience_measures import config

FIX = Path(__file__).parent / "fixtures/multi_audience"


def test_scenario_a_all_values_and_nonmaterial_opex():
    table = analyze_comparisons(load_file(FIX / "consensus.csv"), config(), (Basis.CONSENSUS,))
    result = table.comparisons[0].result
    assert result is not None
    expected = [("37.5", "0.03", "Beat"), ("3.0", None, "In line"),
                ("-0.6", None, "Miss"), ("0.07", None, "Beat"), ("-1500", None, "Miss")]
    for row, (amount, pct, label) in zip(result.rows, expected, strict=True):
        assert row.variance_dollars == Decimal(amount)
        if pct:
            assert row.variance_percent == Decimal(pct)
        assert display_outcome(row, Basis.CONSENSUS) == label
    assert result.rows[1].status == "U" and not result.rows[1].material
    assert result.rows[2].variance_bps == Decimal("-60")
    text = render_markdown(result)
    for value in ("Beat", "Miss", "In line", "-60 bps", "8.3%", "-3.1%"):
        assert value in text


@pytest.mark.parametrize("actual,position", [("1239.99", "Below range"), ("1240", "Within range"),
    ("1240.01", "Within range"), ("1279.99", "Within range"), ("1280", "Within range"),
    ("1280.01", "Above range"), ("1287.5", "Above range")])
def test_guidance_midpoint_and_both_inclusive_ends_with_fraction_oracle(actual, position):
    rows = [{"Line Item": "Revenue", "Type": "Revenue", "Guidance Low": "1240", "Guidance High": "1280", "Actual": actual}]
    result = analyze_comparisons(rows, config(), (Basis.GUIDANCE,)).comparisons[0].result
    row = result.rows[0]
    assert Fraction(row.budget) == (Fraction("1240") + Fraction("1280")) / 2
    assert row.comparison_details.guidance_position == position
    assert "Beat" not in render_markdown(result)
    assert position in render_markdown(result)


def test_loss_surprise_uses_absolute_consensus():
    result = analyze_comparisons(load_file(FIX / "loss.csv"), config(), (Basis.CONSENSUS,)).comparisons[0].result
    row = result.rows[0]
    assert row.variance_dollars == Decimal("0.05") and row.variance_percent == Decimal("0.5")
    assert display_outcome(row, Basis.CONSENSUS) == "Beat"


@pytest.mark.parametrize("basis", [Basis.CONSENSUS, Basis.ESTIMATE, Basis.GUIDANCE])
@pytest.mark.parametrize("schema", ["1.0", "1.6", "1.7"])
def test_new_bases_refuse_legacy_audit_versions(basis, schema):
    result = analyze_rows([{"Line Item": "Revenue", "Type": "Revenue", "Budget": "100", "Actual": "110"}],
                          replace(config(), comparison_basis=basis))
    with pytest.raises(ValueError, match="1.8"):
        build_audit_record(result, schema_version=schema)


def test_new_basis_audit_validates_and_records_consensus_metadata():
    result = analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "Consensus Mean": "100", "Actual": "110",
                                  "Low": "95", "High": "105", "# Est.": "12", "Std. Dev.": "3"}],
                                config(), (Basis.CONSENSUS,)).comparisons[0].result
    record = build_audit_record(result)
    schema = json.loads((FIX.parents[2] / "schemas/audit-1.8.schema.json").read_text())
    Draft202012Validator(schema).validate(record)
    details = record["comparison_details"][0]
    assert details["estimator_count"] == 12 and details["consensus_high"] == "105"
    assert details["consensus_range_position"] == "above the high estimate"
    assert "above the high estimate" in render_markdown(result)


@pytest.mark.parametrize("label", ["Est.", "Estimate"])
def test_ambiguous_estimate_asks_instead_of_becoming_consensus(label):
    with pytest.raises(ValueError, match="consensus.*own model"):
        analyze_comparisons([{"Line Item": "Revenue", label: "100", "Actual": "110"}], config(), (Basis.CONSENSUS,))


def test_missing_consensus_is_distinct_from_supplied_zero():
    table = analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "Consensus": "", "Actual": "110"},
                                {"Line Item": "Other Revenue", "Type": "Revenue", "Consensus": "0.00", "Actual": "0"}],
                               config(), (Basis.CONSENSUS,))
    comparison = table.comparisons[0]
    assert len(comparison.unavailable) == 1 and comparison.unavailable[0].line_item == "Revenue"
    assert comparison.result.rows[0].budget == 0 and comparison.result.rows[0].variance_percent is None
    assert display_outcome(comparison.result.rows[0], Basis.CONSENSUS) == "In line"


def test_reversed_guidance_and_negative_dispersion_are_named_errors():
    with pytest.raises(ValueError, match="Revenue.*low.*high"):
        analyze_comparisons([{"Line Item": "Revenue", "Guidance Low": "10", "Guidance High": "9", "Actual": "11"}],
                            config(), (Basis.GUIDANCE,))
    with pytest.raises(ValueError, match="Revenue.*deviation.*non-negative"):
        analyze_comparisons([{"Line Item": "Revenue", "Consensus": "10", "Actual": "11", "Std Dev": "-1"}],
                            config(), (Basis.CONSENSUS,))


def test_unclassified_zero_does_not_receive_a_consensus_outcome():
    result = analyze_comparisons([{"Line Item": "Fictional Unknown KPI", "Consensus": "10", "Actual": "10"}],
                                config(), (Basis.CONSENSUS,)).comparisons[0].result
    assert display_outcome(result.rows[0], Basis.CONSENSUS) not in {"Beat", "Miss", "In line"}


def test_guidance_midpoint_is_verified_at_the_engine_boundary():
    with pytest.raises(ValueError, match="Revenue.*midpoint"):
        analyze_rows([{"Line Item": "Revenue", "Type": "Revenue", "Budget": "99", "Actual": "110",
                       "guidance_low": "90", "guidance_high": "110"}], replace(config(), comparison_basis=Basis.GUIDANCE))


def test_missing_consensus_still_validates_supplied_dispersion():
    with pytest.raises(ValueError, match="Revenue.*deviation.*non-negative"):
        analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "Consensus": "", "Actual": "110", "Std Dev": "-1"}],
                            config(), (Basis.CONSENSUS,))
