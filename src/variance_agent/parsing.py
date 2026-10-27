from __future__ import annotations

import csv
from collections.abc import Iterator
import io
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, cast
from zipfile import BadZipFile

from .currencies import SYMBOL_CURRENCIES
from .excel import (WorkbookLoader, cell_value, inspect_workbook, legacy_workbook_message, table_formulas_message,
                    workbook_kind)
from .limits import (
    MAX_CELLS, MAX_COLUMNS, MAX_INPUT_BYTES, MAX_JSON_DEPTH, MAX_NUMBER_LENGTH,
    MAX_ROWS, validate_text,
)
from .numeric import financial_context


_NUMBER_RE = re.compile(
    r"(?P<prefix>[+-]?[$€£]?|[$€£][+-]?)\s*"
    r"(?P<number>(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:_[0-9]+)*)(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]+)?)"
)

_MISSING = {"", "na", "n/a", "none", "null", "-", "—"}


@dataclass(frozen=True)
class ParsedInput:
    rows: list[dict[str, object]]
    worksheet: str | None = None
    sheetnames: tuple[str, ...] = ()
    raw_headers: tuple[str, ...] = ()


def is_missing(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in _MISSING)


def _require_finite(number: Decimal, *, field: str, line_item: str) -> Decimal:
    if not number.is_finite():
        raise ValueError(f"{line_item}: field '{field}' must be a finite number.")
    if len(number.as_tuple().digits) > MAX_NUMBER_LENGTH:
        raise ValueError(f"{line_item}: field '{field}' exceeds the supported numeric length.")
    # Zero has no financial scale requirement. Extreme zero exponents bypass
    # arithmetic traps but expand to arbitrarily large fixed-point strings.
    exponent = number.as_tuple().exponent
    if number.is_zero() and isinstance(exponent, int) and abs(exponent) > 999:
        return Decimal("-0") if number.is_signed() else Decimal("0")
    with financial_context():
        _ = +number  # raises if the value cannot be held under the financial policy
    return number


def parse_decimal(
    value: object, *, field: str, line_item: str, currency: str | None = None
) -> Decimal:
    if value is None:
        raise ValueError(f"{line_item}: required field '{field}' is missing.")
    if isinstance(value, bool):
        raise ValueError(f"{line_item}: field '{field}' must be numeric, not boolean.")
    if isinstance(value, Decimal):
        return _require_finite(value, field=field, line_item=line_item)
    if isinstance(value, (int, float)):
        return _require_finite(Decimal(str(value)), field=field, line_item=line_item)
    if not isinstance(value, str):
        raise ValueError(f"{line_item}: field '{field}' must be a numeric scalar.")
    if len(value) > MAX_NUMBER_LENGTH:
        raise ValueError(f"{line_item}: field '{field}' exceeds the supported numeric length.")
    text = value.strip()
    if text.lower() in _MISSING:
        raise ValueError(f"{line_item}: required field '{field}' is missing.")

    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1]

    if text.strip().lower().lstrip("+-") in {"nan", "snan", "inf", "infinity"}:
        raise ValueError(f"{line_item}: field '{field}' must be a finite number.")
    match = _NUMBER_RE.fullmatch(text.strip())
    if match is None or (negative_parentheses and any(sign in match["prefix"] for sign in "+-")):
        raise ValueError(f"{line_item}: field '{field}' has an invalid numeric format: {value!r}.")
    if currency is not None:
        for symbol, code in SYMBOL_CURRENCIES.items():
            if symbol in match["prefix"] and code != currency:
                raise ValueError(f"{line_item}: field '{field}' currency {code} conflicts with "
                                 f"reporting currency {currency}; no FX conversion is performed.")
    sign = "-" if "-" in match["prefix"] else ""
    numeric_text = sign + match["number"].replace(",", "").replace("_", "")
    try:
        number = Decimal(numeric_text)
    except InvalidOperation as exc:
        raise ValueError(f"{line_item}: field '{field}' is not numeric: {value!r}.") from exc
    if negative_parentheses:
        number = number.copy_negate()
    return _require_finite(number, field=field, line_item=line_item)


