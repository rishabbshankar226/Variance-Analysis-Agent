"""X46: a Percent row's Tolerance or Buffer that Excel shows as a percentage reads as that percentage, in points.

Every workbook here is built in the test and every value is fictional.
"""

from __future__ import annotations

import io
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from openpyxl import Workbook

from variance_agent import cli
from variance_agent.comparisons import read_comparison_input
from variance_agent.intake import read_input_assisted
from variance_agent.models import ComparisonBasis

TARGET_NOTE = "Fictional yield: read Target, Actual and Tolerance as the percentages Excel shows (number format '0.0%')."
LIMIT_NOTE = "Fictional margin: read Limit, Actual and Buffer as the percentages Excel shows (number format '0.0%')."


def _book(header: list[str], row: list[object], formats: dict[str, str]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(header)
    sheet.append(row)
    for cell, code in formats.items():
        sheet[cell].number_format = code
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


def _target(tolerance: float, tolerance_format: str | None = "0.00%") -> bytes:
    formats = {"C2": "0.0%", "D2": "0.0%", **({"E2": tolerance_format} if tolerance_format else {})}
    return _book(["Line Item", "Measure", "Actual", "Target", "Tolerance"],
                 ["Fictional yield", "Percent", 0.402, 0.40, tolerance], formats)


def _limit(actual: float, buffer: float) -> bytes:
    return _book(["Line Item", "Measure", "Actual", "Limit", "Limit Kind", "Buffer"],
                 ["Fictional margin", "Percent", actual, 0.40, "Min", buffer], {"C2": "0.0%", "D2": "0.0%", "F2": "0.0%"})


def _fpa_row(data: bytes, basis: ComparisonBasis) -> tuple[dict[str, object], list[str]]:
    result = read_input_assisted(data, ".xlsx", filename="rates.xlsx", compare_to=basis)
    assert not result.has_fatal_errors, result.fatal_error_message
    return result.rows[0], result.visible_transformations


def test_fpa_intake_reads_a_percent_formatted_tolerance_in_points() -> None:
    row, notes = _fpa_row(_target(0.0025), ComparisonBasis.TARGET)
    assert row["Tolerance"] == Decimal("0.25")
    assert TARGET_NOTE in notes


def test_fpa_intake_reads_a_percent_formatted_buffer_in_points() -> None:
    row, notes = _fpa_row(_limit(0.403, 0.005), ComparisonBasis.LIMIT)
    assert row["Buffer"] == Decimal("0.5")
    assert LIMIT_NOTE in notes


def test_the_comparison_reader_reads_a_percent_formatted_tolerance_in_points() -> None:
    # This reader counts no Target column among its amounts, and its analysis refuses a target; the cell is read anyway.
    rows, _, _, notes = read_comparison_input(_target(0.0025), ".xlsx", filename="rates.xlsx", assisted=True)
    assert rows[0]["Tolerance"] == Decimal("0.25")
    assert "Fictional yield: read Actual and Tolerance as the percentages Excel shows (number format '0.0%')." in notes


def test_a_general_tolerance_keeps_its_value_in_points() -> None:
    row, notes = _fpa_row(_target(0.0025, None), ComparisonBasis.TARGET)
    assert row["Tolerance"] == Decimal("0.0025")
    assert "Fictional yield: read Target and Actual as the percentages Excel shows (number format '0.0%')." in notes


def test_a_currency_rows_buffer_is_not_read_as_a_percentage() -> None:
    data = _book(["Line Item", "Measure", "Actual", "Limit", "Limit Kind", "Buffer"],
                 ["Fictional desk", "Currency", 90, 100, "Max", 0.05], {"F2": "0.0%"})
    row, _ = _fpa_row(data, ComparisonBasis.LIMIT)
    assert row["Buffer"] == Decimal("0.05")


@pytest.mark.parametrize("stored", ["0.0025", "0.002", "0.0019", "0.123456789", "0", "0.0005"])
def test_the_points_read_are_the_stored_fraction_times_100_exactly(stored: str) -> None:
    fpa, _ = _fpa_row(_target(float(stored)), ComparisonBasis.TARGET)
    rows, _, _, _ = read_comparison_input(_target(float(stored)), ".xlsx", filename="rates.xlsx", assisted=True)
    for value in (fpa["Tolerance"], rows[0]["Tolerance"]):
        assert isinstance(value, Decimal) and Fraction(value) == Fraction(stored) * 100


def _line(tmp_path: Path, capsys: pytest.CaptureFixture[str], data: bytes, basis: str) -> str:
    path = tmp_path / "rates.xlsx"
    path.write_bytes(data)
    code = cli.main([str(path), "--assisted", "--compare-to", basis, "--period", "Q3 2026", "--bps-threshold", "1",
                     "--dollar-threshold", "1", "--percent-threshold", "1"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    return next(line for line in captured.out.splitlines() if line.startswith("| Fictional"))


@pytest.mark.parametrize(("tolerance", "shown", "outcome"), [
    (0.002, "20 bps", "On target"),  # the difference is the tolerance: edge included
    (0.0019, "19 bps", "Over"),
    (0.0025, "25 bps", "On target"),
])
def test_a_target_rows_outcome_uses_the_tolerance_excel_shows(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], tolerance: float, shown: str, outcome: str) -> None:
    line = _line(tmp_path, capsys, _target(tolerance), "target")
    assert line == f"| Fictional yield | 40% | 40.2% | 20 bps | {shown} | {outcome} |"


@pytest.mark.parametrize(("actual", "buffer", "status"), [
    (0.403, 0.003, "Near"),  # headroom 0.3 points is the buffer: edge included
    (0.403, 0.0029, "Within"),
    (0.403, 0.005, "Near"),
])
def test_a_limit_rows_status_uses_the_buffer_excel_shows(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], actual: float, buffer: float, status: str) -> None:
    line = _line(tmp_path, capsys, _limit(actual, buffer), "limit")
    assert line.endswith(f"| {status} |"), line
