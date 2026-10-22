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
