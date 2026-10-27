"""Footing and identities for balance sheets and cash flow statements read from filings (PLAN.md R9).

Each figure stands for the interval its ``decimals`` states (XBRL Calculations 1.1, as R5 applies
it to income statements). A subtotal must equal the plain sum of a run of lines and earlier
subtotals ending just above it, longest run first, or the same run with lines labeled "Less ..."
subtracted. Unlike an income statement, a balance sheet restarts at each section, so no subtotal is
checked against the one before it. Then the statement's identity must hold in every column: total
assets against total liabilities and equity, or ending cash against beginning cash plus the flows
printed between them. Anything that does not hold is a refusal, never a figure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .numeric import financial_context

Figure = tuple[Decimal, str]  # the displayed value and its decimals

_TOTAL_LABEL = re.compile(
    r"^total\b|^net\s+cash\b|^(?:net\s+)?(?:\(\s*)?(?:increase|decrease|change)\b[^.]*?\bin\s+cash\b", re.IGNORECASE)
_TOTAL_CONCEPT = re.compile(
    r"^us-gaap:(?:Assets|AssetsCurrent|AssetsNoncurrent|Liabilities|LiabilitiesCurrent|LiabilitiesNoncurrent"
    r"|LiabilitiesAndStockholdersEquity|StockholdersEquity|StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    r"|NetCashProvidedByUsedIn(?:Operating|Investing|Financing)Activities(?:ContinuingOperations)?"
    r"|\w*PeriodIncreaseDecrease\w*)$")
_DISCONTINUED = re.compile(r"discontinued", re.IGNORECASE)
_LESS = re.compile(r"^less\b", re.IGNORECASE)
_TOTAL_ASSETS = re.compile(r"^total\s+assets$", re.IGNORECASE)
_TOTAL_LIABILITIES_AND_EQUITY = re.compile(
    r"^total\s+liabilities\b.*\b(?:and|&)\b.*\b(?:equity|deficit|deficiency|capital)\b", re.IGNORECASE)
_REFUSE_FIX = "Choose another statement from this filing."


@dataclass(frozen=True)
class CheckLine:
    name: str
    concept: str
    figures: tuple[Figure | None, ...]  # by column; None where the line prints nothing
    balance: str = ""  # "beginning" or "ending" cash on a cash flow statement (R8)


@dataclass
class Checked:
    closing: int | None = None  # the statement's last line; lines after it are supplemental
    matches: list[tuple[int, list[tuple[int, int]]]] = field(default_factory=list)  # subtotal, (term, weight)
    identity: str = ""  # the identity that held, in words
    problem: str = ""  # why the statement is refused


def half_width(decimals: str) -> Decimal:
    """Half the rounding interval a fact's `decimals` states (XBRL Calculations 1.1, 5.2.3)."""
    if decimals.strip().upper() == "INF" or not re.fullmatch(r"-?\d+", decimals.strip()):
        return Decimal(0)
    return Decimal("0.5").scaleb(-int(decimals))


def _foots(terms: list[tuple[Figure | None, int]], total: Figure | None) -> bool:
    """The weighted terms' intervals, summed, overlap the total's (closed intervals)."""
    if total is None or not terms or any(figure is None for figure, _ in terms):
        return False
    with financial_context():
        centre = sum((figure[0] * weight for figure, weight in terms if figure is not None), Decimal(0))
        spread = sum((half_width(figure[1]) for figure, _ in terms if figure is not None), Decimal(0)) + half_width(total[1])
        return abs(centre - total[0]) <= spread


def _strong_total(line: CheckLine) -> bool:
    if line.balance == "ending":
        return True
    if _DISCONTINUED.search(line.name) or _DISCONTINUED.search(line.concept):
        return False
    return bool(_TOTAL_LABEL.search(line.name) or _TOTAL_CONCEPT.match(line.concept))


def _contra(line: CheckLine) -> bool:
    """A line printed to be subtracted: labeled "Less ...", or negative wherever it prints a figure."""
    values = [figure[0] for figure in line.figures if figure is not None]
    return bool(_LESS.match(line.name)) or (bool(values) and all(v <= 0 for v in values) and any(v < 0 for v in values))


def _run(lines: list[CheckLine], items: list[int], total: int, starts: range) -> tuple[int, list[int]] | None:
    """The first run of items from one of ``starts`` that foots to ``total`` in every column, with its weights."""
    for start in starts:
        run = items[start:]
        plain = [1] * len(run)
        less = [-1 if run_item not in _groups(lines, items) and _LESS.match(lines[run_item].name) else 1 for run_item in run]
        for weights in (plain, less) if less != plain else (plain,):
            if all(_foots([(lines[item].figures[column], weight) for item, weight in zip(run, weights, strict=True)],
                          lines[total].figures[column]) for column in range(len(lines[total].figures))):
                return start, weights
    return None


def _groups(lines: list[CheckLine], items: list[int]) -> set[int]:
    return {item for item in items if _strong_total(lines[item])}


