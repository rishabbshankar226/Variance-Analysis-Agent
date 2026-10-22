"""Smaller engine and CLI fixes from the 2026-10 bug hunt."""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.intake import plain_analysis_error, rank_workbook_sheets
from variance_agent.limits import display_text
from variance_agent.models import LineType

BASE = ["--period", "Q3", "--dollar-threshold", "10", "--percent-threshold", "5"]


# --- --type-map speaks the same vocabulary as the Type column ---


def test_type_map_accepts_the_words_the_type_column_accepts() -> None:
    parsed = cli._parse_type_map(json.dumps({
        "Rent": "opex", "Materials": "COGS", "Fees": "Costs", "Subscriptions": "rev",
        "Product Sales": "Sales", "Sales and Marketing": "Unclassified",
    }).encode("utf-8"))
    assert parsed == {
        "Rent": LineType.EXPENSE, "Materials": LineType.EXPENSE, "Fees": LineType.EXPENSE,
        "Subscriptions": LineType.REVENUE, "Product Sales": LineType.REVENUE,
        "Sales and Marketing": LineType.UNCLASSIFIED,
    }


def test_type_map_still_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Revenue, Expense or Unclassified"):
        cli._parse_type_map(b'{"Rent": "overhead"}')


# --- Output paths that differ only by case or Unicode form are the same file on many systems ---


@pytest.mark.parametrize("second", ["out/report.md", "out/REPORT.MD", "OUT/Report.md"])
def test_outputs_differing_only_in_case_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], second: str,
) -> None:
    (tmp_path / "out").mkdir()
    source = tmp_path / "in.csv"
    source.write_text("Line Item,Type,Budget,Actual\nRent,Expense,100,90\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        cli.main([
            str(source), *BASE, "-o", str(tmp_path / "out" / "Report.md"),
            "--audit-json", str(tmp_path / second),
        ])
    assert exit_info.value.code == 2
    assert "must be distinct" in capsys.readouterr().err


# --- Command-line data errors are one clear line, not a usage banner ---


def test_data_errors_print_one_line_without_the_usage_banner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "in.csv"
    source.write_text("Line Item,Type,Budget,Actual\nRent,Expense,100,oops\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        cli.main([str(source), *BASE])
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith("variance-agent: error: ")
    assert "usage:" not in err and err.count("\n") == 1


def test_bad_arguments_still_show_usage(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--no-such-flag"])
    assert "usage:" in capsys.readouterr().err


def test_check_only_summary_uses_singular_and_plural_correctly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "in.csv"
    source.write_text("Line Item,Type,Budget,Actual\nRent,Expense,100,150\n", encoding="utf-8")
    assert cli.main([str(source), *BASE, "--check-only"]) == 0
    out = capsys.readouterr().out
    assert "1 row, 1 material variance, 0 Unclassified, 0 warnings" in out


# --- Invisible characters stay visible in reports and errors ---


@pytest.mark.parametrize(
    ("char", "escape"),
    [("​", "\\u200b"), ("⁠", "\\u2060"), ("﻿", "\\ufeff"), ("­", "\\u00ad"),
     ("\U000e0041", "\\U000e0041")],
)
def test_invisible_format_characters_are_escaped(char: str, escape: str) -> None:
    assert display_text(f"Rent{char}Expense") == f"Rent{escape}Expense"


def test_joiners_used_in_real_scripts_are_left_alone() -> None:
    assert display_text("می‌خواهم") == "می‌خواهم"


# --- Plain-language error rewriting keeps the user's own words ---


def test_summary_errors_keep_multiword_names() -> None:
    cleaned = plain_analysis_error(
        "ValueError: Summary 'Total Operating Expenses' does not reconcile to Expense detail rows; "
        "check for missing or overlapping data."
    )
    assert cleaned.startswith("Summary total for 'Total Operating Expenses' does not match the sum of its Expense")


def test_names_with_underscores_and_double_hyphens_are_not_rewritten() -> None:
    cleaned = plain_analysis_error("ValueError: Type map value for 'sales_tax' must be Revenue or Expense.")
    assert "'sales_tax'" in cleaned
    cleaned = plain_analysis_error("ValueError: Row 3: Q3--Q4 adjustments is not numeric")
    assert "Q3--Q4 adjustments" in cleaned


def test_internal_field_names_and_flags_are_still_made_plain() -> None:
    cleaned = plain_analysis_error("ValueError: Row Kind for 'line_item' is invalid; supply an exact --sheet name.")
    assert "'line item'" in cleaned or "line_item" not in cleaned
    assert "--sheet" not in cleaned


# --- Cover and notes worksheets are recognised by their whole name ---


def test_price_index_is_a_data_sheet_but_index_is_a_cover() -> None:
    header: list[list[object]] = [["Line Item", "Budget", "Actual"], ["Rent", 1, 2]]
    ranked = {s.name: s for s in rank_workbook_sheets(
        [("Price Index", header), ("Index", header), ("Cover Page", header), ("Notes", header)]
    )}
    assert "cover page or notes" not in ranked["Price Index"].rationale
    for name in ("Index", "Cover Page", "Notes"):
        assert "cover page or notes" in ranked[name].rationale
    assert ranked["Price Index"].score > ranked["Index"].score


def test_hidden_worksheets_do_not_win_automatically(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    from variance_agent.intake import read_input_assisted

    workbook = openpyxl.Workbook()
    old = workbook.active
    old.title = "OLD DRAFT"
    final = workbook.create_sheet("Final")
    for sheet, actual in ((old, 5), (final, 90)):
        sheet.append(["Line Item", "Type", "Budget", "Actual"])
        sheet.append(["Rent", "Expense", 100, actual])
        sheet.append(["Sales", "Revenue", 200, 210])
    old.sheet_state = "hidden"
    buffer = io.BytesIO()
    workbook.save(buffer)

    result = read_input_assisted(buffer.getvalue(), ".xlsx", filename="book.xlsx")
    assert not result.has_fatal_errors
    assert result.sheet_name == "Final"
    assert result.rows[0]["actual"] == Decimal("90")
    assert any("Selected worksheet 'Final'" in note for note in result.visible_transformations)
