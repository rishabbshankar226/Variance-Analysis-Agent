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
import datetime as dt
import io
import re
import unicodedata
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from decimal import ROUND_FLOOR, Decimal, Inexact, InvalidOperation
from enum import StrEnum
from typing import cast
from collections.abc import Callable

from .classification import infer_line_type, is_profit_measure
from .currencies import CURRENCY_SYMBOLS, SYMBOL_CURRENCIES
from .excel import (
    ExcelWorkbook,
    ExcelWorksheet,
    SheetLayout,
    WorkbookFacts,
    WorkbookLoader,
    cell_key,
    column_letters,
    cell_value,
    describe_cell,
    hidden_data_rows,
    hidden_rows_note,
    legacy_workbook_message,
    renamed_workbook_note,
    workbook_kind,
    hidden_rows_question,
    inspect_workbook,
    unsaved_formula_cells,
    unsaved_formulas_message,
)
from .limits import (
    MAX_CELLS,
    MAX_COLUMNS,
    MAX_INPUT_BYTES,
    MAX_NUMBER_LENGTH,
    MAX_ROWS,
)
from .mapping import LayoutMapping, mapping_sha256
from .models import ComparisonBasis, LineType
from .numeric import financial_context, ratio
from .pdf_tables import PdfReadError, StatementTable, extract_statement_tables, statement_tables_from_grid, statement_title
from .ixbrl import BOTTOM_LINE, BOTTOM_LINE_LABEL, FILING_SUBTOTALS, IxbrlError, LineKey, read_statements
from .number_formats import display_divisor, shown_places, shows_percent
from .statement_shape import ShapedStatement, names_subtotal, shape_income_statement
from .ixbrl import Line as IxLine
from .ixbrl import Statement as IxStatement
from .statement_checks import CheckLine, check_balance_sheet, check_cash_flow
from .measures import measure_kind
from .models import MeasureKind
from .comparison import (
    _ACTUAL_SUFFIX,
    BUDGET_SYNONYMS,
    COMPARISON_WORDS,
    OPT_IN_SYNONYMS,
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


@dataclass(frozen=True)
class _ExcelSheet:
    """What the preflight saw on the worksheet being read, for checks only a workbook needs."""

    layout: SheetLayout
    recalculate_on_open: bool = False
    # Numeric cells whose number format shows them scaled: cell_key -> (format, divisor, percent).
    # A divisor of None is a format this reader cannot interpret. Plain cells are not kept.
    display: dict[int, tuple[str, Decimal | None, bool]] = field(default_factory=dict)
    hidden_rows: str | None = None  # the person's answer for rows hidden in Excel: include or exclude
    block: str | None = None  # "columns E-G": which of several side-by-side tables to read (E5)
    # Decimal places each numeric cell's format shows (cell_key -> places), kept only on a sheet laid
    # out like EDGAR's Financial_Report.xlsx, whose stored values are binary floats (E3).
    shown_places: dict[int, int] = field(default_factory=dict)


def _display_entry(code: object, value: object, cache: dict[tuple[str, int], tuple[Decimal | None, bool]],
                   ) -> tuple[str, Decimal | None, bool] | None:
    """How a numeric cell's format scales its display, or None for an unscaled display."""
    if not isinstance(value, Decimal) or not isinstance(code, str) or code == "General":
        return None
    sign = (value > 0) - (value < 0)
    if (code, sign) not in cache:
        cache[code, sign] = (display_divisor(code, value), shows_percent(code, value))
    divisor, percent = cache[code, sign]
    return None if divisor == 1 and not percent else (code, divisor, percent)


_UNIT_WORDS = {Decimal(1000): "thousands", Decimal(1_000_000): "millions", Decimal(1_000_000_000): "billions"}


def _shown_as(divisor: Decimal | None, percent: bool) -> str:
    if percent:
        return "as a percentage"
    if divisor is None:
        return "in a way I can't interpret"
    return f"in {_UNIT_WORDS[divisor]}" if divisor in _UNIT_WORDS else f"divided by {divisor:,}"


def _quoted_format(code: str) -> str:
    return f"'{code[:40]}{'...' if len(code) > 40 else ''}'"


def percent_shown(value: Decimal) -> str:
    """The percentage Excel shows for a rate stored under a percent number format: 0.4 reads "40%" (X31)."""
    if value == 0:
        return "0%"
    with financial_context():
        return f"{format((value * 100).normalize(), 'f')}%"


def percent_shown_note(line_item: str, fields: list[str], code: str) -> str:
    named = fields[0] if len(fields) == 1 else f"{', '.join(fields[:-1])} and {fields[-1]}"
    return (f"{line_item}: read {named} as the percentage{'s' if len(fields) > 1 else ''} Excel shows "
            f"(number format {_quoted_format(code)}).")


def _unsaved_formulas_stop(
    excel: _ExcelSheet | None, filename: str, include: Callable[[int, int], bool],
    describe: Callable[[int, int], str], sheet_name: str | None,
) -> IntakeResult | None:
    """Stop when a read cell holds a formula whose result can't be used (R4); never read it as blank."""
    if excel is None:
        return None
    unsaved = unsaved_formula_cells(excel.layout, excel.recalculate_on_open, include)
    if not unsaved:
        return None
    return IntakeResult(
        has_fatal_errors=True,
        fatal_error_message=unsaved_formulas_message(
            filename, [describe(*cell) for cell in unsaved],
            # The recalculation wording only when a listed cell does hold a (possibly stale) result.
            recalculate_on_open=any(not excel.layout.is_uncached(*cell) for cell in unsaved)),
        sheet_name=sheet_name,
    )


_MAX_EXAMINED = 100  # entries kept per examination list, so a hostile sheet cannot grow the audit


@dataclass(frozen=True)
class WorkbookExamination:
    """What the workbook holds beyond the table read; shown and recorded only with a finding.

    A finding is a fact that changes or could change the read of the chosen sheet (Decision 14):
    hidden data rows or read columns, error results, formulas without a saved result, amounts
    shown scaled, a layout read differently (bands, side-by-side tables, date headers, an EDGAR
    statement, a renamed .xls), links to other workbooks, or a request to recalculate on open on
    a sheet with formulas.
    """

    sheet: str
    sheets: tuple[tuple[str, str], ...]  # (name, visibility)
    tables: tuple[tuple[str, str], ...]  # (name, range) on the chosen sheet
    merged_header_ranges: tuple[str, ...]
    hidden_rows: tuple[tuple[int, str, bool], ...]
    hidden_rows_choice: str | None
    hidden_columns: tuple[str, ...]
    error_cells: tuple[tuple[str, str], ...]
    unsaved_formulas: tuple[str, ...]  # cells outside the read; inside it they stop intake
    external_links: int
    outline_rows: int
    outline_columns: int
    recalculate_on_open: bool
    display_scaled_cells: tuple[tuple[str, str, str], ...]  # (cell, format, how it is shown)
    reading_notes: tuple[str, ...]
    findings: tuple[str, ...]

    def lines(self) -> list[str]:
        """Plain sentences for the read summary and stderr."""
        out = [f"Sheets: {', '.join(f'{name} ({state})' for name, state in self.sheets)}."]
        if self.tables:
            out.append(f"Excel tables on this sheet: {', '.join(f'{name} ({where})' for name, where in self.tables)}.")
        if self.merged_header_ranges:
            out.append(f"Merged header cells: {', '.join(self.merged_header_ranges)}.")
        if self.hidden_rows:
            answer = {"include": "counted", "exclude": "left out"}.get(self.hidden_rows_choice or "", "not decided")
            listed = ", ".join(f"row {row}{f' ({label})' if label else ''}" for row, label, _ in self.hidden_rows)
            out.append(f"Hidden rows: {listed}, {answer}.")
        if self.hidden_columns:
            out.append(f"Hidden columns: {', '.join(self.hidden_columns)}.")
        if self.error_cells:
            out.append(f"Error results: {', '.join(f'{cell} ({error})' for cell, error in self.error_cells)}.")
        if self.unsaved_formulas:
            out.append(f"Formulas without a saved result, not read: {', '.join(self.unsaved_formulas)}.")
        if self.external_links:
            out.append(f"Links to other workbooks: {self.external_links}; the values saved in this file were read.")
        if self.outline_rows or self.outline_columns:
            out.append(f"Outline groups: {self.outline_rows} row level(s), {self.outline_columns} column level(s).")
        if self.recalculate_on_open:
            out.append("The workbook asks Excel to recalculate its formulas when it opens.")
        if self.display_scaled_cells:
            shown = ", ".join(f"{cell} ('{code}' shows it {how})" for cell, code, how in self.display_scaled_cells)
            out.append(f"Amounts shown scaled by their number format: {shown}.")
        return out

    def record(self) -> dict[str, object]:
        """The audit 1.9 `workbook` group."""
        return {
            "sheet": self.sheet,
            "sheets": [{"name": name, "visibility": state} for name, state in self.sheets],
            "tables": [{"name": name, "range": where} for name, where in self.tables],
            "merged_header_ranges": list(self.merged_header_ranges),
            "hidden_rows": [{"row": row, "line_item": label, "collapsed": collapsed}
                            for row, label, collapsed in self.hidden_rows],
            "hidden_rows_choice": self.hidden_rows_choice,
            "hidden_columns": list(self.hidden_columns),
            "error_cells": [{"cell": cell, "error": error} for cell, error in self.error_cells],
            "unsaved_formulas": list(self.unsaved_formulas),
            "external_links": self.external_links,
            "outline_levels": {"rows": self.outline_rows, "columns": self.outline_columns},
            "recalculate_on_open": self.recalculate_on_open,
            "display_scaled_cells": [{"cell": cell, "format": code, "shown": how}
                                     for cell, code, how in self.display_scaled_cells],
            "reading_notes": list(self.reading_notes),
            "findings": list(self.findings),
        }


def _examine(result: IntakeResult, facts: WorkbookFacts, sheet_path: str, sheet_name: str,
             sheets: list[tuple[str, str]], raw_rows: list[list[object]]) -> WorkbookExamination:
    """The examination of the sheet a read used, beside what the read itself recorded."""
    layout = facts.layouts.get(sheet_path, SheetLayout())

    def address(key: int) -> str:
        row, column = divmod(key, MAX_COLUMNS + 1)
        return f"{column_letters(column)}{row}"

    def has_data(column: int) -> bool:
        return any(column <= len(row) and row[column - 1] not in (None, "") for row in raw_rows)

    errors = tuple((address(key), text) for key, text in sorted(layout.errors.items()))
    unsaved = tuple(address(key) for key in sorted(layout.uncached))
    scaled = tuple((c.address, c.code[:40], _shown_as(c.divisor, c.percent)) for c in result.display_scaled_cells)
    recalculate = facts.recalculate_on_open and bool(layout.formulas)
    found = tuple(name for name, present in (
        ("hidden_rows", bool(result.hidden_data_rows)), ("hidden_columns", bool(result.hidden_read_columns)),
        ("error_cells", bool(errors)), ("unsaved_formulas", bool(unsaved)), ("display_scaling", bool(scaled)),
        ("layout", result.layout_read), ("external_links", facts.external_links > 0),
        ("recalculate_on_open", recalculate)) if present)
    return WorkbookExamination(
        sheet=sheet_name,
        sheets=tuple(sheets[:_MAX_EXAMINED]),
        tables=facts.tables.get(sheet_path, ())[:_MAX_EXAMINED],
        merged_header_ranges=tuple(f"{column_letters(c1)}{r1}:{column_letters(c2)}{r2}" for r1, c1, r2, c2
                                   in layout.merged if r1 <= result.header_row_number)[:_MAX_EXAMINED],
        hidden_rows=tuple(result.hidden_data_rows[:_MAX_EXAMINED]),
        hidden_rows_choice=result.hidden_rows_choice,
        hidden_columns=tuple(column_letters(c) for c in sorted(layout.hidden_columns) if has_data(c))[:_MAX_EXAMINED],
        error_cells=errors[:_MAX_EXAMINED],
        unsaved_formulas=unsaved[:_MAX_EXAMINED],
        external_links=facts.external_links,
        outline_rows=layout.outline_rows,
        outline_columns=layout.outline_columns,
        recalculate_on_open=recalculate,
        display_scaled_cells=scaled[:_MAX_EXAMINED],
        reading_notes=tuple(result.layout_notes),
        findings=found,
    )


@dataclass(frozen=True)
class DisplayScaledCell:
    """A Currency amount whose number format shows it scaled (R2): what the reader is told."""

    description: str  # "Row 3, Revenue, Budget column (cell B3)"
    address: str  # "B3"
    code: str  # the number format, as the file stores it
    divisor: Decimal | None  # what the display divides the stored value by; None if unreadable
    percent: bool


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
    # The currency a filing's monetary facts are in, and amount cells whose text marks a currency (X5, X30).
    document_currency: str = ""
    # (file, "Row 2, Sales, Budget column: €100", "EUR")
    symbol_cells: list[tuple[str, str, str]] = field(default_factory=list)
    source_pages: tuple[int, ...] = ()
    reader_notes: list[str] = field(default_factory=list)
    comparable_sheets: list[str] = field(default_factory=list)  # PDF statements that can be compared
    # Currency amounts whose number format shows them scaled, and how many amounts were read (R2).
    display_scaled_cells: list[DisplayScaledCell] = field(default_factory=list)
    currency_amount_cells: int = 0
    # Rows hidden in Excel with anything in them (row, label, collapsed by an outline group), R3.
    hidden_data_rows: list[tuple[int, str, bool]] = field(default_factory=list)
    needs_hidden_rows_choice: bool = False  # stopped to ask whether to count them
    hidden_rows_choice: str | None = None  # the answer applied, when there were such rows
    hidden_read_columns: list[str] = field(default_factory=list)  # read columns Excel hides
    # Notes from the Phase 1 workbook reads (E1-E8), in order, and whether the layout itself was
    # read differently (bands, side-by-side tables, date headers, an EDGAR statement, a renamed .xls).
    layout_notes: list[str] = field(default_factory=list)
    layout_read: bool = False
    workbook_examination: WorkbookExamination | None = None
    source_statement: str | None = None  # the statement an EDGAR-style sheet held
    # An Inline XBRL read: each line's XBRL key per column, for audit 1.9 (PLAN.md R1).
    xbrl_lines: list[dict[str, object]] = field(default_factory=list)
    # A balance sheet or cash flow statement (PLAN.md R7, R9): its kind, the identity it was checked
    # against for audit 1.9, and the sentences the report shows in place of totals.
    half_filled: bool = False  # one half of a two-file pair, read with a placeholder column (PLAN.md R12)
    # A refused file holding a Limit, Benchmark or Target column: the header and its basis, so the chat can read it so.
    opt_in_hint: tuple[str, ComparisonBasis] | None = None
    join: dict[str, object] | None = None  # the pair's join, for audit 1.9
    scorecard: dict[str, object] | None = None  # a holdings scorecard awaiting its labels (PLAN.md R18)
    statement_kind: str = ""
    identities: list[dict[str, object]] = field(default_factory=list)
    statement_checks: list[str] = field(default_factory=list)
    # An LTM build from a 10-K and a 10-Q (PLAN.md R11): its audit record and the report section citing it.
    ltm: dict[str, object] | None = None
    report_appendix: list[str] = field(default_factory=list)
    # A filing's income statement: its own printed totals, which head the report in place of computed ones (Decision 39).
    filing_headline: dict[str, object] | None = None
    # A filing column label's display name where it names a duration ("3 months ended Mar 2026"); keys keep the
    # label (M4).
    period_names: dict[str, str] = field(default_factory=dict)

    def source_document(self) -> dict[str, object] | None:
        """How a PDF or EDGAR-style statement was read, for the audit record; None for other files."""
        if self.ltm is not None:
            return dict(self.ltm)
        if self.join is not None:
            return dict(self.join)
        if self.source_kind == "ixbrl" and self.source_statement is not None:
            document: dict[str, object] = {"kind": "ixbrl", "statement": self.source_statement,
                                           "reader_notes": list(self.reader_notes), "lines": list(self.xbrl_lines)}
            if self.statement_kind:
                document.update(statement_kind=self.statement_kind, identities=list(self.identities))
            if self.filing_headline is not None:
                document["headline"] = dict(self.filing_headline)
            return document
        if self.source_kind == "edgar_xlsx" and self.sheet_name is not None and self.source_statement is not None:
            return {"kind": "edgar_xlsx", "statement": self.source_statement, "sheet": self.sheet_name,
                    "reader_notes": list(self.reader_notes)}
        if self.source_kind != "pdf" or self.sheet_name is None:
            return None
        return {"kind": "pdf", "statement": self.sheet_name, "pages": list(self.source_pages),
                "reader_notes": list(self.reader_notes)}

    @property
    def has_transformations(self) -> bool:
        """Return True if any heuristic adjustment or transformation was made that warrants confirmation."""
        if self.comparison_basis != ComparisonBasis.BUDGET:
            return True
        if self.workbook_examination is not None and self.workbook_examination.findings:
            return True  # the analyst sees what the workbook holds before analysis
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


_HEADER_UNIT = r"(?:'?000'?s?|thousands?|millions?|billions?|k|mm?|bn)"
_HEADER_CURRENCY = r"(?:[$€£]|usd|eur|gbp|dollars|euros|pounds)"
# A unit or currency qualifier at the end of an amount heading, and nothing else: never "(Q3)" (X23).
_HEADER_QUALIFIER = re.compile(
    rf"\s*(?:\(\s*(?:{_HEADER_CURRENCY}\s*)?(?:in\s+)?(?:{_HEADER_CURRENCY}\s*)?{_HEADER_UNIT}?\s*\)"
    rf"|{_HEADER_CURRENCY}\s*'?{_HEADER_UNIT}?|'?000'?s)\s*$", re.IGNORECASE)
_HEADER_CURRENCY_CODE = re.compile(r"[$€£]|\b(?:usd|eur|gbp)\b", re.IGNORECASE)
# The unit word inside a qualifier; "m" and "mm" are millions, as "$M" is in a caption (X45).
_QUALIFIER_UNIT = re.compile(rf"(?<![a-z]){_HEADER_UNIT}(?![a-z])", re.IGNORECASE)


def heading_unit(heading: str) -> Decimal | None:
    """The unit an amount heading's own qualifier names: "Budget ($000)" thousands, "Actual (USD m)" millions. None
    when it names none, "($)" and "(USD)" included (X45)."""
    qualifier = _HEADER_QUALIFIER.search(heading)
    word = _QUALIFIER_UNIT.search(qualifier.group()) if qualifier is not None else None
    if word is None:
        return None
    token = word.group().strip("'").lower()
    if token.startswith(("000", "thousand")) or token == "k":
        return Decimal("1000")
    if token.startswith("billion") or token == "bn":
        return Decimal("1000000000")
    return Decimal("1000000")


def match_column_synonym(header: str) -> tuple[CanonicalRole, str | None]:
    """Map a raw header name to its canonical role and an optional transformation note."""
    norm = normalize_header(header)
    if norm in _LINE_ITEM_SYNONYMS:
        return CanonicalRole.LINE_ITEM, None
    if norm in _ACCOUNT_ID_SYNONYMS:
        return CanonicalRole.ACCOUNT_ID, None
    if basis_for_header(norm, opt_in=_OPT_IN_BASIS.get()) is not None:
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
    # "Budget ($000)", "Actual (USD)": the words before a unit or currency qualifier name the amount (X23).
    bare = _HEADER_QUALIFIER.sub("", header).strip()
    if bare and bare != header.strip():
        role, note = match_column_synonym(bare)
        if role in (CanonicalRole.BUDGET, CanonicalRole.ACTUAL):
            return role, note

    return CanonicalRole.UNKNOWN, None


def _footnote_marks(text: str) -> str:
    """Characters that are not digits but that NFKC folds into digits: superscripts, circled numbers."""
    return "".join(dict.fromkeys(
        ch for ch in text
        if not ch.isascii() and unicodedata.category(ch) != "Nd"
        and any(c in "0123456789" for c in unicodedata.normalize("NFKC", ch))
    ))


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

    # NFKC would also turn a footnote mark into digits ("950\u00b9" -> "9501", "\u2460" -> "1"): refuse it.
    if marks := _footnote_marks(value):
        raise ValueError(
            f"{line_item}: field '{field}' has a footnote mark or small digit ({marks}) in: {value}."
        )
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


_BARE_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_PERIOD_RE = re.compile(
    r"\b((?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-_ ]?\d{2,4})|"
    r"(?:Q[1-4](?:[-_ ]?\d{2,4})?)|"
    r"(?:FY\s*\d{2,4})|"
    r"(?:YTD|MTD)|"
    r"(?:\d{4}[-_]\d{2}))\b",
    re.IGNORECASE,
)

_CURRENCY_LEAD = r"(?:[$€£]\s*|(?:usd|eur|gbp|us\s*dollars?|dollars|euros|pounds)\s+)"
_LETTER_UNIT_END = r"\b(?![&'\w.])"  # "in M" names millions, "in M&A" and "in M." do not


def _unit_caption_re(word: str, short_forms: str) -> re.Pattern[str]:
    """A unit caption naming `word` ("thousands") in a title or header, or one of its short forms (X4)."""
    return re.compile(
        rf"\bin\s+{_CURRENCY_LEAD}?{word}\b"  # in thousands, in $ thousands, in USD thousands
        rf"|\(\s*{_CURRENCY_LEAD}?(?:in\s+)?{word}\b"  # (thousands, ($ in thousands), (USD thousands)
        rf"|\b(?:usd|eur|gbp|dollars|euros|pounds)\s+(?:in\s+)?{word}\b"  # Dollars in Thousands, EUR millions
        rf"|\b{word}\s+of\s+(?:u\.?s\.?\s+)?(?:dollars|euros|pounds)\b"  # (thousands of dollars)
        rf"|{short_forms}",
        re.IGNORECASE,
    )


_THOUSANDS_RE = _unit_caption_re(
    "thousands", r"(?:[$€£]|\b(?:usd|eur|gbp)\b)\s*'?\s*000(?:'?s)?\b|\(\s*'?000(?:'?s)?\s*\)|\b000s\b"
                 r"|[$€£]\s*k\b|\(\s*k\s*\)")
_MILLIONS_RE = _unit_caption_re("millions", rf"[$€£]\s*mm?\b|\(\s*mm?\s*\)|\bin\s+mm?{_LETTER_UNIT_END}")
_BILLIONS_RE = _unit_caption_re("billions", rf"[$€£]\s*bn\b|\(\s*bn\s*\)|\bin\s+bn{_LETTER_UNIT_END}")
_TOTAL_KEYWORD_RE = re.compile(
    r"\b(total|sub\s*total|subtotal|gross\s+profit|net\s+income|operating\s+income|ebitda)\b",
    re.IGNORECASE,
)
_ACCOUNT_NUM_RE = re.compile(r"\b([1-9]\d{3,4})\b")


_TITLE_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
                r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
# The ways a title names a reporting period, most specific first: a span one form takes is not read again by
# a later one, so "Q3 FY2026" is one period, not two (X35).
_TITLE_PERIODS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    rf"\b(?:(?:three|six|nine|twelve|\d{{1,2}})\s+months|(?:13|26|39|52)\s+weeks|(?:fiscal\s+)?(?:year|quarter|period))"
    rf"\s+end(?:ed|ing)\s+{_TITLE_MONTH}\.?\s+\d{{1,2}},?\s+\d{{4}}\b",
    r"\bQ[1-4]\s*(?:FY\s*)?['’]?\d{2,4}\b|\bFY\s*\d{2,4}\s*Q[1-4]\b",
    r"\bH[12]\s*(?:FY\s*)?\d{4}\b",
    r"\bFY\s*\d{2,4}\b",
    rf"\b{_TITLE_MONTH}\.?\s+\d{{4}}\b",
))


