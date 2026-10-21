"""Assisted intake module for reading messy FP&A files in plain language.

Handles:
- Synonym matching and column role normalization (Line Item, Budget, Actual, Account ID).
- Ignoring computed variance columns (Var $, Var %, % of Budget).
- Header row detection across title blocks and blank rows.
- Smart sheet scoring and ranking.
- Converting accounting dashes ('-', '–', '—') to 0.
- Identifying blank budgets for unbudgeted confirmation.
- One-pass problem collection without early exceptions.
- 'Here's how I read your file' summary generation.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import cast

from .currencies import SYMBOL_CURRENCIES
from .excel import WorkbookLoader, cell_value, inspect_archive
from .limits import (
    MAX_INPUT_BYTES,
    MAX_NUMBER_LENGTH,
)
from .models import ComparisonBasis, LineType
from .numeric import financial_context
from .comparison import (
    _ACTUAL_SUFFIX,
    BUDGET_SYNONYMS,
    basis_for_header,
    basis_noun,
    comparison_heading,
    comparison_statement,
    order_period_labels,
    parse_period_label,
    select_strict_comparison,
)


class CanonicalRole(StrEnum):
    LINE_ITEM = "line_item"
    ACCOUNT_ID = "account_id"
    BUDGET = "budget"
    ACTUAL = "actual"
    IGNORED_COMPUTED = "ignored_computed"
    PERIOD = "period"
    CURRENCY = "currency"
    TYPE = "type"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReconciledTotal:
    line_item: str
    budget: Decimal
    actual: Decimal
    row_index: int
    formula_description: str


@dataclass(frozen=True)
class UnreconciledTotal:
    line_item: str
    budget: Decimal
    actual: Decimal
    row_index: int
    sum_budget: Decimal | None = None
    sum_actual: Decimal | None = None


@dataclass(frozen=True)
class SubtotalDetectionResult:
    reconciled_totals: list[ReconciledTotal]
    unreconciled_totals: list[UnreconciledTotal]


@dataclass(frozen=True)
class SignedLedgerDetection:
    is_signed_ledger: bool
    negative_revenue_count: int
    negative_revenue_items: list[str]


@dataclass(frozen=True)
class PeriodColumnPair:
    period: str
    budget_column: str
    actual_column: str


@dataclass(frozen=True)
class ComparisonDetection:
    basis: ComparisonBasis | None
    label: str | None
    comparison_column: int | None
    actual_column: int | None
    candidates: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class GLRangeRule:
    min_account: int
    max_account: int
    line_type: LineType
    match_count: int


_LINE_ITEM_SYNONYMS = {
    "line_item", "line", "item", "account", "account_name", "category",
    "account_description", "description", "gl_account_name", "account_title",
    "line_item_name", "gl_description",
}

_ACCOUNT_ID_SYNONYMS = {
    "gl_account", "gl_account_number", "gl_acct", "account_number",
    "acct_num", "acct", "account_id", "acct_id", "gl",
}

_BUDGET_SYNONYMS = BUDGET_SYNONYMS

_ACTUAL_SYNONYMS = {
    "actual", "actual_amount", "actuals",
    "actual_ytd", "ytd_actual", "act", "actual_amt",
}

_IGNORED_COMPUTED_SYNONYMS = {
    "var", "variance", "var_dollar", "var_percent", "percent_of_budget",
    "pct_of_budget", "budget_variance", "percent_budget", "pct_budget",
}

_PERIOD_SYNONYMS = {"period", "month", "quarter", "year"}
_CURRENCY_SYNONYMS = {"currency", "ccy"}
_TYPE_SYNONYMS = {"type", "line_type", "classification"}

_ACCOUNTING_DASHES = {"-", "–", "—"}
_MISSING_MARKERS = {"", "na", "n/a", "none", "null"}

_NUMBER_RE = re.compile(
    r"(?P<prefix>[+-]?[$€£]?|[$€£][+-]?)\s*"
    r"(?P<number>(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:_[0-9]+)*)(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]+)?)"
)


@dataclass(frozen=True)
class SheetScore:
    name: str
    score: int
    rationale: str


@dataclass(frozen=True)
class IntakeProblem:
    row: int | None
    column: str | None
    line_item: str | None
    message: str
    fix_chip: str | None = None
    technical_detail: str | None = None


@dataclass
class IntakeResult:
    rows: list[dict[str, object]] = field(default_factory=list)
    sheet_name: str | None = None
    header_row_number: int = 1
    column_mapping: dict[CanonicalRole, str] = field(default_factory=dict)
    ignored_columns: list[str] = field(default_factory=list)
    rows_read: int = 0
    rows_skipped_count: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    visible_transformations: list[str] = field(default_factory=list)
    problems: list[IntakeProblem] = field(default_factory=list)
    blank_budget_items: list[str] = field(default_factory=list)
    candidate_sheets: list[SheetScore] = field(default_factory=list)
    available_sheets: list[str] = field(default_factory=list)
    has_fatal_errors: bool = False
    fatal_error_message: str | None = None
    detected_totals: list[str] = field(default_factory=list)
    unreconciled_totals: list[UnreconciledTotal] = field(default_factory=list)
    detected_unit_multiplier: Decimal = field(default=Decimal("1"))
    detected_signed_ledger: bool = False
    negative_revenue_items: list[str] = field(default_factory=list)
    detected_period_pairs: list[PeriodColumnPair] = field(default_factory=list)
    detected_single_periods: list[str] = field(default_factory=list)
    raw_headers: list[str] = field(default_factory=list)
    raw_title_text: str = ""
    comparison_basis: ComparisonBasis = ComparisonBasis.BUDGET
    comparison_label: str | None = None
    comparison_candidates: list[str] = field(default_factory=list)

    @property
    def has_transformations(self) -> bool:
        """Return True if any heuristic adjustment or transformation was made that warrants confirmation."""
        if self.comparison_basis != ComparisonBasis.BUDGET:
            return True
        if self.header_row_number > 1:
            return True
        if self.rows_skipped_count > 0:
            return True
        if self.visible_transformations:
            return True
        if self.ignored_columns:
            return True
        if self.blank_budget_items:
            return True
        if self.detected_totals:
            return True
        if self.detected_signed_ledger:
            return True
        if self.detected_unit_multiplier != Decimal("1"):
            return True
        if self.detected_period_pairs:
            return True
        if len(self.detected_single_periods) > 1:
            return True
        if self.candidate_sheets and len(self.candidate_sheets) > 1:
            # If the selected sheet is not the active/first sheet, it was a transformation
            if self.sheet_name and self.sheet_name != self.candidate_sheets[0].name:
                return True
        std_line_items = {"line_item", "line item", "line", "item", "account", "category"}
        std_budgets = {"budget", "budget_amount", "budget amount", "plan", "planned"}
        std_actuals = {"actual", "actual_amount", "actual amount", "actuals"}
        for role, orig in self.column_mapping.items():
            orig_lower = orig.strip().lower()
            if role == CanonicalRole.LINE_ITEM and orig_lower not in std_line_items:
                return True
            if role == CanonicalRole.BUDGET and orig_lower not in std_budgets:
                return True
            if role == CanonicalRole.ACTUAL and orig_lower not in std_actuals:
                return True
            if role == CanonicalRole.ACCOUNT_ID:
                return True
        return False


def normalize_header(raw: str) -> str:
    """Normalize a column header by stripping punctuation, handling &, and removing currency signs."""
    text = raw.strip().lower()
    text = re.sub(r"\b&\b", "and", text)
    text = text.replace("&", "and")
    text = text.replace("%", " percent ")
    text = text.replace("$", " dollar ")
    # Strip standalone symbols
    text = re.sub(r"[€£#]", "", text)
    # Replace non-alphanumeric with underscores
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def match_column_synonym(header: str) -> tuple[CanonicalRole, str | None]:
    """Map a raw header name to its canonical role and an optional transformation note."""
    norm = normalize_header(header)
    if norm in _LINE_ITEM_SYNONYMS:
        return CanonicalRole.LINE_ITEM, None
    if norm in _ACCOUNT_ID_SYNONYMS:
        return CanonicalRole.ACCOUNT_ID, None
    if basis_for_header(norm) is not None:
        return CanonicalRole.BUDGET, None
    if norm in _ACTUAL_SYNONYMS:
        return CanonicalRole.ACTUAL, None
    if norm in _IGNORED_COMPUTED_SYNONYMS:
        return CanonicalRole.IGNORED_COMPUTED, None
    if norm in _PERIOD_SYNONYMS:
        return CanonicalRole.PERIOD, None
    if norm in _CURRENCY_SYNONYMS:
        return CanonicalRole.CURRENCY, None
    if norm in _TYPE_SYNONYMS:
        return CanonicalRole.TYPE, None

    return CanonicalRole.UNKNOWN, None


def parse_assisted_decimal(
    value: object,
    *,
    field: str,
    line_item: str,
    currency: str | None = None,
    allow_blank: bool = False,
) -> tuple[Decimal | None, str | None]:
    """Parse numeric input supporting accounting dashes as 0 and optional blank detection."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        if allow_blank:
            return None, "blank"
        raise ValueError(f"{line_item}: required value in {field} is missing.")

    if isinstance(value, bool):
        raise ValueError(f"{line_item}: field '{field}' must be numeric, not boolean.")

    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{line_item}: field '{field}' must be a finite number.")
        return value, None

    if isinstance(value, (int, float)):
        dec = Decimal(str(value))
        if not dec.is_finite():
            raise ValueError(f"{line_item}: field '{field}' must be a finite number.")
        return dec, None

    if not isinstance(value, str):
        raise ValueError(f"{line_item}: field '{field}' must be a numeric scalar.")

    text = value.strip()
    if text in _ACCOUNTING_DASHES:
        return Decimal("0"), f"Read accounting dash '{text}' as 0"

    if text.lower() in {"na", "n/a", "none", "null"}:
        raise ValueError(f"{line_item}: required value in {field} is missing (marked {text}).")

    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1]

    if text.strip().lower().lstrip("+-") in {"nan", "snan", "inf", "infinity"}:
        raise ValueError(f"{line_item}: field '{field}' must be a finite number.")

    match = _NUMBER_RE.fullmatch(text.strip())
    if match is None or (negative_parentheses and any(sign in match["prefix"] for sign in "+-")):
        raise ValueError(f"{line_item}: field '{field}' has an unrecognized number format: {value}.")

    if currency is not None:
        for symbol, code in SYMBOL_CURRENCIES.items():
            if symbol in match["prefix"] and code != currency:
                raise ValueError(
                    f"{line_item}: field '{field}' currency {code} conflicts with "
                    f"reporting currency {currency}; no currency conversion is performed."
                )

    sign = "-" if "-" in match["prefix"] else ""
    numeric_text = sign + match["number"].replace(",", "").replace("_", "")
    try:
        with financial_context():
            number = Decimal(numeric_text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{line_item}: field '{field}' is not numeric: {value}.") from exc

    if negative_parentheses:
        number = number.copy_negate()

    if not number.is_finite():
        raise ValueError(f"{line_item}: field '{field}' must be a finite number.")
    if len(number.as_tuple().digits) > MAX_NUMBER_LENGTH:
        raise ValueError(f"{line_item}: field '{field}' exceeds the supported numeric length.")

    return number, None


_PERIOD_RE = re.compile(
    r"\b((?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-_ ]?\d{2,4})|"
    r"(?:Q[1-4](?:[-_ ]?\d{2,4})?)|"
    r"(?:FY\s*\d{2,4})|"
    r"(?:YTD|MTD)|"
    r"(?:\d{4}[-_]\d{2}))\b",
    re.IGNORECASE,
)

_THOUSANDS_RE = re.compile(r"(\(\$000s?\)|in\s+thousands|\$000s?|\b000s\b)", re.IGNORECASE)
_MILLIONS_RE = re.compile(r"(\(in\s+millions\)|in\s+millions|\$m\b|in\s+m\b)", re.IGNORECASE)
_REVENUE_KEYWORDS = re.compile(r"\b(revenue|sales|income|rev)\b", re.IGNORECASE)
_EXPENSE_KEYWORDS = re.compile(r"\b(expense|expenses|cost|costs|cogs|opex|payroll|rent|marketing|freight|utilities)\b", re.IGNORECASE)
_TOTAL_KEYWORD_RE = re.compile(
    r"\b(total|sub\s*total|subtotal|gross\s+profit|net\s+income|operating\s+income|ebitda)\b",
    re.IGNORECASE,
)
_ACCOUNT_NUM_RE = re.compile(r"\b([1-9]\d{3,4})\b")


def detect_period_pairs(headers: list[str]) -> list[PeriodColumnPair]:
    """Scan column headers to detect paired Budget and Actual columns by period."""
    budget_cols: dict[str, str] = {}
    actual_cols: dict[str, str] = {}
    period_order: list[str] = []

    for h in headers:
        m = _PERIOD_RE.search(h)
        if not m:
            continue
        p = m.group(1).strip()
        h_lower = h.lower()
        if "budget" in h_lower or "plan" in h_lower:
            budget_cols[p] = h
            if p not in period_order:
                period_order.append(p)
        elif "actual" in h_lower or "act" in h_lower:
            actual_cols[p] = h
            if p not in period_order:
                period_order.append(p)

    pairs: list[PeriodColumnPair] = []
    for p in period_order:
        if p in budget_cols and p in actual_cols:
            pairs.append(PeriodColumnPair(period=p, budget_column=budget_cols[p], actual_column=actual_cols[p]))
    return pairs


def detect_single_period_column_values(rows: list[dict[str, object]]) -> list[str]:
    """Return distinct non-empty period values if a single period column is present."""
    seen: set[str] = set()
    periods: list[str] = []
    for r in rows:
        pval = r.get("period")
        if pval is not None:
            pstr = str(pval).strip()
            if pstr and pstr not in seen:
                seen.add(pstr)
                periods.append(pstr)
    return periods


def detect_unit_scale(text: str) -> Decimal:
    """Detect whether numbers are in thousands, millions, or base dollars."""
    if _MILLIONS_RE.search(text):
        return Decimal("1000000")
    if _THOUSANDS_RE.search(text):
        return Decimal("1000")
    return Decimal("1")


def scale_rows_by_unit(rows: list[dict[str, object]], multiplier: Decimal) -> list[dict[str, object]]:
    """Scale budget and actual amounts by exact Decimal multiplication."""
    if multiplier == Decimal("1"):
        return rows
    scaled: list[dict[str, object]] = []
    for r in rows:
        rc = dict(r)
        if "budget" in rc and isinstance(rc["budget"], Decimal):
            rc["budget"] = rc["budget"] * multiplier
        if "actual" in rc and isinstance(rc["actual"], Decimal):
            rc["actual"] = rc["actual"] * multiplier
        scaled.append(rc)
    return scaled


def detect_signed_ledger(rows: list[dict[str, object]]) -> SignedLedgerDetection:
    """Detect if ledger stores revenue as negative credits and expenses as positive debits."""
    rev_items: list[tuple[str, bool]] = []
    exp_positive_count = 0
    exp_total = 0

    for r in rows:
        name = str(r.get("line_item", "")).strip()
        b = r.get("budget")
        a = r.get("actual")
        b_dec = Decimal(str(b)) if b is not None else Decimal("0")
        a_dec = Decimal(str(a)) if a is not None else Decimal("0")

        is_rev = bool(_REVENUE_KEYWORDS.search(name)) or str(r.get("type", "")).lower() == "revenue"
        is_exp = bool(_EXPENSE_KEYWORDS.search(name)) or str(r.get("type", "")).lower() == "expense"

        if is_rev and not is_exp:
            is_neg = (b_dec < 0 or a_dec < 0)
            rev_items.append((name, is_neg))
        elif is_exp and not is_rev:
            exp_total += 1
            if b_dec >= 0 and a_dec >= 0:
                exp_positive_count += 1

    neg_rev_count = sum(1 for _, is_neg in rev_items if is_neg)
    is_signed = False
    if rev_items and neg_rev_count > len(rev_items) / 2:
        is_signed = True

    return SignedLedgerDetection(
        is_signed_ledger=is_signed,
        negative_revenue_count=neg_rev_count,
        negative_revenue_items=[name for name, is_neg in rev_items if is_neg],
    )


def flip_ledger_signs(
    rows: list[dict[str, object]], items_to_flip: list[str]
) -> tuple[list[dict[str, object]], list[str]]:
    """Flip signs of affected rows using exact Decimal copy_negate()."""
    to_flip = set(items_to_flip)
    affected: list[str] = []
    flipped: list[dict[str, object]] = []
    for r in rows:
        rc = dict(r)
        name = str(r.get("line_item", "")).strip()
        if name in to_flip:
            affected.append(name)
            if "budget" in rc and isinstance(rc["budget"], Decimal):
                rc["budget"] = rc["budget"].copy_negate()
            if "actual" in rc and isinstance(rc["actual"], Decimal):
                rc["actual"] = rc["actual"].copy_negate()
        flipped.append(rc)
    return flipped, affected


def detect_subtotals_and_totals(rows: list[dict[str, object]]) -> SubtotalDetectionResult:
    """Detect contiguous block subtotals and nested formula totals within 0.01 tolerance."""
    tolerance = Decimal("0.01")
    reconciled_totals: list[ReconciledTotal] = []
    unreconciled_totals: list[UnreconciledTotal] = []
    detail_indices: list[int] = []

    for i, row in enumerate(rows):
        name = str(row.get("line_item", "")).strip()
        b_raw = row.get("budget")
        a_raw = row.get("actual")
        b = Decimal(str(b_raw)) if b_raw is not None else Decimal("0")
        a = Decimal(str(a_raw)) if a_raw is not None else Decimal("0")
        is_total_kw = bool(_TOTAL_KEYWORD_RE.search(name))

        # 1. Contiguous block check over prior detail rows
        found_block = False
        for j in range(len(detail_indices) - 1, -1, -1):
            block_idx = detail_indices[j:]
            if len(block_idx) < 1:
                continue
            sum_b = sum(Decimal(str(rows[k]["budget"])) for k in block_idx)
            sum_a = sum(Decimal(str(rows[k]["actual"])) for k in block_idx)
            if abs(b - sum_b) <= tolerance and abs(a - sum_a) <= tolerance:
                if len(block_idx) >= 2 or is_total_kw:
                    reconciled_totals.append(
                        ReconciledTotal(
                            line_item=name,
                            budget=b,
                            actual=a,
                            row_index=i,
                            formula_description=f"sum of {len(block_idx)} detail rows",
                        )
                    )
                    found_block = True
                    break
        if found_block:
            continue

        # 2. Nested formula check (diff between prior totals or detail)
        found_formula = False
        prior_totals = list(reconciled_totals)
        for prev in prior_totals:
            for d_idx in detail_indices:
                det_b = Decimal(str(rows[d_idx]["budget"]))
                det_a = Decimal(str(rows[d_idx]["actual"]))
                if abs((prev.budget - det_b) - b) <= tolerance and abs((prev.actual - det_a) - a) <= tolerance:
                    reconciled_totals.append(
                        ReconciledTotal(
                            line_item=name,
                            budget=b,
                            actual=a,
                            row_index=i,
                            formula_description=f"{prev.line_item} - {rows[d_idx].get('line_item')}",
                        )
                    )
                    found_formula = True
                    break
            if found_formula:
                break
            for prev2 in prior_totals:
                if prev2.row_index == prev.row_index:
                    continue
                if abs((prev.budget - prev2.budget) - b) <= tolerance and abs((prev.actual - prev2.actual) - a) <= tolerance:
                    reconciled_totals.append(
                        ReconciledTotal(
                            line_item=name,
                            budget=b,
                            actual=a,
                            row_index=i,
                            formula_description=f"{prev.line_item} - {prev2.line_item}",
                        )
                    )
                    found_formula = True
                    break
            if found_formula:
                break

        if found_formula:
            continue

        if is_total_kw:
            sum_prior_b = sum((Decimal(str(rows[k]["budget"])) for k in detail_indices), Decimal("0")) if detail_indices else None
            sum_prior_a = sum((Decimal(str(rows[k]["actual"])) for k in detail_indices), Decimal("0")) if detail_indices else None
            unreconciled_totals.append(
                UnreconciledTotal(
                    line_item=name,
                    budget=b,
                    actual=a,
                    row_index=i,
                    sum_budget=sum_prior_b,
                    sum_actual=sum_prior_a,
                )
            )
        else:
            detail_indices.append(i)

    return SubtotalDetectionResult(
        reconciled_totals=reconciled_totals,
        unreconciled_totals=unreconciled_totals,
    )


def infer_gl_range_rules(items: list[str]) -> list[GLRangeRule]:
    """Infer standard FP&A GL account range rules (4000-4999 Revenue, 5000-8999 Expense)."""
    rev_count = 0
    exp_count = 0

    for item in items:
        m = _ACCOUNT_NUM_RE.search(item)
        if not m:
            continue
        val = int(m.group(1))
        if 4000 <= val <= 4999:
            rev_count += 1
        elif 5000 <= val <= 8999:
            exp_count += 1

    rules: list[GLRangeRule] = []
    if rev_count > 0:
        rules.append(
            GLRangeRule(
                min_account=4000,
                max_account=4999,
                line_type=LineType.REVENUE,
                match_count=rev_count,
            )
        )
    if exp_count > 0:
        rules.append(
            GLRangeRule(
                min_account=5000,
                max_account=8999,
                line_type=LineType.EXPENSE,
                match_count=exp_count,
            )
        )
    return rules


def apply_classification_rules(
    items: list[str],
    rules: list[GLRangeRule],
    keywords: dict[str, LineType] | None = None,
    bulk_default: LineType | None = None,
) -> dict[str, LineType]:
    """Apply GL range rules, keyword rules, and optional default to classify line items."""
    type_map: dict[str, LineType] = {}
    for item in items:
        m = _ACCOUNT_NUM_RE.search(item)
        classified = False
        if m:
            val = int(m.group(1))
            for rule in rules:
                if rule.min_account <= val <= rule.max_account:
                    type_map[item] = rule.line_type
                    classified = True
                    break
        if not classified and keywords:
            for kw, l_type in keywords.items():
                if kw.lower() in item.lower():
                    type_map[item] = l_type
                    classified = True
                    break
        if not classified and bulk_default is not None:
            type_map[item] = bulk_default

    return type_map


def detect_header_row(
    raw_rows: list[list[object]], max_scan: int = 25, selected_period: str | None = None
) -> tuple[int | None, dict[CanonicalRole, int], list[int]]:
    """Scan the first candidate rows to find the header row containing Line Item, Budget, and Actual."""
    for row_idx, row in enumerate(raw_rows[:max_scan]):
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        roles: dict[CanonicalRole, int] = {}
        ignored: list[int] = []

        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            cell_str = str(cell).strip()
            if not cell_str:
                continue

            role, _ = match_column_synonym(cell_str)
            if role == CanonicalRole.IGNORED_COMPUTED:
                ignored.append(col_idx)
            elif role != CanonicalRole.UNKNOWN and role not in roles:
                roles[role] = col_idx

        # A valid budget-vs-actual header must have Line Item, Budget, and Actual
        if (
            CanonicalRole.LINE_ITEM in roles
            and CanonicalRole.BUDGET in roles
            and CanonicalRole.ACTUAL in roles
        ):
            return row_idx, roles, ignored

        # Check for wide monthly / multi-period header row
        cell_strs = [str(c).strip() for c in row if c is not None]
        pairs = detect_period_pairs(cell_strs)
        if pairs:
            # Look for line item role if not already found
            if CanonicalRole.LINE_ITEM not in roles:
                for col_idx, cell in enumerate(row):
                    if cell is not None and str(cell).strip():
                        r, _ = match_column_synonym(str(cell).strip())
                        if r == CanonicalRole.LINE_ITEM:
                            roles[CanonicalRole.LINE_ITEM] = col_idx
                            break
            if CanonicalRole.LINE_ITEM in roles:
                chosen_pair = None
                if selected_period is not None:
                    chosen_pair = next((p for p in pairs if p.period.lower() == selected_period.lower()), None)
                if chosen_pair is None:
                    chosen_pair = pairs[-1]
                for col_idx, cell in enumerate(row):
                    if cell is not None and str(cell).strip():
                        cs = str(cell).strip()
                        if cs == chosen_pair.budget_column:
                            roles[CanonicalRole.BUDGET] = col_idx
                        elif cs == chosen_pair.actual_column:
                            roles[CanonicalRole.ACTUAL] = col_idx
                if CanonicalRole.BUDGET in roles and CanonicalRole.ACTUAL in roles:
                    return row_idx, roles, ignored

        # Check for period-only header columns (e.g. FY2025, FY2024, FY2023 or 2024, 2025).
        # Wide budget-vs-actual layouts (period pairs) never take this path.
        if CanonicalRole.LINE_ITEM in roles and not pairs:
            period_cols: list[int] = []
            for col_idx, cell in enumerate(row):
                cell_s = _header_cell_str(cell)
                if cell_s:
                    stripped = _ACTUAL_SUFFIX.sub("", cell_s).strip()
                    if parse_period_label(stripped) is not None:
                        period_cols.append(col_idx)
            if len(period_cols) >= 2:
                roles[CanonicalRole.ACTUAL] = period_cols[0]
                roles[CanonicalRole.BUDGET] = period_cols[1]
                return row_idx, roles, ignored

    return None, {}, []


def rank_workbook_sheets(sheets: list[tuple[str, list[list[object]]]]) -> list[SheetScore]:
    """Score worksheets in a workbook to rank the best candidate for budget-vs-actual analysis."""
    scores: list[SheetScore] = []
    for name, rows in sheets:
        score = 0
        reasons = []

        header_idx, roles, _ = detect_header_row(rows)
        if header_idx is not None:
            score += 20
            reasons.append("contains Line item, Budget, and Actual columns")
        else:
            # Check for partial matches
            matched_roles = set()
            for r in rows[:15]:
                for c in r:
                    if c:
                        role, _ = match_column_synonym(str(c))
                        if role in (CanonicalRole.LINE_ITEM, CanonicalRole.BUDGET, CanonicalRole.ACTUAL):
                            matched_roles.add(role)
            if matched_roles:
                score += 5 * len(matched_roles)
                reasons.append(f"contains partial headers ({len(matched_roles)}/3)")

        if len(rows) > 1:
            score += min(len(rows), 10)

        lower_name = name.lower()
        if any(term in lower_name for term in ("cover", "contents", "readme", "notes", "index", "summary_cover")):
            score -= 15
            reasons.append("title suggests cover page or notes")

        if "bva" in lower_name or "variance" in lower_name or "p&l" in lower_name or "pnl" in lower_name:
            score += 10
            reasons.append("title matches budget-vs-actual or P&L")

        rationale = "; ".join(reasons) or "general data worksheet"
        scores.append(SheetScore(name=name, score=score, rationale=rationale))

    scores.sort(key=lambda s: s.score, reverse=True)
    return scores


def _excel_loader() -> WorkbookLoader:
    try:
        module: object = __import__("openpyxl", fromlist=["load_workbook"])
    except ImportError as exc:
        raise ValueError(
            "Excel files require the optional Excel tools. Please install with: pip install 'variance-analysis-agent[excel]'"
        ) from exc
    return cast(WorkbookLoader, getattr(module, "load_workbook"))


def _header_cell_str(cell: object) -> str:
    if cell is None:
        return ""
    if isinstance(cell, (int, float, Decimal)):
        try:
            if cell == int(cell):
                return str(int(cell))
        except (ValueError, OverflowError, InvalidOperation):
            pass
    return str(cell).strip()


def detect_comparison_columns(
    header_cells: list[object],
    compare_to: ComparisonBasis | None = None,
) -> ComparisonDetection:
    """Identify comparison and actual columns according to vocabulary and period ordering."""
    headers: list[tuple[int, str]] = []
    for idx, cell in enumerate(header_cells):
        s = _header_cell_str(cell)
        if s:
            headers.append((idx, s))

    all_headers_display = ", ".join(s for _, s in headers)

    actual_col: int | None = None
    actual_label: str | None = None
    for idx, s in headers:
        norm = normalize_header(s)
        if norm in _ACTUAL_SYNONYMS:
            actual_col = idx
            actual_label = s
            break

    # 1. Named candidates
    named_candidates: list[tuple[int, str, ComparisonBasis]] = []
    for idx, s in headers:
        norm = normalize_header(s)
        b = basis_for_header(norm)
        if b is not None:
            named_candidates.append((idx, s, b))

    if named_candidates:
        if compare_to is not None:
            matched = [c for c in named_candidates if c[2] == compare_to]
            noun = basis_noun(compare_to)
            if not matched:
                msg = f"No {noun} column found. Columns found: {all_headers_display}."
                return ComparisonDetection(
                    basis=None,
                    label=None,
                    comparison_column=None,
                    actual_column=actual_col,
                    candidates=(),
                    message=msg,
                )
            if len(matched) > 1:
                col_names = [c[1] for c in matched]
                msg = f"Found more than one {noun} column ({', '.join(col_names)}); keep one and rerun."
                return ComparisonDetection(
                    basis=None,
                    label=None,
                    comparison_column=None,
                    actual_column=actual_col,
                    candidates=tuple(col_names),
                    message=msg,
                )
            col_idx, orig_name, basis = matched[0]
            msg = comparison_statement(basis, None, actual_label)
            return ComparisonDetection(
                basis=basis,
                label=None,
                comparison_column=col_idx,
                actual_column=actual_col,
                candidates=(),
                message=msg,
            )

        distinct_bases = {c[2] for c in named_candidates}
        if len(distinct_bases) > 1:
            col_names = [c[1] for c in named_candidates]
            msg = f"This file has more than one column to compare against ({', '.join(col_names)}). Which should Actual be compared against?"
            return ComparisonDetection(
                basis=None,
                label=None,
                comparison_column=None,
                actual_column=actual_col,
                candidates=tuple(col_names),
                message=msg,
            )
        # One distinct basis: the first column wins, as in detect_header_row.
        col_idx, orig_name, basis = named_candidates[0]
        msg = comparison_statement(basis, None, actual_label)
        return ComparisonDetection(
            basis=basis,
            label=None,
            comparison_column=col_idx,
            actual_column=actual_col,
            candidates=(),
            message=msg,
        )

    # 2. Period-only columns (used only when step 1 found no candidates and the
    #    header is not a wide budget-vs-actual layout of period pairs)
    period_candidates: list[tuple[int, str, str]] = []
    if not detect_period_pairs([s for _, s in headers]):
        for idx, s in headers:
            stripped = _ACTUAL_SUFFIX.sub("", s).strip()
            if parse_period_label(stripped) is not None:
                period_candidates.append((idx, s, stripped))

    if len(period_candidates) >= 2:
        if compare_to is not None and compare_to != ComparisonBasis.PRIOR_PERIOD:
            noun = basis_noun(compare_to)
            msg = f"No {noun} column found. Columns found: {all_headers_display}."
            return ComparisonDetection(
                basis=None,
                label=None,
                comparison_column=None,
                actual_column=None,
                candidates=(),
                message=msg,
            )
        labels = [p[2] for p in period_candidates]
        ordered = order_period_labels(labels)
        if ordered is None:
            msg = f"Could not determine period order for {', '.join(labels)}."
            return ComparisonDetection(
                basis=None,
                label=None,
                comparison_column=None,
                actual_column=None,
                candidates=tuple(labels),
                message=msg,
            )
        label_to_col: dict[str, tuple[int, str]] = {p[2]: (p[0], p[1]) for p in period_candidates}
        newest_label = ordered[0]
        second_newest_label = ordered[1]
        act_col, act_orig = label_to_col[newest_label]
        comp_col, comp_orig = label_to_col[second_newest_label]
        msg = comparison_statement(
            ComparisonBasis.PRIOR_PERIOD,
            label=second_newest_label,
            actual_label=newest_label,
            all_periods=ordered,
        )
        return ComparisonDetection(
            basis=ComparisonBasis.PRIOR_PERIOD,
            label=second_newest_label,
            comparison_column=comp_col,
            actual_column=act_col,
            candidates=(),
            message=msg,
        )

    # 3. Fallback
    if compare_to is not None and compare_to != ComparisonBasis.BUDGET:
        noun = basis_noun(compare_to)
        msg = f"No {noun} column found. Columns found: {all_headers_display}."
        return ComparisonDetection(
            basis=None,
            label=None,
            comparison_column=None,
            actual_column=actual_col,
            candidates=(),
            message=msg,
        )

    return ComparisonDetection(
        basis=ComparisonBasis.BUDGET,
        label=None,
        comparison_column=None,
        actual_column=actual_col,
        candidates=(),
        message="",
    )


def read_input_assisted(
    data: bytes,
    suffix: str,
    *,
    filename: str = "input",
    sheet: str | None = None,
    treat_blank_budgets_as_zero: bool = False,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
) -> IntakeResult:
    """Read any supported file format with assisted header, sheet, dash, and problem handling."""
    if len(data) > MAX_INPUT_BYTES:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=f"The file '{filename}' exceeds the supported file size limit of 32 MiB.",
        )

    norm_suffix = suffix.lower()
    if norm_suffix in {".tsv", ".txt"}:
        return _read_tsv_text(
            data.decode("utf-8-sig", errors="replace"),
            filename,
            treat_blank_budgets_as_zero,
            selected_period,
            compare_to=compare_to,
        )
    if norm_suffix == ".csv":
        return _read_csv_text(
            data.decode("utf-8-sig", errors="replace"),
            filename,
            treat_blank_budgets_as_zero,
            selected_period,
            compare_to=compare_to,
        )
    if norm_suffix in {".xlsx", ".xlsm"}:
        return _read_excel_bytes(
            data,
            filename,
            sheet,
            treat_blank_budgets_as_zero,
            selected_period,
            compare_to=compare_to,
        )
    if norm_suffix == ".json":
        return _read_json_bytes(data, filename, compare_to=compare_to)

    return IntakeResult(
        has_fatal_errors=True,
        fatal_error_message=f"Unsupported input format '{suffix}'. Please use an Excel workbook (.xlsx, .xlsm), CSV, or TSV file.",
    )


