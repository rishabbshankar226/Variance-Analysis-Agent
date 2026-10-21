from __future__ import annotations

from decimal import Decimal

import pytest

from tests.comparison_helpers import B, F, P
from variance_agent.comparison import (
    BUDGET_SYNONYMS,
    basis_for_header,
    basis_noun,
    comparison_heading,
    comparison_statement,
    order_period_labels,
    parse_compare_to,
    parse_period_label,
    select_strict_comparison,
    zero_comparison_label,
)
from variance_agent.models import AnalysisConfig, ComparisonBasis


def test_config_defaults_to_budget() -> None:
    cfg = AnalysisConfig(
        period="Q3", dollar_threshold=Decimal("1"), percent_threshold=Decimal("0.05")
    )
    assert cfg.comparison_basis is ComparisonBasis.BUDGET
    assert cfg.comparison_label is None


@pytest.mark.parametrize(
    "header,basis",
    [
        ("budget", B), ("plan", B), ("forecast", F), ("fcst", F),
        ("outlook", F), ("prior_year", P), ("py", P), ("last_year", P),
        ("actual", None), ("fy2025", None),
    ],
)
def test_basis_for_header(header: str, basis: ComparisonBasis | None) -> None:
    assert basis_for_header(header) is basis


def test_budget_synonyms_match_intake() -> None:
    assert BUDGET_SYNONYMS == {
        "budget", "budget_amount", "plan", "planned",
        "budget_ytd", "ytd_budget", "plan_ytd", "bgt", "budget_amt",
    }


def test_parse_compare_to() -> None:
    assert parse_compare_to("Prior-Period") is P
    assert parse_compare_to("BUDGET") is B
    assert parse_compare_to("forecast") is F
    with pytest.raises(ValueError):
        parse_compare_to("prior_year")


def test_wording() -> None:
    assert [basis_noun(b) for b in (B, F, P)] == ["budget", "forecast", "prior period"]
    assert comparison_heading(B, "FY2025") == "Budget"
    assert comparison_heading(F, None) == "Forecast"
    assert comparison_heading(P, "FY2024") == "Prior Period (FY2024)"
    assert [zero_comparison_label(b) for b in (B, F, P)] == [
        "N/A (Unbudgeted)", "N/A (Not in forecast)", "N/A (New this period)"]


def test_parse_period_label_forms() -> None:
    assert parse_period_label("FY2025") == (2025, "year", 0)
    assert parse_period_label("fy25 Actual") == (2025, "year", 0)
    assert parse_period_label("2025") == (2025, "year", 0)
    assert parse_period_label("Q3 2025") == (2025, "quarter", 3)
    assert parse_period_label("Q3-25 Actuals") == (2025, "quarter", 3)
    assert parse_period_label("September 2025") == (2025, "month", 9)
    assert parse_period_label("2025-09") == (2025, "month", 9)
    assert parse_period_label("Q3") is None
    assert parse_period_label("hello") is None


def test_order_period_labels_mixed_year_spellings() -> None:
    assert order_period_labels(["FY24", "FY2025", "2023"]) == ["FY2025", "FY24", "2023"]
    assert order_period_labels(["Q2 2025", "Q3 2025"]) == ["Q3 2025", "Q2 2025"]
    assert order_period_labels(["Aug 2025", "Sep 2025", "2025-07"]) == [
        "Sep 2025", "Aug 2025", "2025-07"]
    assert order_period_labels(["FY2025", "Q3 2024"]) is None
    assert order_period_labels(["Q3", "Q2"]) is None
    assert order_period_labels(["FY2025", "FY2025"]) is None


def test_comparison_statement() -> None:
    assert comparison_statement(P, "FY2024", "FY2025") == (
        "Comparing FY2025 against FY2024 (prior period).")
    assert comparison_statement(P, "FY2024", "FY2025", ["FY2025", "FY2024", "FY2023"]) == (
        "Found FY2025, FY2024, FY2023 — comparing FY2025 against FY2024.")
    assert comparison_statement(F, None, None) == "Comparing Actual against the forecast."


def test_select_strict_comparison() -> None:
    rows: list[dict[str, object]] = [
        {"line_item": "A", "budget": "1", "forecast": "2", "actual": "3"}]
    assert select_strict_comparison(rows, B) is rows
    assert select_strict_comparison(rows, F) == [
        {"line_item": "A", "budget": "2", "actual": "3"}]
    with pytest.raises(ValueError, match="No prior period column"):
        select_strict_comparison(rows, P)
    with pytest.raises(ValueError, match="more than one forecast column"):
        select_strict_comparison(
            [{"line_item": "A", "forecast": "1", "fcst": "2", "actual": "3"}], F)
