"""Balance sheets and cash flow statements from Inline XBRL filings (docs/analysts/PLAN.md R7-R9).

Every filing here is built by tests/fixtures/ixbrl/build_ixbrl.py and is fictional.
"""

from __future__ import annotations

from decimal import Decimal

from tests.fixtures.ixbrl.build_ixbrl import (
    all_statements_filing,
    balance_rows,
    cash_flow_rows,
    position_filing,
    row,
)
from variance_agent.ixbrl import Statement, read_statements

M = Decimal(1_000_000)


def _statement(data: bytes, kind: str) -> Statement:
    found = [s for s in read_statements(data, "hal-20250927.htm") if s.kind == kind]
    assert len(found) == 1, [s.name for s in found]
    return found[0]


def _values(statement: Statement, label: str) -> list[Decimal | None]:
    line = next(line for line in statement.lines if line.label == label)
    return [None if key is None else key.displayed for key in line.keys]


# R8 and the label cell -------------------------------------------------------------------------


def test_figures_tagged_inside_a_label_are_label_text_not_the_line() -> None:
    sheet = _statement(position_filing("CONSOLIDATED BALANCE SHEETS", balance_rows()), "balance_sheet")
    label = "Common stock, $0.01 par value; 500 shares authorized; 120 and 118 shares issued"
    line = next(line for line in sheet.lines if line.label == label)
    assert (line.concept, line.measure, _values(sheet, label)) == ("us-gaap:CommonStockValue", "Currency", [1 * M, 1 * M])
    assert not sheet.left_out


def test_a_cash_flow_statement_is_one_statement_over_its_duration_columns() -> None:
    flows = _statement(all_statements_filing(), "cash_flow")
    assert (flows.name, flows.labels) == ("Consolidated Statements of Cash Flows", ["FY2025", "FY2024"])


def test_beginning_and_ending_cash_take_the_duration_columns_by_date() -> None:
    flows = _statement(all_statements_filing(), "cash_flow")
    begin = next(line for line in flows.lines if line.label.endswith("beginning of year"))
    end = next(line for line in flows.lines if line.label.endswith("end of year"))
    assert [key.period for key in begin.keys if key] == [("instant", "2024-09-28"), ("instant", "2023-09-30")]
    assert [key.period for key in end.keys if key] == [("instant", "2025-09-27"), ("instant", "2024-09-28")]
    assert [key.displayed for key in begin.keys if key] == [2000 * M, 1350 * M]
    assert [key.displayed for key in end.keys if key] == [2600 * M, 2000 * M]


def test_a_cash_line_that_would_be_both_a_beginning_and_an_ending_balance_refuses() -> None:
    rows = cash_flow_rows()
    # The day before FY2025 starts is FY2024's end: one fact at each places one way, the other the other.
    rows.insert(-2, row("Cash, mixed", "".join(r for r in []) or
                        '<ix:nonFraction name="us-gaap:Cash" contextRef="I25" unitRef="usd" decimals="-6" scale="6"'
                        ' format="ixt:num-dot-decimal">5</ix:nonFraction>',
                        '<ix:nonFraction name="us-gaap:Cash" contextRef="I23" unitRef="usd" decimals="-6" scale="6"'
                        ' format="ixt:num-dot-decimal">5</ix:nonFraction>'))
    flows = _statement(position_filing("CONSOLIDATED STATEMENTS OF CASH FLOWS", rows), "cash_flow")
    assert flows.problem == ("I could not read every figure of 'Cash, mixed' in the Consolidated Statements of Cash Flows: "
                             "its balances fall at the end of one column and the start of another. Upload the filing's "
                             "PDF, or a CSV or Excel copy of the statement.")


def test_a_balance_sheet_keeps_its_instant_columns() -> None:
    sheet = _statement(all_statements_filing(), "balance_sheet")
    assert (sheet.name, sheet.labels) == ("Consolidated Balance Sheets", ["Sep 2025", "Sep 2024"])


# Statement assembly shapes from Draw A, rebuilt fictional -------------------------------------------

from tests.fixtures.ixbrl.build_ixbrl import POSITION_RESOURCES, document, fact, statement  # noqa: E402


def _filing(body: str, resources: str = "") -> bytes:
    return document(body).replace("</ix:resources>", POSITION_RESOURCES + resources + "</ix:resources>").encode("utf-8")