def _read_tsv_text(
    text: str,
    filename: str,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
) -> IntakeResult:
    lines = [line for line in text.splitlines() if line.strip()]
    reader = csv.reader(lines, delimiter="\t")
    raw_rows: list[list[object]] = [cast(list[object], row) for row in reader]
    res = _process_raw_table(
        raw_rows,
        filename,
        sheet_name=None,
        treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
        selected_period=selected_period,
        compare_to=compare_to,
    )
    if "pasted" in filename.lower() or filename == "pasted_data.tsv":
        res.visible_transformations.insert(0, "Read data from pasted tab-separated text")
    return res


def _read_csv_text(
    text: str,
    filename: str,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
) -> IntakeResult:
    lines = [line for line in text.splitlines() if line.strip()]
    reader = csv.reader(lines)
    raw_rows: list[list[object]] = [cast(list[object], row) for row in reader]
    return _process_raw_table(
        raw_rows,
        filename,
        sheet_name=None,
        treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
        selected_period=selected_period,
        compare_to=compare_to,
    )


def _read_json_bytes(
    data: bytes,
    filename: str,
    compare_to: ComparisonBasis | None = None,
) -> IntakeResult:
    # Delegate to parsing.load_json_text and wrap into IntakeResult
    from .parsing import load_json_text
    try:
        rows = load_json_text(data.decode("utf-8"))
        basis = compare_to if compare_to is not None else ComparisonBasis.BUDGET
        if basis != ComparisonBasis.BUDGET:
            try:
                rows = select_strict_comparison(rows, basis)
            except ValueError as exc:
                # The comparison-column error is already user-facing; no read-error prefix.
                return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc))
        canonical_rows: list[dict[str, object]] = []
        for r in rows:
            line_item = r.get("line_item") or r.get("account") or r.get("item")
            canonical_rows.append({
                "line_item": str(line_item or ""),
                "budget": r.get("budget"),
                "actual": r.get("actual"),
            })
        visible_transformations: list[str] = []
        if basis != ComparisonBasis.BUDGET:
            visible_transformations.append(comparison_statement(basis, None, "Actual"))
        return IntakeResult(
            rows=canonical_rows,
            header_row_number=1,
            rows_read=len(canonical_rows),
            column_mapping={
                CanonicalRole.LINE_ITEM: "line_item",
                CanonicalRole.BUDGET: "budget",
                CanonicalRole.ACTUAL: "actual",
            },
            comparison_basis=basis,
            comparison_label=None,
            visible_transformations=visible_transformations,
        )
    except Exception as exc:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=f"Could not read JSON data from '{filename}': {exc}",
        )


