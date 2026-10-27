"""E2: rows hidden in Excel that carry amounts are a confirmed choice, never counted silently (R3).

Every workbook here is built in the test and every value is fictional.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from variance_agent import AnalysisConfig, analyze_file, cli
from variance_agent.api import AudienceOptions
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session
from variance_agent.intake import IntakeResult, read_input_assisted
from variance_agent.parsing import load_input

ASK = ("These rows are hidden in Excel but have amounts, so I need to know whether to count them:")
HINT = "Rerun with --hidden-rows include to count them or --hidden-rows exclude to leave them out."


def _book(build: Callable[[Worksheet], None] | None = None, *, title: bool = False) -> bytes:
    """Probe E2: Draft line (5, 5, Expense) on row 3 hidden; the Old Budget column E hidden."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    if title:
        sheet.append(["Plan review (fictional)"])
    sheet.append(["Line Item", "Budget", "Actual", "Type", "Old Budget"])
    sheet.append(["Revenue", 100, 110, "Revenue", 90])
    sheet.append(["Draft line", 5, 5, "Expense", 5])
    sheet.append(["COGS", 40, 45, "Expense", 40])
    if build is None:
        sheet.row_dimensions[3 + title].hidden = True
        sheet.column_dimensions["E"].hidden = True
    else:
        build(sheet)
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


def _read(data: bytes, hidden_rows: str | None = None) -> IntakeResult:
    return read_input_assisted(data, ".xlsx", filename="plan.xlsx", treat_blank_budgets_as_zero=True,
                               hidden_rows=hidden_rows)


def _expenses(result: IntakeResult) -> tuple[Decimal, Decimal]:
    assert not result.has_fatal_errors, result.fatal_error_message
    rows = [row for row in result.rows if row.get("type") == "Expense"]
    return (sum((Decimal(str(row["budget"])) for row in rows), Decimal(0)),
            sum((Decimal(str(row["actual"])) for row in rows), Decimal(0)))


def test_a_hidden_row_with_amounts_stops_and_asks() -> None:
    result = _read(_book())
    assert result.has_fatal_errors
    assert result.fatal_error_message == f"{ASK}\n- Row 3, Draft line (hidden)"
    assert result.needs_hidden_rows_choice
    assert result.rows == []


def test_counting_the_hidden_rows_keeps_todays_totals_and_says_so() -> None:
    result = _read(_book(), "include")
    assert _expenses(result) == (Decimal(45), Decimal(50))
    assert "Counted 1 row hidden in Excel: row 3 (Draft line)." in result.visible_transformations
    assert result.hidden_rows_choice == "include"


def test_leaving_the_hidden_rows_out_drops_them_before_totals() -> None:
    result = _read(_book(), "exclude")
    assert _expenses(result) == (Decimal(40), Decimal(45))
    assert [row["line_item"] for row in result.rows] == ["Revenue", "COGS"]
    assert "Left out 1 row hidden in Excel: row 3 (Draft line)." in result.visible_transformations


def test_rows_in_a_collapsed_outline_group_are_told_apart_from_rows_hidden_one_by_one() -> None:
    def build(sheet: Worksheet) -> None:
        sheet.row_dimensions[3].hidden = True
        sheet.row_dimensions[4].hidden = True
        sheet.row_dimensions[4].outlineLevel = 1

    result = _read(_book(build))
    assert result.fatal_error_message == f"{ASK}\n- Row 3, Draft line (hidden)\n- Row 4, COGS (in a collapsed outline group)"


@pytest.mark.parametrize(("hidden", "asks"), [(0, False), (1, True)])
def test_the_question_starts_at_one_hidden_data_row(hidden: int, asks: bool) -> None:
    def build(sheet: Worksheet) -> None:
        for row in range(3, 3 + hidden):
            sheet.row_dimensions[row].hidden = True

    result = _read(_book(build))
    assert result.has_fatal_errors is asks
    if not asks:
        assert not any("hidden" in note for note in result.visible_transformations)


def test_a_hidden_title_row_above_the_header_is_not_a_question() -> None:
    result = _read(_book(lambda sheet: setattr(sheet.row_dimensions[1], "hidden", True), title=True))
    assert not result.has_fatal_errors, result.fatal_error_message


def test_a_hidden_column_that_is_read_is_named() -> None:
    result = _read(_book(lambda sheet: setattr(sheet.column_dimensions["C"], "hidden", True)))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert "Read Actual from column C ('Actual'), which is hidden in Excel." in result.visible_transformations


def test_the_choice_is_ignored_on_a_workbook_without_hidden_rows() -> None:
    plain = _read(_book(lambda sheet: None))
    chosen = _read(_book(lambda sheet: None), "exclude")
    assert chosen.rows == plain.rows
    assert chosen.visible_transformations == plain.visible_transformations
    assert chosen.hidden_rows_choice is None


def test_strict_intake_still_counts_every_row() -> None:
    rows = load_input(_book(), ".xlsx", source_name="plan.xlsx").rows
    assert [row["line_item"] for row in rows] == ["Revenue", "Draft line", "COGS"]


def _cli(path: Path, *extra: str) -> list[str]:
    return [str(path), "--period", "X", "--dollar-threshold", "1", "--percent-threshold", "1", *extra]


