from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from deterministic_conditioning.variance_bridge import generate_verified_commentary
from tests.comparison_helpers import B, F, P, cfg
from variance_agent.analysis import analyze_rows
from variance_agent.models import AnalysisConfig
from variance_agent.report import render_markdown

CONTRACTS = Path(__file__).parent / "fixtures" / "contracts"

PRIOR_ROWS: list[dict[str, object]] = [
    {"line_item": "Product Revenue", "type": "Revenue", "budget": "100000", "actual": "120000"},
    {"line_item": "Cost of Revenue", "type": "Expense", "budget": "45000", "actual": "50000"},
    {"line_item": "Operating Expenses", "type": "Expense", "budget": "32000", "actual": "30000"},
    {"line_item": "New Segment Revenue", "type": "Revenue", "budget": "0", "actual": "5000"},
]
FORECAST_ROWS: list[dict[str, object]] = [
    {"line_item": "Subscription Revenue", "type": "Revenue", "budget": "110000", "actual": "115500"},
    {"line_item": "Payroll Expense", "type": "Expense", "budget": "65000", "actual": "68000"},
    {"line_item": "New Partner Revenue", "type": "Revenue", "budget": "0", "actual": "2500"},
]


def _prior_cfg() -> AnalysisConfig:
    return cfg(P, "FY2024", period="FY2025", dollar_threshold=Decimal("1000"))


def test_prior_period_report_matches_golden() -> None:
    text = render_markdown(analyze_rows(PRIOR_ROWS, _prior_cfg()))
    assert text == (CONTRACTS / "prior_period.report.md").read_text(encoding="utf-8")
    assert "budget" not in text.lower()
    assert "| Line Item | Type | Prior Period (FY2024) | Actual |" in text
    assert "- Compared Against: Prior Period (FY2024)" in text
    assert "N/A (New this period)" in text


def test_forecast_report_matches_golden() -> None:
    config = cfg(F, None, period="Q3 2026", dollar_threshold=Decimal("1000"))
    text = render_markdown(analyze_rows(FORECAST_ROWS, config))
    assert text == (CONTRACTS / "forecast.report.md").read_text(encoding="utf-8")
    assert "budget" not in text.lower()
    assert "| Line Item | Type | Forecast | Actual |" in text
    assert "- Compared Against: Forecast" in text
    assert "N/A (Not in forecast)" in text


def test_budget_report_has_no_compared_against_line() -> None:
    text = render_markdown(analyze_rows(PRIOR_ROWS, cfg(B)))
    assert "Compared Against" not in text
    assert "| Budget |" in text


def test_driver_mismatch_names_the_comparison() -> None:
    rows: list[dict[str, object]] = [
        {"line_item": "Product Revenue", "type": "Revenue", "budget": "100000",
         "actual": "120000", "budget_volume": "10", "actual_volume": "10",
         "budget_price": "10", "actual_price": "10"},
    ]
    config = cfg(P, "FY2024", dollar_threshold=Decimal("1000"))
    text = render_markdown(analyze_rows(rows, config))
    assert "do not reconcile to Prior Period (FY2024)/Actual" in text
    assert "budget" not in text.lower()


def test_commentary_uses_basis_noun() -> None:
    config = cfg(P, "FY2024", dollar_threshold=Decimal("1000"))
    text, _ = generate_verified_commentary(analyze_rows(PRIOR_ROWS, config))
    assert "budget" not in text.lower()
    assert "prior period" in text


def test_budget_commentary_unchanged() -> None:
    text, _ = generate_verified_commentary(
        analyze_rows(PRIOR_ROWS, cfg(B, dollar_threshold=Decimal("1000")))
    )
    assert "budget" in text
