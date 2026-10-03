"""Reproductions for the October diagnostic; proposed fixes target PR #1."""
import re
from decimal import Decimal
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from openpyxl import Workbook

from variance_agent.analysis import analyze_rows
from variance_agent.audit import build_audit_record
from variance_agent.cli import main
from variance_agent.models import AnalysisConfig, LineType
from variance_agent.parsing import load_file


def config(type_map=None):
    return AnalysisConfig("Q3", Decimal("1"), Decimal(".05"), type_map or {})


def workbook_with_dimension(path, dimension):
    book = Workbook()
    book.active.append(["Line Item", "Budget", "Actual"])
    book.active.append(["Sales", 100, 120])
    book.active.append(["Rent", 50, 60])
    book.active.append(["Utilities", 20, 25])
    book.save(path)
    book.close()
    with ZipFile(path) as archive:
        contents = {item.filename: archive.read(item.filename) for item in archive.infolist()}
    contents["xl/worksheets/sheet1.xml"] = re.sub(
        rb'<dimension ref="[^"]+"',
        f'<dimension ref="{dimension}"'.encode(),
        contents["xl/worksheets/sheet1.xml"],
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)


@pytest.mark.parametrize("dimension", ["A1:C3", "A1:B4", "A1:C1000"])
def test_workbook_metadata_cannot_hide_or_inflate_financial_rows(tmp_path, dimension):
    source = tmp_path / "source.xlsx"
    workbook_with_dimension(source, dimension)
    result = analyze_rows(load_file(source), config())
    assert len(result.rows) == 3
    assert result.expenses.actual == Decimal("85")
    assert build_audit_record(result)["data_quality"]["totals_complete"]


def test_excel_cell_beyond_header_is_rejected(tmp_path):
    source = tmp_path / "source.xlsx"
    book = Workbook()
    book.active.append(["Line Item", "Budget", "Actual"])
    book.active.append(["Sales", 100, 120, 999])
    book.save(source)
    book.close()
    with pytest.raises(ValueError, match="blank header|beyond"):
        load_file(source)


def test_explicit_detail_account_containing_total_is_not_discarded():
    result = analyze_rows(
        [
            {"Line Item": "Sales", "Budget": 500, "Actual": 600},
            {"Line Item": "Total Quality Management", "Budget": 100, "Actual": 120,
             "Type": "Expense", "Row Kind": "Detail"},
            {"Line Item": "Rent", "Budget": 100, "Actual": 120},
        ], config(),
    )
    assert result.expenses.actual == Decimal("240")
    assert not result.rows[1].excluded_from_aggregation


@pytest.mark.parametrize("label", ["Total Expenses", "Subtotal Expenses", "Grand Total Expenses",
                                        "Revenue Total", "Sub Total Revenue"])
def test_recognized_category_summary_remains_supported(label):
    revenue = "Revenue" in label
    rows = [
        {"Line Item": "Sales" if revenue else "Rent", "Budget": 100, "Actual": 120},
        {"Line Item": label, "Budget": 100, "Actual": 120},
    ]
    result = analyze_rows(rows, config())
    assert result.rows[1].excluded_from_aggregation
    assert (result.revenue if revenue else result.expenses).actual == 120


@pytest.mark.parametrize("malformation", ["missing_parts", "broken_xml"])
def test_malformed_excel_is_an_actionable_cli_error(tmp_path, capsys, malformation):
    source = tmp_path / "bad.xlsx"
    if malformation == "missing_parts":
        with ZipFile(source, "w") as archive:
            archive.writestr("arbitrary.txt", "not a workbook")
    else:
        workbook_with_dimension(source, "A1:C4")
        with ZipFile(source) as archive:
            contents = {item.filename: archive.read(item.filename) for item in archive.infolist()}
        contents["xl/workbook.xml"] = b"<broken"
        with ZipFile(source, "w", ZIP_DEFLATED) as archive:
            for name, content in contents.items():
                archive.writestr(name, content)
    report = tmp_path / "report.md"
    report.write_text("previous report")
    with pytest.raises(SystemExit) as error:
        main([str(source), "--period", "Q3", "--dollar-threshold", "1",
              "--percent-threshold", "5", "--output", str(report)])
    assert error.value.code == 2
    assert "Excel" in capsys.readouterr().err
    assert report.read_text() == "previous report"


@pytest.mark.parametrize("kind", ["Bogus", None, 7])
def test_public_api_rejects_invalid_type_map_values(kind):
    rows = [{"Line Item": "Sales", "Budget": 100, "Actual": 120},
            {"Line Item": "Rent", "Budget": 50, "Actual": 60},
            {"Line Item": "Other", "Budget": 30, "Actual": 40}]
    with pytest.raises(ValueError, match="type.map|Type map"):
        analyze_rows(rows, config({"Other": kind}))


def test_public_api_accepts_supported_type_map_string():
    result = analyze_rows([{"Line Item": "Other", "Budget": 30, "Actual": 40}],
                          config({"Other": "Expense"}))
    assert result.rows[0].line_type == LineType.EXPENSE
    assert result.expenses.actual == 40


@pytest.mark.parametrize("value", ["0e-1000000", Decimal("0e-1000000")])
def test_zero_scale_cannot_expand_audit_serialization(value):
    result = analyze_rows([{"Line Item": "Sales", "Budget": value, "Actual": 0}], config())
    assert len(format(result.rows[0].budget, "f")) < 2000
    assert len(str(build_audit_record(result))) < 5000


def test_ambiguous_summary_name_requires_explicit_row_kind():
    with pytest.raises(ValueError, match="Row Kind|summary"):
        analyze_rows([
            {"Line Item": "Total Quality Management", "Budget": 100, "Actual": 120,
             "Type": "Expense"},
            {"Line Item": "Rent", "Budget": 100, "Actual": 120},
        ], config())


def test_explicit_total_with_custom_label_is_reconciled_and_excluded():
    result = analyze_rows([
        {"Line Item": "Rent", "Budget": 100, "Actual": 120},
        {"Line Item": "Operating Overhead Rollup", "Budget": 100, "Actual": 120,
         "Type": "Expense", "Row Kind": "Total"},
    ], config())
    assert result.expenses.actual == 120
    assert result.rows[1].excluded_from_aggregation


def test_invalid_row_kind_fails_instead_of_guessing():
    with pytest.raises(ValueError, match="Row Kind"):
        analyze_rows([{ "Line Item": "Sales", "Budget": 100, "Actual": 120,
                       "Row Kind": "Maybe"}], config())


def test_blank_optional_row_kind_uses_conservative_inference():
    result = analyze_rows([
        {"Line Item": "Sales", "Budget": 100, "Actual": 120, "Row Kind": ""},
        {"Line Item": "Total Revenue", "Budget": 100, "Actual": 120, "Row Kind": None},
    ], config())
    assert result.revenue.actual == 120
    assert result.rows[1].excluded_from_aggregation


def test_zero_threshold_scale_cannot_expand_audit_serialization():
    cfg = AnalysisConfig("Q3", Decimal("0e-1000000"), Decimal("0e-1000000"))
    result = analyze_rows([{"Line Item": "Sales", "Budget": "0.00", "Actual": 0}], cfg)
    assert len(str(build_audit_record(result))) < 5000
    assert result.rows[0].budget.as_tuple().exponent == -2
