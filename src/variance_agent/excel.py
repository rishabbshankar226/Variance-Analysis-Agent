"""Bound OOXML expansion and retain numeric XML before binary-float conversion."""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from decimal import Decimal
from typing import IO, BinaryIO, Protocol
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

# Only worksheets can legitimately be large. Shared strings, styles and the rest are far smaller
# in real workbooks, and openpyxl loads shared strings whole, so a bigger one is not a file this
# tool should expand on a small host.
_MAX_AUXILIARY_PART_BYTES = 16 * 1024 * 1024
_SNIFF_BYTES = 4096
_WORKSHEET_ROOT = re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?worksheet[\s>]")


def _interleaved(word: bytes) -> bytes:
    """A pattern for `word` that also matches it spread across UTF-16/UTF-32 NUL bytes."""
    return rb"\x00{0,3}".join(re.escape(bytes([byte])) for byte in word)


# DTDs and entity declarations are refused wherever they sit in the prolog and in any encoding;
# the search runs over 256 KiB reads, so no copy of the whole member is ever held.
_DECLARATION = re.compile(
    _interleaved(b"<!") + rb"\x00{0,3}(?:" + _interleaved(b"doctype") + rb"|"
    + _interleaved(b"entity") + rb")",
    re.IGNORECASE,
)
_SCAN_STEP = 256 * 1024
# Longest a declaration can be across a read boundary: 14 UTF-32 characters.
_SCAN_OVERLAP = 64


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


def _worksheet_numbers(xml: IO[bytes]) -> dict[str, str]:
    numbers: dict[str, str] = {}
    row_index = 0
    column_index = 0
    coordinate = ""
    numeric = False
    cells = 0
    depth = 0
    for event, element in ElementTree.iterparse(xml, events=("start", "end")):
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
            # Rows and columns only ever increase above, so a coordinate cannot repeat.
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


def _drain(source: IO[bytes], *, check_declarations: bool) -> tuple[int, bool]:
    """Read a member in steps, returning its size and whether it declares a DTD or entity."""
    size = 0
    declares = False
    tail = b""
    while chunk := source.read(_SCAN_STEP):
        size += len(chunk)
        if size > MAX_ARCHIVE_BYTES:
            break
        if check_declarations and not declares:
            window = tail + chunk
            declares = _DECLARATION.search(window) is not None
            tail = window[-_SCAN_OVERLAP:]
    return size, declares


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
                is_xml = member.filename.lower().endswith((".xml", ".rels"))
                with archive.open(member) as source:
                    head = source.read(_SNIFF_BYTES)
                # Removing NULs also sniffs worksheets written as UTF-16/UTF-32.
                is_worksheet = is_xml and bool(_WORKSHEET_ROOT.search(head.replace(b"\x00", b"")))
                if is_xml and not is_worksheet and member.file_size > _MAX_AUXILIARY_PART_BYTES:
                    raise ValueError(
                        f"Excel part {member.filename} exceeds "
                        f"{_MAX_AUXILIARY_PART_BYTES // (1024 * 1024)} MiB."
                    )
                with archive.open(member) as source:
                    size, declares = _drain(source, check_declarations=is_xml)
                total_bytes += size
                if total_bytes > MAX_ARCHIVE_BYTES:
                    raise ValueError("Excel archive exceeds the 64 MiB expanded size limit.")
                if declares:
                    raise ValueError("Excel XML DTD and entity declarations are forbidden.")
                if is_worksheet:
                    with archive.open(member) as source:
                        worksheet_numbers[member.filename] = _worksheet_numbers(source)
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
