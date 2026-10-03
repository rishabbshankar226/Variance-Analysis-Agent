from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class LineType(StrEnum):
    REVENUE = "Revenue"
    EXPENSE = "Expense"
    UNCLASSIFIED = "Unclassified"


class Status(StrEnum):
    FAVORABLE = "F"
    UNFAVORABLE = "U"
    NEUTRAL = "Neutral"
    UNCLASSIFIED = "Unclassified"


@dataclass(frozen=True)
class AnalysisConfig:
    period: str
    dollar_threshold: Decimal
    percent_threshold: Decimal
    type_map: dict[str, LineType] = field(default_factory=dict)
    currency: str = "USD"


@dataclass(frozen=True)
class DriverReconciliation:
    modeled_budget: Decimal
    modeled_actual: Decimal
    budget_residual: Decimal | None
    actual_residual: Decimal | None
    component_residual: Decimal | None
    amount_tolerance: Decimal
    variance_tolerance: Decimal
    failure_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DriverEvidence:
    label: str
    components: tuple[tuple[str, Decimal], ...]
    reconciles: bool
    reconciliation: DriverReconciliation | None = None


@dataclass(frozen=True)
class SummaryVerification:
    outcome: str
    detail_count: int
    budget_residual: Decimal | None = None
    actual_residual: Decimal | None = None
    tolerance: Decimal | None = None


@dataclass(frozen=True)
class AnalyzedRow:
    line_item: str
    line_type: LineType
    budget: Decimal
    actual: Decimal
    variance_dollars: Decimal
    variance_percent: Decimal | None
    percent_label: str | None
    status: Status
    material: bool
    excluded_from_aggregation: bool
    driver_evidence: DriverEvidence | None
    raw: dict[str, Any]
    classification_source: str = "unavailable"
    summary_source: str = "unavailable"
    materiality_reason: str = "unavailable"
    summary_verification: SummaryVerification | None = None


@dataclass(frozen=True)
class Aggregate:
    budget: Decimal
    actual: Decimal
    variance_dollars: Decimal
    variance_percent: Decimal | None
    percent_label: str | None
    status: Status


@dataclass(frozen=True)
class AnalysisResult:
    config: AnalysisConfig
    rows: tuple[AnalyzedRow, ...]
    material_rows: tuple[AnalyzedRow, ...]
    revenue: Aggregate
    expenses: Aggregate
    warnings: tuple[str, ...]
