from __future__ import annotations

from decimal import Decimal

from variance_agent.models import AnalysisConfig, ComparisonBasis

B = ComparisonBasis.BUDGET
F = ComparisonBasis.FORECAST
P = ComparisonBasis.PRIOR_PERIOD

ROWS: list[dict[str, object]] = [
    {"line_item": "New Revenue", "type": "Revenue", "budget": "0", "actual": "200"},
    {"line_item": "Rent Expense", "type": "Expense", "budget": "100", "actual": "130"},
]


def cfg(
    basis: ComparisonBasis,
    label: str | None = None,
    *,
    period: str = "FY2025",
    dollar_threshold: Decimal = Decimal("10"),
) -> AnalysisConfig:
    return AnalysisConfig(
        period=period,
        dollar_threshold=dollar_threshold,
        percent_threshold=Decimal("0.05"),
        comparison_basis=basis,
        comparison_label=label,
    )
