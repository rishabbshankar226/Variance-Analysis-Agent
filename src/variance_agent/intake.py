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

import codecs
import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field, replace
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from enum import StrEnum
from typing import cast

from .classification import infer_line_type
from .currencies import SYMBOL_CURRENCIES
from .excel import WorkbookLoader, cell_value, inspect_archive
from .limits import (
    MAX_CELLS,
    MAX_COLUMNS,
    MAX_INPUT_BYTES,
    MAX_NUMBER_LENGTH,
    MAX_ROWS,
)
from .mapping import LayoutMapping, mapping_sha256
from .models import ComparisonBasis, LineType
from .numeric import financial_context
from .pdf_tables import PdfReadError, extract_statement_tables
from .statement_shape import shape_income_statement
from .measures import measure_kind
from .models import MeasureKind
from .comparison import (
    _ACTUAL_SUFFIX,
    BUDGET_SYNONYMS,
    COMPARISON_WORDS,
    basis_for_header,
    bases_named_in,
    basis_noun,
    comparison_heading,
    comparison_statement,
    order_period_labels,
    parse_period_label,
    select_strict_comparison,
    zero_comparison_phrase,
)
from .parsing import normalize_key


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
    # Bases that --compare-to (or a chat "Compare to ..." reply) can choose to resolve a stop.
    choices: tuple[ComparisonBasis, ...] = ()


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
# Normalized keys the analysis engine reads as line item / budget / actual / type aliases.
_ROLE_ALIAS_KEYS = frozenset({
    "line_item", "line", "item", "account", "account_name", "category",
    "budget", "budget_amount", "plan", "planned", "actual", "actual_amount", "actuals",
    "type", "line_type", "revenue_expense_type", "classification", "period", "currency",
})
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
    # Whether those blank budgets were read as 0 (confirmed in chat; always on for CLI --assisted).
    blank_budgets_as_zero: bool = False
    # Accounting dashes ('-', en/em dash) read as 0, for the audit's zero_reads record.
    dash_count: int = 0
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
    comparison_choices: list[ComparisonBasis] = field(default_factory=list)
    source_kind: str | None = None  # "pdf" when the rows were read out of a PDF statement
    source_pages: tuple[int, ...] = ()
    reader_notes: list[str] = field(default_factory=list)
    comparable_sheets: list[str] = field(default_factory=list)  # PDF statements that can be compared

    def source_document(self) -> dict[str, object] | None:
        """How a PDF statement was read, for the audit record; None for other files."""
        if self.source_kind != "pdf" or self.sheet_name is None:
            return None
        return {"kind": "pdf", "statement": self.sheet_name, "pages": list(self.source_pages),
                "reader_notes": list(self.reader_notes)}

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

    # NFKC folds full-width digits/signs and non-breaking spaces; U+2212 is the typographic minus.
    text = unicodedata.normalize("NFKC", value).strip().replace("\u2212", "-")
    if text in _ACCOUNTING_DASHES:
        return Decimal("0"), f"Read accounting dash '{text}' as 0"

    if text.lower() in {"na", "n/a", "none", "null"}:
        raise ValueError(f"{line_item}: required value in {field} is missing (marked {text}).")

    # "$(1,234)" is the accounting negative with the symbol outside the parentheses.
    if outside := re.fullmatch(r"([$€£])\s*\((.*)\)", text):
        text = f"({outside.group(1)}{outside.group(2)})"

    # ERP exports (SAP, ...) put the sign after the digits: "500.00-" is -500.00.
    trailing_minus = False
    if text.endswith("-") and not text.startswith("("):
        unsigned = _NUMBER_RE.fullmatch(text[:-1].rstrip())
        if unsigned is not None and not any(sign in unsigned["prefix"] for sign in "+-"):
            trailing_minus = True
            text = text[:-1].rstrip()

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

    if negative_parentheses or trailing_minus:
        number = number.copy_negate()

    if not number.is_finite():
        raise ValueError(f"{line_item}: field '{field}' must be a finite number.")
    if len(number.as_tuple().digits) > MAX_NUMBER_LENGTH:
        raise ValueError(f"{line_item}: field '{field}' exceeds the supported numeric length.")

    if trailing_minus:
        return number, f"Read trailing minus sign on '{value.strip()}' as negative"
    if "\u2212" in value:
        return number, f"Read typographic minus sign in '{value.strip()}' as negative"
    return number, None


_PERIOD_RE = re.compile(
    r"\b((?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-_ ]?\d{2,4})|"
    r"(?:Q[1-4](?:[-_ ]?\d{2,4})?)|"
    r"(?:FY\s*\d{2,4})|"
    r"(?:YTD|MTD)|"
    r"(?:\d{4}[-_]\d{2}))\b",
    re.IGNORECASE,
)

_THOUSANDS_RE = re.compile(r"(\(\$000s?\)|in\s+thousands|\(\s*thousands\b|\$000s?|\b000s\b)", re.IGNORECASE)
_MILLIONS_RE = re.compile(r"(\(in\s+millions\)|in\s+millions|\(\s*millions\b|\$m\b|in\s+m\b)", re.IGNORECASE)
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
        # Whole words only: "Contract Value" and "Planning" must not read as Actual or Budget.
        words = set(normalize_header(h).split("_"))
        is_budget_word = bool(words & {"budget", "budgeted", "plan", "planned"})
        if is_budget_word or ComparisonBasis.BUDGET in bases_named_in(normalize_header(h)):
            budget_cols[p] = h
            if p not in period_order:
                period_order.append(p)
        elif words & {"actual", "actuals", "act"}:
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
        if _row_measure(rc) is not MeasureKind.CURRENCY:
            scaled.append(rc)
            continue
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

        inferred, _ = infer_line_type(name)
        is_rev = inferred is LineType.REVENUE or str(r.get("type", "")).lower() == "revenue"
        is_exp = inferred is LineType.EXPENSE or str(r.get("type", "")).lower() == "expense"

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


