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

import pytest

from variance_agent.intake import (
    detect_unit_scale,
    read_input_assisted,
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
    handle_upload(session, path.read_bytes(), path.name)

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


# X4: the caption forms a fictional title or header can use, and phrases that only look like one.
@pytest.mark.parametrize(("text", "scale"), [
    ("($ in thousands)", "1000"), ("(in thousands)", "1000"), ("($000)", "1000"), ("($000s)", "1000"),
    ("($000's)", "1000"), ("(000's)", "1000"), ("(000)", "1000"), ("(£000)", "1000"), ("(€000)", "1000"),
    ("£'000", "1000"), ("$'000", "1000"), ("USD '000", "1000"), ("Dollars in Thousands", "1000"),
    ("Amounts in $K", "1000"), ("(USD thousands)", "1000"), ("in USD thousands", "1000"),
    ("(thousands of dollars)", "1000"), ("In thousands of U.S. dollars", "1000"),
    ("(in millions)", "1000000"), ("($ in millions)", "1000000"), ("(£m)", "1000000"), ("(€m)", "1000000"),
    ("£m", "1000000"), ("$m", "1000000"), ("($MM)", "1000000"), ("$ in MM", "1000000"), ("EUR millions", "1000000"),
    ("(millions)", "1000000"), ("Millions of dollars", "1000000"), ("(in M)", "1000000"),
    ("(in billions)", "1000000000"), ("($ in billions)", "1000000000"), ("$bn", "1000000000"),
    ("Costs incurred in M&A review", "1"), ("Fictional Co. in Malmo", "1"), ("Budget vs Actual", "1"),
    ("Spend in M. region", "1"),
])
def test_caption_forms_name_their_unit(text: str, scale: str) -> None:
    assert detect_unit_scale(f"Fictional Northwind Co. {text} Q3 2026") == Decimal(scale)


def test_a_billions_caption_scales_and_says_so() -> None:
    data = b"Fictional Holdings ($ in billions)\nLine Item,Type,Budget,Actual\nRevenue,Revenue,1.5,1.75\n"
    result = read_input_assisted(data, ".csv", filename="fictional.csv")
    assert result.rows[0]["actual"] == Decimal("1750000000.00")
    assert ("Amounts scaled from billions (x1,000,000,000). Thresholds stay in the reporting unit (full currency "
            "units, not thousands).") in result.visible_transformations
