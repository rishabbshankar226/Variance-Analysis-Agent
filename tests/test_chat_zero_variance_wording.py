"""The executive TL;DR must not call a zero variance a beat, a saving or an outperformance."""

from __future__ import annotations

from chat_helpers import analysed, ask

ON_PLAN = b"""Line Item,Type,Budget,Actual
Product Sales,Revenue,100000,100000
Payroll,Expense,60000,60000
"""
REVENUE_ONLY_ON_PLAN = b"""Line Item,Type,Budget,Actual
Product Sales,Revenue,100000,100000
Payroll,Expense,60000,63000
"""
EXPENSES_ONLY_ON_PLAN = b"""Line Item,Type,Budget,Actual
Product Sales,Revenue,100000,104000
Payroll,Expense,60000,60000
"""


def _tldr(csv_bytes: bytes) -> str:
    return ask(analysed(csv_bytes), "tldr").text


def test_everything_on_plan_is_said_plainly() -> None:
    text = _tldr(ON_PLAN)
    assert "$0.00 beat" not in text and "$0.00 shortfall" not in text
    assert "outperformed" not in text and "underperformed" not in text
    assert "overspent by $0.00" not in text and "savings of $0.00" not in text
    assert "exactly on plan" in text or "exactly on the" in text or "exactly matching" in text


def test_revenue_on_plan_is_not_an_outperformance() -> None:
    text = _tldr(REVENUE_ONLY_ON_PLAN)
    assert "outperformed plan by $0.00" not in text
    assert "revenue came in exactly on plan" in text
    assert "overspent by $3,000.00" in text


def test_expenses_on_plan_are_not_savings() -> None:
    text = _tldr(EXPENSES_ONLY_ON_PLAN)
    assert "generated savings of $0.00" not in text
    assert "operating expenses came in exactly on plan" in text
    assert "outperformed plan by $4,000.00" in text
