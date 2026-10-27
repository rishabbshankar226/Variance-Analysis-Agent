"""Bound OOXML expansion and retain numeric XML before binary-float conversion."""

from __future__ import annotations

import io
import posixpath
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
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
_RELATIONSHIPS_NAMESPACE = "{http://schemas.openxmlformats.org/package/2006/relationships}"
# Merged ranges matter for reading headers, which sit near the top of a sheet; deeper merges
# are counted, not kept, so a sheet of merged cells cannot grow this state.
_MERGE_HEADER_ROWS = 30
_MAX_KEPT_MERGES = 1000
_MAX_LISTED_TABLES = 100
_MAX_ERROR_TEXT = 16
_OUTLINE_LEVELS = 7

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


def cell_key(row: int, column: int) -> int:
    """One integer per cell, so a set of formula cells costs one int each, not a tuple."""
    return row * (MAX_COLUMNS + 1) + column


@dataclass(frozen=True)
class SheetLayout:
    """What a worksheet hides or leaves uncalculated, read in the same bounded pass as its numbers.

    Rows and columns are 1-based. Formula cells are kept as `cell_key` integers.
    """

    hidden_rows: dict[int, bool] = field(default_factory=dict)  # row -> collapsed in an outline group
    hidden_columns: frozenset[int] = frozenset()
    merged: tuple[tuple[int, int, int, int], ...] = ()  # (first row, first column, last row, last column)
    merged_total: int = 0
    formulas: frozenset[int] = frozenset()  # every formula cell
    uncached: frozenset[int] = frozenset()  # formula cells with no saved result
    errors: dict[int, str] = field(default_factory=dict)  # saved error results such as #REF!
    outline_rows: int = 0  # deepest outline level on rows
    outline_columns: int = 0

    def is_formula(self, row: int, column: int) -> bool:
        return cell_key(row, column) in self.formulas

    def is_uncached(self, row: int, column: int) -> bool:
        return cell_key(row, column) in self.uncached


@dataclass(frozen=True)
class WorkbookFacts:
    """The preflight's stored decimals plus the layout facts intake reports on."""

    numbers: dict[str, dict[str, str]]
    layouts: dict[str, SheetLayout] = field(default_factory=dict)
    # The producer asked Excel to recalculate every formula on open (`calcPr fullCalcOnLoad`), so
    # saved results may be stale: XlsxWriter, for one, saves 0 for every formula and sets it.
    recalculate_on_open: bool = False
    external_links: int = 0
    tables: dict[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)  # sheet path -> (name, range)

    def may_have_unsaved_formulas(self, worksheet_path: str) -> bool:
        """Whether the sheet has a formula whose result might not be usable; False means skip the check."""
        layout = self.layouts.get(worksheet_path)
        return layout is not None and bool(layout.formulas if self.recalculate_on_open else layout.uncached)


_MAX_LISTED_FORMULAS = 10
_NEVER_CALCULATED = ("These cells hold formulas that Excel never calculated, so the file has no saved "
                     "result for them:")
_RECALCULATE_ON_OPEN = ("The file asks Excel to recalculate its formulas when it is opened, so these cells "
                        "may have no saved result or an out-of-date one:")


def column_letters(column: int) -> str:
    """Spreadsheet letters for a 1-based column: 1 -> 'A', 28 -> 'AB'."""
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def unsaved_formula_cells(
    layout: SheetLayout, recalculate_on_open: bool, include: Callable[[int, int], bool],
) -> list[tuple[int, int]]:
    """The (row, column) cells, row by row, whose formula result cannot be used and `include` reads.

    A formula Excel never calculated has no saved result. In a workbook that asks Excel to
    recalculate on open, a saved result may be stale, so every formula cell counts. Only
    formula cells are visited, so a large sheet costs nothing here.
    """
    pool = layout.formulas if recalculate_on_open else layout.uncached
    return sorted(cell for cell in (divmod(key, MAX_COLUMNS + 1) for key in pool) if include(*cell))


def unsaved_formulas_message(filename: str, descriptions: list[str], *, recalculate_on_open: bool) -> str:
    """Stop-and-fix message for formula cells whose results cannot be read (never read as blank)."""
    lead = _RECALCULATE_ON_OPEN if recalculate_on_open else _NEVER_CALCULATED
    lines = [f"I could not read every amount in '{filename}', so I stopped instead of guessing. {lead}"]
    lines.extend(f"- {text}" for text in descriptions[:_MAX_LISTED_FORMULAS])
    if len(descriptions) > _MAX_LISTED_FORMULAS:
        lines.append(f"- ...and {len(descriptions) - _MAX_LISTED_FORMULAS} more.")
    lines.append("Open the file in Excel, let it calculate, save it, and upload it again.")
    return "\n".join(lines)


