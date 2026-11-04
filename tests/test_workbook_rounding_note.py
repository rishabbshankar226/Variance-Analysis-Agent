"""X32: every sheet that writes a percentage as a number says how it rounds, and no cell changes (fictional files).

A percentage cell holds the whole ratio under `0.0%`; the report rounds tenths half to even. At an exact tie the two
can show different tenths, so the sheet says so in a note of its own (docs/improve/PLAN.md, X32).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing
from variance_agent import cli

ANALYSTS = Path(__file__).resolve().parent / "fixtures" / "analysts"
NOTE = ("A percentage cell holds the whole ratio and is rounded only for display, so a tie such as 12.25% may show as "
        "12.3% here while the report rounds it to even, 12.2%. The audit JSON holds the exact value.")
EXISTING = ("Amounts are in USD. Var % is variance divided by the absolute budget. Favorable means revenue above budget "
            "or expenses below budget. Excel stores numbers in double precision; use the CSV or audit JSON export when "
            "exact decimal values are required.")


def _workbook(tmp_path: Path, source: Path, *extra: str):  # type: ignore[no-untyped-def]
    book, report = tmp_path / "w.xlsx", tmp_path / "r.md"
    assert cli.main([str(source), "--dollar-threshold", "1", "--percent-threshold", "1", "-o", str(report),
                     "--xlsx", str(book), *extra]) == 0
    return load_workbook(book), report.read_text(encoding="utf-8")


def _column_a(sheet) -> list[object]:  # type: ignore[no-untyped-def]
    return [row[0] for row in sheet.iter_rows(values_only=True)]


def test_a_tie_keeps_its_exact_cell_and_the_summary_says_how_it_rounds(tmp_path: Path) -> None:
    source = tmp_path / "tie.csv"
    source.write_text("Line Item,Type,Budget,Actual\nLicence Revenue,Revenue,800,898\nHosting,Expense,1000,1000\n",
                      encoding="utf-8")
    book, report = _workbook(tmp_path, source, "--period", "Q3 2026")
    assert "| Licence Revenue | Revenue | $800.00 | $898.00 | $98.00 | 12.2% |" in report
    rows = book["All Rows"]
    header = [cell.value for cell in rows[1]]
    cell = rows.cell(2, header.index("Var %") + 1)
    assert (rows.cell(2, 1).value, cell.value, cell.number_format) == ("Licence Revenue", float(Decimal("0.1225")), "0.0%")
    column = _column_a(book["Summary"])
    assert column[-2:] == [EXISTING, NOTE]
    assert NOTE not in _column_a(book["All Rows"]) + _column_a(book["Material Variances"])


@pytest.mark.parametrize(("source", "basis", "sheet", "said"), [
    ("ines_limits.csv", "limit", "Limits", True), ("theo_benchmark.csv", "benchmark", "Benchmark", False),
    ("marcus_targets.csv", "target", "Targets", False)])
def test_only_a_basis_sheet_with_percentage_cells_says_how_they_round(tmp_path: Path, source: str, basis: str,
                                                                      sheet: str, said: bool) -> None:
    book, _ = _workbook(tmp_path, ANALYSTS / source, "--assisted", "--compare-to", basis, "--period", "Oct 2026",
                        "--bps-threshold", "1")
    column = _column_a(book[sheet])
    assert (NOTE in column) is said
    if said:
        assert column[-2:] == [NOTE, "Excel stores numbers in double precision; use the CSV or audit JSON export "
                                     "when exact decimal values are required."]


@pytest.mark.parametrize(("extra", "sheet"), [
    (("--sheet", "Consolidated Balance Sheets"), "Lines"), ((), "Summary")])
def test_a_statement_or_filing_sheet_says_how_its_percentages_round(tmp_path: Path, extra: tuple[str, ...],
                                                                    sheet: str) -> None:
    filing = tmp_path / "hal-20250927.htm"
    filing.write_bytes(all_statements_filing())
    book, _ = _workbook(tmp_path, filing, "--assisted", "--period", "FY2025", *extra)
    assert NOTE in _column_a(book[sheet])
