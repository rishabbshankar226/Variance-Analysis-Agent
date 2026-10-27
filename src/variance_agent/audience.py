"""Explicit opt-in configuration; the legacy public constructors remain stable."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import AnalysisConfig, AnalysisResult, ComparisonBasis, LineType
from .limits import validate_text
from .parsing import parse_decimal


@dataclass(frozen=True, kw_only=True)
class AudienceConfig(AnalysisConfig):
    per_share_threshold: Decimal | None = None
    count_threshold: Decimal | None = None
    bps_threshold: Decimal | None = None
    percent_values: str | None = None
    actual_label: str | None = None
    comparison_title: str | None = None
    extended_headers: bool = False
    preset: str = "fpa"
    layout: str | None = None
    per_share_lines: bool | None = None
    headline_items: tuple[str, ...] = ()


def validate_audience_config(config: AnalysisConfig) -> None:
    if not isinstance(config, AudienceConfig):
        return
    if config.preset not in {"fpa", "earnings", "quant"} or config.layout not in {None, "standard", "earnings"}:
        raise ValueError("Choose fpa, earnings or quant preset and standard or earnings layout.")
    if config.per_share_lines is not None and not isinstance(config.per_share_lines, bool):
        raise ValueError("Per-share filing lines must be an explicit boolean choice.")
    if not isinstance(config.headline_items, tuple):
        raise ValueError("Headline items must be a tuple of distinct line-item names.")
    for item in config.headline_items:
        validate_text(item, field="Headline item", nonblank=True)
    if len({item.strip().casefold() for item in config.headline_items}) != len(config.headline_items):
        raise ValueError("Headline items must be distinct line-item names.")
    if config.percent_values not in {None, "points", "fractions"}:
        raise ValueError("--percent-values must be points or fractions.")
    for name in ("dollar_threshold", "percent_threshold", "per_share_threshold", "count_threshold", "bps_threshold"):
        value = getattr(config, name)
        if value is not None:
            if not isinstance(value, Decimal):
                raise ValueError(f"--{name.replace('_', '-')} must be a Decimal initialized from text.")
            parse_decimal(value, field=name, line_item="Materiality")
            if value < 0:
                raise ValueError(f"--{name.replace('_', '-')} must be non-negative.")

    for label in (config.actual_label, config.comparison_title):
        if label is not None:
            validate_text(label, field="Comparison label", nonblank=True)
    if not isinstance(config.extended_headers, bool):
        raise ValueError("Extended header recognition must be an explicit boolean choice.")
    if not isinstance(config.type_map, dict):
        raise ValueError("Type map must be a dictionary of line-item classifications.")
    for key, value in config.type_map.items():
        validate_text(key, field="Type map key", nonblank=True)
        try:
            LineType(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("Type map values must be Revenue, Expense or Unclassified.") from exc


def is_audience_result(result: AnalysisResult) -> bool:
    return result.config.comparison_basis in NEW_BASES | OPT_IN_BASES or isinstance(result.config, AudienceConfig) or any(
        row.measure_declared or row.better is not None for row in result.rows
    )


NEW_BASES = frozenset({ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE, ComparisonBasis.GUIDANCE})
# Opt-in bases read from one table with per-row declarations (PLAN.md R13-R15); not the multi-comparison path.
OPT_IN_BASES = frozenset({ComparisonBasis.LIMIT, ComparisonBasis.BENCHMARK, ComparisonBasis.TARGET})


def audience_config(config: AnalysisConfig, *, extended_headers: bool = True) -> AudienceConfig:
    """Promote configuration without changing either legacy constructor."""
    from dataclasses import replace
    if not isinstance(config, AnalysisConfig):
        raise ValueError("Configuration must be an AnalysisConfig instance.")
    if isinstance(config, AudienceConfig):
        current = config
    else:
        current = AudienceConfig(config.period, config.dollar_threshold, config.percent_threshold,
                                 type_map=config.type_map, currency=config.currency,
                                 comparison_basis=config.comparison_basis, comparison_label=config.comparison_label)
    return replace(current, extended_headers=extended_headers)


def effective_layout(config: AnalysisConfig) -> str:
    if isinstance(config, AudienceConfig):
        return config.layout or ("earnings" if config.preset == "earnings" else "standard")
    return "standard"


def effective_per_share_lines(config: AnalysisConfig) -> bool:
    if isinstance(config, AudienceConfig):
        return config.per_share_lines if config.per_share_lines is not None else config.preset == "earnings"
    return False
