"""X20: a zero shown by an Accounting format's "-" section never disagrees with a unit caption (fictional books)."""

from __future__ import annotations

import io
from decimal import Decimal

from openpyxl import Workbook

from variance_agent.intake import read_input_assisted

ACCOUNTING_THOUSANDS = '_(* #,##0,_);_(* (#,##0,);_(* "-"_);_(@_)'


def _book(travel_actual: int, travel_format: str = ACCOUNTING_THOUSANDS) -> bytes:
    """Full amounts stored, shown in thousands under a thousands caption."""
    book = Workbook()
    sheet = book.active
    sheet.append(["Fictional Widgets Inc. (FAKE) ($ in thousands)"])
    sheet.append([])
    sheet.append(["Line Item", "Type", "Budget", "Actual"])
    for label, kind, budget, actual in [("Fictional Sales", "Revenue", 100000, 120000),
                                        ("Fictional Travel", "Expense", 50000, travel_actual)]:
        sheet.append([label, kind, budget, actual])
        for column in (3, 4):
            sheet.cell(row=sheet.max_row, column=column).number_format = ACCOUNTING_THOUSANDS
    sheet.cell(row=sheet.max_row, column=4).number_format = travel_format
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_a_zero_cell_does_not_stop_a_caption_the_formats_agree_with() -> None:
    result = read_input_assisted(_book(0), ".xlsx", filename="zero.xlsx")
    assert not result.has_fatal_errors, result.fatal_error_message
    travel = next(row for row in result.rows if row["line_item"] == "Fictional Travel")
    assert travel["actual"] == Decimal("0")
    assert next(row for row in result.rows if row["line_item"] == "Fictional Sales")["actual"] == Decimal("120000")
    assert any("not scaled again" in note for note in result.visible_transformations)


def test_a_nonzero_cell_in_general_still_disagrees() -> None:
    result = read_input_assisted(_book(40000, "General"), ".xlsx", filename="mixed.xlsx")
    assert result.has_fatal_errors
    assert "number formats don't agree" in (result.fatal_error_message or "")
