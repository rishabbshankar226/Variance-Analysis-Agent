"""Descriptive surprise statistics from supplied history and estimate dispersion."""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from decimal import Decimal, Inexact, localcontext
from pathlib import Path
from typing import TYPE_CHECKING

from .audit import sha256_bytes, validate_source_identity
from .comparison import parse_period_label, period_calendar
from .json_types import JSONObject
from .limits import MAX_ROWS, validate_text
from .models import AnalyzedRow, ComparisonBasis, MeasureKind
from .numeric import financial_context, ratio
from .parsing import load_input, normalize_row, parse_decimal, read_input_bytes

if TYPE_CHECKING:
    from .comparisons import TableAnalysis, UnavailableComparison


@dataclass(frozen=True)
class HistoryEntry:
    entity: str
    metric: str
    period: str
    surprise: Decimal
    segment: str = ""
    measure: MeasureKind | None = None


@dataclass(frozen=True)
class SurpriseHistory:
    entries: tuple[HistoryEntry, ...]
    source_name: str | None = None
    source_sha256: str | None = None


@dataclass(frozen=True, kw_only=True)
class SurpriseOptions:
    history: SurpriseHistory | None = None
    window: int = 8
    entity: str | None = None


@dataclass(frozen=True)
class SurpriseStatistic:
    entity: str
    line_item: str
    segment: str
    measure: MeasureKind
    surprise: Decimal | None
    history_sha256: str | None
    prior_periods: tuple[str, ...]
    prior_surprises: tuple[Decimal, ...]
    prior_count: int
    window: int
    sample_variance: Decimal | None
    sample_stddev: Decimal | None
    standardized_surprise: Decimal | None
    standardized_reason: str | None
    dispersion_surprise: Decimal | None
    dispersion_reason: str | None


def _period(label: str) -> tuple[int, str, int]:
    key = parse_period_label(label, extended=True)
    if key is None:
        raise ValueError(f"History period {label!r} is not recognized; supply an explicit quarter or period label.")
    return key


def _validate_history(history: SurpriseHistory) -> None:
    if len(history.entries) > MAX_ROWS:
        raise ValueError("History exceeds the supported row count.")
    validate_source_identity(history.source_name, history.source_sha256)
    groups: dict[tuple[str, str, str], list[HistoryEntry]] = {}
    for entry in history.entries:
        for field, value in (("entity", entry.entity), ("metric", entry.metric), ("period", entry.period)):
            validate_text(value, field=f"History {field}", nonblank=True)
        validate_text(entry.segment, field="History segment")
        if not isinstance(entry.surprise, Decimal):
            raise ValueError("History surprise must be exact Decimal text, never float.")
        parse_decimal(entry.surprise, field="surprise", line_item=entry.metric)
        if entry.measure is not None and not isinstance(entry.measure, MeasureKind):
            raise ValueError("History Measure must be a supported measure kind.")
        groups.setdefault((entry.entity.casefold(), entry.metric.casefold(), entry.segment.casefold()), []).append(entry)
    for entries in groups.values():
        keys = [_period(entry.period) for entry in entries]
        if len(set(keys)) != len(keys):
            raise ValueError(f"History {entries[0].metric}: duplicate history period.")
        if len({key[1] for key in keys}) > 1:
            raise ValueError("History mixes period granularity; choose a single period type.")
        if len({period_calendar(entry.period) for entry in entries if _period(entry.period)[1] == "quarter"}) > 1:
            raise ValueError("History mixes fiscal and calendar quarters; map consistent periods explicitly.")


def history_from_rows(rows: list[dict[str, object]]) -> SurpriseHistory:
    """Bound and parse in-memory history, without claiming a source-file hash."""
    from .api import validate_table
    from .measures import measure_kind
    validate_table(rows)
    entries = []
    for raw in rows:
        row = normalize_row(raw)
        entity = row.get("entity", row.get("ticker"))
        metric = row.get("metric", row.get("line_item"))
        period = row.get("period")
        for field, value in (("entity", entity), ("metric", metric), ("period", period)):
            validate_text(value, field=f"History {field}", nonblank=True)
        value = row.get("surprise")
        if isinstance(value, float):
            raise ValueError("History surprise cannot be float; supply exact numeric text.")
        amount = parse_decimal(value, field="surprise", line_item=str(metric))
        segment = row.get("segment", "")
        validate_text(segment, field="History segment")
        entries.append(HistoryEntry(str(entity).strip(), str(metric).strip(), str(period).strip(), amount,
                                    str(segment).strip(), measure_kind(row["measure"], str(metric)) if row.get("measure") else None))
    history = SurpriseHistory(tuple(entries))
    _validate_history(history)
    return history