class _ToleranceIndex:
    """Grid index over (budget, actual) points that answers "which stored point lies within
    the tolerance of this one?" without comparing against every stored point.

    Cells are twice the tolerance wide, so any point within the tolerance of a query lies in
    the query's cell or one of its eight neighbours. Candidates are always re-checked with the
    exact ``<=`` comparison, so the grid only prunes.
    """

    def __init__(self) -> None:
        self._cells: dict[tuple[int, int], list[int]] = {}
        self._points: list[tuple[Decimal, Decimal]] = []

    @staticmethod
    def _cell(value: Decimal) -> int:
        # Units of 0.01, two per cell; scaleb only moves the exponent, so it is exact.
        return int(value.scaleb(2).to_integral_value(rounding=ROUND_FLOOR)) // 2

    def add(self, budget: Decimal, actual: Decimal) -> None:
        self._cells.setdefault((self._cell(budget), self._cell(actual)), []).append(len(self._points))
        self._points.append((budget, actual))

    def find(
        self,
        budget: Decimal,
        actual: Decimal,
        tolerance: Decimal,
        *,
        newest_first: bool,
        max_position: int | None = None,
        skip: int | None = None,
    ) -> int | None:
        """Position of the newest (or oldest) stored point within ``tolerance`` of the query."""
        base_b, base_a = self._cell(budget), self._cell(actual)
        best: int | None = None
        for cell_b in (base_b - 1, base_b, base_b + 1):
            for cell_a in (base_a - 1, base_a, base_a + 1):
                positions = self._cells.get((cell_b, cell_a))
                if not positions:
                    continue
                for position in (reversed(positions) if newest_first else positions):
                    if max_position is not None and position > max_position:
                        if newest_first:
                            continue
                        break
                    if position == skip:
                        continue
                    point_b, point_a = self._points[position]
                    if abs(point_b - budget) <= tolerance and abs(point_a - actual) <= tolerance:
                        if best is None or (position > best if newest_first else position < best):
                            best = position
                        break
        return best


def detect_subtotals_and_totals(rows: list[dict[str, object]]) -> SubtotalDetectionResult:
    """Detect contiguous block subtotals and nested formula totals within 0.01 tolerance.

    A row is a block subtotal when it equals the sum of the detail rows just above it (two or
    more rows, or one row when its label says total), and a formula total when it equals a
    prior total minus a detail row or minus another prior total. Both searches use tolerance
    indexes, so detection stays near-linear on ledgers of tens of thousands of rows.
    """
    tolerance = Decimal("0.01")
    reconciled_totals: list[ReconciledTotal] = []
    unreconciled_totals: list[UnreconciledTotal] = []
    detail_indices: list[int] = []  # row index of each detail row, in order
    details = _ToleranceIndex()  # (budget, actual) of each detail row
    totals = _ToleranceIndex()  # (budget, actual) of each reconciled total
    # prefix holds, at position j, the (budget, actual) sum of the first j detail rows, so the
    # sum of the last L detail rows is prefix[m] - prefix[m - L].
    prefix = _ToleranceIndex()
    prefix.add(Decimal("0"), Decimal("0"))
    running_b = Decimal("0")
    running_a = Decimal("0")

    for i, row in enumerate(rows):
        name = str(row.get("line_item", "")).strip()
        b_raw = row.get("budget")
        a_raw = row.get("actual")
        b = Decimal(str(b_raw)) if b_raw is not None else Decimal("0")
        a = Decimal(str(a_raw)) if a_raw is not None else Decimal("0")
        is_total_kw = bool(_TOTAL_KEYWORD_RE.search(name))
        detail_count = len(detail_indices)

        # 1. Contiguous block check: the smallest block of prior detail rows that sums to this row.
        start = prefix.find(
            running_b - b, running_a - a, tolerance, newest_first=True,
            max_position=detail_count - 1 if is_total_kw else detail_count - 2,
        )
        if start is not None:
            reconciled_totals.append(
                ReconciledTotal(
                    line_item=name, budget=b, actual=a, row_index=i,
                    formula_description=f"sum of {detail_count - start} detail rows",
                )
            )
            totals.add(b, a)
            continue

        # 2. Nested formula check (a prior total minus a detail row, or minus another prior total)
        prior_total_count = len(reconciled_totals)
        found_formula = False
        for prev_position in range(prior_total_count):
            prev = reconciled_totals[prev_position]
            wanted_b, wanted_a = prev.budget - b, prev.actual - a
            detail_position = details.find(wanted_b, wanted_a, tolerance, newest_first=False)
            if detail_position is not None:
                subtracted = str(rows[detail_indices[detail_position]].get("line_item"))
            else:
                other = totals.find(
                    wanted_b, wanted_a, tolerance, newest_first=False,
                    max_position=prior_total_count - 1, skip=prev_position,
                )
                if other is None:
                    continue
                subtracted = reconciled_totals[other].line_item
            reconciled_totals.append(
                ReconciledTotal(
                    line_item=name, budget=b, actual=a, row_index=i,
                    formula_description=f"{prev.line_item} - {subtracted}",
                )
            )
            totals.add(b, a)
            found_formula = True
            break
        if found_formula:
            continue

        if is_total_kw:
            unreconciled_totals.append(
                UnreconciledTotal(
                    line_item=name, budget=b, actual=a, row_index=i,
                    sum_budget=running_b if detail_count else None,
                    sum_actual=running_a if detail_count else None,
                )
            )
        else:
            detail_indices.append(i)
            details.add(b, a)
            running_b += b
            running_a += a
            prefix.add(running_b, running_a)

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
            elif role == CanonicalRole.LINE_ITEM and role in roles:
                # "Category" usually groups accounts; a column that names them wins over it.
                if (normalize_header(str(row[roles[role]])) == "category"
                        and normalize_header(cell_str) != "category"):
                    roles[role] = col_idx
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
                # Fill only the roles a named column has not already taken.
                free = [c for c in period_cols if c not in roles.values()]
                for role in (CanonicalRole.ACTUAL, CanonicalRole.BUDGET):
                    if role not in roles and free:
                        roles[role] = free.pop(0)
                if CanonicalRole.BUDGET in roles and CanonicalRole.ACTUAL in roles:
                    return row_idx, roles, ignored

    return None, {}, []


