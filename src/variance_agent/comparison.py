"""Shared vocabulary for the comparison basis (Budget, Forecast, Prior Period)."""
from __future__ import annotations

import re

from decimal import Decimal
from variance_agent.models import AnalysisConfig, AnalyzedRow, ComparisonBasis, ComparisonDetails, LineType, MeasureKind, Status
from variance_agent.numeric import financial_context

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
_EXTENDED_SYNONYMS: dict[ComparisonBasis, frozenset[str]] = {
    ComparisonBasis.CONSENSUS: frozenset({"consensus", "cons", "street", "consensus_mean", "mean_estimate"}),
    ComparisonBasis.ESTIMATE: frozenset({"our_est", "house", "model", "internal_estimate"}),
    ComparisonBasis.GUIDANCE: frozenset({"guidance", "guide"}),
}

# Opt-in bases (PLAN.md R13-R15): their headers count only when --compare-to names the basis.
OPT_IN_SYNONYMS: dict[ComparisonBasis, frozenset[str]] = {
    ComparisonBasis.LIMIT: frozenset({"limit", "covenant", "covenant_level", "covenant_limit"}),
    ComparisonBasis.BENCHMARK: frozenset({"benchmark", "index", "benchmark_return"}),
    ComparisonBasis.TARGET: frozenset({"target", "target_weight"}),
}

_NOUNS: dict[ComparisonBasis, str] = {
    ComparisonBasis.BUDGET: "budget",
    ComparisonBasis.FORECAST: "forecast",
    ComparisonBasis.PRIOR_PERIOD: "prior period",
    ComparisonBasis.CONSENSUS: "consensus",
    ComparisonBasis.ESTIMATE: "estimate",
    ComparisonBasis.GUIDANCE: "guidance",
    ComparisonBasis.LIMIT: "limit",
    ComparisonBasis.BENCHMARK: "benchmark",
    ComparisonBasis.TARGET: "target",
}
_ZERO_LABELS: dict[ComparisonBasis, str] = {
    ComparisonBasis.BUDGET: "N/A (Unbudgeted)",
    ComparisonBasis.FORECAST: "N/A (Not in forecast)",
    ComparisonBasis.PRIOR_PERIOD: "N/A (New this period)",
    ComparisonBasis.CONSENSUS: "N/A (No consensus)",
    ComparisonBasis.ESTIMATE: "N/A (No estimate)",
    ComparisonBasis.GUIDANCE: "N/A (No guidance)",
    ComparisonBasis.LIMIT: "N/A (Zero limit)",
    ComparisonBasis.BENCHMARK: "N/A (Zero benchmark)",
    ComparisonBasis.TARGET: "N/A (Zero target)",
}
_ZERO_PHRASES: dict[ComparisonBasis, str] = {
    ComparisonBasis.BUDGET: "unbudgeted",
    ComparisonBasis.FORECAST: "not in forecast",
    ComparisonBasis.PRIOR_PERIOD: "new this period",
    ComparisonBasis.CONSENSUS: "no consensus",
    ComparisonBasis.ESTIMATE: "no estimate",
    ComparisonBasis.GUIDANCE: "no guidance",
    ComparisonBasis.LIMIT: "a zero limit",
    ComparisonBasis.BENCHMARK: "a zero benchmark",
    ComparisonBasis.TARGET: "a zero target",
}
_CLI_VALUES: dict[str, ComparisonBasis] = {
    "budget": ComparisonBasis.BUDGET,
    "forecast": ComparisonBasis.FORECAST,
    "prior-period": ComparisonBasis.PRIOR_PERIOD,
    "consensus": ComparisonBasis.CONSENSUS,
    "estimate": ComparisonBasis.ESTIMATE,
    "guidance": ComparisonBasis.GUIDANCE,
    "limit": ComparisonBasis.LIMIT,
    "benchmark": ComparisonBasis.BENCHMARK,
    "target": ComparisonBasis.TARGET,
}


