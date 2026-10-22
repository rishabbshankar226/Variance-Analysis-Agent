"""Label inference must not file costs under Revenue or add profit subtotals to a category.

Before the 2026-10 bug hunt ``Sales Commissions`` and ``Income Taxes`` were inferred as Revenue
(the word "sales"/"income" won), so an overrun was reported Favorable and added to Total Revenue.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from variance_agent.analysis import analyze_rows
from variance_agent.models import AnalysisConfig, LineType, Status

CFG = AnalysisConfig("Q3", Decimal("10"), Decimal("0.05"))

EXPENSES = [
    "Sales Commissions", "Commissions", "Income Taxes", "Income Tax Expense",
    "Provision for Income Taxes", "Sales Salaries", "Sales Compensation", "Sales Tax",
    "Salaries & Wages", "Salaries and Wages", "Sales Returns and Allowances", "Bonus Provision",
    "Rent Expense", "Payroll", "Marketing",
]
REVENUES = [
    "Sales", "Service Revenue", "Product Sales", "Interest Income", "Subscription Revenue",
    "Revenue, net of returns", "Net Sales",
]
UNCLASSIFIED = [
    "Income Before Taxes", "Income before income taxes", "Pre-Tax Income", "Pretax Income",
    "Income from Operations", "Comprehensive Income", "Net Income", "Net Income After Taxes",
    "Operating Income", "Operating Loss", "Gross Profit", "Gross Margin", "EBITDA", "EBIT",
    "Profit after tax", "Other Income (Expense)", "Sales and Marketing",
]


def _classify(label: str) -> tuple[LineType, str]:
    result = analyze_rows([{"Line Item": label, "Budget": 100, "Actual": 150}], CFG)
    row = result.rows[0]
    return row.line_type, row.classification_source


@pytest.mark.parametrize("label", EXPENSES)
def test_cost_labels_are_expenses(label: str) -> None:
    assert _classify(label)[0] is LineType.EXPENSE, label


@pytest.mark.parametrize("label", REVENUES)
def test_revenue_labels_stay_revenue(label: str) -> None:
    assert _classify(label)[0] is LineType.REVENUE, label


@pytest.mark.parametrize("label", UNCLASSIFIED)
def test_profit_subtotals_and_mixed_labels_are_not_guessed(label: str) -> None:
    line_type, _ = _classify(label)
    assert line_type is LineType.UNCLASSIFIED, label


def test_profit_subtotals_say_why() -> None:
    assert _classify("Income Before Taxes")[1] == "non_additive_profit"
    assert _classify("Comprehensive Income")[1] == "non_additive_profit"


def test_commission_overrun_is_unfavorable_and_stays_out_of_revenue() -> None:
    result = analyze_rows(
        [
            {"Line Item": "Service Revenue", "Budget": 1000, "Actual": 1000},
            {"Line Item": "Sales Commissions", "Budget": 100, "Actual": 150},
            {"Line Item": "Income Taxes", "Budget": 50, "Actual": 90},
        ],
        CFG,
    )
    by_name = {row.line_item: row for row in result.rows}
    assert by_name["Sales Commissions"].status is Status.UNFAVORABLE
    assert by_name["Income Taxes"].status is Status.UNFAVORABLE
    assert result.revenue.budget == Decimal("1000") and result.revenue.actual == Decimal("1000")
    assert result.expenses.budget == Decimal("150") and result.expenses.actual == Decimal("240")


def test_explicit_type_and_type_map_still_win() -> None:
    result = analyze_rows(
        [{"Line Item": "Sales Commissions", "Type": "Revenue", "Budget": 100, "Actual": 150}], CFG,
    )
    assert result.rows[0].line_type is LineType.REVENUE
    mapped = AnalysisConfig("Q3", Decimal("10"), Decimal("0.05"), type_map={"Income Taxes": LineType.REVENUE})
    result = analyze_rows([{"Line Item": "Income Taxes", "Budget": 100, "Actual": 150}], mapped)
    assert result.rows[0].line_type is LineType.REVENUE


def test_signed_ledger_detection_uses_the_same_classifier() -> None:
    """Negative-credit detection must not call commissions revenue and flip their sign."""
    from variance_agent.intake import detect_signed_ledger

    rows: list[dict[str, object]] = [
        {"line_item": "Sales Commissions", "budget": Decimal("-100"), "actual": Decimal("-120")},
        {"line_item": "Income Taxes", "budget": Decimal("-50"), "actual": Decimal("-60")},
        {"line_item": "Rent", "budget": Decimal("100"), "actual": Decimal("100")},
    ]
    assert not detect_signed_ledger(rows).is_signed_ledger
