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
        for x_right, value in zip(columns, values or (), strict=False):
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
    for x_right, head in zip([400, 470, 540], ["2025", "2024", "% Change"], strict=False):
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
    for x_right, year in zip(cols, ["2025", "2024", "2023"], strict=False):
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
    for x_right, year in zip(cols, ["2025", "2024"], strict=False):
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
    for x_right, year in zip(cols, ["2025", "2024"], strict=False):
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
    for x_right, year in zip(cols, ["2026", "2025", "2026", "2025"], strict=False):
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


def build_fixture_r() -> None:
    """Fixture r: layout printed from an EDGAR HTML filing.

    The index lists note numbers and page numbers in two aligned columns, the unit
    caption shares the year header line, and a "Form 10-K" footer carries the page
    number in the last amount column.
    """
    def chrome(page: Page, number: str) -> None:
        page.center(306, 30, FICTIONAL, size=7)
        page.text(480, 44, "Index to Financial Statements", size=7)
        page.text(210, 770, f"NORTHWIND FICTIONAL 2025 Form 10-K {number}", size=7)

    index = Page()
    chrome(index, "38")
    index.text(LABEL_X, 70, "INDEX TO CONSOLIDATED FINANCIAL STATEMENTS", size=10)
    for i, (note, name, page_no) in enumerate([
        ("", "Consolidated Statements of Operations", "42"),
        ("", "Consolidated Statements of Financial Position", "43"),
        ("1", "Summary of Accounting Policies", "44"),
        ("2", "Net Sales", "45"),
        ("3", "Leases", "47"),
    ]):
        if note:
            index.text(LABEL_X, 90 + i * ROW, "Note")
            index.right(130, 90 + i * ROW, note)
            index.text(170, 90 + i * ROW, name)
        else:
            index.text(LABEL_X, 90 + i * ROW, name)
        index.right(560, 90 + i * ROW, page_no)

    cols = [432, 495, 557]
    income = Page()
    chrome(income, "42")
    income.text(LABEL_X, 70, "Consolidated Statements of Operations", size=10)
    income.text(LABEL_X, 88, "(millions, except per share data)")
    for x_right, year in zip(cols, ["2025", "2024", "2023"], strict=False):
        income.right(x_right - 18, 88, year)
    end = _statement(income, 104, cols, [
        ("Net sales", ("6,566", "6,412", "6,120"), 0),
        ("Cost of sales", ("4,502", "4,828", "4,306"), 0),
        ("Operating income", ("2,064", "1,584", "1,814"), 0),
        ("Net earnings", ("1,610", "1,250", "1,402"), 0),
        ("Basic earnings per share", ("3.22", "2.50", "2.80"), 0),
        ("Antidilutive shares", ("0.5", "2.1", "1.1"), 0),
    ], dollar_rows=frozenset({"Net sales", "Basic earnings per share"}))
    income.text(LABEL_X, end + 10, "See accompanying Notes to Consolidated Financial Statements.")
    income.right(557, end + 30, "7")  # a stray footnote marker after the statement

    position = Page()
    chrome(position, "43")
    position.text(LABEL_X, 70, "Consolidated Statements of Financial Position", size=10)
    position.right(481, 86, "January 31,")
    position.right(549, 86, "February 1,")
    position.text(LABEL_X, 99, "(millions, except footnotes)")
    position.right(468, 99, "2026")
    position.right(536, 99, "2025")
    _statement(position, 116, [488, 557], [
        ("Cash and cash equivalents", ("4,762", "3,805"), 0),
        ("Inventory", ("12,740", "11,886"), 0),
        ("Total assets", ("17,502", "15,691"), 0),
    ], dollar_rows=frozenset({"Cash and cash equivalents"}))

    write_pdf(FIXTURES_DIR / "fixture_r_html_printed_10k.pdf", [index, income, position])


