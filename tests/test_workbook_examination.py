"""The workbook examination summary and audit 1.9 (PLAN.md, Decision 14).

A clean workbook keeps today's stderr, chat summary and 1.7 audit byte for byte; a workbook
with a finding shows the examination and records it in audit 1.9. Every workbook here is built
in the test and every value is fictional.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from jsonschema import Draft202012Validator, ValidationError
from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from variance_agent import cli
from variance_agent.chat.handlers import handle_upload
from variance_agent.chat.session import Session
from variance_agent.intake import format_intake_summary, read_input_assisted

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "audit-1.9.schema.json").read_text(encoding="utf-8"))


def _book(build: Callable[[Worksheet], None] | None = None, *, rows: list[list[object]] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Plan"
    for row in rows or [["Line Item", "Budget", "Actual", "Type", "Notes"], ["Revenue", 100, 110, "Revenue", "ok"],
                        ["Draft line", 5, 5, "Expense", ""], ["COGS", 40, 45, "Expense", ""]]:
        sheet.append(row)
    if build is not None:
        build(sheet)
    capture = io.BytesIO()
    workbook.save(capture)
    data = capture.getvalue()
    # Saved results as Excel would write them, so the sheet's formulas (if any) read.
    return _calm(data)


def _calm(data: bytes, extra: dict[str, bytes] | None = None, edits: list[tuple[str, bytes, bytes]] = ()) -> bytes:  # type: ignore[assignment]
    with ZipFile(io.BytesIO(data)) as archive:
        parts = {item.filename: archive.read(item) for item in archive.infolist()}
    parts["xl/workbook.xml"] = parts["xl/workbook.xml"].replace(b'fullCalcOnLoad="1"', b'fullCalcOnLoad="0"')
    for member, old, new in edits:
        assert old in parts[member]
        parts[member] = parts[member].replace(old, new)
    parts.update(extra or {})
    capture = io.BytesIO()
    with ZipFile(capture, "w", ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return capture.getvalue()


def _cli(tmp_path: Path, data: bytes, *extra: str) -> tuple[dict[str, object], str]:
    path = tmp_path / "plan.xlsx"
    path.write_bytes(data)
    audit = tmp_path / "audit.json"
    assert cli.main([str(path), "--assisted", "--period", "X", "--dollar-threshold", "1", "--percent-threshold", "1",
                     "--audit-json", str(audit), "-o", str(tmp_path / "report.md"), *extra]) == 0
    return json.loads(audit.read_text(encoding="utf-8")), ""


def test_a_clean_workbook_has_no_findings_and_keeps_its_17_audit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = _book()
    result = read_input_assisted(data, ".xlsx", filename="plan.xlsx")
    assert result.workbook_examination is not None
    assert result.workbook_examination.findings == ()
    assert "noticed in the workbook" not in format_intake_summary(result)
    record, _ = _cli(tmp_path, data)
    assert record["schema_version"] == "1.7"
    assert "workbook" not in record
    assert "[workbook]" not in capsys.readouterr().err


def test_hidden_rows_are_a_finding_recorded_in_audit_19(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def build(sheet: Worksheet) -> None:
        sheet.row_dimensions[3].hidden = True
        sheet.column_dimensions["E"].hidden = True

    record, _ = _cli(tmp_path, _book(build), "--hidden-rows", "include")
    Draft202012Validator(SCHEMA).validate(record)
    assert record["schema_version"] == "1.9"
    workbook = record["workbook"]
    assert isinstance(workbook, dict)
    assert workbook["sheet"] == "Plan"
    assert workbook["sheets"] == [{"name": "Plan", "visibility": "visible"}]
    assert workbook["hidden_rows"] == [{"row": 3, "line_item": "Draft line", "collapsed": False}]
    assert workbook["hidden_rows_choice"] == "include"
    assert workbook["hidden_columns"] == ["E"]
    assert workbook["findings"] == ["hidden_rows"]
    assert workbook["reading_notes"] == ["Counted 1 row hidden in Excel: row 3 (Draft line)."]
    err = capsys.readouterr().err
    assert "[workbook] Hidden rows: row 3 (Draft line), counted." in err
    assert "[workbook] Hidden columns: E." in err


def test_error_results_and_unsaved_formulas_outside_the_read_are_findings() -> None:
    def build(sheet: Worksheet) -> None:
        sheet["E2"] = "=1/0"
        sheet["F2"] = "=B2*2"
        sheet["F1"] = "Var $"

    data = _calm(_book(build), edits=[("xl/worksheets/sheet1.xml", b'<c r="E2"><f>1/0</f><v /></c>',
                                       b'<c r="E2" t="e"><f>1/0</f><v>#DIV/0!</v></c>')])
    result = read_input_assisted(data, ".xlsx", filename="plan.xlsx")
    assert not result.has_fatal_errors, result.fatal_error_message
    exam = result.workbook_examination
    assert exam is not None
    assert exam.findings == ("error_cells", "unsaved_formulas")
    assert exam.error_cells == (("E2", "#DIV/0!"),)
    assert exam.unsaved_formulas == ("F2",)
    summary = format_intake_summary(result)
    assert "**What I noticed in the workbook:**" in summary
    assert "- Error results: E2 (#DIV/0!)." in summary
    assert "- Formulas without a saved result, not read: F2." in summary


def test_links_to_other_workbooks_are_a_finding() -> None:
    link = b'<externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
    data = _calm(_book(), extra={"xl/externalLinks/externalLink1.xml": link})
    exam = read_input_assisted(data, ".xlsx", filename="plan.xlsx").workbook_examination
    assert exam is not None
    assert exam.findings == ("external_links",)
    assert "Links to other workbooks: 1; the values saved in this file were read." in exam.lines()


def test_an_edgar_statement_read_is_recorded_as_its_document_kind(tmp_path: Path) -> None:
    from tests.test_excel_edgar_statement import _statement
    record, _ = _cli(tmp_path, _statement())
    Draft202012Validator(SCHEMA).validate(record)
    assert record["schema_version"] == "1.9"
    document = record["source"]["document"]  # type: ignore[index]
    assert document["kind"] == "edgar_xlsx"
    assert document["statement"] == "Consolidated Statements of Operations"
    assert document["sheet"] == "Consolidated Statements of Ope"
    assert record["workbook"]["findings"] == ["layout"]  # type: ignore[index]


def test_an_older_audit_version_refuses_a_workbook_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "plan.xlsx"
    path.write_bytes(_book(lambda sheet: setattr(sheet.row_dimensions[3], "hidden", True)))
    with pytest.raises(SystemExit) as stopped:
        cli.main([str(path), "--assisted", "--hidden-rows", "exclude", "--period", "X", "--dollar-threshold", "1",
                  "--percent-threshold", "1", "--audit-json", str(tmp_path / "a.json"), "--audit-schema-version", "1.7"])
    assert stopped.value.code == 2
    assert ("Audit schema 1.7 cannot record what the workbook examination found; use --audit-schema-version 1.9."
            in capsys.readouterr().err)


def test_the_chat_shows_the_examination_with_the_read_summary() -> None:
    session = Session()
    data = _calm(_book(), extra={"xl/externalLinks/externalLink1.xml": b"<externalLink/>"})
    response = handle_upload(session, data, "plan.xlsx")
    assert "**What I noticed in the workbook:**" in response.text
    assert "- Links to other workbooks: 1; the values saved in this file were read." in response.text


def test_the_19_workbook_group_is_closed(tmp_path: Path) -> None:
    def build(sheet: Worksheet) -> None:
        sheet.row_dimensions[3].hidden = True

    record, _ = _cli(tmp_path, _book(build), "--hidden-rows", "include")
    record["workbook"]["surprise"] = True  # type: ignore[index]
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(record)
