"""X43: an amount shows the decimal places its value needs, at least two, never a scaled value's trailing zeros."""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.measures import format_measure
from variance_agent.models import MeasureKind


@pytest.mark.parametrize(("value", "kind", "shown"), [
    ("89999.000", MeasureKind.CURRENCY, "$89,999.00"),  # 89.999 scaled by a thousands caption
    ("89999.0005", MeasureKind.CURRENCY, "$89,999.0005"),  # a fourth place the value needs stays
    ("89999.00", MeasureKind.CURRENCY, "$89,999.00"),
    ("89999.1", MeasureKind.CURRENCY, "$89,999.10"),
    ("1.230", MeasureKind.PER_SHARE, "$1.23/sh"),
    ("1.2345", MeasureKind.PER_SHARE, "$1.2345/sh"),
    ("0.000", MeasureKind.CURRENCY, "$0.00"),
    ("-10.500", MeasureKind.CURRENCY, "-$10.50"),
    ("1E+3", MeasureKind.CURRENCY, "$1,000.00"),
])
def test_an_amount_shows_the_places_its_value_needs(value: str, kind: MeasureKind, shown: str) -> None:
    text = format_measure(Decimal(value), kind)
    assert text == shown
    # Nothing is rounded: the figure shown is the stored value.
    figure = text.replace("$", "").replace(",", "").removesuffix("/sh")
    assert Fraction(figure) == Fraction(value)


def test_a_captioned_limit_rows_amounts_show_cents(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "desk.csv"
    source.write_text("Fictional Desk ($ in thousands)\n\nLine Item,Actual,Limit,Limit Kind,Buffer\n"
                      "Fictional desk exposure,89.999,100,Max,10\n", encoding="utf-8")
    code = cli.main([str(source), "--assisted", "--compare-to", "limit", "--period", "Q3 2026",
                     "--dollar-threshold", "1", "--percent-threshold", "1"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    line = next(row for row in captured.out.splitlines() if row.startswith("| Fictional"))
    assert line == ("| Fictional desk exposure | Max | $100,000.00 | $89,999.00 | $10,001.00 | 10.0% | 90.0% | $10,000.00 "
                    "| Within |")