_COVER_SHEET_WORDS = frozenset({
    "cover", "page", "sheet", "contents", "table", "of", "readme", "read", "me", "notes", "index", "summary",
})


def rank_workbook_sheets(
    sheets: list[tuple[str, list[list[object]]]],
    *,
    basis: ComparisonBasis = ComparisonBasis.BUDGET,
    label: str | None = None,
) -> list[SheetScore]:
    """Score worksheets in a workbook to rank the best candidate for budget-vs-actual analysis.

    ``basis``/``label`` only change the wording of each rationale, never the scores.
    """
    heading = comparison_heading(basis, label)
    noun = basis_noun(basis)
    scores: list[SheetScore] = []
    for name, rows in sheets:
        score = 0
        reasons = []

        header_idx, roles, _ = detect_header_row(rows)
        if header_idx is not None:
            score += 20
            reasons.append(f"contains Line item, {heading}, and Actual columns")
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
        if set(re.findall(r"[a-z]+", lower_name)) <= _COVER_SHEET_WORDS:  # "Index", not "Price Index"
            score -= 15
            reasons.append("title suggests cover page or notes")

        if "bva" in lower_name or "variance" in lower_name or "p&l" in lower_name or "pnl" in lower_name:
            score += 10
            reasons.append(f"title matches {noun}-vs-actual or P&L")

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
    return cast(WorkbookLoader, getattr(module, "load_workbook"))  # noqa: B009 (dynamic optional import)


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


def _column_name(index: int) -> str:
    """Spreadsheet-style column name for a zero-based index: 0 -> 'column A', 27 -> 'column AB'."""
    letters = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return f"column {letters}"


def _stop(
    message: str,
    *,
    actual_column: int | None = None,
    candidates: list[str] | tuple[str, ...] = (),
    choices: list[ComparisonBasis] | tuple[ComparisonBasis, ...] = (),
) -> ComparisonDetection:
    """A detection that stops intake and asks, naming the candidates."""
    return ComparisonDetection(
        basis=None,
        label=None,
        comparison_column=None,
        actual_column=actual_column,
        candidates=tuple(candidates),
        message=message,
        choices=tuple(choices),
    )


def _ask_which(candidates: list[str]) -> str:
    return (
        f"This file has more than one column to compare against ({', '.join(candidates)}). "
        "Which should Actual be compared against?"
    )


def _carries_period(header: str) -> bool:
    """True when a header names a period, even alongside words such as 'Forecast'."""
    if _PERIOD_RE.search(header):
        return True
    words = [
        w for w in normalize_header(header).split("_")
        if w and w not in COMPARISON_WORDS and w not in _ACTUAL_SYNONYMS
    ]
    return bool(words) and parse_period_label(" ".join(words)) is not None


@dataclass(frozen=True)
class _PeriodColumns:
    """Period-only amount columns (FY2025, 2024 ...) and what blocks reading them."""

    columns: list[tuple[int, str, str]]  # (column index, header, period label)
    ordered: list[str] | None  # labels newest first, or None when unorderable
    blockers: list[tuple[int, str]]  # period headers that also name a comparison ('FY2025 Forecast')
    has_explicit_actual: bool  # an undated Actual column sits beside the period columns

    @property
    def ambiguous(self) -> bool:
        return bool(self.blockers) or self.has_explicit_actual

    @property
    def usable(self) -> bool:
        return bool(self.columns) and not self.ambiguous and self.ordered is not None

    def candidate_headers(self) -> list[tuple[int, str]]:
        """Columns Actual could be compared against: the newest is Actual unless one is named."""
        cols = [(idx, header) for idx, header, _ in self.columns]
        if self.ordered is not None and not self.has_explicit_actual:
            newest = self.ordered[0]
            cols = [(idx, header) for idx, header, label in self.columns if label != newest]
        return sorted(cols + self.blockers)


def _period_columns(headers: list[tuple[int, str]]) -> _PeriodColumns:
    columns: list[tuple[int, str, str]] = []
    # Wide budget-vs-actual layouts (period pairs) never take the period-only path.
    if not detect_period_pairs([s for _, s in headers]):
        for idx, s in headers:
            stripped = _ACTUAL_SUFFIX.sub("", s).strip()
            if parse_period_label(stripped) is not None:
                columns.append((idx, s, stripped))
    if len(columns) < 2:
        return _PeriodColumns([], None, [], False)
    period_idx = {idx for idx, _, _ in columns}
    blockers: list[tuple[int, str]] = []
    has_explicit_actual = False
    for idx, s in headers:
        norm = normalize_header(s)
        if idx in period_idx or basis_for_header(norm) is not None:
            continue
        if norm in _ACTUAL_SYNONYMS:
            has_explicit_actual = True
        elif bases_named_in(norm) and _carries_period(s):
            blockers.append((idx, s))
    ordered = order_period_labels([label for _, _, label in columns])
    return _PeriodColumns(columns, ordered, blockers, has_explicit_actual)


