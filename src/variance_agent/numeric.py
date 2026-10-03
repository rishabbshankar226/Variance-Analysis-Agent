"""Deterministic decimal arithmetic with explicit precision-loss failures."""

from contextlib import contextmanager
from decimal import (
    Context,
    Decimal,
    DecimalException,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Underflow,
    localcontext,
)

NUMERIC_POLICY_ID = "decimal-50-half-even-e999-v1"


@contextmanager
def financial_context():
    # Construct a fresh context: never inherit caller precision, rounding or traps.
    policy = Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999,
        Emax=999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow, Underflow, Inexact],
    )
    with localcontext(policy) as context:
        try:
            yield context
        except DecimalException as exc:
            raise ValueError(
                "Financial calculation exceeds the supported decimal precision or range "
                "(50 significant digits; exponent limits -999 to 999). "
                "Reduce input precision or rescale the dataset consistently."
            ) from exc


def ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Ratios may repeat; rounding them must never drive materiality decisions."""
    with localcontext() as context:
        context.traps[Inexact] = False
        return numerator / denominator