def test_the_cli_asks_for_the_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "e2_hidden_rows.xlsx"
    path.write_bytes(_book())
    with pytest.raises(SystemExit) as stopped:
        cli.main(_cli(path, "--assisted"))
    assert stopped.value.code == 2
    assert capsys.readouterr().err == f"variance-agent: error: {ASK} - Row 3, Draft line (hidden) {HINT}\n"


@pytest.mark.parametrize(("choice", "total"), [
    ("include", "- Total Expenses: $50.00 vs. $45.00 ($5.00, 11.1%, U)"),
    ("exclude", "- Total Expenses: $45.00 vs. $40.00 ($5.00, 12.5%, U)"),
])
def test_the_cli_applies_the_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str], choice: str, total: str) -> None:
    path = tmp_path / "e2_hidden_rows.xlsx"
    path.write_bytes(_book())
    assert cli.main(_cli(path, "--assisted", "--hidden-rows", choice)) == 0
    assert total in capsys.readouterr().out


def test_the_flag_is_refused_where_nothing_can_be_hidden(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "plan.csv"
    path.write_text("Line Item,Budget,Actual\nRevenue,100,110\n", encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        cli.main(_cli(path, "--assisted", "--hidden-rows", "include"))
    assert stopped.value.code == 2
    assert "--hidden-rows requires XLSX or XLSM input." in capsys.readouterr().err


def test_a_mapping_replays_the_choice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "plan.xlsx"
    path.write_bytes(_book())
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"mapping_version": "1.5", "hidden_rows": "exclude"}), encoding="utf-8")
    assert cli.main(_cli(path, "--mapping", str(mapping))) == 0
    assert "- Total Expenses: $45.00 vs. $40.00 ($5.00, 12.5%, U)" in capsys.readouterr().out


def test_a_mapping_refuses_an_unknown_choice(tmp_path: Path) -> None:
    from variance_agent.mapping import load_mapping
    with pytest.raises(ValueError, match="hidden_rows must be include or exclude"):
        load_mapping(json.dumps({"hidden_rows": "sometimes"}))


def test_the_chat_offers_both_answers_and_applies_one() -> None:
    session = Session()
    asked = handle_upload(session, _book(), "plan.xlsx")
    assert asked.level == "error"
    assert "Row 3, Draft line (hidden)" in asked.text
    assert asked.chips[:2] == ["Count the hidden rows", "Leave the hidden rows out"]
    answered = handle_message(session, "Leave the hidden rows out")
    assert answered.phase == Phase.AWAITING_INTAKE_CONFIRMATION, answered.text
    assert "Left out 1 row hidden in Excel: row 3 (Draft line)." in answered.text
    assert session.hidden_rows == "exclude"


def test_a_saved_chat_mapping_keeps_the_choice() -> None:
    from variance_agent.chat.handlers import _layout_mapping_for
    session = Session()
    handle_upload(session, _book(), "plan.xlsx")
    handle_message(session, "Count the hidden rows")
    assert _layout_mapping_for(session).to_dict()["hidden_rows"] == "include"


def test_the_file_api_needs_an_explicit_choice(tmp_path: Path) -> None:
    path = tmp_path / "plan.xlsx"
    path.write_bytes(_book())
    config = AnalysisConfig("X", Decimal("1"), Decimal("1"))
    with pytest.raises(ValueError) as caught:
        analyze_file(path, config, options=AudienceOptions(assisted=True))
    assert str(caught.value) == (f"{ASK}\n- Row 3, Draft line (hidden)\nChoose whether to count them "
                                 "(hidden_rows='include' or 'exclude'; --hidden-rows on the command line).")
    for choice, lines in (("include", 3), ("exclude", 2)):
        table = analyze_file(path, config, options=AudienceOptions(assisted=True, hidden_rows=choice))
        assert len(table.comparisons[0].result.rows) == lines


def test_the_flag_needs_assisted_intake_because_strict_reads_every_row(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "plan.xlsx"
    path.write_bytes(_book())
    with pytest.raises(SystemExit) as stopped:
        cli.main(_cli(path, "--hidden-rows", "exclude"))
    assert stopped.value.code == 2
    assert ("--hidden-rows requires --assisted or --mapping; strict intake reads every row as given."
            in capsys.readouterr().err)


def test_an_earnings_review_asks_the_same_question_and_stays_an_earnings_review() -> None:
    session = Session()
    handle_message(session, "review earnings")
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in (["Line Item", "Consensus", "Actual", "Measure", "Better"], ["Revenue", 100, 110, "Currency", "Higher"],
                ["Draft EPS", "0.5", "0.6", "Per Share", "Higher"], ["Diluted EPS", "1.10", "1.25", "Per Share", "Higher"]):
        sheet.append(row)
    sheet.row_dimensions[3].hidden = True
    capture = io.BytesIO()
    workbook.save(capture)
    asked = handle_upload(session, capture.getvalue(), "street.xlsx")
    assert asked.text == f"{ASK}\n- Row 3, Draft EPS (hidden)"
    assert asked.chips[:2] == ["Count the hidden rows", "Leave the hidden rows out"]
    answered = handle_message(session, "Leave the hidden rows out")
    assert session.earnings_mode, answered.text
    assert "Left out 1 row hidden in Excel: row 3 (Draft EPS)." in answered.text
    assert [row["line_item"] for row in session.parsed_rows] == ["Revenue", "Diluted EPS"]