def title_periods(text: str, limit: int = 3) -> list[str]:
    """The reporting periods a title names, as it prints them and in its order: at most `limit`, distinct (X35)."""
    taken: list[tuple[int, int, str]] = []
    for pattern in _TITLE_PERIODS:
        for match in pattern.finditer(text):
            if not any(start < match.end() and match.start() < end for start, end, _ in taken):
                taken.append((match.start(), match.end(), " ".join(match.group().split())))
    found: list[str] = []
    for _, _, period in sorted(taken):
        period = period[0].upper() + period[1:]
        if period.lower() not in {named.lower() for named in found}:
            found.append(period)
    return found[:limit]


def chosen_period_pair(pairs: list[PeriodColumnPair], selected_period: str | None) -> PeriodColumnPair:
    """The pair a chosen period names; else the newest by period order, whatever the column order; else, when the
    labels give no order, the last pair, as before (X48)."""
    named = next((p for p in pairs if selected_period is not None and p.period.lower() == selected_period.lower()), None)
    if named is not None:
        return named
    newest = order_period_labels([p.period for p in pairs])
    return next(p for p in pairs if p.period == newest[0]) if newest else pairs[-1]


def detect_period_pairs(headers: list[str]) -> list[PeriodColumnPair]:
    """Scan column headers to detect paired Budget and Actual columns by period."""
    budget_cols: dict[str, str] = {}
    actual_cols: dict[str, str] = {}
    period_order: list[str] = []

    for h in headers:
        m = _PERIOD_RE.search(h) or _BARE_YEAR_RE.search(h)  # "2026 Budget", from a bare-year band (M3)
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
    if _BILLIONS_RE.search(text):
        return Decimal("1000000000")
    if _THOUSANDS_RE.search(text):
        return Decimal("1000")
    return Decimal("1")


# Declared in the row's unit (docs/financial-rules.md), so a unit caption scales them with its amounts (X41).
UNIT_DECLARATIONS = {"buffer": "Buffer", "tolerance": "Tolerance"}


def scaled_declaration(value: object, multiplier: Decimal, *, field: str, line_item: str) -> object:
    """A Buffer or Tolerance times the unit, exactly; a cell the engine can't read is left for it to refuse (X41)."""
    from .parsing import is_missing, parse_decimal
    if is_missing(value):
        return value
    try:
        amount = parse_decimal(value, field=field, line_item=line_item)
    except ValueError:
        return value
    with financial_context():
        return amount * multiplier


def unit_declarations(rows: list[dict[str, object]]) -> list[str]:
    """The declarations a unit scales in these rows, as headings ("Buffer", "Tolerance"), in that order."""
    from .parsing import is_missing
    present = {normalize_key(str(key)) for row in rows if _row_measure(row) is MeasureKind.CURRENCY
               for key, value in row.items() if not is_missing(value)}
    return [label for key, label in UNIT_DECLARATIONS.items() if key in present]


def scale_rows_by_unit(rows: list[dict[str, object]], multiplier: Decimal) -> list[dict[str, object]]:
    """Scale budget and actual amounts, and each Buffer and Tolerance (X41), by exact Decimal multiplication."""
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
        for key in [key for key in rc if normalize_key(str(key)) in UNIT_DECLARATIONS]:
            rc[key] = scaled_declaration(rc[key], multiplier, field=str(key), line_item=str(rc.get("line_item", "Row")))
        scaled.append(rc)
    return scaled


def scaling_note(unit_label: str, declarations: list[str]) -> str:
    """The note for amounts scaled by a unit, naming the declarations scaled with them (X41)."""
    included = f", {' and '.join(declarations)} included" if declarations else ""
    return (f"Amounts scaled from {unit_label}{included}. Thresholds stay in the reporting unit "
            "(full currency units, not thousands).")


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


def _signed_profit_lines(rows: list[dict[str, object]]) -> list[str]:
    """The profit lines of a signed ledger whose sign turns with revenue's (X7).

    A profit line turns when turning it makes it add up as a subtotal, or when it adds up neither
    way (the ledger's own convention); it keeps its stored sign when only that sign adds up.
    """
    money = [r for r in rows if _row_measure(r) is MeasureKind.CURRENCY]
    profit = [name for r in money if is_profit_measure(name := str(r.get("line_item", "")).strip())]
    if not profit:
        return []
    turned, _ = flip_ledger_signs(money, profit)
    adds_up_turned = {t.line_item for t in detect_subtotals_and_totals(turned).reconciled_totals}
    adds_up_stored = {t.line_item for t in detect_subtotals_and_totals(money).reconciled_totals}
    return [name for name in profit if name in adds_up_turned or name not in adds_up_stored]


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
                chosen_pair = chosen_period_pair(pairs, selected_period)
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


_MONTH_ABBREVIATIONS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _date_period(value: object) -> str | None:
    """A month period label ("Sep 2026") for a date-typed cell, as the PDF reader labels a dated column."""
    if not isinstance(value, dt.date):
        return None
    return f"{_MONTH_ABBREVIATIONS[value.month - 1]} {value.year}"


def _dated_header_rows(raw_rows: list[list[object]], max_scan: int = 25) -> tuple[list[list[object]], bool]:
    """The rows header detection scans, with date-typed cells read as period labels (E6)."""
    converted = False
    scan: list[list[object]] = []
    for row in raw_rows[:max_scan]:
        labels = [_date_period(cell) for cell in row]
        converted = converted or any(label is not None for label in labels)
        scan.append([cell if label is None else label for cell, label in zip(row, labels, strict=True)])
    return ([*scan, *raw_rows[max_scan:]], True) if converted else (raw_rows, False)


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
        b = basis_for_header(normalize_header(s), opt_in=_OPT_IN_BASIS.get())
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


# One half of a two-file pair (PLAN.md R12): the value column the file lacks, and whether a
# placeholder for it was added. Set only for the length of one read_input_assisted call.
_HALF: ContextVar[dict[str, object] | None] = ContextVar("variance_agent_half", default=None)
# A limit, benchmark or target read (PLAN.md R13-R15): its headers count only while --compare-to names it.
_OPT_IN_BASIS: ContextVar[ComparisonBasis | None] = ContextVar("variance_agent_opt_in_basis", default=None)


def _opt_in_header(raw_rows: list[list[object]]) -> tuple[str, ComparisonBasis] | None:
    """A limit, benchmark or target column in the first rows, named as printed."""
    for row in raw_rows[:25]:
        for cell in row:
            text = str(cell).strip() if cell is not None else ""
            for basis, synonyms in OPT_IN_SYNONYMS.items():
                if text and normalize_header(text) in synonyms:
                    return text, basis
    return None


def read_input_assisted(
    data: bytes,
    suffix: str,
    *,
    filename: str = "input",
    sheet: str | None = None,
    treat_blank_budgets_as_zero: bool = False,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
    per_share_lines: bool = False,
    hidden_rows: str | None = None,
    missing_column: CanonicalRole | None = None,
) -> IntakeResult:
    """Read any supported file format with assisted header, sheet, dash, and problem handling.

    ``hidden_rows`` ("include" or "exclude") answers the question a workbook with rows hidden in
    Excel otherwise stops on; it does nothing for other files. ``missing_column`` (Budget or
    Actual) reads one half of a two-file pair: when the file has no such column, a placeholder
    of zeros is appended at its right edge so every other check runs as for a whole file, and
    ``half_filled`` says so.
    """
    if missing_column is None:
        opt_in = _OPT_IN_BASIS.set(compare_to if compare_to in OPT_IN_SYNONYMS else None)
        try:
            return _read_input_assisted(data, suffix, filename=filename, sheet=sheet,
                                        treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
                                        selected_period=selected_period, compare_to=compare_to,
                                        per_share_lines=per_share_lines, hidden_rows=hidden_rows)
        finally:
            _OPT_IN_BASIS.reset(opt_in)
    holder: dict[str, object] = {"missing": missing_column, "filled": False}
    token = _HALF.set(holder)
    opt_in_token = _OPT_IN_BASIS.set(compare_to if compare_to in OPT_IN_SYNONYMS else None)
    try:
        result = _read_input_assisted(data, suffix, filename=filename, sheet=sheet,
                                      treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
                                      selected_period=selected_period, compare_to=compare_to,
                                      per_share_lines=per_share_lines, hidden_rows=hidden_rows)
    finally:
        _OPT_IN_BASIS.reset(opt_in_token)
        _HALF.reset(token)
    result.half_filled = bool(holder["filled"])
    return result


def _fill_half(raw_rows: list[list[object]], missing: CanonicalRole) -> tuple[list[list[object]], bool]:
    """Append a placeholder column for the value a half file lacks, if it lacks it (PLAN.md R12)."""
    if detect_header_row(raw_rows)[0] is not None or (_OPT_IN_BASIS.get() is None and _opt_in_header(raw_rows) is not None):
        return raw_rows, False  # without --compare-to naming it, a limit, benchmark or target file is never a half
    present = CanonicalRole.ACTUAL if missing is CanonicalRole.BUDGET else CanonicalRole.BUDGET
    for header_at, row in enumerate(raw_rows[:25]):
        roles = {match_column_synonym(str(cell).strip())[0] for cell in row if cell is not None and str(cell).strip()}
        if CanonicalRole.LINE_ITEM in roles and present in roles and missing not in roles:
            width = max(len(r) for r in raw_rows)
            name = "Actual" if missing is CanonicalRole.ACTUAL else "Budget"
            filled = []
            for at, r in enumerate(raw_rows):
                blank = all(cell is None or str(cell).strip() == "" for cell in r)
                value: object = name if at == header_at else (None if at < header_at or blank else "0")
                filled.append([*r, *([None] * (width - len(r))), value])
            return filled, True
    return raw_rows, False


