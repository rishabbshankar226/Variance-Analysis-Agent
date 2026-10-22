"""Blank comparison amounts: the chat offers only choices that change the outcome (WS2 P2)."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from tests.chat_helpers import finish_setup
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

BLANK_BUDGET = (
    b"Line Item,Type,Budget,Actual\n"
    b"Sales,Revenue,1000,1200\n"
    b"Consulting,Revenue,,300\n"
    b"Rent,Expense,500,500\n"
)
BLANK_FORECAST = (
    b"Line Item,Type,Forecast,Actual\n"
    b"Subscription Revenue,Revenue,110000,115500\n"
    b"New Partner Revenue,Revenue,,2500\n"
    b"Payroll Expense,Expense,65000,68000\n"
)


def _consulting_budget(session: Session) -> Decimal:
    assert session.parsed_rows is not None
    row = next(r for r in session.parsed_rows if r["line_item"] == "Consulting")
    budget = row["budget"]
    assert isinstance(budget, Decimal)
    return budget


@pytest.mark.parametrize(("data", "zero_chip"), [
    (BLANK_BUDGET, "Treat blank budgets as 0 (unbudgeted)"),
    (BLANK_FORECAST, "Treat blank forecast values as 0 (not in forecast)"),
], ids=["budget", "forecast"])
def test_prompt_offers_one_reading_and_says_what_it_is(data: bytes, zero_chip: str) -> None:
    session = Session()
    response = handle_upload(session, data, "blank.csv")
    assert session.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
    assert response.chips == [zero_chip, "Upload a different file"]
    assert "read as 0" in response.text


def test_keep_answer_is_explained_not_silently_read_as_zero() -> None:
    session = Session()
    handle_upload(session, BLANK_BUDGET, "blank.csv")
    response = handle_message(session, "Keep blank budgets")
    assert session.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
    assert response.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
    assert "cannot stay blank" in response.text
    assert response.chips is not None and response.chips[0].startswith("Treat blank budgets as 0")


def test_forecast_keep_answer_is_explained_too() -> None:
    session = Session()
    handle_upload(session, BLANK_FORECAST, "blank.csv")
    response = handle_message(session, "Keep blank forecast values")
    assert session.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
    assert "cannot stay blank" in response.text
    assert "budget" not in response.text.lower()


@pytest.mark.parametrize("answer", [
    "Treat blank budgets as 0 (unbudgeted)", "yes", "0", "treat them as zero", "unbudgeted",
])
def test_confirming_reads_the_blank_as_zero_and_says_so(answer: str) -> None:
    session = Session()
    handle_upload(session, BLANK_BUDGET, "blank.csv")
    response = handle_message(session, answer)
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert _consulting_budget(session) == Decimal("0")
    assert "Treated blank budgets as 0 on 1 unbudgeted line" in response.text


def test_an_unrecognised_answer_asks_again() -> None:
    session = Session()
    handle_upload(session, BLANK_BUDGET, "blank.csv")
    response = handle_message(session, "hmm")
    assert session.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
    assert response.chips is not None and response.chips[0].startswith("Treat blank budgets as 0")


def test_the_audit_records_the_zero_read() -> None:
    session = Session()
    handle_upload(session, BLANK_BUDGET, "blank.csv")
    handle_message(session, "Treat blank budgets as 0 (unbudgeted)")
    finish_setup(session)
    download = handle_message(session, "export audit").download
    assert download is not None
    record = json.loads(next(iter(download.values())))
    assert record["transformations"]["zero_reads"]["blank_budgets"] == 1
