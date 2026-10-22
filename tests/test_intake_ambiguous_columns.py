"""Assisted intake must not silently pick one of several candidate columns."""

from __future__ import annotations

from decimal import Decimal

import pytest

from variance_agent.intake import IntakeResult, read_input_assisted


def _read(text: str) -> IntakeResult:
    return read_input_assisted(text.encode("utf-8"), ".csv", filename="t.csv")


def test_repeated_budget_and_actual_columns_stop_the_read() -> None:
    res = _read("Line Item,Type,Budget,Actual,Budget,Actual\nRent,Expense,100,90,200,210\n")
    assert res.has_fatal_errors
    message = res.fatal_error_message or ""
    assert "more than one" in message
    assert "column D" in message and "column F" in message  # where the repeats are


def test_actual_and_actual_ytd_are_ambiguous() -> None:
    res = _read("Line Item,Type,Budget,Actual,Actual YTD\nRent,Expense,100,90,900\n")
    assert res.has_fatal_errors
    assert "more than one Actual column" in (res.fatal_error_message or "")
    assert res.comparison_candidates == ["Actual (column D)", "Actual YTD (column E)"]


def test_single_columns_are_unaffected() -> None:
    res = _read("Line Item,Type,Budget,Actual\nRent,Expense,100,90\n")
    assert not res.has_fatal_errors
    assert res.rows[0]["actual"] == Decimal("90")


CATEGORY_FIRST = (
    "Category,Account Description,Type,Budget,Actual\n"
    "Revenue,Product Sales,Revenue,100,120\nExpense,Rent,Expense,50,60\n"
)
CATEGORY_LAST = (
    "Account Description,Category,Type,Budget,Actual\n"
    "Product Sales,Revenue,Revenue,100,120\nRent,Expense,Expense,50,60\n"
)


@pytest.mark.parametrize("text", [CATEGORY_FIRST, CATEGORY_LAST])
def test_account_name_beats_a_grouping_category_column(text: str) -> None:
    res = _read(text)
    assert not res.has_fatal_errors
    assert [r["line_item"] for r in res.rows] == ["Product Sales", "Rent"]


def test_category_alone_is_still_the_line_item() -> None:
    res = _read("Category,Budget,Actual\nRent,100,90\n")
    assert [r["line_item"] for r in res.rows] == ["Rent"]


def test_a_column_that_merely_contains_act_is_not_the_actual() -> None:
    res = _read("Line Item,Budget,Contract Value,Actual\nRent,100,5000,90\n")
    assert not res.has_fatal_errors
    assert res.rows[0]["actual"] == Decimal("90")


def test_repeated_budget_columns_are_named_with_their_positions() -> None:
    res = _read("Line Item,Type,Budget,Budget,Actual\nRent,Expense,100,200,90\n")
    assert res.has_fatal_errors
    assert "budget column (Budget (column C), Budget (column D))" in (res.fatal_error_message or "")


def test_budget_and_plan_are_synonyms_and_the_first_is_used() -> None:
    res = _read("Line Item,Type,Budget,Plan,Actual\nRent,Expense,100,200,90\n")
    assert not res.has_fatal_errors
    assert res.rows[0]["budget"] == Decimal("100")


def test_period_pair_ignores_headers_that_merely_contain_act_or_plan() -> None:
    from variance_agent.intake import detect_period_pairs

    pairs = detect_period_pairs([
        "Actual Q3 2026", "Contract Value Q3 2026", "Planning Notes Q3 2026", "Budget Q3 2026",
    ])
    assert [(p.budget_column, p.actual_column) for p in pairs] == [("Budget Q3 2026", "Actual Q3 2026")]
