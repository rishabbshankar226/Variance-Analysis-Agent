"""The preflight's layout facts: hidden rows and columns, merges, formulas and saved results.

Every workbook here is built in the test and fictional.
"""

from __future__ import annotations

import io
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

from variance_agent.excel import cell_key, inspect_archive, inspect_workbook

SHEET = "xl/worksheets/sheet1.xml"


def _book(build: object) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Line Item", "Budget", "Actual", "Type", "Old Budget"])
    sheet.append(["Revenue", 100, 110, "Revenue", 90])
    sheet.append(["Draft line", 5, 5, "Expense", 5])
    sheet.append(["COGS", 40, 45, "Expense", 40])
    build(sheet)  # type: ignore[operator]
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


def _rewrite(data: bytes, member: str, old: bytes, new: bytes) -> bytes:
    with ZipFile(io.BytesIO(data)) as archive:
        parts = {item.filename: archive.read(item) for item in archive.infolist()}
    assert old in parts[member], parts[member][:400]
    parts[member] = parts[member].replace(old, new)
    capture = io.BytesIO()
    with ZipFile(capture, "w", ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return capture.getvalue()


def test_a_clean_sheet_has_no_layout_facts_and_the_numbers_are_unchanged() -> None:
    data = _book(lambda sheet: None)
    facts = inspect_workbook(data)
    layout = facts.layouts[SHEET]
    assert facts.numbers == inspect_archive(data)
    assert (layout.hidden_rows, layout.hidden_columns, layout.merged, layout.formulas, layout.uncached) == (
        {}, frozenset(), (), frozenset(), frozenset())
    assert layout.errors == {}
    assert (layout.outline_rows, layout.outline_columns) == (0, 0)


def test_hidden_rows_say_whether_an_outline_group_collapsed_them() -> None:
    def build(sheet: object) -> None:
        sheet.row_dimensions[3].hidden = True  # type: ignore[attr-defined]
        sheet.row_dimensions[4].hidden = True  # type: ignore[attr-defined]
        sheet.row_dimensions[4].outlineLevel = 1  # type: ignore[attr-defined]
        sheet.row_dimensions[2].outlineLevel = 2  # type: ignore[attr-defined]

    layout = inspect_workbook(_book(build)).layouts[SHEET]
    assert layout.hidden_rows == {3: False, 4: True}
    assert layout.outline_rows == 2


def test_a_zero_height_row_counts_as_hidden_and_a_short_one_does_not() -> None:
    data = _book(lambda sheet: None)
    data = _rewrite(data, SHEET, b'<row r="3">', b'<row r="3" ht="0" customHeight="1">')
    data = _rewrite(data, SHEET, b'<row r="4">', b'<row r="4" ht="0.5" customHeight="1">')
    assert inspect_workbook(data).layouts[SHEET].hidden_rows == {3: False}


def test_hidden_columns_are_listed_and_a_range_to_the_last_column_stops_at_the_limit() -> None:
    def build(sheet: object) -> None:
        sheet.column_dimensions["E"].hidden = True  # type: ignore[attr-defined]

    data = _book(build)
    assert inspect_workbook(data).layouts[SHEET].hidden_columns == frozenset({5})
    wide = _rewrite(data, SHEET, b'min="5" max="5"', b'min="5" max="16384"')
    assert inspect_workbook(wide).layouts[SHEET].hidden_columns == frozenset(range(5, 257))


def test_header_merges_are_kept_and_deeper_ones_only_counted() -> None:
    def build(sheet: object) -> None:
        sheet.merge_cells("B1:C1")  # type: ignore[attr-defined]
        sheet.merge_cells("A31:B31")  # type: ignore[attr-defined]

    layout = inspect_workbook(_book(build)).layouts[SHEET]
    assert layout.merged == ((1, 2, 1, 3),)
    assert layout.merged_total == 2


def test_a_formula_without_a_saved_result_is_uncached_and_one_with_a_result_is_not() -> None:
    def build(sheet: object) -> None:
        sheet["B5"] = "=B2-B3"  # type: ignore[index]
        sheet["C5"] = "=C2-C3"  # type: ignore[index]

    data = _book(build)
    layout = inspect_workbook(data).layouts[SHEET]
    assert layout.formulas == frozenset({cell_key(5, 2), cell_key(5, 3)})
    assert layout.uncached == layout.formulas
    assert layout.is_uncached(5, 2) and not layout.is_uncached(5, 4)
    # Excel writes the result beside the formula once it has calculated it.
    cached = _rewrite(data, SHEET, b"<f>C2-C3</f><v />", b"<f>C2-C3</f><v>65</v>")
    layout = inspect_workbook(cached).layouts[SHEET]
    assert layout.is_formula(5, 3) and not layout.is_uncached(5, 3)
    assert layout.is_uncached(5, 2)
    assert inspect_workbook(cached).numbers[SHEET]["5:3"] == "65"


def test_a_cached_empty_string_is_a_result_but_an_empty_number_is_not() -> None:
    data = _book(lambda sheet: sheet.__setitem__("A5", '=""'))
    text = _rewrite(data, SHEET, b'<c r="A5"><f>""</f><v /></c>', b'<c r="A5" t="str"><f>""</f><v></v></c>')
    assert inspect_workbook(data).layouts[SHEET].is_uncached(5, 1)
    assert not inspect_workbook(text).layouts[SHEET].is_uncached(5, 1)


def test_a_shared_formula_dependent_without_a_result_is_uncached() -> None:
    data = _book(lambda sheet: sheet.__setitem__("B5", "=B2-B3"))
    shared = _rewrite(data, SHEET, b'<c r="B5"><f>B2-B3</f><v /></c>',
                      b'<c r="B5"><f t="shared" ref="B5:C5" si="0">B2-B3</f><v>60</v></c>'
                      b'<c r="C5"><f t="shared" si="0"/></c>')
    layout = inspect_workbook(shared).layouts[SHEET]
    assert not layout.is_uncached(5, 2)
    assert layout.is_uncached(5, 3)


def test_saved_error_results_are_kept_by_cell() -> None:
    data = _book(lambda sheet: sheet.__setitem__("C5", "=1/0"))
    errored = _rewrite(data, SHEET, b'<c r="C5"><f>1/0</f><v /></c>', b'<c r="C5" t="e"><f>1/0</f><v>#DIV/0!</v></c>')
    layout = inspect_workbook(errored).layouts[SHEET]
    assert layout.errors == {cell_key(5, 3): "#DIV/0!"}
    assert not layout.is_uncached(5, 3)


def test_the_recalculate_on_open_flag_external_links_and_tables_are_read() -> None:
    from openpyxl.worksheet.table import Table

    def build(sheet: object) -> None:
        sheet.add_table(Table(displayName="Plan", ref="A1:E4"))  # type: ignore[attr-defined]

    data = _book(build)
    facts = inspect_workbook(data)
    # openpyxl asks Excel to recalculate every workbook it writes.
    assert facts.recalculate_on_open is True
    assert facts.tables == {SHEET: (("Plan", "A1:E4"),)}
    assert facts.external_links == 0
    calm = _rewrite(data, "xl/workbook.xml", b'fullCalcOnLoad="1"', b'fullCalcOnLoad="0"')
    assert inspect_workbook(calm).recalculate_on_open is False
