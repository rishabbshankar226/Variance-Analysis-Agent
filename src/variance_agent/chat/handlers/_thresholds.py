"""Reading typed materiality thresholds.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from variance_agent.parsing import parse_decimal


_THRESHOLD_RE = re.compile(
    r"(?:(?:\$|dollar[s]?\s*[:=]?\s*)"
    r"(?P<dollar>[0-9][0-9,_.]*(?:[kKmMbB])?)"
    r"(?:"
    r"(?:\s+(?:or|and)\s+(?P<pct>[0-9][0-9,_.]*)\s*%?)"
    r"|"
    r"(?:\s*(?:/|&|,)\s*(?P<pct3>[0-9][0-9,_.]*)\s*(?:%|percent|pct))"
    r")"
    r"|"
    r"(?P<pct2>[0-9][0-9,_.]*)\s*(?:%|percent|pct)"
    r"\s*(?:or|and|/|,|&)\s*"
    r"(?:\$|dollar[s]?\s*[:=]?\s*)"
    r"(?P<dollar2>[0-9][0-9,_.]*(?:[kKmMbB])?))",
    re.IGNORECASE,
)


def _parse_threshold_amount(val_str: str, field: str) -> Decimal:
    """Parse a dollar threshold value supporting k/m/b shorthand multipliers."""
    clean = val_str.replace(",", "").replace("_", "").strip()
    multiplier = Decimal(1)
    if clean.lower().endswith("k"):
        multiplier = Decimal(1000)
        clean = clean[:-1].strip()
    elif clean.lower().endswith("m"):
        multiplier = Decimal(1000000)
        clean = clean[:-1].strip()
    elif clean.lower().endswith("b"):
        multiplier = Decimal(1000000000)
        clean = clean[:-1].strip()
    return parse_decimal(clean, field=field, line_item="Materiality") * multiplier


def _parse_threshold_text(text: str) -> tuple[Decimal, Decimal] | None:
    """Extract dollar and percent thresholds from natural text."""
    match = _THRESHOLD_RE.search(text)
    if match:
        dollar_str = match.group("dollar") or match.group("dollar2")
        pct_str = match.group("pct") or match.group("pct3") or match.group("pct2")
        if dollar_str and pct_str:
            pct_str = pct_str.replace(",", "").replace("_", "")
            try:
                dollar = _parse_threshold_amount(dollar_str, field="dollar_threshold")
                pct = parse_decimal(pct_str, field="percent_threshold", line_item="Materiality")
                return (dollar, pct / Decimal("100"))
            except (ValueError, InvalidOperation):
                return None
    return None


_SINGLE_DOLLAR_RE = re.compile(
    r"(?:(?:\$|dollar[s]?\s*[:=]?\s*)(?P<dollar>[0-9][0-9,_.]*(?:[kKmMbB])?)|(?P<dollar2>[0-9][0-9,_.]*(?:[kKmMbB])?)\s*(?:dollars?))",
    re.IGNORECASE,
)
_SINGLE_PCT_RE = re.compile(
    r"(?:(?P<pct>[0-9][0-9,_.]*)\s*%|(?:percent|percentage|pct)\s*[:=]?\s*(?P<pct2>[0-9][0-9,_.]*))",
    re.IGNORECASE,
)


def _parse_partial_threshold_text(text: str) -> tuple[Decimal | None, Decimal | None]:
    """Extract dollar and/or percent thresholds from text, supporting partial adjustments."""
    both = _parse_threshold_text(text)
    if both is not None:
        return both

    dollar: Decimal | None = None
    pct: Decimal | None = None

    d_match = _SINGLE_DOLLAR_RE.search(text)
    if d_match:
        d_str = d_match.group("dollar") or d_match.group("dollar2")
        if d_str:
            try:
                dollar = _parse_threshold_amount(d_str, field="dollar_threshold")
            except (ValueError, InvalidOperation):
                pass

    p_match = _SINGLE_PCT_RE.search(text)
    if p_match:
        p_str = p_match.group("pct") or p_match.group("pct2")
        if p_str:
            p_str = p_str.replace(",", "").replace("_", "")
            try:
                parsed_pct = parse_decimal(p_str, field="percent_threshold", line_item="Materiality")
                pct = parsed_pct / Decimal("100")
            except (ValueError, InvalidOperation):
                pass

    return (dollar, pct)
