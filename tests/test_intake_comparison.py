from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tests.comparison_helpers import B, F, P
from variance_agent.intake import CanonicalRole, read_input_assisted
from variance_agent.models import ComparisonBasis

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _read(name: str, compare_to: ComparisonBasis | None = None):
    path = FIXTURES_DIR / name
    return read_input_assisted(
        path.read_bytes(),
        path.suffix,
        filename=name,
        compare_to=compare_to,
    )


def _read_text(csv_text: str, compare_to: ComparisonBasis | None = None):
    return read_input_assisted(
        csv_text.encode("utf-8"),
        ".csv",
        filename="test.csv",
        compare_to=compare_to,
    )


def _read_sample(path_str: str, compare_to: ComparisonBasis | None = None):
    p = Path(__file__).resolve().parent.parent / path_str
    return read_input_assisted(
        p.read_bytes(),
        p.suffix,
        filename=p.name,
        compare_to=compare_to,
    )


def test_forecast_column_detected() -> None:
    res = _read("fixture_k_forecast.csv")
    assert (res.comparison_basis, res.comparison_label) == (F, None)
    assert res.rows[0]["budget"] == Decimal("110000")
    assert "Comparing Actual against the forecast." in res.visible_transformations


def test_10k_three_years_compares_newest_two() -> None:
    res = _read("fixture_j_10k_three_years.csv")
    assert (res.comparison_basis, res.comparison_label) == (P, "FY2024")
    assert res.rows[0]["actual"] == Decimal("120000") and res.rows[0]["budget"] == Decimal("100000")
    assert "Found FY2025, FY2024, FY2023 — comparing FY2025 against FY2024." in res.visible_transformations


def test_reversed_year_columns() -> None:
    res = _read("fixture_m_years_reversed.csv")
    assert (res.comparison_basis, res.comparison_label) == (P, "2024")
    assert res.rows[0]["actual"] == Decimal("120000") and res.rows[0]["budget"] == Decimal("100000")


def test_numeric_year_headers_from_excel() -> None:
    res = _read("fixture_n_numeric_years.xlsx")
    assert (res.comparison_basis, res.comparison_label) == (P, "2024")
    assert res.rows[0]["actual"] == Decimal("120000") and res.rows[0]["budget"] == Decimal("100000")


def test_two_dated_actual_columns_are_prior_period() -> None:
    res = _read_text("Line Item,Type,FY2025 Actual,FY2024 Actual\nRent Expense,Expense,130,100\n")
    assert (res.comparison_basis, res.comparison_label) == (P, "FY2024")
    assert res.rows[0]["actual"] == Decimal("130") and res.rows[0]["budget"] == Decimal("100")


def test_budget_and_forecast_stops_and_asks() -> None:
    res = _read("fixture_l_budget_and_forecast.csv")
    assert res.has_fatal_errors and res.comparison_candidates == ["Budget", "Forecast"]
    assert res.fatal_error_message is not None
    assert "Budget" in res.fatal_error_message and "Forecast" in res.fatal_error_message


def test_compare_to_resolves_ambiguity() -> None:
    res = _read("fixture_l_budget_and_forecast.csv", compare_to=F)
    assert res.comparison_basis is F and res.rows[0]["budget"] == Decimal("110000")


def test_compare_to_missing_basis_errors() -> None:
    res = _read("fixture_k_forecast.csv", compare_to=P)
    assert res.has_fatal_errors and res.fatal_error_message is not None
    assert "No prior period column found" in res.fatal_error_message


def test_unorderable_periods_stop() -> None:
    res = _read_text("Line Item,Type,FY2025,Q3 2024\nRent Expense,Expense,1,2\n")
    assert res.has_fatal_errors and res.fatal_error_message is not None
    assert "FY2025" in res.fatal_error_message


def test_plain_budget_file_unchanged() -> None:
    res = _read_sample("examples/sample_variance.csv")
    assert res.comparison_basis is B and not any("Comparing" in t for t in res.visible_transformations)


def test_json_compare_to_forecast() -> None:
    data = b'[{"line_item": "A", "type": "Revenue", "forecast": 100, "actual": 120}]'
    res = read_input_assisted(data, ".json", filename="data.json", compare_to=F)
    assert res.comparison_basis is F and res.rows[0]["budget"] == 100


def _assert_wide_layout_stays_budget(csv_text: str, period: str) -> None:
    res = _read_text(csv_text)
    assert not res.has_fatal_errors
    assert res.comparison_basis is B and res.comparison_label is None
    assert res.rows[0]["budget"] == Decimal("3") and res.rows[0]["actual"] == Decimal("4")
    assert res.column_mapping[CanonicalRole.BUDGET] == f"{period} Budget"
    assert res.column_mapping[CanonicalRole.ACTUAL] == f"{period} Actual"
    assert res.visible_transformations == [
        f"Analyzed period: {period} (Budget from '{period} Budget', Actual from '{period} Actual')"
    ]


def test_wide_month_layout_stays_budget() -> None:
    _assert_wide_layout_stays_budget(
        "Line Item,Type,Jan-26 Budget,Jan-26 Actual,Feb-26 Budget,Feb-26 Actual\nRent,Expense,1,2,3,4\n",
        "Feb-26",
    )


def test_wide_fiscal_year_layout_stays_budget() -> None:
    _assert_wide_layout_stays_budget(
        "Line Item,Type,FY2025 Budget,FY2025 Actual,FY2024 Budget,FY2024 Actual\nRent,Expense,1,2,3,4\n",
        "FY2024",
    )


def test_wide_quarter_layout_stays_budget() -> None:
    _assert_wide_layout_stays_budget(
        "Line Item,Type,Q1 2026 Budget,Q1 2026 Actual,Q2 2026 Budget,Q2 2026 Actual\nRent,Expense,1,2,3,4\n",
        "Q2 2026",
    )


def test_two_budget_synonym_columns_use_the_first() -> None:
    res = _read_text("Line Item,Type,Budget,Plan,Actual\nRent,Expense,1,2,3\n")
    assert not res.has_fatal_errors
    assert res.comparison_basis is B and res.comparison_candidates == []
    assert res.rows[0]["budget"] == Decimal("1") and res.rows[0]["actual"] == Decimal("3")
    assert res.column_mapping[CanonicalRole.BUDGET] == "Budget"
    assert res.visible_transformations == []


def test_malformed_json_keeps_read_error_prefix() -> None:
    res = read_input_assisted(b"{not json", ".json", filename="bad.json")
    assert res.has_fatal_errors and res.fatal_error_message is not None
    assert res.fatal_error_message.startswith("Could not read JSON data from 'bad.json': ")