def describe_cell(row: int, column: int, *, line_item: str = "", field: str = "") -> str:
    """'Row 4, Other income, Budget column (cell B4)', with the parts a reader knows."""
    parts = [f"Row {row}", *([line_item] if line_item else []), *([f"{field} column"] if field else [])]
    return f"{', '.join(parts)} (cell {column_letters(column)}{row})"


def table_formulas_message(
    facts: WorkbookFacts, worksheet_path: str, filename: str, *, header_row: int, headers: list[str],
    rows: dict[int, list[object]], line_item_column: int | None,
) -> str | None:
    """The unsaved-formula stop for a table read whole: every data row under a named header.

    `headers` is the header row's text by 0-based column; `rows` maps physical row numbers to
    their raw values. Returns None when every read formula has a usable saved result.
    """
    layout = facts.layouts.get(worksheet_path, SheetLayout())

    def read(row: int, column: int) -> bool:
        return row in rows and column <= len(headers) and bool(headers[column - 1].strip())

    def describe(row: int, column: int) -> str:
        values = rows[row]
        label = values[line_item_column] if line_item_column is not None and line_item_column < len(values) else None
        return describe_cell(row, column, line_item="" if label is None else str(label).strip(),
                             field=headers[column - 1].strip())

    unsaved = unsaved_formula_cells(layout, facts.recalculate_on_open, read)
    if not unsaved:
        return None
    return unsaved_formulas_message(filename, [describe(*cell) for cell in unsaved],
                                    recalculate_on_open=any(not layout.is_uncached(*cell) for cell in unsaved))


HIDDEN_ROW_CHOICES = ("include", "exclude")
_MAX_LISTED_ROWS = 10


def hidden_data_rows(
    layout: SheetLayout, rows: dict[int, list[object]] | list[list[object]], *, header_row: int,
    line_item_column: int | None,
) -> list[tuple[int, str, bool]]:
    """Rows below the header that Excel hides and that hold anything: (row, label, collapsed).

    `rows` maps physical row numbers to raw values, or is a list where index i is row i + 1.
    """
    found = []
    for number, collapsed in sorted(layout.hidden_rows.items()):
        values = rows.get(number) if isinstance(rows, dict) else (
            rows[number - 1] if 0 < number <= len(rows) else None)
        if number <= header_row or values is None or all(v is None or str(v).strip() == "" for v in values):
            continue
        label = values[line_item_column] if line_item_column is not None and line_item_column < len(values) else None
        found.append((number, "" if label is None else str(label).strip(), collapsed))
    return found


def hidden_rows_question(rows: list[tuple[int, str, bool]]) -> str:
    """Ask whether rows hidden in Excel are counted (R3); a person answers, never a default."""
    lines = ["These rows are hidden in Excel but have amounts, so I need to know whether to count them:"]
    for number, label, collapsed in rows[:_MAX_LISTED_ROWS]:
        how = "in a collapsed outline group" if collapsed else "hidden"
        lines.append(f"- Row {number}{f', {label}' if label else ''} ({how})")
    if len(rows) > _MAX_LISTED_ROWS:
        lines.append(f"- ...and {len(rows) - _MAX_LISTED_ROWS} more.")
    return "\n".join(lines)


def hidden_rows_note(choice: str, rows: list[tuple[int, str, bool]]) -> str:
    """What was done with the rows hidden in Excel, for the read summary."""
    named = [f"row {number}{f' ({label})' if label else ''}" for number, label, _ in rows[:_MAX_LISTED_ROWS]]
    if len(rows) > _MAX_LISTED_ROWS:
        named.append(f"and {len(rows) - _MAX_LISTED_ROWS} more")
    verb = "Counted" if choice == "include" else "Left out"
    return f"{verb} {len(rows)} row{'s' if len(rows) != 1 else ''} hidden in Excel: {', '.join(named)}."


_OLE2_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_SAVE_AS = "Open it in Excel, choose File > Save As, pick Excel Workbook (.xlsx), and upload that copy"


