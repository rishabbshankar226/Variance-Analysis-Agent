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
from dataclasses import dataclass, field, replace
from collections import defaultdict, deque
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
def names_subtotal(label: str) -> bool:
    """Whether a printed label alone marks a subtotal for this shaper."""
    return bool(_SUBTOTAL_RE.search(label.strip()))


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
    # False when the statement could not be checked (no header row, or an unreadable figure):
    # the rows are the input unchanged, so their signs and subtotals are still unresolved.
    shaped: bool = True
    # For callers that check footing themselves (filing reads, PLAN.md R5): the data rows kept, in
    # order; each matched subtotal's data row with the (data row, weight) terms it sums; and the
    # subtotal-named lines no run of lines above added up to.
    kept: list[int] = field(default_factory=list)
    matches: list[tuple[int, list[tuple[int, int]]]] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    openings: list[int] = field(default_factory=list)  # a statement's first figure, carried in (OCI's net income)


@dataclass
class _Item:
    """One line, or a block of lines that a "Total" row sums, as the statement prints it."""

    rows: list[int]
    values: list[Decimal]
    is_group: bool = False
    total_row: int | None = None  # a group's own subtotal row


def _amount(text: object) -> Decimal | None:
    raw = str(text).strip().replace("$", "").replace("\u2212", "-").replace(" ", "")
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
    return all(abs(c - t) <= tolerance for c, t in zip(computed, target, strict=True))


def _block_start(
    pending: list[_Item], values: list[Decimal], unit: Decimal, *, any_suffix: bool
) -> int | None:
    """Where the block a subtotal sums begins, if it is the plain sum of lines above it.

    The block runs from the last summed block to the subtotal. A "Total" row may sum only
    the lines just above it ("Revenue", then costs, then "Total costs and expenses"), so
    with ``any_suffix`` it also tries shorter runs ending at it, longest first.
    """
    first = max((k + 1 for k, item in enumerate(pending) if item.is_group), default=0)
    for start in range(first, len(pending) if any_suffix else min(first + 1, len(pending))):
        block = pending[start:]
        sums = [sum((item.values[p] for item in block), Decimal(0)) for p in range(len(values))]
        if _close(sums, values, len(block) + 1, unit):
            return start
    return None


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _term(item: _Item) -> int:
    return item.total_row if item.total_row is not None else item.rows[0]