def _foot(lines: list[CheckLine], closing: int, statement: str) -> tuple[list[tuple[int, list[tuple[int, int]]]], str]:
    items: list[int] = []
    matches: list[tuple[int, list[tuple[int, int]]]] = []
    grouped: set[int] = set()
    for i in range(closing + 1):
        strong = _strong_total(lines[i])
        # A net line just after its gross line and contra line (cost less accumulated depreciation)
        # sums those two; if it does not, it is a line of its own.
        weak = (not strong and len(items) >= 2 and items[-2:] == [i - 2, i - 1]
                and not grouped & {i - 2, i - 1} and _contra(lines[i - 1]))
        if not strong and not weak:
            items.append(i)
            continue
        found = _run(lines, items, i, range(len(items)) if strong else range(len(items) - 2, len(items) - 1))
        if found is None:
            if weak:
                items.append(i)
                continue
            return matches, (f"I couldn't tell which lines '{lines[i].name}' adds up in the {statement}, so I can't "
                             f"check it and stopped instead of guessing. {_REFUSE_FIX}")
        start, weights = found
        matches.append((i, list(zip(items[start:], weights, strict=True))))
        items = [*items[:start], i]
        grouped.add(i)
    return matches, ""


def _dollars(value: Decimal) -> str:
    whole = abs(value) == abs(value).to_integral_value()
    text = format(abs(value).quantize(Decimal(1)) if whole else abs(value), ",f")
    return ("-" if value < 0 else "") + "$" + text


def _columns(columns: list[str]) -> str:
    return columns[0] if len(columns) == 1 else ", ".join(columns[:-1]) + " and " + columns[-1]


def _within(terms: set[int], target: int, matches: dict[int, list[tuple[int, int]]]) -> bool:
    """Whether ``target`` is among the lines a subtotal sums, directly or through its subtotals."""
    return any(term == target or (term in matches and _within({t for t, _ in matches[term]}, target, matches))
               for term in terms)


def check_balance_sheet(lines: list[CheckLine], statement: str, columns: list[str]) -> Checked:
    """R9 for a balance sheet: every subtotal foots, and total assets equal total liabilities and equity."""
    assets = next((i for i, line in enumerate(lines)
                   if line.concept == "us-gaap:Assets" or _TOTAL_ASSETS.match(line.name)), None)
    claims = next((i for i, line in enumerate(lines) if line.concept == "us-gaap:LiabilitiesAndStockholdersEquity"
                   or _TOTAL_LIABILITIES_AND_EQUITY.match(line.name)), None)
    if assets is None or claims is None:
        return Checked(problem=(f"I couldn't find both total assets and total liabilities and equity in the {statement}, "
                                f"so I can't check that it balances and stopped instead of guessing. {_REFUSE_FIX}"))
    closing = max(assets, claims)
    matches, problem = _foot(lines, closing, statement)
    if problem:
        return Checked(closing, matches, problem=problem)
    for column, label in enumerate(columns):
        left, right = lines[assets].figures[column], lines[claims].figures[column]
        if not _foots([(left, 1)], right):
            shown = [_dollars(figure[0]) if figure is not None else "blank" for figure in (left, right)]
            return Checked(closing, matches, problem=(
                f"In the {statement}, {lines[assets].name} ({shown[0]}) and {lines[claims].name} ({shown[1]}) differ by "
                f"more than their rounding in {label}, so I stopped instead of guessing. {_REFUSE_FIX}"))
    return Checked(closing, matches, identity=(
        f"{lines[assets].name} equals {lines[claims].name} in {_columns(columns)}, within the rounding each figure's "
        "decimals state"))


def check_cash_flow(lines: list[CheckLine], statement: str, columns: list[str]) -> Checked:
    """R9 for a cash flow statement: every subtotal foots, and ending cash rolls forward from beginning cash."""
    ending = next((i for i, line in enumerate(lines) if line.balance == "ending"), None)
    beginning = next((i for i, line in enumerate(lines) if line.balance == "beginning"
                      and (ending is None or i < ending)), None)
    if ending is None or beginning is None:
        return Checked(problem=(f"I couldn't find the beginning and ending cash balances in the {statement}, so I can't "
                                f"check that cash rolls forward and stopped instead of guessing. {_REFUSE_FIX}"))
    matches, problem = _foot(lines, ending, statement)
    if problem:
        return Checked(ending, matches, problem=problem)
    by_total = dict(matches)
    if not _within({t for t, _ in by_total[ending]}, beginning, by_total):
        return Checked(ending, matches, problem=(
            f"In the {statement}, {lines[ending].name} does not roll forward from {lines[beginning].name}, so I stopped "
            f"instead of guessing. {_REFUSE_FIX}"))
    return Checked(ending, matches, identity=(
        f"Ending cash equals beginning cash plus the flows printed between them in {_columns(columns)}, within the "
        "rounding each figure's decimals state"))
