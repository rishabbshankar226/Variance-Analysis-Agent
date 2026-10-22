"""A statement the shaper cannot check must not skip sign and subtotal handling silently."""

from __future__ import annotations

import pytest

from variance_agent import intake
from variance_agent.pdf_tables import StatementTable
from variance_agent.statement_shape import shape_income_statement

HEADER: list[object] = ["Line Item", "FY2025", "FY2024"]


def _statement(rows: list[list[object]]) -> list[list[object]]:
    return [["(In thousands)"], HEADER, *rows]


CLEAN = _statement([
    ["Revenue", "1,000", "900"],
    ["Cost of revenue", "(400)", "(380)"],
    ["Gross profit", "600", "520"],
    ["Net income", "600", "520"],
])
WITH_FOOTNOTE = _statement([
    ["Revenue", "1,000", "900"],
    ["Cost of revenue", "(400)(1)", "(380)"],  # "(1)" is a footnote marker the shaper cannot read
    ["Gross profit", "600", "520"],
    ["Net income", "600", "520"],
])


def test_shaping_reports_whether_it_ran() -> None:
    assert shape_income_statement(CLEAN).shaped is True
    assert shape_income_statement(WITH_FOOTNOTE).shaped is False
    assert shape_income_statement([["no header here"]]).shaped is False


def test_an_unreadable_figure_leaves_the_callers_decimal_flags_alone() -> None:
    from decimal import InvalidOperation, getcontext

    getcontext().clear_flags()
    shape_income_statement(WITH_FOOTNOTE)
    intake.read_input_assisted(b"Line Item,Budget,Actual\nRent,1,oops\n", ".csv", filename="t.csv")
    assert not getcontext().flags[InvalidOperation]


def _read_pdf(monkeypatch: pytest.MonkeyPatch, rows: list[list[object]]) -> intake.IntakeResult:
    table = StatementTable(
        name="Statements of Operations (p. 4)", page_numbers=(4,), raw_rows=rows, kind="income",
    )
    monkeypatch.setattr(intake, "extract_statement_tables", lambda data, filename: [table])
    return intake.read_input_assisted(b"%PDF-1.4", ".pdf", filename="filing.pdf")


def test_clean_statement_is_shaped_and_subtotals_are_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _read_pdf(monkeypatch, CLEAN)
    assert not result.has_fatal_errors
    assert [row["line_item"] for row in result.rows] == ["Revenue", "Cost of revenue"]


def test_unreadable_figure_stops_the_read_instead_of_skipping_the_arithmetic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _read_pdf(monkeypatch, WITH_FOOTNOTE)
    assert result.has_fatal_errors
    message = result.fatal_error_message or ""
    assert "Cost of revenue" in message
    assert "PDF" in message  # the advice must fit a PDF, not tell the user to edit a spreadsheet cell


def test_unshaped_statement_without_unreadable_cells_still_gets_the_ordinary_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No 'Line Item' header row means the shaper stands aside; subtotals are still found by sums."""
    rows: list[list[object]] = [
        ["Line Item", "Budget", "Actual"],
        ["Product A", "300", "310"],
        ["Product B", "200", "190"],
        ["Total revenue", "500", "500"],
    ]
    table = StatementTable(name="Statement (p. 1)", page_numbers=(1,), raw_rows=rows, kind="income")
    monkeypatch.setattr(intake, "extract_statement_tables", lambda data, filename: [table])
    result = intake.read_input_assisted(b"%PDF-1.4", ".pdf", filename="filing.pdf")
    assert not result.has_fatal_errors
    assert "Total revenue" in result.detected_totals