def workbook_kind(data: bytes) -> str:
    """What a file named .xls holds: "ooxml" (an .xlsx), "biff" (Excel 97-2003), "html" or "other"."""
    if data.startswith(b"PK\x03\x04"):
        return "ooxml"
    if data.startswith(_OLE2_SIGNATURE):
        return "biff"
    head = data[:1024].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith((b"<!doctype html", b"<html")) or (head.startswith(b"<?xml") and b"<html" in head):
        return "html"
    return "other"


def legacy_workbook_message(filename: str, kind: str) -> str:
    """The refusal for an .xls that is not an .xlsx inside, with the fix."""
    if kind == "biff":
        return f"'{filename}' is in the Excel 97-2003 format (.xls), which I can't read. {_SAVE_AS}."
    if kind == "html":
        return (f"'{filename}' is a web page saved with an .xls name, not an Excel workbook. "
                f"{_SAVE_AS}, or export it as CSV.")
    return (f"'{filename}' isn't an Excel workbook I can read. Save it from Excel as an Excel Workbook "
            "(.xlsx) or as CSV, and upload that copy.")


def renamed_workbook_note(filename: str) -> str:
    return f"Read '{filename}' as an Excel workbook: it is an .xlsx file with an .xls name."


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true"}


def _is_zero(value: str | None) -> bool:
    if value is None:
        return False
    try:
        return Decimal(value.strip()) == 0
    except (InvalidOperation, ValueError):
        return False


def _outline_level(value: str | None) -> int:
    return int(value) if value is not None and value.isdigit() and int(value) <= _OUTLINE_LEVELS else 0


def _column_number(letters: str) -> int:
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - ord("A") + 1
    return number


def _range_bounds(reference: str) -> tuple[int, int, int, int] | None:
    parts = reference.split(":")
    matches = [_CELL_REFERENCE.fullmatch(part) for part in parts]
    if not 1 <= len(parts) <= 2 or any(match is None for match in matches):
        return None
    cells = [(int(m[2]), _column_number(m[1])) for m in matches if m is not None]
    (first_row, first_column), (last_row, last_column) = cells[0], cells[-1]
    return (min(first_row, last_row), min(first_column, last_column),
            max(first_row, last_row), max(first_column, last_column))


def _worksheet_scan(xml: IO[bytes]) -> tuple[dict[str, str], SheetLayout]:
    numbers: dict[str, str] = {}
    row_index = 0
    column_index = 0
    coordinate = ""
    numeric = False
    cells = 0
    depth = 0
    zero_height = False
    hidden_rows: dict[int, bool] = {}
    hidden_columns: set[int] = set()
    merged: list[tuple[int, int, int, int]] = []
    merged_total = 0
    formulas: set[int] = set()
    uncached: set[int] = set()
    errors: dict[int, str] = {}
    outline_rows = outline_columns = 0
    cell_type = "n"
    has_formula = has_result = False
    result_text: str | None = None
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
            level = _outline_level(element.get("outlineLevel"))
            outline_rows = max(outline_rows, level)
            height = element.get("ht")
            if _truthy(element.get("hidden")) or _is_zero(height) or (zero_height and height is None):
                hidden_rows[row_index] = level >= 1
        elif event == "start" and element.tag == f"{_SHEET_NAMESPACE}sheetFormatPr":
            zero_height = _truthy(element.get("zeroHeight"))
        elif event == "start" and element.tag == f"{_SHEET_NAMESPACE}col":
            outline_columns = max(outline_columns, _outline_level(element.get("outlineLevel")))
            if _truthy(element.get("hidden")) or _is_zero(element.get("width")):
                low, high = element.get("min", ""), element.get("max", "")
                if low.isdigit() and high.isdigit() and int(low) >= 1:
                    # Cells beyond the column limit are refused, so a range to column XFD stops there.
                    hidden_columns.update(range(int(low), min(int(high), MAX_COLUMNS) + 1))
        elif event == "start" and element.tag == f"{_SHEET_NAMESPACE}mergeCell":
            bounds = _range_bounds(element.get("ref", ""))
            if bounds is not None:
                merged_total += 1
                if bounds[0] <= _MERGE_HEADER_ROWS and len(merged) < _MAX_KEPT_MERGES:
                    merged.append(bounds)
        elif event == "start" and element.tag == f"{_SHEET_NAMESPACE}f":
            has_formula = True
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
            cell_type = element.get("t", "n")
            numeric = cell_type == "n"
            has_formula = has_result = False
            result_text = None
        elif event == "end" and element.tag == f"{_SHEET_NAMESPACE}v":
            # A cached empty string (t="str", <v></v>) is a result; an empty <v/> elsewhere is not.
            has_result = bool(element.text) or cell_type == "str"
            result_text = element.text
            if numeric and element.text is not None:
                if len(element.text) > MAX_NUMBER_LENGTH:
                    raise ValueError("Excel numeric literal exceeds the supported length.")
                numbers[coordinate] = element.text
        elif event == "end" and element.tag == f"{_SHEET_NAMESPACE}c":
            key = cell_key(row_index, column_index)
            if has_formula:
                formulas.add(key)
                if not has_result:
                    uncached.add(key)
            if cell_type == "e" and result_text:
                errors[key] = result_text[:_MAX_ERROR_TEXT]
            numeric = has_formula = has_result = False
        if event == "end":
            element.clear()
            depth -= 1
    layout = SheetLayout(
        hidden_rows=hidden_rows,
        hidden_columns=frozenset(hidden_columns),
        merged=tuple(merged),
        merged_total=merged_total,
        formulas=frozenset(formulas),
        uncached=frozenset(uncached),
        errors=errors,
        outline_rows=outline_rows,
        outline_columns=outline_columns,
    )
    return numbers, layout


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
    return inspect_workbook(data).numbers


