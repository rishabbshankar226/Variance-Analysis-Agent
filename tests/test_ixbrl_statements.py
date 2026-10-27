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
