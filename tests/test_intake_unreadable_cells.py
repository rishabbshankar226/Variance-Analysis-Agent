"""Assisted intake must not turn amounts it cannot read into zero.

Before the 2026-10 bug hunt, ``Service Revenue,500,"500.00-"`` and a blank Actual were read
as 0, the run carried on, and the report showed a 100% revenue shortfall.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.intake import IntakeResult, parse_assisted_decimal, read_input_assisted

HEADER = "Line Item,Type,Budget,Actual\n"


def _read(body: str, *, suffix: str = ".csv") -> IntakeResult:
    return read_input_assisted(
        (HEADER + body).encode("utf-8"), suffix, filename="t" + suffix,
        treat_blank_budgets_as_zero=True,
    )


@pytest.mark.parametrize("cell", ["TBD", "n/a", "12abc", "1.234,56", "--5", ""])
def test_unreadable_or_blank_actual_stops_the_read(cell: str) -> None:
    res = _read(f'Service Revenue,Revenue,500,"{cell}"\nRent,Expense,100,90\n')
    assert res.has_fatal_errors
    assert res.fatal_error_message is not None
    message = res.fatal_error_message
    assert "Row 2" in message and "Service Revenue" in message and "Actual" in message
    assert "stopped" in message.lower() or "could not" in message.lower()
    assert res.problems, "the structured problems stay available to callers"


def test_unreadable_budget_stops_the_read() -> None:
    res = _read("Service Revenue,Revenue,lots,500\n")
    assert res.has_fatal_errors
    assert res.fatal_error_message is not None
    assert "Row 2" in res.fatal_error_message and "Budget" in res.fatal_error_message


def test_message_lists_cells_and_counts_the_rest() -> None:
    body = "".join(f"Item {i},Expense,10,oops\n" for i in range(25))
    res = _read(body)
    assert res.fatal_error_message is not None
    assert "Item 0" in res.fatal_error_message
    assert "Item 24" not in res.fatal_error_message
    assert "15 more" in res.fatal_error_message  # 25 problems, 10 shown


def test_blank_budget_is_still_a_confirmation_not_an_error() -> None:
    res = _read("Rent,Expense,,90\n")
    assert not res.has_fatal_errors
    assert res.blank_budget_items == ["Row 2: Rent"]


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("500.00-", Decimal("-500.00")),
        ("1,234.50-", Decimal("-1234.50")),
        ("500.00 -", Decimal("-500.00")),
        ("−500", Decimal("-500")),  # U+2212 MINUS SIGN
        ("１２３", Decimal("123")),  # full-width digits
        (" 250 ", Decimal("250")),  # non-breaking spaces
        ("$− 1,000", Decimal("-1000")),
    ],
)
def test_typographic_and_trailing_minus_are_read_as_negative(cell: str, expected: Decimal) -> None:
    value, note = parse_assisted_decimal(cell, field="Actual", line_item="x")
    assert value == expected
    assert note is None or "sign" in note.lower() or "minus" in note.lower()


def test_trailing_minus_is_reported_in_the_intake_notes() -> None:
    res = _read('Credit Memos,Expense,100,"40.00-"\nRent,Expense,100,"90.00-"\n')
    assert not res.has_fatal_errors
    assert [r["actual"] for r in res.rows] == [Decimal("-40.00"), Decimal("-90.00")]
    assert any("minus" in note.lower() and "2" in note for note in res.visible_transformations)
    assert res.has_transformations


@pytest.mark.parametrize("cell", ["5-5", "5--", "-5-", "(5)-", "1-2-3"])
def test_ambiguous_signs_are_not_guessed(cell: str) -> None:
    with pytest.raises(ValueError):
        parse_assisted_decimal(cell, field="Actual", line_item="x")


def test_accounting_dash_count_reaches_the_audit_transformations() -> None:
    from variance_agent.intake import audit_transformations

    res = _read("Rent,Expense,100,-\nFees,Expense,-,5\n")
    assert audit_transformations(res)["zero_reads"] == {"accounting_dashes": 2, "blank_budgets": 0}


def test_cli_assisted_exits_2_and_lists_the_cell(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "in.csv"
    source.write_text(HEADER + "Service Revenue,Revenue,500,TBD\nRent,Expense,100,90\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        cli.main([
            str(source), "--assisted", "--period", "Q3", "--dollar-threshold", "10",
            "--percent-threshold", "5", "-o", str(tmp_path / "r.md"),
        ])
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "Service Revenue" in err and "Actual" in err
    assert not (tmp_path / "r.md").exists()


# --- Text encodings are decoded strictly and reported, never silently replaced ---

CSV_TEXT = "Line Item,Type,Budget,Actual\nCafé Revenue,Revenue,100,€120\nRent,Expense,50,60\n"


def _read_bytes(data: bytes, suffix: str = ".csv") -> IntakeResult:
    return read_input_assisted(data, suffix, filename="t" + suffix)


def test_utf8_bom_file_reads_without_a_note() -> None:
    res = _read_bytes(("﻿" + CSV_TEXT.replace("€", "")).encode("utf-8"))
    assert not res.has_fatal_errors
    assert res.rows[0]["line_item"] == "Café Revenue"
    assert not any("windows" in note.lower() for note in res.visible_transformations)


@pytest.mark.parametrize("codec", ["utf-16", "utf-16-le", "utf-16-be"])
def test_utf16_files_are_decoded(codec: str) -> None:
    text = CSV_TEXT.replace("€", "")
    # utf-16 already writes a BOM; the explicit-endian codecs need one to be recognised.
    data = text.encode(codec) if codec == "utf-16" else ("﻿" + text).encode(codec)
    res = _read_bytes(data)
    assert not res.has_fatal_errors
    assert res.rows[0]["line_item"] == "Café Revenue"


def test_windows_1252_file_is_decoded_and_reported() -> None:
    res = _read_bytes(CSV_TEXT.replace("€120", "$120").encode("cp1252"))
    assert not res.has_fatal_errors
    assert res.rows[0]["line_item"] == "Café Revenue"
    assert any("Windows-1252" in note for note in res.visible_transformations)
    assert res.has_transformations


def test_windows_1252_euro_sign_is_a_currency_symbol_not_a_replacement_character() -> None:
    res = _read_bytes(CSV_TEXT.encode("cp1252"))
    assert not res.has_fatal_errors
    assert res.rows[0]["actual"] == Decimal("120")


def test_undecodable_bytes_stop_with_an_actionable_message() -> None:
    res = _read_bytes(b"Line Item,Budget,Actual\nRent,\x81\x8d,5\n")  # bytes cp1252 leaves undefined
    assert res.has_fatal_errors
    assert res.fatal_error_message is not None
    assert "UTF-8" in res.fatal_error_message and "t.csv" in res.fatal_error_message
    assert "�" not in res.fatal_error_message
