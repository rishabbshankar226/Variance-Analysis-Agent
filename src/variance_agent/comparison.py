"""Shared vocabulary for the comparison basis (Budget, Forecast, Prior Period)."""
from __future__ import annotations

import re

from variance_agent.models import ComparisonBasis

BUDGET_SYNONYMS: frozenset[str] = frozenset({
    "budget", "budget_amount", "plan", "planned",
    "budget_ytd", "ytd_budget", "plan_ytd", "bgt", "budget_amt",
})
FORECAST_SYNONYMS: frozenset[str] = frozenset({
    "forecast", "fcst", "outlook", "projection", "projected",
})
PRIOR_PERIOD_SYNONYMS: frozenset[str] = frozenset({
    "prior_year", "py", "last_year", "prior_period",
})

_SYNONYMS: dict[ComparisonBasis, frozenset[str]] = {
    ComparisonBasis.BUDGET: BUDGET_SYNONYMS,
    ComparisonBasis.FORECAST: FORECAST_SYNONYMS,
    ComparisonBasis.PRIOR_PERIOD: PRIOR_PERIOD_SYNONYMS,
}
_NOUNS: dict[ComparisonBasis, str] = {
    ComparisonBasis.BUDGET: "budget",
    ComparisonBasis.FORECAST: "forecast",
    ComparisonBasis.PRIOR_PERIOD: "prior period",
}
_ZERO_LABELS: dict[ComparisonBasis, str] = {
    ComparisonBasis.BUDGET: "N/A (Unbudgeted)",
    ComparisonBasis.FORECAST: "N/A (Not in forecast)",
    ComparisonBasis.PRIOR_PERIOD: "N/A (New this period)",
}
_ZERO_PHRASES: dict[ComparisonBasis, str] = {
    ComparisonBasis.BUDGET: "unbudgeted",
    ComparisonBasis.FORECAST: "not in forecast",
    ComparisonBasis.PRIOR_PERIOD: "new this period",
}
_CLI_VALUES: dict[str, ComparisonBasis] = {
    "budget": ComparisonBasis.BUDGET,
    "forecast": ComparisonBasis.FORECAST,
    "prior-period": ComparisonBasis.PRIOR_PERIOD,
}


def basis_for_header(normalized: str) -> ComparisonBasis | None:
    for basis, synonyms in _SYNONYMS.items():
        if normalized in synonyms:
            return basis
    return None


def _has_phrase(tokens: list[str], phrase: str) -> bool:
    words = phrase.split("_")
    return any(tokens[i:i + len(words)] == words for i in range(len(tokens) - len(words) + 1))


def bases_named_in(normalized: str) -> list[ComparisonBasis]:
    """Bases whose synonyms appear as whole words in a normalized header ('jan_2026_bgt')."""
    tokens = normalized.split("_")
    return [
        basis for basis, synonyms in _SYNONYMS.items()
        if any(_has_phrase(tokens, synonym) for synonym in synonyms)
    ]


COMPARISON_WORDS: frozenset[str] = frozenset(
    word for synonyms in _SYNONYMS.values() for synonym in synonyms for word in synonym.split("_")
)


def parse_compare_to(value: str) -> ComparisonBasis:
    try:
        return _CLI_VALUES[value.strip().lower()]
    except KeyError:
        raise ValueError(
            f"Unknown comparison basis {value!r}; use budget, forecast or prior-period."
        ) from None


def basis_noun(basis: ComparisonBasis) -> str:
    return _NOUNS[basis]


def comparison_heading(basis: ComparisonBasis, label: str | None) -> str:
    if basis is ComparisonBasis.PRIOR_PERIOD:
        return f"Prior Period ({label})" if label else "Prior Period"
    return "Forecast" if basis is ComparisonBasis.FORECAST else "Budget"


def zero_comparison_label(basis: ComparisonBasis) -> str:
    return _ZERO_LABELS[basis]


