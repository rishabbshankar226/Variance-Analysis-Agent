"""Response formatting bridge between the engine and the chat UI.

Reuses the exact formatting functions from report.py so that every number
displayed in the chatbot is identical to what appears in the CLI report.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from variance_agent.models import AnalysisResult, AnalyzedRow, Status, MeasureKind
from variance_agent.measures import format_measure
from variance_agent.report import _money, _pct, _report_places, _safe_inline, _threshold_number
from variance_agent.currencies import CURRENCY_SYMBOLS


@dataclass(frozen=True)
class Response:
    """Structured response from a handler to the chat UI."""

    text: str
    table: list[dict[str, str]] | None = None
    chips: list[str] | None = None
    download: dict[str, str | bytes] | None = None
    phase: str | None = None


def format_money(value: Decimal, currency: str = "USD", places: int = 2) -> str:
    """Format a monetary value using the engine's exact formatter."""
    return _money(value, currency, places)


def format_pct(budget: Decimal, variance: Decimal, label: str | None = None) -> str:
    """Format a percentage using the engine's exact formatter."""
    return _pct(budget, variance, label)


def format_threshold_amount(value: Decimal, currency: str = "USD") -> str:
    """A dollar cutoff with every significant digit ('$10,000.00', '$2.505')."""
    return f"{CURRENCY_SYMBOLS.get(currency, '$')}{_threshold_number(value, 2)}"


def format_threshold_pct(ratio: Decimal) -> str:
    """A percent cutoff held as a ratio, with every significant digit ('5.0%', '0.125%')."""
    return f"{_threshold_number(ratio, 1, scale=2)}%"


def safe_inline(value: object) -> str:
    """Sanitize source-derived text for display."""
    return _safe_inline(value)


def report_places(result: AnalysisResult) -> int:
    """Determine decimal places needed for exact reconciliation."""
    return _report_places(result)


def row_to_table_dict(
    row: AnalyzedRow, currency: str = "USD", places: int = 2, comparison: str = "Budget",
) -> dict[str, str]:
    """Convert an AnalyzedRow to a display-ready table row dict.

    ``comparison`` names the column Actual is compared against, e.g. "Forecast".
    """
    if row.measure is not MeasureKind.CURRENCY:
        variance = row.variance_bps if row.measure is MeasureKind.PERCENT else row.variance_dollars
        assert variance is not None
        return {
            "Line Item": safe_inline(row.line_item), "Measure": str(row.measure),
            comparison: format_measure(row.budget, row.measure, currency),
            "Actual": format_measure(row.actual, row.measure, currency),
            "Variance": format_measure(variance, row.measure, currency, variance=True),
            "Var (%)": format_pct(row.budget, row.variance_dollars, row.percent_label), "Status": str(row.status),
        }
    return {
        "Line Item": safe_inline(row.line_item),
        "Type": str(row.line_type),
        comparison: format_money(row.budget, currency, places),
        "Actual": format_money(row.actual, currency, places),
        f"Var ({CURRENCY_SYMBOLS.get(currency, '$')})": format_money(
            row.variance_dollars, currency, places,
        ),
        "Var (%)": format_pct(row.budget, row.variance_dollars, row.percent_label),
        "Status": str(row.status),
    }


def status_label(status: Status) -> str:
    """Human-readable status label."""
    labels = {
        Status.FAVORABLE: "Favorable",
        Status.UNFAVORABLE: "Unfavorable",
        Status.NEUTRAL: "Neutral",
        Status.UNCLASSIFIED: "Unclassified",
    }
    return labels.get(status, str(status))
