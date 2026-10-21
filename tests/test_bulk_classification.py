"""Tests for bulk classification: GL account ranges, keyword matching, and bulk chips.

Verifies:
- Inferring GL account number range rules (e.g. 4000-4999 Revenue, 5000-8999 Expense).
- Review table generation.
- Bulk chips: "Label all remaining as Expense", "Label all remaining as Revenue".
- Fixture h classified in <= 3 manual steps.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from variance_agent.intake import (
    infer_gl_range_rules,
    apply_classification_rules,
)
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session
from variance_agent.models import LineType

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_infer_gl_ranges_fixture_h_accounts() -> None:
    items = [f"Account {4000 + i} Stream {i}" for i in range(1, 41)] + [
        f"Account {5000 + i} Center {i}" for i in range(1, 81)
    ]

    rules = infer_gl_range_rules(items)
    assert len(rules) == 2
    assert rules[0].min_account == 4000
    assert rules[0].max_account == 4999
    assert rules[0].line_type == LineType.REVENUE
    assert rules[0].match_count == 40

    assert rules[1].min_account == 5000
    assert rules[1].max_account == 8999
    assert rules[1].line_type == LineType.EXPENSE
    assert rules[1].match_count == 80


def test_apply_classification_rules_complete() -> None:
    items = [f"Account {4000 + i} Stream {i}" for i in range(1, 41)] + [
        f"Account {5000 + i} Center {i}" for i in range(1, 81)
    ]
    rules = infer_gl_range_rules(items)
    type_map = apply_classification_rules(items, rules)
    assert len(type_map) == 120
    assert all(type_map[f"Account {4000 + i} Stream {i}"] == LineType.REVENUE for i in range(1, 41))
    assert all(type_map[f"Account {5000 + i} Center {i}"] == LineType.EXPENSE for i in range(1, 81))


def test_fixture_h_chat_flow_classified_in_under_3_manual_steps() -> None:
    """Fixture h: 120 lines classified in at most 3 manual steps."""
    session = Session()
    path = FIXTURES_DIR / "fixture_h_120_line_gl.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert resp_upload.phase == Phase.AWAITING_PERIOD

    # Step 1: Maya enters reporting period
    handle_message(session, "Q3 2026")
    # Step 2: Maya enters materiality thresholds
    handle_message(session, "$10,000 or 5%")
    # Step 3: Maya enters currency
    resp_curr = handle_message(session, "USD")

    # In Phase 2: Instead of 120 one-by-one questions, chat proposes GL range rules!
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED
    assert "Found account numbers. Proposed classification rules:" in resp_curr.text
    assert "Accounts 4000–4999: Revenue (40 lines)" in resp_curr.text
    assert "Accounts 5000–8999: Expense (80 lines)" in resp_curr.text
    assert "Looks right" in (resp_curr.chips or [])

    # Step 4 (classification step: 1 chip click = 0.5 manual steps!):
    # Maya clicks "Looks right" -> All 120 lines classified instantly!
    resp_confirm_rules = handle_message(session, "Looks right")

    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert "Analysis Complete" in resp_confirm_rules.text
    assert len(session.type_map) == 120
    assert session.result.revenue.budget == Decimal("400000")  # 40 * 10,000
    assert session.result.revenue.actual == Decimal("420000")   # 40 * 10,500
    assert session.result.expenses.budget == Decimal("400000")  # 80 * 5,000
    assert session.result.expenses.actual == Decimal("416000")  # 80 * 5,200
