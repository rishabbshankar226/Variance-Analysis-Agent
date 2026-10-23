"""Saved layout mapping memory for deterministic FP&A file intake.

Holds only structural rules, headers, ranges, and choices; never financial amounts.
Supports saving, loading, layout fingerprinting, and CLI --mapping application.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Iterable

from .models import ComparisonBasis
from .limits import validate_text


@dataclass
class LayoutMapping:
    mapping_version: str = "1.5"
    layout_fingerprint: str = ""
    header_row_number: int = 1
    sheet_name: str | None = None
    column_mapping: dict[str, str] = field(default_factory=dict)
    unit_scale: str | None = None
    flip_signs: bool = False
    treat_blank_budgets_as_zero: bool = True
    exclude_totals: list[str] = field(default_factory=list)
    period_column_selection: str | None = None
    classification_rules: dict[str, object] | None = None
    # Optional: the chosen comparison. Omitted from the file when unset, so Budget
    # mappings (and their SHA-256) are unchanged and older mappings still load.
    comparison_basis: ComparisonBasis | None = None
    comparison_bases: tuple[ComparisonBasis, ...] = ()
    measure_options: dict[str, str] | None = None
    better_directions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "mapping_version": self.mapping_version,
            "layout_fingerprint": self.layout_fingerprint,
            "header_row_number": self.header_row_number,
            "sheet_name": self.sheet_name,
            "column_mapping": dict(self.column_mapping),
            "unit_scale": self.unit_scale,
            "flip_signs": self.flip_signs,
            "treat_blank_budgets_as_zero": self.treat_blank_budgets_as_zero,
            "exclude_totals": list(self.exclude_totals),
            "period_column_selection": self.period_column_selection,
            "classification_rules": self.classification_rules,
        }
        if self.comparison_basis is not None:
            data["comparison_basis"] = self.comparison_basis.value
        if self.comparison_bases:
            data["comparison_bases"] = [str(basis) for basis in self.comparison_bases]
        if self.measure_options:
            data["measure_options"] = dict(self.measure_options)
        if self.better_directions:
            data["better_directions"] = dict(self.better_directions)
        return data


def _normalize_header_str(raw: str) -> str:
    text = raw.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def compute_layout_fingerprint(headers: Iterable[str]) -> str:
    """Compute deterministic SHA-256 fingerprint from raw header names."""
    norm = [_normalize_header_str(h) for h in headers if h.strip()]
    content = ",".join(norm).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def mapping_sha256(mapping: LayoutMapping) -> str:
    """Compute deterministic SHA-256 digest of mapping payload."""
    payload = json.dumps(mapping.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save_mapping(mapping: LayoutMapping) -> str:
    """Serialize layout mapping to JSON string, verifying no amounts are stored."""
    data = mapping.to_dict()
    # Ensure no rows or amounts are included
    for forbidden in ("rows", "amounts", "data", "budget_values", "actual_values"):
        if forbidden in data:
            del data[forbidden]
    return json.dumps(data, indent=2, ensure_ascii=False)


MAX_MAPPING_BYTES = 1024 * 1024
_RULE_KEYS = frozenset({"gl_ranges", "keywords", "bulk_default"})
_LINE_TYPE_NAMES = {"revenue": "Revenue", "expense": "Expense", "unclassified": "Unclassified"}


def _bad(field_name: str, expected: str) -> ValueError:
    return ValueError(f"Mapping file: {field_name} must be {expected}.")


def _whole_number(value: object, field_name: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad(field_name, "a whole number")
    if minimum is not None and value < minimum:
        raise _bad(field_name, f"a whole number of {minimum} or more")
    return value


def _text_or_none(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _bad(field_name, "text")
    return value


def _flag(value: object, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise _bad(field_name, "true or false")
    return value


def _line_type_name(value: object, field_name: str, *, allow_unclassified: bool) -> str:
    name = _LINE_TYPE_NAMES.get(str(value).strip().lower()) if isinstance(value, str) else None
    if name is None or (name == "Unclassified" and not allow_unclassified):
        allowed = "Revenue, Expense or Unclassified" if allow_unclassified else "Revenue or Expense"
        raise _bad(field_name, allowed)
    return name


def _unit_scale(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise _bad("unit_scale", "a positive number such as 1000")
    text = str(value).strip()
    try:
        scale = Decimal(text)
    except InvalidOperation:
        raise _bad("unit_scale", "a positive number such as 1000") from None
    if not scale.is_finite() or scale <= 0:
        raise _bad("unit_scale", "a positive number such as 1000")
    return text


def _classification_rules(value: object) -> dict[str, object] | None:
    """Validate the saved classification rules and spell their line types canonically."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _bad("classification_rules", "an object or null")
    unknown = sorted(str(key) for key in value if key not in _RULE_KEYS)
    if unknown:
        raise _bad("classification_rules", f"limited to gl_ranges, keywords and bulk_default (found {unknown[0]})")
    rules: dict[str, object] = {}
    if "gl_ranges" in value:
        raw_ranges = value["gl_ranges"]
        if not isinstance(raw_ranges, list):
            raise _bad("classification_rules.gl_ranges", "a list")
        ranges: list[object] = []
        for entry in raw_ranges:
            if not isinstance(entry, dict) or set(entry) != {"min", "max", "type"}:
                raise _bad("each gl_ranges entry", "an object with exactly min, max and type")
            low = _whole_number(entry["min"], "gl_ranges min")
            high = _whole_number(entry["max"], "gl_ranges max")
            if low > high:
                raise _bad("gl_ranges min", "no larger than max")
            ranges.append({
                "min": low, "max": high,
                "type": _line_type_name(entry["type"], "gl_ranges type", allow_unclassified=False),
            })
        rules["gl_ranges"] = ranges
    if "keywords" in value:
        raw_keywords = value["keywords"]
        if not isinstance(raw_keywords, dict):
            raise _bad("classification_rules.keywords", "an object")
        rules["keywords"] = {
            str(key): _line_type_name(kind, f"the type for keyword '{key}'", allow_unclassified=True)
            for key, kind in raw_keywords.items()
        }
    if "bulk_default" in value:
        bulk = value["bulk_default"]
        rules["bulk_default"] = (
            None if bulk is None else _line_type_name(bulk, "bulk_default", allow_unclassified=False)
        )
    return rules


