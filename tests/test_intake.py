"""Tests for assisted file reading and intake processing (Phase 1)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent.intake import (
    CanonicalRole,
    detect_header_row,
    match_column_synonym,
    normalize_header,
    parse_assisted_decimal,
    rank_workbook_sheets,
    read_input_assisted,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_normalize_header() -> None:
    assert normalize_header("Account Description") == "account_description"
    assert normalize_header("Budget & Actual") == "budget_and_actual"
    assert normalize_header("Var $") == "var_dollar"
    assert normalize_header("Var %") == "var_percent"
    assert normalize_header("  Budget YTD (USD)  ") == "budget_ytd_usd"
    assert normalize_header("GL Account #") == "gl_account"


def test_match_column_synonym() -> None:
    # Line Item
    assert match_column_synonym("Account Description") == (CanonicalRole.LINE_ITEM, None)
    assert match_column_synonym("GL Account Name") == (CanonicalRole.LINE_ITEM, None)
    assert match_column_synonym("Account Title") == (CanonicalRole.LINE_ITEM, None)
    assert match_column_synonym("Line Item Name") == (CanonicalRole.LINE_ITEM, None)
    assert match_column_synonym("description") == (CanonicalRole.LINE_ITEM, None)

    # Account ID
    assert match_column_synonym("GL Account") == (CanonicalRole.ACCOUNT_ID, None)
    assert match_column_synonym("GL Account Number") == (CanonicalRole.ACCOUNT_ID, None)
    assert match_column_synonym("Acct #") == (CanonicalRole.ACCOUNT_ID, None)

    # Budget
    assert match_column_synonym("Budget YTD") == (CanonicalRole.BUDGET, None)
    assert match_column_synonym("YTD Budget") == (CanonicalRole.BUDGET, None)
    assert match_column_synonym("Plan YTD") == (CanonicalRole.BUDGET, None)
    assert match_column_synonym("Bgt") == (CanonicalRole.BUDGET, None)
    assert match_column_synonym("Budget Amt") == (CanonicalRole.BUDGET, None)
    assert match_column_synonym("Forecast") == (CanonicalRole.BUDGET, None)

    # Actual
    assert match_column_synonym("Actual YTD") == (CanonicalRole.ACTUAL, None)
    assert match_column_synonym("YTD Actual") == (CanonicalRole.ACTUAL, None)
    assert match_column_synonym("Act") == (CanonicalRole.ACTUAL, None)
    assert match_column_synonym("Actual Amt") == (CanonicalRole.ACTUAL, None)

    # Ignored computed columns
    assert match_column_synonym("Var $") == (CanonicalRole.IGNORED_COMPUTED, None)
    assert match_column_synonym("Var %") == (CanonicalRole.IGNORED_COMPUTED, None)
    assert match_column_synonym("Variance") == (CanonicalRole.IGNORED_COMPUTED, None)
    assert match_column_synonym("% of Budget") == (CanonicalRole.IGNORED_COMPUTED, None)


def test_parse_assisted_decimal_dashes_and_blanks() -> None:
    # Standard numbers
    val, note = parse_assisted_decimal("1,500.50", field="Budget", line_item="Salaries")
    assert val == Decimal("1500.50")
    assert note is None

    # Accounting dashes read as 0
    for dash in ("-", "–", "—"):
        val, note = parse_assisted_decimal(dash, field="Actual", line_item="Travel")
        assert val == Decimal("0")
        assert note is not None
        assert "accounting dash" in note.lower()

    # Blanks for Budget return None with is_blank indicator
    val, note = parse_assisted_decimal("", field="Budget", line_item="New Initiative", allow_blank=True)
    assert val is None
    assert note == "blank"

    # n/a raises a plain-language missing error
    with pytest.raises(ValueError) as exc:
        parse_assisted_decimal("n/a", field="Actual", line_item="Marketing")
    assert "required value in Actual is missing (marked n/a)" in str(exc.value)


def test_detect_header_row_skips_title_blocks() -> None:
    # Rows representing Fixture a: 4 title rows, then row 5 header
    rows = [
        ["FICTIONAL SYNTHETIC DATA - ACME CORP ERP EXPORT"],
        ["Report: YTD Departmental Variance Analysis"],
        ["Entity: 100 - North America (Fictional)"],
        ["Run Date: 2026-10-01 | Period: Q3 2026 | Currency: USD"],
        ["GL Account", "Account Description", "Budget YTD", "Actual YTD", "Var $", "Var %"],
        ["6100", "Software Subscriptions", 120000, 135000, 15000, 0.125],
    ]
    header_idx, mapping, ignored = detect_header_row(rows)
    assert header_idx == 4  # 0-indexed row 4 (1-indexed row 5)
    assert mapping[CanonicalRole.LINE_ITEM] == 1  # Account Description
    assert mapping[CanonicalRole.BUDGET] == 2     # Budget YTD
    assert mapping[CanonicalRole.ACTUAL] == 3     # Actual YTD
    assert mapping[CanonicalRole.ACCOUNT_ID] == 0 # GL Account
    assert 4 in ignored and 5 in ignored          # Var $, Var %


def test_rank_workbook_sheets() -> None:
    # Sheet 1: Cover Page (no BvA columns)
    cover_rows = [
        ["Acme Corporation - Monthly Management Pack"],
        ["Confidential - For Internal Use Only"],
    ]
    # Sheet 2: BvA (has line item, budget, actual)
    bva_rows = [
        ["Line Item", "Budget", "Actual"],
        ["Product Revenue", 500000, 520000],
    ]
    sheets = [
        ("Cover Page", cover_rows),
        ("BvA", bva_rows),
    ]
    ranked = rank_workbook_sheets(sheets)
    assert len(ranked) == 2
    assert ranked[0].name == "BvA"
    assert ranked[0].score > ranked[1].score
    assert "contains Line item, Budget, and Actual columns" in ranked[0].rationale


def test_read_input_assisted_fixture_a() -> None:
    path = FIXTURES_DIR / "fixture_a_erp_title_block.xlsx"
    res = read_input_assisted(path.read_bytes(), suffix=".xlsx", filename=path.name)
    assert not res.has_fatal_errors
    assert res.header_row_number == 5
    assert len(res.rows) == 5
    assert res.rows[0]["line_item"] == "Software Subscriptions"
    assert res.rows[0]["budget"] == Decimal("120000")
    assert res.rows[0]["actual"] == Decimal("135000")
    assert res.rows[0]["account_id"] == "6100"
    assert any("Var $" in note for note in res.visible_transformations)
    assert res.rows_skipped_count == 4


def test_read_input_assisted_fixture_d_dashes_and_blanks() -> None:
    path = FIXTURES_DIR / "fixture_d_thousands_dashes_blanks.xlsx"
    # When allow_blank_budgets is False, res flags blank budgets for confirmation
    res = read_input_assisted(path.read_bytes(), suffix=".xlsx", filename=path.name, treat_blank_budgets_as_zero=False)
    assert len(res.blank_budget_items) == 1
    assert "New Cloud Migration Expense" in res.blank_budget_items[0]

    # When treat_blank_budgets_as_zero is True, sets blank budget to 0
    res_zero = read_input_assisted(path.read_bytes(), suffix=".xlsx", filename=path.name, treat_blank_budgets_as_zero=True)
    assert not res_zero.has_fatal_errors
    row_new = next(r for r in res_zero.rows if "New Cloud Migration" in str(r["line_item"]))
    assert row_new["budget"] == Decimal("0")
    # Travel Expense had accounting dash '-'
    row_trv = next(r for r in res_zero.rows if "Travel" in str(r["line_item"]))
    assert row_trv["actual"] == Decimal("0")
    assert any("accounting dash" in t.lower() for t in res_zero.visible_transformations)


def test_read_input_assisted_pasted_tsv() -> None:
    path = FIXTURES_DIR / "fixture_i_pasted_tsv.txt"
    tsv_bytes = path.read_bytes()
    res = read_input_assisted(tsv_bytes, suffix=".tsv", filename="pasted_table.tsv")
    assert not res.has_fatal_errors
    assert len(res.rows) == 5
    assert res.rows[0]["line_item"] == "Subscription Revenue"
    assert res.rows[0]["budget"] == Decimal("100000")
    assert res.rows[0]["actual"] == Decimal("115000")


def test_read_input_assisted_fixture_g_selects_bva_sheet() -> None:
    path = FIXTURES_DIR / "fixture_g_cover_page_active.xlsx"
    res = read_input_assisted(path.read_bytes(), suffix=".xlsx", filename=path.name)
    assert not res.has_fatal_errors
    assert res.sheet_name == "BvA"
    assert len(res.rows) == 4
    assert res.rows[0]["line_item"] == "Product Revenue"
