"""Property tests for statement shaping against an exact Fraction oracle (fictional statements).

Each case builds a random but internally consistent income statement from known line
effects (positive adds to income), prints it the way filings do (subtotals between
lines, an "other" block either added or subtracted, optional "Total" rows), then
checks what ``shape_income_statement`` recovers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction

import pytest

from variance_agent.statement_shape import shape_income_statement

CASES = 300


@dataclass
class _Case:
    rows: list[list[object]]
    effects: dict[str, list[Fraction]]  # line label -> true effect on income per period
    net: list[Fraction]  # true net income per period
    printed_figures: int


def _text(value: Fraction, places: int) -> str:
    """Print like a filing: thousands commas, parentheses for negatives."""
    scaled = round(abs(value) * 10**places)  # round half to even, as Fraction.__round__
    whole, part = divmod(scaled, 10**places)
    body = f"{whole:,}" + (f".{part:0{places}d}" if places else "")
    return f"({body})" if value < 0 else body


def _amount(text: str) -> Fraction:
    negative = text.startswith("(")
    value = Fraction(text.strip("()").replace(",", ""))
    return -value if negative else value


def _case(rng: random.Random, *, true_places: int, printed_places: int) -> _Case:
    periods = rng.choice((2, 3))

    def figure() -> list[Fraction]:
        return [Fraction(rng.randint(1, 99_999 * 10**true_places), 10**true_places)
                for _ in range(periods)]

    rows: list[list[object]] = []
    effects: dict[str, list[Fraction]] = {}

    def line(label: str, printed: list[Fraction], effect: list[Fraction]) -> None:
        rows.append([label, *(_text(v, printed_places) for v in printed)])
        effects[label] = effect

    def subtotal(label: str, value: list[Fraction]) -> None:
        rows.append([label, *(_text(v, printed_places) for v in value)])

    def add(a: list[Fraction], b: list[Fraction], sign: int = 1) -> list[Fraction]:
        return [x + sign * y for x, y in zip(a, b, strict=True)]

    zero = [Fraction(0)] * periods
    revenue = zero
    for i in range(rng.randint(1, 3)):
        value = figure()
        line(f"Product line {i + 1}", value, value)
        revenue = add(revenue, value)
    if rng.random() < 0.5:
        subtotal("Total revenue", revenue)

    costs = zero
    for i in range(rng.randint(1, 4)):
        value = figure()
        line(f"Operating cost {i + 1}", value, [-v for v in value])
        costs = add(costs, value)
    if rng.random() < 0.5:
        subtotal("Total operating expenses", costs)
    operating = add(revenue, costs, -1)
    subtotal("Operating income", operating)

    # Other items: printed with their effect's sign in a block the statement adds, or
    # with the opposite sign in a block it subtracts.
    subtracted = rng.random() < 0.5
    other_printed = zero
    other_effect = zero
    for i in range(rng.randint(1, 3)):
        effect = figure() if rng.random() < 0.5 else [-v for v in figure()]
        printed = [-e for e in effect] if subtracted else effect
        line(f"Nonoperating item {i + 1}", printed, effect)
        other_printed = add(other_printed, printed)
        other_effect = add(other_effect, effect)
    if rng.random() < 0.5:
        subtotal("Total other expense, net" if subtracted else "Total other income, net",
                 other_printed)
    before_tax = add(operating, other_effect)
    subtotal("Income before income taxes", before_tax)

    tax = figure()
    line("Income tax expense", tax, [-v for v in tax])
    net = add(before_tax, tax, -1)
    subtotal("Net income", net)

    header = ["Line Item", *(f"FY{2026 - p}" for p in range(periods))]
    return _Case([["(In millions)"], header, *rows], effects, net, len(rows))


def _check(case: _Case, *, exact: bool, unit: Fraction) -> bool:
    """Assert every label and amount the shaper produced; return True if all were labeled."""
    shaped = shape_income_statement(case.rows)
    assert shaped.rows[1][-1] == "Type"
    shaped_net = [Fraction(0)] * (len(shaped.rows[1]) - 2)
    for label, *cells, kind in shaped.rows[2:]:
        effect = case.effects[str(label)]
        if not kind:
            continue
        expected = "Revenue" if effect[0] > 0 else "Expense"
        assert kind == expected, label
        amounts = [_amount(str(c)) for c in cells]
        printed_effect = amounts if kind == "Revenue" else [-a for a in amounts]
        for got, true in zip(printed_effect, effect, strict=True):
            # The shaped amount is the printed figure with the sign settled: exact when
            # printing is exact, within half a printed unit when the filing rounded.
            assert got == true if exact else abs(got - true) <= unit / 2, label
        shaped_net = [n + e for n, e in zip(shaped_net, printed_effect, strict=True)]
    if shaped.unlabeled:
        return False
    tolerance = Fraction(0) if exact else unit * case.printed_figures / 2
    for got, true in zip(shaped_net, case.net, strict=True):
        assert abs(got - true) <= tolerance
    return True


@pytest.mark.parametrize("seed", [20261021])
def test_exact_statements_match_the_fraction_oracle(seed: int) -> None:
    rng = random.Random(seed)
    labeled = sum(_check(_case(rng, true_places=1, printed_places=1), exact=True,
                         unit=Fraction(1, 10)) for _ in range(CASES))
    assert labeled == CASES  # fixed seed; genuine ambiguity would only leave lines unlabeled


@pytest.mark.parametrize("seed", [20261022])
def test_rounded_statements_stay_within_rounding(seed: int) -> None:
    """Filings round every printed figure on its own, subtotals included."""
    rng = random.Random(seed)
    labeled = sum(_check(_case(rng, true_places=2, printed_places=1), exact=False,
                         unit=Fraction(1, 10)) for _ in range(CASES))
    assert labeled == CASES
