"""X41: a unit caption scales a Currency row's Buffer and Tolerance with its amounts (fictional files)."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.comparisons import read_comparison_input
from variance_agent.intake import read_input_assisted
from variance_agent.models import ComparisonBasis

CAPTION = "Fictional Desk ($ in thousands)\n\n"


def _limit(actual: str, buffer: str = "10") -> str:
    return CAPTION + f"Line Item,Actual,Limit,Limit Kind,Buffer\nFictional desk exposure,{actual},100,Max,{buffer}\n"


def _benchmark(actual: str) -> str:
    return CAPTION + f"Line Item,Actual,Benchmark,Better,Tolerance\nFictional sleeve value,{actual},100,Higher,10\n"


def _target(actual: str) -> str:
    return CAPTION + f"Line Item,Actual,Target,Tolerance\nFictional cash balance,{actual},100,10\n"


def _row(tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, basis: str) -> str:
    path = tmp_path / "desk.csv"
    path.write_text(text, encoding="utf-8")
    code = cli.main([str(path), "--assisted", "--compare-to", basis, "--period", "Q3 2026",
                     "--dollar-threshold", "1", "--percent-threshold", "1"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    return next(line for line in captured.out.splitlines() if line.startswith("| Fictional"))


def _amount(cell: str) -> Decimal:
    return Decimal(cell.strip().lstrip("$").replace(",", ""))


@pytest.mark.parametrize(("actual", "outcome", "headroom"), [("95", "Near", 5000), ("90", "Near", 10000),
                                                            ("89.999", "Within", 10001)])
def test_a_limit_buffer_is_in_the_captions_unit(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], actual: str, outcome: str, headroom: int) -> None:
    cells = _row(tmp_path, capsys, _limit(actual), "limit").strip("|").split("|")
    # Line Item | Limit Kind | Limit | Actual | Headroom | Headroom % | Utilization | Buffer | Outcome
    assert (_amount(cells[4]), _amount(cells[7]), cells[8].strip()) == (headroom, 10000, outcome)


@pytest.mark.parametrize(("actual", "outcome"), [("110", "In line"), ("110.001", "Higher than benchmark")])
def test_a_benchmark_tolerance_is_in_the_captions_unit(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], actual: str, outcome: str) -> None:
    line = _row(tmp_path, capsys, _benchmark(actual), "benchmark")
    assert "| $10,000.00 |" in line and f"| {outcome} |" in line


@pytest.mark.parametrize(("actual", "outcome"), [("110", "On target"), ("110.001", "Over")])
def test_a_target_tolerance_is_in_the_captions_unit(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], actual: str, outcome: str) -> None:
    line = _row(tmp_path, capsys, _target(actual), "target")
    assert "| $10,000.00 |" in line and line.endswith(f"| {outcome} |")


def test_the_scaling_note_names_what_it_scaled() -> None:
    result = read_input_assisted(_limit("95").encode(), ".csv", filename="desk.csv", compare_to=ComparisonBasis.LIMIT)
    assert ("Amounts scaled from thousands (x1,000), Buffer included. Thresholds stay in the reporting unit "
            "(full currency units, not thousands).") in result.visible_transformations
    plain = read_input_assisted((CAPTION + "Line Item,Type,Budget,Actual\nFictional Sales,Revenue,100,110\n").encode(),
                                ".csv", filename="plain.csv")
    assert ("Amounts scaled from thousands (x1,000). Thresholds stay in the reporting unit "
            "(full currency units, not thousands).") in plain.visible_transformations


def test_the_comparison_reader_scales_them_too() -> None:
    rows, _, _, notes = read_comparison_input(_target("110").encode(), ".csv", filename="t.csv", assisted=True)
    assert Decimal(str(rows[0]["Tolerance"])) == 10000
    assert any(note.startswith("Amounts scaled from thousands (x1,000), Tolerance included.") for note in notes)


def test_a_percent_rows_tolerance_stays_in_points() -> None:
    text = CAPTION + ("Line Item,Measure,Actual,Target,Tolerance\nFictional cash balance,Currency,110,100,10\n"
                      "Fictional margin,Percent,41%,40%,1\n")
    result = read_input_assisted(text.encode(), ".csv", filename="t.csv", compare_to=ComparisonBasis.TARGET)
    rows = {row["line_item"]: row for row in result.rows}
    assert Decimal(str(rows["Fictional cash balance"]["Tolerance"])) == 10000
    assert str(rows["Fictional margin"]["Tolerance"]) == "1"


@pytest.mark.parametrize("buffer", ["10.5", "0", "0.001", "12345.678"])
def test_a_scaled_buffer_is_the_stored_value_times_the_unit_exactly(buffer: str) -> None:
    result = read_input_assisted(_limit("95", buffer).encode(), ".csv", filename="desk.csv",
                                 compare_to=ComparisonBasis.LIMIT)
    assert Fraction(str(result.rows[0]["Buffer"])) == Fraction(buffer) * 1000
