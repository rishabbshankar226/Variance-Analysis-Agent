"""X22: a total that doesn't match its lines is named with its figures, and can be left out (fictional data)."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from tests.chat_helpers import finish_setup
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session
from variance_agent.intake import audit_transformations, plain_analysis_error

ROUNDED = b"""Fictional Northwind Co. ($ in thousands)

Line Item,Type,Budget,Actual
Fictional Product Revenue,Revenue,500,540
Fictional Service Revenue,Revenue,200,160
Total Revenue,Revenue,700,700
Fictional Salaries,Expense,150,152
Fictional Rent,Expense,60,60
Fictional Travel,Expense,40,45
Total Opex,Expense,251,257
"""


def _refused() -> tuple[Session, object]:
    session = Session()
    handle_upload(session, ROUNDED, "rounded.csv")
    response = None
    for answer in ("Looks right", "Q3 2026", "$10,000 or 5%"):
        response = handle_message(session, answer)
    response = handle_message(session, "USD")
    return session, response


def test_the_refusal_names_the_total_and_its_arithmetic() -> None:
    session, response = _refused()
    text = response.text.replace("\\", "")  # type: ignore[attr-defined]
    apart = Fraction(251000) - Fraction(250000)  # Fraction oracle: the total less the sum of its lines
    assert ("'Total Opex' looks like the total of the Expense lines above it, but its Budget is $251,000.00 and those "
            f"lines add up to $250,000.00 (${int(apart):,}.00 apart).") in text
    assert "can't be checked, so I stopped instead of guessing" in text
    assert response.chips[:2] == ["Leave Total Opex out", "Upload a different file"]  # type: ignore[attr-defined]
    assert session.phase is not Phase.AWAITING_FILE and session.parsed_rows is not None
    assert "detail rows detail rows" not in text


def test_leaving_the_total_out_runs_the_analysis_and_records_it() -> None:
    session, _ = _refused()
    response = handle_message(session, "Leave Total Opex out")
    assert session.phase is Phase.EXPLORING and session.result is not None
    assert session.result.expenses.budget == Decimal("250000")
    assert "Total Opex" in audit_transformations(session.intake_result)["excluded_totals"]  # type: ignore[arg-type]
    assert any("Left out 'Total Opex' at your request" in note for note in session.intake_result.visible_transformations)  # type: ignore[union-attr]
    assert response.level != "error"


def test_a_total_that_matches_is_excluded_silently_as_before() -> None:
    session = Session()
    handle_upload(session, ROUNDED.replace(b"Total Opex,Expense,251,257", b"Total Opex,Expense,250,257"), "ok.csv")
    finish_setup(session)
    assert session.result is not None and session.result.expenses.budget == Decimal("250000")


def test_the_cli_wording_is_no_longer_garbled() -> None:
    message = plain_analysis_error("Summary 'Total Opex' does not reconcile to Expense detail rows; check for missing data.")
    assert message == ("Summary total for 'Total Opex' does not match the sum of its Expense detail rows. "
                       "Please check for missing or overlapping line items.")