@financial_context()
def _read_input_assisted(
    data: bytes,
    suffix: str,
    *,
    filename: str = "input",
    sheet: str | None = None,
    treat_blank_budgets_as_zero: bool = False,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
    per_share_lines: bool = False,
    hidden_rows: str | None = None,
) -> IntakeResult:
    if len(data) > MAX_INPUT_BYTES:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=(f"The file '{filename}' exceeds the supported file size limit of 32 MiB. Save just the "
                                 "sheet with the statement as a new file and upload that."),
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
    if norm_suffix in {".htm", ".html"}:
        return _read_ixbrl_bytes(data, filename, sheet, treat_blank_budgets_as_zero, selected_period,
                                 compare_to=compare_to, per_share_lines=per_share_lines)
    if norm_suffix == ".xls":
        kind = workbook_kind(data)
        if kind != "ooxml":
            return IntakeResult(has_fatal_errors=True, fatal_error_message=legacy_workbook_message(filename, kind))
        result = _read_excel_bytes(data, filename, sheet, treat_blank_budgets_as_zero, selected_period,
                                   compare_to=compare_to, hidden_rows=hidden_rows, per_share_lines=per_share_lines)
        if not result.has_fatal_errors:
            result.visible_transformations.insert(0, renamed_workbook_note(filename))
            result.layout_notes.insert(0, renamed_workbook_note(filename))
            result.layout_read = True
            if result.workbook_examination is not None:
                result.workbook_examination = replace(
                    result.workbook_examination, reading_notes=tuple(result.layout_notes),
                    findings=tuple(dict.fromkeys([*result.workbook_examination.findings, "layout"])))
        return result
    if norm_suffix in {".xlsx", ".xlsm"}:
        return _read_excel_bytes(
            data,
            filename,
            sheet,
            treat_blank_budgets_as_zero,
            selected_period,
            compare_to=compare_to,
            hidden_rows=hidden_rows,
            per_share_lines=per_share_lines,
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
            per_share_lines=per_share_lines,
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
                    f"'{filename}' has more than {MAX_COLUMNS} columns, which is more than I can read. Delete the "
                    "columns the analysis doesn't need and upload the file again."
                )
            cells += len(record)
            if len(rows) >= MAX_ROWS or cells > MAX_CELLS:
                raise ValueError(
                    f"'{filename}' has more rows or cells than I can read "
                    f"(limits: {MAX_ROWS:,} rows and {MAX_CELLS:,} cells). Save just the rows the analysis needs "
                    "as a new file and upload that."
                )
            rows.append(cast(list[object], record))
    except csv.Error as exc:
        raise ValueError(f"I could not split '{filename}' into columns: {str(exc).rstrip('.')}. Save it from "
                         "Excel as CSV and upload that.") from exc
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
            fatal_error_message=(f"Could not read JSON data from '{filename}': {str(exc).rstrip('.')}. Save the "
                                 "table as CSV or Excel and upload that instead."),
        )


def _hidden_sheets_last(ranked: list[SheetScore], hidden: set[str]) -> list[SheetScore]:
    """Visible worksheets first (a hidden draft must not win automatically), order otherwise kept."""
    marked = [
        replace(s, rationale=f"{s.rationale}; hidden worksheet") if s.name in hidden else s for s in ranked
    ]
    return sorted(marked, key=lambda s: s.name in hidden)


@dataclass(frozen=True)
class _SheetChoice:
    """A workbook's sheets, ranked on their first rows, and the one a read uses (with the duration its name chose)."""

    sheetnames: list[str]
    all_sheets_raw: list[tuple[str, list[list[object]]]]
    ranked: list[SheetScore]
    sheet_states: list[tuple[str, str]]
    hidden: set[str]
    chosen_sheet: str
    duration: str | None


def _read_excel_bytes(
    data: bytes,
    filename: str,
    sheet: str | None,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
    hidden_rows: str | None = None,
    per_share_lines: bool = False,
) -> IntakeResult:
    try:
        facts = inspect_workbook(data)
        stored_numbers = facts.numbers
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
            message = (f"The Excel file '{filename}' could not be opened safely. Open it in Excel, save it again "
                       "as .xlsx, and upload that.")
        return IntakeResult(has_fatal_errors=True, fatal_error_message=message)

    loader = _excel_loader()
    with io.BytesIO(data) as src:
        wb = None
        try:
            wb = loader(src, read_only=True, data_only=True)
            choice = _choose_sheet(wb, filename, sheet, stored_numbers)
            if isinstance(choice, IntakeResult):
                return choice
            target_ws, full_raw_rows, excel = _sheet_rows(wb, choice.chosen_sheet, facts, stored_numbers, hidden_rows)
            return _read_chosen_sheet(choice, target_ws, full_raw_rows, excel, facts, filename,
                                      treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
                                      selected_period=selected_period, compare_to=compare_to,
                                      per_share_lines=per_share_lines)
        except Exception as exc:
            return IntakeResult(
                has_fatal_errors=True,
                fatal_error_message=(f"Could not read Excel file '{filename}': {str(exc).rstrip('.')}. Open it in "
                                     "Excel, save the sheet with the statement as a new workbook, and upload that."),
            )
        finally:
            if wb is not None:
                wb.close()


def _choose_sheet(
    wb: ExcelWorkbook, filename: str, sheet: str | None, stored_numbers: dict[str, dict[str, str]],
) -> IntakeResult | _SheetChoice:
    """Rank the workbook's sheets on their first rows, then choose the one named, else the best ranked."""
    sheetnames = list(wb.sheetnames)
    if not sheetnames:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=(f"The Excel workbook '{filename}' contains no worksheets. Open it in "
                                 "Excel, check that it holds the statement, then save it and upload it again."),
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
    sheet_states = [(n, str(getattr(wb[n], "sheet_state", "visible"))) for n in sheetnames]
    hidden = {n for n, state in sheet_states if state != "visible"}
    if hidden:
        ranked = _hidden_sheets_last(ranked, hidden)

    # If user explicitly specified sheet, use that; otherwise pick top ranked sheet
    chosen_sheet = sheet
    duration = None
    band = re.fullmatch(r"(?P<sheet>.+) \((?P<duration>[^()]+)\)", chosen_sheet or "")
    if chosen_sheet not in sheetnames and band is not None and band["sheet"] in sheetnames:
        # "Sheet (9 Months Ended)" names one duration of an EDGAR-style statement sheet.
        chosen_sheet, duration = band["sheet"], band["duration"]
    if chosen_sheet is None:
        chosen_sheet = ranked[0].name if ranked else sheetnames[0]
    elif chosen_sheet not in sheetnames:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=(
                f"Worksheet '{chosen_sheet}' was not found in '{filename}'. "
                f"Available sheets: {', '.join(sheetnames)}. Choose one of those sheets."
            ),
            available_sheets=sheetnames,
        )
    return _SheetChoice(sheetnames, all_sheets_raw, ranked, sheet_states, hidden, chosen_sheet, duration)


def _sheet_rows(
    wb: ExcelWorkbook, chosen_sheet: str, facts: WorkbookFacts, stored_numbers: dict[str, dict[str, str]],
    hidden_rows: str | None,
) -> tuple[ExcelWorksheet, list[list[object]], _ExcelSheet]:
    """Every row of the chosen sheet, and what the preflight and the cells' number formats say about it (R2, E3)."""
    target_ws = wb[chosen_sheet]
    target_ws.reset_dimensions()
    numbers = stored_numbers.get(target_ws._worksheet_path, {})

    full_raw_rows: list[list[object]] = []
    display: dict[int, tuple[str, Decimal | None, bool]] = {}
    format_cache: dict[tuple[str, int], tuple[Decimal | None, bool]] = {}
    places: dict[int, int] = {}
    edgar_like = False
    for r_idx, cells in enumerate(target_ws.iter_rows(), start=1):
        row_vals = [
            cell_value(c, numbers=numbers, row=r_idx, column=c_idx)
            for c_idx, c in enumerate(cells, start=1)
        ]
        if r_idx == 1:
            edgar_like = bool(row_vals) and _looks_like_edgar_title(row_vals[0])
        for c_idx, (c, value) in enumerate(zip(cells, row_vals, strict=True), start=1):
            code = getattr(c, "number_format", None)
            entry = _display_entry(code, value, format_cache)
            if entry is not None:
                display[cell_key(r_idx, c_idx)] = entry
            if edgar_like and isinstance(value, Decimal) and isinstance(code, str):
                shown = shown_places(code, value)
                if shown is not None:
                    places[cell_key(r_idx, c_idx)] = shown
        full_raw_rows.append(row_vals)

    excel = _ExcelSheet(
        layout=facts.layouts.get(target_ws._worksheet_path, SheetLayout()),
        recalculate_on_open=facts.recalculate_on_open,
        display=display,
        hidden_rows=hidden_rows,
        shown_places=places,
    )
    return target_ws, full_raw_rows, excel


def _read_chosen_sheet(
    choice: _SheetChoice, target_ws: ExcelWorksheet, full_raw_rows: list[list[object]], excel: _ExcelSheet,
    facts: WorkbookFacts, filename: str, *, treat_blank_budgets_as_zero: bool, selected_period: str | None,
    compare_to: ComparisonBasis | None, per_share_lines: bool,
) -> IntakeResult:
    """Read the chosen sheet as an EDGAR-style statement or as a table, and say which sheet was read and why."""
    sheetnames, all_sheets_raw, hidden, sheet_states = choice.sheetnames, choice.all_sheets_raw, choice.hidden, choice.sheet_states
    ranked, chosen_sheet, duration = choice.ranked, choice.chosen_sheet, choice.duration
    statement_notes: list[str] = []
    statements = ([] if detect_header_row(_dated_header_rows(full_raw_rows)[0])[0] is not None
                  else _edgar_statement_tables(full_raw_rows, excel.layout, per_share_lines=per_share_lines,
                                               shown_places=excel.shown_places, notes=statement_notes))
    if statements:
        # Only a sheet today's read can't find a header on: files that read today read the same.
        statement = _read_edgar_statement(
            statements, duration, full_raw_rows, filename, chosen_sheet, excel,
            treat_blank_budgets_as_zero=treat_blank_budgets_as_zero, selected_period=selected_period,
            compare_to=compare_to, sheet_notes=statement_notes)
        statement.available_sheets = sheetnames
        if not statement.has_fatal_errors:
            statement.workbook_examination = _examine(
                statement, facts, target_ws._worksheet_path, chosen_sheet, sheet_states, full_raw_rows)
        return statement
    if duration is not None:
        excel = replace(excel, block=duration)
    result = _process_raw_table(
        full_raw_rows,
        filename,
        sheet_name=chosen_sheet,
        treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
        selected_period=selected_period,
        compare_to=compare_to,
        excel=excel,
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
    if not result.has_fatal_errors:
        result.workbook_examination = _examine(
            result, facts, target_ws._worksheet_path, chosen_sheet, sheet_states, full_raw_rows)
    if chosen_sheet != sheetnames[0] and ranked:
        rationale = (
            ranked[0].rationale if ranked[0].name == chosen_sheet
            else f"better matches {basis_noun(result.comparison_basis)}-vs-actual data"
        )
        result.visible_transformations.insert(
            0, f"Selected worksheet '{chosen_sheet}' ({rationale}) over '{sheetnames[0]}'"
        )
    return result


def _two_row_header(rows: list[list[object]], max_scan: int = 25) -> tuple[int, list[object], str] | None:
    """A header split over two rows: names on the upper row stand for blank cells of the lower one (X24).

    Returns the lower row's index, the combined header and the note that says so, when the combined
    row is a header and no single row was.
    """
    def blank(cell: object) -> bool:
        return cell is None or str(cell).strip() == ""

    for upper_at in range(min(len(rows), max_scan) - 1):
        upper, lower = rows[upper_at], rows[upper_at + 1]
        if all(blank(cell) for cell in lower):
            continue
        width = max(len(upper), len(lower))
        combined: list[object] = []
        taken: list[str] = []
        for column in range(width):
            below = lower[column] if column < len(lower) else None
            above = upper[column] if column < len(upper) else None
            if blank(below) and not blank(above):
                combined.append(above)
                taken.append(str(above).strip())
            else:
                combined.append(below)
        if taken and detect_header_row([combined])[0] is not None:
            names = ", ".join(f"'{name}'" for name in taken)
            return upper_at + 1, combined, (f"Read the column names from rows {upper_at + 1} and {upper_at + 2} together: "
                                            f"{names} (row {upper_at + 1}) above blank cells of row {upper_at + 2}.")
    return None


def _period_bands(
    raw_rows: list[list[object]], header_idx: int, layout: SheetLayout,
) -> tuple[list[list[object]], list[str]] | None:
    """The rows with each period heading joined onto the Budget/Actual columns below it (E4).

    A heading spans its merged cells, or runs right across blank cells when it is not merged.
    None unless at least two distinct period headings sit directly above the header row.
    """
    if header_idx == 0:
        return None
    above, header = raw_rows[header_idx - 1], raw_rows[header_idx]
    bands = [_statement_cell(above[c]) if c < len(above) else "" for c in range(len(header))]
    merged = [(c1, c2) for r1, c1, _, c2 in layout.merged if r1 == header_idx and c2 > c1]
    carried = ""
    for column in range(len(header)):
        span = next(((c1, c2) for c1, c2 in merged if c1 <= column + 1 <= c2), None)
        if span is not None:
            bands[column] = bands[span[0] - 1]
        elif bands[column]:
            carried = bands[column]
        else:
            bands[column] = carried
    labels = list(dict.fromkeys(band for band in bands if band))
    # A band is a period heading, or a bare year: 2025 | 2026 over Budget/Actual (M3).
    if len(labels) < 2 or not all(_PERIOD_RE.fullmatch(label) or _BARE_YEAR_RE.fullmatch(label) for label in labels):
        return None
    combined: list[object] = []
    for column, cell in enumerate(header):
        role = match_column_synonym(str(cell).strip())[0] if cell is not None and str(cell).strip() else None
        joins = bands[column] and role in {CanonicalRole.BUDGET, CanonicalRole.ACTUAL}
        combined.append(f"{bands[column]} {str(cell).strip()}" if joins else cell)
    return [*raw_rows[:header_idx], combined, *raw_rows[header_idx + 1:]], labels


def _table_blocks(raw_rows: list[list[object]], header_idx: int) -> list[tuple[int, int]]:
    """Column ranges of tables side by side, split by columns blank from the header down (E5)."""
    below = raw_rows[header_idx:]
    width = max((len(row) for row in below), default=0)

    def blank(column: int) -> bool:
        return all(column >= len(row) or row[column] is None or str(row[column]).strip() == "" for row in below)

    blocks: list[tuple[int, int]] = []
    start: int | None = None
    for column in range(width + 1):
        if column == width or blank(column):
            if start is not None:
                blocks.append((start, column - 1))
                start = None
        elif start is None:
            start = column
    return blocks if len(blocks) >= 2 else []


def _block_name(block: tuple[int, int]) -> str:
    return f"columns {column_letters(block[0] + 1)}-{column_letters(block[1] + 1)}"


def _only_block(raw_rows: list[list[object]], header_idx: int, block: tuple[int, int]) -> list[list[object]]:
    """The rows with every other table blanked from the header down; columns keep their places."""
    first, last = block
    return [*raw_rows[:header_idx],
            *([cell if first <= c <= last else None for c, cell in enumerate(row)] for row in raw_rows[header_idx:])]


def _block_reads(raw_rows: list[list[object]], header_idx: int, block: tuple[int, int],
                 compare_to: ComparisonBasis | None) -> bool:
    rows = _only_block(raw_rows, header_idx, block)
    found, _, _ = detect_header_row(rows)
    return found == header_idx and detect_comparison_columns(rows[header_idx], compare_to=compare_to).basis is not None


def _block_note(raw_rows: list[list[object]], header_idx: int, chosen: tuple[int, int],
                blocks: list[tuple[int, int]], sheet_name: str | None) -> str:
    header = raw_rows[header_idx]
    others = [f"a table in {_block_name(b)} "
              f"({', '.join(str(header[c]).strip() for c in range(b[0], b[1] + 1) if c < len(header) and header[c] is not None)}), "
              f"chosen as sheet '{sheet_name} ({_block_name(b)})'" for b in blocks if b != chosen]
    return f"Read the table in {_block_name(chosen)}; this sheet also has {'; '.join(others)}."


_STATEMENT_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def _statement_cell(value: object) -> str:
    return "" if value is None else str(value).strip()


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _looks_like_edgar_title(cell: object) -> bool:
    if not isinstance(cell, str):
        return False
    head, separator, _ = cell.strip().partition(" - ")
    return bool(separator) and statement_title(head) is not None


def _as_shown(value: Decimal, places: int | None) -> Decimal:
    """The amount Excel displays: at the format's decimal places, or at 15 significant digits for
    General (beyond them a binary float's decimal text is representation error, not the figure)."""
    with financial_context() as context:
        context.traps[Inexact] = False
        if places is not None:
            return value.quantize(Decimal(1).scaleb(-places))
        if value == 0 or len(value.as_tuple().digits) <= 15:
            return value
        return value.quantize(Decimal(1).scaleb(value.adjusted() - 14)).normalize()


def _breakdown_start(body: list[tuple[str, list[str]]]) -> int | None:
    """Where breakdowns stacked under a statement begin (a member, a share class, a second entity).

    The SEC repeats the statement for each member of a breakdown below the consolidated lines,
    under the member's name: a "[Member]" row, or a heading after which the statement restarts
    (its next heading repeats an earlier one).
    """
    headings: list[str] = []
    for index, (label, values) in enumerate(body):
        if any(values):
            continue
        if label.endswith("[Member]"):
            return index
        following = next(((text, row) for text, row in body[index + 1:] if text), None)
        if (label and following is not None and not any(following[1]) and following[0] in headings
                and label not in headings):
            return index
        headings.append(label)
    return None


def _breakdown_heads(body: list[tuple[str, list[str]]], cut: int) -> list[str]:
    """The member names heading each repeated section from `cut` on."""
    restart = next((text for text, _ in body[cut + 1:] if text), None)
    heads = []
    for index in range(cut, len(body)):
        label, values = body[index]
        if not label or any(values):
            continue
        following = next((text for text, _ in body[index + 1:] if text), None)
        if label.endswith("[Member]") or (index == cut) or (following == restart and label != restart):
            heads.append(label)
    return list(dict.fromkeys(heads))


def _edgar_statement_tables(
    raw_rows: list[list[object]], layout: SheetLayout, *, per_share_lines: bool,
    shown_places: dict[int, int] | None = None, notes: list[str] | None = None,
) -> list[StatementTable]:
    """Statements on a sheet laid out like EDGAR's Financial_Report.xlsx (E3).

    The SEC writes the statement title and its unit caption in one cell ("CONSOLIDATED
    STATEMENTS OF OPERATIONS - USD ($) $ in Millions"), a duration band ("12 Months Ended",
    merged over its columns) above the period dates, or the dates alone for a balance sheet,
    then one row per line. Empty when the sheet is not in that shape.
    """
    if not raw_rows or not raw_rows[0] or not isinstance(raw_rows[0][0], str):
        return []
    head, separator, caption = raw_rows[0][0].strip().partition(" - ")
    title = statement_title(head) if separator else None
    if title is None:
        return []
    width = max(len(row) for row in raw_rows[:2])
    band = [_statement_cell(raw_rows[0][c]) if c < len(raw_rows[0]) else "" for c in range(width)]
    for first_row, first_column, _, last_column in layout.merged:
        if first_row == 1 and first_column >= 2:
            for column in range(first_column, min(last_column, width) + 1):
                band[column - 1] = band[first_column - 1]
    second = raw_rows[1] if len(raw_rows) > 1 else []
    dates = [_statement_cell(second[c]) if c < len(second) else "" for c in range(width)]
    if any(_STATEMENT_YEAR.search(text) for text in dates[1:]):
        headers, body_start = [f"{band[c]} {dates[c]}".strip() for c in range(1, width)], 2
    else:
        headers, body_start = band[1:], 1
    if sum(1 for header in headers if _STATEMENT_YEAR.search(header)) < 2:
        return []
    columns = [c for c in range(1, width) if headers[c - 1]]  # unheaded columns hold footnote marks
    shown = shown_places or {}
    rounded: list[tuple[str, Decimal, Decimal]] = []
    body: list[tuple[str, list[str]]] = []
    for r_idx, row in enumerate(raw_rows[body_start:], start=body_start + 1):
        values = []
        for c in columns:
            value = row[c] if c < len(row) else None
            if isinstance(value, Decimal):
                displayed = _as_shown(value, shown.get(cell_key(r_idx, c + 1)))
                if displayed != value:
                    rounded.append((f"{column_letters(c + 1)}{r_idx}", value, displayed))
                value = displayed
            values.append(_statement_cell(value))
        body.append((_statement_cell(row[0]) if row else "", values))
    cut = _breakdown_start(body)
    if notes is not None:
        if rounded:
            cell, stored, displayed = rounded[0]
            notes.append(f"Read {_plural(len(rounded), 'amount')} as the workbook shows {'it' if len(rounded) == 1 else 'them'} "
                         f"(cell {cell}: stored {stored}, shown {displayed}); the SEC writes these workbooks with "
                         "binary floating-point numbers")
        if cut is not None:
            notes.append(f"Left out the breakdown that follows the statement from row {body_start + cut + 1}: "
                         + ", ".join(f"'{head}'" for head in _breakdown_heads(body, cut)))
    if cut is not None:
        body = body[:cut]
    return statement_tables_from_grid(title, caption.strip(), [headers[c - 1] for c in columns], body,
                                      per_share_lines=per_share_lines)


def _read_edgar_statement(
    tables: list[StatementTable], duration: str | None, raw_rows: list[list[object]], filename: str,
    sheet_name: str, excel: _ExcelSheet, *, treat_blank_budgets_as_zero: bool, selected_period: str | None,
    compare_to: ComparisonBasis | None, sheet_notes: list[str] | None = None,
) -> IntakeResult:
    """Read one statement of an EDGAR-style sheet as the PDF reader reads one (E3)."""
    def duration_of(table: StatementTable) -> str:
        return table.name.rpartition(", ")[2] if ", " in table.name else ""

    chosen = tables[0] if duration is None else next((t for t in tables if duration_of(t) == duration), None)
    if chosen is None:
        named = ", ".join(f"'{sheet_name} ({duration_of(t)})'" for t in tables if duration_of(t)) or f"'{sheet_name}'"
        return IntakeResult(has_fatal_errors=True, sheet_name=sheet_name, fatal_error_message=(
            f"Sheet '{sheet_name}' has no {duration} columns. Choose one of: {named}."))
    # A machine-written statement has no formulas, hidden lines or scaled formats; refuse any.
    stop = _unsaved_formulas_stop(excel, filename, lambda r, c: True, describe_cell, sheet_name)
    if stop is not None:
        return stop
    hidden = hidden_data_rows(excel.layout, raw_rows, header_row=1, line_item_column=0)
    if hidden and excel.hidden_rows is None:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=hidden_rows_question(hidden),
                            sheet_name=sheet_name, hidden_data_rows=hidden, needs_hidden_rows_choice=True)
    if hidden and excel.hidden_rows == "exclude":
        # A statement's subtotals foot over every line, so lines can't be dropped from it.
        return _statement_refusal(sheet_name, "has lines hidden in Excel, and leaving lines out would break the "
                                  "statement's subtotals. Count them, or unhide them")
    if excel.display:
        return _statement_refusal(sheet_name, "shows some amounts scaled by their number format, so their unit "
                                  "can't be read from the caption. Give the amounts a plain number format")
    if chosen.kind in _NOT_REVENUE_AND_EXPENSE:
        return IntakeResult(has_fatal_errors=True, sheet_name=sheet_name, fatal_error_message=(
            f"'{chosen.name}' lists {_NOT_REVENUE_AND_EXPENSE[chosen.kind]}, which can't be compared as revenue "
            "and expense yet. Choose the income statement's sheet instead."))
    shaped = shape_income_statement(chosen.raw_rows)
    result = _process_raw_table(
        shaped.rows, filename, sheet_name=sheet_name, treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
        selected_period=selected_period, compare_to=compare_to, signs_resolved=shaped.shaped,
    )
    result.source_kind = "edgar_xlsx"
    result.source_statement = chosen.name
    result.reader_notes = [*chosen.notes, *shaped.audit_notes]
    result.detected_totals[:0] = shaped.subtotals
    others = [f"This sheet also has {t.name}; choose it as sheet '{sheet_name} ({duration_of(t)})'"
              for t in tables if t is not chosen and duration_of(t)]
    read_note = f"Read '{chosen.name}' from sheet '{sheet_name}', laid out as in an EDGAR Financial_Report.xlsx"
    result.visible_transformations[:0] = [read_note, *(sheet_notes or []), *chosen.notes, *shaped.notes, *others]
    result.layout_notes[:0] = [read_note, *(sheet_notes or []), *others]
    result.reader_notes[:0] = list(sheet_notes or [])
    result.layout_read = True
    return result


