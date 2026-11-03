"""N1: a workbook for every comparison the report covers, matching the report word for word (fictional files).

Each sheet is read back with openpyxl. A Currency figure or a percentage is a number cell equal to float() of the
audit's exact Decimal, in the existing sheets' format for that kind of figure; every word and heading is the report's.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing
from variance_agent import cli
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Session

ANALYSTS = Path(__file__).resolve().parent / "fixtures" / "analysts"
MONEY_FORMAT = "#,##0.00;[Red]-#,##0.00"
PCT_FORMAT = "0.0%"
DOUBLES = "Excel stores numbers in double precision"


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], source: Path, *extra: str):  # type: ignore[no-untyped-def]
    out = {name: tmp_path / name for name in ("r.md", "a.json", "w.xlsx")}
    code = cli.main([str(source), "--assisted", "--dollar-threshold", "1", "--percent-threshold", "1",
                     "-o", str(out["r.md"]), "--audit-json", str(out["a.json"]), "--xlsx", str(out["w.xlsx"]), *extra])
    assert code == 0, capsys.readouterr().err
    return (load_workbook(out["w.xlsx"]), out["r.md"].read_text(encoding="utf-8"),
            json.loads(out["a.json"].read_text(encoding="utf-8")))


def _table(report: str, heading: str) -> list[list[str]]:
    lines = report.split(heading + "\n\n", 1)[1].split("\n\n", 1)[0].splitlines()
    return [[cell.strip().replace("\\", "") for cell in line.strip("|").split("|")] for line in lines if not line.startswith("|---")]


def _values(sheet) -> list[list[object]]:  # type: ignore[no-untyped-def]
    return [[cell.value for cell in row] for row in sheet.iter_rows()]


def _notes(sheet) -> str:  # type: ignore[no-untyped-def]
    return " ".join(str(v) for row in _values(sheet) for v in row if isinstance(v, str))


def test_a_limit_workbook_matches_the_report_and_the_audit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    book, report, audit = _run(tmp_path, capsys, ANALYSTS / "ines_limits.csv", "--compare-to", "limit", "--period", "Oct 2026")
    assert book.sheetnames == ["Limits"]
    sheet = book["Limits"]
    table = _table(report, "## Lines, by severity")
    rows = _values(sheet)
    assert rows[0] == table[0]
    details = {d["line_item"]: d for d in audit["basis_details"]}
    measures = {m["line_item"]: m for m in audit["measure_rows"]}
    for number, (cells, words) in enumerate(zip(rows[1:len(table)], table[1:], strict=True), start=2):
        name = cells[0]
        assert (name, cells[1], cells[8]) == (words[0], words[1], words[8])
        d, m = details[name], measures[name]
        for column, value in ((2, m["comparison"]), (3, m["actual"]), (4, d["headroom"])):
            assert cells[column] == float(value) and sheet.cell(number, column + 1).number_format == MONEY_FORMAT
        for column, value in ((5, d["headroom_percent"]), (6, d["utilization"])):
            assert cells[column] == float(value) and sheet.cell(number, column + 1).number_format == PCT_FORMAT
        assert cells[7] == (None if d["buffer"] is None else float(d["buffer"]))
    assert DOUBLES in _notes(sheet) and "Breach is strictly beyond a limit" in _notes(sheet)


@pytest.mark.parametrize(("source", "basis", "sheet_name", "status"), [
    ("theo_benchmark.csv", "benchmark", "Benchmark", True), ("marcus_targets.csv", "target", "Targets", False)])
def test_a_benchmark_or_target_workbook_matches_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                          source: str, basis: str, sheet_name: str, status: bool) -> None:
    book, report, _ = _run(tmp_path, capsys, ANALYSTS / source, "--compare-to", basis, "--period", "Oct 2026",
                           "--bps-threshold", "1")
    assert book.sheetnames == [sheet_name]
    rows = _values(book[sheet_name])
    table = _table(report, "## Lines")
    # Rates, basis points and tolerances stay the report's text, as the Measures sheet holds them.
    assert [[str(v) if v is not None else "" for v in row] for row in rows[:len(table)]] == table
    assert ("Status" in table[0]) is status


def test_covenant_metrics_get_a_limits_sheet_and_their_build(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    filing = tmp_path / "hal-20250927.htm"
    filing.write_bytes(all_statements_filing())
    book, report, _ = _run(tmp_path, capsys, filing, "--metrics", str(ANALYSTS / "clara_metrics.json"),
                           "--compare-file", str(ANALYSTS / "clara_covenants.csv"), "--compare-to", "limit",
                           "--period", "FY2025", "--multiple-threshold", "0.1")
    assert book.sheetnames == ["Limits", "Metrics"]
    limits, words = _values(book["Limits"]), _table(report, "## Lines, by severity")
    # Turns stay the report's text; the two percentages are numbers that show as the report's percent.
    assert [limits[1][i] for i in (0, 1, 2, 3, 4, 7, 8)] == [words[1][i] for i in (0, 1, 2, 3, 4, 7, 8)]
    assert [f"{float(limits[1][i]) * 100:.1f}%" for i in (5, 6)] == [words[1][i] for i in (5, 6)]
    build = [str(row[0]) for row in _values(book["Metrics"]) if row[0]]
    assert build[0] == ("Gross leverage = 0.88x = (Long-term debt [balance sheet, instant]) / (Net income [income, fy] "
                        "+ Interest expense [income, fy] + Depreciation and amortization [cash flow, fy])")
    assert "Long-term debt [balance sheet, instant]: $1,500,000,000.00 (Sep 2025, hal-20250927.htm)" in build


def test_a_balance_sheet_workbook_matches_the_report_and_the_audit(tmp_path: Path,
                                                                   capsys: pytest.CaptureFixture[str]) -> None:
    filing = tmp_path / "hal-20250927.htm"
    filing.write_bytes(all_statements_filing())
    book, report, audit = _run(tmp_path, capsys, filing, "--sheet", "Consolidated Balance Sheets", "--period", "FY2025")
    assert book.sheetnames == ["Lines"]
    sheet = book["Lines"]
    rows = _values(sheet)
    table = _table(report, "## Lines")
    assert rows[0] == table[0] == ["Line Item", "Prior Period (Sep 2024)", "Actual", "Change", "Change (%)",
                                   "Direction", "Material"]
    measures = {m["line_item"]: m for m in audit["measure_rows"]}
    for number, (cells, words) in enumerate(zip(rows[1:len(table)], table[1:], strict=True), start=2):
        assert (cells[0], cells[5], cells[6]) == (words[0], words[5], words[6])
        m = measures[str(cells[0]).removesuffix(" (Total)")]
        for column, value in ((1, m["comparison"]), (2, m["actual"]), (3, m["variance"])):
            assert cells[column] == float(value) and sheet.cell(number, column + 1).number_format == MONEY_FORMAT
    assert "Checked every subtotal and the balance sheet identity" in _notes(sheet) and DOUBLES in _notes(sheet)


def test_a_filings_income_workbook_is_headed_by_its_printed_totals(tmp_path: Path,
                                                                   capsys: pytest.CaptureFixture[str]) -> None:
    filing = tmp_path / "hal-20250927.htm"
    filing.write_bytes(all_statements_filing())
    book, report, _ = _run(tmp_path, capsys, filing, "--period", "FY2025")
    assert book.sheetnames == ["Summary", "Material Variances", "Root Causes & Actions", "All Rows"]
    summary = _values(book["Summary"])
    labels = [row[0] for row in summary]
    assert "Total Revenue" not in labels and "Net Operating Impact" not in labels
    net_sales = next(row for row in summary if row[0] == "Net sales")
    assert net_sales[1:4] == [3_900_000_000, 4_100_000_000, 200_000_000]
    assert "- Net sales: $4,100,000,000.00 vs. $3,900,000,000.00 ($200,000,000.00, 5.1%)" in report
    assert "Headline figures are the filing's own printed totals, each from its XBRL fact." in _notes(book["Summary"])


def test_labels_that_look_like_formulas_stay_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "limits.csv"
    source.write_text("Line Item,Actual,Limit,Limit Kind\n=SUM(A1:A2),90,100,Max\n+Desk,80,100,Max\n-Desk,70,100,Max\n"
                      "@Desk,60,100,Max\n", encoding="utf-8")
    book, _, _ = _run(tmp_path, capsys, source, "--compare-to", "limit", "--period", "Oct 2026")
    names = {row[0] for row in _values(book["Limits"])[1:5]}
    assert names == {"=SUM(A1:A2)", "+Desk", "-Desk", "@Desk"}


def test_the_chat_exports_a_limit_workbook() -> None:
    session = Session()
    handle_upload(session, (ANALYSTS / "ines_limits.csv").read_bytes(), "ines_limits.csv")
    for answer in ("Looks right", "Oct 2026", "$1 or 1%", "USD"):
        handle_message(session, answer)
    reply = handle_message(session, "export excel")
    assert reply.level != "error" and reply.download is not None, reply.text
    assert [str(name) for name in reply.download] == ["variance_workbook_oct_2026.xlsx"]
    assert reply.text.startswith("Excel workbook ready for download: Limits sheet.")


def test_a_filing_with_export_flags_gets_the_same_workbook(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """An export flag sends a run down the comparison path; a filing's statement keeps its own sheets there (N1)."""
    filing = tmp_path / "hal-20250927.htm"
    filing.write_bytes(all_statements_filing())
    book, _, _ = _run(tmp_path, capsys, filing, "--period", "FY2025", "--long-output", str(tmp_path / "long.csv"))
    assert book.sheetnames == ["Summary", "Material Variances", "Root Causes & Actions", "All Rows"]
    assert "Net sales" in [row[0] for row in _values(book["Summary"])]
