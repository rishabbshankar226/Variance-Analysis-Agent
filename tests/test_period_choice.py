"""X6: choosing a period reads that period's Budget and Actual columns, never another pair's (fictional data)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.chat_helpers import finish_setup
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Session
from variance_agent.intake import read_input_assisted

MONTH_AND_YTD = (
    "GL Account,Account Description,Sep-26 Budget,Sep-26 Actual,Budget YTD,Actual YTD\n"
    "4000,Fictional Product Revenue,55556,60000,500000,540000\n"
    "6000,Fictional Salaries,22222,23000,200000,207000\n"
).encode("utf-8")


def _revenue(result_rows: list[dict[str, object]]) -> tuple[object, object]:
    row = next(r for r in result_rows if r["line_item"] == "Fictional Product Revenue")
    return row["budget"], row["actual"]


@pytest.mark.parametrize(("period", "budget", "actual"), [("Sep-26", "55556", "60000"), ("YTD", "500000", "540000")])
def test_a_chosen_period_reads_its_own_columns(period: str, budget: str, actual: str) -> None:
    result = read_input_assisted(MONTH_AND_YTD, ".csv", filename="f.csv", selected_period=period)
    assert _revenue(result.rows) == (Decimal(budget), Decimal(actual))


def test_without_a_choice_the_header_reads_as_before() -> None:
    result = read_input_assisted(MONTH_AND_YTD, ".csv", filename="f.csv")
    assert _revenue(result.rows) == (Decimal("500000"), Decimal("540000"))


def test_a_file_with_one_pair_reads_it_whatever_the_choice() -> None:
    only_ytd = b"Account Description,Budget YTD,Actual YTD\nFictional Product Revenue,500000,540000\n"
    result = read_input_assisted(only_ytd, ".csv", filename="f.csv", selected_period="Sep-26")
    assert _revenue(result.rows) == (Decimal("500000"), Decimal("540000"))


def test_the_chat_summary_and_the_analysis_agree_on_the_chosen_month() -> None:
    session = Session()
    upload = handle_upload(session, MONTH_AND_YTD, "f.csv")
    assert upload.chips is not None and "Sep-26" in upload.chips
    summary = handle_message(session, "Sep-26").text
    assert "Budget from 'Sep-26 Budget', Actual from 'Sep-26 Actual'" in summary.replace("\\", "")
    finish_setup(session)
    assert session.result is not None
    row = next(r for r in session.result.rows if r.line_item == "Fictional Product Revenue")
    assert (row.budget, row.actual) == (Decimal("55556"), Decimal("60000"))
