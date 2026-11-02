"""C3: a one-unit line beside a zero has a sign the printed figures can't tell, so the shaper refuses (fictional)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from variance_agent.statement_shape import shape_income_statement

PRE_TAX = 6  # the data row of "Income before income taxes"


def _rows(prior_pretax: str, prior_other: str) -> list[list[object]]:
    return [["Line Item", "FY2026", "FY2025"],
            ["Fictional net revenues", "900", "800"], ["Fictional costs", "600", "550"],
            ["Operating income", "300", "250"],
            ["Other expense, net", "0", prior_other], ["Interest expense", "(40)", "(20)"], ["Interest income", "6", "4"],
            ["Income before income taxes", "266", prior_pretax]]


@pytest.mark.parametrize(("pretax", "other"), [("234", "(1)"), ("233", "(1)")], ids=["one-unit-gap", "no-gap"])
def test_a_one_unit_line_beside_a_zero_leaves_two_readings(pretax: str, other: str) -> None:
    """Added or subtracted, the (1) line lands within the rounding of five printed figures (R5): no guess."""
    shaped = shape_income_statement(_rows(pretax, other), Decimal(1))
    assert PRE_TAX not in [row for row, _ in shaped.matches]


def test_a_larger_line_has_one_reading() -> None:
    shaped = shape_income_statement(_rows("229", "(5)"), Decimal(1))
    assert (PRE_TAX, [(2, 1), (3, 1), (4, 1), (5, 1)]) in shaped.matches
