"""Build synthetic, fictional 10-K and 10-Q style PDF fixtures.

Every company, figure and filing here is fictional. Run from the repository root:
    python tests/fixtures/realworld/build_pdf_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from minipdf import Page, write_pdf  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent
COMPANY = "NORTHWIND FICTIONAL HOLDINGS, INC."
FICTIONAL = "FICTIONAL SYNTHETIC DATA - NOT A REAL COMPANY OR FILING"
LABEL_X = 72
ROW = 13

Row = tuple[str, tuple[str, ...] | None, int]  # label, values (None = no values), indent


def _statement(
    page: Page,
    y: float,
    columns: list[float],
    rows: list[Row],
    *,
    dollar_rows: frozenset[str] = frozenset(),
) -> float:
    for label, values, indent in rows:
        page.text(LABEL_X + indent, y, label)
        for x_right, value in zip(columns, values or ()):
            if label in dollar_rows:
                page.text(x_right - 52, y, "$")
            page.right(x_right, y, value)
        y += ROW
    return y


def _title_block(page: Page, title: str, caption: str) -> None:
    page.center(306, 40, FICTIONAL, size=7)
    page.center(306, 60, COMPANY, size=10)
    page.center(306, 74, title, size=10)
    page.center(306, 88, caption)


def build_fixture_o() -> None:
    """Fixture o: 10-K with cover, index, MD&A table, income statement and a two-page balance sheet."""
    cover = Page()
    cover.center(306, 40, FICTIONAL, size=7)
    cover.center(306, 200, "FORM 10-K", size=16)
    cover.center(306, 230, COMPANY, size=12)
    cover.center(306, 250, "For the fiscal year ended December 31, 2025")

    index = Page()
    index.center(306, 40, FICTIONAL, size=7)
    index.center(306, 60, "INDEX TO CONSOLIDATED FINANCIAL STATEMENTS", size=10)
    for i, (name, page_no) in enumerate([
        ("Consolidated Statements of Operations", "4"),
        ("Consolidated Balance Sheets", "5"),
        ("Notes to Consolidated Financial Statements", "7"),
    ]):
        index.text(LABEL_X, 90 + i * ROW, name)
        index.right(540, 90 + i * ROW, page_no)

    mdna = Page()
    mdna.center(306, 40, FICTIONAL, size=7)
    mdna.text(LABEL_X, 60, "MANAGEMENT'S DISCUSSION AND ANALYSIS", size=10)
    mdna.text(LABEL_X, 80, "Revenue increased 12% compared with the prior year.")
    for x_right, head in zip([400, 470, 540], ["2025", "2024", "% Change"]):
        mdna.right(x_right, 100, head)
    _statement(mdna, 114, [400, 470, 540], [
        ("Total revenue", ("1,661.0", "1,488.3", "12 %"), 0),
        ("Operating income", ("443.5", "350.4", "27 %"), 0),
    ])

    income = Page()
    _title_block(income, "CONSOLIDATED STATEMENTS OF OPERATIONS",
                 "(In millions, except per share amounts)")
    cols = [380, 460, 540]
    income.center(445, 112, "Year Ended December 31,")
    for x_right, year in zip(cols, ["2025", "2024", "2023"]):
        income.right(x_right, 125, year)
    end = _statement(income, 145, cols, [
        ("Revenue:", None, 0),
        ("Product revenue", ("1,250.4", "1,100.2", "980.0"), 10),
        ("Subscription, licensing and other", None, 10),
        ("services revenue", ("410.6", "388.1", "350.0"), 20),
        ("Total revenue", ("1,661.0", "1,488.3", "1,330.0"), 0),
        ("Cost of revenue", ("702.3", "640.0", "590.5"), 0),
        ("Gross profit", ("958.7", "848.3", "739.5"), 0),
        ("Operating expenses:", None, 0),
        ("Research and development", ("210.0", "195.5", "180.0"), 10),
        ("Selling, general and administrative", ("305.2", "290.0", "270.1"), 10),
        ("Restructuring charges (1)", ("—", "12.4", "—"), 10),
        ("Total operating expenses", ("515.2", "497.9", "450.1"), 0),
        ("Operating income", ("443.5", "350.4", "289.4"), 0),
        ("Other income (expense), net", ("(18.7)", "4.2", "(2.5)"), 0),
        ("Income before income taxes", ("424.8", "354.6", "286.9"), 0),
        ("Provision for income taxes", ("89.2", "74.5", "60.2"), 0),
        ("Net income", ("335.6", "280.1", "226.7"), 0),
        ("Earnings per share:", None, 0),
        ("Basic", ("3.36", "2.80", "2.27"), 10),
        ("Diluted", ("3.31", "2.77", "2.24"), 10),
        ("Weighted-average shares outstanding:", None, 0),
        ("Basic", ("99.9", "100.0", "99.9"), 10),
        ("Diluted", ("101.4", "101.1", "101.2"), 10),
    ], dollar_rows=frozenset({"Product revenue", "Net income"}))
    income.text(LABEL_X, end + 10, "See accompanying notes to consolidated financial statements.")
    income.center(306, 760, "4")

    cols = [460, 540]
    assets = Page()
    _title_block(assets, "CONSOLIDATED BALANCE SHEETS", "(In millions)")
    assets.center(465, 112, "December 31,")
    for x_right, year in zip(cols, ["2025", "2024"]):
        assets.right(x_right, 125, year)
    _statement(assets, 145, cols, [
        ("Cash and cash equivalents", ("820.5", "610.2"), 0),
        ("Accounts receivable, net", ("300.1", "280.4"), 0),
        ("Total current assets", ("1,120.6", "890.6"), 0),
        ("Property and equipment, net", ("450.0", "430.0"), 0),
        ("Total assets", ("1,570.6", "1,320.6"), 0),
    ], dollar_rows=frozenset({"Cash and cash equivalents", "Total assets"}))
    assets.center(306, 760, "5")

    liabilities = Page()
    _title_block(liabilities, "CONSOLIDATED BALANCE SHEETS (Continued)", "(In millions)")
    liabilities.center(465, 112, "December 31,")
    for x_right, year in zip(cols, ["2025", "2024"]):
        liabilities.right(x_right, 125, year)
    _statement(liabilities, 145, cols, [
        ("Accounts payable", ("120.3", "110.0"), 0),
        ("Total liabilities", ("520.3", "480.0"), 0),
        ("Total stockholders' equity", ("1,050.3", "840.6"), 0),
        ("Total liabilities and stockholders' equity", ("1,570.6", "1,320.6"), 0),
    ])
    liabilities.center(306, 760, "6")

    write_pdf(FIXTURES_DIR / "fixture_o_10k_statements.pdf",
              [cover, index, mdna, income, assets, liabilities])


def build_fixture_p() -> None:
    """Fixture p: 10-Q income statement with three- and nine-month columns side by side."""
    page = Page()
    _title_block(page, "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS",
                 "(In thousands) (Unaudited)")
    cols = [330, 400, 480, 550]
    page.center(342, 106, "Three Months Ended")
    page.center(342, 118, "September 30,")
    page.center(522, 106, "Nine Months Ended")
    page.center(522, 118, "September 30,")
    for x_right, year in zip(cols, ["2026", "2025", "2026", "2025"]):
        page.right(x_right, 131, year)
    _statement(page, 150, cols, [
        ("Revenue", ("52,310", "48,120", "150,880", "139,400"), 0),
        ("Cost of revenue", ("21,004", "19,870", "61,230", "58,010"), 0),
        ("Gross profit", ("31,306", "28,250", "89,650", "81,390"), 0),
        ("Operating expenses", ("18,200", "17,950", "55,100", "52,300"), 0),
        ("Operating income", ("13,106", "10,300", "34,550", "29,090"), 0),
        ("Net income per diluted share", ("0.41", "0.32", "1.08", "0.91"), 0),
    ], dollar_rows=frozenset({"Revenue"}))
    write_pdf(FIXTURES_DIR / "fixture_p_10q_three_and_nine_months.pdf", [page])


def build_fixture_q() -> None:
    """Fixture q: an image-only (scanned) page with no readable text."""
    page = Page()
    page.box(72, 72, 468, 600)
    write_pdf(FIXTURES_DIR / "fixture_q_scanned_no_text.pdf", [page])


def main() -> None:
    build_fixture_o()
    build_fixture_p()
    build_fixture_q()
    print("Built fictional PDF fixtures o, p and q in tests/fixtures/realworld/")


if __name__ == "__main__":
    main()
