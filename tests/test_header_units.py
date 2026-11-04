"""X23: an amount heading may end in a unit or currency, which is read, not a reason to refuse (fictional data)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from variance_agent.intake import CanonicalRole, currency_conflict, match_column_synonym, read_input_assisted


@pytest.mark.parametrize("budget", ["Budget ($000)", "Budget $000", "Budget ($K)", "Budget (in thousands)",
                                    "Budget ($ in thousands)", "Budget $", "Budget (USD)"])
def test_a_qualified_budget_heading_is_the_budget(budget: str) -> None:
    assert match_column_synonym(budget)[0] is CanonicalRole.BUDGET


def test_a_qualified_actual_heading_is_the_actual() -> None:
    assert match_column_synonym("Actual (000s)")[0] is CanonicalRole.ACTUAL


def test_a_period_in_parentheses_is_not_a_qualifier() -> None:
    assert match_column_synonym("Budget (Q3)")[0] is CanonicalRole.UNKNOWN


def _read(header: str):  # type: ignore[no-untyped-def]
    data = f"Line Item,{header},Actual {header.split(' ', 1)[1]}\nFictional Sales,250,275\n".encode("utf-8")
    return read_input_assisted(data, ".csv", filename="units.csv")


def test_a_thousands_heading_scales_the_amounts() -> None:
    result = _read("Budget ($000)")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal("250000"), Decimal("275000"))
    assert any(note.startswith("Amounts scaled from thousands") for note in result.visible_transformations)


def test_a_currency_heading_reads_unscaled_and_must_match_the_reporting_currency() -> None:
    result = _read("Budget (USD)")
    assert not result.has_fatal_errors and result.rows[0]["budget"] == Decimal("250")
    assert currency_conflict(result, "USD", "units.csv") is None
    conflict = currency_conflict(result, "EUR", "units.csv")
    assert conflict is not None and "the 'Budget (USD)' column heading" in conflict[0]
