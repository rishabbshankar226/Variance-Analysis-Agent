"""C2: a unit caption scales stored amounts exactly once on every path (fictional workbooks; tickers end in .FAKE).

The FP&A path's handling (E1) is the reference: a caption scales stored values once, and never over cells
whose number format already shows them scaled. Each case runs on the FP&A path, the earnings path and the
file API, which share no intake code.
"""

from __future__ import annotations

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from openpyxl import Workbook

from variance_agent import analyze_file, cli
from variance_agent.api import AudienceOptions
from variance_agent.audience import AudienceConfig
from variance_agent.comparisons import read_comparison_input
from variance_agent.models import ComparisonBasis

CAPTION = "Fictional Widgets Inc. (FAKE) ($ in thousands)"
LINES = [("Revenue", "Revenue", 1234, 1200), ("Operating Expenses", "Expense", 800, 790)]
COMMON = ["--period", "Q3", "--dollar-threshold", "1", "--percent-threshold", "0.01", "--assisted"]


def _book(path: Path, *, caption: bool, scaled_format: bool | str) -> Path:
    """Line Item, Type, Actual, Consensus, Budget. A scaled format holds the full amount and shows thousands."""
    book = Workbook()
    sheet = book.active
    sheet.title = "Results"
    if caption:
        sheet.append([CAPTION])
        sheet.append([])
    sheet.append(["Line Item", "Type", "Actual", "Consensus", "Budget"])
    for label, kind, actual, consensus in LINES:
        sheet.append([label, kind, *(v * 1000 if scaled_format else v for v in (actual, consensus, consensus))])
        if scaled_format:
            for column in (3, 4, 5):
                sheet.cell(row=sheet.max_row, column=column).number_format = "#,##0,"
    if scaled_format == "mixed":
        sheet.cell(row=sheet.max_row, column=3).number_format = "General"
    book.save(path)
    return path


def _fpa_actual(path: Path, tmp_path: Path) -> str:
    report = tmp_path / "fpa.md"
    assert cli.main([str(path), *COMMON, "-o", str(report)]) == 0
    row = next(line for line in report.read_text(encoding="utf-8").splitlines() if line.startswith("| Revenue |"))
    return row.split("|")[4].strip()  # | Line | Type | Budget | Actual | ...


def _earnings_actual(path: Path, tmp_path: Path) -> str:
    report = tmp_path / "earnings.md"
    assert cli.main([str(path), *COMMON, "--preset", "earnings", "--compare-to", "consensus", "-o", str(report)]) == 0
    row = next(line for line in report.read_text(encoding="utf-8").splitlines() if line.startswith("| Revenue |"))
    return row.split("|")[4].strip()  # | Line | Segment | Measure | Actual | Consensus | ...


def _api_actual(path: Path) -> Decimal:
    table = analyze_file(path, AudienceConfig("Q3", Decimal("1"), Decimal("0.01")),
                         options=AudienceOptions(assisted=True, bases=(ComparisonBasis.CONSENSUS,)))
    result = table.comparisons[0].result
    assert result is not None
    return next(row.actual for row in result.rows if row.line_item == "Revenue")


@pytest.mark.parametrize(("caption", "scaled_format"), [(True, False), (False, True), (True, True)],
                         ids=["caption-alone", "format-alone", "both"])
def test_every_path_reads_the_full_amount_once(tmp_path: Path, caption: bool, scaled_format: bool) -> None:
    path = _book(tmp_path / "book.xlsx", caption=caption, scaled_format=scaled_format)
    assert _fpa_actual(path, tmp_path) == "$1,234,000.00"
    assert _earnings_actual(path, tmp_path) == "$1,234,000.00"
    actual = _api_actual(path)
    assert Fraction(actual) == Fraction(1234) * 1000  # Fraction oracle: stored x 1,000, exactly once


def test_the_earnings_path_says_it_scaled_and_records_the_scale(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _book(tmp_path / "book.xlsx", caption=True, scaled_format=False)
    audit, report = tmp_path / "a.json", tmp_path / "r.md"
    assert cli.main([str(path), *COMMON, "--preset", "earnings", "--compare-to", "consensus",
                     "--audit-json", str(audit), "-o", str(report)]) == 0
    assert ("[comparison intake] Amounts scaled from thousands (x1,000). Thresholds stay in the reporting unit "
            "(full currency units, not thousands).") in capsys.readouterr().err
    assert json.loads(audit.read_text("utf-8"))["transformations"]["unit_scale"] == "1000"


def test_a_caption_over_cells_already_shown_in_thousands_is_not_applied_again(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _book(tmp_path / "book.xlsx", caption=True, scaled_format=True)
    _earnings_actual(path, tmp_path)
    assert "so they were read as stored, not scaled again" in capsys.readouterr().err


@pytest.mark.parametrize("preset", [[], ["--preset", "earnings", "--compare-to", "consensus"]], ids=["fpa", "earnings"])
def test_a_caption_over_a_mix_of_formats_refuses_on_every_path(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], preset: list[str]) -> None:
    path = _book(tmp_path / "book.xlsx", caption=True, scaled_format="mixed")
    with pytest.raises(SystemExit):
        cli.main([str(path), *COMMON, *preset, "-o", str(tmp_path / "r.md")])
    assert ("The title of 'book.xlsx' says amounts are in thousands, but the amounts' number formats don't agree "
            "with it") in capsys.readouterr().err.replace("\n", " ")


def test_only_a_currency_row_s_amount_columns_scale() -> None:
    text = (f"{CAPTION}\n\nLine Item,Measure,Actual,Consensus,Consensus Low,Consensus High,# Est\n"
            "Revenue,Currency,\"1,234\",$1200,(5),1300,12\nDiluted EPS,Per Share,1.25,1.20,1.10,1.30,12\n")
    rows, _, _, notes = read_comparison_input(text.encode("utf-8"), ".csv", filename="t.csv", assisted=True)
    revenue, eps = rows
    assert (revenue["Actual"], revenue["Consensus"], revenue["Consensus Low"], revenue["Consensus High"]) == (
        "1234000", "$1200000", "-5000", "1300000")
    assert revenue["# Est"] == "12"
    assert {k: eps[k] for k in ("Actual", "Consensus", "Consensus Low", "Consensus High", "# Est")} == {
        "Actual": "1.25", "Consensus": "1.20", "Consensus Low": "1.10", "Consensus High": "1.30", "# Est": "12"}
    assert any(note.startswith("Amounts scaled from thousands") for note in notes)


def test_a_cell_the_strict_reader_refuses_is_left_for_it_to_refuse() -> None:
    text = f"{CAPTION}\n\nLine Item,Actual,Consensus\nRevenue,500-,400\n"
    rows, _, _, _ = read_comparison_input(text.encode("utf-8"), ".csv", filename="t.csv", assisted=True)
    assert rows[0]["Actual"] == "500-"
    assert rows[0]["Consensus"] == "400000"


def test_without_a_caption_nothing_scales() -> None:
    text = "Line Item,Actual,Consensus\nRevenue,1234,1200\n"
    rows, _, _, notes = read_comparison_input(text.encode("utf-8"), ".csv", filename="t.csv", assisted=True)
    assert (rows[0]["Actual"], rows[0]["Consensus"]) == ("1234", "1200")
    assert not any("scaled" in note for note in notes)