def normalize_key(key: str) -> str:
    key = key.strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    return key.strip("_")


def _normalized_headers(headers: Iterable[object]) -> list[str]:
    normalized: list[str] = []
    seen: dict[str, str] = {}
    for raw in headers:
        original = "" if raw is None else str(raw)
        validate_text(original, field="Column header")
        key = normalize_key(original) if raw is not None else ""
        if key and key in seen:
            raise ValueError(
                f"Columns {seen[key]!r} and {original!r} normalize to the same key {key!r}."
            )
        if key:
            seen[key] = original
        normalized.append(key)
        if len(normalized) > MAX_COLUMNS:
            raise ValueError(f"Dataset exceeds the supported column count ({MAX_COLUMNS}).")
    return normalized


def normalize_row(row: dict[str, object]) -> dict[str, object]:
    if not isinstance(row, dict):
        raise ValueError("Each row must be an object with named columns.")
    if len(row) > MAX_COLUMNS:
        raise ValueError(f"Row exceeds the supported column count ({MAX_COLUMNS}).")
    normalized: dict[str, object] = {}
    originals: dict[str, str] = {}
    for raw_key, value in row.items():
        original = "" if raw_key is None else str(raw_key)
        validate_text(original, field="Column header")
        key = normalize_key(original)
        if not key:
            if value is not None and value != "":
                raise ValueError("Row data appears under a blank column header.")
            continue
        if key in normalized:
            raise ValueError(
                f"Columns {originals[key]!r} and {original!r} normalize to the same key {key!r}."
            )
        normalized[key] = value
        if isinstance(value, str):
            validate_text(value, field=f"Column {original!r}")
        originals[key] = original
    return normalized


def load_csv_text(text: str) -> list[dict[str, object]]:
    _validate_capture(text.encode("utf-8"))
    # Keep cells positional until validation; DictReader overwrites duplicate
    # blank header keys and can hide populated cells from the checks below.
    reader = csv.reader(io.StringIO(text), strict=True)
    headers = next(reader, None)
    if not headers:
        raise ValueError("CSV input has no header row.")
    normalized_headers = _normalized_headers(headers)
    output: list[dict[str, object]] = []
    for values in reader:
        if not values:  # Preserve DictReader's handling of empty physical lines.
            continue
        if len(values) != len(headers):
            raise ValueError(f"CSV row {reader.line_num}: column count does not match header.")
        if any(value and not header for header, value in zip(normalized_headers, values, strict=True)):
            raise ValueError(f"CSV row {reader.line_num}: data appears under a blank header.")
        output.append({header: value for header, value in zip(normalized_headers, values, strict=True) if header})
        if len(output) > MAX_ROWS or len(output) * len(headers) > MAX_CELLS:
            raise ValueError("CSV exceeds the supported row or cell count.")
    return output


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"Duplicate JSON key: {key!r}.")
        output[key] = value
    return output


def _validate_json_depth(payload: object) -> None:
    # Decoder recursion behavior varies across Python versions. Iterators keep
    # this explicit check's memory proportional to depth, rather than row count.
    iterators: list[Iterator[object]] = [iter((payload,))]
    cells = 0
    while iterators:
        try:
            value = next(iterators[-1])
        except StopIteration:
            iterators.pop()
            continue
        cells += 1
        if cells > MAX_CELLS:
            raise ValueError("JSON exceeds the supported value count.")
        if isinstance(value, dict):
            children = iter(value.values())
        elif isinstance(value, list):
            children = iter(value)
        else:
            if isinstance(value, str):
                validate_text(value, field="JSON value")
            continue
        if len(iterators) > MAX_JSON_DEPTH:
            raise ValueError("JSON nesting exceeds the supported depth.")
        iterators.append(children)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON constant {value!r} is not a finite number.")


def load_json_value(text: str) -> object:
    """Decode with bounded nesting, exact decimals, and unique object keys."""
    _validate_capture(text.encode("utf-8"))
    try:
        payload: object = json.loads(text, parse_float=Decimal, object_pairs_hook=_json_object,
                                     parse_constant=_reject_json_constant)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the supported depth.") from exc
    _validate_json_depth(payload)
    return payload