def _statement_refusal(sheet_name: str, problem: str) -> IntakeResult:
    return IntakeResult(has_fatal_errors=True, sheet_name=sheet_name,
                        fatal_error_message=f"Sheet '{sheet_name}' {problem}, and upload the file again.")


def _half_width(decimals: str) -> Decimal:
    """Half the rounding interval a fact's `decimals` states (XBRL Calculations 1.1, 5.2.3)."""
    if decimals.strip().upper() == "INF" or not re.fullmatch(r"-?\d+", decimals.strip()):
        return Decimal(0)
    return Decimal("0.5").scaleb(-int(decimals))


def _foots(terms: list[tuple[Decimal, str, int]], total: tuple[Decimal, str]) -> bool:
    """R5: the weighted terms' rounding intervals, summed, overlap the total's (closed intervals)."""
    with financial_context():
        centre = sum((value * weight for value, _, weight in terms), Decimal(0))
        spread = sum((_half_width(decimals) for _, decimals, _ in terms), Decimal(0)) + _half_width(total[1])
        return abs(centre - total[0]) <= spread


# A section's own subtotal closes it: a "Total …" line, or a cash flow section's "Net cash … activities" (Decision 41).
_SECTION_CLOSER = re.compile(r"^total\b|^net\s+cash\b.*\bactivities\b", re.IGNORECASE)


def _unique_names(lines: list[tuple[str, str]], keep: int | None = None, closers: set[int] | None = None) -> list[str]:
    """Tell repeated labels apart by section, else by their place; keys stay with the line by position.

    A line printed after its section's own subtotal (a "Total …" or "Net cash … activities" line, or one of
    ``closers``) is not in that section, so it is never named by it. Where one occurrence of a label is in no
    open section and the others are each in their own, that one keeps its printed label; so does the line at
    ``keep`` (a statement's bottom line, Decision 39).
    """
    labels = [label for label, _ in lines]
    closed: set[str] = set()
    sections: list[str] = []
    for i, (label, section) in enumerate(lines):
        sections.append("" if section in closed else section)
        if section and (_SECTION_CLOSER.match(label) or i in (closers or set())):
            closed.add(section)
    names = list(labels)
    for label in {label for label in labels if labels.count(label) > 1}:
        at = [i for i, name in enumerate(labels) if name == label]
        by_section = [sections[i] for i in at]
        named = [section for section in by_section if section]
        distinct = len(set(named)) == len(named)
        one_open = distinct and len(named) == len(at) - 1  # exactly one occurrence outside every open section
        by_name = one_open or (distinct and len(named) == len(at))
        for n, (i, section) in enumerate(zip(at, by_section, strict=True), start=1):
            if i == keep or (one_open and not section):
                continue  # keeps its printed label
            names[i] = f"{section}: {label}" if by_name else f"{label} ({n})"
    return names


_COUNT_WORDS = {2: "twice", 3: "three times", 4: "four times"}


def _numbered_notes(labels: list[str], names: list[str]) -> list[str]:
    """Which numbered copy of a repeated label is which, by the printed line each follows (M5)."""
    notes: list[str] = []
    for label in dict.fromkeys(label for label, name in zip(labels, names, strict=True) if name == f"{label} (1)"):
        at = [i for i, name in enumerate(names) if re.fullmatch(rf"{re.escape(label)} \(\d+\)", name)]
        places = [f"({n}) is " + ("the first line" if i == 0 else f"the one after '{labels[i - 1]}'")
                  for n, i in enumerate(at, start=1)]
        times = _COUNT_WORDS.get(len(at), f"{len(at)} times")
        notes.append(f"'{label}' is printed {times} with no section to tell the copies apart: "
                     + ", ".join([places[0], *(place.replace(" is ", " ", 1) for place in places[1:])]) + ".")
    return notes


def _key_record(label: str, key: LineKey | None) -> dict[str, object] | None:
    if key is None:
        return None
    return {"label": label, "concept": key.concept, "context": key.context, "period": list(key.period),
            "dims": [{"axis": axis, "member": member} for axis, member in key.dims],
            "stored": format(key.stored, "f"), "displayed": format(key.displayed, "f"), "decimals": key.decimals}


def _read_ixbrl_bytes(
    data: bytes,
    filename: str,
    sheet: str | None,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
    per_share_lines: bool = False,
) -> IntakeResult:
    """Read one face statement from an Inline XBRL 10-K or 10-Q; each statement acts like a worksheet."""
    try:
        statements = read_statements(data, filename, per_share_lines=per_share_lines)
    except IxbrlError as exc:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc), source_kind="ixbrl")
    names = [s.name for s in statements]
    comparable = names  # balance sheets and cash flows compare as Increase or Decrease (R7)
    ranked = rank_statements(names)
    chosen = next((s for s in statements if s.name == (ranked[0].name if sheet is None else sheet)), None)
    if chosen is None:
        return IntakeResult(has_fatal_errors=True, available_sheets=names, source_kind="ixbrl", fatal_error_message=(
            f"No statement called '{sheet}' was found in '{filename}'. Statements found: {', '.join(names)}. "
            "Choose one of those statements."))
    if chosen.problem:
        return IntakeResult(has_fatal_errors=True, available_sheets=names, source_kind="ixbrl",
                            fatal_error_message=chosen.problem)
    if chosen.kind in _NOT_REVENUE_AND_EXPENSE:
        result = _read_ixbrl_position(chosen, filename, treat_blank_budgets_as_zero, selected_period, compare_to)
        result.candidate_sheets, result.available_sheets, result.comparable_sheets = ranked, names, comparable
        return _with_period_names(result, chosen.names)
    all_lines = chosen.lines
    # A comprehensive-income statement opens with net income, so only an income statement ends there. The
    # bottom line is found by its concept or printed label before repeated labels are told apart (Decision 39).
    bottom = next((i for i, line in enumerate(all_lines) if BOTTOM_LINE.match(line.concept)
                   or BOTTOM_LINE_LABEL.match(line.label)), None) if chosen.kind == "income" else None
    all_names = _unique_names([(line.label, line.section) for line in all_lines], keep=bottom,
                              closers={i for i, line in enumerate(all_lines) if line.section_total})
    below = [] if bottom is None else list(range(bottom + 1, len(all_lines)))
    lines = all_lines[:bottom + 1] if bottom is not None else all_lines
    names_by_line = all_names[:len(lines)]
    measures = any(line.measure != "Currency" for line in lines)
    header: list[object] = ["Line Item", *chosen.labels, *(["Measure", "Better"] if measures else [])]
    raw_rows: list[list[object]] = [header]
    blanks: list[tuple[int, int]] = []
    for at, (name, line) in enumerate(zip(names_by_line, lines, strict=True)):
        # A column with no fact reads as 0 where the line prints a dash; a blank one reads as 0 only once
        # a footed subtotal confirms it (below), and refuses otherwise.
        cells: list[object] = [format(key.displayed, "f") if key is not None else ("—" if line.dash else "0")
                               for key in line.keys]
        blanks += [(at, column) for column, key in enumerate(line.keys) if key is None and not line.dash]
        if measures:
            cells += [line.measure, "Higher" if line.measure == "Per Share" else ""]
        raw_rows.append([name, *cells])
    precisions = [int(key.decimals) for line in lines if line.measure == "Currency" for key in line.keys
                  if key is not None and re.fullmatch(r"-?\d+", key.decimals)]
    unit = Decimal(1).scaleb(-min(precisions)) if precisions else None
    # A line whose concept is a total is offered to the shaper as a subtotal; one that then adds up
    # from nothing is a detail line that borrowed a total's concept, and is read as a line.
    hints = {i for i, line in enumerate(lines) if line.total}
    while True:
        shaped = shape_income_statement(raw_rows, unit, FILING_SUBTOTALS, frozenset(hints),
                                        frozenset(i for i in hints if lines[i].section_total), zero_lines_signless=True,
                                        openings_as_lines=True, keep_printed_signs=True)
        matched = {row for row, _ in shaped.matches} | set(shaped.openings)
        # The bottom line is net income by its concept, whatever it is named (Decision 39): never demoted.
        demote = {i for i in hints if i not in matched and i != bottom and not names_subtotal(names_by_line[i])
                  and not FILING_SUBTOTALS.search(names_by_line[i])}
        if not demote:
            break
        hints -= demote
    fail = _footing_failure(shaped, lines, names_by_line, chosen.name)
    if fail is not None and chosen.runs_on:
        fail = _runs_on_refusal(chosen.name)
    if fail is not None:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=fail, sheet_name=chosen.name, source_kind="ixbrl")
    confirmed = {total for total, _ in shaped.matches} | {term for _, terms in shaped.matches for term, _ in terms}
    unconfirmed = next(((at, column) for at, column in blanks if at not in confirmed), None)
    if unconfirmed is not None:
        at, column = unconfirmed
        return IntakeResult(has_fatal_errors=True, sheet_name=chosen.name, source_kind="ixbrl", fatal_error_message=(
            f"'{names_by_line[at]}' prints no figure for {chosen.labels[column]} in the {chosen.name}, and no subtotal "
            "there confirms it is 0, so I stopped instead of guessing. Choose another statement from this filing."))
    blank_notes = [f"Read the blank {chosen.labels[column]} figure of '{names_by_line[at]}' as 0: the subtotal it sits "
                   "in adds up with it at 0" for at, column in blanks]
    credits = _revenue_block_credits(shaped, lines, names_by_line)
    # A line the statement's arithmetic can't place is never typed by its label (Decision 42): it stays unclassified,
    # shown as printed, and carries no F or U until the analyst labels it.
    type_at = next(row for row in shaped.rows if row and row[0] == "Line Item").index("Type")
    data_from = next(i for i, row in enumerate(shaped.rows) if row and row[0] == "Line Item") + 1
    for row in shaped.rows[data_from:]:
        if not str(row[type_at] or "").strip():
            row[type_at] = "Unclassified"
    # Footing has already set the statement's subtotals aside, so every line kept is a detail line, whatever
    # its label says ("Total revenue, net" printed alone); the engine's own Total check never stops it (Decision 39).
    header_at = next(i for i, row in enumerate(shaped.rows) if row and row[0] == "Line Item")
    shaped.rows[header_at:] = [[*shaped.rows[header_at], "Row Kind"],
                               *([*row, "Detail"] for row in shaped.rows[header_at + 1:])]
    result = _process_raw_table(
        shaped.rows, filename, sheet_name=chosen.name, treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
        selected_period=selected_period, compare_to=compare_to, signs_resolved=shaped.shaped,
    )
    if not result.has_fatal_errors:
        actual_label = str(result.column_mapping.get(CanonicalRole.ACTUAL, ""))
        comparison_label = str(result.column_mapping.get(CanonicalRole.BUDGET, ""))
        if actual_label in chosen.labels and comparison_label in chosen.labels:
            result.filing_headline = _filing_headline(
                shaped, lines, names_by_line, bottom,
                (chosen.labels.index(actual_label), chosen.labels.index(comparison_label)), (actual_label, comparison_label))
            if unit_text := _unit_sentence(lines):
                result.filing_headline["unit"] = unit_text
    if not result.has_fatal_errors and credits:
        # A line both compared columns print as zero changes nothing compared: it is not called a credit among
        # costs on the strength of another year the statement prints (Decision 41).
        zero = {str(row["line_item"]) for row in result.rows
                if Decimal(str(row.get("actual") or 0)) == 0 and Decimal(str(row.get("budget") or 0)) == 0}
        credits = [note for note in credits if not any(note.startswith(f"Read '{name}' as a credit") for name in zero)]
        for at, note in enumerate(shaped.audit_notes):
            for name in zero:
                if note == f"Labeled '{name}' as expense, a credit among costs":
                    shaped.audit_notes[at] = f"Labeled '{name}' as expense"
        credits = _credits_by_year(credits, result, shaped)
    left_out = [f"Left out {item}" for item in chosen.left_out]
    if below and bottom is not None:
        left_out.append(f"Left out {_plural(len(below), 'line')} below '{all_names[bottom]}' (how net income is "
                        f"attributed): {', '.join(repr(all_names[i]) for i in below)}".replace('"', "'"))
    result.visible_transformations[:0] = credits
    # The report itself says why a line is read as it is: every sign it turns, and every credit among costs
    # (Decisions 39, 42).
    reading = [*(note for note in shaped.notes if " the statement prints it as " in note), *credits]
    if reading:
        from .report import _safe_inline
        result.report_appendix = ["## How the filing was read", "", *(f"- {_safe_inline(note)}" for note in reading)]
    result.source_kind = "ixbrl"
    result.source_statement = chosen.name
    result.document_currency = chosen.currency
    unit_note = [f"Units: {unit_text}"] if (unit_text := _unit_sentence(lines)) else []
    result.reader_notes = [*chosen.notes, *unit_note, *left_out, *shaped.audit_notes, *credits, *blank_notes,
                           *_numbered_notes([line.label for line in all_lines], all_names)]
    result.xbrl_lines = [
        {"line_item": all_names[i], "concept": all_lines[i].concept, "measure": all_lines[i].measure,
         "subtotal": i < len(lines) and i not in shaped.kept, "left_out": i >= len(lines),
         "columns": [_key_record(label, key) for label, key in zip(chosen.labels, all_lines[i].keys, strict=True)]}
        for i in range(len(all_lines))]
    result.candidate_sheets = ranked
    result.available_sheets = names
    result.comparable_sheets = comparable
    result.detected_totals[:0] = shaped.subtotals
    result.visible_transformations[:0] = [f"Read '{chosen.name}' from the Inline XBRL filing", *left_out, *shaped.notes,
                                          *blank_notes]
    return _with_period_names(result, chosen.names)


