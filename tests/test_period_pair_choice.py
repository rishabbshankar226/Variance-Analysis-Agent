"""X48: a file with a Budget and Actual pair per period reads the pair named, else the newest (fictional data)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.intake import read_input_assisted
from variance_agent.mapping import LayoutMapping, save_mapping


def _pairs(first: str, second: str) -> str:
    return (f"Line Item,Type,{first} Budget,{first} Actual,{second} Budget,{second} Actual\n"
            "Fictional Sales,Revenue,200,230,100,110\nFictional Rent,Expense,60,66,50,55\n")


@pytest.mark.parametrize(("first", "second"), [("2026", "2025"), ("Sep 2026", "Aug 2026"), ("FY2026", "FY2025")])
def test_newest_first_columns_read_the_newest_pair(first: str, second: str) -> None:
    result = read_input_assisted(_pairs(first, second).encode(), ".csv", filename="f.csv")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal("200"), Decimal("230"))
    assert f"Analyzed period: {first} (Budget from '{first} Budget', Actual from '{first} Actual')" in (
        result.visible_transformations)


@pytest.mark.parametrize(("first", "second", "budget", "actual"), [
    ("Q1 2026", "Q2 2026", "100", "110"),  # oldest first: the newest is the last, as before
    ("Jan-26", "Feb-26", "100", "110"),  # an order the labels can't give: the last, as before
])
def test_columns_read_as_before_where_the_last_pair_is_the_newest_or_no_order_is_known(
        first: str, second: str, budget: str, actual: str) -> None:
    result = read_input_assisted(_pairs(first, second).encode(), ".csv", filename="f.csv")
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal(budget), Decimal(actual))


def test_a_chosen_period_still_wins() -> None:
    result = read_input_assisted(_pairs("2026", "2025").encode(), ".csv", filename="f.csv", selected_period="2025")
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal("100"), Decimal("110"))


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, *extra: str) -> tuple[int, str, str]:
    source = tmp_path / "f.csv"
    source.write_text(text, encoding="utf-8")
    try:
        code = cli.main([str(source), "--assisted", "--dollar-threshold", "1", "--percent-threshold", "1", *extra])
    except SystemExit as stop:
        code = int(stop.code or 0)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _sales(report: str) -> str:
    return next(line for line in report.splitlines() if line.startswith("| Fictional Sales"))


@pytest.mark.parametrize(("period", "budget", "actual"), [
    ("2026", "$200.00", "$230.00"),  # names the newer pair
    ("2025", "$100.00", "$110.00"),  # names the older pair
    ("Q3 2026", "$200.00", "$230.00"),  # names no pair: the newest
])
def test_the_command_line_reads_the_pair_period_names(tmp_path: Path, capsys: pytest.CaptureFixture[str], period: str,
                                                      budget: str, actual: str) -> None:
    code, out, err = _run(tmp_path, capsys, _pairs("2026", "2025"), "--period", period)
    assert code == 0, err
    assert budget in _sales(out) and actual in _sales(out)


@pytest.mark.parametrize(("period", "budget"), [("Feb-26", "$100.00"), ("jan-26", "$200.00")])
def test_an_order_the_labels_cant_give_reads_the_pair_period_names(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], period: str, budget: str) -> None:
    code, out, err = _run(tmp_path, capsys, _pairs("Jan-26", "Feb-26"), "--period", period)
    assert code == 0, err
    assert budget in _sales(out)


def test_an_order_the_labels_cant_give_refuses_when_no_pair_is_named(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(tmp_path, capsys, _pairs("Jan-26", "Feb-26"), "--period", "Feb 2026")
    assert code == 2 and out == ""
    assert ("'f.csv' has a Budget and Actual pair for Jan-26 and for Feb-26, and their order isn't clear. Rerun with "
            "--period set to the one to read: Jan-26 or Feb-26.") in err


def test_a_mappings_period_wins_over_the_period_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mapping = tmp_path / "f.mapping.json"
    mapping.write_text(save_mapping(LayoutMapping(period_column_selection="2025")), encoding="utf-8")
    code, out, err = _run(tmp_path, capsys, _pairs("2025", "2026"), "--period", "2026", "--mapping", str(mapping))
    assert code == 0, err
    assert "$200.00" in _sales(out) and "$230.00" in _sales(out)
