"""Exact stable wire output. Only CSV text columns receive formula protection."""
from __future__ import annotations

import csv
import io
import json
import unicodedata
from decimal import Decimal
from typing import TYPE_CHECKING

from .comparison import display_outcome
from .comparisons import UnavailableComparison, _identity, verify_comparisons
from .audit import validate_source_identity
from .json_types import JSONObject
from .models import AnalyzedRow, ComparisonBasis

if TYPE_CHECKING:
    from .panel import BatchResult

LONG_FIELDS = ("line_item", "segment", "measure", "basis", "comparison_present", "comparison", "actual", "variance",
               "variance_percent", "variance_bps", "status", "material", "display_label", "source_sha256")
STATISTIC_FIELDS = ("prior_surprise_count", "surprise_window", "sample_variance", "sample_stddev", "standardized_surprise",
                    "standardized_reason", "dispersion_surprise", "dispersion_reason", "history_sha256")
_NUMERIC = {"comparison", "actual", "variance", "variance_percent", "variance_bps",
            "prior_surprise_count", "surprise_window", "sample_variance", "sample_stddev",
            "standardized_surprise", "dispersion_surprise"}


def _decimal(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def long_rows(batch: BatchResult) -> list[JSONObject]:
    """Groups sort lexically by declared keys, then source metric order, then requested basis order."""
    validate_source_identity(batch.source_name, batch.source_sha256)
    output: list[JSONObject] = []
    statistics_enabled = _has_statistics(batch)
    for group in batch.groups:
        table = group.analysis
        if table is None:
            continue
        verify_comparisons(table)
        validate_source_identity(table.source_name, table.source_sha256)
        if len(set(table.metric_order)) != len(table.metric_order):
            raise ValueError("Long output requires unique line item, segment and measure identities.")
        statistics = {(stat.line_item.strip().casefold(), stat.segment.strip().casefold(), stat.measure): stat
                      for stat in table.statistics}
        maps = []
        for comparison in table.comparisons:
            current: dict[tuple[str, str, object], AnalyzedRow | UnavailableComparison] = {}
            for row in comparison.result.rows if comparison.result else ():
                current[_identity(row)] = row
            for missing in comparison.unavailable:
                current[(missing.line_item.casefold(), missing.segment.casefold(), missing.measure)] = missing
            maps.append(current)
        expected = {identity for current in maps for identity in current}
        if set(table.metric_order) != expected:
            raise RuntimeError("Long-output metric order does not match the analyzed rows.")
        for identity in table.metric_order:
            for comparison, current in zip(table.comparisons, maps, strict=True):
                entry = current.get(identity)
                if entry is None:
                    continue
                present = isinstance(entry, AnalyzedRow)
                record: JSONObject = dict(zip(batch.group_by, group.keys, strict=True))
                record.update({"line_item": entry.line_item, "segment": entry.segment, "measure": str(entry.measure),
                               "basis": str(comparison.basis), "comparison_present": present,
                               "comparison": _decimal(entry.budget) if isinstance(entry, AnalyzedRow) else None,
                               "actual": _decimal(entry.actual),
                               "variance": _decimal(entry.variance_dollars) if isinstance(entry, AnalyzedRow) else None,
                               "variance_percent": _decimal(entry.variance_percent) if isinstance(entry, AnalyzedRow) else None,
                               "variance_bps": _decimal(entry.variance_bps) if isinstance(entry, AnalyzedRow) else None,
                               "status": str(entry.status) if isinstance(entry, AnalyzedRow) else None,
                               "material": entry.material if isinstance(entry, AnalyzedRow) else None,
                               "display_label": display_outcome(entry, comparison.basis) if isinstance(entry, AnalyzedRow) else "",
                               "source_sha256": batch.source_sha256 or table.source_sha256})
                if statistics_enabled:
                    stat = statistics.get(identity) if comparison.basis is ComparisonBasis.CONSENSUS else None
                    record.update({field: None for field in STATISTIC_FIELDS})
                    if stat is not None:
                        record.update(prior_surprise_count=str(stat.prior_count), surprise_window=str(stat.window),
                                      sample_variance=_decimal(stat.sample_variance), sample_stddev=_decimal(stat.sample_stddev),
                                      standardized_surprise=_decimal(stat.standardized_surprise),
                                      standardized_reason=stat.standardized_reason,
                                      dispersion_surprise=_decimal(stat.dispersion_surprise), dispersion_reason=stat.dispersion_reason,
                                      history_sha256=stat.history_sha256)
                output.append(record)
    return output


def _safe_text(value: str) -> str:
    probe = value.lstrip()
    while probe and (probe[0].isspace() or unicodedata.category(probe[0]).startswith("C")):
        probe = probe[1:]
    return "'" + value if probe.startswith(("=", "+", "-", "@")) else value


def _csv(fields: tuple[str, ...], rows: list[JSONObject], numeric: set[str]) -> str:
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
    writer.writerow({key: _safe_text(key) for key in fields})
    for row in rows:
        writer.writerow({key: "true" if value is True else "false" if value is False else
                         _safe_text(value) if isinstance(value, str) and key not in numeric else value
                         for key, value in row.items()})
    return handle.getvalue()


def long_csv(batch: BatchResult) -> str:
    fields = (*LONG_FIELDS, *STATISTIC_FIELDS) if _has_statistics(batch) else LONG_FIELDS
    return _csv((*batch.group_by, *fields), long_rows(batch), _NUMERIC)


def long_jsonl(batch: BatchResult) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n" for row in long_rows(batch))


def errors_csv(batch: BatchResult) -> str:
    rows: list[JSONObject] = []
    for group in batch.groups:
        if group.error is not None:
            row: JSONObject = dict(zip(batch.group_by, group.keys, strict=True))
            row.update(error=group.error, source_sha256=batch.source_sha256)
            rows.append(row)
    return _csv((*batch.group_by, "error", "source_sha256"), rows, set())


def _has_statistics(batch: BatchResult) -> bool:
    return batch.statistics_enabled or any(group.analysis is not None and group.analysis.statistic_context is not None
                                           for group in batch.groups)