def _with_period_names(result: IntakeResult, names: dict[str, str]) -> IntakeResult:
    """Each column label's display name ("3 months ended Mar 2026"), and the comparing note in those words (M4)."""
    result.period_names = dict(names)
    actual = str(result.column_mapping.get(CanonicalRole.ACTUAL, ""))
    comparison = result.comparison_label or ""
    said = f"Comparing {actual} against {comparison} ("
    for at, note in enumerate(result.visible_transformations):
        if names and note.startswith(said):
            result.visible_transformations[at] = (f"Comparing {names.get(actual, actual)} against "
                                                  f"{names.get(comparison, comparison)} (" + note[len(said):])
    return result


_CHANGE_NOTE = ("Compared each line as an Increase or Decrease of its printed figure: a figure printed in parentheses "
                "is negative, so a larger outflow or deduction shows as a Decrease")
_IDENTITY_NAME = {"balance_sheet": "the balance sheet identity", "cash_flow": "the cash roll-forward"}


def _read_ixbrl_position(chosen: IxStatement, filename: str, treat_blank_budgets_as_zero: bool,
                         selected_period: str | None, compare_to: ComparisonBasis | None) -> IntakeResult:
    """A balance sheet or cash flow statement: every line at its printed value, checked by R9 first (R7)."""
    money = [line for line in chosen.lines if line.measure == "Currency"]
    others = [f"Left out '{line.label}' (per-share and share counts are not money totals)"
              for line in chosen.lines if line.measure != "Currency"]
    names = _unique_names([(line.label, line.section) for line in money],
                          closers={i for i, line in enumerate(money) if line.section_total})
    figures = [CheckLine(names[i], line.concept, tuple(
        (key.displayed, key.decimals) if key is not None else ((Decimal(0), "INF") if line.dash else None)
        for key in line.keys), line.balance) for i, line in enumerate(money)]
    checked = (check_balance_sheet if chosen.kind == "balance_sheet" else check_cash_flow)(figures, chosen.name, chosen.labels)
    if checked.problem or checked.closing is None or checked.sides is None:
        problem = _runs_on_refusal(chosen.name) if chosen.runs_on else checked.problem
        return IntakeResult(has_fatal_errors=True, sheet_name=chosen.name, source_kind="ixbrl",
                            fatal_error_message=problem or f"I couldn't check the {chosen.name}. Upload a CSV or "
                                                                   "Excel copy of the statement instead.")
    closing, totals = checked.closing, {row for row, _ in checked.matches}
    # Every subtotal the check footed closes its section too ("Property and equipment, net"), so a repeated label
    # after it is never named by that section (Decision 41).
    names = _unique_names([(line.label, line.section) for line in money],
                          closers={i for i, line in enumerate(money) if line.section_total} | totals)
    raw_rows: list[list[object]] = [["Line Item", *chosen.labels, "Statement Kind", "Row Kind"]]
    for i, line in enumerate(money[:closing + 1]):
        # A dash reads as 0 through intake's own dash rule; a blank the footing confirmed is 0 (R9).
        cells = [format(key.displayed, "f") if key is not None else ("—" if line.dash else "0") for key in line.keys]
        raw_rows.append([names[i], *cells, chosen.kind, "Total" if i in totals else "Detail"])
    result = _process_raw_table(raw_rows, filename, sheet_name=chosen.name,
                                treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
                                selected_period=selected_period, compare_to=compare_to, signs_resolved=True)
    if result.has_fatal_errors:
        return result
    after = names[closing + 1:]
    left_out = [f"Left out {item}" for item in chosen.left_out] + others
    if after:
        left_out.append(f"Left out {_plural(len(after), 'line')} after '{names[closing]}' (supplemental disclosures): "
                        + ", ".join(f"'{name}'" for name in after))
    identity = f"Checked every subtotal and {_IDENTITY_NAME[chosen.kind]}: {checked.identity}"
    unit_note = [f"Units: {unit}"] if (unit := _unit_sentence(money)) else []  # Decision 40
    blanks = [f"Read the blank {chosen.labels[column]} figure of '{names[row]}' as 0: the subtotal it sits in adds up "
              "with it at 0" for row, column in checked.blanks if not money[row].dash]
    result.source_kind = "ixbrl"
    result.source_statement = chosen.name
    result.document_currency = chosen.currency
    result.statement_kind = chosen.kind
    result.statement_checks = [*unit_note, identity, *left_out, *blanks, _CHANGE_NOTE]
    left, right = checked.sides
    rule = ("total assets = total liabilities and equity" if chosen.kind == "balance_sheet"
            else "ending cash = beginning cash + the flows printed between them")
    result.identities = [{"identity": chosen.kind, "rule": rule, "left": names[left], "right": names[right],
                          "columns": list(chosen.labels), "holds": True,
                          # R9: every subtotal footed, with its terms; each term's decimals are on its line's keys.
                          "footing": [{"subtotal": names[total], "terms": [{"line_item": names[term], "weight": weight}
                                                                           for term, weight in terms]}
                                      for total, terms in checked.matches]}]
    result.reader_notes = [*chosen.notes, *unit_note, *left_out, identity, *blanks, _CHANGE_NOTE,
                           *_numbered_notes([line.label for line in money], names)]
    result.xbrl_lines = [
        {"line_item": names[i], "concept": line.concept, "measure": line.measure,
         "subtotal": i in totals, "left_out": i > closing,
         "columns": [_key_record(label, key) for label, key in zip(chosen.labels, line.keys, strict=True)]}
        for i, line in enumerate(money)]
    result.visible_transformations[:0] = [f"Read '{chosen.name}' from the Inline XBRL filing", *left_out, identity,
                                          *blanks, _CHANGE_NOTE]
    return result


_REVENUE_CONCEPT = re.compile(r"^us-gaap:(?:Revenues|RevenueFromContractWithCustomer\w*|SalesRevenue\w*"
                              r"|RevenuesNetOfInterestExpense|RevenueNet)$")


def _revenue_block(shaped: ShapedStatement, lines: list[IxLine]) -> tuple[set[int], int | None]:
    """The lines of the filing's printed revenue, and the one that names it: its total when the statement prints
    one, else its first line (Decision 28). Empty, and None, where the statement prints no revenue concept."""
    terms = dict(shaped.matches)
    block: set[int] = set()

    def take(row: int) -> None:
        if row in block:
            return
        block.add(row)
        for term, _ in terms.get(row, []):
            take(term)

    for i, line in enumerate(lines):
        # A revenue concept on a one-axis breakdown line (fees by product on a bank's statement) is part of
        # some revenue, not the filing's revenue: only a dimensionless revenue fact defines the block.
        if _REVENUE_CONCEPT.match(line.concept) and not any(key is not None and key.dims for key in line.keys):
            take(i)
    if not block:
        return block, None
    totals = [i for i in sorted(block) if i in terms]
    return block, totals[-1] if totals else min(block)


_SCALE_WORDS = {0: "full amounts", 3: "thousands", 6: "millions", 9: "billions"}


def _unit_sentence(lines: list[IxLine]) -> str:
    """The unit the filing prints a statement's money in, from its facts' scale (Decision 40). Label text is quoted
    as printed, so its amounts are in that unit while the report shows every figure in full."""
    scales: dict[int, int] = {}
    for line in lines:
        if line.measure == "Currency":
            for key in line.keys:
                if key is not None:
                    scales[key.scale] = scales.get(key.scale, 0) + 1
    if not scales:
        return ""
    words = [_SCALE_WORDS.get(scale, f"units of 10^{scale}") for scale, _ in sorted(scales.items(), key=lambda kv: -kv[1])]
    if words == ["full amounts"]:
        return "The filing prints these figures in full, as this report shows them."
    unit = f"at more than one scale ({' and '.join(words)})" if len(words) > 1 else f"in {words[0]}"
    return (f"The filing prints these figures {unit}; this report shows them in full, and amounts inside line labels "
            "are quoted as the filing prints them.")


_EXPENSE_TOTAL = re.compile(r"^us-gaap:(?:CostsAndExpenses|OperatingExpenses|BenefitsLossesAndExpenses|NoninterestExpense)$")
_OPERATING_INCOME = "us-gaap:OperatingIncomeLoss"


def _filing_headline(shaped: ShapedStatement, lines: list[IxLine], names: list[str], bottom: int | None,
                     columns: tuple[int, int], labels: tuple[str, str]) -> dict[str, object]:
    """The filing's own printed totals for the report's headline (Decision 39): its revenue, total expenses,
    operating income and net income, whichever it prints, each from its fact for the two columns compared.
    Nothing here is added up: a revenue printed as several lines without a total is named, not summed."""
    block, named = _revenue_block(shaped, lines)
    roles: dict[int, str] = {}
    notes: list[str] = []
    if named is not None and (named in dict(shaped.matches) or len(block) == 1):
        roles[named] = "revenue"
    elif named is not None:
        shown = ", ".join(f"'{names[i]}'" for i in sorted(block))
        notes.append(f"The filing prints its revenue as {len(block)} lines with no total of its own ({shown}), so no "
                     "revenue figure heads this report.")
    for i, line in enumerate(lines):
        if _EXPENSE_TOTAL.match(line.concept):
            roles.setdefault(i, "expenses")
        elif line.concept == _OPERATING_INCOME:
            roles.setdefault(i, "operating_income")
    if bottom is not None and bottom < len(lines):
        roles.setdefault(bottom, "net_income")
    items: list[dict[str, object]] = []
    for i in sorted(roles):
        now, before = (lines[i].keys[c] for c in columns)
        missing = [label for key, label in zip((now, before), labels, strict=True) if key is None or key.dims]
        if now is None or before is None or missing:
            notes.append(f"'{names[i]}' prints no tagged figure for {' or '.join(missing)}, so it isn't in the headline.")
            continue
        with financial_context():
            change = now.displayed - before.displayed
            percent = ratio(change, abs(before.displayed)) if before.displayed != 0 else None
        items.append({"role": roles[i], "line_item": names[i], "concept": lines[i].concept,
                      "actual": _key_record(labels[0], now), "comparison": _key_record(labels[1], before),
                      "change": format(change, "f"), "change_percent": None if percent is None else format(percent, "f")})
    return {"items": items, "notes": notes}


def _credits_by_year(credits: list[str], result: IntakeResult, shaped: ShapedStatement) -> list[str]:
    """Call a line among costs a credit only where it adds to income in every compared year it prints.

    A line read among costs with its sign turned is a credit where its compared value comes out
    negative; where one comes out positive, that year it reduced income (a loss), and the note names
    the years each way instead (C4). Values and labels are unchanged.
    """
    years = (str(result.column_mapping.get(CanonicalRole.ACTUAL, "")),
             str(result.column_mapping.get(CanonicalRole.BUDGET, "")))
    rows = {str(row["line_item"]): row for row in result.rows}
    reworded: list[str] = []
    for note in credits:
        name = next((n for n in rows if note.startswith(f"Read '{n}' as a credit among costs: ")), None)
        if name is None:
            reworded.append(note)
            continue
        values = (Decimal(str(rows[name].get("actual") or 0)), Decimal(str(rows[name].get("budget") or 0)))
        adds = [year for year, value in zip(years, values, strict=True) if value < 0]
        reduces = [year for year, value in zip(years, values, strict=True) if value > 0]
        if not reduces:
            reworded.append(note)
            continue
        revenue = note.split(": the filing's revenue is ", 1)[1].removesuffix(", and this line is not part of it")
        ways = ([f"adds to income in {' and '.join(adds)}"] if adds else []) + \
               [f"reduces {'it' if adds else 'income'} in {' and '.join(reduces)}"]
        reworded.append(f"Read '{name}' among costs with its sign turned: it {' and '.join(ways)}, and the filing's "
                        f"revenue is {revenue}, which it is not part of")
        shaped.audit_notes = [f"Labeled '{name}' as expense, among costs with its sign turned"
                              if audit == f"Labeled '{name}' as expense, a credit among costs" else audit
                              for audit in shaped.audit_notes]
    return reworded


