"""X35: the period a file's title names is offered as a chip when the chat asks for the period.

Every workbook here is built in the test and every value is fictional.
"""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.responses import Response
from variance_agent.chat.session import Phase, Session

QUESTION = "What reporting period does this analysis cover? (e.g., Q3 2026, October 2026, FY2026)"


def _book(title: str | None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    if title is not None:
        sheet.append(["Fictional Northwind Co. (FICTIONAL DATA)"])
        sheet.append([title])
    sheet.append(["Line Item", "Type", "Budget", "Actual"])
    sheet.append(["Product Sales", "Revenue", 100000, 120000])
    sheet.append(["Payroll", "Expense", 60000, 68000])
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


def _period_question(title: str | None) -> tuple[Session, Response]:
    session = Session()
    reply = handle_upload(session, _book(title), "plan.xlsx")
    if session.phase == Phase.AWAITING_INTAKE_CONFIRMATION:
        reply = handle_message(session, "Looks right")
    assert session.phase == Phase.AWAITING_PERIOD, reply.text
    return session, reply


@pytest.mark.parametrize(("title", "chips"), [
    ("Budget vs Actual Report Q3 2026 ($ in thousands)", ["Q3 2026"]),
    ("Income Statement - Budget vs Actual Nine months ended September 30, 2026", ["Nine months ended September 30, 2026"]),
    ("Budget vs Actual Report For the period ended September 30, 2026", ["Period ended September 30, 2026"]),
    ("Operating plan Q3 FY2026", ["Q3 FY2026"]),
    ("Operating plan FY2026 Q3", ["FY2026 Q3"]),
    ("Half-year review H1 2026", ["H1 2026"]),
    ("Annual plan FY2026", ["FY2026"]),
    ("Monthly pack October 2026", ["October 2026"]),
    ("Quarterly pack Q3 2026 and October 2026", ["Q3 2026", "October 2026"]),
])
def test_the_period_the_title_names_is_offered_as_a_chip(title: str, chips: list[str]) -> None:
    _, reply = _period_question(title)
    assert reply.chips == chips
    assert QUESTION in reply.text
    named = " and ".join(f"**{chip}**" for chip in chips)
    one = "it" if len(chips) == 1 else "one"
    assert f"Your file's title says {named}: choose {one} below, or type a different period." in reply.text


@pytest.mark.parametrize("title", [
    "Income Statement - Budget vs Actual Nine months ended September 30, 2026",
    "Budget vs Actual Report For the period ended September 30, 2026",
    "Operating plan Q3 FY2026", "Operating plan FY2026 Q3", "Half-year review H1 2026", "Annual plan FY2026",
    "Monthly pack October 2026",
])
def test_choosing_the_chip_sets_the_period_as_if_typed(title: str) -> None:
    session, reply = _period_question(title)
    assert reply.chips
    chosen = handle_message(session, reply.chips[0])
    assert session.period == reply.chips[0]
    assert chosen.text.startswith(f"Period set to: **{reply.chips[0]}**")


def test_a_lead_in_before_a_typed_period_is_still_dropped() -> None:
    session, _ = _period_question(None)
    handle_message(session, "period is Q3 2026")
    assert session.period == "Q3 2026"


@pytest.mark.parametrize("title", [None, "Budget vs Actual Report ($ in thousands)"])
def test_a_title_naming_no_period_asks_exactly_as_before(title: str | None) -> None:
    _, reply = _period_question(title)
    assert not reply.chips
    assert "title says" not in reply.text
    assert QUESTION in reply.text