def _read_excel_bytes(
    data: bytes,
    filename: str,
    sheet: str | None,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
) -> IntakeResult:
    try:
        stored_numbers = inspect_archive(data)
    except Exception:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=f"The Excel file '{filename}' could not be opened safely.",
        )

    loader = _excel_loader()
    with io.BytesIO(data) as src:
        wb = None
        try:
            wb = loader(src, read_only=True, data_only=True)
            sheetnames = list(wb.sheetnames)
            if not sheetnames:
                return IntakeResult(
                    has_fatal_errors=True,
                    fatal_error_message=f"The Excel workbook '{filename}' contains no worksheets.",
                )

            # Pre-extract rows for ranking if multiple sheets
            all_sheets_raw: list[tuple[str, list[list[object]]]] = []
            for name in sheetnames:
                ws = wb[name]
                ws.reset_dimensions()
                sheet_rows: list[list[object]] = []
                numbers = stored_numbers.get(ws._worksheet_path, {})
                for r_idx, cells in enumerate(ws.iter_rows(), start=1):
                    if r_idx > 30:  # Scan up to 30 rows for ranking
                        break
                    row_vals = [
                        cell_value(c, numbers=numbers, row=r_idx, column=c_idx)
                        for c_idx, c in enumerate(cells, start=1)
                    ]
                    if any(v is not None and str(v).strip() != "" for v in row_vals):
                        sheet_rows.append(row_vals)
                all_sheets_raw.append((name, sheet_rows))

            ranked = rank_workbook_sheets(all_sheets_raw)

            # If user explicitly specified sheet, use that; otherwise pick top ranked sheet
            chosen_sheet = sheet
            if chosen_sheet is None:
                chosen_sheet = ranked[0].name if ranked else sheetnames[0]
            elif chosen_sheet not in sheetnames:
                return IntakeResult(
                    has_fatal_errors=True,
                    fatal_error_message=f"Worksheet '{chosen_sheet}' was not found in '{filename}'. Available sheets: {', '.join(sheetnames)}.",
                    available_sheets=sheetnames,
                )

            target_ws = wb[chosen_sheet]
            target_ws.reset_dimensions()
            numbers = stored_numbers.get(target_ws._worksheet_path, {})

            full_raw_rows: list[list[object]] = []
            for r_idx, cells in enumerate(target_ws.iter_rows(), start=1):
                row_vals = [
                    cell_value(c, numbers=numbers, row=r_idx, column=c_idx)
                    for c_idx, c in enumerate(cells, start=1)
                ]
                full_raw_rows.append(row_vals)

            result = _process_raw_table(
                full_raw_rows,
                filename,
                sheet_name=chosen_sheet,
                treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
                selected_period=selected_period,
                compare_to=compare_to,
            )
            result.candidate_sheets = ranked
            result.available_sheets = sheetnames
            if chosen_sheet != sheetnames[0] and ranked:
                rationale = ranked[0].rationale if ranked[0].name == chosen_sheet else "better matches budget-vs-actual data"
                result.visible_transformations.insert(
                    0, f"Selected worksheet '{chosen_sheet}' ({rationale}) over '{sheetnames[0]}'"
                )
            return result
        except Exception as exc:
            return IntakeResult(
                has_fatal_errors=True,
                fatal_error_message=f"Could not read Excel file '{filename}': {exc}",
            )
        finally:
            if wb is not None:
                wb.close()