def _revenue_block_credits(shaped: ShapedStatement, lines: list[IxLine], names: list[str]) -> list[str]:
    """Keep Total Revenue to the filing's revenue: lines outside it that add to income are cost-side credits.

    The shaper labels every line that adds to income as revenue. Where the statement prints its
    revenue (a revenue concept, or a total summing such lines), only that block is revenue; other
    income (equity earnings, gains, other income, net) is relabeled an expense with its sign turned,
    which leaves net income and the net variance unchanged. Returns the notes it adds.
    """
    block, named = _revenue_block(shaped, lines)
    if named is None:
        return []
    header = next(row for row in shaped.rows if row and row[0] == "Line Item")
    at = shaped.rows.index(header)
    type_at = header.index("Type")
    revenue, concept = names[named], lines[named].concept
    notes: list[str] = []
    credited: set[str] = set()
    for data_index, row in zip(shaped.kept, shaped.rows[at + 1:], strict=True):
        if not str(row[type_at] or "").strip() and data_index not in block \
                and infer_line_type(str(row[0]))[0] is LineType.REVENUE:
            # A line the arithmetic couldn't place is not made revenue by its label (Decision 39): it stays for
            # the analyst to label, listed as unclassified.
            row[type_at] = "Unclassified"
            notes.append(f"Left '{row[0]}' unlabeled: the statement's arithmetic doesn't show whether it adds to or "
                         f"reduces income, and the filing's revenue is '{revenue}' ({concept}), which it is not part of")
            continue
        if row[type_at] != "Revenue" or data_index in block:
            continue
        row[type_at] = "Expense"
        for column in range(1, type_at):
            if header[column] in {"Measure", "Better"} or row[column] in ("", "—"):
                continue
            with financial_context():
                # The shaper writes the cells it flips with thousands separators.
                row[column] = format(-Decimal(str(row[column]).replace(",", "")), "f")
        notes.append(f"Read '{row[0]}' as a credit among costs: the filing's revenue is '{revenue}' ({concept}), "
                     "and this line is not part of it")
        credited.add(f"Labeled '{row[0]}' as revenue")
    # The shaper's own notes were written before this: keep them true to the final labels.
    moved = sum(note in credited for note in shaped.audit_notes)
    shaped.audit_notes = [f"{note.removesuffix(' as revenue')} as expense, a credit among costs" if note in credited else note
                          for note in shaped.audit_notes]
    for at_note, note in enumerate(shaped.notes):
        count = _LABEL_COUNT.match(note)
        if count and moved:
            revenue_lines, expense_lines = int(count["revenue"]) - moved, int(count["expense"]) + moved
            shaped.notes[at_note] = (f"Labeled {_plural(revenue_lines, 'line')} revenue and "
                                     f"{_plural(expense_lines, 'line')} expense{count['rest']}")
            audit_at = shaped.audit_notes.index(note)
            shaped.audit_notes[audit_at] = shaped.notes[at_note]
    return notes


_LABEL_COUNT = re.compile(r"^Labeled (?P<revenue>\d+) lines? revenue and (?P<expense>\d+) lines? expense(?P<rest> .*)$")


def _runs_on_refusal(statement: str) -> str:
    """A statement that failed its checks and is followed by an untitled table of other periods (M2)."""
    return (f"The {statement} seems to run on into the next table, which shows other periods, so I couldn't read it "
            "whole and stopped instead of guessing. Upload a CSV or Excel copy of the statement, or the filing's PDF.")


def _footing_failure(shaped: ShapedStatement, lines: list[IxLine], names: list[str], statement: str) -> str | None:
    """R5's refusal, or None when every subtotal foots within its facts' rounding."""
    fix = "Upload a CSV or Excel copy of the statement, or the filing's PDF."
    matched = {total_row for total_row, _ in shaped.matches} | set(shaped.openings)
    # A subtotal is left out of the lines only once it is shown to add up; one that is never checked
    # (nothing above it to add up) would drop a printed figure, so it refuses too.
    unchecked = [names[i] for i in range(len(lines)) if i not in shaped.kept and i not in matched]
    if unchecked:
        missing = unchecked[0]
        row = next(i for i in range(len(lines)) if names[i] == missing)
        if unsure := shaped.ambiguous.get(row):  # two sign readings fit within rounding (C3m)
            which = " and ".join(f"'{names[r]}'" for r in unsure)
            return (f"I couldn't tell whether {which} adds to or takes away from '{missing}' in the {statement}: "
                    "within the rounding of the printed figures, both readings add up, so I stopped instead of "
                    f"guessing. {fix}")
        return (f"I couldn't tell which lines '{missing}' adds up in the {statement}, so I can't check it "
                f"and stopped instead of guessing. {fix}")
    for total_row, terms in shaped.matches:
        for column, total_key in enumerate(lines[total_row].keys):
            if total_key is None:
                continue
            parts = [(key.displayed, key.decimals, weight) for row, weight in terms
                     for key in [lines[row].keys[column]] if key is not None]
            if not _foots(parts, (total_key.displayed, total_key.decimals)):
                return (f"'{names[total_row]}' in the {statement} doesn't add up from the lines above it within the "
                        f"filing's rounding, so I stopped instead of guessing. {fix}")
    return None


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
    per_share_lines: bool = False,
) -> IntakeResult:
    """Read one statement from a 10-K / 10-Q style PDF; each statement acts like a worksheet."""
    try:
        tables = (extract_statement_tables(data, filename, per_share_lines=True) if per_share_lines
                  else extract_statement_tables(data, filename))
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
                f"Statements found: {', '.join(names)}. Choose one of those statements."
            ),
            available_sheets=names,
            source_kind="pdf",
        )
    if chosen.kind in _NOT_REVENUE_AND_EXPENSE:
        income = [t.name for t in tables if t.kind not in _NOT_REVENUE_AND_EXPENSE]
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=(
                f"'{chosen.name}' lists {_NOT_REVENUE_AND_EXPENSE[chosen.kind]}, which can't be "
                "compared as revenue and expense yet. "
                + (f"Choose an income statement instead: {', '.join(income)}." if income
                   else "Upload the income statement instead, or a CSV or Excel copy of it.")
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
    if match := re.search(r"has a footnote mark or small digit \((.+?)\) in: (.*)\.$", detail):
        return (f"'{match.group(2)}' has a footnote mark ({match.group(1)}) next to the amount. "
                "Remove the mark so the cell holds only the amount.")
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


@dataclass(frozen=True)
class _TableCall:
    """The settings of one ``_process_raw_table`` call, which each stage of its read takes."""

    filename: str
    sheet_name: str | None
    treat_blank_budgets_as_zero: bool
    selected_period: str | None
    compare_to: ComparisonBasis | None
    signs_resolved: bool
    from_pdf: bool
    excel: _ExcelSheet | None
    layout_retry: bool


@dataclass
class _TableRead:
    """A table read once its header and comparison basis are known: what each later stage reads and adds."""

    call: _TableCall
    raw_rows: list[list[object]]
    header_idx: int
    roles: dict[CanonicalRole, int]
    ignored_col_indices: list[int]
    date_note: str | None
    detection: ComparisonDetection
    basis: ComparisonBasis  # detection.basis, which a read that goes on always has
    comparison_field: str = ""
    header_str_row: list[str] = field(default_factory=list)
    period_pairs: list[PeriodColumnPair] = field(default_factory=list)
    column_mapping: dict[CanonicalRole, str] = field(default_factory=dict)
    ignored_columns: list[str] = field(default_factory=list)
    visible_transformations: list[str] = field(default_factory=list)
    line_item_idx: int = 0
    budget_idx: int = 0
    actual_idx: int = 0
    acct_id_idx: int | None = None
    period_idx: int | None = None
    curr_idx: int | None = None
    type_idx: int | None = None
    passthrough: list[tuple[int, str]] = field(default_factory=list)
    hidden_rows: list[tuple[int, str, bool]] = field(default_factory=list)
    excluded_rows: set[int] = field(default_factory=set)
    output_rows: list[dict[str, object]] = field(default_factory=list)
    problems: list[IntakeProblem] = field(default_factory=list)
    unreadable_cells: list[IntakeProblem] = field(default_factory=list)  # amounts that must never be read as 0
    symbol_cells: list[tuple[str, str, str]] = field(default_factory=list)  # amounts whose text marks a currency (X5)
    section_rows: list[str] = field(default_factory=list)  # labels with nothing beside them: section headings (X16)
    blank_budget_items: list[str] = field(default_factory=list)
    # Numeric Currency amounts read from cells: (row, column, line item, field), for R2.
    currency_cells: list[tuple[int, int, str, str]] = field(default_factory=list)
    dash_count: int = 0
    minus_count: int = 0  # trailing / typographic minus signs read as negative
    layout_notes: list[str] = field(default_factory=list)
    hidden_read_columns: list[str] = field(default_factory=list)
    raw_title_text: str = ""
    detected_mult: Decimal = Decimal("1")
    display_cells: list[DisplayScaledCell] = field(default_factory=list)
    signed_det: SignedLedgerDetection = field(init=False)
    flipped_items: list[str] = field(default_factory=list)
    subtotals_det: SubtotalDetectionResult = field(init=False)
    reconciled_names: list[str] = field(default_factory=list)

    @property
    def header_row(self) -> list[object]:
        return self.raw_rows[self.header_idx]

    @property
    def header_row_number(self) -> int:
        return self.header_idx + 1


def _process_raw_table(
    raw_rows: list[list[object]],
    filename: str,
    sheet_name: str | None,
    treat_blank_budgets_as_zero: bool,
    selected_period: str | None = None,
    compare_to: ComparisonBasis | None = None,
    signs_resolved: bool = False,
    from_pdf: bool = False,
    excel: _ExcelSheet | None = None,
    layout_retry: bool = True,
) -> IntakeResult:
    """Map, parse and check one table of rows. ``signs_resolved`` marks rows from a shaped
    financial statement: their signs are settled and their subtotals already removed, so the
    signed-ledger flip and sum-based subtotal detection are skipped. ``excel`` carries what the
    workbook preflight saw on the sheet; raw row ``i`` is physical row ``i + 1``. ``layout_retry``
    allows one re-read of a workbook as period bands (E4) or side-by-side tables (E5)."""
    call = _TableCall(filename, sheet_name, treat_blank_budgets_as_zero, selected_period, compare_to, signs_resolved,
                      from_pdf, excel, layout_retry)
    found = _find_header(raw_rows, call)
    if isinstance(found, IntakeResult):
        return found
    raw_rows, header_idx, roles, ignored_col_indices, date_note = found
    stop = _named_block_retry(raw_rows, header_idx, call)
    if stop is not None:
        return stop
    detected = _detect_basis(raw_rows, header_idx, call)
    if isinstance(detected, IntakeResult):
        return detected
    detection, basis = detected
    table = _TableRead(call, raw_rows, header_idx, roles, ignored_col_indices, date_note, detection, basis)
    _map_columns(table)
    _row_columns(table)
    stop = _check_layout(table)
    if stop is not None:
        return stop
    _start_rows(table)
    stop = _read_data_rows(table)
    if stop is not None:
        return stop
    stop = _post_row_notes(table)
    if stop is not None:
        return stop
    stop = _unit_scale(table)
    if stop is not None:
        return stop
    _signs_and_totals(table)
    return _table_result(table)


def _find_header(
    raw_rows: list[list[object]], call: _TableCall,
) -> IntakeResult | tuple[list[list[object]], int, dict[CanonicalRole, int], list[int], str | None]:
    """The rows as read, their header row, its roles and ignored columns, and the note on dated headings; or the stop."""
    filename, sheet_name, selected_period, compare_to = call.filename, call.sheet_name, call.selected_period, call.compare_to
    excel = call.excel
    if not raw_rows:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=(f"The file '{filename}' contains no data. Upload a file with a header row (such "
                                 "as Line Item, Budget, Actual) and at least one line."),
            sheet_name=sheet_name,
        )
    half = _HALF.get()
    if half is not None and isinstance(half["missing"], CanonicalRole):
        raw_rows, filled = _fill_half(raw_rows, half["missing"])
        half["filled"] = bool(half["filled"]) or filled

    dated_rows, has_dates = _dated_header_rows(raw_rows)
    header_idx, roles, ignored_col_indices = detect_header_row(dated_rows, selected_period=selected_period)
    date_note = None
    if header_idx is None and (split := _two_row_header(dated_rows)) is not None:
        lower, split_header, date_note = split  # a header split over two rows, read together (X24)
        raw_rows = dated_rows = [*dated_rows[:lower], split_header, *dated_rows[lower + 1:]]
        header_idx, roles, ignored_col_indices = detect_header_row(dated_rows, selected_period=selected_period)
    if header_idx is not None and has_dates and dated_rows[header_idx] != raw_rows[header_idx]:
        # Only the header row takes the labels; a date in a data cell keeps its value.
        original = raw_rows[header_idx]
        dated = [f"{cell.isoformat()[:10]} as {_date_period(cell)} ({_column_name(idx)})"
                 for idx, cell in enumerate(original) if isinstance(cell, dt.date)]
        date_note = f"Read the dates in the header row as periods: {', '.join(dated)}."
        raw_rows = [*raw_rows[:header_idx], dated_rows[header_idx], *raw_rows[header_idx + 1:]]
    if header_idx is None:
        # A header cell that is a formula Excel never calculated reads as blank; say so instead.
        stop = _unsaved_formulas_stop(excel, filename, lambda r, c: r <= min(len(raw_rows), 25), describe_cell,
                                      sheet_name)
        if stop is not None:
            return stop
        opt_in = _opt_in_header(raw_rows) if compare_to not in OPT_IN_SYNONYMS else None
        hint = (f" This file has a '{opt_in[0]}' column: compare against it with --compare-to {opt_in[1].value}."
                if opt_in is not None else "")
        if compare_to is None:
            message = (
                f"Could not find a header row with Line Item, Budget, and Actual columns in '{filename}' "
                f"(a Forecast or Prior Year column can stand in for Budget). Add a header row that names those "
                f"columns, and upload the file again.{hint}"
            )
        else:
            message = (
                f"Could not find a header row with Line Item, {comparison_heading(compare_to, None)}, "
                f"and Actual columns in '{filename}'. Add a header row that names those columns, and upload the "
                "file again."
            )
        return IntakeResult(has_fatal_errors=True, fatal_error_message=message, sheet_name=sheet_name,
                            opt_in_hint=opt_in)
    return raw_rows, header_idx, roles, ignored_col_indices, date_note


def _reread(call: _TableCall, rows: list[list[object]], note: str, period: str | None) -> IntakeResult:
    """Read a workbook's rows again as laid out (E4, E5), once, and lead its notes with how they were read."""
    excel = call.excel
    result = _process_raw_table(rows, call.filename, call.sheet_name, call.treat_blank_budgets_as_zero, period,
                                call.compare_to, call.signs_resolved, call.from_pdf,
                                None if excel is None else replace(excel, block=None), layout_retry=False)
    if not result.has_fatal_errors:
        result.visible_transformations.insert(0, note)
        result.layout_notes.insert(0, note)
        result.layout_read = True
    return result


def _named_block_retry(raw_rows: list[list[object]], header_idx: int, call: _TableCall) -> IntakeResult | None:
    """The read of the one side-by-side table a sheet choice names (E5), or None when it names none."""
    excel, sheet_name = call.excel, call.sheet_name
    if excel is not None and excel.block is not None and call.layout_retry:
        blocks = _table_blocks(raw_rows, header_idx)
        chosen_block = next((b for b in blocks if _block_name(b) == excel.block), None)
        if chosen_block is None:
            tables_named = ", ".join(_block_name(b) for b in blocks)
            return IntakeResult(has_fatal_errors=True, sheet_name=sheet_name, fatal_error_message=(
                f"Sheet '{sheet_name}' has no separate table in {excel.block}. "
                + (f"Choose one of its tables: {tables_named}." if tables_named else "Choose the whole sheet instead.")))
        return _reread(call, _only_block(raw_rows, header_idx, chosen_block),
                       _block_note(raw_rows, header_idx, chosen_block, blocks, sheet_name), call.selected_period)
    return None


def _detect_basis(
    raw_rows: list[list[object]], header_idx: int, call: _TableCall,
) -> IntakeResult | tuple[ComparisonDetection, ComparisonBasis]:
    """The comparison the header row reads against and its basis; else one re-read as period bands (E4) or side-by-side
    tables (E5), or the stop that asks which comparison to use."""
    excel, sheet_name, selected_period, compare_to = call.excel, call.sheet_name, call.selected_period, call.compare_to
    header_row = raw_rows[header_idx]
    detection = detect_comparison_columns(header_row, compare_to=compare_to)
    if detection.basis is None and excel is not None and call.layout_retry:
        # Only a read that stops is tried again, so a sheet that reads today reads the same.
        banded = _period_bands(raw_rows, header_idx, excel.layout)
        if banded is not None:
            rows, labels = banded
            named = next((label for label in labels if selected_period and label.lower() == selected_period.lower()), None)
            newest = order_period_labels(labels)
            combined = [str(c) for c in rows[header_idx] if c is not None and str(c).strip()]
            band_note = ("Read the period headings above the header row with the columns below them: "
                         f"{', '.join(c for c in combined if any(c.startswith(label) for label in labels))}.")
            return _reread(call, rows, band_note, named or (newest[0] if newest else selected_period))
        blocks = _table_blocks(raw_rows, header_idx)
        readable = [b for b in blocks if _block_reads(raw_rows, header_idx, b, compare_to)]
        if readable:
            return _reread(call, _only_block(raw_rows, header_idx, readable[0]),
                           _block_note(raw_rows, header_idx, readable[0], blocks, sheet_name), selected_period)
    if detection.basis is None:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=detection.message,
            comparison_candidates=list(detection.candidates),
            comparison_choices=list(detection.choices),
            sheet_name=sheet_name,
        )
    return detection, detection.basis


