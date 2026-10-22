"""Memory and time bounds of the OOXML pre-scan, on hostile but small archives.

The hosted instance has 512 MB, so a few-hundred-KiB upload must not be able to make the
pre-scan allocate hundreds of MiB.
"""

from __future__ import annotations

import io
import sys
import tracemalloc
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from variance_agent import excel
from variance_agent.excel import inspect_archive

SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
SHEET = "xl/worksheets/sheet1.xml"
SHARED = "xl/sharedStrings.xml"


def _workbook_members(rows: list[list[object]] | None = None) -> dict[str, bytes]:
    capture = io.BytesIO()
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows or [["Line Item", "Budget", "Actual"], ["Sales", 100, 120]]:
        sheet.append(row)
    workbook.save(capture)
    workbook.close()
    with ZipFile(io.BytesIO(capture.getvalue())) as archive:
        return {item.filename: archive.read(item) for item in archive.infolist()}


def _zip(members: dict[str, bytes]) -> bytes:
    capture = io.BytesIO()
    with ZipFile(capture, "w", ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return capture.getvalue()


def _shared_strings(entries: int) -> bytes:
    return (
        f'<?xml version="1.0"?><sst xmlns="{SHEET_NS}">'.encode()
        + b"<si><t>x</t></si>" * entries
        + b"</sst>"
    )


def _peak_bytes(call: object) -> int:
    assert callable(call)
    tracemalloc.start()
    try:
        call()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_a_huge_shared_string_table_is_scanned_in_steps_not_expanded() -> None:
    members = _workbook_members()
    members[SHARED] = _shared_strings(4 * 1024 * 1024 // 17)  # ~4 MiB of XML, ~1 KiB zipped
    data = _zip(members)
    assert len(data) < 100_000

    peak = _peak_bytes(lambda: inspect_archive(data))

    # Parsing it into elements costs ~7x its size and holding it twice 2x; scanning in 256 KiB steps
    # holds a few steps at most.
    assert peak < 1024 * 1024 + 512 * 1024, f"pre-scan peaked at {peak / 2**20:.1f} MiB"


def test_a_non_worksheet_part_over_the_cap_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(excel, "_MAX_AUXILIARY_PART_BYTES", 1024 * 1024)
    members = _workbook_members()
    members[SHARED] = _shared_strings(2 * 1024 * 1024 // 17)
    with pytest.raises(ValueError, match="sharedStrings"):
        inspect_archive(_zip(members))


def test_a_worksheet_may_exceed_the_cap_for_other_parts(monkeypatch: pytest.MonkeyPatch) -> None:
    rows: list[list[object]] = [[i, i + 1, i + 2] for i in range(4000)]
    members = _workbook_members(rows)
    assert len(members[SHEET]) > 100 * 1024
    monkeypatch.setattr(excel, "_MAX_AUXILIARY_PART_BYTES", 100 * 1024)
    numbers = inspect_archive(_zip(members))[SHEET]
    assert len(numbers) == 4000 * 3


def test_a_worksheet_is_recognised_by_its_content_not_its_path() -> None:
    members = _workbook_members()
    members["xl/odd/data1.xml"] = members.pop(SHEET)
    numbers = inspect_archive(_zip(members))
    assert numbers["xl/odd/data1.xml"]["2:2"] == "100"


@pytest.mark.parametrize("member", [SHEET, SHARED, "xl/workbook.xml"])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-32"])
def test_a_dtd_after_a_long_prolog_comment_is_still_refused(member: str, encoding: str) -> None:
    # A DTD may follow any amount of prolog, so scanning only the head of the part is not enough.
    members = _workbook_members()
    padding = "<!--" + "x" * 5000 + "-->"
    hostile = (
        f'<?xml version="1.0"?>{padding}<!DOCTYPE x [<!ENTITY e "boom">]>'
        f'<root xmlns="{SHEET_NS}"/>'
    ).encode(encoding)
    members[member] = hostile
    with pytest.raises(ValueError, match="DTD"):
        inspect_archive(_zip(members))


def test_the_worksheet_scan_keeps_little_beyond_the_numbers_it_returns() -> None:
    rows: list[list[object]] = [list(range(i, i + 10)) for i in range(10_000)]
    members = _workbook_members(rows)
    data = _zip(members)
    result: dict[str, dict[str, str]] = {}

    def scan() -> None:
        result.update(inspect_archive(data))

    peak = _peak_bytes(scan)
    numbers = result[SHEET]
    kept = sys.getsizeof(numbers) + sum(
        sys.getsizeof(key) + sys.getsizeof(value) for key, value in numbers.items()
    )
    # The worksheet XML is read once and the result dict is the only per-cell state. A set of
    # every coordinate (the old duplicate check) would add roughly another 60 bytes per cell.
    budget = kept
    assert peak < 1.3 * budget, f"peak {peak / 2**20:.1f} MiB vs {budget / 2**20:.1f} MiB kept"


@pytest.mark.parametrize("offset", [-40, -9, -4, -1, 0])
def test_a_dtd_straddling_a_read_boundary_is_still_found(offset: int) -> None:
    step = excel._SCAN_STEP
    prefix = b'<?xml version="1.0"?><!--'
    padding = b"x" * (step + offset - len(prefix) - len(b"-->") - 1)
    hostile = prefix + padding + b'--><!DOCTYPE x [<!ENTITY e "boom">]><sst/>'
    members = _workbook_members()
    members[SHARED] = hostile
    with pytest.raises(ValueError, match="DTD"):
        inspect_archive(_zip(members))
