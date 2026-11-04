"""X7: profit lines in a signed ledger take the sign that adds up, so totals stay right (fictional data)."""

from __future__ import annotations

from decimal import Decimal

from tests.chat_helpers import analysed, ask
from variance_agent.intake import audit_transformations, read_input_assisted

PROFITABLE = b"""Line Item,Budget,Actual
Fictional Product Revenue,-500000,-540000
Fictional Service Revenue,-200000,-160000
Total Revenue,-700000,-700000
Cost of Goods Sold,220000,236000
Gross Profit,-480000,-464000
Salaries,150000,152000
Rent,30000,30000
Total Operating Expenses,180000,182000
Net Income,-300000,-282000
"""


def _read(data: bytes):  # type: ignore[no-untyped-def]
    return read_input_assisted(data, ".csv", filename="ledger.csv")


def test_profit_lines_turn_with_revenue_and_are_excluded_as_subtotals() -> None:
    result = _read(PROFITABLE)
    names = [row["line_item"] for row in result.rows]
    assert "Gross Profit" not in names and "Net Income" not in names
    assert ("Revenue looks like it's stored as negative (credits). Flipped signs to positive-cost convention for "
            "3 revenue lines and 2 profit lines (Gross Profit, Net Income).") in result.visible_transformations
    assert audit_transformations(result)["flipped_line_items"] == [
        "Fictional Product Revenue", "Fictional Service Revenue", "Total Revenue", "Gross Profit", "Net Income"]


def test_the_chat_totals_come_out_right() -> None:
    text = ask(analysed(PROFITABLE, "ledger.csv"), "summary").text
    assert "**Total Revenue:** $700,000.00 vs. $700,000.00" in text
    assert "**Total Expenses:** $418,000.00 vs. $400,000.00" in text


def test_a_loss_making_profit_line_turns_to_its_loss() -> None:
    data = b"Line Item,Budget,Actual\nFictional Revenue,-100,-90\nTotal Revenue,-100,-90\nCost of Goods Sold,150,150\nGross Profit,50,60\n"
    result = _read(data)
    assert "Gross Profit" not in [row["line_item"] for row in result.rows]
    assert "Gross Profit" in audit_transformations(result)["flipped_line_items"]


def test_a_presentation_signed_profit_line_is_kept_as_stored() -> None:
    data = PROFITABLE.replace(b"Gross Profit,-480000,-464000", b"Gross Profit,480000,464000")
    result = _read(data)
    assert "Gross Profit" not in [row["line_item"] for row in result.rows]  # adds up as stored
    assert "Gross Profit" not in audit_transformations(result)["flipped_line_items"]


def test_a_profit_line_that_adds_up_neither_way_is_turned_and_kept() -> None:
    data = PROFITABLE.replace(b"Gross Profit,-480000,-464000", b"Gross Profit,-480001,-464000")
    result = _read(data)
    gross = next(row for row in result.rows if row["line_item"] == "Gross Profit")
    assert (gross["budget"], gross["actual"]) == (Decimal("480001"), Decimal("464000"))
