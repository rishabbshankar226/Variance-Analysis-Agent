"""X13: no output may overwrite a file the run reads, including the second files (fictional files)."""

from __future__ import annotations

from pathlib import Path

import pytest

from variance_agent import cli

ANALYSTS = Path(__file__).resolve().parent / "fixtures" / "analysts"
REFUSAL = "Input, type-map, report, audit, and workbook output paths must be distinct."
NUMBERS = ["--period", "Q3", "--dollar-threshold", "1", "--percent-threshold", "1"]


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    actual, budget = tmp_path / "act.csv", tmp_path / "bud.csv"
    actual.write_text("Line Item,Actual\nFictional Sales,120\n", encoding="utf-8")
    budget.write_text("Line Item,Budget\nFictional Sales,100\n", encoding="utf-8")
    return actual, budget


def test_the_report_may_not_overwrite_the_compare_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    actual, budget = _pair(tmp_path)
    before = budget.read_bytes()
    with pytest.raises(SystemExit):
        cli.main([str(actual), "--assisted", "--compare-file", str(budget), *NUMBERS, "-o", str(budget)])
    assert REFUSAL in capsys.readouterr().err
    assert budget.read_bytes() == before


@pytest.mark.parametrize("flag", ["--ltm-from", "--metrics", "--panel"])
def test_the_audit_may_not_overwrite_another_input(tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str) -> None:
    actual, other = _pair(tmp_path)
    before = other.read_bytes()
    with pytest.raises(SystemExit):
        cli.main([str(actual), "--assisted", flag, str(other), *NUMBERS, "--audit-json", str(other)])
    assert REFUSAL in capsys.readouterr().err
    assert other.read_bytes() == before


def test_a_fresh_output_path_still_writes(tmp_path: Path) -> None:
    actual, budget = _pair(tmp_path)
    assert cli.main([str(actual), "--assisted", "--compare-file", str(budget), *NUMBERS,
                     "-o", str(tmp_path / "r.md")]) == 0
