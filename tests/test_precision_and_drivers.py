from decimal import Decimal, localcontext

import pytest

from variance_agent.analysis import analyze_rows
from variance_agent.audit import build_audit_record
from variance_agent.models import AnalysisConfig
from variance_agent.report import render_markdown


def cfg(pct=".05"):
    return AnalysisConfig("Q3", Decimal("100"), Decimal(pct))


def test_analysis_is_independent_of_callers_decimal_precision():
    rows = [{"Line Item": "Sales", "Budget": "123456.78", "Actual": "123457.79"}]
    expected = analyze_rows(rows, cfg())
    with localcontext() as context:
        context.prec = 4
        observed = analyze_rows(rows, cfg())
        assert context.prec == 4
    assert observed == expected
    assert observed.rows[0].variance_dollars == Decimal("1.01")


def test_report_and_audit_are_independent_of_callers_decimal_context():
    rows = [
        {"Line Item": "Sales", "Budget": "123456.78", "Actual": "123457.79"},
        {"Line Item": "Rent", "Budget": "23456.78", "Actual": "23457.79"},
        {"Line Item": "Unknown", "Budget": 1, "Actual": 2},
    ]
    result = analyze_rows(rows, cfg())
    report = render_markdown(result)
    audit = build_audit_record(result)
    with localcontext() as context:
        context.prec = 4
        assert render_markdown(result) == report
        assert build_audit_record(result) == audit


def test_materiality_does_not_compare_a_rounded_ratio():
    # 1/3 is strictly greater than this terminating decimal.
    threshold = "0." + "3" * 50
    result = analyze_rows([{"Line Item": "Sales", "Budget": 3, "Actual": 4}], cfg(threshold))
    assert result.rows[0].material


def test_extreme_precision_fails_loudly_instead_of_losing_cents():
    with pytest.raises(ValueError, match="precision|range"):
        analyze_rows([{"Line Item": "Sales", "Budget": "1e100", "Actual": "0.01"}], cfg())


def test_later_reconciled_driver_is_used_if_first_model_does_not_reconcile():
    result = analyze_rows(
        [
            {
                "Line Item": "Sales",
                "Budget": 1000,
                "Actual": 1200,
                "Budget Volume": 1,
                "Actual Volume": 1,
                "Budget Price": 10,
                "Actual Price": 10,
                "Budget Units": 100,
                "Actual Units": 120,
            }
        ],
        cfg(),
    )
    evidence = result.rows[0].driver_evidence
    assert evidence.reconciles
    assert evidence.label == "units / price"
    assert sum(value for _, value in evidence.components) == 200


@pytest.mark.parametrize("missing", ["N/A", "NA", "—", " ", None])
def test_unavailable_optional_driver_does_not_block_valid_model(missing):
    result = analyze_rows(
        [
            {
                "Line Item": "Sales",
                "Budget": 1000,
                "Actual": 1200,
                "Budget Volume": missing,
                "Actual Volume": 1,
                "Budget Price": 10,
                "Actual Price": 10,
                "Budget Units": 100,
                "Actual Units": 120,
            }
        ],
        cfg(),
    )
    assert result.rows[0].driver_evidence.reconciles
    assert result.rows[0].driver_evidence.label == "units / price"


@pytest.mark.parametrize("label", [True, ["Sales"], {"name": "Revenue"}])
def test_line_item_must_be_a_scalar_label(label):
    with pytest.raises(ValueError, match="Line Item"):
        analyze_rows([{"Line Item": label, "Budget": 100, "Actual": 120}], cfg())


@pytest.mark.parametrize("budget", [3, -3])
def test_materiality_exact_boundary_with_negative_and_positive_budgets(budget):
    from fractions import Fraction

    threshold = Decimal("0." + "3" * 50)
    actual = budget + 1
    result = analyze_rows(
        [{"Line Item": "Sales", "Budget": budget, "Actual": actual}], cfg(str(threshold))
    )
    assert result.rows[0].material == (abs(Fraction(1, budget)) > Fraction(threshold))


def test_decimal_rounding_and_traps_do_not_leak_in_or_out():
    from decimal import Inexact, ROUND_UP

    rows = [{"Line Item": "Sales", "Budget": 3, "Actual": 4}]
    expected = analyze_rows(rows, cfg())
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        flags = dict(context.flags)
        assert analyze_rows(rows, cfg()) == expected
        assert render_markdown(expected).startswith("# FP&A")
        assert build_audit_record(expected)["totals"]["revenue"]["variance_dollars"] == "1"
        assert context.prec == 2
        assert context.rounding == ROUND_UP
        assert context.traps[Inexact]
        assert context.flags == flags


def test_cli_threshold_conversion_is_context_independent(tmp_path):
    import json
    from variance_agent.cli import main

    source = tmp_path / "source.csv"
    source.write_text("Line Item,Budget,Actual\nSales,3,4\n")
    destination = tmp_path / "audit.json"
    threshold = "33." + "3" * 48
    with localcontext() as context:
        context.prec = 2
        assert (
            main(
                [
                    str(source),
                    "--period",
                    "Q3",
                    "--dollar-threshold",
                    "100",
                    "--percent-threshold",
                    threshold,
                    "--audit-json",
                    str(destination),
                ]
            )
            == 0
        )
    record = json.loads(destination.read_text())
    assert record["data_quality"]["material_variance_count"] == 1
    assert record["materiality"]["percent_threshold"] == "0." + "3" * 50


def test_large_exact_values_remain_supported():
    result = analyze_rows([{"Line Item": "Sales", "Budget": "1e40", "Actual": "2e40"}], cfg())
    assert result.revenue.variance_dollars == Decimal("1e40")
    assert result.revenue.variance_percent == 1


def test_all_nonreconciling_models_retain_hypothesis_evidence():
    result = analyze_rows(
        [
            {
                "Line Item": "Sales",
                "Budget": 1000,
                "Actual": 1200,
                "Budget Volume": 1,
                "Actual Volume": 1,
                "Budget Price": 10,
                "Actual Price": 10,
                "Budget Units": 2,
                "Actual Units": 2,
            }
        ],
        cfg(),
    )
    evidence = result.rows[0].driver_evidence
    assert evidence is not None
    assert not evidence.reconciles
    assert "Hypothesis" in render_markdown(result)


def test_mutated_decimal_defaults_do_not_change_results(monkeypatch):
    from decimal import DefaultContext, ROUND_UP

    rows = [{"Line Item": "Sales", "Budget": 3, "Actual": 4}]
    expected = analyze_rows(rows, cfg())
    monkeypatch.setattr(DefaultContext, "rounding", ROUND_UP)
    assert analyze_rows(rows, cfg()) == expected
