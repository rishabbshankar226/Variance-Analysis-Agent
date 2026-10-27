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
    r"^total\b|^net\s+cash\b.*\b(?:activities|operations)\b|^(?:net\s+)?(?:\(\s*)?(?:increase|decrease|change)\b[^.]*?\bin\s+cash\b",
    re.IGNORECASE)
_TOTAL_CONCEPT = re.compile(
    r"^us-gaap:(?:Assets|AssetsCurrent|AssetsNoncurrent|Liabilities|LiabilitiesCurrent|LiabilitiesNoncurrent"
    r"|LiabilitiesAndStockholdersEquity|StockholdersEquity|StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    r"|NetCashProvidedByUsedIn(?:Operating|Investing|Financing)Activities(?:ContinuingOperations)?"
    r"|\w*PeriodIncreaseDecrease\w*)$")
_DISCONTINUED = re.compile(r"discontinued", re.IGNORECASE)
_LESS = re.compile(r"^less\b", re.IGNORECASE)
_CONTINUING = re.compile(r"\bcontinuing\s+operations\b", re.IGNORECASE)
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
    blanks: list[tuple[int, int]] = field(default_factory=list)  # (line, column) blank cells read as 0
    sides: tuple[int, int] | None = None  # the identity's two lines: assets and claims, or ending and beginning cash


def half_width(decimals: str) -> Decimal:
    """Half the rounding interval a fact's `decimals` states (XBRL Calculations 1.1, 5.2.3)."""
    if decimals.strip().upper() == "INF" or not re.fullmatch(r"-?\d+", decimals.strip()):
        return Decimal(0)
    return Decimal("0.5").scaleb(-int(decimals))


def _foots(terms: list[tuple[Figure | None, int]], total: Figure | None) -> bool:
    """The weighted terms' intervals, summed, overlap the total's (closed intervals). A blank is an exact 0."""
    if not terms:
        return False
    zero: Figure = (Decimal(0), "INF")
    with financial_context():
        pairs = [(figure or zero, weight) for figure, weight in terms]
        target = total or zero
        centre = sum((figure[0] * weight for figure, weight in pairs), Decimal(0))
        spread = sum((half_width(figure[1]) for figure, _ in pairs), Decimal(0)) + half_width(target[1])
        return abs(centre - target[0]) <= spread


def _firm_total(line: CheckLine) -> bool:
    """A total by its concept (or the ending cash balance): it must foot, or the statement refuses."""
    if line.balance == "ending":
        return True
    return not _DISCONTINUED.search(line.concept) and bool(_TOTAL_CONCEPT.match(line.concept))


def _strong_total(line: CheckLine) -> bool:
    """A total by concept, or by label; a label alone (discontinued operations' lines among them) may prove a line."""
    return _firm_total(line) or bool(_TOTAL_LABEL.search(line.name))


def _contra(line: CheckLine) -> bool:
    """A line printed to be subtracted: labeled "Less ...", or negative wherever it prints a figure."""
    values = [figure[0] for figure in line.figures if figure is not None]
    return bool(_LESS.match(line.name)) or (bool(values) and all(v <= 0 for v in values) and any(v < 0 for v in values))


def _run(lines: list[CheckLine], items: list[int], total: int, starts: range,
         signs: tuple[tuple[int, ...], ...] | None, grouped: set[int]) -> tuple[int, list[int]] | None:
    """The first run of items from one of ``starts`` that foots to ``total`` in every column, with its weights.

    Without ``signs``, a run is summed plainly, then with its "Less ..." lines subtracted; with
    ``signs``, each of those weightings is tried (a net line's two parts).
    """
    for start in starts:
        run = items[start:]
        if signs is not None:
            options = [list(sign) for sign in signs if len(sign) == len(run)]
        else:
            plain = [1] * len(run)
            less = [-1 if item not in grouped and _LESS.match(lines[item].name) else 1 for item in run]
            options = [plain, less] if less != plain else [plain]
        for weights in options:
            if all(_foots([(lines[item].figures[column], weight) for item, weight in zip(run, weights, strict=True)],
                          lines[total].figures[column]) for column in range(len(lines[total].figures))):
                return start, weights
    return None


def _foot(lines: list[CheckLine], closing: int, statement: str
          ) -> tuple[list[tuple[int, list[tuple[int, int]]]], str]:
    items: list[int] = []
    matches: list[tuple[int, list[tuple[int, int]]]] = []
    grouped: set[int] = set()
    held: int | None = None  # beginning cash waits for the ending balance it rolls into
    for i in range(closing + 1):
        line = lines[i]
        if line.balance == "beginning" and held is None:
            held = i
            continue
        if line.balance == "ending" and held is not None:
            items.append(held)
            held = None
        strong = _strong_total(line)
        plain_tail = 0  # lines (not subtotals) just above, which a net line may sum
        while plain_tail < len(items) and items[-1 - plain_tail] not in grouped:
            plain_tail += 1
        if strong:
            found = _run(lines, items, i, range(len(items)), None, grouped)
        elif plain_tail >= 2 and _contra(lines[items[-1]]):
            # A net line after its gross lines and contra line (cost less accumulated depreciation).
            found = _run(lines, items, i, range(len(items) - plain_tail, len(items) - 1), None, grouped)
        elif plain_tail >= 2 and _CONTINUING.search(line.name):
            # Net income less discontinued operations, before the adjustments.
            found = _run(lines, items, i, range(len(items) - 2, len(items) - 1), ((1, 1), (1, -1)), grouped)
        else:
            items.append(i)
            continue
        if found is None:
            if not _firm_total(line):  # a label that only looks like a total ("Total loans ...") is a line
                items.append(i)
                continue
            return matches, (f"I couldn't tell which lines '{line.name}' adds up in the {statement}, so I can't "
                             f"check it and stopped instead of guessing. {_REFUSE_FIX}")
        start, weights = found
        matches.append((i, list(zip(items[start:], weights, strict=True))))
        items = [*items[:start], i]
        grouped.add(i)
    covered = {total for total, _ in matches} | {term for _, terms in matches for term, _ in terms}
    stray = next((i for i in range(closing + 1) if i not in covered), None)
    if stray is not None:
        return matches, (f"I couldn't tell which total '{lines[stray].name}' belongs to in the {statement}, so I can't "
                         f"check it and stopped instead of guessing. {_REFUSE_FIX}")
    return matches, ""


def _blanks(lines: list[CheckLine], closing: int) -> list[tuple[int, int]]:
    """Blank cells inside the checked lines: each reads as 0, confirmed by the subtotal it sits in."""
    return [(i, column) for i in range(closing + 1) for column, figure in enumerate(lines[i].figures) if figure is None]


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
        "decimals state"), blanks=_blanks(lines, closing), sides=(assets, claims))


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
        "rounding each figure's decimals state"), blanks=_blanks(lines, ending), sides=(ending, beginning))
