"""M4: a filing column's duration shows in display text, and every key keeps the column's label (fictional 10-Q)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fixtures.ixbrl.build_ixbrl import income_filing
from variance_agent import cli
from variance_agent.chat.handlers import handle_upload
from variance_agent.chat.session import Session
from variance_agent.intake import read_input_assisted
from variance_agent.ixbrl import read_statements

QUARTER = Path(__file__).resolve().parent / "fixtures" / "analysts" / "hal-20260328.htm"
THREE = "Condensed Consolidated Statements of Operations, 3 Months Ended"
SIX = "Condensed Consolidated Statements of Operations, 6 Months Ended"


def test_the_readers_note_names_each_columns_duration() -> None:
    notes = {s.name: s.notes for s in read_statements(QUARTER.read_bytes(), QUARTER.name)}
    assert "Read the column for the 3 months ended 2026-03-28 as Mar 2026" in notes[THREE]
    assert "Read the column for the 6 months ended 2025-03-29 as Mar 2025" in notes[SIX]


@pytest.mark.parametrize(("sheet", "months"), [(THREE, 3), (SIX, 6)])
def test_the_same_label_names_each_statements_own_duration(sheet: str, months: int) -> None:
    result = read_input_assisted(QUARTER.read_bytes(), ".htm", filename=QUARTER.name, sheet=sheet)
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.comparison_label == "Mar 2025"
    assert result.period_names == {"Mar 2026": f"{months} months ended Mar 2026",
                                   "Mar 2025": f"{months} months ended Mar 2025"}
    assert (f"Comparing {months} months ended Mar 2026 against {months} months ended Mar 2025 (prior period)."
            in result.visible_transformations)


def test_an_annual_filing_keeps_its_fiscal_year_labels() -> None:
    result = read_input_assisted(income_filing(), ".htm", filename="hal-20250927.htm")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.period_names == {}
    assert not any("months ended" in note for note in [*result.visible_transformations, *result.reader_notes])


def test_a_spreadsheet_has_no_period_names() -> None:
    data = b"Line Item,Type,Budget,Actual\nFictional Sales,Revenue,100,110\n"
    assert read_input_assisted(data, ".csv", filename="plan.csv").period_names == {}


def test_the_chat_summary_names_the_durations() -> None:
    reply = handle_upload(Session(), QUARTER.read_bytes(), QUARTER.name)
    text = reply.text.replace("\\", "")
    assert "Prior Period (3 months ended Mar 2025) from 'Mar 2025'" in text
    assert "Actual (3 months ended Mar 2026) from 'Mar 2026'" in text


def test_the_report_names_the_duration_and_every_key_keeps_the_label(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = {name: tmp_path / name for name in ("r.md", "a.json", "long.csv", "long.jsonl")}
    code = cli.main([str(QUARTER), "--assisted", "--sheet", SIX, "--period", "Q2 FY2026", "--dollar-threshold", "1",
                     "--percent-threshold", "1", "-o", str(out["r.md"]), "--audit-json", str(out["a.json"]),
                     "--long-output", str(out["long.csv"]), "--long-output-jsonl", str(out["long.jsonl"])])
    assert code == 0, capsys.readouterr().err
    assert "Prior Period (6 months ended Mar 2025)" in out["r.md"].read_text(encoding="utf-8")
    audit = json.loads(out["a.json"].read_text(encoding="utf-8"))
    assert audit["comparison"]["label"] == "Mar 2025"
    for name in ("long.csv", "long.jsonl"):
        assert "months ended" not in out[name].read_text(encoding="utf-8")
