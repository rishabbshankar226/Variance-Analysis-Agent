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
from .numeric import financial_context
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


_LINE_ITEM_SYNONYMS = {
    "line_item", "line", "item", "account", "account_name", "category",
    "account_description", "description", "gl_account_name", "account_title",
    "line_item_name", "gl_description",
}

_ACCOUNT_ID_SYNONYMS = {
    "gl_account", "gl_account_number", "gl_acct", "account_number",
    "acct_num", "acct", "account_id", "acct_id", "gl",
}

_BUDGET_SYNONYMS = {
    "budget", "budget_amount", "plan", "planned",
    "budget_ytd", "ytd_budget", "plan_ytd", "bgt", "budget_amt",
}

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
    candidate_sheets: list[SheetScore] = field(default_factory=list)
    available_sheets: list[str] = field(default_factory=list)
    has_fatal_errors: bool = False
    fatal_error_message: str | None = None

    @property
    def has_transformations(self) -> bool:
        """Return True if any heuristic adjustment or transformation was made that warrants confirmation."""
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
    if not norm:
        return CanonicalRole.UNKNOWN, None

    if norm == "forecast":
        return CanonicalRole.BUDGET, "Forecast is being used as the plan"

    if norm in _LINE_ITEM_SYNONYMS:
        return CanonicalRole.LINE_ITEM, None
    if norm in _ACCOUNT_ID_SYNONYMS:
        return CanonicalRole.ACCOUNT_ID, None
    if norm in _BUDGET_SYNONYMS:
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


def detect_header_row(
    raw_rows: list[list[object]], max_scan: int = 25
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


def read_input_assisted(
    data: bytes,
    suffix: str,
    *,
    filename: str = "input",
    sheet: str | None = None,
    treat_blank_budgets_as_zero: bool = False,
) -> IntakeResult:
    """Read any supported file format with assisted header, sheet, dash, and problem handling."""
    if len(data) > MAX_INPUT_BYTES:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=f"The file '{filename}' exceeds the supported file size limit of 32 MiB.",
        )

    norm_suffix = suffix.lower()
    if norm_suffix in {".tsv", ".txt"}:
        return _read_tsv_text(data.decode("utf-8-sig", errors="replace"), filename, treat_blank_budgets_as_zero)
    if norm_suffix == ".csv":
        return _read_csv_text(data.decode("utf-8-sig", errors="replace"), filename, treat_blank_budgets_as_zero)
    if norm_suffix in {".xlsx", ".xlsm"}:
        return _read_excel_bytes(data, filename, sheet, treat_blank_budgets_as_zero)
    if norm_suffix == ".json":
        return _read_json_bytes(data, filename)

    return IntakeResult(
        has_fatal_errors=True,
        fatal_error_message=f"Unsupported input format '{suffix}'. Please use an Excel workbook (.xlsx, .xlsm), CSV, or TSV file.",
    )


def _read_tsv_text(text: str, filename: str, treat_blank_budgets_as_zero: bool) -> IntakeResult:
    lines = [line for line in text.splitlines() if line.strip()]
    reader = csv.reader(lines, delimiter="\t")
    raw_rows: list[list[object]] = [cast(list[object], row) for row in reader]
    res = _process_raw_table(raw_rows, filename, sheet_name=None, treat_blank_budgets_as_zero=treat_blank_budgets_as_zero)
    if "pasted" in filename.lower() or filename == "pasted_data.tsv":
        res.visible_transformations.insert(0, "Read data from pasted tab-separated text")
    return res


def _read_csv_text(text: str, filename: str, treat_blank_budgets_as_zero: bool) -> IntakeResult:
    lines = [line for line in text.splitlines() if line.strip()]
    reader = csv.reader(lines)
    raw_rows: list[list[object]] = [cast(list[object], row) for row in reader]
    return _process_raw_table(raw_rows, filename, sheet_name=None, treat_blank_budgets_as_zero=treat_blank_budgets_as_zero)


def _read_json_bytes(data: bytes, filename: str) -> IntakeResult:
    # Delegate to parsing.load_json_text and wrap into IntakeResult
    from .parsing import load_json_text
    try:
        rows = load_json_text(data.decode("utf-8"))
        # JSON rows are already named; keep every field (Type, Row Kind, drivers) for analysis.
        canonical_rows: list[dict[str, object]] = [dict(r) for r in rows]
        return IntakeResult(
            rows=canonical_rows,
            header_row_number=1,
            rows_read=len(canonical_rows),
            column_mapping={
                CanonicalRole.LINE_ITEM: "line_item",
                CanonicalRole.BUDGET: "budget",
                CanonicalRole.ACTUAL: "actual",
            },
        )
    except Exception as exc:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=f"Could not read JSON data from '{filename}': {exc}",
        )


def _read_excel_bytes(
    data: bytes, filename: str, sheet: str | None, treat_blank_budgets_as_zero: bool
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
) -> IntakeResult:
    if not raw_rows:
        return IntakeResult(
            has_fatal_errors=True,
            fatal_error_message=f"The file '{filename}' contains no data.",
            sheet_name=sheet_name,
        )

    header_idx, roles, ignored_col_indices = detect_header_row(raw_rows)
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

        for idx, header in passthrough:
            value = row[idx] if idx < len(row) else None
            if value is not None and str(value).strip():
                row_dict[header] = value

        output_rows.append(row_dict)

    if dash_count > 0:
        visible_transformations.append(
            f"Read accounting dashes ('-') as 0 across {dash_count} amount{'s' if dash_count != 1 else ''}"
        )

    if treat_blank_budgets_as_zero and blank_budget_items:
        visible_transformations.append(
            f"Treated blank budgets as 0 on {len(blank_budget_items)} unbudgeted line{'s' if len(blank_budget_items) != 1 else ''}"
        )

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
    )


def format_intake_summary(result: IntakeResult) -> str:
    """Generate the 'Here's how I read your file' summary for Maya in plain English."""
    lines: list[str] = ["Here's how I read your file:\n"]

    if result.sheet_name:
        lines.append(f"- **Worksheet:** {result.sheet_name}")

    lines.append(f"- **Header row:** Row {result.header_row_number}")

    col_details = []
    if CanonicalRole.LINE_ITEM in result.column_mapping:
        col_details.append(f"Line item from '{result.column_mapping[CanonicalRole.LINE_ITEM]}'")
    if CanonicalRole.ACCOUNT_ID in result.column_mapping:
        col_details.append(f"Account ID from '{result.column_mapping[CanonicalRole.ACCOUNT_ID]}'")
    if CanonicalRole.BUDGET in result.column_mapping:
        col_details.append(f"Budget from '{result.column_mapping[CanonicalRole.BUDGET]}'")
    if CanonicalRole.ACTUAL in result.column_mapping:
        col_details.append(f"Actual from '{result.column_mapping[CanonicalRole.ACTUAL]}'")
    lines.append(f"- **Columns mapped:** {', '.join(col_details)}")

    read_text = f"- **Rows read:** {result.rows_read} data row{'s' if result.rows_read != 1 else ''}"
    if result.rows_skipped_count > 0:
        read_text += f" ({result.rows_skipped_count} row{'s' if result.rows_skipped_count != 1 else ''} skipped: {', '.join(result.skip_reasons)})"
    lines.append(read_text)

    if result.visible_transformations:
        lines.append("\n**Visible adjustments:**")
        for transform in result.visible_transformations:
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
