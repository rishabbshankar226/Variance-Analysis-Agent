"""Reading financial-statement tables out of fictional 10-K / 10-Q PDFs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from variance_agent.pdf_tables import PdfReadError, StatementTable, extract_statement_tables

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"
TEN_K = FIXTURES_DIR / "fixture_o_10k_statements.pdf"
TEN_Q = FIXTURES_DIR / "fixture_p_10q_three_and_nine_months.pdf"
SCANNED = FIXTURES_DIR / "fixture_q_scanned_no_text.pdf"

needs_pdfplumber = pytest.mark.skipif(
    __import__("importlib").util.find_spec("pdfplumber") is None,
    reason="the optional [pdf] extra is not installed",
)


def _read(path: Path, **kwargs: float) -> list[StatementTable]:
    return extract_statement_tables(path.read_bytes(), path.name, **kwargs)  # type: ignore[arg-type]


@needs_pdfplumber
def test_10k_finds_statements_and_skips_index_and_mdna_pages() -> None:
    tables = _read(TEN_K)
    assert [t.name for t in tables] == [
        "Consolidated Statements of Operations (p. 4)",
        "Consolidated Balance Sheets (pp. 5-6)",
    ]
    assert [t.page_numbers for t in tables] == [(4,), (5, 6)]


@needs_pdfplumber
def test_10k_income_statement_rows() -> None:
    income = _read(TEN_K)[0]
    assert income.raw_rows == [
        ["(In millions, except per share amounts)"],
        ["Line Item", "FY2025", "FY2024", "FY2023"],
        ["Product revenue", "1,250.4", "1,100.2", "980.0"],
        ["Subscription, licensing and other services revenue", "410.6", "388.1", "350.0"],
        ["Total revenue", "1,661.0", "1,488.3", "1,330.0"],
        ["Cost of revenue", "702.3", "640.0", "590.5"],
        ["Gross profit", "958.7", "848.3", "739.5"],
        ["Research and development", "210.0", "195.5", "180.0"],
        ["Selling, general and administrative", "305.2", "290.0", "270.1"],
        ["Restructuring charges (1)", "—", "12.4", "—"],
        ["Total operating expenses", "515.2", "497.9", "450.1"],
        ["Operating income", "443.5", "350.4", "289.4"],
        ["Other income (expense), net", "(18.7)", "4.2", "(2.5)"],
        ["Income before income taxes", "424.8", "354.6", "286.9"],
        ["Provision for income taxes", "89.2", "74.5", "60.2"],
        ["Net income", "335.6", "280.1", "226.7"],
    ]


@needs_pdfplumber
def test_10k_notes_name_every_column_and_left_out_row() -> None:
    notes = _read(TEN_K)[0].notes
    assert "Read column 'Year Ended December 31, 2025' as FY2025" in notes
    assert "Read column 'Year Ended December 31, 2023' as FY2023" in notes
    left_out = [n for n in notes if n.startswith("Left out")]
    assert left_out == [
        "Left out 'Earnings per share: Basic' (per-share and share counts are not money totals)",
        "Left out 'Earnings per share: Diluted' (per-share and share counts are not money totals)",
        "Left out 'Weighted-average shares outstanding: Basic' "
        "(per-share and share counts are not money totals)",
        "Left out 'Weighted-average shares outstanding: Diluted' "
        "(per-share and share counts are not money totals)",
    ]


@needs_pdfplumber
def test_10k_balance_sheet_continues_onto_next_page() -> None:
    balance = _read(TEN_K)[1]
    assert balance.raw_rows[:3] == [
        ["(In millions)"],
        ["Line Item", "Dec 2025", "Dec 2024"],
        ["Cash and cash equivalents", "820.5", "610.2"],
    ]
    assert [row[0] for row in balance.raw_rows[2:]] == [
        "Cash and cash equivalents", "Accounts receivable, net", "Total current assets",
        "Property and equipment, net", "Total assets", "Accounts payable", "Total liabilities",
        "Total stockholders' equity", "Total liabilities and stockholders' equity",
    ]


@needs_pdfplumber
def test_10q_splits_three_and_nine_month_columns() -> None:
    three, nine = _read(TEN_Q)
    assert three.name == "Condensed Consolidated Statements of Operations, Three Months Ended (p. 1)"
    assert nine.name == "Condensed Consolidated Statements of Operations, Nine Months Ended (p. 1)"
    assert three.raw_rows[:3] == [
        ["(In thousands) (Unaudited)"],
        ["Line Item", "Sep 2026", "Sep 2025"],
        ["Revenue", "52,310", "48,120"],
    ]
    assert nine.raw_rows[1:3] == [
        ["Line Item", "Sep 2026", "Sep 2025"],
        ["Revenue", "150,880", "139,400"],
    ]
    assert [row[0] for row in nine.raw_rows[2:]] == [
        "Revenue", "Cost of revenue", "Gross profit", "Operating expenses", "Operating income",
    ]
    assert "Read column 'Nine Months Ended September 30, 2026' as Sep 2026" in nine.notes
    assert any(n.startswith("Left out 'Net income per diluted share'") for n in nine.notes)


@needs_pdfplumber
def test_html_printed_10k_layout() -> None:
    """Layout seen in a real 10-K printed from EDGAR HTML, rebuilt with fictional data."""
    income, position = _read(FIXTURES_DIR / "fixture_r_html_printed_10k.pdf")
    assert income.name == "Consolidated Statements of Operations (p. 2)"
    assert income.raw_rows == [
        ["(millions, except per share data)"],
        ["Line Item", "FY2025", "FY2024", "FY2023"],
        ["Net sales", "6,566", "6,412", "6,120"],
        ["Cost of sales", "4,502", "4,828", "4,306"],
        ["Operating income", "2,064", "1,584", "1,814"],
        ["Net earnings", "1,610", "1,250", "1,402"],
    ]
    assert any(n.startswith("Left out 'Antidilutive shares'") for n in income.notes)
    assert position.raw_rows[:3] == [
        ["(millions, except footnotes)"],
        ["Line Item", "Jan 2026", "Feb 2025"],
        ["Cash and cash equivalents", "4,762", "3,805"],
    ]
    assert [row[0] for row in position.raw_rows[2:]] == [
        "Cash and cash equivalents", "Inventory", "Total assets"]


@needs_pdfplumber
def test_combined_10q_for_parent_and_subsidiary() -> None:
    """Layout seen in a real combined 10-Q, rebuilt with fictional data."""
    tables = _read(FIXTURES_DIR / "fixture_s_combined_10q.pdf")
    assert [t.name for t in tables] == [
        "Northwind Fictional Holdings, Inc.: Statements of Consolidated Operations, "
        "Three Months Ended (p. 1)",
        "Northwind Fictional Holdings, Inc.: Statements of Consolidated Operations, "
        "Six Months Ended (p. 1)",
        "Northwind Fictional Holdings, Inc.: Consolidated Balance Sheets (p. 2)",
        "Northwind Fictional Holdings, Inc.: Condensed Statements of Consolidated Cash Flows (p. 3)",
        "Northwind Fictional Airways, Inc.: Statements of Consolidated Operations, "
        "Three Months Ended (p. 4)",
        "Northwind Fictional Airways, Inc.: Statements of Consolidated Operations, "
        "Six Months Ended (p. 4)",
    ]
    three_months, six_months, position, cash = tables[:4]
    assert three_months.raw_rows[1:3] == [
        ["Line Item", "Jun 2026", "Jun 2025"], ["Passenger revenue", "16,100", "13,836"]]
    assert six_months.raw_rows[2] == ["Passenger revenue", "29,267", "25,696"]
    assert position.raw_rows == [
        ["(In millions, except shares)"],
        ["Line Item", "Jun 2026", "Dec 2025"],
        ["Cash and cash equivalents", "1,166", "942"],
        ["Receivables, net", "473", "391"],
        ["Total current assets", "1,639", "1,333"],
        ["Total assets", "4,569", "3,448"],
        ["Accounts payable", "772", "567"],
        ["Other (current liabilities)", "854", "757"],
        ["Total current liabilities", "1,626", "1,324"],
        ["Long-term debt", "1,294", "1,062"],
        ["Other (noncurrent liabilities)", "500", "478"],
        ["Total noncurrent liabilities", "1,794", "1,540"],
        ["Common stock at par, $0.01 par value; authorized 1,000 shares; issued and outstanding "
         "1,000 shares at both June 30, 2026 and December 31, 2025", "—", "—"],
        ["Retained earnings", "1,149", "584"],
        ["Total liabilities and stockholders' equity", "4,569", "3,448"],
    ]
    assert "Named the repeated line 'Other' as 'Other (current liabilities)'" in position.notes
    assert [row[0] for row in cash.raw_rows[2:]] == [
        "Net cash provided by operating activities", "Capital expenditures",
        "Investing Activities: Other, net", "Payments of long-term debt",
        "Financing Activities: Other, net",
    ]


@needs_pdfplumber
def test_repeat_reads_are_cached_and_isolated() -> None:
    first = _read(TEN_K)
    first[0].raw_rows.clear()
    first[0].notes.clear()
    second = _read(TEN_K)
    assert len(second[0].raw_rows) == 16
    assert second[0].notes


@needs_pdfplumber
def test_scanned_pdf_gets_a_plain_message() -> None:
    with pytest.raises(PdfReadError, match="looks like a scanned image"):
        _read(SCANNED)


@needs_pdfplumber
def test_damaged_pdf_gets_a_plain_message() -> None:
    with pytest.raises(PdfReadError, match="couldn't open 'broken.pdf'"):
        extract_statement_tables(b"%PDF-1.4 not really a pdf", "broken.pdf")


@needs_pdfplumber
def test_page_that_breaks_the_reader_gets_a_plain_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object, **kwargs: object) -> object:
        raise RuntimeError("pdfminer internals")

    monkeypatch.setattr("pdfplumber.page.Page.extract_words", broken)
    with pytest.raises(PdfReadError, match="couldn't open") as caught:
        _read(TEN_K, max_seconds=19.5)  # a key the cache has not seen
    assert "pdfminer" not in str(caught.value)


@needs_pdfplumber
def test_pdf_without_statements_gets_a_plain_message(tmp_path: Path) -> None:
    from tests.fixtures.realworld.minipdf import Page, write_pdf

    page = Page()
    page.text(72, 72, "FICTIONAL SYNTHETIC DATA - board meeting minutes")
    path = tmp_path / "minutes.pdf"
    write_pdf(path, [page])
    with pytest.raises(PdfReadError, match="couldn't find an income statement"):
        _read(path)


@needs_pdfplumber
def test_page_limit() -> None:
    with pytest.raises(PdfReadError, match="has 6 pages"):
        _read(TEN_K, max_pages=5)


@needs_pdfplumber
def test_time_limit() -> None:
    with pytest.raises(PdfReadError, match="took too long"):
        _read(TEN_K, max_seconds=0)


def test_missing_pdf_extra_explains_the_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pdfplumber", None)
    with pytest.raises(PdfReadError, match=r"pip install 'variance-analysis-agent\[pdf\]'"):
        extract_statement_tables(b"%PDF-1.4 uncached", "statement.pdf")