def basis_for_header(normalized: str, *, extended: bool = False,
                     opt_in: ComparisonBasis | None = None) -> ComparisonBasis | None:
    tables = _SYNONYMS | _EXTENDED_SYNONYMS if extended else dict(_SYNONYMS)
    if opt_in in OPT_IN_SYNONYMS:
        tables = {**tables, opt_in: OPT_IN_SYNONYMS[opt_in]}
    for basis, synonyms in tables.items():
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
            f"Unknown comparison basis {value!r}; use budget, forecast, prior-period, consensus, estimate, guidance, "
            "limit, benchmark or target."
        ) from None


def basis_noun(basis: ComparisonBasis) -> str:
    return _NOUNS[basis]


def comparison_heading(basis: ComparisonBasis, label: str | None) -> str:
    if basis is ComparisonBasis.PRIOR_PERIOD:
        return f"Prior Period ({label})" if label else "Prior Period"
    if basis in _EXTENDED_SYNONYMS or basis in OPT_IN_SYNONYMS:
        return _NOUNS[basis].title()
    return "Forecast" if basis is ComparisonBasis.FORECAST else "Budget"


def zero_comparison_label(basis: ComparisonBasis) -> str:
    return _ZERO_LABELS[basis]


def zero_comparison_phrase(basis: ComparisonBasis) -> str:
    """'unbudgeted', 'not in forecast' or 'new this period', for a zero comparison amount."""
    return _ZERO_PHRASES[basis]


_ACTUAL_SUFFIX = re.compile(r"\s+actuals?$", re.IGNORECASE)
_YEAR = r"(\d{4}|\d{2})"
_FY_RE = re.compile(rf"^fy\s?{_YEAR}$", re.IGNORECASE)
_BARE_YEAR_RE = re.compile(r"^(\d{4})$")
_QUARTER_RE = re.compile(rf"^q([1-4])[\s-]{_YEAR}$", re.IGNORECASE)
_MONTH_NAME_RE = re.compile(r"^([a-z]+)\s+(\d{4})$", re.IGNORECASE)
_ISO_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_MONTHS = (
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
)


def _year(text: str) -> int:
    """Four-digit years as written; two-digit years use the strptime pivot (69-99 -> 1969-1999)."""
    value = int(text)
    if len(text) != 2:
        return value
    return 1900 + value if value >= 69 else 2000 + value


def _month_index(name: str) -> int | None:
    name = name.lower()
    for i, full in enumerate(_MONTHS, start=1):
        if name == full or (len(name) == 3 and full.startswith(name)) or (name == "sept" and i == 9):
            return i
    return None


def parse_period_label(text: str, *, extended: bool = False) -> tuple[int, str, int] | None:
    """Return (year, granularity, index) for a recognizable period label."""
    s = _ACTUAL_SUFFIX.sub("", text.strip())
    if extended:
        match = re.fullmatch(r"(?:f)?([1-4])q(?:fy)?(\d{2}|\d{4})", s, re.IGNORECASE)
        if match:
            return (_year(match[2]), "quarter", int(match[1]))
        match = re.fullmatch(r"q([1-4])(?:\s*fy\s*|'|’)(\d{2}|\d{4})", s, re.IGNORECASE)
        if match:
            return (_year(match[2]), "quarter", int(match[1]))
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


def order_period_labels(labels: list[str], *, extended: bool = False) -> list[str] | None:
    """Order labels newest first, or None when the order cannot be trusted."""
    parsed: list[tuple[tuple[int, str, int], str]] = []
    for label in labels:
        key = parse_period_label(label, extended=extended)
        if key is None:
            return None
        parsed.append((key, label))
    if extended and any(key[1] == "quarter" for key, _ in parsed):
        if len({period_calendar(label) for _, label in parsed}) > 1:
            return None
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
    if all_periods and len(all_periods) >= 3 and label and actual_label:
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
    wanted = (_SYNONYMS | _EXTENDED_SYNONYMS)[basis]
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


def period_calendar(label: str) -> str:
    return "fiscal" if re.search(r"fy|^f[1-4]q", label, re.IGNORECASE) else "calendar"