def load_mapping(data: bytes | str) -> LayoutMapping:
    """Parse a LayoutMapping from JSON, rejecting anything the CLI could not apply safely."""
    raw = data if isinstance(data, bytes) else data.encode("utf-8")
    if len(raw) > MAX_MAPPING_BYTES:
        raise ValueError("Mapping file is too large (the limit is 1 MiB).")
    parsed = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(parsed, dict):
        raise ValueError("Mapping file must be a JSON object.")

    raw_columns = parsed.get("column_mapping", {})
    if not isinstance(raw_columns, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_columns.items()
    ):
        raise _bad("column_mapping", "an object of column names")
    raw_totals = parsed.get("exclude_totals", [])
    if not isinstance(raw_totals, list) or not all(isinstance(item, str) for item in raw_totals):
        raise _bad("exclude_totals", "a list of line-item names")
    version = parsed.get("mapping_version", "1.5")
    fingerprint = parsed.get("layout_fingerprint", "")
    if not isinstance(version, str) or not isinstance(fingerprint, str):
        raise _bad("mapping_version and layout_fingerprint", "text")

    basis_raw = parsed.get("comparison_basis")
    comparison_basis: ComparisonBasis | None = None
    if basis_raw is not None:
        try:
            comparison_basis = ComparisonBasis(str(basis_raw))
        except ValueError:
            raise ValueError(
                "Mapping comparison_basis must be budget, forecast or prior_period."
            ) from None

    raw_bases = parsed.get("comparison_bases", [])
    if not isinstance(raw_bases, list) or any(not isinstance(value, str) for value in raw_bases):
        raise _bad("comparison_bases", "a list of distinct comparison names")
    try:
        comparison_bases = tuple(ComparisonBasis(value) for value in raw_bases)
    except ValueError as exc:
        raise _bad("comparison_bases", "recognized comparison names") from exc
    if len(set(comparison_bases)) != len(comparison_bases):
        raise _bad("comparison_bases", "distinct comparison names")
    measure_options = parsed.get("measure_options")
    allowed = {"percent_values", "per_share_threshold", "count_threshold", "bps_threshold"}
    if measure_options is not None and (not isinstance(measure_options, dict)
                                        or any(k not in allowed or not isinstance(v, str) for k, v in measure_options.items())):
        raise _bad("measure_options", "an object of recognized scale/threshold text choices")
    if isinstance(measure_options, dict) and "percent_values" in measure_options:
        if measure_options["percent_values"] not in {"points", "fractions"}:
            raise _bad("measure_options.percent_values", "points or fractions")
    directions = parsed.get("better_directions", {})
    if not isinstance(directions, dict) or any(not isinstance(k, str) or v not in ("Higher", "Lower")
                                              for k, v in directions.items()):
        raise _bad("better_directions", "an object of line-item names to Higher or Lower")
    for label in directions:
        validate_text(label, field="Mapping file direction label", nonblank=True)
    for option in (measure_options or {}).values():
        validate_text(option, field="Mapping file measure option", nonblank=True)
    return LayoutMapping(
        mapping_version=version,
        layout_fingerprint=fingerprint,
        header_row_number=_whole_number(parsed.get("header_row_number", 1), "header_row_number", minimum=1),
        sheet_name=_text_or_none(parsed.get("sheet_name"), "sheet_name"),
        column_mapping=dict(raw_columns),
        unit_scale=_unit_scale(parsed.get("unit_scale")),
        flip_signs=_flag(parsed.get("flip_signs"), "flip_signs", False),
        treat_blank_budgets_as_zero=_flag(
            parsed.get("treat_blank_budgets_as_zero"), "treat_blank_budgets_as_zero", True
        ),
        exclude_totals=list(raw_totals),
        period_column_selection=_text_or_none(
            parsed.get("period_column_selection"), "period_column_selection"
        ),
        classification_rules=_classification_rules(parsed.get("classification_rules")),
        comparison_basis=comparison_basis, comparison_bases=comparison_bases,
        measure_options=measure_options, better_directions=directions,
    )
