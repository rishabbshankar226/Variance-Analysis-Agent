"""Measure vocabulary and exact input units. No monetary label is inferred."""
from __future__ import annotations

from decimal import Decimal

from .audience import AudienceConfig
from .models import AnalysisConfig, AnalyzedRow, BetterDirection, LineType, MeasureKind
from .numeric import financial_context
from .parsing import is_missing, normalize_key, parse_decimal

_ALIASES = {
    "currency": MeasureKind.CURRENCY, "money": MeasureKind.CURRENCY,
    "per_share": MeasureKind.PER_SHARE, "eps": MeasureKind.PER_SHARE,
    "percent": MeasureKind.PERCENT, "percentage": MeasureKind.PERCENT, "rate": MeasureKind.PERCENT,
    "count": MeasureKind.COUNT, "units": MeasureKind.COUNT,
    "multiple": MeasureKind.MULTIPLE, "multiples": MeasureKind.MULTIPLE, "turns": MeasureKind.MULTIPLE,
}


def measure_kind(value: object, line_item: str) -> MeasureKind:
    if is_missing(value):
        return MeasureKind.CURRENCY
    if not isinstance(value, str) or normalize_key(value) not in _ALIASES:
        raise ValueError(f"{line_item}: Measure must be Currency, Per Share, Percent, Count, or Multiple.")
    return _ALIASES[normalize_key(value)]


def direction(value: object, kind: MeasureKind, line_type: LineType, line_item: str) -> tuple[BetterDirection | None, str]:
    if is_missing(value):
        if kind is MeasureKind.PER_SHARE:
            return BetterDirection.HIGHER, "default_higher"
        if kind in {MeasureKind.PERCENT, MeasureKind.COUNT, MeasureKind.MULTIPLE}:
            raise ValueError(f"{line_item}: is Higher or Lower better? Supply Better as Higher or Lower.")
        return None, "type"
    if not isinstance(value, str) or value.strip().casefold() not in {"higher", "lower"}:
        raise ValueError(f"{line_item}: Better must be Higher or Lower.")
    selected = BetterDirection.HIGHER if value.strip().casefold() == "higher" else BetterDirection.LOWER
    if kind is MeasureKind.CURRENCY and line_type is not LineType.UNCLASSIFIED:
        expected = BetterDirection.HIGHER if line_type is LineType.REVENUE else BetterDirection.LOWER
        if selected is not expected:
            raise ValueError(f"{line_item}: Better {selected} contradicts Type {line_type}.")
    return selected, "explicit_better"


@financial_context()
def parse_measure_amount(value: object, *, kind: MeasureKind, config: AnalysisConfig, field: str, line_item: str) -> Decimal:
    if isinstance(value, float) and (kind is not MeasureKind.CURRENCY or isinstance(config, AudienceConfig)):
        raise ValueError(f"{line_item}: {field} cannot be a float; supply exact numeric text.")
    turns = isinstance(value, str) and value.strip().casefold().endswith("x")
    if turns and kind is not MeasureKind.MULTIPLE:
        raise ValueError(f"{line_item}: {field} uses x but Measure is {kind}.")
    if turns:
        assert isinstance(value, str)
        value = value.strip()[:-1]
    if kind is MeasureKind.CURRENCY:
        return parse_decimal(value, field=field, line_item=line_item, currency=config.currency)
    if isinstance(value, float):
        raise ValueError(f"{line_item}: {field} cannot be a float; supply exact numeric text.")
    has_percent = isinstance(value, str) and value.strip().endswith("%")
    if has_percent:
        if kind is not MeasureKind.PERCENT:
            raise ValueError(f"{line_item}: {field} uses % but Measure is {kind}.")
        assert isinstance(value, str)
        value = value.strip()[:-1]
    amount = parse_decimal(value, field=field, line_item=line_item)
    if kind is MeasureKind.PERCENT and not has_percent:
        scale = config.percent_values if isinstance(config, AudienceConfig) else None
        if scale is None:
            raise ValueError(f"{line_item}: bare rate in {field} needs --percent-values points or fractions.")
        if scale == "fractions":
            amount *= Decimal("100")
    return amount


def absolute_cutoff(config: AnalysisConfig, kind: MeasureKind, line_item: str = "Materiality") -> Decimal:
    if kind is MeasureKind.CURRENCY:
        return config.dollar_threshold
    name = {MeasureKind.PER_SHARE: "per_share_threshold", MeasureKind.COUNT: "count_threshold",
            MeasureKind.PERCENT: "bps_threshold", MeasureKind.MULTIPLE: "multiple_threshold"}[kind]
    value = getattr(config, name, None)
    if not isinstance(value, Decimal):
        raise ValueError(f"{line_item}: supply --{name.replace('_', '-')} for {kind} rows.")
    return value


def currency_row(row: AnalyzedRow) -> bool:
    return row.measure is MeasureKind.CURRENCY


def metric_inferences(rows: tuple[AnalyzedRow, ...], config: AnalysisConfig | None = None) -> list[str]:
    notes: list[str] = []
    for row in rows:
        if row.segment_declared:
            from .segments import SEGMENT_KEYS
            column = next((key for key in SEGMENT_KEYS if key in row.raw), "segment")
            column = str(row.raw.get("segment_source", column)).replace("_", " ").title()
            notes.append(f"{row.line_item}: read {column} as Segment {row.segment or '(unsegmented)'!r}.")
        if row.measure_declared:
            notes.append(f"{row.line_item}: read Measure as {row.measure}.")
        if row.measure is MeasureKind.PERCENT and any(str(row.raw.get(k, "")).strip().endswith("%") for k in ("budget", "actual")):
            notes.append(f"{row.line_item}: read % values as percentage points.")
        if row.better is not None:
            label = "defaulted" if row.direction_source == "default_higher" else "read"
            notes.append(f"{row.line_item}: {label} Better to {row.better}.")
    if isinstance(config, AudienceConfig) and config.percent_values is not None:
        notes.append(f"Read bare Percent values as {config.percent_values}.")
    return notes


def format_measure(value: Decimal, kind: MeasureKind, currency: str = "USD", *, variance: bool = False) -> str:
    from .report import _money
    if kind is MeasureKind.CURRENCY:
        return _money(value, currency, max(2, -int(value.as_tuple().exponent)))
    if kind is MeasureKind.PER_SHARE:
        return _money(value, currency, max(2, -int(value.as_tuple().exponent))) + "/sh"
    if kind is MeasureKind.MULTIPLE and value.as_tuple().exponent < -2:  # type: ignore[operator]
        # A computed ratio repeats; it is shown to two places, and the audit keeps it exact.
        from decimal import ROUND_HALF_EVEN, Inexact
        with financial_context() as context:
            context.traps[Inexact] = False
            value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    number = format(value, ",f")
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    if kind is MeasureKind.MULTIPLE:
        return number + "x"
    return number + (" bps" if variance else "%") if kind is MeasureKind.PERCENT else number + " units"