def _process_raw_table(
    raw_rows: list[list[object]],
    filename: str,
    sheet_name: str | None,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
) -> IntakeResult:
    if not raw_rows:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=f"The file '{filename}' contains no data.",
            sheet_name=sheet_name,
        )

    header_idx, roles, ignored_col_indices = detect_header_row(raw_rows, selected_period=selected_period)
    if header_idx is None:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=(
                f"Could not find a header row with Line Item, Budget, and Actual columns in '{filename}'."
            ),
            sheet_name=sheet_name,
        )

    header_row = raw_rows[header_idx]
    header_row_number = header_idx + 1
    skipped_count = header_idx
    skip_reasons = []
    if skipped_count > 0:
        skip_reasons.append(f"{skipped_count} title block row{'s' if skipped_count != 1 else ''} above header")

    detection = detect_comparison_columns(header_row, compare_to=compare_to)
    if detection.basis is None:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=detection.message,
            comparison_candidates=list(detection.candidates),
            sheet_name=sheet_name,
        )

    if detection.comparison_column is not None:
        roles[CanonicalRole.BUDGET] = detection.comparison_column
    if detection.actual_column is not None:
        roles[CanonicalRole.ACTUAL] = detection.actual_column

    header_str_row = [str(c).strip() for c in header_row if c is not None]
    period_pairs = detect_period_pairs(header_str_row)

    column_mapping: dict[CanonicalRole, str] = {}
    for role, col_idx in roles.items():
        if col_idx < len(header_row):
            column_mapping[role] = str(header_row[col_idx]).strip()

    ignored_columns = [
        str(header_row[idx]).strip()
        for idx in ignored_col_indices
        if idx < len(header_row) and str(header_row[idx]).strip()
    ]

    visible_transformations: list[str] = []

    if detection.basis != ComparisonBasis.BUDGET and detection.message:
        visible_transformations.append(detection.message)

    if period_pairs:
        chosen_pair = None
        if selected_period is not None:
            chosen_pair = next((p for p in period_pairs if p.period.lower() == selected_period.lower()), None)
        if chosen_pair is None:
            chosen_pair = period_pairs[-1]
        visible_transformations.append(
            f"Analyzed period: {chosen_pair.period} (Budget from '{chosen_pair.budget_column}', Actual from '{chosen_pair.actual_column}')"
        )

    if ignored_columns:
        visible_transformations.append(f"Ignored computed columns: {', '.join(ignored_columns)}")

    for role, orig_name in column_mapping.items():
        _, note = match_column_synonym(orig_name)
        if note:
            visible_transformations.append(note)

    if CanonicalRole.ACCOUNT_ID in column_mapping:
        visible_transformations.append(f"Used '{column_mapping[CanonicalRole.ACCOUNT_ID]}' as the account ID")

    line_item_idx = roles[CanonicalRole.LINE_ITEM]
    budget_idx = roles[CanonicalRole.BUDGET]
    actual_idx = roles[CanonicalRole.ACTUAL]
    acct_id_idx = roles.get(CanonicalRole.ACCOUNT_ID)
    period_idx = roles.get(CanonicalRole.PERIOD)
    curr_idx = roles.get(CanonicalRole.CURRENCY)
    type_idx = roles.get(CanonicalRole.TYPE)

    output_rows: list[dict[str, object]] = []
    problems: list[IntakeProblem] = []
    blank_budget_items: list[str] = []
    dash_count = 0

    data_rows = raw_rows[header_idx + 1:]
    for physical_idx, row in enumerate(data_rows, start=header_row_number + 1):
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        line_item_val = row[line_item_idx] if line_item_idx < len(row) else None
        line_item_str = "" if line_item_val is None else str(line_item_val).strip()
        if not line_item_str:
            problems.append(
                IntakeProblem(
                    row=physical_idx,
                    column=column_mapping.get(CanonicalRole.LINE_ITEM, "Line Item"),
                    line_item="(Blank)",
                    message=f"Row {physical_idx}: Line item description is blank.",
                )
            )
            continue

        raw_budget = row[budget_idx] if budget_idx < len(row) else None
        budget_dec: Decimal | None = None
        try:
            budget_dec, b_note = parse_assisted_decimal(
                raw_budget,
                field="Budget",
                line_item=line_item_str,
                allow_blank=True,
            )
            if b_note == "blank":
                blank_budget_items.append(f"Row {physical_idx}: {line_item_str}")
                if treat_blank_budgets_as_zero:
                    budget_dec = Decimal("0")
            elif b_note and "dash" in b_note:
                dash_count += 1
        except ValueError as exc:
            problems.append(
                IntakeProblem(
                    row=physical_idx,
                    column=column_mapping.get(CanonicalRole.BUDGET, "Budget"),
                    line_item=line_item_str,
                    message=f"Row {physical_idx}, {line_item_str}, Budget column: {exc}",
                )
            )

        raw_actual = row[actual_idx] if actual_idx < len(row) else None
        actual_dec: Decimal | None = None
        try:
            actual_dec, a_note = parse_assisted_decimal(
                raw_actual,
                field="Actual",
                line_item=line_item_str,
                allow_blank=False,
            )
            if a_note and "dash" in a_note:
                dash_count += 1
        except ValueError as exc:
            problems.append(
                IntakeProblem(
                    row=physical_idx,
                    column=column_mapping.get(CanonicalRole.ACTUAL, "Actual"),
                    line_item=line_item_str,
                    message=f"Row {physical_idx}, {line_item_str}, Actual column: {exc}",
                )
            )

        row_dict: dict[str, object] = {
            "line_item": line_item_str,
            "budget": budget_dec if budget_dec is not None else Decimal("0"),
            "actual": actual_dec if actual_dec is not None else Decimal("0"),
        }

        if acct_id_idx is not None and acct_id_idx < len(row):
            acct_val = row[acct_id_idx]
            if acct_val is not None:
                row_dict["account_id"] = str(acct_val).strip()

        if period_idx is not None and period_idx < len(row):
            pval = row[period_idx]
            if pval is not None:
                row_dict["period"] = str(pval).strip()

        if curr_idx is not None and curr_idx < len(row):
            cval = row[curr_idx]
            if cval is not None:
                row_dict["currency"] = str(cval).strip()

        if type_idx is not None and type_idx < len(row):
            tval = row[type_idx]
            if tval is not None:
                row_dict["type"] = str(tval).strip()

        output_rows.append(row_dict)

    if dash_count > 0:
        visible_transformations.append(
            f"Read accounting dashes ('-') as 0 across {dash_count} amount{'s' if dash_count != 1 else ''}"
        )

    if treat_blank_budgets_as_zero and blank_budget_items:
        visible_transformations.append(
            f"Treated blank budgets as 0 on {len(blank_budget_items)} unbudgeted line{'s' if len(blank_budget_items) != 1 else ''}"
        )

    # 1. Unit scaling check (from title block rows and header row)
    raw_title_text = " ".join(
        str(c).strip() for r in raw_rows[:header_idx] for c in r if c is not None and str(c).strip()
    )
    detected_mult = detect_unit_scale(raw_title_text + " " + " ".join(header_str_row))
    if detected_mult != Decimal("1"):
        output_rows = scale_rows_by_unit(output_rows, detected_mult)
        unit_label = "thousands (x1,000)" if detected_mult == Decimal("1000") else "millions (x1,000,000)"
        visible_transformations.append(
            f"Amounts scaled from {unit_label}. Thresholds stay in the reporting unit ($)."
        )

    # 2. Signed ledger check
    signed_det = detect_signed_ledger(output_rows)
    flipped_items: list[str] = []
    if signed_det.is_signed_ledger:
        output_rows, flipped_items = flip_ledger_signs(output_rows, signed_det.negative_revenue_items)
        visible_transformations.append(
            f"Revenue looks like it's stored as negative (credits). Flipped signs to positive-cost convention for {len(flipped_items)} revenue line{'s' if len(flipped_items) != 1 else ''}."
        )

    # 3. Subtotals and totals detection
    subtotals_det = detect_subtotals_and_totals(output_rows)
    reconciled_names = [t.line_item for t in subtotals_det.reconciled_totals]
    if reconciled_names:
        output_rows = [r for r in output_rows if str(r.get("line_item", "")).strip() not in set(reconciled_names)]
        visible_transformations.append(
            f"Detected {len(reconciled_names)} subtotal/total rows: {', '.join(reconciled_names)}. Excluded from line items to avoid double-counting."
        )

    single_periods = detect_single_period_column_values(output_rows)

    return IntakeResult(
        rows=output_rows,
        sheet_name=sheet_name,
        header_row_number=header_row_number,
        column_mapping=column_mapping,
        ignored_columns=ignored_columns,
        rows_read=len(output_rows),
        rows_skipped_count=skipped_count,
        skip_reasons=skip_reasons,
        visible_transformations=visible_transformations,
        problems=problems,
        blank_budget_items=blank_budget_items,
        detected_totals=reconciled_names,
        unreconciled_totals=subtotals_det.unreconciled_totals,
        detected_unit_multiplier=detected_mult,
        detected_signed_ledger=signed_det.is_signed_ledger,
        negative_revenue_items=flipped_items,
        detected_period_pairs=period_pairs,
        detected_single_periods=single_periods,
        raw_headers=header_str_row,
        raw_title_text=raw_title_text,
        comparison_basis=detection.basis,
        comparison_label=detection.label,
        comparison_candidates=list(detection.candidates),
    )


