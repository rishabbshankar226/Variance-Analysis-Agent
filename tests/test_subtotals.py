"""Tests for subtotal and total row detection and exclusion.

Verifies:
- Reconciled contiguous block sums (subtotals) within 0.01 tolerance.
- Reconciled nested/formula totals (Gross Profit, Net Income).
- Flagging unreconciled totals for user decision.
- Clean analysis of detail rows after total exclusion for Fixture b.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from variance_agent.intake import (
    detect_subtotals_and_totals,
)
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_detect_contiguous_block_subtotals() -> None:
    rows = [
        {"line_item": "Product Revenue", "budget": Decimal("500000"), "actual": Decimal("520000")},
        {"line_item": "Service Revenue", "budget": Decimal("200000"), "actual": Decimal("190000")},
        {"line_item": "Total Revenue", "budget": Decimal("700000"), "actual": Decimal("710000")},
        {"line_item": "Cost of Goods Sold", "budget": Decimal("300000"), "actual": Decimal("310000")},
        {"line_item": "Gross Profit", "budget": Decimal("400000"), "actual": Decimal("400000")},
        {"line_item": "R&D Expense", "budget": Decimal("120000"), "actual": Decimal("125000")},
        {"line_item": "Sales & Marketing", "budget": Decimal("100000"), "actual": Decimal("115000")},
        {"line_item": "G&A Expense", "budget": Decimal("80000"), "actual": Decimal("75000")},
        {"line_item": "Total Operating Expenses", "budget": Decimal("300000"), "actual": Decimal("315000")},
        {"line_item": "Net Income", "budget": Decimal("100000"), "actual": Decimal("85000")},
    ]

    detected = detect_subtotals_and_totals(rows)
    reconciled_names = [item.line_item for item in detected.reconciled_totals]
    assert "Total Revenue" in reconciled_names
    assert "Gross Profit" in reconciled_names
    assert "Total Operating Expenses" in reconciled_names
    assert "Net Income" in reconciled_names
    assert len(detected.unreconciled_totals) == 0


def test_detect_unreconciled_total_candidate() -> None:
    rows = [
        {"line_item": "Marketing Digital", "budget": Decimal("20000"), "actual": Decimal("22000")},
        {"line_item": "Marketing Events", "budget": Decimal("30000"), "actual": Decimal("28000")},
        # Total is off by $5,000
        {"line_item": "Total Marketing", "budget": Decimal("55000"), "actual": Decimal("50000")},
    ]

    detected = detect_subtotals_and_totals(rows)
    assert len(detected.reconciled_totals) == 0
    assert len(detected.unreconciled_totals) == 1
    assert detected.unreconciled_totals[0].line_item == "Total Marketing"


def test_fixture_b_chat_flow_subtotals_exclusion() -> None:
    """Fixture b in chat: detects 4 totals, offers exclusion, completes analysis cleanly."""
    session = Session()
    path = FIXTURES_DIR / "fixture_b_departmental_subtotals.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)

    # In chat, after detecting subtotals, intake summary proposes excluding the 4 total rows
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Here's how I read your file:" in resp_upload.text
    assert "Detected 4 subtotal/total rows" in resp_upload.text
    assert "Total Revenue" in resp_upload.text
    assert "Looks right" in (resp_upload.chips or [])

    # Confirming proceeds to period
    handle_message(session, "Looks right")
    assert session.phase == Phase.AWAITING_PERIOD

    # Continue flow to analysis
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")

    # In chat, Sales & Marketing Expense contains both 'Sales' and 'Expense', so Maya classifies it
    if session.phase == Phase.RESOLVE_UNCLASSIFIED:
        resp_final = handle_message(session, "Expense")
    else:
        resp_final = resp_curr

    # Reaches EXPLORING with clean analysis!
    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert "Analysis Complete" in resp_final.text
    # Detail rows: Product Revenue (500k), Service Revenue (200k) -> Revenue budget 700k
    assert session.result.revenue.budget == Decimal("700000")
    assert session.result.revenue.actual == Decimal("710000")
