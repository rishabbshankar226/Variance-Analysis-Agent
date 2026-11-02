"""X31: a Percent cell that Excel shows as a percentage is read as that percentage, whatever --percent-values says.

Every workbook here is built in the test and every value is fictional.
"""

from __future__ import annotations

import io
from fractions import Fraction
from pathlib import Path

import pytest
from openpyxl import Workbook

from variance_agent import cli
from variance_agent.comparisons import read_comparison_input
from variance_agent.intake import read_input_assisted

NOTE = "Gross margin: read Budget and Actual as the percentages Excel shows (number format '0.0%')."
BOTH = {"E3": "0.0%", "F3": "0.0%"}


def _book(formats: dict[str, str], budget: object = 0.40, actual: object = 0.425) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "KPIs"
    sheet.append(["Line Item", "Type", "Measure", "Better", "Budget", "Actual"])
    sheet.append(["Product Revenue", "Revenue", "Currency", "", 1_200_000, 1_350_000])
    sheet.append(["Gross margin", "", "Percent", "Higher", budget, actual])
    for cell, code in formats.items():
        sheet[cell].number_format = code
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], data: bytes, *flag: str) -> tuple[int, str, str]:
    path = tmp_path / "kpis.xlsx"
    path.write_bytes(data)
    code = cli.main([str(path), "--assisted", "--period", "Q3 2026", "--dollar-threshold", "10000",
                     "--percent-threshold", "5", "--bps-threshold", "50", *flag])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _margin(data: bytes) -> tuple[object, object]:
    result = read_input_assisted(data, ".xlsx", filename="kpis.xlsx")
    assert not result.has_fatal_errors, result.fatal_error_message
    row = next(row for row in result.rows if row["line_item"] == "Gross margin")
    return row["budget"], row["actual"]


@pytest.mark.parametrize("flag", [("--percent-values", "points"), ("--percent-values", "fractions"), ()])
def test_a_percent_formatted_cell_reads_as_the_percentage_excel_shows(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: tuple[str, ...]) -> None:
    code, out, err = _run(tmp_path, capsys, _book(BOTH), *flag)
    assert code == 0, err
    assert "| Gross margin | Percent | 40% | 42.5% | 250 bps |" in out
    assert f"[assisted intake] {NOTE}" in err


def test_fpa_intake_reads_a_percent_formatted_cell_as_shown() -> None:
    result = read_input_assisted(_book(BOTH), ".xlsx", filename="kpis.xlsx")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert _margin(_book(BOTH)) == ("40%", "42.5%")
    assert NOTE in result.visible_transformations


def test_a_general_cell_beside_a_percent_cell_stays_a_bare_rate(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(tmp_path, capsys, _book({"F3": "0.0%"}), "--percent-values", "points")
    assert code == 0, err
    assert "| Gross margin | Percent | 0.4% | 42.5% |" in out
    assert "[assisted intake] Gross margin: read Actual as the percentage Excel shows (number format '0.0%')." in err


def test_the_comparison_reader_reads_a_percent_formatted_cell_as_shown() -> None:
    rows, _, _, notes = read_comparison_input(_book(BOTH), ".xlsx", filename="kpis.xlsx", assisted=True)
    margin = next(row for row in rows if row["Line Item"] == "Gross margin")
    assert (margin["Budget"], margin["Actual"]) == ("40%", "42.5%")
    assert NOTE in notes
    plain = next(row for row in rows if row["Line Item"] == "Product Revenue")
    assert (plain["Budget"], plain["Actual"]) == (1_200_000, 1_350_000)


@pytest.mark.parametrize("stored", ["0.4", "0.425", "0", "-0.03", "1.25", "0.123456789", "0.0005"])
def test_the_percentage_read_is_the_stored_rate_times_100_exactly(stored: str) -> None:
    budget, _ = _margin(_book(BOTH, budget=float(stored)))
    assert isinstance(budget, str) and budget.endswith("%"), budget
    assert Fraction(budget[:-1]) == Fraction(stored) * 100


def test_a_zero_and_a_negative_rate_read_plainly() -> None:
    assert _margin(_book(BOTH, budget=0, actual=-0.03)) == ("0%", "-3%")