def build_fixture_s() -> None:
    """Fixture s: combined 10-Q for a parent and its subsidiary, laid out like a real one.

    Titles read "Statements of Consolidated ...", three- and six-month headers share a
    line, only one year of the balance-sheet date header lines up with its column, a
    wrapped common-stock label carries stray numbers, and "Other" repeats.
    """
    parent, subsidiary = "NORTHWIND FICTIONAL HOLDINGS, INC.", "NORTHWIND FICTIONAL AIRWAYS, INC."
    end_note = ("The accompanying Combined Notes to Condensed Consolidated Financial Statements "
                "are an integral part of these statements.")

    def heading(page: Page, company: str, title: str, caption: str) -> None:
        page.center(306, 30, FICTIONAL, size=7)
        page.text(20, 44, "Table of Contents", size=7)
        page.center(306, 60, company, size=10)
        page.center(306, 74, title, size=10)
        page.center(306, 88, caption)

    def operations(company: str, revenue: tuple[str, ...]) -> Page:
        page = Page()
        heading(page, company, "STATEMENTS OF CONSOLIDATED OPERATIONS (UNAUDITED)", "(In millions)")
        page.text(330, 104, "Three Months Ended June 30,")
        page.text(470, 104, "Six Months Ended June 30,")
        cols = [380, 440, 510, 574]
        for x_right, year in zip(cols, ["2026", "2025", "2026", "2025"], strict=False):
            page.right(x_right, 117, year)
        end = _statement(page, 133, cols, [
            ("Operating revenue:", None, 0),
            ("Passenger revenue", revenue, 10),
            ("Cargo revenue", ("527", "430", "949", "859"), 10),
            ("Total operating revenue", ("16,627", "14,266", "30,216", "26,555"), 10),
            ("Operating expense:", None, 0),
            ("Salaries and related costs", ("4,686", "4,413", "9,100", "8,700"), 10),
            ("Aircraft fuel", ("5,110", "2,775", "9,000", "5,500"), 10),
            ("Special charges (credits)", ("(145)", "447", "(100)", "500"), 10),
            ("Other operating expenses", ("5,880", "5,306", "10,416", "10,000"), 10),
            ("Total operating expense", ("15,531", "12,941", "28,416", "24,700"), 10),
            ("Operating income", ("1,096", "1,325", "1,800", "1,855"), 0),
            ("Nonoperating income (expense):", None, 0),
            ("Interest expense", ("(343)", "(361)", "(690)", "(720)"), 10),
            ("Interest income", ("148", "167", "300", "330"), 10),
            ("Total nonoperating expense, net", ("(195)", "(194)", "(390)", "(390)"), 10),
            # 1,096 - 195 = 901; filings round each figure on its own, so print 900.
            ("Income before income taxes", ("900", "1,131", "1,410", "1,465"), 0),
            ("Income tax expense", ("200", "250", "310", "320"), 0),
            ("Net income", ("700", "881", "1,100", "1,145"), 0),
        ], dollar_rows=frozenset({"Passenger revenue", "Net income"}))
        page.text(LABEL_X, end + 10, end_note, size=7)
        page.center(306, 760, "3")
        return page

    position = Page()
    heading(position, parent, "CONSOLIDATED BALANCE SHEETS (UNAUDITED)", "(In millions, except shares)")
    position.right(449, 104, "June 30, 2026")
    position.right(569, 104, "December 31, 2025")
    cols = [467, 574]
    y = _statement(position, 120, cols, [
        ("Cash and cash equivalents", ("1,166", "942"), 0),
        ("Receivables, net", ("473", "391"), 0),
        ("Total current assets", ("1,639", "1,333"), 0),
        ("Total assets", ("4,569", "3,448"), 0),
        ("LIABILITIES AND STOCKHOLDERS' EQUITY", None, 0),
        ("Accounts payable", ("772", "567"), 0),
        ("Other", ("854", "757"), 0),
        ("Total current liabilities", ("1,626", "1,324"), 0),
        ("Long-term debt", ("1,294", "1,062"), 0),
        ("Other", ("500", "478"), 0),
        ("Total noncurrent liabilities", ("1,794", "1,540"), 0),
        ("Stockholders' equity:", None, 0),
    ], dollar_rows=frozenset({"Cash and cash equivalents"}))
    position.text(LABEL_X, y, "Common stock at par,")
    position.right(300, y, "$0.01")
    position.text(304, y, "par value; authorized 1,000 shares; issued and outstanding")
    y += ROW
    position.text(LABEL_X, y, "1,000 shares at both June 30,")
    position.right(300, y, "2026")
    position.text(304, y, "and December 31, 2025")
    position.right(467, y, "—")
    position.right(574, y, "—")
    y = _statement(position, y + ROW, cols, [
        ("Retained earnings", ("1,149", "584"), 0),
        ("Total liabilities and stockholders' equity", ("4,569", "3,448"), 0),
    ])
    position.text(LABEL_X, y + 10, end_note, size=7)

    cash = Page()
    heading(cash, parent, "CONDENSED STATEMENTS OF CONSOLIDATED CASH FLOWS (UNAUDITED)", "(In millions)")
    cash.center(530, 104, "Six Months Ended June 30,")
    cols = [490, 574]
    for x_right, year in zip(cols, ["2026", "2025"], strict=False):
        cash.right(x_right, 117, year)
    y = _statement(cash, 133, cols, [
        ("Net cash provided by operating activities", ("2,409", "1,927"), 0),
        ("Investing Activities:", None, 0),
        ("Capital expenditures", ("(1,015)", "(920)"), 10),
        ("Other, net", ("(111)", "(70)"), 10),
        ("Financing Activities:", None, 0),
        ("Payments of long-term debt", ("(537)", "(611)"), 10),
        ("Other, net", ("(93)", "(99)"), 10),
    ])
    cash.text(LABEL_X, y + 10, end_note, size=7)
    cash.text(LABEL_X, y + 40, "Northwind Fictional quarterly report page")
    cash.right(574, y + 40, "6")

    write_pdf(FIXTURES_DIR / "fixture_s_combined_10q.pdf", [
        operations(parent, ("16,100", "13,836", "29,267", "25,696")),
        position, cash,
        operations(subsidiary, ("16,100", "13,836", "29,267", "25,696")),
    ])