def shape_income_statement(raw_rows: list[list[object]], unit: Decimal | None = None,
                           extra_subtotals: re.Pattern[str] | None = None,
                           subtotal_rows_hint: frozenset[int] = frozenset(),
                           section_total_rows_hint: frozenset[int] = frozenset(),
                           zero_lines_signless: bool = False, openings_as_lines: bool = False,
                           keep_printed_signs: bool = False) -> ShapedStatement:
    """Label each line of an income statement by how the statement's subtotals add up.

    ``unit`` sets the rounding unit of the printed figures; by default it is the finest place any
    figure shows, as for a PDF statement printed in its caption's unit. ``extra_subtotals`` names
    more subtotal labels for one reader, ``subtotal_rows_hint`` data rows its source marks as
    totals, and ``section_total_rows_hint`` those among them that may sum just the lines above them,
    as a "Total" row does; with ``zero_lines_signless``, sign readings that differ only on lines that
    are zero in every period count as one; with ``openings_as_lines``, a subtotal-named first figure (OCI's
    net income, a lone "Total revenues") is read as a line. The PDF reader passes none, so its reading
    is unchanged.
    """
    header_at = next((i for i, row in enumerate(raw_rows) if row and row[0] == "Line Item"), None)
    if header_at is None:
        return ShapedStatement(rows=raw_rows, shaped=False)
    if "Measure" in raw_rows[header_at]:
        return _shape_with_measures(raw_rows, header_at)
    header, data = raw_rows[header_at], raw_rows[header_at + 1:]
    periods = len(header) - 1
    # Parsing runs in the policy context: an unreadable figure raises InvalidOperation, and
    # that flag must not stay behind in the caller's Decimal context.
    with financial_context():
        parsed = [[_amount(cell) for cell in row[1:1 + periods]] for row in data]
    if any(value is None for values in parsed for value in values):
        return ShapedStatement(rows=raw_rows, shaped=False)
    amounts = [[value for value in values if value is not None] for values in parsed]
    if unit is None:
        unit = min((Decimal(1).scaleb(min(v.as_tuple().exponent, 0))  # type: ignore[arg-type]
                    for values in amounts for v in values), default=Decimal(1))
    matches: list[tuple[int, list[tuple[int, int]]]] = []
    unmatched: list[str] = []
    openings: list[int] = []
    previous_total: int | None = None

    signs: dict[int, int] = {}
    subtotal_rows: list[int] = []
    pending: list[_Item] = []
    running: list[Decimal] | None = None
    with financial_context():
        for i, row in enumerate(data):
            values = amounts[i]
            label_text = str(row[0]).strip()
            opening = openings_as_lines and not pending and running is None
            if opening or not (_SUBTOTAL_RE.search(label_text) or (extra_subtotals and extra_subtotals.search(label_text))
                               or i in subtotal_rows_hint):
                pending.append(_Item([i], values))
                continue
            subtotal_rows.append(i)
            is_total = str(row[0]).strip().lower().startswith("total") or i in section_total_rows_hint
            start = _block_start(pending, values, unit, any_suffix=is_total)
            if start is not None:
                lines = [r for item in pending[start:] for r in item.rows]
                matches.append((i, [(_term(item), 1) for item in pending[start:]]))
                pending = [*pending[:start], _Item(lines, values, is_group=True, total_row=i)]
                continue
            # A running subtotal: the last one, plus or minus each line or block since.
            base = running or [Decimal(0)] * periods
            if pending and len(pending) <= _MAX_ITEMS:
                fits = [
                    combo for combo in itertools.product((1, -1), repeat=len(pending))
                    if _close([base[p] + sum((s * item.values[p] for s, item in zip(combo, pending, strict=True)),
                                             Decimal(0)) for p in range(periods)],
                              values, len(pending) + 2, unit)
                ]
                if zero_lines_signless and len(fits) > 1:
                    live = [k for k, item in enumerate(pending) if any(v != 0 for v in item.values)]
                    if len({tuple(combo[k] for k in live) for combo in fits}) == 1:
                        fits = fits[:1]  # the readings agree on every line that is not zero
                if len(fits) == 1:
                    for s, item in zip(fits[0], pending, strict=True):
                        for r in item.rows:
                            signs[r] = s
                    base_terms = [(previous_total, 1)] if previous_total is not None and running is not None else []
                    matches.append((i, [*base_terms, *((_term(item), s) for s, item in zip(fits[0], pending, strict=True))]))
                elif not fits:
                    unmatched.append(str(row[0]).strip())
            elif not pending and running is None:
                openings.append(i)
            elif not pending and running is not None and previous_total is not None:
                # A subtotal repeating the one before it (net income, then net income attributable
                # to the parent) foots on that one alone; any other value has nothing to add up from.
                if _close(running, values, 2, unit):
                    matches.append((i, [(previous_total, 1)]))
                else:
                    unmatched.append(str(row[0]).strip())
            running, pending, previous_total = values, [], i

    shaped = ShapedStatement(rows=[*raw_rows[:header_at], [*header, "Type"]], matches=matches, unmatched=unmatched,
                             openings=openings)
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
            elif keep_printed_signs and any(effects):
                # Its effect changes sign between columns (a tax expense one year, a benefit the next): the type the
                # statement's own arithmetic gives it, added or subtracted, keeps every figure as printed (Decision 42).
                kind = "Revenue" if sign > 0 else "Expense"
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
        shaped.kept.append(i)

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
        one = len(shaped.unlabeled) == 1
        shaped.notes.append(
            f"Couldn't tell from the statement's arithmetic whether {names} "
            f"{'adds to or reduces' if one else 'add to or reduce'} income; "
            f"you'll be asked to label {'it' if one else 'them'}")
    shaped.audit_notes = [*subtotal_note, *shaped.notes,
                          *(f"Labeled '{label}' as {kind.lower()}" for label, kind in labels)]
    return shaped


def _shape_with_measures(raw_rows: list[list[object]], header_at: int) -> ShapedStatement:
    """Keep non-money rows outside the unchanged monetary reconciliation."""
    header = raw_rows[header_at]
    measure_at = header.index("Measure")
    better_at = header.index("Better") if "Better" in header else None
    columns = [index for index, label in enumerate(header) if index and label not in {"Measure", "Better", "Type"}]
    data = raw_rows[header_at + 1:]
    def kind(row: list[object]) -> str:
        return str(row[measure_at]) if measure_at < len(row) and row[measure_at] else "Currency"
    reduced = [[row[0], *[row[index] if index < len(row) else "" for index in columns]]
               for row in data if row and kind(row) == "Currency"]
    money = shape_income_statement([*raw_rows[:header_at], ["Line Item", *[header[index] for index in columns]], *reduced])
    shaped_header = next(row for row in money.rows if row and row[0] == "Line Item")
    money_at = money.rows.index(shaped_header)
    mapped: dict[str, deque[list[object]]] = defaultdict(deque)
    for row in money.rows[money_at + 1:]:
        mapped[str(row[0])].append(row)
    output = [*raw_rows[:header_at], ["Line Item", *[header[index] for index in columns], "Type", "Measure", "Better"]]
    for row in data:
        if not row:
            continue
        measure = kind(row)
        better = row[better_at] if better_at is not None and better_at < len(row) else ""
        if measure == "Currency":
            if not mapped[str(row[0])]:
                continue  # the existing shaper excluded a monetary subtotal
            source = mapped[str(row[0])].popleft()
            cells = source[1:1 + len(columns)]
            line_type = source[-1] if "Type" in shaped_header else ""
        else:
            cells = [row[index] if index < len(row) else "" for index in columns]
            line_type = ""
        output.append([row[0], *cells, line_type, measure, better])
    return replace(money, rows=output)
