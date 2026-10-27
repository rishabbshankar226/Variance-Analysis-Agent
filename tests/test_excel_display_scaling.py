"""E1: a unit caption describes what Excel shows, so a display-scaled amount is not scaled twice (R2).

Every workbook here is built in the test and every value is fictional.
"""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from variance_agent import cli
from variance_agent.intake import IntakeResult, read_input_assisted

SCALED_NOTE = ("The title says amounts are in {unit}, and the cells already hold full amounts that Excel "
               "displays in {unit} (number format '{code}'), so they were read as stored, not scaled again.")
UNCAPTIONED_NOTE = ("Excel shows some amounts scaled by their number format (cell {cell}: its format '{code}' "
                    "shows it {phrase}); the full stored amounts were read.")
FIX = "Give every amount the same number format, or change the title, and upload the file again."
RATE_FIX = "If a row is a rate, mark it Percent in a Measure column, or leave the row out."


def _book(caption: str | None, amounts: list[tuple[str, object, object, str]], formats: dict[str, str],
          extra_header: list[str] | None = None, extra: dict[str, list[object]] | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    if caption is not None:
        sheet.append([caption])
    sheet.append(["Line Item", "Budget", "Actual", "Type", *(extra_header or [])])
    for line, budget, actual, kind in amounts:
        sheet.append([line, budget, actual, kind, *((extra or {}).get(line, []))])
    for cell, code in formats.items():
        sheet[cell].number_format = code
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


# Probe E1: full values stored, shown in thousands, under a thousands caption.
E1_ROWS = [("Revenue", 100000, 110000, "Revenue"), ("COGS", 40000, 45000, "Expense")]
ALL_E1 = {cell: "#,##0," for cell in ("B3", "C3", "B4", "C4")}


def _read(data: bytes) -> IntakeResult:
    return read_input_assisted(data, ".xlsx", filename="plan.xlsx", treat_blank_budgets_as_zero=True)


def _amounts(result: IntakeResult) -> list[tuple[object, object]]:
    assert not result.has_fatal_errors, result.fatal_error_message
    return [(row["budget"], row["actual"]) for row in result.rows]


def test_a_caption_matching_the_display_format_is_not_applied_again() -> None:
    result = _read(_book("($ in thousands)", E1_ROWS, ALL_E1))
    assert _amounts(result) == [(Decimal(100000), Decimal(110000)), (Decimal(40000), Decimal(45000))]
    assert result.detected_unit_multiplier == Decimal(1)
    assert SCALED_NOTE.format(unit="thousands", code="#,##0,") in result.visible_transformations
    assert not any(note.startswith("Amounts scaled from") for note in result.visible_transformations)


def test_a_caption_over_plain_formats_still_scales_as_before() -> None:
    rows = [("Revenue", 100, 110, "Revenue"), ("COGS", 40, 45, "Expense")]
    result = _read(_book("($ in thousands)", rows, {cell: "#,##0" for cell in ALL_E1}))
    assert _amounts(result) == [(Decimal(100000), Decimal(110000)), (Decimal(40000), Decimal(45000))]
    assert result.detected_unit_multiplier == Decimal(1000)
    assert ("Amounts scaled from thousands (x1,000). Thresholds stay in the reporting unit "
            "(full currency units, not thousands).") in result.visible_transformations


def test_millions_shown_in_millions_are_read_as_stored() -> None:
    rows = [("Revenue", 100_000_000, 110_000_000, "Revenue")]
    result = _read(_book("(in millions)", rows, {"B3": "#,##0,,", "C3": "#,##0,,"}))
    assert _amounts(result) == [(Decimal(100_000_000), Decimal(110_000_000))]
    assert SCALED_NOTE.format(unit="millions", code="#,##0,,") in result.visible_transformations


def _refusal(caption_unit: str, cells: list[str], *, rate: bool = False) -> str:
    return "\n".join([
        f"The title of 'plan.xlsx' says amounts are in {caption_unit}, but the amounts' number formats "
        "don't agree with it, so I can't tell which unit each amount is in:",
        *(f"- {cell}" for cell in cells), *([RATE_FIX] if rate else []), FIX,
    ])


@pytest.mark.parametrize(("caption", "unit", "code", "phrase"), [
    ("($ in thousands)", "thousands", "#,##0,,", "in millions"),
    ("(in millions)", "millions", "#,##0,", "in thousands"),
    ("($ in thousands)", "thousands", "#,##0,,,", "in billions"),
])
def test_a_caption_and_a_display_format_in_different_units_stop(caption: str, unit: str, code: str, phrase: str) -> None:
    result = _read(_book(caption, [("Revenue", 100000, 110000, "Revenue")], {"B3": code, "C3": code}))
    assert result.has_fatal_errors
    assert result.fatal_error_message == _refusal(unit, [
        f"Row 3, Revenue, Budget column (cell B3): its format '{code}' shows it {phrase}",
        f"Row 3, Revenue, Actual column (cell C3): its format '{code}' shows it {phrase}"])


def test_mixed_formats_under_one_caption_stop_and_name_the_scaled_cells() -> None:
    formats = {"B3": "#,##0,", "C3": "#,##0,", "B4": "#,##0", "C4": "#,##0"}
    result = _read(_book("($ in thousands)", [*E1_ROWS[:1], ("COGS", 40, 45, "Expense")], formats))
    assert result.fatal_error_message == _refusal("thousands", [
        "Row 3, Revenue, Budget column (cell B3): its format '#,##0,' shows it in thousands",
        "Row 3, Revenue, Actual column (cell C3): its format '#,##0,' shows it in thousands"])


def test_a_percent_format_on_a_money_row_under_a_caption_stops_with_the_rate_fix() -> None:
    rows = [("Revenue", 100, 110, "Revenue"), ("Gross margin", Decimal("0.25"), Decimal("0.3"), "Revenue")]
    result = _read(_book("($ in thousands)", rows, {"B4": "0%", "C4": "0%"}))
    assert result.fatal_error_message == _refusal("thousands", [
        "Row 4, Gross margin, Budget column (cell B4): its format '0%' shows it as a percentage",
        "Row 4, Gross margin, Actual column (cell C4): its format '0%' shows it as a percentage"], rate=True)


def test_a_format_this_reader_cannot_interpret_stops_under_a_caption() -> None:
    code = "[>=1000]#,##0,;#,##0"
    result = _read(_book("($ in thousands)", [("Revenue", 100, 110, "Revenue")], {"B3": code}))
    assert result.fatal_error_message == _refusal("thousands", [
        f"Row 3, Revenue, Budget column (cell B3): its format '{code}' shows it in a way I can't interpret"])


def _up(formats: dict[str, str]) -> dict[str, str]:
    """The same cells one row higher, for a sheet without the caption row."""
    return {cell[0] + str(int(cell[1:]) - 1): code for cell, code in formats.items()}


def test_without_a_caption_the_stored_amounts_are_read_and_the_display_is_noted() -> None:
    result = _read(_book(None, E1_ROWS, _up(ALL_E1)))
    assert _amounts(result) == [(Decimal(100000), Decimal(110000)), (Decimal(40000), Decimal(45000))]
    assert result.detected_unit_multiplier == Decimal(1)
    assert UNCAPTIONED_NOTE.format(cell="B2", code="#,##0,", phrase="in thousands") in result.visible_transformations


def test_a_declared_percent_row_keeps_its_percent_format_without_a_question() -> None:
    rows = [("Revenue", 100, 110, "Revenue"), ("Gross margin", "25%", "30%", "")]
    data = _book("($ in thousands)", rows, {}, extra_header=["Measure", "Better"],
                 extra={"Revenue": ["Currency", ""], "Gross margin": ["Percent", "Higher"]})
    result = _read(data)
    assert not result.has_fatal_errors, result.fatal_error_message


def test_a_plain_file_has_no_new_note() -> None:
    result = _read(_book(None, [("Revenue", 100, 110, "Revenue")], {}))
    assert not result.has_fatal_errors
    assert not any("number format" in note for note in result.visible_transformations)


def test_the_e1_probe_reports_the_true_totals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "e1_display_scaled.xlsx"
    path.write_bytes(_book("($ in thousands)", E1_ROWS, ALL_E1))
    code = cli.main([str(path), "--assisted", "--period", "X", "--dollar-threshold", "1", "--percent-threshold", "1"])
    captured = capsys.readouterr()
    assert code == 0
    assert "- Total Revenue: $110,000.00 vs. $100,000.00 ($10,000.00, 10.0%, F)" in captured.out
    assert "Amounts scaled from thousands" not in captured.err
    assert f"[assisted intake] {SCALED_NOTE.format(unit='thousands', code='#,##0,')}" in captured.err


@pytest.mark.parametrize(("formats", "expected"), [
    (ALL_E1, [(Decimal(100000), Decimal(110000)), (Decimal(40000), Decimal(45000))]),
    ({}, [(Decimal(100000000), Decimal(110000000)), (Decimal(40000000), Decimal(45000000))]),
])
def test_a_mapping_unit_is_reconciled_with_the_formats_like_a_caption(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], formats: dict[str, str], expected: list[tuple[Decimal, Decimal]],
) -> None:
    path = tmp_path / "plan.xlsx"
    path.write_bytes(_book(None, E1_ROWS, _up(formats)))
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"mapping_version": "1.5", "unit_scale": "1000"}), encoding="utf-8")
    audit = tmp_path / "audit.json"
    code = cli.main([str(path), "--mapping", str(mapping), "--period", "X", "--dollar-threshold", "1",
                     "--percent-threshold", "1", "--audit-json", str(audit), "-o", str(tmp_path / "r.md")])
    assert code == 0, capsys.readouterr().err
    rows = {row["line_item"]: (Decimal(row["budget"]), Decimal(row["actual"]))
            for row in json.loads(audit.read_text(encoding="utf-8"))["material_variances"]}
    assert [rows["Revenue"], rows["COGS"]] == expected


def test_a_mapping_unit_with_mixed_formats_stops(tmp_path: Path) -> None:
    path = tmp_path / "plan.xlsx"
    path.write_bytes(_book(None, E1_ROWS, {"B2": "#,##0,", "C2": "#,##0,"}))
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"mapping_version": "1.5", "unit_scale": "1000"}), encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        cli.main([str(path), "--mapping", str(mapping), "--period", "X", "--dollar-threshold", "1", "--percent-threshold", "1"])
    assert stopped.value.code == 2
