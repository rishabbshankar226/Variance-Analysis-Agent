"""Helpers for driving the chat bot through its guided intake in tests."""

from __future__ import annotations

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.responses import Response
from variance_agent.chat.session import Phase, Session

SAMPLE_CSV = b"""Line Item,Type,Budget,Actual
Product Sales,Revenue,100000,120000
Service Revenue,Revenue,50000,47000
Payroll,Expense,60000,68000
Marketing,Expense,20000,33000
Office Supplies,Expense,5000,4800
Rent,Expense,15000,15000
"""

_ANSWERS = {
    Phase.AWAITING_INTAKE_CONFIRMATION: "Looks right",
    Phase.AWAITING_PERIOD: "Q3 2026",
    Phase.AWAITING_THRESHOLDS: "$1,000 or 5%",
    Phase.AWAITING_CURRENCY: "USD",
}


def finish_setup(session: Session, *, unclassified: str = "Skip all") -> Session:
    """Answer the guided questions until the session reaches EXPLORING."""
    for _ in range(12):
        if session.phase == Phase.EXPLORING:
            break
        if session.phase == Phase.RESOLVE_UNCLASSIFIED:
            handle_message(session, unclassified)
        else:
            handle_message(session, _ANSWERS[session.phase])
    assert session.phase == Phase.EXPLORING
    return session


def analysed(
    csv_bytes: bytes = SAMPLE_CSV, name: str = "data.csv", *, session: Session | None = None,
    unclassified: str = "Skip all",
) -> Session:
    """A session that has uploaded ``csv_bytes`` and finished the guided setup."""
    target = session if session is not None else Session()
    handle_upload(target, csv_bytes, name)
    return finish_setup(target, unclassified=unclassified)


def ask(session: Session, text: str) -> Response:
    return handle_message(session, text)