def _period_detection(periods: _PeriodColumns) -> ComparisonDetection:
    """Read period-only columns as newest = Actual, next newest = Prior Period, or ask."""
    if periods.ambiguous:
        names = [h for _, h in periods.candidate_headers()]
        return _stop(_ask_which(names), candidates=names)
    labels = [label for _, _, label in periods.columns]
    if periods.ordered is None:
        return _stop(
            f"Could not determine period order for {', '.join(labels)}.",
            candidates=labels,
        )
    label_to_col = {label: idx for idx, _, label in periods.columns}
    newest, second = periods.ordered[0], periods.ordered[1]
    return ComparisonDetection(
        basis=ComparisonBasis.PRIOR_PERIOD,
        label=second,
        comparison_column=label_to_col[second],
        actual_column=label_to_col[newest],
        candidates=(),
        message=comparison_statement(
            ComparisonBasis.PRIOR_PERIOD,
            label=second,
            actual_label=newest,
            all_periods=periods.ordered,
        ),
    )


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
    actual_headers: list[str] = []
    for idx, s in headers:
        norm = normalize_header(s)
        if norm in _ACTUAL_SYNONYMS:
            actual_headers.append(f"{s} ({_column_name(idx)})")
            if actual_col is None:
                actual_col = idx
                actual_label = s

    named: list[tuple[int, str, ComparisonBasis]] = []
    for idx, s in headers:
        b = basis_for_header(normalize_header(s))
        if b is not None:
            named.append((idx, s, b))
    periods = _period_columns(headers)

    def choose_named(col_idx: int, basis: ComparisonBasis) -> ComparisonDetection:
        act_col, act_label = actual_col, actual_label
        if act_col is None and periods.usable and periods.ordered is not None:
            # No Actual column: the newest period column is the Actual.
            act_label = periods.ordered[0]
            act_col = next(idx for idx, _, label in periods.columns if label == act_label)
        return ComparisonDetection(
            basis=basis,
            label=None,
            comparison_column=col_idx,
            actual_column=act_col,
            candidates=(),
            message=comparison_statement(basis, None, act_label),
        )

    if len(actual_headers) > 1 and not detect_period_pairs([s for _, s in headers]):
        # Which one is the Actual (this month, year to date, ...) is the user's call.
        return _stop(
            f"Found more than one Actual column ({', '.join(actual_headers)}); keep one and try again.",
            actual_column=actual_col,
            candidates=actual_headers,
        )

    def not_found(basis: ComparisonBasis) -> ComparisonDetection:
        return _stop(
            f"No {basis_noun(basis)} column found. Columns found: {all_headers_display}.",
            actual_column=actual_col,
        )

    if compare_to is not None:
        matched = [c for c in named if c[2] == compare_to]
        if len(matched) > 1:
            col_names = [c[1] for c in matched]
            return _stop(
                f"Found more than one {basis_noun(compare_to)} column ({', '.join(col_names)}); "
                "keep one and rerun.",
                actual_column=actual_col,
                candidates=col_names,
            )
        if matched:
            return choose_named(matched[0][0], compare_to)
        if compare_to is ComparisonBasis.PRIOR_PERIOD and periods.columns:
            return _period_detection(periods)
        if named or periods.columns or compare_to is not ComparisonBasis.BUDGET:
            return not_found(compare_to)
        return ComparisonDetection(
            basis=ComparisonBasis.BUDGET,
            label=None,
            comparison_column=None,
            actual_column=actual_col,
            candidates=(),
            message="",
        )

    named_bases: list[ComparisonBasis] = []
    for _, _, b in named:
        if b not in named_bases:
            named_bases.append(b)

    # 1. Named columns and period-only columns together: ask, never guess.
    if named and periods.columns:
        choices = list(named_bases)
        if periods.usable and ComparisonBasis.PRIOR_PERIOD not in choices:
            choices.append(ComparisonBasis.PRIOR_PERIOD)
        cols = sorted([(idx, s) for idx, s, _ in named] + periods.candidate_headers())
        names = [s for _, s in cols]
        return _stop(_ask_which(names), actual_column=actual_col, candidates=names, choices=choices)

    # 2. Named columns only.
    if named:
        if len(named_bases) > 1:
            col_names = [c[1] for c in named]
            return _stop(
                _ask_which(col_names), actual_column=actual_col, candidates=col_names, choices=named_bases,
            )
        # Different names for one basis (Budget, Plan) take the first; an exact repeat is a mistake.
        repeated = len({normalize_header(c[1]) for c in named}) < len(named)
        if repeated and not detect_period_pairs([s for _, s in headers]):
            col_names = [f"{c[1]} ({_column_name(c[0])})" for c in named]
            return _stop(
                f"Found more than one {basis_noun(named_bases[0])} column ({', '.join(col_names)}); "
                "keep one and try again.",
                actual_column=actual_col,
                candidates=col_names,
            )
        return choose_named(named[0][0], named[0][2])

    # 3. Period-only columns.
    if periods.columns:
        return _period_detection(periods)

    # 4. Fallback
    return ComparisonDetection(
        basis=ComparisonBasis.BUDGET,
        label=None,
        comparison_column=None,
        actual_column=actual_col,
        candidates=(),
        message="",
    )


def _decode_text(data: bytes, filename: str) -> tuple[str, str | None]:
    """Decode CSV/TSV bytes without ever substituting replacement characters.

    UTF-16 (with a byte-order mark) and UTF-8 (with or without one) are read silently;
    Windows-1252, the usual encoding of Excel "CSV" exports on Windows, is read with a note;
    anything else is refused rather than corrupted.
    """
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        try:
            return data.decode("utf-16"), None
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8-sig"), None
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1252"), (
            "Read the file as Windows-1252 text because it is not valid UTF-8. "
            "Check that accented letters and currency symbols look right."
        )
    except UnicodeDecodeError:
        raise ValueError(
            f"I could not read '{filename}' as text. Save it as a UTF-8 CSV "
            "(in Excel: Save As, then CSV UTF-8) and upload it again."
        ) from None


@financial_context()
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
    if norm_suffix in {".tsv", ".txt", ".csv"}:
        try:
            text, encoding_note = _decode_text(data, filename)
        except ValueError as exc:
            return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc))
        reader = _read_tsv_text if norm_suffix != ".csv" else _read_csv_text
        result = reader(
            text, filename, treat_blank_budgets_as_zero, selected_period, compare_to=compare_to,
        )
        if encoding_note and not result.has_fatal_errors:
            result.visible_transformations.insert(0, encoding_note)
        return result
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
    if norm_suffix == ".pdf":
        return _read_pdf_bytes(
            data,
            filename,
            sheet,
            treat_blank_budgets_as_zero,
            selected_period,
            compare_to=compare_to,
        )

    return IntakeResult(
        has_fatal_errors=True,
        fatal_error_message=(
            f"Unsupported input format '{suffix}'. Please use an Excel workbook (.xlsx, .xlsm), "
            "a CSV, TSV, JSON or PDF file."
        ),
    )


