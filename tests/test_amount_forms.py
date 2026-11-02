"""Printed amount forms recognised when reading PDF statements and assisted CSV/Excel cells."""

from __future__ import annotations

from decimal import Decimal

import pytest

from variance_agent.intake import parse_assisted_decimal
from variance_agent.pdf_tables import _is_amount
from variance_agent.statement_shape import _amount


@pytest.mark.parametrize(
    "text",
    ["1,234", "-1,234", "−1,234", "$1,234", "(1,234)", "($1,234)", "$(1,234)", "(5.0)%", "12.5%",
     "—", "–", "-", "$—", "(—)"],
)
def test_pdf_amount_forms_are_recognised(text: str) -> None:
    assert _is_amount(text)


@pytest.mark.parametrize("text", ["(1,234", "1,234)", "1,23", "abc", "", "(", "$", "12abc", "(1,234)(1)"])
def test_unbalanced_or_unreadable_forms_are_not_amounts(text: str) -> None:
    assert not _is_amount(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("$(1,234)", Decimal("-1234")), ("($1,234)", Decimal("-1234")), ("− 1,234", Decimal("-1234")),
     ("(1,234)", Decimal("-1234")), ("$1,234", Decimal("1234"))],
)
def test_statement_shaper_reads_the_same_forms(text: str, expected: Decimal) -> None:
    assert _amount(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [("$(1,234)", Decimal("-1234")), ("$ (1,234.50)", Decimal("-1234.50")), ("€(99)", Decimal("-99"))],
)
def test_assisted_cells_accept_currency_before_parentheses(text: str, expected: Decimal) -> None:
    value, _ = parse_assisted_decimal(text, field="Actual", line_item="x")
    assert value == expected


def test_currency_before_parentheses_still_respects_the_reporting_currency() -> None:
    with pytest.raises(ValueError, match="conflicts with reporting currency"):
        parse_assisted_decimal("€(99)", field="Actual", line_item="x", currency="USD")


# A footnote mark folds into digits under NFKC ("950¹" would read 9501), so it is refused, never read.
@pytest.mark.parametrize("text", ["950¹", "¹950", "9²50", "950₁", "①", "⑩", "950⑴", "950⒈"])
def test_a_footnote_mark_beside_an_amount_is_refused_not_read_as_a_digit(text: str) -> None:
    with pytest.raises(ValueError, match="has a footnote mark or small digit") as raised:
        parse_assisted_decimal(text, field="Actual", line_item="Product Revenue")
    assert text in str(raised.value)


@pytest.mark.parametrize(("text", "expected"), [("９５０", Decimal("950")), ("950", Decimal("950")),
                                                ("(１,２３４)", Decimal("-1234"))])
def test_full_width_digits_still_fold_into_the_amount(text: str, expected: Decimal) -> None:
    value, _ = parse_assisted_decimal(text, field="Actual", line_item="Product Revenue")
    assert value == expected


def test_a_footnote_mark_stops_intake_naming_the_cell_and_the_mark() -> None:
    from variance_agent.intake import read_input_assisted

    data = "Line Item,Type,Budget,Actual\nProduct Revenue,Revenue,900,950¹\nStaff Costs,Expense,800,820\n"
    result = read_input_assisted(data.encode("utf-8"), ".csv", filename="fictional.csv")
    assert result.has_fatal_errors
    assert result.fatal_error_message is not None
    assert "Row 2, Product Revenue, Actual column: '950¹' has a footnote mark (¹) next to the amount" in (
        result.fatal_error_message)
    assert not result.rows
