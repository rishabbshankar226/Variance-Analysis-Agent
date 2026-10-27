from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum


class LineType(StrEnum):
    REVENUE = "Revenue"
    EXPENSE = "Expense"
    UNCLASSIFIED = "Unclassified"


class Status(StrEnum):
    FAVORABLE = "F"
    UNFAVORABLE = "U"
    NEUTRAL = "Neutral"
    UNCLASSIFIED = "Unclassified"


class MeasureKind(StrEnum):
    CURRENCY = "Currency"
    PER_SHARE = "Per Share"
    PERCENT = "Percent"
    COUNT = "Count"
    MULTIPLE = "Multiple"  # 3.25x, in turns (PLAN.md R16)


class BetterDirection(StrEnum):
    HIGHER = "Higher"
    LOWER = "Lower"


class ComparisonBasis(StrEnum):
    BUDGET = "budget"
    FORECAST = "forecast"
    PRIOR_PERIOD = "prior_period"
    CONSENSUS = "consensus"
    ESTIMATE = "estimate"
    GUIDANCE = "guidance"
    LIMIT = "limit"  # opt-in (PLAN.md R13-R15): each row's limit, benchmark or target
    BENCHMARK = "benchmark"
    TARGET = "target"


@dataclass(frozen=True)
class AnalysisConfig:
    period: str
    dollar_threshold: Decimal
    percent_threshold: Decimal
    type_map: dict[str, LineType] = field(default_factory=dict)
    currency: str = "USD"
    comparison_basis: ComparisonBasis = ComparisonBasis.BUDGET
    comparison_label: str | None = None


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
class ComparisonDetails:
    consensus_low: Decimal | None = None
    consensus_high: Decimal | None = None
    estimator_count: int | None = None
    dispersion: Decimal | None = None
    consensus_range_position: str | None = None
    guidance_low: Decimal | None = None
    guidance_high: Decimal | None = None
    guidance_position: str | None = None
    guidance_midpoint: Decimal | None = None


@dataclass(frozen=True)
class BasisDetails:
    """A row compared with a limit, benchmark or target (PLAN.md R13-R15): its declarations and outcome."""

    basis: str
    outcome: str  # Breach | Near | Within; Above | Below | In line; Over | Under | On target
    difference: Decimal  # actual - comparison, in the row's unit
    difference_bps: Decimal | None = None  # for Percent rows
    limit_kind: str | None = None  # Max | Min
    buffer: Decimal | None = None
    headroom: Decimal | None = None
    utilization: Decimal | None = None  # None is NM: a zero limit
    tolerance: Decimal | None = None
    severity: int | None = None  # 0 Breach, 1 Near, 2 Within


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
    raw: dict[str, object]
    classification_source: str = "unavailable"
    summary_source: str = "unavailable"
    materiality_reason: str = "unavailable"
    summary_verification: SummaryVerification | None = None
    measure: MeasureKind = MeasureKind.CURRENCY
    better: BetterDirection | None = None
    direction_source: str = "type"
    variance_bps: Decimal | None = None
    measure_declared: bool = False
    comparison_details: ComparisonDetails | None = None
    segment: str = ""
    segment_declared: bool = False
    statement_kind: str = ""  # "balance_sheet" or "cash_flow": compared as Increase or Decrease (PLAN.md R7)
    basis_details: BasisDetails | None = None  # a limit, benchmark or target comparison (PLAN.md R13-R15)


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
