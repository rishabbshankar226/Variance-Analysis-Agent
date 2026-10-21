"""Tests for wide monthly and multi-period layouts.

Verifies:
- Detecting paired Budget and Actual columns across multiple periods.
- Period selection chips in chat.
- Mapping selected period columns and pre-filling the reporting period.
- Multi-period rows filtering on a single Period column.
- Verifying Fixture e wide layout in chat.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from variance_agent.intake import (
    detect_period_pairs,
    detect_single_period_column_values,
)
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_detect_wide_monthly_period_pairs() -> None:
    headers = [
        "Account",
        "Jul-26 Budget", "Jul-26 Actual",
        "Aug-26 Budget", "Aug-26 Actual",
        "Sep-26 Budget", "Sep-26 Actual",
        "Q3 Budget", "Q3 Actual",
    ]

    pairs = detect_period_pairs(headers)
    assert len(pairs) == 4
    periods = [p.period for p in pairs]
    assert periods == ["Jul-26", "Aug-26", "Sep-26", "Q3"]

    q3_pair = next(p for p in pairs if p.period == "Q3")
    assert q3_pair.budget_column == "Q3 Budget"
    assert q3_pair.actual_column == "Q3 Actual"


def test_detect_single_period_column_values() -> None:
    rows = [
        {"line_item": "Sales", "budget": "100", "actual": "110", "period": "2026-01"},
        {"line_item": "Sales", "budget": "100", "actual": "115", "period": "2026-02"},
        {"line_item": "Sales", "budget": "100", "actual": "120", "period": "2026-03"},
    ]
    periods = detect_single_period_column_values(rows)
    assert periods == ["2026-01", "2026-02", "2026-03"]


def test_fixture_e_chat_flow_wide_monthly() -> None:
    """Fixture e in chat: detects multiple periods, offers chips, analyzes Q3."""
    session = Session()
    path = FIXTURES_DIR / "fixture_e_wide_monthly.xlsx"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)

    # In chat, wide multi-period files prompt user to pick which period to analyze
    assert session.phase == Phase.AWAITING_PERIOD_CHOICE
    assert "Found data for multiple periods" in resp_upload.text
    assert "Which period would you like to analyze?" in resp_upload.text
    assert set(resp_upload.chips or []).issuperset({"Jul-26", "Aug-26", "Sep-26", "Q3"})

    # User clicks Q3
    resp_q3 = handle_message(session, "Q3")
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Here's how I read your file:" in resp_q3.text
    assert "Analyzed period:** Q3" in resp_q3.text
    assert "Budget from 'Q3 Budget'" in resp_q3.text
    assert "Actual from 'Q3 Actual'" in resp_q3.text
    assert "Looks right" in (resp_q3.chips or [])

    # Confirm proceeds to thresholds (period already pre-filled to Q3!)
    resp_confirm = handle_message(session, "Looks right")
    assert session.phase == Phase.AWAITING_THRESHOLDS
    assert "Period set to: **Q3**" in resp_confirm.text

    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")

    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert "Analysis Complete" in resp_curr.text
    # Q3 Budget and Actual:
    # Subscription Revenue: 300,000 / 315,000
    # Consulting Revenue: 150,000 / 149,000
    # Total Revenue: 450,000 / 464,000
    assert session.result.revenue.budget == Decimal("450000")
    assert session.result.revenue.actual == Decimal("464000")
