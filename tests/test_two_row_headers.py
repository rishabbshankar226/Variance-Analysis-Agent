"""X24: a header split over two rows is read together (fictional workbooks)."""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from variance_agent.intake import read_input_assisted


def _book(merged: bool, lower_amounts: tuple[str, str] = ("Budget", "Actual")) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["Account Description", "Type", "Year to Date", None])
    sheet.append([None, None, *lower_amounts])
    sheet.append(["Fictional Sales", "Revenue", 100, 120])
    sheet.append(["Fictional Rent", "Expense", 50, 55])
    if merged:
        sheet.merge_cells("A1:A2")
        sheet.merge_cells("C1:D1")
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize("merged", [True, False], ids=["merged", "unmerged"])
def test_a_two_row_header_reads(merged: bool) -> None:
    result = read_input_assisted(_book(merged), ".xlsx", filename="two_rows.xlsx")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert [(row["line_item"], row["budget"], row["actual"]) for row in result.rows] == [
        ("Fictional Sales", Decimal("100"), Decimal("120")), ("Fictional Rent", Decimal("50"), Decimal("55"))]
    assert ("Read the column names from rows 1 and 2 together: 'Account Description', 'Type' (row 1) above blank "
            "cells of row 2.") in result.visible_transformations


def test_a_lower_row_without_amount_names_still_refuses() -> None:
    result = read_input_assisted(_book(True, ("Notes", "Owner")), ".xlsx", filename="two_rows.xlsx")
    assert result.has_fatal_errors
    assert "Could not find a header row" in (result.fatal_error_message or "")
