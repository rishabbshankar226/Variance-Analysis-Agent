"""E7: a formula with no saved result is its own state, never a blank (PLAN.md, R4).

Every workbook here is built in the test and every value is fictional.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from variance_agent import cli
from variance_agent.chat.handlers import handle_upload
from variance_agent.chat.session import Session
from variance_agent.comparisons import read_comparison_input
from variance_agent.intake import read_input_assisted
from variance_agent.parsing import load_input

SHEET = "xl/worksheets/sheet1.xml"
NEVER = ("These cells hold formulas that Excel never calculated, so the file has no saved result "
         "for them:")
STALE = ("The file asks Excel to recalculate its formulas when it is opened, so these cells may have "
         "no saved result or an out-of-date one:")
FIX = "Open the file in Excel, let it calculate, save it, and upload it again."


def _message(filename: str, lead: str, cells: list[str]) -> str:
    return "\n".join([
        f"I could not read every amount in '{filename}', so I stopped instead of guessing. {lead}",
        *(f"- {cell}" for cell in cells), FIX,
    ])


def _book(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


def _rewrite(data: bytes, edits: list[tuple[str, bytes, bytes]]) -> bytes:
    with ZipFile(io.BytesIO(data)) as archive:
        parts = {item.filename: archive.read(item) for item in archive.infolist()}
    for member, old, new in edits:
        assert old in parts[member], parts[member][:300]
        parts[member] = parts[member].replace(old, new)
    capture = io.BytesIO()
    with ZipFile(capture, "w", ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return capture.getvalue()


CALM = ("xl/workbook.xml", b'fullCalcOnLoad="1"', b'fullCalcOnLoad="0"')

# Probe E7b: Other income's budget is =B2-B3 (true value 60), never calculated; Actual 70.
E7B = [["Line Item", "Budget", "Actual", "Type"], ["Revenue", 100, 110, "Revenue"],
       ["COGS", 40, 45, "Expense"], ["Other income", "=B2-B3", 70, "Revenue"]]
# Probe E7: a Total row of formulas, never calculated.
E7 = [["Line Item", "Budget", "Actual", "Type"], ["Revenue", 100, 110, "Revenue"],
      ["COGS", 40, 45, "Expense"], ["Total", "=B2+B3", "=C2+C3", ""]]


def _assisted(data: bytes, filename: str = "plan.xlsx", *, blank_budgets_as_zero: bool = True) -> str:
    result = read_input_assisted(data, ".xlsx", filename=filename,
                                 treat_blank_budgets_as_zero=blank_budgets_as_zero)
    assert result.has_fatal_errors, result.rows
    assert result.rows == []
    return result.fatal_error_message or ""


def test_an_uncalculated_budget_formula_stops_instead_of_reading_zero() -> None:
    data = _rewrite(_book(E7B), [CALM])
    assert _assisted(data) == _message("plan.xlsx", NEVER, ["Row 4, Other income, Budget column (cell B4)"])


def test_an_uncalculated_actual_formula_is_not_called_blank() -> None:
    data = _rewrite(_book(E7), [CALM])
    assert _assisted(data) == _message("plan.xlsx", NEVER, [
        "Row 4, Total, Budget column (cell B4)", "Row 4, Total, Actual column (cell C4)"])


def test_the_comparison_column_is_named_by_its_basis() -> None:
    rows = [["Line Item", "Forecast", "Actual", "Type"], ["Revenue", "=100", 110, "Revenue"]]
    assert _assisted(_rewrite(_book(rows), [CALM])) == _message(
        "plan.xlsx", NEVER, ["Row 2, Revenue, Forecast column (cell B2)"])


def test_a_line_item_and_a_driver_column_formula_stop_too() -> None:
    rows = [["Line Item", "Budget", "Actual", "Type", "Volume"],
            ['="Rev"&"enue"', 100, 110, "Revenue", 10], ["COGS", 40, 45, "Expense", "=2*5"]]
    assert _assisted(_rewrite(_book(rows), [CALM])) == _message("plan.xlsx", NEVER, [
        "Row 2, Line Item column (cell A2)", "Row 3, COGS, Volume column (cell E3)"])


def test_a_formula_in_an_ignored_variance_column_is_not_a_reason_to_stop() -> None:
    rows = [["Line Item", "Budget", "Actual", "Type", "Var $"], ["Revenue", 100, 110, "Revenue", "=C2-B2"]]
    result = read_input_assisted(_rewrite(_book(rows), [CALM]), ".xlsx", filename="plan.xlsx")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.rows[0]["actual"] == Decimal("110")


def test_a_calculated_formula_reads_its_saved_result() -> None:
    data = _rewrite(_book(E7B), [CALM, (SHEET, b"<f>B2-B3</f><v />", b"<f>B2-B3</f><v>60</v>")])
    result = read_input_assisted(data, ".xlsx", filename="plan.xlsx", treat_blank_budgets_as_zero=True)
    assert not result.has_fatal_errors, result.fatal_error_message
    other = next(row for row in result.rows if row["line_item"] == "Other income")
    assert other["budget"] == Decimal("60")
    assert all("blank budgets" not in note for note in result.visible_transformations)


def test_a_saved_result_in_a_workbook_flagged_to_recalculate_on_open_is_not_trusted() -> None:
    # XlsxWriter, for one, saves 0 as every formula's result and sets this flag.
    data = _rewrite(_book(E7B), [(SHEET, b"<f>B2-B3</f><v />", b"<f>B2-B3</f><v>0</v>")])
    assert _assisted(data) == _message("plan.xlsx", STALE, ["Row 4, Other income, Budget column (cell B4)"])


def test_a_flagged_workbook_whose_formulas_have_no_results_says_never_calculated() -> None:
    # openpyxl sets the flag on every workbook and saves formulas without results.
    assert _assisted(_book(E7B)) == _message("plan.xlsx", NEVER, ["Row 4, Other income, Budget column (cell B4)"])


def test_a_flagged_workbook_mixing_saved_and_missing_results_lists_both_as_untrusted() -> None:
    data = _rewrite(_book(E7), [(SHEET, b"<f>B2+B3</f><v />", b"<f>B2+B3</f><v>0</v>")])
    assert _assisted(data) == _message("plan.xlsx", STALE, [
        "Row 4, Total, Budget column (cell B4)", "Row 4, Total, Actual column (cell C4)"])


@pytest.mark.parametrize(("count", "tail"), [(10, []), (11, ["...and 1 more."])])
def test_at_most_ten_cells_are_listed(count: int, tail: list[str]) -> None:
    rows: list[list[object]] = [["Line Item", "Budget", "Actual", "Type"]]
    rows += [[f"Line {n}", f"={n}", 5, "Expense"] for n in range(count)]
    listed = [f"Row {n + 2}, Line {n}, Budget column (cell B{n + 2})" for n in range(min(count, 10))]
    message = _assisted(_rewrite(_book(rows), [CALM]))
    assert message == _message("plan.xlsx", NEVER, listed).replace(f"\n{FIX}", "".join(f"\n- {t}" for t in tail) + f"\n{FIX}")


def test_a_header_formula_stops_with_the_formula_message_not_the_header_message() -> None:
    rows = [["Line Item", '="Bud"&"get"', "Actual"], ["Revenue", 100, 110]]
    assert _assisted(_rewrite(_book(rows), [CALM])) == _message(
        "plan.xlsx", NEVER, ["Row 1 (cell B1)"])


def test_the_cli_stops_with_exit_2_and_the_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "e7b_budget_formula.xlsx"
    path.write_bytes(_book(E7B))
    with pytest.raises(SystemExit) as stopped:
        cli.main([str(path), "--assisted", "--period", "X", "--dollar-threshold", "1", "--percent-threshold", "1"])
    captured = capsys.readouterr()
    assert stopped.value.code == 2
    assert captured.out == ""
    # The CLI prints its error on one line.
    expected = _message("e7b_budget_formula.xlsx", NEVER, ["Row 4, Other income, Budget column (cell B4)"])
    assert captured.err == f"variance-agent: error: {expected.replace(chr(10), ' ')}\n"
    assert "Treated blank budgets as 0" not in captured.err


def test_the_chat_names_the_cell_and_the_fix() -> None:
    session = Session()
    response = handle_upload(session, _rewrite(_book(E7B), [CALM]), "plan.xlsx")
    assert response.level == "error"
    assert "Row 4, Other income, Budget column (cell B4)" in response.text
    assert FIX in response.text


def test_strict_intake_names_the_formula_instead_of_a_missing_value() -> None:
    rows = [["Line Item", "Budget", "Actual", "Type"], ["Revenue", "=50*2", 110, "Revenue"]]
    with pytest.raises(ValueError) as caught:
        load_input(_rewrite(_book(rows), [CALM]), ".xlsx", source_name="plan.xlsx")
    assert str(caught.value) == _message("plan.xlsx", NEVER, ["Row 2, Revenue, Budget column (cell B2)"])


def test_the_file_api_refuses_on_assisted_and_strict_reads() -> None:
    rows = [["Line Item", "Budget", "Actual", "Type"], ["Revenue", 100, "=100+10", "Revenue"]]
    data = _rewrite(_book(rows), [CALM])
    expected = _message("plan.xlsx", NEVER, ["Row 2, Revenue, Actual column (cell C2)"])
    read: Callable[..., object] = read_comparison_input
    for assisted in (True, False):
        with pytest.raises(ValueError) as caught:
            read(data, ".xlsx", filename="plan.xlsx", assisted=assisted)
        assert str(caught.value) == expected