def _map_columns(table: _TableRead) -> None:
    """Map the header's columns to roles, take a chosen period's pair, and start the notes on how they were read."""
    roles, header_row, detection, selected_period = table.roles, table.header_row, table.detection, table.call.selected_period
    table.comparison_field = comparison_heading(table.basis, detection.label)

    if detection.comparison_column is not None:
        roles[CanonicalRole.BUDGET] = detection.comparison_column
    if detection.actual_column is not None:
        roles[CanonicalRole.ACTUAL] = detection.actual_column

    table.header_str_row = header_str_row = [str(c).strip() for c in header_row if c is not None]
    table.period_pairs = period_pairs = detect_period_pairs(header_str_row)
    # A chosen period reads its own Budget/Actual pair, even beside "Budget YTD"/"Actual YTD" synonyms (X6).
    chosen_pair = next((p for p in period_pairs if selected_period and p.period.lower() == selected_period.lower()), None)
    if chosen_pair is not None and detection.basis is ComparisonBasis.BUDGET:
        names = [None if c is None else str(c).strip() for c in header_row]
        if chosen_pair.budget_column in names and chosen_pair.actual_column in names:
            roles[CanonicalRole.BUDGET] = names.index(chosen_pair.budget_column)
            roles[CanonicalRole.ACTUAL] = names.index(chosen_pair.actual_column)

    column_mapping = table.column_mapping
    for role, col_idx in roles.items():
        if col_idx < len(header_row):
            column_mapping[role] = str(header_row[col_idx]).strip()

    table.ignored_columns = ignored_columns = [
        str(header_row[idx]).strip()
        for idx in table.ignored_col_indices
        if idx < len(header_row) and str(header_row[idx]).strip()
    ]

    visible_transformations = table.visible_transformations
    if table.date_note is not None:
        visible_transformations.append(table.date_note)

    if detection.basis != ComparisonBasis.BUDGET and detection.message:
        visible_transformations.append(detection.message)

    if period_pairs:
        chosen_pair = chosen_period_pair(period_pairs, selected_period)
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


def _row_columns(table: _TableRead) -> None:
    """The columns each data row is read from: one per role, and the columns passed through without one."""
    roles, header_row, ignored_col_indices = table.roles, table.header_row, table.ignored_col_indices
    table.line_item_idx = roles[CanonicalRole.LINE_ITEM]
    table.budget_idx = roles[CanonicalRole.BUDGET]
    table.actual_idx = roles[CanonicalRole.ACTUAL]
    table.acct_id_idx = roles.get(CanonicalRole.ACCOUNT_ID)
    table.period_idx = roles.get(CanonicalRole.PERIOD)
    table.curr_idx = roles.get(CanonicalRole.CURRENCY)
    table.type_idx = roles.get(CanonicalRole.TYPE)

    # Columns without a canonical role (Row Kind, volume/price drivers, ...) pass through
    # unchanged so analysis still sees them; aliases of mapped roles are left out.
    mapped = set(roles.values()) | set(ignored_col_indices)
    table.passthrough = [
        (idx, str(header_row[idx]).strip())
        for idx in range(len(header_row))
        if idx not in mapped and header_row[idx] is not None and str(header_row[idx]).strip()
        and normalize_key(str(header_row[idx])) not in _ROLE_ALIAS_KEYS
    ]


def _check_layout(table: _TableRead) -> IntakeResult | None:
    """Stop on a formula Excel never calculated in a cell the read uses, or ask about rows hidden in Excel (R3)."""
    excel, filename, sheet_name = table.call.excel, table.call.filename, table.call.sheet_name
    raw_rows, roles, column_mapping, header_row_number = table.raw_rows, table.roles, table.column_mapping, table.header_row_number
    hidden_rows = (hidden_data_rows(excel.layout, raw_rows, header_row=header_row_number,
                                    line_item_column=roles[CanonicalRole.LINE_ITEM]) if excel is not None else [])
    excluded_rows = {number for number, _, _ in hidden_rows} if excel and excel.hidden_rows == "exclude" else set()
    table.hidden_rows, table.excluded_rows = hidden_rows, excluded_rows
    if excel is not None:
        # Every column this read uses, named the way the amount messages name them.
        read_columns: dict[int, str] = {idx: header for idx, header in table.passthrough}
        for role, idx in roles.items():
            read_columns[idx] = (table.comparison_field if role is CanonicalRole.BUDGET else "Actual"
                                 if role is CanonicalRole.ACTUAL else column_mapping.get(role, ""))
        line_item_column = roles[CanonicalRole.LINE_ITEM]

        def describe(row_number: int, column: int) -> str:
            row = raw_rows[row_number - 1]
            label = row[line_item_column] if line_item_column < len(row) else None
            return describe_cell(row_number, column, line_item="" if label is None else str(label).strip(),
                                 field=read_columns[column - 1])

        stop = _unsaved_formulas_stop(
            excel, filename,
            lambda r, c: header_row_number < r <= len(raw_rows) and c - 1 in read_columns and r not in excluded_rows,
            describe, sheet_name)
        if stop is not None:
            return stop
    if hidden_rows and (excel is None or excel.hidden_rows is None):
        return IntakeResult(has_fatal_errors=True, fatal_error_message=hidden_rows_question(hidden_rows),
                            sheet_name=sheet_name, header_row_number=header_row_number,
                            column_mapping=column_mapping, hidden_data_rows=hidden_rows,
                            needs_hidden_rows_choice=True)
    return None


def _start_rows(table: _TableRead) -> None:
    """Before the data rows: a currency a column heading names (X23), and the notes on what the read uses that Excel hides."""
    excel, filename, roles, column_mapping = table.call.excel, table.call.filename, table.roles, table.column_mapping
    hidden_rows, visible_transformations, layout_notes = table.hidden_rows, table.visible_transformations, table.layout_notes
    for role in (CanonicalRole.BUDGET, CanonicalRole.ACTUAL):  # a heading that names a currency marks its column (X23)
        heading = column_mapping.get(role, "")
        if (qualifier := _HEADER_QUALIFIER.search(heading)) and (mark := _HEADER_CURRENCY_CODE.search(qualifier.group())):
            heading_code = SYMBOL_CURRENCIES.get(mark.group(), mark.group().upper())
            table.symbol_cells.append((filename, f"the '{heading}' column heading", heading_code))

    if table.date_note is not None:
        layout_notes.append(table.date_note)
    if hidden_rows and excel is not None and excel.hidden_rows is not None:
        layout_notes.append(hidden_rows_note(excel.hidden_rows, hidden_rows))
        visible_transformations.append(layout_notes[-1])
    if excel is not None:
        for role, idx in sorted(roles.items(), key=lambda item: item[1]):
            if role in {CanonicalRole.LINE_ITEM, CanonicalRole.BUDGET, CanonicalRole.ACTUAL} \
                    and idx + 1 in excel.layout.hidden_columns:
                what = ("line items" if role is CanonicalRole.LINE_ITEM
                        else table.comparison_field if role is CanonicalRole.BUDGET else "Actual")
                table.hidden_read_columns.append(column_letters(idx + 1))
                layout_notes.append(
                    f"Read {what} from {_column_name(idx)} ('{column_mapping.get(role, '')}'), which is hidden in Excel.")
                visible_transformations.append(layout_notes[-1])


def _read_data_rows(table: _TableRead) -> IntakeResult | None:
    """Read each row below the header in turn, or the stop a row's Measure makes."""
    data_rows = table.raw_rows[table.header_idx + 1:]
    for physical_idx, row in enumerate(data_rows, start=table.header_row_number + 1):
        stop = _read_data_row(table, physical_idx, row)
        if stop is not None:
            return stop
    return None


def _read_data_row(table: _TableRead, physical_idx: int, row: list[object]) -> IntakeResult | None:
    """One data row: left out, read into ``table.output_rows``, or the stop for a Measure no reader knows."""
    if not row or all(c is None or str(c).strip() == "" for c in row):
        return None
    if physical_idx in table.excluded_rows:
        return None

    line_item_str = _row_line_item(table, physical_idx, row)
    if line_item_str is None:
        return None

    header_row = table.header_row
    measure_column = next((i for i, h in enumerate(header_row) if h is not None and normalize_key(str(h)) == "measure"), None)
    try:
        kind = measure_kind(row[measure_column] if measure_column is not None and measure_column < len(row) else None,
                            line_item_str)
    except ValueError as exc:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=str(exc))
    raw_budget, budget_dec, raw_actual, actual_dec = _row_amounts(table, physical_idx, row, line_item_str, kind)
    row_dict = _row_record(table, row, line_item_str, budget_dec, actual_dec)
    _apply_measure(table, physical_idx, row, row_dict, line_item_str, kind, measure_column, raw_budget, raw_actual)
    table.output_rows.append(row_dict)
    return None


def _row_line_item(table: _TableRead, physical_idx: int, row: list[object]) -> str | None:
    """The row's line item; None for a row left out, as a blank line item (a problem) or a section heading (X16)."""
    line_item_idx, acct_id_idx = table.line_item_idx, table.acct_id_idx
    line_item_val = row[line_item_idx] if line_item_idx < len(row) else None
    line_item_str = "" if line_item_val is None else str(line_item_val).strip()
    if not line_item_str:
        table.problems.append(
            IntakeProblem(
                row=physical_idx,
                column=table.column_mapping.get(CanonicalRole.LINE_ITEM, "Line Item"),
                line_item="(Blank)",
                message=f"Row {physical_idx}: Line item description is blank.",
            )
        )
        return None
    # A label with nothing in any other column is a section heading, not an amount to fill in (X16).
    if all(c is None or str(c).strip() == "" for j, c in enumerate(row) if j not in (line_item_idx, acct_id_idx)):
        table.section_rows.append(f"Row {physical_idx} ({line_item_str})")
        return None
    return line_item_str


def _row_amounts(
    table: _TableRead, physical_idx: int, row: list[object], line_item_str: str, kind: MeasureKind,
) -> tuple[object, Decimal | None, object, Decimal | None]:
    """The row's comparison and Actual cells and the amounts read from them; a cell that can't be read is a problem."""
    filename, comparison_field, column_mapping = table.call.filename, table.comparison_field, table.column_mapping
    budget_idx, actual_idx = table.budget_idx, table.actual_idx
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
            table.blank_budget_items.append(f"Row {physical_idx}: {line_item_str}")
            if table.call.treat_blank_budgets_as_zero:
                budget_dec = Decimal("0")
        elif b_note and "dash" in b_note:
            table.dash_count += 1
        elif b_note and "minus" in b_note:
            table.minus_count += 1
    except ValueError as exc:
        problem = _cell_problem(
            physical_idx, line_item_str,
            column_mapping.get(CanonicalRole.BUDGET, comparison_field), comparison_field, exc,
        )
        table.problems.append(problem)
        table.unreadable_cells.append(problem)

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
            table.dash_count += 1
        elif a_note and "minus" in a_note:
            table.minus_count += 1
    except ValueError as exc:
        problem = _cell_problem(
            physical_idx, line_item_str,
            column_mapping.get(CanonicalRole.ACTUAL, "Actual"), "Actual", exc,
        )
        table.problems.append(problem)
        table.unreadable_cells.append(problem)

    for raw, field_label in ((raw_budget, comparison_field), (raw_actual, "Actual")):
        if isinstance(raw, str) and (code := next((c for s, c in SYMBOL_CURRENCIES.items() if s in raw), None)):
            table.symbol_cells.append(
                (filename, f"Row {physical_idx}, {line_item_str}, {field_label} column: {raw.strip()}", code))
    return raw_budget, budget_dec, raw_actual, actual_dec


def _row_record(
    table: _TableRead, row: list[object], line_item_str: str, budget_dec: Decimal | None, actual_dec: Decimal | None,
) -> dict[str, object]:
    """The row as the analysis reads it: line item, amounts, the optional role columns and the passthrough columns."""
    acct_id_idx, period_idx, curr_idx, type_idx = table.acct_id_idx, table.period_idx, table.curr_idx, table.type_idx
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

    for idx, header in table.passthrough:
        value = row[idx] if idx < len(row) else None
        if value is not None and str(value).strip():
            row_dict[header] = value
    return row_dict


def _apply_measure(
    table: _TableRead, physical_idx: int, row: list[object], row_dict: dict[str, object], line_item_str: str,
    kind: MeasureKind, measure_column: int | None, raw_budget: object, raw_actual: object,
) -> None:
    """What the row's Measure does to its amounts: the currency cells R2 checks, a percent Excel shows (X31), a percent
    or multiple kept as written, and the notes that say so."""
    excel, header_row, visible_transformations = table.call.excel, table.header_row, table.visible_transformations
    budget_idx, actual_idx, comparison_field = table.budget_idx, table.actual_idx, table.comparison_field
    if kind is MeasureKind.CURRENCY:
        for column_idx, raw_value, field_name in ((budget_idx, raw_budget, comparison_field),
                                                  (actual_idx, raw_actual, "Actual")):
            # A zero shows the same in any unit, so it can't disagree with a caption (X20).
            if isinstance(raw_value, Decimal) and raw_value != 0:
                table.currency_cells.append((physical_idx, column_idx + 1, line_item_str, field_name))
    if kind is MeasureKind.PERCENT and excel is not None:
        # A cell Excel shows as a percentage is that percentage, not a bare rate for the flag to scale (X31).
        shown = [(column_idx, field_name, entry[0]) for column_idx, raw_value, field_name in
                 ((budget_idx, raw_budget, comparison_field), (actual_idx, raw_actual, "Actual"))
                 if isinstance(raw_value, Decimal)
                 and (entry := excel.display.get(cell_key(physical_idx, column_idx + 1))) is not None and entry[2]]
        for column_idx, _, _ in shown:
            if column_idx == budget_idx:
                raw_budget = percent_shown(cast(Decimal, raw_budget))
            else:
                raw_actual = percent_shown(cast(Decimal, raw_actual))
        if shown:
            visible_transformations.append(
                percent_shown_note(line_item_str, [field_name for _, field_name, _ in shown], shown[0][2]))
    if kind is MeasureKind.PERCENT or kind is MeasureKind.MULTIPLE:
        # Preserve the explicit percent sign / bare scale until a flag or chat confirmation settles it;
        # a multiple keeps its x, which the analysis reads as turns.
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


def _post_row_notes(table: _TableRead) -> IntakeResult | None:
    """After the rows: the notes on section headings, dashes, minus signs and blank comparisons, or the stop for amounts
    that can't be read."""
    visible_transformations, dash_count, minus_count = table.visible_transformations, table.dash_count, table.minus_count
    section_rows, unreadable_cells, blank_budget_items = table.section_rows, table.unreadable_cells, table.blank_budget_items
    if section_rows:
        visible_transformations.append(
            f"Left out {len(section_rows)} section heading row{'s' if len(section_rows) != 1 else ''} with no "
            f"amounts in any column: {', '.join(section_rows)}.")
    if unreadable_cells:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=_unreadable_cells_message(table.call.filename, unreadable_cells, from_pdf=table.call.from_pdf),
            problems=table.problems,
            sheet_name=table.call.sheet_name,
            header_row_number=table.header_row_number,
            column_mapping=table.column_mapping,
            comparison_basis=table.basis,
            comparison_label=table.detection.label,
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

    if table.call.treat_blank_budgets_as_zero and blank_budget_items:
        count = len(blank_budget_items)
        plural = "s" if count != 1 else ""
        if table.detection.basis is ComparisonBasis.BUDGET:
            visible_transformations.append(f"Treated blank budgets as 0 on {count} unbudgeted line{plural}")
        else:
            visible_transformations.append(
                f"Treated blank {basis_noun(table.basis)} values as 0 on {count} "
                f"line{plural} {zero_comparison_phrase(table.basis)}"
            )
    return None


def _unit_scale(table: _TableRead) -> IntakeResult | None:
    """Scale the amounts by a unit the title or header names, unless their number formats already show them scaled (R2)."""
    filename, excel, currency_cells = table.call.filename, table.call.excel, table.currency_cells
    # 1. Unit scaling check (from title block rows and header row)
    table.raw_title_text = raw_title_text = " ".join(
        str(c).strip() for r in table.raw_rows[:table.header_idx] for c in r if c is not None and str(c).strip()
    )
    sides = _heading_units(table, raw_title_text)
    if sides is None:
        detected_mult = detect_unit_scale(raw_title_text + " " + " ".join(table.header_str_row))
    elif sides[0][1] != sides[1][1]:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=_heading_units_differ(sides),
                            sheet_name=table.call.sheet_name, header_row_number=table.header_row_number,
                            column_mapping=table.column_mapping)
    else:
        detected_mult = cast(Decimal, sides[0][1])
    table.display_cells = display_cells = _display_scaled_cells(excel, currency_cells)
    display_note, display_stop = _reconcile_display(filename, detected_mult, display_cells, len(currency_cells))
    if display_stop is not None:
        return IntakeResult(has_fatal_errors=True, fatal_error_message=display_stop, sheet_name=table.call.sheet_name,
                            header_row_number=table.header_row_number, column_mapping=table.column_mapping)
    if display_note is not None:
        if detected_mult != Decimal("1"):
            detected_mult = Decimal("1")  # the cells already hold full amounts
        table.visible_transformations.append(display_note)
        table.layout_notes.append(display_note)
    if detected_mult != Decimal("1"):
        declarations = unit_declarations(table.output_rows)
        table.output_rows = scale_rows_by_unit(table.output_rows, detected_mult)
        unit_label = f"{_UNIT_WORDS[detected_mult]} (x{detected_mult:,})"
        table.visible_transformations.append(scaling_note(unit_label, declarations))
    table.detected_mult = detected_mult
    return None