_CANDIDATE_DELIMITERS = (",", ";", "\t", "|")


def _sniff_delimiter(text: str) -> str:
    """Pick the delimiter that splits the first lines into the most consistent 3+ columns.

    European Excel exports use ";" because "," is the decimal mark; ties keep the comma.
    """
    sample = text[:65536]
    best, best_lines = ",", 0
    for delimiter in _CANDIDATE_DELIMITERS:
        try:
            widths = [
                len(record)
                for record in csv.reader(io.StringIO(sample, newline=""), delimiter=delimiter)
                if record
            ][:50]
        except csv.Error:
            continue
        if not widths:
            continue
        modal = max(set(widths), key=lambda width: (widths.count(width), width))
        if modal >= 3 and widths.count(modal) > best_lines:
            best, best_lines = delimiter, widths.count(modal)
    return best


def _delimited_rows(text: str, delimiter: str, filename: str) -> list[list[object]]:
    """Split delimited text into rows, keeping quoted newlines and enforcing the input limits.

    Blank lines are kept as empty rows so that row numbers in messages match the file.
    """
    rows: list[list[object]] = []
    cells = 0
    try:
        for record in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter):
            if len(record) > MAX_COLUMNS:
                raise ValueError(
                    f"'{filename}' has more than {MAX_COLUMNS} columns, which is more than I can read."
                )
            cells += len(record)
            if len(rows) >= MAX_ROWS or cells > MAX_CELLS:
                raise ValueError(
                    f"'{filename}' has more rows or cells than I can read "
                    f"(limits: {MAX_ROWS:,} rows and {MAX_CELLS:,} cells)."
                )
            rows.append(cast(list[object], record))
    except csv.Error as exc:
        raise ValueError(f"I could not split '{filename}' into columns: {exc}.") from exc
    return rows


def _read_tsv_text(
    text: str,
    filename: str,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
) -> IntakeResult:
    try:
        raw_rows = _delimited_rows(text, "\t", filename)
    except ValueError as exc:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc))
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
    try:
        raw_rows = _delimited_rows(text, _sniff_delimiter(text), filename)
    except ValueError as exc:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc))
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
        rows = load_json_text(data.decode("utf-8-sig"))
        basis = compare_to if compare_to is not None else ComparisonBasis.BUDGET
        if basis != ComparisonBasis.BUDGET:
            try:
                rows = select_strict_comparison(rows, basis)
            except ValueError as exc:
                # The comparison-column error is already user-facing; no read-error prefix.
                return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc))
        # JSON rows are already named; keep every field (Type, Row Kind, drivers) for analysis.
        canonical_rows: list[dict[str, object]] = [dict(r) for r in rows]
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


def _hidden_sheets_last(ranked: list[SheetScore], hidden: set[str]) -> list[SheetScore]:
    """Visible worksheets first (a hidden draft must not win automatically), order otherwise kept."""
    marked = [
        replace(s, rationale=f"{s.rationale}; hidden worksheet") if s.name in hidden else s for s in ranked
    ]
    return sorted(marked, key=lambda s: s.name in hidden)


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
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ValueError) else ""
        if any(term in reason for term in ("worksheet exceeds", "physical rows", "physical coordinates")):
            # A very large sheet, hidden or not, makes the whole workbook unsafe to read.
            message = (
                f"The Excel file '{filename}' has a worksheet larger than I can read "
                f"(at most {MAX_ROWS:,} rows and {MAX_CELLS:,} cells on any sheet, hidden sheets included). "
                "Export the sheet you need to CSV, or save a copy without the large sheet."
            )
        else:
            message = f"The Excel file '{filename}' could not be opened safely."
        return IntakeResult(has_fatal_errors=True, fatal_error_message=message)

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
            hidden = {n for n in sheetnames if getattr(wb[n], "sheet_state", "visible") != "visible"}
            if hidden:
                ranked = _hidden_sheets_last(ranked, hidden)

            # If user explicitly specified sheet, use that; otherwise pick top ranked sheet
            chosen_sheet = sheet
            if chosen_sheet is None:
                chosen_sheet = ranked[0].name if ranked else sheetnames[0]
            elif chosen_sheet not in sheetnames:
                return IntakeResult(
                    has_fatal_errors=True,
                    fatal_error_message=(
                        f"Worksheet '{chosen_sheet}' was not found in '{filename}'. "
                        f"Available sheets: {', '.join(sheetnames)}."
                    ),
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
            if result.comparison_basis is not ComparisonBasis.BUDGET:
                # Same scores; the rationale names the comparison this file was read against.
                ranked = rank_workbook_sheets(
                    all_sheets_raw, basis=result.comparison_basis, label=result.comparison_label
                )
                if hidden:
                    ranked = _hidden_sheets_last(ranked, hidden)
            result.candidate_sheets = ranked
            result.available_sheets = sheetnames
            if chosen_sheet != sheetnames[0] and ranked:
                rationale = (
                    ranked[0].rationale if ranked[0].name == chosen_sheet
                    else f"better matches {basis_noun(result.comparison_basis)}-vs-actual data"
                )
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


_STATEMENT_KINDS = (
    # (pattern, score, rationale): an income statement is the usual variance target.
    (re.compile(r"comprehensive", re.IGNORECASE), 5, "comprehensive income statement"),
    (re.compile(r"operations|income|earnings", re.IGNORECASE), 30, "income statement"),
    (re.compile(r"balance\s+sheet|financial\s+position", re.IGNORECASE), 20, "balance sheet"),
    (re.compile(r"cash\s+flows?", re.IGNORECASE), 10, "cash flow statement"),
)


_NOT_REVENUE_AND_EXPENSE = {
    "balance_sheet": "assets, liabilities and equity",
    "cash_flow": "cash coming in and going out",
}


def rank_statements(names: list[str]) -> list[SheetScore]:
    """Order statements read from a PDF: income statement first, then balance sheet, cash flows."""
    scores = []
    for name in names:
        score, rationale = 0, "financial statement"
        for pattern, kind_score, kind in _STATEMENT_KINDS:
            if pattern.search(name):
                score, rationale = kind_score, kind
                break
        scores.append(SheetScore(name=name, score=score, rationale=rationale))
    scores.sort(key=lambda s: s.score, reverse=True)  # stable: page order breaks ties
    return scores


def _read_pdf_bytes(
    data: bytes,
    filename: str,
    sheet: str | None,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
) -> IntakeResult:
    """Read one statement from a 10-K / 10-Q style PDF; each statement acts like a worksheet."""
    try:
        tables = extract_statement_tables(data, filename)
    except PdfReadError as exc:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc))

    names = [t.name for t in tables]
    ranked = rank_statements(names)
    chosen_name = ranked[0].name if sheet is None else sheet
    chosen = next((t for t in tables if t.name == chosen_name), None)
    if chosen is None:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=(
                f"No statement called '{sheet}' was found in '{filename}'. "
                f"Statements found: {', '.join(names)}."
            ),
            available_sheets=names,
            source_kind="pdf",
        )
    if chosen.kind in _NOT_REVENUE_AND_EXPENSE:
        income = [t.name for t in tables if t.kind not in _NOT_REVENUE_AND_EXPENSE]
        instead = f" Choose an income statement instead: {', '.join(income)}." if income else ""
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=(
                f"'{chosen.name}' lists {_NOT_REVENUE_AND_EXPENSE[chosen.kind]}, which can't be "
                f"compared as revenue and expense yet.{instead}"
            ),
            available_sheets=income,  # the statements that can be chosen instead
            source_kind="pdf",
        )

    shaped = shape_income_statement(chosen.raw_rows)
    result = _process_raw_table(
        shaped.rows,
        filename,
        sheet_name=chosen.name,
        treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
        selected_period=selected_period,
        compare_to=compare_to,
        signs_resolved=shaped.shaped,
        from_pdf=True,
    )
    result.source_kind = "pdf"
    result.source_pages = chosen.page_numbers
    result.reader_notes = [*chosen.notes, *shaped.audit_notes]
    result.candidate_sheets = ranked
    result.available_sheets = names
    result.comparable_sheets = [t.name for t in tables if t.kind not in _NOT_REVENUE_AND_EXPENSE]
    # Statement subtotals are excluded like detected totals, so the audit records them too.
    result.detected_totals[:0] = shaped.subtotals
    result.visible_transformations[:0] = [
        f"Read '{chosen.name}' from the PDF", *chosen.notes, *shaped.notes]
    return result


