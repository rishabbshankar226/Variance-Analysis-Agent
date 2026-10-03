from __future__ import annotations

import csv
import io
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from zipfile import BadZipFile


_NUMBER_RE = re.compile(
    r"(?P<prefix>[+-]?[$€£]?|[$€£][+-]?)\s*"
    r"(?P<number>(?:(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:_[0-9]+)*)(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]+)?)"
)

_MISSING = {"", "na", "n/a", "none", "null", "-", "—"}


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in _MISSING)


def _require_finite(number: Decimal, *, field: str, line_item: str) -> Decimal:
    if not number.is_finite():
        raise ValueError(f"{line_item}: field '{field}' must be a finite number.")
    # Zero has no financial scale requirement. Extreme zero exponents bypass
    # arithmetic traps but expand to arbitrarily large fixed-point strings.
    if number.is_zero() and abs(number.as_tuple().exponent) > 999:
        return Decimal("-0") if number.is_signed() else Decimal("0")
    return number


def parse_decimal(value: Any, *, field: str, line_item: str) -> Decimal:
    if value is None:
        raise ValueError(f"{line_item}: required field '{field}' is missing.")
    if isinstance(value, bool):
        raise ValueError(f"{line_item}: field '{field}' must be numeric, not boolean.")
    if isinstance(value, Decimal):
        return _require_finite(value, field=field, line_item=line_item)
    if isinstance(value, (int, float)):
        return _require_finite(Decimal(str(value)), field=field, line_item=line_item)

    text = str(value).strip()
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


def _normalized_headers(headers: Iterable[Any]) -> list[str]:
    normalized: list[str] = []
    seen: dict[str, str] = {}
    for raw in headers:
        original = "" if raw is None else str(raw)
        key = normalize_key(original) if raw is not None else ""
        if key and key in seen:
            raise ValueError(
                f"Columns {seen[key]!r} and {original!r} normalize to the same key {key!r}."
            )
        if key:
            seen[key] = original
        normalized.append(key)
    return normalized


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    originals: dict[str, str] = {}
    for raw_key, value in row.items():
        if raw_key is None:
            continue
        original = str(raw_key)
        key = normalize_key(original)
        if key in normalized:
            raise ValueError(
                f"Columns {originals[key]!r} and {original!r} normalize to the same key {key!r}."
            )
        normalized[key] = value
        originals[key] = original
    return normalized


def load_csv_text(text: str) -> list[dict[str, Any]]:
    # Keep cells positional until validation; DictReader overwrites duplicate
    # blank header keys and can hide populated cells from the checks below.
    reader = csv.reader(io.StringIO(text), strict=True)
    headers = next(reader, None)
    if not headers:
        raise ValueError("CSV input has no header row.")
    normalized_headers = _normalized_headers(headers)
    output: list[dict[str, Any]] = []
    for values in reader:
        if not values:  # Preserve DictReader's handling of empty physical lines.
            continue
        if len(values) != len(headers):
            raise ValueError(f"CSV row {reader.line_num}: column count does not match header.")
        if any(value and not header for header, value in zip(normalized_headers, values)):
            raise ValueError(f"CSV row {reader.line_num}: data appears under a blank header.")
        output.append({header: value for header, value in zip(normalized_headers, values) if header})
    return output


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"Duplicate JSON key: {key!r}.")
        output[key] = value
    return output


def load_json_value(text: str) -> Any:
    """Decode without binary float conversion or silently overwritten keys."""
    return json.loads(text, parse_float=Decimal, object_pairs_hook=_json_object)


def load_json_text(text: str) -> list[dict[str, Any]]:
    payload = load_json_value(text)
    if isinstance(payload, dict):
        if "rows" in payload and "data" in payload:
            raise ValueError("JSON input contains both 'rows' and 'data'; supply one dataset.")
        payload = payload.get("rows", payload.get("data"))
    if not isinstance(payload, list):
        raise ValueError("JSON input must be a list of row objects or contain a 'rows'/'data' list.")
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError("Every JSON row must be an object.")
    return [normalize_row(row) for row in payload]


def load_file(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return load_csv_text(path.read_text(encoding="utf-8-sig"))
    if suffix == ".json":
        return load_json_text(path.read_text(encoding="utf-8"))
    if suffix in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise ValueError(
                "Excel input requires the optional dependency: pip install 'variance-analysis-agent[excel]'"
            ) from exc

        # Owning the input handle also closes it if workbook construction fails.
        with path.open("rb") as source:
            wb = None
            try:
                wb = load_workbook(source, read_only=True, data_only=True)
                ws = wb.active
                if ws is None:
                    raise ValueError("Excel input has no active worksheet.")
                # Producer-provided dimensions can truncate data or inflate work.
                ws.reset_dimensions()
                rows = ws.iter_rows(values_only=True)
                try:
                    raw_headers = list(next(rows))
                except StopIteration as exc:
                    raise ValueError("Excel input is empty.") from exc
                headers = _normalized_headers(raw_headers)
                output: list[dict[str, Any]] = []
                for row_number, values in enumerate(rows, start=2):
                    if all(value is None or value == "" for value in values):
                        continue
                    if any(value is not None and value != ""
                           for value in values[len(headers):]):
                        raise ValueError(f"Excel row {row_number}: data appears under a blank "
                                         "header beyond the header row.")
                    if any(value is not None and value != "" and not header
                           for header, value in zip(headers, values)):
                        raise ValueError(f"Excel row {row_number}: data appears under a blank header.")
                    # Without declared dimensions, physical rows may be short.
                    padded = list(values) + [None] * max(0, len(headers) - len(values))
                    output.append({h: v for h, v in zip(headers, padded) if h})
                return output
            except (BadZipFile, KeyError, SyntaxError) as exc:
                raise ValueError(f"Invalid Excel workbook {path.name!r}: {exc}") from exc
            finally:
                if wb is not None:
                    wb.close()
    raise ValueError(f"Unsupported input format '{suffix}'. Use CSV, JSON, XLSX, or XLSM.")


def first_present(row: dict[str, Any], candidates: Iterable[str]) -> tuple[str, Any] | None:
    for key in candidates:
        if key in row:
            return key, row[key]
    return None
