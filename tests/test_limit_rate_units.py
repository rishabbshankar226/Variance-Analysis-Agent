"""X47: a Percent limit row shows its headroom and buffer in basis points, as its tolerance is (fictional data)."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest
from openpyxl import load_workbook

from variance_agent import cli

HEADER = "Line Item,Measure,Actual,Limit,Limit Kind,Buffer\n"


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], row: str, *extra: str) -> tuple[str, dict[str, str]]:
    source, audit = tmp_path / "limits.csv", tmp_path / "audit.json"
    source.write_text(HEADER + row + "\n", encoding="utf-8")
    code = cli.main([str(source), "--assisted", "--compare-to", "limit", "--period", "Q3 2026", "--bps-threshold", "1",
                     "--dollar-threshold", "1", "--percent-threshold", "1", "--audit-json", str(audit), *extra])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    line = next(line for line in captured.out.splitlines() if line.startswith("| Fictional"))
    return line, json.loads(audit.read_text(encoding="utf-8"))["basis_details"][0]


@pytest.mark.parametrize(("row", "line"), [
    ("Fictional margin,Percent,41%,40%,Min,0.5",
     "| Fictional margin | Min | 40% | 41% | 100 bps | 2.5% | 102.5% | 50 bps | Within |"),
    ("Fictional margin,Percent,39.5%,40%,Min,0.5",
     "| Fictional margin | Min | 40% | 39.5% | -50 bps | -1.2% | 98.8% | 50 bps | Breach |"),
    ("Fictional leverage,Percent,40.25%,40%,Max,",
     "| Fictional leverage | Max | 40% | 40.25% | -25 bps | -0.6% | 100.6% |  | Breach |"),
])
def test_a_percent_limit_rows_headroom_and_buffer_are_in_basis_points(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], row: str, line: str) -> None:
    shown, details = _run(tmp_path, capsys, row)
    assert shown == line
    cells = [cell.strip() for cell in shown.strip("|").split("|")]
    # The audit keeps points; the table shows them times 100.
    assert Fraction(cells[4].removesuffix(" bps")) == Fraction(details["headroom"]) * 100
    if details.get("buffer") is not None:
        assert Fraction(cells[7].removesuffix(" bps")) == Fraction(details["buffer"]) * 100


def test_a_currency_limit_row_is_unchanged(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shown, _ = _run(tmp_path, capsys, "Fictional desk,Currency,90,100,Max,10")
    assert shown == "| Fictional desk | Max | $100.00 | $90.00 | $10.00 | 10.0% | 90.0% | $10.00 | Near |"


def test_the_limits_sheet_shows_basis_points(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    book = tmp_path / "limits.xlsx"
    _run(tmp_path, capsys, "Fictional margin,Percent,41%,40%,Min,0.5", "--xlsx", str(book))
    sheet = load_workbook(book)["Limits"]
    row = next(r for r in sheet.iter_rows(values_only=True) if r and r[0] == "Fictional margin")
    assert (row[4], row[7]) == ("100 bps", "50 bps")