_MAX_LISTED_CELLS = 10


def _plain_cell_detail(detail: str, field_label: str) -> str:
    """Say what is wrong with a cell the way a person would, not in parser terms."""
    if match := re.search(r"has an unrecognized number format: (.*)\.$", detail):
        return f"'{match.group(1)}' is not an amount I can read."
    if match := re.search(r"is missing \(marked (.+)\)\.$", detail):
        return f"the amount is marked {match.group(1)}."
    if detail.startswith("required value in") and "is missing" in detail:
        return "the amount is blank."
    return detail


def _cell_problem(
    row: int, line_item: str, column: str | None, field_label: str, exc: ValueError,
) -> IntakeProblem:
    """A problem for one amount that could not be read, worded for the person who must fix it."""
    detail = _plain_cell_detail(str(exc).removeprefix(f"{line_item}: "), field_label)
    return IntakeProblem(
        row=row,
        column=column,
        line_item=line_item,
        message=f"Row {row}, {line_item}, {field_label} column: {detail}",
        technical_detail=str(exc),
    )


def _unreadable_cells_message(filename: str, cells: list[IntakeProblem], *, from_pdf: bool = False) -> str:
    """Stop-and-fix message for amounts that cannot be read (never read as 0)."""
    if from_pdf:
        lines = [
            f"I could not read every figure in the PDF '{filename}' as a number, so I stopped "
            "instead of guessing. A footnote marker or stray symbol next to a figure is the usual "
            "cause. Upload an Excel or CSV copy of the statement, or check these figures:"
        ]
    else:
        lines = [
            f"I could not read every amount in '{filename}', so I stopped instead of guessing. "
            "Fix these cells and upload the file again:"
        ]
    lines.extend(f"- {cell.message}" for cell in cells[:_MAX_LISTED_CELLS])
    if len(cells) > _MAX_LISTED_CELLS:
        lines.append(f"- ...and {len(cells) - _MAX_LISTED_CELLS} more.")
    return "\n".join(lines)


