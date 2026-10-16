"""Reject unsafe OOXML archives before the worksheet loader can expand them."""

from __future__ import annotations

import io
import struct
from decimal import Decimal
from pathlib import Path
from typing import NoReturn
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

import variance_agent.parsing as parsing
from variance_agent.analysis import analyze_rows
from variance_agent.cli import main
from variance_agent.models import AnalysisConfig


MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2048
MAX_ROWS = 100_000
SHEET_MEMBER = "xl/worksheets/sheet1.xml"
SHEET_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
UNSAFE_CASES = (
    "physical_row_index",
    "physical_cell_row_index",
    "physical_column_index",
    "xml_dtd",
    "xml_depth",
    "xml_entity",
    "utf16_xml_entity",
    "workbook_xml_dtd",
    "duplicate_member",
    "too_many_members",
    "declared_uncompressed_total",
)


def _workbook_members() -> list[tuple[str, bytes]]:
    capture = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Line Item", "Budget", "Actual"])
    sheet.append(["Sales", 100, 120])
    try:
        workbook.save(capture)
    finally:
        workbook.close()
    with ZipFile(io.BytesIO(capture.getvalue())) as archive:
        return [(item.filename, archive.read(item)) for item in archive.infolist()]


def _encode_archive(members: list[tuple[str, bytes]]) -> bytes:
    capture = io.BytesIO()
    with ZipFile(capture, "w", ZIP_DEFLATED) as archive:
        for name, content in members:
            archive.writestr(name, content)
    return capture.getvalue()


def _worksheet_coordinate(data: bytes, case: str) -> bytes:
    worksheet = ElementTree.fromstring(data)
    rows = worksheet.findall(f"{SHEET_NAMESPACE}sheetData/{SHEET_NAMESPACE}row")
    assert len(rows) == 2
    if case == "physical_row_index":
        rows[1].set("r", str(MAX_ROWS + 1))
        for column, cell in zip("ABC", rows[1]):
            cell.set("r", f"{column}{MAX_ROWS + 1}")
    elif case == "physical_cell_row_index":
        # The row tag remains small; cell coordinates must be checked as well.
        rows[1][0].set("r", f"A{MAX_ROWS + 1}")
    elif case == "physical_column_index":
        rows[1][0].set("r", "IW2")  # IW is column 257, immediately beyond the limit.
    else:
        raise AssertionError(f"Unexpected coordinate case: {case}")
    return ElementTree.tostring(worksheet, encoding="utf-8")


def _oversized_declared_member(data: bytes) -> bytes:
    """Forge only a central-directory size, without creating a large payload."""
    modified = bytearray(data)
    central_offset = modified.find(b"PK\x01\x02")
    assert central_offset >= 0
    struct.pack_into("<I", modified, central_offset + 24, MAX_ARCHIVE_BYTES + 1)
    return bytes(modified)


def _unsafe_workbook(case: str) -> bytes:
    members = _workbook_members()
    contents = dict(members)
    if case.startswith("physical_"):
        contents[SHEET_MEMBER] = _worksheet_coordinate(contents[SHEET_MEMBER], case)
    elif case == "xml_dtd":
        contents[SHEET_MEMBER] = b"<!DOCTYPE worksheet>" + contents[SHEET_MEMBER]
    elif case == "xml_depth":
        extension = (
            b'<extLst><ext uri="audit"><guard xmlns="urn:variance-audit:depth">'
            + b"<level>" * 256
            + b"</level>" * 256
            + b"</guard></ext></extLst>"
        )
        assert contents[SHEET_MEMBER].endswith(b"</worksheet>")
        contents[SHEET_MEMBER] = contents[SHEET_MEMBER].replace(
            b"</worksheet>", extension + b"</worksheet>"
        )
    elif case in {"xml_entity", "utf16_xml_entity"}:
        xml = (
            b'<!DOCTYPE worksheet [<!ENTITY audit "Sales">]>'
            + contents[SHEET_MEMBER].replace(b">Sales<", b">&audit;<")
        )
        if case == "utf16_xml_entity":
            xml = ('<?xml version="1.0" encoding="UTF-16"?>' + xml.decode("utf-8")).encode(
                "utf-16"
            )
        contents[SHEET_MEMBER] = xml
    elif case == "workbook_xml_dtd":
        contents["xl/workbook.xml"] = b"<!DOCTYPE workbook>" + contents["xl/workbook.xml"]
    elif case == "too_many_members":
        for index in range(MAX_ARCHIVE_MEMBERS + 1 - len(contents)):
            contents[f"padding/{index}.bin"] = b""
    elif case not in {"duplicate_member", "declared_uncompressed_total"}:
        raise AssertionError(f"Unexpected unsafe workbook case: {case}")

    if case == "duplicate_member":
        with pytest.warns(UserWarning, match="Duplicate name"):
            return _encode_archive(list(contents.items()) + [(SHEET_MEMBER, contents[SHEET_MEMBER])])
    archive = _encode_archive(list(contents.items()))
    return _oversized_declared_member(archive) if case == "declared_uncompressed_total" else archive