def test_a_balance_sheet_printed_as_two_titled_tables_reads_as_one() -> None:
    rows = balance_rows()
    split = next(i for i, r in enumerate(rows) if "LIABILITIES AND" in r)
    body = (statement("CONSOLIDATED BALANCE SHEETS — ASSETS", rows[:split])
            + statement("CONSOLIDATED BALANCE SHEETS — LIABILITIES AND EQUITY", rows[split:]))
    sheet = _statement(_filing(body), "balance_sheet")
    assert [line.label for line in sheet.lines][-1] == "Total liabilities and stockholders' equity"
    assert len(sheet.lines) == 15


def test_a_cash_flow_title_without_of_is_a_cash_flow_statement() -> None:
    flows = _statement(_filing(statement("Condensed Consolidated Statements Cash Flows", cash_flow_rows())), "cash_flow")
    assert flows.name == "Condensed Consolidated Statements Cash Flows"


def test_a_cash_table_of_instants_titled_like_the_statement_is_not_the_statement() -> None:
    reconciliation = [row("Cash and cash equivalents", fact("us-gaap:CashAndCashEquivalentsAtCarryingValue", "I25", "2,500"),
                          fact("us-gaap:CashAndCashEquivalentsAtCarryingValue", "I24", "1,900")),
                      row("Restricted cash", fact("us-gaap:RestrictedCash", "I25", "100"), fact("us-gaap:RestrictedCash", "I24", "100")),
                      row("Total cash, cash equivalents and restricted cash shown in the statements of cash flows",
                          fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I25", "2,600"),
                          fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I24", "2,000"))]
    body = (statement("Cash reported in the statements of cash flows", reconciliation)
            + statement("CONSOLIDATED STATEMENTS OF CASH FLOWS", cash_flow_rows()))
    flows = _statement(_filing(body), "cash_flow")
    assert flows.lines[0].label == "Net income"


QUARTER_RESOURCES = "".join(
    f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999'
    f'</xbrli:identifier></xbrli:entity><xbrli:period>{period}</xbrli:period></xbrli:context>'
    for cid, period in [
        ("Q3_25", "<xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate>"),
        ("Q3_24", "<xbrli:startDate>2024-07-01</xbrli:startDate><xbrli:endDate>2024-09-30</xbrli:endDate>"),
        ("YTD_25", "<xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate>"),
        ("YTD_24", "<xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-09-30</xbrli:endDate>"),
        ("E_0630_25", "<xbrli:instant>2025-06-30</xbrli:instant>"), ("E_0630_24", "<xbrli:instant>2024-06-30</xbrli:instant>"),
        ("E_1231_24", "<xbrli:instant>2024-12-31</xbrli:instant>"), ("E_1231_23", "<xbrli:instant>2023-12-31</xbrli:instant>"),
        ("E_0930_25", "<xbrli:instant>2025-09-30</xbrli:instant>"), ("E_0930_24", "<xbrli:instant>2024-09-30</xbrli:instant>"),
    ])


def test_three_and_nine_month_columns_in_one_table_each_take_their_own_beginning_cash() -> None:
    cash = "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"

    def four(label: str, concept: str, values: tuple[str, str, str, str], contexts: tuple[str, str, str, str]) -> str:
        return row(label, *(fact(concept, c, v) for v, c in zip(values, contexts, strict=True)))

    durations = ("Q3_25", "Q3_24", "YTD_25", "YTD_24")
    rows = [four("Net income", "us-gaap:NetIncomeLoss", ("100", "90", "300", "270"), durations),
            four("Net cash provided by operating activities", "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                 ("100", "90", "300", "270"), durations),
            four("Net increase in cash",
                 "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
                 ("100", "90", "300", "270"), durations),
            four("Cash at beginning of period", cash, ("1,200", "1,000", "1,000", "820"),
                 ("E_0630_25", "E_0630_24", "E_1231_24", "E_1231_23")),
            four("Cash at end of period", cash, ("1,300", "1,090", "1,300", "1,090"),
                 ("E_0930_25", "E_0930_24", "E_0930_25", "E_0930_24"))]
    found = [s for s in read_statements(_filing(statement("CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS", rows),
                                                 QUARTER_RESOURCES), "hal.htm") if s.kind == "cash_flow"]
    assert [(s.name, s.problem) for s in found] == [
        ("Condensed Consolidated Statements of Cash Flows, 3 Months Ended", ""),
        ("Condensed Consolidated Statements of Cash Flows, 9 Months Ended", "")]
    quarter, year_to_date = found
    assert _values(quarter, "Cash at beginning of period") == [1200 * M, 1000 * M]
    assert _values(year_to_date, "Cash at beginning of period") == [1000 * M, 820 * M]
    assert _values(year_to_date, "Cash at end of period") == [1300 * M, 1090 * M]
