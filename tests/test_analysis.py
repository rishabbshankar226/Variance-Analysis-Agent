from decimal import Decimal

import pytest

from variance_agent.analysis import analyze_rows
from variance_agent.models import AnalysisConfig, LineType, Status


def config(dollars="10000", pct="0.05"):
    return AnalysisConfig(
        period="Q3 2026",
        dollar_threshold=Decimal(dollars),
        percent_threshold=Decimal(pct),
    )


def test_fu_logic_and_materiality_sorting():
    rows = [
        {"Line Item": "Product Revenue", "Budget": "100000", "Actual": "120000", "Type": "Revenue"},
        {"Line Item": "Marketing Expense", "Budget": "50000", "Actual": "62000", "Type": "Expense"},
        {"Line Item": "Rent Expense", "Budget": "30000", "Actual": "25000", "Type": "Expense"},
    ]
    result = analyze_rows(rows, config())
    assert result.rows[0].status == Status.FAVORABLE
    assert result.rows[1].status == Status.UNFAVORABLE
    assert result.rows[2].status == Status.FAVORABLE
    assert [r.line_item for r in result.material_rows] == [
        "Product Revenue",
        "Marketing Expense",
        "Rent Expense",
    ]


def test_zero_budget_rules():
    rows = [
        {"Line Item": "Other Revenue", "Budget": 0, "Actual": 5000, "Type": "Revenue"},
        {"Line Item": "Utilities Expense", "Budget": 0, "Actual": 0, "Type": "Expense"},
        {"Line Item": "Rebate Revenue", "Budget": 0, "Actual": -100, "Type": "Revenue"},
    ]
    result = analyze_rows(rows, config(dollars="999999", pct="0.05"))
    assert result.rows[0].variance_percent is None
    assert result.rows[0].percent_label == "N/A (Unbudgeted)"
    assert result.rows[1].variance_percent == 0
    assert result.rows[2].variance_percent is None
    assert result.rows[2].variance_dollars == Decimal("-100")


def test_threshold_is_strictly_greater_than():
    rows = [
        {"Line Item": "Marketing Expense", "Budget": 100000, "Actual": 110000, "Type": "Expense"},
    ]
    result = analyze_rows(rows, config(dollars="10000", pct="0.10"))
    assert not result.rows[0].material


def test_unclassified_rows_are_not_forced_into_totals():
    rows = [{"Line Item": "Mystery", "Budget": 100, "Actual": 120}]
    result = analyze_rows(rows, config(dollars="1", pct="0.01"))
    assert result.rows[0].line_type == LineType.UNCLASSIFIED
    assert result.revenue.actual == 0
    assert result.expenses.actual == 0
    assert result.warnings


def test_subtotals_are_excluded_from_aggregation():
    rows = [
        {"Line Item": "Sales Revenue", "Budget": 100, "Actual": 110, "Type": "Revenue"},
        {"Line Item": "Total Revenue", "Budget": 100, "Actual": 110, "Type": "Revenue"},
    ]
    result = analyze_rows(rows, config(dollars="999", pct="9"))
    assert result.revenue.budget == Decimal("100")
    assert result.revenue.actual == Decimal("110")


def test_missing_budget_fails_instead_of_imputing():
    with pytest.raises(ValueError, match="Budget"):
        analyze_rows(
            [{"Line Item": "Sales Revenue", "Actual": 10, "Type": "Revenue"}],
            config(),
        )


def test_driver_decomposition_only_marked_supported_when_reconciled():
    rows = [
        {
            "Line Item": "Subscription Revenue",
            "Budget": 1000,
            "Actual": 1320,
            "Type": "Revenue",
            "Budget Volume": 100,
            "Actual Volume": 120,
            "Budget Price": 10,
            "Actual Price": 11,
        }
    ]
    result = analyze_rows(rows, config(dollars="1", pct="0.01"))
    evidence = result.rows[0].driver_evidence
    assert evidence is not None
    assert evidence.reconciles
    assert sum(v for _, v in evidence.components) == Decimal("320")


def test_duplicate_names_create_data_quality_warning():
    rows = [
        {"Line Item": "Sales Revenue", "Budget": 100, "Actual": 110, "Type": "Revenue"},
        {"Line Item": "Sales Revenue", "Budget": 50, "Actual": 55, "Type": "Revenue"},
    ]
    result = analyze_rows(rows, config(dollars="9999", pct="9"))
    assert any("Duplicate line-item names" in warning for warning in result.warnings)