def zero_comparison_phrase(basis: ComparisonBasis) -> str:
    """'unbudgeted', 'not in forecast' or 'new this period', for a zero comparison amount."""
    return _ZERO_PHRASES[basis]


_ACTUAL_SUFFIX = re.compile(r"\s+actuals?$", re.IGNORECASE)
_YEAR = r"(\d{4}|\d{2})"
_FY_RE = re.compile(rf"^fy{_YEAR}$", re.IGNORECASE)
_BARE_YEAR_RE = re.compile(r"^(\d{4})$")
_QUARTER_RE = re.compile(rf"^q([1-4])[\s-]{_YEAR}$", re.IGNORECASE)
_MONTH_NAME_RE = re.compile(r"^([a-z]+)\s+(\d{4})$", re.IGNORECASE)
_ISO_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_MONTHS = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
)


def _year(text: str) -> int:
    value = int(text)
    return 2000 + value if len(text) == 2 else value


def _month_index(name: str) -> int | None:
    name = name.lower()
    for i, full in enumerate(_MONTHS, start=1):
        if name == full or (len(name) == 3 and full.startswith(name)):
            return i
    return None


def parse_period_label(text: str) -> tuple[int, str, int] | None:
    """Return (year, granularity, index) for a recognizable period label."""
    s = _ACTUAL_SUFFIX.sub("", text.strip())
    if m := _FY_RE.match(s):
        return (_year(m.group(1)), "year", 0)
    if m := _BARE_YEAR_RE.match(s):
        return (int(m.group(1)), "year", 0)
    if m := _QUARTER_RE.match(s):
        return (_year(m.group(2)), "quarter", int(m.group(1)))
    if m := _ISO_MONTH_RE.match(s):
        return (int(m.group(1)), "month", int(m.group(2)))
    if m := _MONTH_NAME_RE.match(s):
        month = _month_index(m.group(1))
        if month is not None:
            return (int(m.group(2)), "month", month)
    return None


def order_period_labels(labels: list[str]) -> list[str] | None:
    """Order labels newest first, or None when the order cannot be trusted."""
    parsed: list[tuple[tuple[int, str, int], str]] = []
    for label in labels:
        key = parse_period_label(label)
        if key is None:
            return None
        parsed.append((key, label))
    if len({key[1] for key, _ in parsed}) > 1:
        return None
    if len({key for key, _ in parsed}) != len(parsed):
        return None
    parsed.sort(key=lambda item: (item[0][0], item[0][2]), reverse=True)
    return [label for _, label in parsed]


def comparison_statement(
    basis: ComparisonBasis,
    label: str | None,
    actual_label: str | None,
    all_periods: list[str] | None = None,
) -> str:
    actual = actual_label or "Actual"
    if all_periods and label and actual_label:
        return (
            f"Found {', '.join(all_periods)} — "
            f"comparing {actual_label} against {label}."
        )
    noun = basis_noun(basis)
    if basis is ComparisonBasis.PRIOR_PERIOD and label:
        return f"Comparing {actual} against {label} ({noun})."
    return f"Comparing {actual} against the {noun}."


def select_strict_comparison(
    rows: list[dict[str, object]], basis: ComparisonBasis
) -> list[dict[str, object]]:
    """Make the chosen basis the sole 'budget' column; Budget returns rows unchanged."""
    if basis is ComparisonBasis.BUDGET:
        return rows
    noun = basis_noun(basis)
    wanted = _SYNONYMS[basis]
    all_keys = {key for row in rows for key in row}
    matches = sorted(all_keys & wanted)
    if not matches:
        raise ValueError(
            f"No {noun} column found. Columns found: {sorted(all_keys)}."
        )
    if len(matches) > 1:
        raise ValueError(
            f"Found more than one {noun} column ({', '.join(matches)}); "
            "keep one and rerun."
        )
    source = matches[0]
    result: list[dict[str, object]] = []
    for row in rows:
        new = {k: v for k, v in row.items() if k not in BUDGET_SYNONYMS and k != source}
        if source in row:
            new["budget"] = row[source]
        result.append(new)
    return result