def _parse_part(archive: ZipFile, name: str) -> ElementTree.Element | None:
    """Parse a small part the preflight already size-checked and found free of declarations."""
    try:
        return ElementTree.fromstring(archive.read(name))
    except (KeyError, ElementTree.ParseError):
        return None


def _workbook_facts(archive: ZipFile, worksheets: list[str]) -> tuple[bool, int, dict[str, tuple[tuple[str, str], ...]]]:
    names = set(archive.namelist())
    recalculate = False
    workbook = _parse_part(archive, "xl/workbook.xml") if "xl/workbook.xml" in names else None
    if workbook is not None:
        calc = workbook.find(f"{_SHEET_NAMESPACE}calcPr")
        recalculate = calc is not None and _truthy(calc.get("fullCalcOnLoad"))
    links = sum(1 for name in names if re.fullmatch(r"xl/externalLinks/externalLink\d+\.xml", name))
    tables: dict[str, tuple[tuple[str, str], ...]] = {}
    for sheet in worksheets:
        folder, base = posixpath.split(sheet)
        rels_name = posixpath.join(folder, "_rels", base + ".rels")
        rels = _parse_part(archive, rels_name) if rels_name in names else None
        if rels is None:
            continue
        found: list[tuple[str, str]] = []
        for rel in rels.iter(f"{_RELATIONSHIPS_NAMESPACE}Relationship"):
            if not str(rel.get("Type", "")).endswith("/table") or len(found) >= _MAX_LISTED_TABLES:
                continue
            reference = str(rel.get("Target", ""))
            # Targets are relative to the sheet's folder, or package-absolute when they start with "/".
            target = posixpath.normpath(reference[1:] if reference.startswith("/") else posixpath.join(folder, reference))
            table = _parse_part(archive, target) if target in names else None
            if table is not None:
                name = str(table.get("displayName") or table.get("name") or "")
                found.append((name, str(table.get("ref", ""))))
        if found:
            tables[sheet] = tuple(found)
    return recalculate, links, tables


def inspect_workbook(data: bytes) -> WorkbookFacts:
    """`inspect_archive`, plus what each worksheet hides or leaves uncalculated."""
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
            layouts: dict[str, SheetLayout] = {}
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
                        worksheet_numbers[member.filename], layouts[member.filename] = _worksheet_scan(source)
            recalculate, links, tables = _workbook_facts(archive, list(layouts))
            return WorkbookFacts(worksheet_numbers, layouts, recalculate, links, tables)
    except (BadZipFile, KeyError, SyntaxError, NotImplementedError, RuntimeError) as exc:
        raise ValueError(f"Invalid Excel archive: {exc}") from exc


def cell_value(cell: ExcelCell, *, numbers: dict[str, str], row: int, column: int) -> object:
    if cell.value is not None and cell.data_type == "n":
        number = numbers.get(f"{row}:{column}")
        if number is None:
            raise ValueError("Excel numeric cell is missing its stored decimal representation.")
        return Decimal(number)
    return cell.value
