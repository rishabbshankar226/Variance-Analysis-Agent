from decimal import Decimal

import pytest

from variance_agent.analysis import analyze_rows
from variance_agent.audit import build_audit_record
from variance_agent.cli import main
from variance_agent.models import AnalysisConfig, LineType
from variance_agent.parsing import load_csv_text, load_json_text, load_file


CFG = AnalysisConfig("Q3", Decimal("100"), Decimal(".05"))


def row(name="Revenue", budget=100, actual=120, **extra):
    return {"Line Item": name, "Budget": budget, "Actual": actual, **extra}


def test_json_decimal_precision_survives_loading():
    result = analyze_rows(
        load_json_text(
            '[{"Line Item":"Revenue","Budget":9007199254740992.01,"Actual":9007199254740992.02}]'
        ),
        CFG,
    )
    assert result.rows[0].variance_dollars == Decimal(".01")


@pytest.mark.parametrize(
    "text",
    [
        "Line Item,Budget,Actual\nRevenue,1,000,1200\n",
        "Line Item,Budget,Actual,Type\nRevenue,100,120\n",
        "Line Item,Budget,Actual,\nRevenue,100,120,hidden\n",
    ],
)
def test_csv_rejects_data_loss(text):
    with pytest.raises(ValueError):
        load_csv_text(text)


def test_null_line_item_is_rejected():
    with pytest.raises(ValueError, match="Line Item"):
        analyze_rows([row(None)], CFG)


@pytest.mark.parametrize("name", ["Net Income", "Operating Income", "Gross Profit"])
def test_profit_metrics_are_not_additive_revenue(name):
    result = analyze_rows([row(name)], CFG)
    assert result.rows[0].line_type == LineType.UNCLASSIFIED


def test_summary_must_reconcile_before_it_is_discarded():
    with pytest.raises(ValueError, match="summary|Summary"):
        analyze_rows([row(), row("Total Revenue", 200, 240)], CFG)


def test_driver_components_must_reconcile_to_variance():
    result = analyze_rows(
        [
            row(
                budget=1000000,
                actual=1000001,
                **{
                    "Budget Volume": 1,
                    "Actual Volume": 1,
                    "Budget Price": 1000000.9,
                    "Actual Price": 1000000.1,
                },
            )
        ],
        CFG,
    )
    assert not result.rows[0].driver_evidence.reconciles


@pytest.mark.parametrize("collision", ["input_report", "input_audit", "outputs", "type_map"])
def test_cli_rejects_path_collisions_without_writing(tmp_path, collision):
    source = tmp_path / "input.csv"
    source.write_text("Line Item,Budget,Actual\nRevenue,100,120\n")
    mapping = tmp_path / "types.json"
    mapping.write_text('{"Revenue":"Revenue"}')
    report, audit = tmp_path / "report.md", tmp_path / "audit.json"
    if collision == "input_report":
        report = source
    elif collision == "input_audit":
        audit = source
    elif collision == "outputs":
        audit = report
    else:
        report = mapping
    originals = {p: p.read_bytes() for p in (source, mapping)}
    with pytest.raises(SystemExit) as error:
        main(
            [
                str(source),
                "--period",
                "Q3",
                "--dollar-threshold",
                "100",
                "--percent-threshold",
                "5",
                "--type-map",
                str(mapping),
                "--output",
                str(report),
                "--audit-json",
                str(audit),
            ]
        )
    assert error.value.code == 2
    assert all(p.read_bytes() == content for p, content in originals.items())


def test_cli_missing_file_has_actionable_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        main(
            [
                str(tmp_path / "missing.csv"),
                "--period",
                "Q3",
                "--dollar-threshold",
                "100",
                "--percent-threshold",
                "5",
            ]
        )
    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_fingerprint_includes_nonmaterial_analysis_rows():
    first = analyze_rows([row("Sales A", 100, 100), row("Sales B", 100, 100)], CFG)
    second = analyze_rows([row("Sales A", 100, 101), row("Sales B", 100, 99)], CFG)
    assert (
        build_audit_record(first)["analysis_fingerprint"]
        != build_audit_record(second)["analysis_fingerprint"]
    )


def test_excel_blank_rows_are_ignored(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "input.xlsx"
    wb = Workbook()
    wb.active.append(["Line Item", "Budget", "Actual"])
    wb.active.append(["Revenue", 100, 120])
    wb.active.append([None, None, None])
    wb.active.append(["Rent", 10, 12])
    wb.save(path)
    result = analyze_rows(load_file(path), CFG)
    assert len(result.rows) == 2


def test_duplicate_json_fields_are_rejected():
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_json_text('[{"Line Item":"Revenue","Budget":100,"Actual":110,"Actual":999}]')


def test_explicit_unknown_classification_is_not_overridden_by_label():
    result = analyze_rows([row("Sales", Type="Unclassified")], CFG)
    assert result.rows[0].line_type == LineType.UNCLASSIFIED


def test_conflicting_budget_aliases_are_rejected():
    with pytest.raises(ValueError, match="multiple|Multiple|ambiguous"):
        analyze_rows([row(Plan=999)], CFG)


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_cli_detects_input_aliases(tmp_path, alias_kind):
    source = tmp_path / "input.csv"
    source.write_text("Line Item,Budget,Actual\nRevenue,100,120\n")
    original = source.read_bytes()
    output = tmp_path / "report.md"
    if alias_kind == "symlink":
        output.symlink_to(source)
    else:
        output.hardlink_to(source)
    with pytest.raises(SystemExit) as error:
        main(
            [
                str(source),
                "--period",
                "Q3",
                "--dollar-threshold",
                "100",
                "--percent-threshold",
                "5",
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2
    assert source.read_bytes() == original


def test_excel_data_under_blank_header_is_rejected(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "input.xlsx"
    wb = Workbook()
    wb.active.append(["Line Item", "Budget", "Actual", None])
    wb.active.append(["Revenue", 100, 120, 999])
    wb.save(path)
    with pytest.raises(ValueError, match="blank header"):
        load_file(path)


def test_mixed_nested_summaries_are_rejected_when_scope_is_ambiguous():
    with pytest.raises(ValueError, match="ambiguous"):
        analyze_rows([row(), row("Subtotal Revenue"), row("Total Revenue")], CFG)


def test_cli_real_report_and_audit_agree(tmp_path):
    import hashlib
    import json

    source = tmp_path / "input.csv"
    source.write_text("Line Item,Budget,Actual\nSales,1000,1200\nRent,500,550\n")
    report, audit = tmp_path / "report.md", tmp_path / "audit.json"
    assert (
        main(
            [
                str(source),
                "--period",
                "Q3",
                "--dollar-threshold",
                "10",
                "--percent-threshold",
                "5",
                "--output",
                str(report),
                "--audit-json",
                str(audit),
            ]
        )
        == 0
    )
    record = json.loads(audit.read_text())
    assert record["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["totals"]["net_operating_variance"] == "150"
    assert "$150.00" in report.read_text()
