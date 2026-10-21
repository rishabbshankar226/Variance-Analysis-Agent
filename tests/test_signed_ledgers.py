"""Tests for signed ledger detection and sign flipping.

Verifies:
- Detecting negative revenue credits / positive expense debits.
- Exact Decimal negation without float arithmetic.
- Chat flow proposing and confirming sign flip for Fixture c.
- Analysis results in positive revenue and correct favorability.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from variance_agent.intake import (
    detect_signed_ledger,
    flip_ledger_signs,
)
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_detect_signed_ledger_negative_revenue() -> None:
    rows = [
        {"line_item": "Product Revenue", "budget": Decimal("-500000"), "actual": Decimal("-520000")},
        {"line_item": "Services Revenue", "budget": Decimal("-200000"), "actual": Decimal("-190000")},
        {"line_item": "Payroll Expense", "budget": Decimal("300000"), "actual": Decimal("320000")},
        {"line_item": "Marketing Expense", "budget": Decimal("100000"), "actual": Decimal("95000")},
    ]

    detected = detect_signed_ledger(rows)
    assert detected.is_signed_ledger is True
    assert detected.negative_revenue_count == 2
    assert "Product Revenue" in detected.negative_revenue_items
    assert "Services Revenue" in detected.negative_revenue_items


def test_flip_ledger_signs_exact_decimal() -> None:
    rows = [
        {"line_item": "Product Revenue", "budget": Decimal("-500000"), "actual": Decimal("-520000")},
        {"line_item": "Services Revenue", "budget": Decimal("-200000"), "actual": Decimal("-190000")},
        {"line_item": "Payroll Expense", "budget": Decimal("300000"), "actual": Decimal("320000")},
    ]

    flipped, affected = flip_ledger_signs(rows, ["Product Revenue", "Services Revenue"])
    assert len(affected) == 2
    assert flipped[0]["budget"] == Decimal("500000")
    assert flipped[0]["actual"] == Decimal("520000")
    assert flipped[1]["budget"] == Decimal("200000")
    assert flipped[1]["actual"] == Decimal("190000")
    assert flipped[2]["budget"] == Decimal("300000")
    assert flipped[2]["actual"] == Decimal("320000")


def test_fixture_c_chat_flow_signed_ledger() -> None:
    """Fixture c in chat: detects signed ledger, proposes sign flip, completes analysis with positive revenue."""
    session = Session()
    path = FIXTURES_DIR / "fixture_c_signed_ledger.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)

    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Here's how I read your file:" in resp_upload.text
    assert "Revenue looks like it's stored as negative (credits)" in resp_upload.text
    assert "Flipped signs to positive-cost convention" in resp_upload.text
    assert "Looks right" in (resp_upload.chips or [])

    handle_message(session, "Looks right")
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")

    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert "Analysis Complete" in resp_curr.text
    # Revenue is positive now: 500k + 200k = 700k
    assert session.result.revenue.budget == Decimal("700000")
    assert session.result.revenue.actual == Decimal("710000")
    # Actual (710k) > Budget (700k) is FAVORABLE
    assert str(session.result.revenue.status) == "F"