def load_history(path: str | Path) -> SurpriseHistory:
    """Capture one bounded CSV/JSON history; values for Percent metrics are bps."""
    source = Path(path)
    if source.suffix.lower() not in {".csv", ".json"}:
        raise ValueError("History input must be CSV or JSON.")
    data = read_input_bytes(source)
    parsed = load_input(data, source.suffix, source_name=source.name)
    history = history_from_rows(parsed.rows)
    return replace(history, source_name=source.name, source_sha256=sha256_bytes(data))


def validate_options(options: SurpriseOptions) -> None:
    if not isinstance(options.window, int) or isinstance(options.window, bool) or options.window < 4:
        raise ValueError(f"A surprise window of {options.window} is below the minimum of 4 or is not an integer.")
    if options.entity is not None:
        validate_text(options.entity, field="History entity", nonblank=True)
    if options.history is not None:
        _validate_history(options.history)


def infer_entity(rows: list[dict[str, object]]) -> str | None:
    entities = set()
    for raw in rows:
        row = normalize_row(raw)
        value = row.get("ticker", row.get("entity"))
        if value is not None:
            validate_text(value, field="Entity", nonblank=True)
            entities.add(str(value).strip())
    if len(entities) > 1:
        raise ValueError("Multiple entities found; use a panel or choose the entity explicitly.")
    return next(iter(entities), None)


@financial_context()
def _statistics(table: TableAnalysis, options: SurpriseOptions) -> tuple[SurpriseStatistic, ...]:
    validate_options(options)
    consensus = next((c for c in table.comparisons if c.basis is ComparisonBasis.CONSENSUS), None)
    if consensus is None:
        raise ValueError("Surprise statistics require a supplied Consensus comparison.")
    entity = options.entity
    if entity is None and consensus.result is not None:
        entity = infer_entity([row.raw for row in consensus.result.rows])
    if entity is None and options.history is not None:
        raise ValueError("History needs an entity; supply a Ticker/Entity column or --entity.")
    entity = entity or ""
    current = _period(table.config.period) if options.history is not None else None
    available = list(consensus.result.rows) if consensus.result is not None else []
    entries: list[AnalyzedRow | UnavailableComparison] = [*available, *consensus.unavailable]
    output = []
    for entry in entries:
        present = isinstance(entry, AnalyzedRow)
        surprise = ((entry.variance_bps if entry.measure is MeasureKind.PERCENT else entry.variance_dollars)
                    if isinstance(entry, AnalyzedRow) else None)
        selected: list[HistoryEntry] = []
        if options.history is not None:
            for prior in options.history.entries:
                if (prior.entity.casefold(), prior.metric.casefold(), prior.segment.casefold()) != (
                        entity.casefold(), entry.line_item.casefold(), entry.segment.casefold()):
                    continue
                key = _period(prior.period)
                assert current is not None
                if key[1] != current[1]:
                    raise ValueError(f"{entry.line_item}: history and current period have different granularity.")
                if key[1] == "quarter" and period_calendar(prior.period) != period_calendar(table.config.period):
                    raise ValueError(f"{entry.line_item}: history and current period mix fiscal and calendar quarters.")
                if prior.measure is not None and prior.measure is not entry.measure:
                    raise ValueError(f"{entry.line_item}: history Measure conflicts with the current measure.")
                if key < current:
                    selected.append(prior)
            selected = sorted(selected, key=lambda prior: _period(prior.period))[-options.window:]
        count = len(selected)
        variance = deviation = standardized = None
        reason: str | None = "history not supplied" if options.history is None else "fewer than 4 prior surprises"
        if count >= 4:
            n = Decimal(count)
            total = sum((prior.surprise for prior in selected), Decimal("0"))
            squares = sum((prior.surprise * prior.surprise for prior in selected), Decimal("0"))
            variance = ratio(n * squares - total * total, n * (n - 1))
            with localcontext() as context:
                context.traps[Inexact] = False
                deviation = variance.sqrt()
            if deviation == 0:
                reason = "zero historical deviation"
            elif surprise is not None:
                standardized, reason = ratio(surprise, deviation), None
        dispersion = entry.comparison_details.dispersion if entry.comparison_details is not None else None
        dispersion_reason: str | None = "estimate dispersion not supplied" if dispersion is None else "zero estimate dispersion"
        dispersion_surprise = None
        if dispersion is not None and dispersion != 0 and surprise is not None:
            denominator = dispersion * Decimal("100") if entry.measure is MeasureKind.PERCENT else dispersion
            dispersion_surprise, dispersion_reason = ratio(surprise, denominator), None
        if not present:
            reason = dispersion_reason = "consensus not supplied"
        output.append(SurpriseStatistic(entity, entry.line_item, entry.segment, entry.measure, surprise,
                                       options.history.source_sha256 if options.history is not None else None,
                                       tuple(prior.period for prior in selected), tuple(prior.surprise for prior in selected),
                                       count, options.window, variance, deviation,
                                       standardized, reason, dispersion_surprise, dispersion_reason))
    return tuple(output)


