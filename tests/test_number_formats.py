"""How much an Excel number format scales what it displays (PLAN.md, R2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from variance_agent.number_formats import display_divisor, shows_percent

ONE, K, M, B = Decimal(1), Decimal(1000), Decimal(1_000_000), Decimal(1_000_000_000)
PCT = Decimal("0.01")


@pytest.mark.parametrize(("code", "value", "expected"), [
    ("General", Decimal(5), ONE),
    ("0", Decimal(5), ONE),
    ("#,##0", Decimal(5), ONE),  # grouping only
    ("#,##0.00", Decimal(5), ONE),
    ("#,##0,", Decimal(5), K),  # one scaling comma
    ("#,##0,,", Decimal(5), M),  # two
    ("#,##0,,,", Decimal(5), B),  # three
    ("0.0,", Decimal(5), K),  # after the decimals
    ('#,##0","', Decimal(5), ONE),  # a quoted comma is a literal
    ("#,##0\\,", Decimal(5), ONE),  # so is an escaped one
    (",0", Decimal(5), ONE),  # a comma before any digit is a literal
    ("[Red]#,##0,", Decimal(5), K),
    ("[$-409]#,##0,", Decimal(5), K),
    ('_(* #,##0,_);_(* (#,##0,);_(* "-"??_);_(@_)', Decimal(5), K),  # accounting, in thousands
    ('_(* #,##0,_);_(* (#,##0,);_(* "-"??_);_(@_)', Decimal(-5), K),
    ('_(* #,##0,_);_(* (#,##0,);_(* "-"??_);_(@_)', Decimal(0), ONE),  # the zero section has no digits to scale
    ("#,##0,;(#,##0)", Decimal(5), K),  # sections by sign
    ("#,##0,;(#,##0)", Decimal(-5), ONE),
    ("#,##0,;(#,##0)", Decimal(0), K),  # zero falls back to the first section
    ("0%", Decimal("0.25"), PCT),
    ("0.0%", Decimal("0.25"), PCT),
    ('0"%"', Decimal(5), ONE),  # a quoted percent sign is a literal
    ("@", Decimal(5), ONE),
])
def test_display_divisor(code: str, value: Decimal, expected: Decimal) -> None:
    assert display_divisor(code, value) == expected


@pytest.mark.parametrize("code", [
    "[>=1000]#,##0,;#,##0",  # a conditional section: Excel picks sections by the condition
    "0.00E+00",  # scientific display
    "0.0,0",  # a comma between fractional digits
    # A comma just before the decimal point: ECMA-376 calls it scaling, but LibreOffice renders
    # these unscaled as General (checked 2026-10-26), so no reading of them is trusted.
    "#,##0,.00",
    "0,.0",
])
def test_formats_this_reader_cannot_interpret(code: str) -> None:
    assert display_divisor(code, Decimal(5)) is None


@pytest.mark.parametrize(("code", "value", "expected"), [
    ("0%", Decimal(1), True), ("#,##0,", Decimal(1), False), ('0"%"', Decimal(1), False),
    ("#,##0;0%", Decimal(-1), True), ("#,##0;0%", Decimal(1), False),
])
def test_shows_percent(code: str, value: Decimal, expected: bool) -> None:
    assert shows_percent(code, value) is expected