def _process_raw_table(
    raw_rows: list[list[object]],
    filename: str,
    sheet_name: str | None,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
    signs_resolved: bool = False,
    from_pdf: bool = False,
) -> IntakeResult:
    """Map, parse and check one table of rows. ``signs_resolved`` marks rows from a shaped
    financial statement: their signs are settled and their subtotals already removed, so the
    signed-ledger flip and sum-based subtotal detection are skipped."""
    if not raw_rows:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=f"The file '{filename}' contains no data.",
            sheet_name=sheet_name,
        )

    header_idx, roles, ignored_col_indices = detect_header_row(raw_rows, selected_period=selected_period)
    if header_idx is None:
        if compare_to is None:
            message = (
                f"Could not find a header row with Line Item, Budget, and Actual columns in '{filename}' "
                "(a Forecast or Prior Year column can stand in for Budget)."
            )
        else:
            message = (
                f"Could not find a header row with Line Item, {comparison_heading(compare_to, None)}, "
                f"and Actual columns in '{filename}'."
            )
        return IntakeResult(has_fatal_errors=True, fatal_error_message=message, sheet_name=sheet_name)

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
            comparison_choices=list(detection.choices),
            sheet_name=sheet_name,
        )

    comparison_field = comparison_heading(detection.basis, detection.label)

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

    for orig_name in column_mapping.values():
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

    # Columns without a canonical role (Row Kind, volume/price drivers, ...) pass through
    # unchanged so analysis still sees them; aliases of mapped roles are left out.
    mapped = set(roles.values()) | set(ignored_col_indices)
    passthrough = [
        (idx, str(header_row[idx]).strip())
        for idx in range(len(header_row))
        if idx not in mapped and header_row[idx] is not None and str(header_row[idx]).strip()
        and normalize_key(str(header_row[idx])) not in _ROLE_ALIAS_KEYS
    ]

    output_rows: list[dict[str, object]] = []
    problems: list[IntakeProblem] = []
    unreadable_cells: list[IntakeProblem] = []  # amounts that must never be read as 0
    blank_budget_items: list[str] = []
    dash_count = 0
    minus_count = 0  # trailing / typographic minus signs read as negative

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

        measure_column = next((i for i, h in enumerate(header_row) if h is not None and normalize_key(str(h)) == "measure"), None)
        try:
            kind = measure_kind(row[measure_column] if measure_column is not None and measure_column < len(row) else None,
                                line_item_str)
        except ValueError as exc:
            return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc))
        raw_budget = row[budget_idx] if budget_idx < len(row) else None
        budget_dec: Decimal | None = None
        try:
            budget_dec, b_note = parse_assisted_decimal(
                _rate_number(raw_budget, kind),
                field=comparison_field,
                line_item=line_item_str,
                allow_blank=True,
            )
            if b_note == "blank":
                blank_budget_items.append(f"Row {physical_idx}: {line_item_str}")
                if treat_blank_budgets_as_zero:
                    budget_dec = Decimal("0")
            elif b_note and "dash" in b_note:
                dash_count += 1
            elif b_note and "minus" in b_note:
                minus_count += 1
        except ValueError as exc:
            problem = _cell_problem(
                physical_idx, line_item_str,
                column_mapping.get(CanonicalRole.BUDGET, comparison_field), comparison_field, exc,
            )
            problems.append(problem)
            unreadable_cells.append(problem)

        raw_actual = row[actual_idx] if actual_idx < len(row) else None
        actual_dec: Decimal | None = None
        try:
            actual_dec, a_note = parse_assisted_decimal(
                _rate_number(raw_actual, kind),
                field="Actual",
                line_item=line_item_str,
                allow_blank=False,
            )
            if a_note and "dash" in a_note:
                dash_count += 1
            elif a_note and "minus" in a_note:
                minus_count += 1
        except ValueError as exc:
            problem = _cell_problem(
                physical_idx, line_item_str,
                column_mapping.get(CanonicalRole.ACTUAL, "Actual"), "Actual", exc,
            )
            problems.append(problem)
            unreadable_cells.append(problem)

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

        for idx, header in passthrough:
            value = row[idx] if idx < len(row) else None
            if value is not None and str(value).strip():
                row_dict[header] = value

        if kind is MeasureKind.PERCENT:
            # Preserve the explicit percent sign / bare scale until a flag or chat confirmation settles it.
            row_dict["budget"] = raw_budget
            row_dict["actual"] = raw_actual
            if any(str(value).strip().endswith("%") for value in (raw_budget, raw_actual)):
                visible_transformations.append(f"{line_item_str}: read % values as percentage points.")
        if measure_column is not None:
            visible_transformations.append(f"{line_item_str}: read Measure as {kind}.")
            better_value = next((row[i] for i, h in enumerate(header_row)
                                 if h is not None and normalize_key(str(h)) == "better" and i < len(row)), None)
            if kind is MeasureKind.PER_SHARE and not str(better_value or "").strip():
                visible_transformations.append(f"{line_item_str}: defaulted Better to Higher.")
            elif str(better_value or "").strip():
                visible_transformations.append(f"{line_item_str}: read Better as {better_value}.")
        output_rows.append(row_dict)

    if unreadable_cells:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=_unreadable_cells_message(filename, unreadable_cells, from_pdf=from_pdf),
            problems=problems,
            sheet_name=sheet_name,
            header_row_number=header_row_number,
            column_mapping=column_mapping,
            comparison_basis=detection.basis,
            comparison_label=detection.label,
        )

    if dash_count > 0:
        visible_transformations.append(
            f"Read accounting dashes ('-') as 0 across {dash_count} amount{'s' if dash_count != 1 else ''}"
        )
    if minus_count > 0:
        visible_transformations.append(
            f"Read a trailing or typographic minus sign (for example '500.00-') as a negative "
            f"amount across {minus_count} amount{'s' if minus_count != 1 else ''}"
        )

    if treat_blank_budgets_as_zero and blank_budget_items:
        count = len(blank_budget_items)
        plural = "s" if count != 1 else ""
        if detection.basis is ComparisonBasis.BUDGET:
            visible_transformations.append(f"Treated blank budgets as 0 on {count} unbudgeted line{plural}")
        else:
            visible_transformations.append(
                f"Treated blank {basis_noun(detection.basis)} values as 0 on {count} "
                f"line{plural} {zero_comparison_phrase(detection.basis)}"
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
            f"Amounts scaled from {unit_label}. Thresholds stay in the reporting unit "
            "(full currency units, not thousands)."
        )

    # 2. Signed ledger check
    signed_det = (SignedLedgerDetection(False, 0, [])
                  if signs_resolved else detect_signed_ledger([r for r in output_rows if _row_measure(r) is MeasureKind.CURRENCY]))
    flipped_items: list[str] = []
    if signed_det.is_signed_ledger:
        output_rows, flipped_items = flip_ledger_signs(output_rows, signed_det.negative_revenue_items)
        visible_transformations.append(
            "Revenue looks like it's stored as negative (credits). Flipped signs to positive-cost "
            f"convention for {len(flipped_items)} revenue line{'s' if len(flipped_items) != 1 else ''}."
        )

    # 3. Subtotals and totals detection. An explicit Row Kind column already marks totals,
    # and the analysis reconciles and excludes those rows itself, so they are kept.
    has_row_kind = any(normalize_key(header) == "row_kind" for _, header in passthrough)
    subtotals_det = (
        SubtotalDetectionResult(reconciled_totals=[], unreconciled_totals=[])
        if has_row_kind or signs_resolved
        else detect_subtotals_and_totals([r for r in output_rows if _row_measure(r) is MeasureKind.CURRENCY])
    )
    reconciled_names = [t.line_item for t in subtotals_det.reconciled_totals]
    if reconciled_names:
        output_rows = [r for r in output_rows
                       if _row_measure(r) is not MeasureKind.CURRENCY
                       or str(r.get("line_item", "")).strip() not in set(reconciled_names)]
        visible_transformations.append(
            f"Detected {len(reconciled_names)} subtotal/total rows: {', '.join(reconciled_names)}. "
            "Excluded from line items to avoid double-counting."
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
        blank_budgets_as_zero=treat_blank_budgets_as_zero,
        dash_count=dash_count,
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


def audit_transformations(
    intake_res: IntakeResult, mapping: LayoutMapping | None = None,
) -> dict[str, object]:
    """The audit's transformations record: what assisted intake did to the file.

    Shared by the CLI (--assisted, --mapping) and the chat's audit export. A mapping adds only
    what it alone decides (period selection, classification rules, its own digest); the header
    row, columns, scale, sign flips and exclusions are what intake actually applied. The CLI
    folds the mapping's own scale, flips and exclusions into ``intake_res`` first.
    """
    blank_budgets = len(intake_res.blank_budget_items) if intake_res.blank_budgets_as_zero else 0
    return {
        "header_row_number": intake_res.header_row_number,
        "column_mapping": {role.value: name for role, name in intake_res.column_mapping.items()},
        "ignored_columns": intake_res.ignored_columns,
        "sign_flip": intake_res.detected_signed_ledger,
        "flipped_line_items": intake_res.negative_revenue_items if intake_res.detected_signed_ledger else [],
        "unit_scale": (
            str(intake_res.detected_unit_multiplier)
            if intake_res.detected_unit_multiplier != Decimal("1") else None
        ),
        "zero_reads": {"accounting_dashes": intake_res.dash_count, "blank_budgets": blank_budgets},
        "excluded_totals": intake_res.detected_totals,
        "period_selection": mapping.period_column_selection if mapping is not None else None,
        "classification_rules": mapping.classification_rules if mapping is not None else None,
        "mapping_file_sha256": mapping_sha256(mapping) if mapping is not None else None,
    }


def format_intake_summary(result: IntakeResult) -> str:
    """Generate the 'Here's how I read your file' summary for Maya in plain English."""
    lines: list[str] = ["Here's how I read your file:\n"]

    if result.sheet_name:
        source = "Statement" if result.source_kind == "pdf" else "Worksheet"
        lines.append(f"- **{source}:** {result.sheet_name}")

    for t in result.visible_transformations:
        if t.startswith("Analyzed period:"):
            period_name = t.split(":")[1].split("(")[0].strip()
            lines.append(f"- **Analyzed period:** {period_name}")
            break

    if result.source_kind != "pdf":  # a PDF has no rows to count; its page is in the name
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
        skipped = result.rows_skipped_count
        read_text += f" ({skipped} row{'s' if skipped != 1 else ''} skipped: {', '.join(result.skip_reasons)})"
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


_INTERNAL_FIELD_NAMES = frozenset(_ROLE_ALIAS_KEYS | {
    "row_kind", "account_id", "budget_amount", "actual_amount", "line_type", "revenue_expense_type",
})


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
    m_reconcile = re.search(
        r"Summary\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))\s+does not reconcile to\s+([^;]+)", text, re.IGNORECASE
    )
    if m_reconcile:
        summary_name = m_reconcile.group(1) or m_reconcile.group(2) or m_reconcile.group(3)
        line_type = m_reconcile.group(4).strip()
        return (
            f"Summary total for '{summary_name}' does not match the sum of its {line_type} detail rows. "
            "Please check for missing or overlapping line items."
        )

    # 7. Ambiguous summary label / Row Kind
    if "ambiguous summary label" in text.lower() or "row kind" in text.lower():
        return "Some subtotal or total rows could not be distinguished from detail rows. Please check summary line items."

    # 8. Unclassified items
    if "unclassified" in text.lower():
        text = re.sub(r"\bunclassified\b", "not yet labeled revenue or expense", text, flags=re.IGNORECASE)

    # 9. CLI flags (only a flag standing alone, never "--" inside a line-item name)
    text = re.sub(r"(?<![\w-])--[a-z][a-z0-9\-]*", "setting", text)

    # 10. Internal field names in quotes; the user's own snake_case names stay as written
    text = re.sub(
        r"'([a-z0-9]+_[a-z0-9_]+)'",
        lambda m: f"'{m.group(1).replace('_', ' ')}'" if m.group(1) in _INTERNAL_FIELD_NAMES else m.group(0),
        text,
    )

    # 11. Forbidden words
    text = re.sub(r"\bnormalize[sd]?\b", "standardize", text, flags=re.IGNORECASE)
    text = re.sub(r"\baliases?\b", "synonym", text, flags=re.IGNORECASE)
    text = re.sub(r"\bschemas?\b", "structure", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpayload\b", "data", text, flags=re.IGNORECASE)

    return text


def _row_measure(row: dict[str, object]) -> MeasureKind:
    value = next((v for k, v in row.items() if normalize_key(k) == "measure"), None)
    return measure_kind(value, str(row.get("line_item", "Row")))


def _rate_number(value: object, kind: MeasureKind) -> object:
    return value.strip()[:-1] if kind is MeasureKind.PERCENT and isinstance(value, str) and value.strip().endswith("%") else value
