"""E6: real Excel dates as column headers read as periods; data cells keep their values.

Every workbook here is built in the test and every value is fictional.
"""

from __future__ import annotations

import datetime as dt
import io
from decimal import Decimal

from openpyxl import Workbook

from variance_agent.intake import read_input_assisted
from variance_agent.models import ComparisonBasis


def _book(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


def test_date_headers_read_as_periods_newest_against_the_one_before() -> None:
    data = _book([["Line Item", dt.datetime(2025, 9, 30), dt.datetime(2026, 9, 30), "Type"],
                  ["Revenue", 100, 110, "Revenue"], ["COGS", 40, 45, "Expense"]])
    result = read_input_assisted(data, ".xlsx", filename="years.xlsx")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.comparison_basis is ComparisonBasis.PRIOR_PERIOD
    assert [(row["budget"], row["actual"]) for row in result.rows] == [(Decimal(100), Decimal(110)), (Decimal(40), Decimal(45))]
    assert ("Read the dates in the header row as periods: 2025-09-30 as Sep 2025 (column B), "
            "2026-09-30 as Sep 2026 (column C).") in result.visible_transformations
    assert result.comparison_label == "Sep 2025"


def test_two_dates_in_one_month_are_not_ordered_by_guess() -> None:
    data = _book([["Line Item", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 30)], ["Revenue", 100, 110]])
    result = read_input_assisted(data, ".xlsx", filename="years.xlsx")
    assert result.has_fatal_errors
    assert result.rows == []


def test_a_date_in_a_data_cell_is_left_as_it_was() -> None:
    rows: list[list[object]] = [["Line Item", "Budget", "Actual", "Type", "Posted"],
                                ["Revenue", 100, 110, "Revenue", dt.datetime(2026, 9, 30)]]
    result = read_input_assisted(_book(rows), ".xlsx", filename="plan.xlsx")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.rows[0]["Posted"] == dt.datetime(2026, 9, 30)
    assert not any("dates in the header" in note for note in result.visible_transformations)