def extended_heading(config: AnalysisConfig) -> str:
    from .audience import AudienceConfig
    if isinstance(config, AudienceConfig) and config.comparison_title is not None:
        return config.comparison_title
    return comparison_heading(config.comparison_basis, config.comparison_label)


def display_outcome(row: AnalyzedRow, basis: ComparisonBasis) -> str:
    if row.basis_details is not None:  # a limit, benchmark or target: its own words (PLAN.md R13-R15)
        return row.basis_details.outcome
    if row.statement_kind:  # a balance sheet or cash flow line: the change of its printed figure (PLAN.md R7)
        word = "Increase" if row.variance_dollars > 0 else "Decrease" if row.variance_dollars < 0 else "No change"
        if row.variance_dollars != 0 and row.budget < 0 and row.actual < 0:
            # Both figures printed negative (an outflow, a deduction): say whether it grew or shrank (Decisions 38, 39).
            word += ", larger negative" if abs(row.actual) > abs(row.budget) else ", smaller negative"
        return f"{word} ({row.status})" if row.better is not None and row.variance_dollars != 0 else word
    if (basis is not ComparisonBasis.CONSENSUS or row.status is Status.UNCLASSIFIED
            or (row.line_type is LineType.UNCLASSIFIED and row.better is None)):
        return str(row.status)
    if not row.material:
        return "In line"
    return "Beat" if row.status is Status.FAVORABLE else "Miss" if row.status is Status.UNFAVORABLE else "In line"


@financial_context()
def comparison_details(raw: dict[str, object], actual: Decimal, measure: MeasureKind, config: AnalysisConfig) -> ComparisonDetails | None:
    from .measures import parse_measure_amount
    from .parsing import is_missing, parse_decimal
    def optional(key: str) -> Decimal | None:
        value = raw.get(key)
        return None if is_missing(value) else parse_measure_amount(value, kind=measure, config=config,
                                                                   field=key.replace("_", " "), line_item=name)
    name = str(raw.get("line_item", "Row"))
    if config.comparison_basis is ComparisonBasis.CONSENSUS:
        low, high, dispersion = optional("consensus_low"), optional("consensus_high"), optional("dispersion")
        if low is not None and high is not None and low > high:
            raise ValueError(f"{name}: consensus low must not exceed high.")
        if dispersion is not None and dispersion < 0:
            raise ValueError(f"{name}: standard deviation must be non-negative.")
        count = None
        if not is_missing(raw.get("estimator_count")):
            number = parse_decimal(raw["estimator_count"], field="Number of estimates", line_item=name)
            if number < 0 or number != number.to_integral_value():
                raise ValueError(f"{name}: number of estimates must be a non-negative whole number.")
            count = int(number)
        position = "above the high estimate" if high is not None and actual > high else (
            "below the low estimate" if low is not None and actual < low else None)
        return ComparisonDetails(consensus_low=low, consensus_high=high, estimator_count=count,
                                 dispersion=dispersion, consensus_range_position=position)
    if config.comparison_basis is ComparisonBasis.GUIDANCE:
        low, high = optional("guidance_low"), optional("guidance_high")
        if (low is None) != (high is None):
            raise ValueError(f"{name}: guidance range needs both low and high.")
        if low is not None and high is not None:
            if low > high:
                raise ValueError(f"{name}: guidance low must not exceed high.")
            position = "Below range" if actual < low else "Above range" if actual > high else "Within range"
            return ComparisonDetails(guidance_low=low, guidance_high=high, guidance_position=position,
                                     guidance_midpoint=(low + high) / Decimal("2"))
    return None


@financial_context()
def validate_guidance_midpoint(budget: Decimal, details: ComparisonDetails | None, name: str) -> None:
    if details is not None and details.guidance_low is not None and details.guidance_high is not None:
        if budget != (details.guidance_low + details.guidance_high) / Decimal("2"):
            raise ValueError(f"{name}: comparison must equal the exact guidance midpoint.")
