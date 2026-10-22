"""Chat answers that were silently wrong or incomplete (WS2 P1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.chat_helpers import analysed, ask
from variance_agent.analysis import analyze_rows
from variance_agent.chat.handlers import _detect_period_elapsed_months
from variance_agent.chat.session import Phase, Session
from variance_agent.models import AnalysisConfig

UNCLASSIFIED_FILE = b"""Line Item,Type,Budget,Actual
Sales,Revenue,100000,120000
Travel,Expense,10000,16000
Rent,Expense,15000,15000
Mystery,,500,900
"""


# ---- unclassified rows must be disclosed wherever totals appear -------------------


@pytest.mark.parametrize("prompt", [
    "profitability",
    "run rate",
    "sensitivity",
    "what if revenue drops 5%",
    "compare actual vs budget",
    "compare revenue vs expenses",
    "budget utilization",
    "waterfall",
    "memo",
    "tldr",
])
def test_totals_say_when_unclassified_rows_are_left_out(prompt: str) -> None:
    response = ask(analysed(UNCLASSIFIED_FILE), prompt)
    assert "unclassified" in response.text.lower(), prompt


def test_no_caveat_when_nothing_is_unclassified() -> None:
    session = analysed()
    for prompt in ("profitability", "run rate", "sensitivity", "budget utilization"):
        assert "unclassified" not in ask(session, prompt).text.lower(), prompt


# ---- what-if guards ---------------------------------------------------------------


def test_what_if_on_an_unclassified_row_asks_to_classify_it_first() -> None:
    response = ask(analysed(UNCLASSIFIED_FILE), "what if mystery drops 10%")
    assert "classify" in response.text.lower()
    assert "Profit Delta" not in response.text
    assert response.table is None


@pytest.mark.parametrize("prompt", [
    "what if revenue drops 150%", "what if expenses fall 101%", "what if travel drops 150%",
])
def test_what_if_cannot_drop_more_than_everything(prompt: str) -> None:
    response = ask(analysed(UNCLASSIFIED_FILE), prompt)
    assert "more than 100%" in response.text
    assert "Profit Delta" not in response.text


def test_what_if_a_full_drop_is_still_allowed() -> None:
    assert "Profit Delta" in ask(analysed(UNCLASSIFIED_FILE), "what if revenue drops 100%").text


# ---- expense status lists the largest overspends ----------------------------------


def _many_overspends() -> bytes:
    lines = ["Line Item,Type,Budget,Actual", "Sales,Revenue,1000000,1000000"]
    for i in range(1, 8):
        lines.append(f"Dept {i},Expense,1000,{1000 + i * 100}")
    return ("\n".join(lines) + "\n").encode()


def test_expense_status_lists_the_largest_overspends_first() -> None:
    text = ask(analysed(_many_overspends()), "expense status").text
    listed = [line for line in text.splitlines() if line.startswith("• **Dept")]
    assert [line.split("**")[1].rstrip(":") for line in listed] == [
        "Dept 7", "Dept 6", "Dept 5", "Dept 4", "Dept 3",
    ]


# ---- metrics ----------------------------------------------------------------------


def test_metrics_do_not_count_excluded_subtotals() -> None:
    rows: list[dict[str, object]] = [
        {"line_item": "Sales", "type": "Revenue", "budget": "100", "actual": "120"},
        {"line_item": "Rent", "type": "Expense", "budget": "50", "actual": "60"},
        {"line_item": "Total Revenue", "type": "Revenue", "budget": "100", "actual": "120"},
    ]
    result = analyze_rows(rows, AnalysisConfig(
        period="Q3", dollar_threshold=Decimal("1"), percent_threshold=Decimal("0.01"),
    ))
    assert any(row.excluded_from_aggregation for row in result.rows)
    session = Session()
    session.phase = Phase.EXPLORING
    session.result = result
    text = ask(session, "metrics").text
    assert "**Total Line Items:** 2" in text
    assert "1 Revenue, 1 Expense" in text
    assert "2 Favorable" not in text


# ---- duplicate account names --------------------------------------------------------

DUPLICATE_FILE = b"""Line Item,Type,Budget,Actual
Sales,Revenue,100000,120000
Travel,Expense,10000,16000
Travel,Expense,2000,1500
Rent,Expense,15000,15000
"""


def test_detail_shows_every_row_that_shares_a_name() -> None:
    response = ask(analysed(DUPLICATE_FILE), "detail travel")
    assert "Multiple matches" not in response.text
    assert response.table is not None
    assert [row["Actual"] for row in response.table] == ["$16,000.00", "$1,500.00"]
    assert "2 line items are named" in response.text


def test_why_covers_every_row_that_shares_a_name() -> None:
    text = ask(analysed(DUPLICATE_FILE), "why travel").text
    assert "2 line items are named" in text
    assert "$16,000.00" in text and "$1,500.00" in text


def test_different_names_still_ask_which_one() -> None:
    csv = b"Line Item,Type,Budget,Actual\nSales,Revenue,10,12\nSalaries,Expense,10,12\n"
    response = ask(analysed(csv), "why sal")
    assert "Multiple matches" in response.text
    assert response.chips is not None and len(set(response.chips)) == len(response.chips)


# ---- run-rate period parsing --------------------------------------------------------


@pytest.mark.parametrize(("period", "months"), [
    ("Q1 FY2026", 3),
    ("Q3 2026", 9),
    ("FY2026 Q2", 6),
    ("FY2026", 12),
    ("Full Year 2026", 12),
    ("Annual 2026", 12),
    ("FY ending June 2026", 12),
    ("H1 FY26", 6),
    ("H1 2026", 6),
    ("H2 2026", 12),
    ("first half 2026", 6),
    ("Jan-Jun 2026", 6),
    ("January to March 2026", 3),
    ("October 2026", 10),
    ("Month ended Sep 30, 2026", 9),
    ("Jul-26", 7),
    ("YTD Sep", 9),
    ("Month 3", 3),
    ("m11", 11),
])
def test_elapsed_months_follow_the_period_named(period: str, months: int) -> None:
    assert _detect_period_elapsed_months(period)[0] == months


@pytest.mark.parametrize("period", ["banana", "2026"])
def test_an_unrecognised_period_is_flagged_not_guessed_silently(period: str) -> None:
    session = analysed()
    session.period = period
    assert "was not recognised" in ask(session, "run rate").text


# ---- "sheet 2" means the second sheet in the list -------------------------------------


def _workbook(sheets: dict[str, int]) -> bytes:
    """One small P&L per sheet; Sales actual is the sheet's number so each sheet is recognisable."""
    import io

    from openpyxl import Workbook

    book = Workbook()
    first = True
    for name, sales in sheets.items():
        sheet = book.active if first else book.create_sheet()
        assert sheet is not None
        sheet.title = name
        first = False
        sheet.append(["Line Item", "Type", "Budget", "Actual"])
        sheet.append(["Sales", "Revenue", 1000, sales])
        sheet.append(["Rent", "Expense", 500, 500])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_sheet_number_picks_the_listed_position_not_a_name_containing_the_digit() -> None:
    session = analysed(_workbook({"Alpha 2": 1100, "Beta": 1200, "Gamma": 1300}), "w.xlsx")
    response = ask(session, "sheet 2")
    assert session.worksheet == "Beta"
    assert "Switched to worksheet **'Beta'**" in response.text
    assert "Analysis Complete" in response.text
    assert "$1,200.00" in response.text


def test_a_sheet_literally_named_with_a_digit_still_wins() -> None:
    session = analysed(_workbook({"Alpha": 1100, "2": 1200, "Gamma": 1300}), "w.xlsx")
    ask(session, "sheet 2")
    assert session.worksheet == "2"


def test_sheet_number_out_of_range_is_not_found() -> None:
    session = analysed(_workbook({"Alpha": 1100, "Beta": 1200}), "w.xlsx")
    assert "was not found" in ask(session, "sheet 7").text
    assert session.worksheet == "Alpha"


def test_a_year_that_is_not_a_position_still_matches_by_name() -> None:
    session = analysed(_workbook({"Alpha": 1100, "FY 2025": 1200}), "w.xlsx")
    ask(session, "sheet 2025")
    assert session.worksheet == "FY 2025"