def build_fixture_t() -> None:
    """Fictional HALV.FAKE: dollars in millions, EPS per share, counts in units."""
    page = Page()
    page.center(306, 40, FICTIONAL, size=7)
    page.center(306, 60, "HALVORSEN INSTRUMENTS, INC. - HALV.FAKE", size=10)
    page.center(306, 74, "CONSOLIDATED STATEMENTS OF OPERATIONS", size=10)
    page.center(306, 88, "(Dollars in millions, except per-share data; share counts in units)", size=8)
    for x, year in zip([440, 540], ["2026", "2025"], strict=True):
        page.right(x, 112, year)
    _statement(page, 130, [440, 540], [
        ("Revenue", ("1,287.5", "1,250.0"), 0),
        ("Operating expenses", ("383.0", "380.0"), 0),
        ("Operating income", ("904.5", "870.0"), 0),
        ("Earnings per share:", None, 0),
        ("Basic", ("0.95", "0.88"), 10),
        ("Diluted", ("0.91", "0.84"), 10),
        ("Weighted average common shares outstanding:", None, 0),
        ("Basic", ("50,000,000", "49,000,000"), 10),
        ("Diluted", ("52,000,000", "51,000,000"), 10),
    ])
    page.text(72, 270, "See accompanying notes to consolidated financial statements.", size=7)
    page.right(574, 750, "1")
    write_pdf(FIXTURES_DIR / "fixture_t_halvorsen_fake_eps.pdf", [page])


def main() -> None:
    build_fixture_o()
    build_fixture_p()
    build_fixture_q()
    build_fixture_r()
    build_fixture_s()
    build_fixture_t()
    print("Built fictional PDF fixtures o, p, q, r, s and t in tests/fixtures/realworld/")


if __name__ == "__main__":
    main()
