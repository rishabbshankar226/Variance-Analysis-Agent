"""X49: the amounts take a unit only from their own headings or the title, never from another column's heading.

Every file here is fictional.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.intake import read_input_assisted

TITLE = "Fictional Co Q3 2026 ($ in thousands)\n"


def _read(header: str, row: str, *, title: str = ""):  # type: ignore[no-untyped-def]
    return read_input_assisted(f"{title}{header}\n{row}\n".encode("utf-8"), ".csv", filename="units.csv")


@pytest.mark.parametrize(("other", "word", "example"), [
    ("Headcount (000s)", "thousands", "($000)"),
    ("Variance ($000)", "thousands", "($000)"),
    ("Notes ($ in millions)", "millions", "($M)"),
])
def test_a_unit_only_another_heading_names_refuses(other: str, word: str, example: str) -> None:
    result = _read(f"Line Item,Budget,Actual,{other}", "Fictional Sales,250,275,1")
    assert result.has_fatal_errors and not result.rows
    assert result.fatal_error_message == (
        f"'{other}' names {word}, but 'Budget' and 'Actual' name no unit, so I can't tell whether the amounts are in "
        f"{word}. Give the 'Budget' and 'Actual' headings their unit, such as 'Budget {example}', or put a caption "
        f"such as ($ in {word}) above the table, then upload the file again.")


@pytest.mark.parametrize("other", ["Headcount (000s)", "Variance ($000)"])
def test_a_title_caption_scales_whatever_another_heading_names(other: str) -> None:
    result = _read(f"Line Item,Budget,Actual,{other}", "Fictional Sales,250,275,1", title=TITLE)
    assert not result.has_fatal_errors, result.fatal_error_message
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal("250000"), Decimal("275000"))


def test_no_unit_anywhere_reads_unscaled() -> None:
    result = _read("Line Item,Budget,Actual,Headcount", "Fictional Sales,250000,275000,12")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal("250000"), Decimal("275000"))


def test_amount_headings_with_their_own_unit_scale_by_it() -> None:
    result = _read("Line Item,Budget ($000),Actual ($000),Headcount (000s)", "Fictional Sales,250,275,1")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal("250000"), Decimal("275000"))


def test_a_bare_amount_heading_takes_no_unit_from_another_heading() -> None:
    result = _read("Line Item,Budget ($000),Actual,Headcount (000s)", "Fictional Sales,250,275,1")
    assert result.has_fatal_errors and result.fatal_error_message == (
        "'Budget ($000)' is in thousands, but 'Actual' names no unit, so I can't tell what 'Actual' is in. Give both "
        "headings the same unit, such as ($000), then upload the file again.")


def test_the_command_line_refuses(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "h1.csv"
    source.write_text("Line Item,Type,Budget,Actual,Headcount (000s)\nFictional Sales,Revenue,250000,275000,1.2\n",
                      encoding="utf-8")
    with pytest.raises(SystemExit) as stop:
        cli.main([str(source), "--assisted", "--period", "Q3 2026", "--dollar-threshold", "1", "--percent-threshold", "1"])
    assert stop.value.code == 2
    assert "'Headcount (000s)' names thousands, but 'Budget' and 'Actual' name no unit" in capsys.readouterr().err