def load_json_text(text: str) -> list[dict[str, object]]:
    payload = load_json_value(text)
    if isinstance(payload, dict):
        if "rows" in payload and "data" in payload:
            raise ValueError("JSON input contains both 'rows' and 'data'; supply one dataset.")
        payload = payload.get("rows", payload.get("data"))
    if not isinstance(payload, list):
        raise ValueError("JSON input must be a list of row objects or contain a 'rows'/'data' list.")
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError("Every JSON row must be an object.")
    if len(payload) > MAX_ROWS:
        raise ValueError(f"Dataset exceeds the supported row count ({MAX_ROWS}).")
    return [normalize_row(row) for row in payload]


def _excel_loader() -> WorkbookLoader:
    try:
        module: object = __import__("openpyxl", fromlist=["load_workbook"])
    except ImportError as exc:
        raise ValueError(
            "Excel input requires the optional dependency: pip install 'variance-analysis-agent[excel]'"
        ) from exc
    return cast(WorkbookLoader, getattr(module, "load_workbook"))  # noqa: B009 (dynamic optional import)


def web_page_message(filename: str) -> str:
    """The refusal for an HTML file, naming what to upload instead."""
    return (f"'{filename}' is a web page. If it's a 10-K or 10-Q from SEC EDGAR, upload the filing's PDF, or "
            "download Financial_Report.xlsx from the filing's EDGAR folder and upload that; I can't read the "
            "HTML filing itself yet.")


def validate_input_format(suffix: str, *, assisted: bool = False, filename: str | None = None) -> None:
    suffix = suffix.lower()
    if suffix in {".htm", ".html"}:
        raise ValueError(web_page_message(filename or f"input{suffix}"))
    if suffix == ".pdf":
        if not assisted:
            raise ValueError(
                "PDF files are read with --assisted, which finds the financial statements in the "
                "filing and lists every adjustment it makes."
            )
        return
    if suffix not in {".csv", ".json", ".xlsx", ".xlsm", ".xls"}:
        raise ValueError(f"Unsupported input format '{suffix}'. Use CSV, JSON, XLSX, or XLSM.")
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        _excel_loader()


def read_input_bytes(path: str | Path) -> bytes:
    with Path(path).open("rb") as source:
        data = source.read(MAX_INPUT_BYTES + 1)
    _validate_capture(data)
    return data


def _validate_capture(data: bytes) -> None:
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds the supported size (32 MiB).")


def load_file(path: str | Path, *, sheet: str | None = None) -> list[dict[str, object]]:
    path = Path(path)
    validate_input_format(path.suffix)
    return load_bytes(read_input_bytes(path), path.suffix, source_name=path.name, sheet=sheet)


def load_bytes(
    data: bytes, suffix: str, *, source_name: str = "input", sheet: str | None = None
) -> list[dict[str, object]]:
    return load_input(data, suffix, source_name=source_name, sheet=sheet).rows


