"""X18: the comparison path knows every header name assisted intake knows (fictional data)."""

from __future__ import annotations

from pathlib import Path

from variance_agent import cli, comparisons, intake

NUMBERS = ["--assisted", "--compare-to", "budget,forecast", "--period", "Q3", "--dollar-threshold", "1",
           "--percent-threshold", "1"]


def _report(tmp_path: Path, text: str) -> str:
    data, report = tmp_path / "t.csv", tmp_path / "r.md"
    data.write_text(text, encoding="utf-8")
    assert cli.main([str(data), *NUMBERS, "-o", str(report)]) == 0
    return report.read_text(encoding="utf-8")


def test_a_description_column_names_the_lines(tmp_path: Path) -> None:
    text = _report(tmp_path, "Description,Budget,Forecast,Actual\nFictional Sales,100,110,120\nFictional Rent,50,55,60\n")
    assert "Fictional Sales" in text and "Fictional Rent" in text


def test_a_ytd_actual_column_is_the_actual(tmp_path: Path) -> None:
    text = _report(tmp_path, "Line Item,Budget,Forecast,YTD Actual\nFictional Sales,100,110,120\n")
    assert "Fictional Sales" in text


def test_a_known_name_keeps_its_precedence(tmp_path: Path) -> None:
    text = _report(tmp_path, "Account,Description,Budget,Forecast,Actual\nACC-1,Fictional Sales,100,110,120\n")
    assert "ACC-1" in text


def test_the_comparison_names_match_intake_s() -> None:
    assert set(comparisons._LINE_ITEM_KEYS) | set(comparisons._MORE_LINE_ITEM_KEYS) == intake._LINE_ITEM_SYNONYMS
    assert set(comparisons._ACTUAL_KEYS) | set(comparisons._MORE_ACTUAL_KEYS) == intake._ACTUAL_SYNONYMS