def format_intake_summary(result: IntakeResult) -> str:
    """Generate the 'Here's how I read your file' summary for Maya in plain English."""
    lines: list[str] = ["Here's how I read your file:\n"]

    if result.sheet_name:
        lines.append(f"- **Worksheet:** {result.sheet_name}")

    for t in result.visible_transformations:
        if t.startswith("Analyzed period:"):
            period_name = t.split(":")[1].split("(")[0].strip()
            lines.append(f"- **Analyzed period:** {period_name}")
            break

    lines.append(f"- **Header row:** Row {result.header_row_number}")

    col_details = []
    if CanonicalRole.LINE_ITEM in result.column_mapping:
        col_details.append(f"Line item from '{result.column_mapping[CanonicalRole.LINE_ITEM]}'")
    if CanonicalRole.ACCOUNT_ID in result.column_mapping:
        col_details.append(f"Account ID from '{result.column_mapping[CanonicalRole.ACCOUNT_ID]}'")
    if CanonicalRole.BUDGET in result.column_mapping:
        heading = comparison_heading(result.comparison_basis, result.comparison_label)
        col_details.append(f"{heading} from '{result.column_mapping[CanonicalRole.BUDGET]}'")
    if CanonicalRole.ACTUAL in result.column_mapping:
        col_details.append(f"Actual from '{result.column_mapping[CanonicalRole.ACTUAL]}'")
    lines.append(f"- **Columns mapped:** {', '.join(col_details)}")

    read_text = f"- **Rows read:** {result.rows_read} data row{'s' if result.rows_read != 1 else ''}"
    if result.rows_skipped_count > 0:
        read_text += f" ({result.rows_skipped_count} row{'s' if result.rows_skipped_count != 1 else ''} skipped: {', '.join(result.skip_reasons)})"
    lines.append(read_text)

    if result.detected_totals:
        lines.append(
            f"- **Detected {len(result.detected_totals)} subtotal/total rows:** "
            f"{', '.join(result.detected_totals)} (excluded from line items so they are not double-counted)"
        )

    if result.visible_transformations:
        lines.append("\n**Visible adjustments:**")
        for transform in result.visible_transformations:
            if not transform.startswith("Analyzed period:"):
                lines.append(f"- {transform}")

    if result.problems:
        lines.append("\n⚠️ **Items needing attention:**")
        for prob in result.problems[:5]:
            lines.append(f"- {prob.message}")
        if len(result.problems) > 5:
            lines.append(f"- ...and {len(result.problems) - 5} more items.")

    return "\n".join(lines)