def _forbid_workbook_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_loader(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("Unsafe OOXML reached the worksheet loader before rejection")

    monkeypatch.setattr(parsing, "_excel_loader", lambda: forbidden_loader)


@pytest.mark.parametrize("case", UNSAFE_CASES)
def test_unsafe_excel_is_rejected_before_workbook_loading(
    case: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _unsafe_workbook(case)
    _forbid_workbook_loading(monkeypatch)
    with pytest.raises(ValueError):
        parsing.load_input(archive, ".xlsx", source_name=f"{case}.xlsx")


@pytest.mark.parametrize("case", UNSAFE_CASES)
def test_cli_rejects_unsafe_excel_without_overwriting_outputs(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / f"{case}.xlsx"
    source.write_bytes(_unsafe_workbook(case))
    report, audit = tmp_path / "report.md", tmp_path / "audit.json"
    report.write_bytes(b"previous report\n")
    audit.write_bytes(b"previous audit\n")
    _forbid_workbook_loading(monkeypatch)

    with pytest.raises(SystemExit) as error:
        main(
            [
                str(source),
                "--period", "Q3",
                "--dollar-threshold", "1",
                "--percent-threshold", "5",
                "--output", str(report),
                "--audit-json", str(audit),
            ]
        )

    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err
    assert report.read_bytes() == b"previous report\n"
    assert audit.read_bytes() == b"previous audit\n"


def test_large_producer_dimensions_do_not_expand_small_physical_sheet() -> None:
    members = dict(_workbook_members())
    worksheet = ElementTree.fromstring(members[SHEET_MEMBER])
    dimension = worksheet.find(f"{SHEET_NAMESPACE}dimension")
    assert dimension is not None
    dimension.set("ref", "A1:XFD1048576")
    members[SHEET_MEMBER] = ElementTree.tostring(worksheet, encoding="utf-8")

    parsed = parsing.load_input(_encode_archive(list(members.items())), ".xlsx")

    assert parsed.rows == [{"line_item": "Sales", "budget": 100, "actual": 120}]


def test_custom_worksheet_location_cannot_bypass_physical_row_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    members = dict(_workbook_members())
    custom_member = "custom/ledger.xml"
    members[custom_member] = _worksheet_coordinate(
        members.pop(SHEET_MEMBER), "physical_row_index"
    )
    relationships = ElementTree.fromstring(members["xl/_rels/workbook.xml.rels"])
    sheet_relationships = [
        relation for relation in relationships
        if relation.get("Type", "").endswith("/worksheet")
    ]
    assert len(sheet_relationships) == 1
    sheet_relationships[0].set("Target", f"/{custom_member}")
    members["xl/_rels/workbook.xml.rels"] = ElementTree.tostring(
        relationships, encoding="utf-8"
    )
    content_types = ElementTree.fromstring(members["[Content_Types].xml"])
    sheet_types = [
        item for item in content_types if item.get("PartName") == f"/{SHEET_MEMBER}"
    ]
    assert len(sheet_types) == 1
    sheet_types[0].set("PartName", f"/{custom_member}")
    members["[Content_Types].xml"] = ElementTree.tostring(content_types, encoding="utf-8")
    _forbid_workbook_loading(monkeypatch)

    with pytest.raises(ValueError):
        parsing.load_input(_encode_archive(list(members.items())), ".xlsx")


def test_non_cell_numeric_xml_cannot_overwrite_actual_amount() -> None:
    members = dict(_workbook_members())
    worksheet = ElementTree.fromstring(members[SHEET_MEMBER])
    stray_value = ElementTree.SubElement(worksheet, f"{SHEET_NAMESPACE}v")
    stray_value.text = "999"
    members[SHEET_MEMBER] = ElementTree.tostring(worksheet, encoding="utf-8")

    parsed = parsing.load_input(_encode_archive(list(members.items())), ".xlsx")
    result = analyze_rows(
        parsed.rows, AnalysisConfig("Q3", Decimal("1"), Decimal("0.05"))
    )

    assert result.rows[0].actual == Decimal("120")
    assert result.revenue.actual == Decimal("120")


def test_out_of_order_physical_cells_rejected_before_workbook_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    members = dict(_workbook_members())
    worksheet = ElementTree.fromstring(members[SHEET_MEMBER])
    header = worksheet.find(f"{SHEET_NAMESPACE}sheetData/{SHEET_NAMESPACE}row")
    assert header is not None
    assert [cell.get("r") for cell in header] == ["A1", "B1", "C1"]
    header[:] = [header[0], header[2], header[1]]
    members[SHEET_MEMBER] = ElementTree.tostring(worksheet, encoding="utf-8")
    _forbid_workbook_loading(monkeypatch)

    with pytest.raises(ValueError):
        parsing.load_input(_encode_archive(list(members.items())), ".xlsx")
