"""C1: strict and assisted intake agree on formulas Excel never calculated in a computed column (fictional books)."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from variance_agent import cli

NUMBERS = ["--period", "Q3", "--dollar-threshold", "1", "--percent-threshold", "1"]


def _book(path: Path, *, formula_column: str) -> Path:
    """Line Item, Type, Budget, Actual, Var $, Notes; openpyxl saves formulas with no cached result."""
    book = Workbook()
    sheet = book.active
    sheet.append(["Line Item", "Type", "Budget", "Actual", "Var $", "Notes"])
    for row, (label, kind, budget, actual) in enumerate(
            [("Fictional Sales", "Revenue", 100, 120), ("Fictional Rent", "Expense", 50, 55)], start=2):
        sheet.append([label, kind, budget, actual, actual - budget, "fictional"])
        sheet[f"{formula_column}{row}"] = f"=D{row}-C{row}" if formula_column != "D" else f"=C{row}+20"
    book.save(path)
    return path


@pytest.mark.parametrize("mode", [[], ["--assisted"]], ids=["strict", "assisted"])
def test_unsaved_formulas_in_a_computed_column_read_in_both_modes(tmp_path: Path, mode: list[str]) -> None:
    report = tmp_path / "r.md"
    assert cli.main([str(_book(tmp_path / "b.xlsx", formula_column="E")), *mode, *NUMBERS, "-o", str(report)]) == 0
    assert "| Fictional Sales | Revenue | $100.00 | $120.00 | $20.00 | 20.0% | F |" in report.read_text(encoding="utf-8")


@pytest.mark.parametrize("mode", [[], ["--assisted"]], ids=["strict", "assisted"])
def test_an_unsaved_formula_in_an_amount_column_refuses_in_both_modes(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: list[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main([str(_book(tmp_path / "b.xlsx", formula_column="D")), *mode, *NUMBERS, "-o", str(tmp_path / "r.md")])
    assert "These cells hold formulas that Excel never calculated" in capsys.readouterr().err.replace("\n", " ")


def test_strict_still_stops_on_an_unsaved_formula_in_a_column_it_may_read(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main([str(_book(tmp_path / "b.xlsx", formula_column="F")), *NUMBERS, "-o", str(tmp_path / "r.md")])
    assert "Notes column" in capsys.readouterr().err.replace("\n", " ")