def plain_analysis_error(error_text: str) -> str:
    """Rewrite any technical or exception error message into plain accounting language for Maya."""
    text = error_text.strip()
    # Strip exception type prefixes
    for prefix in ("ValueError:", "RuntimeError:", "KeyError:", "SyntaxError:", "BadZipFile:"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    # Common pattern replacements
    # 1. Missing columns
    m_missing = re.search(r"required field ['\"]?([^'\"]+)['\"]? was not found", text, re.IGNORECASE)
    if m_missing:
        field = m_missing.group(1)
        return f"Could not find a required '{field}' column. Please check your column headers or choose a different worksheet."

    # 2. Blank header / data under blank header
    if "data appears under a blank header" in text.lower():
        return "Some data appears under a blank column header. Please ensure all columns with data have a header name."

    # 3. Normalization conflicts
    if "normalize" in text.lower() or "same key" in text.lower():
        return "Two or more columns have identical or conflicting names. Please use unique column names for each field."

    # 4. Multiple aliases
    if "multiple aliases" in text.lower():
        return "Multiple columns match the same field. Please provide only one column for each field."

    # 5. Archive / XML / DTD / corruption
    if any(term in text.lower() for term in ("archive", "ooxml", "xml", "dtd", "badzipfile", "corrupt")):
        return "The workbook file appears to be damaged or could not be read. Please try saving it again in Excel and re-uploading."

    # 6. Unreconciled summaries
    m_reconcile = re.search(r"Summary\s+([^ ]+)\s+does not reconcile to\s+([^;]+)", text, re.IGNORECASE)
    if m_reconcile:
        summary_name = m_reconcile.group(1).strip("'\"`")
        line_type = m_reconcile.group(2).strip()
        return f"Summary total for '{summary_name}' does not match the sum of its {line_type} detail rows. Please check for missing or overlapping line items."

    # 7. Ambiguous summary label / Row Kind
    if "ambiguous summary label" in text.lower() or "row kind" in text.lower():
        return "Some subtotal or total rows could not be distinguished from detail rows. Please check summary line items."

    # 8. Unclassified items
    if "unclassified" in text.lower():
        text = re.sub(r"\bunclassified\b", "not yet labeled revenue or expense", text, flags=re.IGNORECASE)

    # 9. CLI flags
    text = re.sub(r"--[a-z0-9\-]+", "setting", text)

    # 10. Snake_case keys in quotes
    text = re.sub(r"'([a-z0-9]+)_([a-z0-9_]+)'", r"'\1 \2'", text)

    # 11. Forbidden words
    text = re.sub(r"\bnormalize[sd]?\b", "standardize", text, flags=re.IGNORECASE)
    text = re.sub(r"\baliases?\b", "synonym", text, flags=re.IGNORECASE)
    text = re.sub(r"\bschemas?\b", "structure", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpayload\b", "data", text, flags=re.IGNORECASE)

    return text
