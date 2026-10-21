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


# --- R14: named and period-only candidates are weighed against each other ---


def _assert_asks(res, *names: str) -> None:  # type: ignore[no-untyped-def]
    assert res.has_fatal_errors and not res.rows
    assert res.fatal_error_message is not None
    assert "Which should Actual be compared against?" in res.fatal_error_message
    for name in names:
        assert name in res.comparison_candidates
        assert name in res.fatal_error_message


_BUDGET_AND_YEARS = "Line Item,Type,Budget,FY2025,FY2024\nRent Expense,Expense,90,130,100\n"


def test_budget_column_and_year_columns_ask() -> None:
    res = _read_text(_BUDGET_AND_YEARS)
    _assert_asks(res, "Budget", "FY2024")
    assert res.comparison_choices == [B, P]


def test_budget_column_and_year_columns_resolve_with_compare_to() -> None:
    prior = _read_text(_BUDGET_AND_YEARS, compare_to=P)
    assert not prior.has_fatal_errors
    assert (prior.comparison_basis, prior.comparison_label) == (P, "FY2024")
    assert prior.rows[0]["actual"] == Decimal("130") and prior.rows[0]["budget"] == Decimal("100")

    budget = _read_text(_BUDGET_AND_YEARS, compare_to=B)
    assert not budget.has_fatal_errors and budget.comparison_basis is B
    assert budget.rows[0]["budget"] == Decimal("90") and budget.rows[0]["actual"] == Decimal("130")


def test_forecast_column_and_dated_actuals_ask() -> None:
    res = _read_text("Line Item,Type,Forecast,FY2025 Actual,FY2024 Actual\nRent Expense,Expense,90,130,100\n")
    _assert_asks(res, "Forecast", "FY2024 Actual")
    assert res.comparison_choices == [F, P]


def test_dated_forecast_beside_dated_actuals_asks() -> None:
    res = _read_text(
        "Line Item,Type,FY2025 Forecast,FY2025 Actual,FY2024 Actual\nRent Expense,Expense,90,130,100\n"
    )
    _assert_asks(res, "FY2025 Forecast", "FY2024 Actual")
    assert res.comparison_choices == []


def test_wide_monthly_forecast_layout_asks() -> None:
    res = _read_text(
        "Line Item,Type,Jan 2026 Forecast,Jan 2026 Actual,Feb 2026 Forecast,Feb 2026 Actual\n"
        "Rent Expense,Expense,1,2,3,4\n"
    )
    _assert_asks(res, "Jan 2026 Forecast", "Feb 2026 Forecast")
    assert res.comparison_choices == []


def test_wide_bgt_layout_pairs_as_budget() -> None:
    res = _read_text(
        "Line Item,Type,Jan 2026 Bgt,Jan 2026 Actual,Feb 2026 Bgt,Feb 2026 Actual\nRent,Expense,1,2,3,4\n"
    )
    assert not res.has_fatal_errors
    assert res.comparison_basis is B and res.comparison_label is None
    assert [p.period for p in res.detected_period_pairs] == ["Jan 2026", "Feb 2026"]
    assert res.rows[0]["budget"] == Decimal("3") and res.rows[0]["actual"] == Decimal("4")
    assert res.column_mapping[CanonicalRole.BUDGET] == "Feb 2026 Bgt"
    assert res.column_mapping[CanonicalRole.ACTUAL] == "Feb 2026 Actual"


def test_year_columns_beside_explicit_actual_ask() -> None:
    res = _read_text("Line Item,Type,FY25,FY24,Actual\nRent Expense,Expense,130,100,140\n")
    _assert_asks(res, "FY25", "FY24")
    assert res.comparison_choices == []


def test_header_fallback_keeps_named_budget_role() -> None:
    from variance_agent.intake import detect_header_row

    header: list[object] = ["Line Item", "Type", "Budget", "FY2025", "FY2024"]
    idx, roles, _ = detect_header_row([header])
    assert idx == 0
    assert roles[CanonicalRole.BUDGET] == 2 and roles[CanonicalRole.ACTUAL] == 3


# --- Final review I1: intake text names the comparison ---


def test_bad_prior_period_cell_problem_names_prior_period() -> None:
    res = _read_text("Line Item,Type,FY2025,FY2024\nRent Expense,Expense,130,abc\nFees,Expense,1,2\n")
    assert res.problems and "Prior Period (FY2024) column" in res.problems[0].message
    assert "budget" not in res.problems[0].message.lower()
    assert res.problems[0].column == "FY2024"


def test_blank_forecast_cells_treated_as_zero_note() -> None:
    res = read_input_assisted(
        b"Line Item,Type,Forecast,Actual\nA Revenue,Revenue,,10\nB Revenue,Revenue,,20\n",
        ".csv", filename="t.csv", treat_blank_budgets_as_zero=True,
    )
    assert "Treated blank forecast values as 0 on 2 lines not in forecast" in res.visible_transformations


def test_blank_budget_note_unchanged() -> None:
    res = read_input_assisted(
        b"Line Item,Type,Budget,Actual\nA Revenue,Revenue,,10\n",
        ".csv", filename="t.csv", treat_blank_budgets_as_zero=True,
    )
    assert "Treated blank budgets as 0 on 1 unbudgeted line" in res.visible_transformations


def test_missing_header_row_message_names_requested_basis() -> None:
    unknown = _read_text("Name,Amount\nRent,1\n")
    assert unknown.fatal_error_message is not None
    assert "Could not find a header row with Line Item, Budget, and Actual columns" in unknown.fatal_error_message
    assert "Forecast" in unknown.fatal_error_message

    forecast = _read_text("Name,Amount\nRent,1\n", compare_to=F)
    assert forecast.fatal_error_message is not None
    assert "Line Item, Forecast, and Actual columns" in forecast.fatal_error_message
    assert "budget" not in forecast.fatal_error_message.lower()


def test_worksheet_rationale_names_forecast(tmp_path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    cover = wb.active
    assert cover is not None
    cover.title = "Cover"
    cover.append(["Quarterly pack"])
    data = wb.create_sheet("Data")
    data.append(["Line Item", "Type", "Forecast", "Actual"])
    data.append(["Subscription Revenue", "Revenue", 110000, 115500])
    path = tmp_path / "pack.xlsx"
    wb.save(path)
    res = read_input_assisted(path.read_bytes(), ".xlsx", filename="pack.xlsx")
    assert res.comparison_basis is F
    note = res.visible_transformations[0]
    assert note.startswith("Selected worksheet 'Data'") and "Forecast" in note
    assert "budget" not in note.lower()
