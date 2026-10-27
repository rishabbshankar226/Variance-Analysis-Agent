"""Limit, benchmark and target comparisons (PLAN.md R13-R15, docs/financial-rules.md).

Each row declares what its comparison means: a limit is a Max or a Min, with an optional buffer;
a benchmark row says whether Higher or Lower is better, with an optional tolerance; a target row
may give a tolerance and never takes F or U. Nothing is defaulted, so a missing declaration refuses
the row by name. The words (Breach, Near, Within; Above, Below, In line; Over, Under, On target)
describe the supplied comparison and are never advice.
"""

from __future__ import annotations

from decimal import Decimal

from .models import BasisDetails, BetterDirection, ComparisonBasis, MeasureKind
from .numeric import financial_context, ratio
from .parsing import is_missing, parse_decimal

_HUNDRED = Decimal(100)


def _optional(raw: dict[str, object], key: str, field: str, line_item: str) -> Decimal | None:
    value = raw.get(key)
    if is_missing(value):
        return None
    amount = parse_decimal(value, field=field, line_item=line_item)
    if amount < 0:
        raise ValueError(f"{line_item}: {field} must be zero or more, in the row's own unit.")
    return amount


def basis_details(raw: dict[str, object], comparison: Decimal, actual: Decimal, measure: MeasureKind,
                  basis: ComparisonBasis, better: BetterDirection | None) -> BasisDetails | None:
    """The row's outcome against its limit, benchmark or target; None for any other basis."""
    if basis not in {ComparisonBasis.LIMIT, ComparisonBasis.BENCHMARK, ComparisonBasis.TARGET}:
        return None
    name = str(raw.get("line_item", "Row"))
    with financial_context():
        difference = actual - comparison
        bps = difference * _HUNDRED if measure is MeasureKind.PERCENT else None
        if basis is ComparisonBasis.LIMIT:
            kind_value = raw.get("limit_kind")
            if is_missing(kind_value):
                raise ValueError(f"{name}: is the limit a Max or a Min? Supply Limit Kind as Max or Min.")
            kind = str(kind_value).strip().casefold()
            if kind not in {"max", "min"}:
                raise ValueError(f"{name}: Limit Kind must be Max or Min.")
            buffer = _optional(raw, "buffer", "Buffer", name)
            headroom = comparison - actual if kind == "max" else actual - comparison
            utilization = None if comparison == 0 else ratio(actual, comparison)
            share = None if comparison == 0 else ratio(headroom, abs(comparison))
            if headroom < 0:
                outcome, severity = "Breach", 0
            elif headroom == 0:
                outcome, severity = "At limit", 1  # the owner's call at STOP 2 (Decision 38); section 3 said Within
            elif buffer is not None and headroom <= buffer:
                outcome, severity = "Near", 2
            else:
                outcome, severity = "Within", 3
            return BasisDetails("limit", outcome, difference, bps, kind.title(), buffer, headroom, utilization,
                                severity=severity, headroom_percent=share)
        tolerance = _optional(raw, "tolerance", "Tolerance", name)
        in_line = abs(difference) <= tolerance if tolerance is not None else difference == 0
        if basis is ComparisonBasis.BENCHMARK:
            if better is None:
                raise ValueError(f"{name}: is Higher or Lower better against the benchmark? Supply Better as Higher or Lower.")
            outcome = "In line" if in_line else "Higher than benchmark" if difference > 0 else "Lower than benchmark"
            return BasisDetails("benchmark", outcome, difference, bps, tolerance=tolerance)
        if better is not None:
            raise ValueError(f"{name}: a target is neutral, so it takes no Better direction; remove Better for this row.")
        outcome = "On target" if in_line else "Over" if difference > 0 else "Under"
        return BasisDetails("target", outcome, difference, bps, tolerance=tolerance)
