"""Category summary labels in their common spellings are verified and excluded like `Total Revenue`.

Strict mode used to reject `Total Revenues` and `Total Operating Expenses` as "ambiguous summary
label; specify Row Kind", although `Total Revenue` and `Total Expenses` were recognised.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from variance_agent.analysis import analyze_rows
from variance_agent.models import AnalysisConfig, LineType

CFG = AnalysisConfig("Q3", Decimal("10"), Decimal("0.05"))


def _rows(revenue_total: str, expense_total: str, *, expense_sum: int = 150) -> list[dict[str, object]]:
    return [
        {"Line Item": "Product Sales", "Budget": 600, "Actual": 650},
        {"Line Item": "Service Revenue", "Budget": 400, "Actual": 420},
        {"Line Item": revenue_total, "Budget": 1000, "Actual": 1070},
        {"Line Item": "Payroll", "Budget": 100, "Actual": 110},
        {"Line Item": "Rent", "Budget": 50, "Actual": 50},
        {"Line Item": expense_total, "Budget": 150, "Actual": expense_sum + 10},
    ]


@pytest.mark.parametrize(
    "label",
    [
        "Total Revenue", "Total Revenues", "Total Sales", "Total Operating Revenue", "Total Operating Revenues",
        "Total Net Revenue", "Total Net Sales", "Revenues Total", "Revenue Subtotal", "Total Income",
    ],
)
def test_revenue_summary_spellings_are_excluded_after_reconciling(label: str) -> None:
    result = analyze_rows(_rows(label, "Total Expenses"), CFG)
    summary = next(row for row in result.rows if row.line_item == label)
    assert summary.excluded_from_aggregation
    assert summary.line_type is LineType.REVENUE
    assert summary.summary_verification is not None
    assert summary.summary_verification.outcome == "reconciled_and_excluded"
    assert result.revenue.budget == Decimal(1000) and result.revenue.actual == Decimal(1070)


@pytest.mark.parametrize(
    "label",
    [
        "Total Expenses", "Total Operating Expenses", "Total Costs", "Total Operating Costs",
        "Total Costs and Expenses", "Total Cost and Expenses", "Total Opex", "Total COGS", "Expenses Total",
        "Total Other Expenses", "Total Operating Expense",
    ],
)
def test_expense_summary_spellings_are_excluded_after_reconciling(label: str) -> None:
    result = analyze_rows(_rows("Total Revenue", label), CFG)
    summary = next(row for row in result.rows if row.line_item == label)
    assert summary.excluded_from_aggregation
    assert summary.line_type is LineType.EXPENSE
    assert result.expenses.budget == Decimal(150) and result.expenses.actual == Decimal(160)


def test_a_summary_that_does_not_add_up_is_still_rejected() -> None:
    with pytest.raises(ValueError, match="does not reconcile"):
        analyze_rows(_rows("Total Revenue", "Total Operating Expenses", expense_sum=200), CFG)


@pytest.mark.parametrize(
    "label",
    ["Total Quality Management", "Total Operating Income", "Total Compensation Review", "Subtotal Misc"],
)
def test_other_total_labels_still_need_a_row_kind(label: str) -> None:
    rows = _rows("Total Revenue", "Total Expenses")
    rows.append({"Line Item": label, "Budget": 5, "Actual": 6})
    with pytest.raises(ValueError, match="ambiguous summary label"):
        analyze_rows(rows, CFG)


def test_an_explicit_row_kind_still_decides() -> None:
    rows = _rows("Total Revenues", "Total Expenses")
    rows[2]["Row Kind"] = "Detail"  # the user says it is an ordinary account, not a summary
    result = analyze_rows(rows, CFG)
    assert not next(r for r in result.rows if r.line_item == "Total Revenues").excluded_from_aggregation