def attach_statistics(table: TableAnalysis, options: SurpriseOptions | None = None) -> TableAnalysis:
    if options is None:
        opted_in = False
        for comparison in table.comparisons:
            if comparison.basis is not ComparisonBasis.CONSENSUS:
                continue
            rows: list[AnalyzedRow | UnavailableComparison] = list(comparison.result.rows) if comparison.result else []
            rows.extend(comparison.unavailable)
            opted_in = opted_in or any(row.comparison_details is not None and row.comparison_details.dispersion is not None
                                      for row in rows)
        if not opted_in:
            return table
        options = SurpriseOptions()
    return replace(table, statistic_context=options, statistics=_statistics(table, options))


def verify_statistics(table: TableAnalysis) -> None:
    if table.statistic_context is None:
        if table.statistics:
            raise RuntimeError("Surprise statistics have no configuration.")
    elif table.statistics != _statistics(table, table.statistic_context):
        raise RuntimeError("Surprise statistic verification mismatch.")


def statistic_record(stat: SurpriseStatistic) -> JSONObject:
    record: JSONObject = {}
    for field in fields(stat):
        value = getattr(stat, field.name)
        record[field.name] = (format(value, "f") if isinstance(value, Decimal) else str(value) if isinstance(value, MeasureKind)
                              else [format(item, "f") if isinstance(item, Decimal) else item for item in value]
                              if isinstance(value, tuple) else value)
    return record


def statistics_configuration(table: TableAnalysis) -> JSONObject:
    options = table.statistic_context
    assert options is not None
    return {"window": options.window, "entity": options.entity,
            "history_source": options.history.source_name if options.history is not None else None,
            "history_sha256": options.history.source_sha256 if options.history is not None else None}


@financial_context()
def render_statistics(table: TableAnalysis) -> str:
    from .report import _safe_inline
    if not table.statistics:
        return ""
    lines = ["", "## Descriptive surprise statistics", "", "Compared only with supplied history and estimate dispersion.", "",
             "| Entity | Metric | Segment | Prior count | Standardized surprise | Dispersion surprise | Availability |",
             "|---|---|---|---:|---:|---:|---|"]
    for stat in table.statistics:
        cells = [stat.entity, stat.line_item, stat.segment, str(stat.prior_count),
                 format(stat.standardized_surprise, ".4f") if stat.standardized_surprise is not None else "N/A",
                 format(stat.dispersion_surprise, ".4f") if stat.dispersion_surprise is not None else "N/A",
                 "; ".join(reason for reason in (stat.standardized_reason, stat.dispersion_reason) if reason)]
        lines.append("| " + " | ".join(_safe_inline(cell) for cell in cells) + " |")
    return "\n".join([*lines, ""])