_HeadingUnit = tuple[str, Decimal | None, str]  # a heading, its unit, and where a unit not its own comes from


def _heading_units(table: _TableRead, title: str) -> tuple[_HeadingUnit, _HeadingUnit] | None:
    """Budget's (or the comparison's) and Actual's units when either heading names its own (X45): each its own, else
    the caption the title and the other headings give, else none. None when neither names one, to scale as before."""
    half = _HALF.get()
    placeholder = half["missing"] if half is not None and half["filled"] else None
    headings = [(role, table.column_mapping.get(role)) for role in (CanonicalRole.BUDGET, CanonicalRole.ACTUAL)]
    own = {role: heading_unit(heading) for role, heading in headings if heading is not None and role is not placeholder}
    if len(own) < 2:  # a half file's placeholder column takes its partner's unit
        unit = next(iter(own.values()), None)
        return None if unit is None else (("", unit, ""), ("", unit, ""))
    if all(unit is None for unit in own.values()):
        return None
    others = " ".join(h for h in table.header_str_row if h not in {heading for _, heading in headings})
    caption, source = detect_unit_scale(title), "the title says"
    if caption == 1:
        caption, source = detect_unit_scale(others), "another heading says"
    found = caption if caption != 1 else None

    def side(role: CanonicalRole, heading: str | None) -> _HeadingUnit:
        unit = own[role]
        if unit is not None:
            return cast(str, heading), unit, ""
        return cast(str, heading), found, source if found is not None else ""
    return side(*headings[0]), side(*headings[1])


def _heading_units_differ(sides: tuple[_HeadingUnit, _HeadingUnit]) -> str:
    """The refusal for amount headings in different units, or a unit beside none, naming both (X45)."""
    def said(heading: str, unit: Decimal | None, source: str) -> str:
        if unit is None:
            return f"'{heading}' names no unit"
        return f"'{heading}' is in {_UNIT_WORDS[unit]}" + (f", as {source}" if source else "")
    first, second = sides
    if first[1] is not None and second[1] is not None:
        return (f"{said(*first)}{', and ' if first[2] else ' and '}{said(*second)}. Change one column so both use "
                "the same unit, then upload the file again.")
    named, unnamed = (first, second) if first[1] is not None else (second, first)
    qualifier = _HEADER_QUALIFIER.search(named[0])
    assert qualifier is not None  # a unit beside none is always the heading's own
    return (f"{said(*first)}, but {said(*second)}, so I can't tell what '{unnamed[0]}' is in. Give both headings the "
            f"same unit, such as {qualifier.group().strip()}, then upload the file again.")


def _signs_and_totals(table: _TableRead) -> None:
    """Flip a signed ledger's revenue and profit lines, and leave out subtotal rows that reconcile."""
    signs_resolved, output_rows, visible_transformations = table.call.signs_resolved, table.output_rows, table.visible_transformations
    # 2. Signed ledger check
    signed_det = (SignedLedgerDetection(False, 0, [])
                  if signs_resolved else detect_signed_ledger([r for r in output_rows if _row_measure(r) is MeasureKind.CURRENCY]))
    flipped_items: list[str] = []
    if signed_det.is_signed_ledger:
        output_rows, flipped_items = flip_ledger_signs(output_rows, signed_det.negative_revenue_items)
        output_rows, profit_items = flip_ledger_signs(output_rows, _signed_profit_lines(output_rows))
        revenue_lines = f"{len(flipped_items)} revenue line{'s' if len(flipped_items) != 1 else ''}"
        profit_lines = (f" and {len(profit_items)} profit line{'s' if len(profit_items) != 1 else ''} "
                        f"({', '.join(profit_items)})" if profit_items else "")
        visible_transformations.append(
            "Revenue looks like it's stored as negative (credits). Flipped signs to positive-cost "
            f"convention for {revenue_lines}{profit_lines}."
        )
        flipped_items = [*flipped_items, *profit_items]

    # 3. Subtotals and totals detection. An explicit Row Kind column already marks totals,
    # and the analysis reconciles and excludes those rows itself, so they are kept.
    has_row_kind = any(normalize_key(header) == "row_kind" for _, header in table.passthrough)
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
    table.output_rows, table.signed_det, table.flipped_items = output_rows, signed_det, flipped_items
    table.subtotals_det, table.reconciled_names = subtotals_det, reconciled_names


def _table_result(table: _TableRead) -> IntakeResult:
    """The read table, with everything the read found and did."""
    excel, output_rows, hidden_rows = table.call.excel, table.output_rows, table.hidden_rows
    skipped_count = table.header_idx
    skip_reasons = []
    if skipped_count > 0:
        skip_reasons.append(f"{skipped_count} title block row{'s' if skipped_count != 1 else ''} above header")

    single_periods = detect_single_period_column_values(output_rows)

    return IntakeResult(
        rows=output_rows,
        sheet_name=table.call.sheet_name,
        header_row_number=table.header_row_number,
        column_mapping=table.column_mapping,
        ignored_columns=table.ignored_columns,
        rows_read=len(output_rows),
        rows_skipped_count=skipped_count,
        skip_reasons=skip_reasons,
        visible_transformations=table.visible_transformations,
        problems=table.problems,
        blank_budget_items=table.blank_budget_items,
        blank_budgets_as_zero=table.call.treat_blank_budgets_as_zero,
        dash_count=table.dash_count,
        detected_totals=table.reconciled_names,
        unreconciled_totals=table.subtotals_det.unreconciled_totals,
        detected_unit_multiplier=table.detected_mult,
        symbol_cells=table.symbol_cells,
        detected_signed_ledger=table.signed_det.is_signed_ledger,
        negative_revenue_items=table.flipped_items,
        detected_period_pairs=table.period_pairs,
        detected_single_periods=single_periods,
        raw_headers=table.header_str_row,
        raw_title_text=table.raw_title_text,
        comparison_basis=table.basis,
        comparison_label=table.detection.label,
        comparison_candidates=list(table.detection.candidates),
        display_scaled_cells=table.display_cells,
        currency_amount_cells=len(table.currency_cells),
        hidden_data_rows=hidden_rows,
        hidden_rows_choice=excel.hidden_rows if hidden_rows and excel is not None else None,
        hidden_read_columns=table.hidden_read_columns,
        layout_notes=table.layout_notes,
        layout_read=table.date_note is not None,
    )


def _display_scaled_cells(
    excel: _ExcelSheet | None, cells: list[tuple[int, int, str, str]],
) -> list[DisplayScaledCell]:
    if excel is None or not excel.display:
        return []
    found = []
    for row, column, line_item, field_name in cells:
        entry = excel.display.get(cell_key(row, column))
        if entry is not None:
            code, divisor, percent = entry
            found.append(DisplayScaledCell(describe_cell(row, column, line_item=line_item, field=field_name),
                                           f"{column_letters(column)}{row}",
                                           code, divisor, percent))
    return found


def _reconcile_display(
    filename: str, caption: Decimal, cells: list[DisplayScaledCell], amount_count: int, *, mapping: bool = False,
) -> tuple[str | None, str | None]:
    """R2: (note, stop) for amounts whose number format shows them scaled under a caption `caption`.

    A mapping's declared unit is reconciled the same way (``mapping``), since it stands in for
    a caption the file does not have.
    """
    if not cells:
        return None, None
    first = cells[0]
    says = "The mapping says" if mapping else "The title says"
    if caption == Decimal("1"):
        return (f"Excel shows some amounts scaled by their number format (cell {first.address}: its format "
                f"{_quoted_format(first.code)} shows it {_shown_as(first.divisor, first.percent)}); the full "
                "stored amounts were read."), None
    if len(cells) == amount_count and all(c.divisor == caption and not c.percent for c in cells):
        unit = _UNIT_WORDS.get(caption, f"units of {caption:,}")
        return (f"{says} amounts are in {unit}, and the cells already hold full amounts that Excel "
                f"displays in {unit} (number format {_quoted_format(first.code)}), so they were read as "
                "stored, not scaled again."), None
    unit = _UNIT_WORDS.get(caption, f"units of {caption:,}")
    source = f"The mapping for '{filename}'" if mapping else f"The title of '{filename}'"
    lines = [f"{source} says amounts are in {unit}, but the amounts' number formats don't "
             "agree with it, so I can't tell which unit each amount is in:"]
    lines.extend(f"- {c.description}: its format {_quoted_format(c.code)} shows it {_shown_as(c.divisor, c.percent)}"
                 for c in cells[:_MAX_LISTED_CELLS])
    if len(cells) > _MAX_LISTED_CELLS:
        lines.append(f"- ...and {len(cells) - _MAX_LISTED_CELLS} more.")
    if any(c.percent for c in cells):
        lines.append("If a row is a rate, mark it Percent in a Measure column, or leave the row out.")
    change = "unit_scale in the mapping" if mapping else "the title"
    lines.append(f"Give every amount the same number format, or change {change}, and upload the file again.")
    return None, "\n".join(lines)


def currency_conflict(result: IntakeResult, currency: str, filename: str) -> tuple[str, str] | None:
    """Why amounts marked in another currency cannot report in `currency` (X5, X30), and the currency they are in.

    No currency is ever converted. Returns (problem, marked currency or "") for the caller to add its own fix,
    or None when they agree.
    """
    if result.document_currency and result.document_currency != currency:
        found = result.document_currency
        if found not in CURRENCY_SYMBOLS:
            return (f"'{filename}' reports its amounts in {found}. This tool reports in USD, EUR or GBP only and "
                    "converts no currency.", "")
        return (f"'{filename}' reports its amounts in {found}, but the reporting currency is {currency}, and no "
                "currency is converted.", found)
    marked = [(cell, code) for _, cell, code in result.symbol_cells if code != currency]
    if not marked:
        return None
    codes = sorted({code for _, code in marked})
    files = " and ".join(f"'{name}'" for name in dict.fromkeys(f for f, _, c in result.symbol_cells if c != currency))
    lines = [f"Some amounts in {files} are marked in {' and '.join(codes)}, but the reporting currency is "
             f"{currency}, and no currency is converted:"]
    lines.extend(f"- {cell}" for cell, _ in marked[:_MAX_LISTED_CELLS])
    if len(marked) > _MAX_LISTED_CELLS:
        lines.append(f"- ...and {len(marked) - _MAX_LISTED_CELLS} more.")
    return "\n".join(lines), codes[0] if len(codes) == 1 else ""


def reconcile_declared_unit(
    intake_res: IntakeResult, rows: list[dict[str, object]], unit: Decimal, filename: str,
) -> list[dict[str, object]]:
    """Apply a mapping's unit to a file with no unit caption, reconciled with the amounts' formats (R2).

    Raises ValueError, naming the cells, when the formats disagree with the declared unit.
    """
    note, stop = _reconcile_display(filename, unit, intake_res.display_scaled_cells,
                                    intake_res.currency_amount_cells, mapping=True)
    if stop is not None:
        raise ValueError(stop)
    if note is not None:
        intake_res.visible_transformations.append(note)
        return rows
    intake_res.detected_unit_multiplier = unit
    return scale_rows_by_unit(rows, unit)


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
        # Present only with a finding; audit 1.9 records it, older versions refuse it.
        **({"workbook": intake_res.workbook_examination.record()}
           if intake_res.workbook_examination is not None and intake_res.workbook_examination.findings else {}),
    }


def format_intake_summary(result: IntakeResult) -> str:
    """Generate the 'Here's how I read your file' summary for Maya in plain English."""
    lines: list[str] = ["Here's how I read your file:\n"]

    if result.sheet_name:
        source = "Statement" if result.source_kind in {"pdf", "ixbrl"} else "Worksheet"
        lines.append(f"- **{source}:** {result.sheet_name}")

    for t in result.visible_transformations:
        if t.startswith("Analyzed period:"):
            period_name = t.split(":")[1].split("(")[0].strip()
            lines.append(f"- **Analyzed period:** {period_name}")
            break

    if result.source_kind not in {"pdf", "ixbrl"}:  # a filing has no header row to name; its statement is named
        lines.append(f"- **Header row:** Row {result.header_row_number}")

    col_details = []
    if CanonicalRole.LINE_ITEM in result.column_mapping:
        col_details.append(f"Line item from '{result.column_mapping[CanonicalRole.LINE_ITEM]}'")
    if CanonicalRole.ACCOUNT_ID in result.column_mapping:
        col_details.append(f"Account ID from '{result.column_mapping[CanonicalRole.ACCOUNT_ID]}'")
    if CanonicalRole.BUDGET in result.column_mapping:
        heading = comparison_heading(result.comparison_basis, result.period_names.get(result.comparison_label or "",
                                                                                      result.comparison_label))
        col_details.append(f"{heading} from '{result.column_mapping[CanonicalRole.BUDGET]}'")
    if CanonicalRole.ACTUAL in result.column_mapping:
        col_details.append(f"{_actual_heading(result)} from '{result.column_mapping[CanonicalRole.ACTUAL]}'")
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

    exam = result.workbook_examination
    if exam is not None and exam.findings:
        lines.append("\n**What I noticed in the workbook:**")
        lines.extend(f"- {line}" for line in exam.lines())

    if result.problems:
        lines.append("\n⚠️ **Items needing attention:**")
        for prob in result.problems[:5]:
            lines.append(f"- {prob.message}")
        if len(result.problems) > 5:
            lines.append(f"- ...and {len(result.problems) - 5} more items.")

    return "\n".join(lines)


@dataclass(frozen=True)
class IntakeSummaryRows:
    """The facts of `format_intake_summary` as rows, for a page that sets them out as a panel.

    `rows` are (label, value) pairs in reading order; `adjustments` and `attention` are sentences.
    Values are the file's own labels, unescaped: a page must set them as text, never as markup.
    """

    rows: list[tuple[str, str]]
    adjustments: list[str]
    attention: list[str]
    more_attention: int


def intake_summary_rows(result: IntakeResult) -> IntakeSummaryRows:
    """The same reading of the file as `format_intake_summary`, one fact per row."""
    rows: list[tuple[str, str]] = []
    if result.sheet_name:
        rows.append(("Statement" if result.source_kind in {"pdf", "ixbrl"} else "Worksheet", result.sheet_name))
    for t in result.visible_transformations:
        if t.startswith("Analyzed period:"):
            rows.append(("Analyzed period", t.split(":")[1].split("(")[0].strip()))
            break
    if result.source_kind not in {"pdf", "ixbrl"}:
        rows.append(("Header row", f"Row {result.header_row_number}"))
    if CanonicalRole.LINE_ITEM in result.column_mapping:
        rows.append(("Line items", f"from '{result.column_mapping[CanonicalRole.LINE_ITEM]}'"))
    if CanonicalRole.ACCOUNT_ID in result.column_mapping:
        rows.append(("Account ID", f"from '{result.column_mapping[CanonicalRole.ACCOUNT_ID]}'"))
    if CanonicalRole.BUDGET in result.column_mapping:
        heading = comparison_heading(result.comparison_basis, result.period_names.get(result.comparison_label or "",
                                                                                      result.comparison_label))
        rows.append((heading, f"from '{result.column_mapping[CanonicalRole.BUDGET]}'"))
    if CanonicalRole.ACTUAL in result.column_mapping:
        rows.append((_actual_heading(result), f"from '{result.column_mapping[CanonicalRole.ACTUAL]}'"))
    read = f"{result.rows_read} data row{'s' if result.rows_read != 1 else ''}"
    if result.rows_skipped_count > 0:
        skipped = result.rows_skipped_count
        read += f" ({skipped} row{'s' if skipped != 1 else ''} skipped: {', '.join(result.skip_reasons)})"
    rows.append(("Rows read", read))
    if result.detected_totals:
        rows.append(("Subtotals left out", f"{', '.join(result.detected_totals)} (so they are not counted twice)"))
    adjustments = [t for t in result.visible_transformations if not t.startswith("Analyzed period:")]
    attention = [prob.message for prob in result.problems[:5]]
    return IntakeSummaryRows(rows, adjustments, attention, max(0, len(result.problems) - 5))


_INTERNAL_FIELD_NAMES = frozenset(_ROLE_ALIAS_KEYS | {
    "row_kind", "account_id", "budget_amount", "actual_amount", "line_type", "revenue_expense_type",
})


def _actual_heading(result: IntakeResult) -> str:
    """"Actual", with the filing's duration where it names one: "Actual (3 months ended Mar 2026)" (M4)."""
    name = result.period_names.get(str(result.column_mapping.get(CanonicalRole.ACTUAL, "")))
    return f"Actual ({name})" if name else "Actual"


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
        r"Summary\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))\s+does not reconcile to\s+(\w+)\s+detail rows", text,
        re.IGNORECASE,
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
    """A rate's % sign, or a multiple's x (3.25x, PLAN.md R16), comes off before the number is read."""
    if isinstance(value, str) and ((kind is MeasureKind.PERCENT and value.strip().endswith("%"))
                                   or (kind is MeasureKind.MULTIPLE and value.strip().casefold().endswith("x"))):
        return value.strip()[:-1]
    return value
