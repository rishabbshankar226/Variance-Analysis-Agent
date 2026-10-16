"""Bound OOXML expansion and retain numeric XML before binary-float conversion."""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from decimal import Decimal
from typing import BinaryIO, Protocol
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .limits import (
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_MEMBERS,
    MAX_CELLS,
    MAX_COLUMNS,
    MAX_NUMBER_LENGTH,
    MAX_ROWS,
    MAX_XML_DEPTH,
)

_CELL_REFERENCE = re.compile(r"([A-Z]{1,3})([1-9][0-9]{0,6})")
_SHEET_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class ExcelCell(Protocol):
    value: object
    coordinate: str
    data_type: str


class ExcelWorksheet(Protocol):
    title: str
    _worksheet_path: str

    def reset_dimensions(self) -> None: ...

    def iter_rows(self) -> Iterator[tuple[ExcelCell, ...]]: ...


class ExcelWorkbook(Protocol):
    active: ExcelWorksheet | None
    sheetnames: list[str]

    def __getitem__(self, key: str) -> ExcelWorksheet: ...

    def close(self) -> None: ...


class WorkbookLoader(Protocol):
    def __call__(
        self, source: BinaryIO, *, read_only: bool, data_only: bool
    ) -> ExcelWorkbook: ...


def _worksheet_numbers(xml: bytes) -> dict[str, str]:
    numbers: dict[str, str] = {}
    row_index = 0
    column_index = 0
    coordinate = ""
    numeric = False
    seen: set[str] = set()
    cells = 0
    depth = 0
    for event, element in ElementTree.iterparse(io.BytesIO(xml), events=("start", "end")):
        if event == "start":
            depth += 1
            if depth > MAX_XML_DEPTH:
                raise ValueError(f"Excel XML exceeds the supported depth ({MAX_XML_DEPTH}).")
        if event == "start" and element.tag == f"{_SHEET_NAMESPACE}row":
            previous = row_index
            row_index = int(element.get("r", str(row_index + 1)))
            if not previous < row_index <= MAX_ROWS:
                raise ValueError(f"Excel physical rows must increase within 1..{MAX_ROWS}.")
            column_index = 0
        elif event == "start" and element.tag == f"{_SHEET_NAMESPACE}c":
            previous_column = column_index
            cells += 1
            if cells > MAX_CELLS:
                raise ValueError(f"Excel worksheet exceeds the supported cell count ({MAX_CELLS}).")
            reference = element.get("r")
            if reference is None:
                column_index += 1
                # Numeric values in implicit cells are indexed below by row/column.
                coordinate = f"{row_index}:{column_index}"
            else:
                match = _CELL_REFERENCE.fullmatch(reference)
                if match is None:
                    raise ValueError("Excel cell contains an invalid physical coordinate.")
                column_index = 0
                for letter in match[1]:
                    column_index = column_index * 26 + ord(letter) - ord("A") + 1
                cell_row = int(match[2])
                if cell_row != row_index:
                    raise ValueError("Excel cell coordinate conflicts with its physical row.")
                coordinate = f"{row_index}:{column_index}"
            if not 1 <= row_index <= MAX_ROWS or not 1 <= column_index <= MAX_COLUMNS:
                raise ValueError(f"Excel physical coordinates exceed {MAX_ROWS} rows or "
                                 f"{MAX_COLUMNS} columns.")
            if column_index <= previous_column:
                raise ValueError("Excel physical cell columns must be strictly increasing.")
            if coordinate in seen:
                raise ValueError("Excel worksheet contains duplicate cell coordinates.")
            seen.add(coordinate)
            numeric = element.get("t", "n") == "n"
        elif event == "end" and element.tag == f"{_SHEET_NAMESPACE}v" and numeric:
            if element.text is not None:
                if len(element.text) > MAX_NUMBER_LENGTH:
                    raise ValueError("Excel numeric literal exceeds the supported length.")
                numbers[coordinate] = element.text
        elif event == "end" and element.tag == f"{_SHEET_NAMESPACE}c":
            numeric = False
        if event == "end":
            element.clear()
            depth -= 1
    return numbers


def inspect_archive(data: bytes) -> dict[str, dict[str, str]]:
    """Reject dangerous structures before openpyxl can expand physical cells."""
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValueError(f"Excel archive exceeds {MAX_ARCHIVE_MEMBERS} members.")
            if len({member.filename for member in members}) != len(members):
                raise ValueError("Excel archive contains duplicate member paths.")
            if sum(member.file_size for member in members) > MAX_ARCHIVE_BYTES:
                raise ValueError("Excel archive exceeds the 64 MiB expanded size limit.")
            worksheet_numbers: dict[str, dict[str, str]] = {}
            total_bytes = 0
            for member in members:
                with archive.open(member) as source:
                    content = source.read(MAX_ARCHIVE_BYTES - total_bytes + 1)
                total_bytes += len(content)
                if total_bytes > MAX_ARCHIVE_BYTES:
                    raise ValueError("Excel archive exceeds the 64 MiB expanded size limit.")
                if member.filename.lower().endswith((".xml", ".rels")):
                    # Removing NULs also detects declarations in UTF-16/UTF-32 XML.
                    declaration_text = content.replace(b"\x00", b"").lower()
                    if b"<!doctype" in declaration_text or b"<!entity" in declaration_text:
                        raise ValueError("Excel XML DTD and entity declarations are forbidden.")
                    worksheet_numbers[member.filename] = _worksheet_numbers(content)
            return worksheet_numbers
    except (BadZipFile, KeyError, SyntaxError, NotImplementedError, RuntimeError) as exc:
        raise ValueError(f"Invalid Excel archive: {exc}") from exc


def cell_value(cell: ExcelCell, *, numbers: dict[str, str], row: int, column: int) -> object:
    if cell.value is not None and cell.data_type == "n":
        number = numbers.get(f"{row}:{column}")
        if number is None:
            raise ValueError("Excel numeric cell is missing its stored decimal representation.")
        return Decimal(number)
    return cell.value
