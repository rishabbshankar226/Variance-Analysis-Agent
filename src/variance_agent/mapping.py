"""Saved layout mapping memory for deterministic FP&A file intake.

Holds only structural rules, headers, ranges, and choices; never financial amounts.
Supports saving, loading, layout fingerprinting, and CLI --mapping application.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Iterable

from .limits import MAX_INPUT_BYTES


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

    def to_dict(self) -> dict[str, object]:
        return {
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


def load_mapping(data: bytes | str) -> LayoutMapping:
    """Parse and validate a LayoutMapping from JSON bytes or string."""
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError("Mapping file exceeds maximum allowed size.")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Mapping file must be a JSON object.")

    version = str(parsed.get("mapping_version", "1.5"))
    fingerprint = str(parsed.get("layout_fingerprint", ""))
    header_row = int(parsed.get("header_row_number", 1))
    sheet_name = parsed.get("sheet_name")
    if sheet_name is not None:
        sheet_name = str(sheet_name)
    column_mapping = {str(k): str(v) for k, v in dict(parsed.get("column_mapping", {})).items()}
    unit_scale = str(parsed["unit_scale"]) if parsed.get("unit_scale") is not None else None
    flip_signs = bool(parsed.get("flip_signs", False))
    treat_blank_zero = bool(parsed.get("treat_blank_budgets_as_zero", True))
    exclude_totals = [str(item) for item in list(parsed.get("exclude_totals", []))]
    period_sel = str(parsed["period_column_selection"]) if parsed.get("period_column_selection") is not None else None
    rules = parsed.get("classification_rules")
    classification_rules = dict(rules) if isinstance(rules, dict) else None

    return LayoutMapping(
        mapping_version=version,
        layout_fingerprint=fingerprint,
        header_row_number=header_row,
        sheet_name=sheet_name,
        column_mapping=column_mapping,
        unit_scale=unit_scale,
        flip_signs=flip_signs,
        treat_blank_budgets_as_zero=treat_blank_zero,
        exclude_totals=exclude_totals,
        period_column_selection=period_sel,
        classification_rules=classification_rules,
    )
