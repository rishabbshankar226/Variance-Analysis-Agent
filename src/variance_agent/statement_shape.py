"""Shape a published income statement into revenue and expense lines.

A filing prints subtotals (Gross profit, Operating income, Net income) between its
lines, and signs each line by how the statement adds up rather than by what it is:
one filing prints interest expense as (343) in a block it adds, another prints other
income as (106) in a block it subtracts. This walks the statement top to bottom,
checks every subtotal against the lines above it, and from that arithmetic labels
each line Revenue (it adds to income) or Expense (it reduces income). Lines the
arithmetic cannot settle stay unlabeled so the user is asked. Amounts stay exact
Decimals; only a line whose printed sign disagrees with its label is flipped.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .numeric import financial_context

_SUBTOTAL_RE = re.compile(
    r"^total\b"
    r"|^gross\s+(?:profit|margin)\b"
    r"|^operating\s+(?:income|loss|profit)(?:\s*\(loss\))?$"
    r"|^(?:income|earnings|loss|profit)(?:\s*\(loss\))?\s+(?:from\s+operations|before)\b"
    r"|^net\s+(?:income|earnings|loss|profit)(?:\s*\(loss\))?$"
    r"|^(?:other\s+)?comprehensive\s+(?:income|loss)\b",
    re.IGNORECASE,
)
_REVENUE_WORDS = re.compile(r"\b(?:revenues?|sales|income|gains?)\b", re.IGNORECASE)
_EXPENSE_WORDS = re.compile(
    r"\b(?:expenses?|costs?|charges?|tax(?:es)?|provision|depreciation|amortization"
    r"|impairments?|losses?)\b",
    re.IGNORECASE,
)
_DASHES = {"-", "–", "—", ""}
_MAX_ITEMS = 16  # sign combinations searched per subtotal: 2**16


@dataclass
class ShapedStatement:
    """Rows ready for intake (subtotals removed, a Type column added) and what changed."""

    rows: list[list[object]]
    subtotals: list[str] = field(default_factory=list)
    unlabeled: list[str] = field(default_factory=list)
    flipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # shown to the user
    audit_notes: list[str] = field(default_factory=list)  # subtotals, notes and every label


@dataclass
class _Item:
    """One line, or a block of lines that a "Total" row sums, as the statement prints it."""

    rows: list[int]
    values: list[Decimal]
    is_group: bool = False


def _amount(text: object) -> Decimal | None:
    raw = str(text).strip().replace("$", "")
    if raw in _DASHES:
        return Decimal(0)
    negative = raw.startswith("(") and raw.endswith(")")
    core = raw.strip("()").replace(",", "")
    if core.startswith("-"):
        negative, core = not negative, core[1:]
    try:
        value = Decimal(core)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return -value if negative else value


def _text(value: Decimal) -> str:
    return format(value, ",")


def _close(computed: list[Decimal], target: list[Decimal], terms: int, unit: Decimal) -> bool:
    """Equal within the rounding of `terms` independently rounded printed figures."""
    tolerance = unit * terms / 2
    return all(abs(c - t) <= tolerance for c, t in zip(computed, target))


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def shape_income_statement(raw_rows: list[list[object]]) -> ShapedStatement:
    """Label each line of an income statement by how the statement's subtotals add up."""
    header_at = next((i for i, row in enumerate(raw_rows) if row and row[0] == "Line Item"), None)
    if header_at is None:
        return ShapedStatement(rows=raw_rows)
    header, data = raw_rows[header_at], raw_rows[header_at + 1:]
    periods = len(header) - 1
    parsed = [[_amount(cell) for cell in row[1:1 + periods]] for row in data]
    if any(value is None for values in parsed for value in values):
        return ShapedStatement(rows=raw_rows)
    amounts = [[value for value in values if value is not None] for values in parsed]
    unit = min((Decimal(1).scaleb(min(v.as_tuple().exponent, 0))  # type: ignore[arg-type]
                for values in amounts for v in values), default=Decimal(1))

    signs: dict[int, int] = {}
    subtotal_rows: list[int] = []
    pending: list[_Item] = []
    running: list[Decimal] | None = None
    with financial_context():
        for i, row in enumerate(data):
            values = amounts[i]
            if not _SUBTOTAL_RE.search(str(row[0]).strip()):
                pending.append(_Item([i], values))
                continue
            subtotal_rows.append(i)
            # A block total: the plain sum of the lines since the last block.
            start = max((k + 1 for k, item in enumerate(pending) if item.is_group), default=0)
            block = pending[start:]
            sums = [sum((item.values[p] for item in block), Decimal(0)) for p in range(periods)]
            if block and _close(sums, values, len(block) + 1, unit):
                lines = [r for item in block for r in item.rows]
                pending = [*pending[:start], _Item(lines, values, is_group=True)]
                continue
            # A running subtotal: the last one, plus or minus each line or block since.
            base = running or [Decimal(0)] * periods
            if pending and len(pending) <= _MAX_ITEMS:
                fits = [
                    combo for combo in itertools.product((1, -1), repeat=len(pending))
                    if _close([base[p] + sum((s * item.values[p] for s, item in zip(combo, pending)),
                                             Decimal(0)) for p in range(periods)],
                              values, len(pending) + 2, unit)
                ]
                if len(fits) == 1:
                    for s, item in zip(fits[0], pending):
                        for r in item.rows:
                            signs[r] = s
            running, pending = values, []

    shaped = ShapedStatement(rows=[*raw_rows[:header_at], [*header, "Type"]])
    labels: list[tuple[str, str]] = []
    flips: list[str] = []
    for i, row in enumerate(data):
        label = str(row[0])
        if i in subtotal_rows:
            shaped.subtotals.append(label)
            continue
        cells = list(row[1:1 + periods])
        sign = signs.get(i)
        kind = ""
        if sign is not None:
            effects = [sign * v for v in amounts[i]]
            if all(e >= 0 for e in effects) and any(e > 0 for e in effects):
                kind = "Revenue"
            elif all(e <= 0 for e in effects) and any(e < 0 for e in effects):
                kind = "Expense"
            elif _REVENUE_WORDS.search(label):
                kind = "Revenue"
            elif _EXPENSE_WORDS.search(label):
                kind = "Expense"
            elif any(effects):
                kind = "Revenue"  # a signed "net" line: positive adds to income
            if kind:
                new = effects if kind == "Revenue" else [-e for e in effects]
                if new != amounts[i]:
                    cells = [_text(v) for v in new]
                    shaped.flipped.append(label)
                    verb = "subtracts" if kind == "Revenue" else "adds"
                    noun = "income" if kind == "Revenue" else "an expense"
                    flips.append(f"Read '{label}' as {noun}: the statement prints it as "
                                 f"{row[1]} and {verb} it")
                labels.append((label, kind))
        if not kind:
            shaped.unlabeled.append(label)
        shaped.rows.append([label, *cells, kind])

    # Intake already lists excluded subtotals in its summary; the audit gets them here too.
    subtotal_note = (
        [f"Left out {_plural(len(shaped.subtotals), 'subtotal')} the statement computes from "
         f"the lines above: {', '.join(shaped.subtotals)}"] if shaped.subtotals else [])
    revenue = sum(kind == "Revenue" for _, kind in labels)
    if labels:
        shaped.notes.append(
            f"Labeled {_plural(revenue, 'line')} revenue and "
            f"{_plural(len(labels) - revenue, 'line')} expense from how the statement adds up")
    shaped.notes.extend(flips)
    if shaped.unlabeled:
        names = ", ".join(f"'{name}'" for name in shaped.unlabeled)
        shaped.notes.append(
            f"Couldn't tell from the statement's arithmetic whether {names} add to or reduce "
            f"income; you'll be asked to label {'it' if len(shaped.unlabeled) == 1 else 'them'}")
    shaped.audit_notes = [*subtotal_note, *shaped.notes,
                          *(f"Labeled '{label}' as {kind.lower()}" for label, kind in labels)]
    return shaped
