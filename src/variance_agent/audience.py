"""Explicit opt-in configuration; the legacy public constructors remain stable."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import AnalysisConfig, AnalysisResult
from .parsing import parse_decimal


@dataclass(frozen=True, kw_only=True)
class AudienceConfig(AnalysisConfig):
    per_share_threshold: Decimal | None = None
    count_threshold: Decimal | None = None
    bps_threshold: Decimal | None = None
    percent_values: str | None = None


def validate_audience_config(config: AnalysisConfig) -> None:
    if not isinstance(config, AudienceConfig):
        return
    if config.percent_values not in {None, "points", "fractions"}:
        raise ValueError("--percent-values must be points or fractions.")
    for name in ("per_share_threshold", "count_threshold", "bps_threshold"):
        value = getattr(config, name)
        if value is not None:
            if not isinstance(value, Decimal):
                raise ValueError(f"--{name.replace('_', '-')} must be a Decimal initialized from text.")
            parse_decimal(value, field=name, line_item="Materiality")
            if value < 0:
                raise ValueError(f"--{name.replace('_', '-')} must be non-negative.")


def is_audience_result(result: AnalysisResult) -> bool:
    return isinstance(result.config, AudienceConfig) or any(
        row.measure_declared or row.better is not None for row in result.rows
    )
