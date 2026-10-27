"""E4 banded period headers and E5 side-by-side tables on one sheet.

Both are tried only where today's read stops on a repeated column, so a sheet that reads
today reads the same. Every workbook here is built in the test and every value is fictional.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from variance_agent.intake import IntakeResult, read_input_assisted


def _book(rows: list[list[object]], merges: tuple[str, ...] = ()) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    for cells in merges:
        sheet.merge_cells(cells)
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


# Probe E4: Q3 2026 merged over Budget/Actual, then Q2 2026 over the same pair.
E4 = [["", "Q3 2026", "", "Q2 2026", ""], ["Line Item", "Budget", "Actual", "Budget", "Actual"],
      ["Revenue", 100, 110, 95, 97], ["Marketing", 20, 26, 20, 19]]
BAND_NOTE = ("Read the period headings above the header row with the columns below them: Q3 2026 Budget, "
             "Q3 2026 Actual, Q2 2026 Budget, Q2 2026 Actual.")


def _read(data: bytes, *, period: str | None = None, sheet: str | None = None) -> IntakeResult:
    return read_input_assisted(data, ".xlsx", filename="plan.xlsx", selected_period=period, sheet=sheet)


def _pairs(result: IntakeResult) -> list[tuple[str, Decimal, Decimal]]:
    assert not result.has_fatal_errors, result.fatal_error_message
    return [(str(row["line_item"]), Decimal(str(row["budget"])), Decimal(str(row["actual"]))) for row in result.rows]


@pytest.mark.parametrize("merges", [("B1:C1", "D1:E1"), ()])
def test_banded_headers_read_as_period_pairs_newest_first(merges: tuple[str, ...]) -> None:
    result = _read(_book(E4, merges))
    assert _pairs(result) == [("Revenue", Decimal(100), Decimal(110)), ("Marketing", Decimal(20), Decimal(26))]
    assert result.visible_transformations[0] == BAND_NOTE
    assert ("Analyzed period: Q3 2026 (Budget from 'Q3 2026 Budget', Actual from 'Q3 2026 Actual')"
            in result.visible_transformations)


def test_a_named_period_picks_its_band() -> None:
    result = _read(_book(E4, ("B1:C1", "D1:E1")), period="Q2 2026")
    assert _pairs(result) == [("Revenue", Decimal(95), Decimal(97)), ("Marketing", Decimal(20), Decimal(19))]


def test_repeated_columns_without_period_bands_still_stop() -> None:
    rows = [["Plan review (fictional)", "", "", "", ""], *E4[1:]]
    result = _read(_book(rows))
    assert result.has_fatal_errors
    assert "more than one Actual column" in (result.fatal_error_message or "")


# Probe E5: a P&L block and a KPI block separated by a blank column.
E5 = [["Line Item", "Budget", "Actual", None, "KPI", "Target", "Actual"],
      ["Revenue", 100, 110, None, "Headcount", 50, 52], ["COGS", 40, 45, None, "Churn %", 2, 3]]


def test_side_by_side_tables_are_read_one_at_a_time() -> None:
    result = _read(_book(E5))
    assert _pairs(result) == [("Revenue", Decimal(100), Decimal(110)), ("COGS", Decimal(40), Decimal(45))]
    assert result.visible_transformations[0] == (
        "Read the table in columns A-C; this sheet also has a table in columns E-G (KPI, Target, Actual), "
        "chosen as sheet 'Sheet (columns E-G)'.")


def test_the_other_table_is_chosen_by_its_columns() -> None:
    rows = [["Line Item", "Budget", "Actual", None, "Line Item", "Budget", "Actual"],
            ["Revenue", 100, 110, None, "Headcount", 50, 52]]
    result = _read(_book(rows), sheet="Sheet (columns E-G)")
    assert _pairs(result) == [("Headcount", Decimal(50), Decimal(52))]
    assert result.visible_transformations[0] == (
        "Read the table in columns E-G; this sheet also has a table in columns A-C (Line Item, Budget, Actual), "
        "chosen as sheet 'Sheet (columns A-C)'.")


def test_a_blank_column_inside_one_table_with_data_below_is_not_a_split() -> None:
    rows = [["Line Item", "Budget", "Actual", None, "Actual"], ["Revenue", 100, 110, 1, 120]]
    result = _read(_book(rows))
    assert result.has_fatal_errors
    assert "more than one Actual column" in (result.fatal_error_message or "")
