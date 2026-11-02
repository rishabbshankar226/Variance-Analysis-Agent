"""X42: on the measure path, the report and the audit say how assisted intake read the file (fictional files)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_percent_formats import BOTH, _book
from variance_agent import cli
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Session

SHOWN = "Gross margin: read Budget and Actual as the percentages Excel shows (number format '0.0%')."
ONE_SHOWN = "Gross margin: read Actual as the percentage Excel shows (number format '0.0%')."
BARE = "Read bare Percent values as points."


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], data: bytes, *extra: str) -> tuple[str, list[str]]:
    source = tmp_path / "kpis.xlsx"
    source.write_bytes(data)
    report, audit = tmp_path / "report.md", tmp_path / "audit.json"
    code = cli.main([str(source), "--period", "Q3 2026", "--dollar-threshold", "10000", "--percent-threshold", "5",
                     "--bps-threshold", "50", "--percent-values", "points", "-o", str(report),
                     "--audit-json", str(audit), *extra])
    assert code == 0, capsys.readouterr().err
    return report.read_text(encoding="utf-8"), list(json.loads(audit.read_text(encoding="utf-8"))["inferences"])


def _read_section(report: str) -> list[str]:
    section = report.split("## How the file was read\n", 1)[1].split("\n## ", 1)[0]
    return [line[2:] for line in section.splitlines() if line.startswith("- ")]


def test_the_report_and_audit_say_the_cells_were_read_as_excel_shows_them(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report, inferences = _run(tmp_path, capsys, _book(BOTH), "--assisted")
    notes = _read_section(report)
    assert SHOWN in notes and SHOWN in inferences
    assert BARE not in notes and BARE not in inferences
    # Intake's restatements of a row's own Measure, Better and % reading are not said twice.
    assert notes.count("Gross margin: read Measure as Percent.") == 1
    assert not any(note.startswith("Gross margin: read Better as") for note in notes)


def test_a_bare_rate_beside_a_formatted_one_keeps_the_bare_rate_note(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report, inferences = _run(tmp_path, capsys, _book({"F3": "0.0%"}), "--assisted")
    assert ONE_SHOWN in _read_section(report) and ONE_SHOWN in inferences
    assert BARE in _read_section(report) and BARE in inferences


def test_intake_notes_come_first_in_intakes_order(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, inferences = _run(tmp_path, capsys, _book(BOTH), "--assisted")
    assert inferences.index(SHOWN) < inferences.index("Gross margin: read Measure as Percent.")


def test_the_chat_carries_the_note_into_the_analysis() -> None:
    session = Session()
    handle_upload(session, _book(BOTH), "kpis.xlsx")
    for answer in ("Looks right", "Q3 2026", "$10,000 or 5%", "USD", "50"):
        handle_message(session, answer)
    assert session.result is not None
    assert SHOWN in session.result.warnings
    assert not any(warning.startswith("Read bare Percent values") for warning in session.result.warnings)


def test_a_strict_run_adds_no_intake_notes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "kpis.csv"
    source.write_text("Line Item,Type,Measure,Better,Budget,Actual\nProduct Revenue,Revenue,Currency,,1200000,1350000\n"
                      "Gross margin,,Percent,Higher,40,42.5\n", encoding="utf-8")
    audit = tmp_path / "audit.json"
    code = cli.main([str(source), "--period", "Q3 2026", "--dollar-threshold", "10000", "--percent-threshold", "5",
                     "--bps-threshold", "50", "--percent-values", "points", "-o", str(tmp_path / "r.md"),
                     "--audit-json", str(audit)])
    assert code == 0, capsys.readouterr().err
    inferences = json.loads(audit.read_text(encoding="utf-8"))["inferences"]
    assert BARE in inferences
    assert not any("Excel shows" in note or note.startswith("Read header row") for note in inferences)
