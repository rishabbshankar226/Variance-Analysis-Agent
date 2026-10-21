"""Tests for unit detection and scaling.

Verifies:
- Detecting units from titles and headers: ($000), $000s, in thousands, (in millions).
- Exact Decimal scaling of amounts.
- Thresholds staying in reporting units.
- Verifying Fixture d with scaling in chat.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from variance_agent.intake import (
    detect_unit_scale,
    scale_rows_by_unit,
)
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_detect_unit_scale_thousands() -> None:
    assert detect_unit_scale("Operating Expense Summary ($000s) - Fictional") == Decimal("1000")
    assert detect_unit_scale("Departmental P&L (in thousands)") == Decimal("1000")
    assert detect_unit_scale("FY2026 Budget ($000)") == Decimal("1000")


def test_detect_unit_scale_millions() -> None:
    assert detect_unit_scale("Global Revenue Summary (in millions)") == Decimal("1000000")
    assert detect_unit_scale("Corporate Plan ($M)") == Decimal("1000000")


def test_detect_unit_scale_dollars_default() -> None:
    assert detect_unit_scale("Standard Ledger Export") == Decimal("1")


def test_scale_rows_by_unit_exact_decimal() -> None:
    rows = [
        {"line_item": "Salaries", "budget": Decimal("500"), "actual": Decimal("520")},
        {"line_item": "Travel", "budget": Decimal("40"), "actual": Decimal("0")},
    ]

    scaled = scale_rows_by_unit(rows, Decimal("1000"))
    assert scaled[0]["budget"] == Decimal("500000")
    assert scaled[0]["actual"] == Decimal("520000")
    assert scaled[1]["budget"] == Decimal("40000")
    assert scaled[1]["actual"] == Decimal("0")


def test_fixture_d_chat_flow_unit_scaling() -> None:
    """Fixture d in chat: detects ($000s), handles blank budgets, scales by 1,000, evaluates threshold in dollars."""
    session = Session()
    path = FIXTURES_DIR / "fixture_d_thousands_dashes_blanks.xlsx"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)

    # Step 1: Blank budget prompt
    assert session.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
    resp_confirm_blanks = handle_message(session, "Treat blank budgets as 0 (unbudgeted)")

    # Step 2: Intake summary shows unit scaling + dashes + blanks
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Amounts scaled from thousands (x1,000)" in resp_confirm_blanks.text
    assert "Thresholds stay in the reporting unit" in resp_confirm_blanks.text
    assert "Looks right" in (resp_confirm_blanks.chips or [])

    # Step 3: Proceed through period, thresholds ($10,000 or 5%), and currency
    handle_message(session, "Looks right")
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")

    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert "Analysis Complete" in resp_curr.text
    # Salaries variance: actual 520,000 - budget 500,000 = 20,000 > 10,000 dollar threshold!
    salaries_row = next(r for r in session.result.material_rows if r.line_item == "Salaries Expense")
    assert salaries_row.budget == Decimal("500000")
    assert salaries_row.actual == Decimal("520000")
    assert salaries_row.variance_dollars == Decimal("20000")
    assert salaries_row.material is True
