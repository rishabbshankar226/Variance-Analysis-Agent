"""Deterministic, noninteractive group isolation over the table engine."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import DecimalException

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import PanelOptions
from .comparisons import TableAnalysis
from .limits import validate_text
from .models import LineType, MeasureKind
from .parsing import normalize_key


@dataclass(frozen=True)
class GroupResult:
    keys: tuple[str, ...]
    analysis: TableAnalysis | None
    error: str | None = None


@dataclass(frozen=True)
class BatchResult:
    group_by: tuple[str, ...]
    groups: tuple[GroupResult, ...]
    source_sha256: str | None = None
    source_name: str | None = None


def analyze_groups(rows: list[dict[str, object]], normalized: list[dict[str, object]],
                   group_by: tuple[str, ...], options: PanelOptions) -> BatchResult:
    from .api import _analyze_table
    from .long_output import LONG_FIELDS
    if not isinstance(group_by, tuple) or not group_by:
        raise ValueError("Choose a nonempty tuple of distinct group keys.")
    for key in group_by:
        validate_text(key, field="Group key", nonblank=True)
    keys = tuple(normalize_key(key) for key in group_by)
    if len(set(keys)) != len(keys):
        raise ValueError("Group keys must be distinct.")
    if any(key in {*LONG_FIELDS, "error"} for key in keys):
        raise ValueError("A group key conflicts with a reserved long-output column.")
    period_key = "period" in keys
    if period_key and options.config.period:
        raise ValueError("A Period group key cannot be combined with a configured period (--period).")
    if not period_key and not options.config.period:
        raise ValueError("A configured period is required without a Period group key.")
    groups: dict[tuple[str, ...], list[dict[str, object]]] = {}
    for original, row in zip(rows, normalized, strict=True):
        values = []
        for name, key in zip(group_by, keys, strict=True):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Missing or non-text group key {name!r}; supply a nonblank text value.")
            validate_text(value, field=f"Group key {name}", nonblank=True)
            values.append(value)
        groups.setdefault(tuple(values), []).append(original)
    output = []
    for identity, group in sorted(groups.items()):
        config = replace(options.config, period=identity[keys.index("period")]) if period_key else options.config
        try:
            table = _analyze_table(group, config, options.audience)
            for comparison in table.comparisons:
                for analyzed in comparison.result.rows if comparison.result else ():
                    if analyzed.measure is MeasureKind.CURRENCY and analyzed.line_type is LineType.UNCLASSIFIED and analyzed.better is None:
                        raise ValueError(f"{analyzed.line_item}: confirm Type or Better explicitly with a column or mapping "
                                         "before panel analysis.")
            # Unique identities are required to emit one unambiguous metric/basis record.
            identities = table.metric_order
            if len(set(identities)) != len(identities):
                raise ValueError("Duplicate line item, segment and measure; map distinct metric identities before panel analysis.")
            output.append(GroupResult(identity, table))
        except (ValueError, DecimalException) as exc:
            output.append(GroupResult(identity, None, str(exc)))
    return BatchResult(group_by, tuple(output))
