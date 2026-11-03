"""X45: Budget and Actual headings that name different units refuse instead of sharing one multiplier (fictional data)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.intake import read_input_assisted

THOUSANDS_TITLE = "Fictional Co Q3 2026 ($ in thousands)\n"


def _read(budget: str, actual: str, *, title: str = "", values: tuple[str, str] = ("250", "275")):  # type: ignore[no-untyped-def]
    data = f"{title}Line Item,{budget},{actual}\nFictional Sales,{values[0]},{values[1]}\n".encode("utf-8")
    return read_input_assisted(data, ".csv", filename="units.csv")


@pytest.mark.parametrize(("budget", "actual", "message"), [
    ("Budget ($000)", "Actual ($M)",
     "'Budget ($000)' is in thousands and 'Actual ($M)' is in millions. Change one column so both use the same unit, "
     "then upload the file again."),
    ("Budget ($M)", "Actual ($000)",
     "'Budget ($M)' is in millions and 'Actual ($000)' is in thousands. Change one column so both use the same unit, "
     "then upload the file again."),
    ("Budget ($000)", "Actual ($)",
     "'Budget ($000)' is in thousands, but 'Actual ($)' names no unit, so I can't tell what 'Actual ($)' is in. Give both headings "
     "the same unit, such as ($000), then upload the file again."),
    ("Budget ($000)", "Actual",
     "'Budget ($000)' is in thousands, but 'Actual' names no unit, so I can't tell what 'Actual' is in. Give both headings "
     "the same unit, such as ($000), then upload the file again."),
    ("Budget", "Actual (bn)",
     "'Budget' names no unit, but 'Actual (bn)' is in billions, so I can't tell what 'Budget' is in. Give both headings the "
     "same unit, such as (bn), then upload the file again."),
])
def test_headings_in_different_units_refuse(budget: str, actual: str, message: str) -> None:
    result = _read(budget, actual)
    assert result.has_fatal_errors and not result.rows
    assert result.fatal_error_message == message


@pytest.mark.parametrize(("budget", "actual", "multiplier"), [
    ("Budget ($000)", "Actual ($000)", Decimal("1000")),
    ("Budget ($K)", "Actual (in thousands)", Decimal("1000")),
    ("Budget ($M)", "Actual ($mm)", Decimal("1000000")),
    ("Budget (USD m)", "Actual (USD m)", Decimal("1000000")),
    ("Budget ($)", "Actual", Decimal("1")),
    ("Budget (USD)", "Actual (USD)", Decimal("1")),
])
def test_headings_in_one_unit_scale_by_it(budget: str, actual: str, multiplier: Decimal) -> None:
    result = _read(budget, actual)
    assert not result.has_fatal_errors, result.fatal_error_message
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (250 * multiplier, 275 * multiplier)
    assert result.detected_unit_multiplier == multiplier


def test_a_title_caption_over_bare_headings_scales_as_before() -> None:
    result = _read("Budget", "Actual", title=THOUSANDS_TITLE)
    assert not result.has_fatal_errors, result.fatal_error_message
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal("250000"), Decimal("275000"))


def test_a_title_caption_against_a_headings_own_unit_refuses() -> None:
    result = _read("Budget", "Actual ($M)", title=THOUSANDS_TITLE)
    assert result.has_fatal_errors and result.fatal_error_message == (
        "'Budget' is in thousands, as the title says, and 'Actual ($M)' is in millions. Change one column so both use "
        "the same unit, then upload the file again.")


def test_a_headings_own_unit_wins_over_the_title() -> None:
    result = _read("Budget ($000)", "Actual ($000)", title="Fictional Co Q3 2026 ($ in millions)\n")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert (result.rows[0]["budget"], result.rows[0]["actual"]) == (Decimal("250000"), Decimal("275000"))


def test_the_command_line_refuses_and_writes_no_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "a1.csv"
    source.write_text("Line Item,Type,Budget ($000),Actual ($M)\nFictional Sales,Revenue,250,0.275\n", encoding="utf-8")
    report = tmp_path / "report.md"
    with pytest.raises(SystemExit) as stop:
        cli.main([str(source), "--assisted", "--period", "Oct 2026", "--dollar-threshold", "1",
                  "--percent-threshold", "1", "-o", str(report)])
    assert stop.value.code == 2
    assert "'Budget ($000)' is in thousands and 'Actual ($M)' is in millions." in capsys.readouterr().err
    assert not report.exists()


def test_one_half_of_a_pair_scales_by_its_own_heading() -> None:
    """A two-file pair's half has a placeholder for the other column, which names no unit of its own."""
    from variance_agent.intake import CanonicalRole
    result = read_input_assisted(b"Line Item,Budget ($000)\nFictional Sales,250\n", ".csv", filename="budget.csv",
                                 missing_column=CanonicalRole.ACTUAL)
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.half_filled and result.rows[0]["budget"] == Decimal("250000")