def load_input(
    data: bytes, suffix: str, *, source_name: str = "input", sheet: str | None = None
) -> ParsedInput:
    """Parse the same captured bytes whose digest identifies the analysis input."""
    if suffix.lower() == ".xls":
        # Read by content: an .xlsx renamed .xls is read as one; anything else is refused with the fix.
        kind = workbook_kind(data)
        if kind != "ooxml":
            raise ValueError(legacy_workbook_message(source_name, kind))
        suffix = ".xlsx"
    _validate_capture(data)
    suffix = suffix.lower()
    if sheet is not None and suffix not in {".xlsx", ".xlsm"}:
        raise ValueError("Worksheet selection requires XLSX or XLSM input.")
    if sheet is not None and not isinstance(sheet, str):
        raise ValueError("Worksheet name must be text.")
    if suffix == ".csv":
        text = data.decode("utf-8-sig")
        raw = next(csv.reader(io.StringIO(text)), [])
        return ParsedInput(load_csv_text(text), raw_headers=tuple(raw))
    if suffix == ".json":
        text = data.decode("utf-8")
        payload = load_json_value(text)
        table = payload.get("rows", payload.get("data")) if isinstance(payload, dict) else payload
        json_headers = (tuple(dict.fromkeys(k for row in table if isinstance(row, dict) for k in row if isinstance(k, str)))
                        if isinstance(table, list) else ())
        return ParsedInput(load_json_text(text), raw_headers=json_headers)
    if suffix in {".xlsx", ".xlsm"}:
        facts = inspect_workbook(data)
        stored_numbers = facts.numbers
        load_workbook = _excel_loader()

        # Own the capture handle even if workbook construction fails.
        with io.BytesIO(data) as source:
            wb = None
            try:
                wb = load_workbook(source, read_only=True, data_only=True)
                if sheet is not None and sheet not in wb.sheetnames:
                    raise ValueError(f"Worksheet {sheet!r} was not found; supply an exact --sheet name.")
                ws = wb.active if sheet is None else wb[sheet]
                if ws is None:
                    raise ValueError("Excel input has no active worksheet.")
                # Producer-provided dimensions can truncate data or inflate work.
                ws.reset_dimensions()
                numbers = stored_numbers.get(ws._worksheet_path, {})
                rows = ws.iter_rows()
                try:
                    raw_headers = [cell_value(cell, numbers=numbers, row=1, column=column)
                                   for column, cell in enumerate(next(rows), start=1)]
                except StopIteration as exc:
                    raise ValueError("Excel input is empty.") from exc
                headers = _normalized_headers(raw_headers)
                output: list[dict[str, object]] = []
                read_rows: dict[int, list[object]] = {}
                track_formulas = facts.may_have_unsaved_formulas(ws._worksheet_path)
                for row_number, cells in enumerate(rows, start=2):
                    values = tuple(cell_value(cell, numbers=numbers, row=row_number, column=column)
                                   for column, cell in enumerate(cells, start=1))
                    if track_formulas:
                        read_rows[row_number] = list(values)
                    if all(value is None or value == "" for value in values):
                        continue
                    if any(value is not None and value != ""
                           for value in values[len(headers):]):
                        raise ValueError(f"Excel row {row_number}: data appears under a blank "
                                         "header beyond the header row.")
                    if any(value is not None and value != "" and not header
                           for header, value in zip(headers, values, strict=False)):
                        raise ValueError(f"Excel row {row_number}: data appears under a blank header.")
                    # Without declared dimensions, physical rows may be short.
                    padded = list(values) + [None] * max(0, len(headers) - len(values))
                    output.append({h: v for h, v in zip(headers, padded, strict=False) if h})
                # A formula Excel never calculated reads as blank; name it instead (R4).
                stop = None if not track_formulas else table_formulas_message(
                    facts, ws._worksheet_path, source_name, header_row=1,
                    headers=["" if h is None else str(h) for h in raw_headers], rows=read_rows,
                    line_item_column=headers.index("line_item") if "line_item" in headers else None)
                if stop is not None:
                    raise ValueError(stop)
                return ParsedInput(output, ws.title, tuple(wb.sheetnames), tuple(str(h) if h is not None else "" for h in raw_headers))
            except (BadZipFile, KeyError, SyntaxError) as exc:
                raise ValueError(f"Invalid Excel workbook {source_name!r}: {exc}") from exc
            finally:
                if wb is not None:
                    wb.close()
    raise ValueError(f"Unsupported input format '{suffix}'. Use CSV, JSON, XLSX, or XLSM.")


def get_workbook_sheets(data: bytes, suffix: str) -> list[str]:
    """Return list of sheet names from Excel bytes without parsing data rows."""
    suffix = suffix.lower()
    if suffix not in {".xlsx", ".xlsm"}:
        return []
    load_workbook = _excel_loader()
    with io.BytesIO(data) as source:
        wb = None
        try:
            wb = load_workbook(source, read_only=True, data_only=True)
            return list(wb.sheetnames)
        except Exception:
            return []
        finally:
            if wb is not None:
                wb.close()


def first_present(row: dict[str, object], candidates: Iterable[str]) -> tuple[str, object] | None:
    for key in candidates:
        if key in row:
            return key, row[key]
    return None
