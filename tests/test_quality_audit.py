from dataclasses import replace
from decimal import Decimal, localcontext
import json

import pytest

from variance_agent.analysis import analyze_rows, _verify_result
from variance_agent.cli import main, _load_type_map
from variance_agent.models import AnalysisConfig, ComparisonBasis, Status
from variance_agent.parsing import load_json_text, load_json_value, parse_decimal

CFG = AnalysisConfig("Q3", Decimal("10"), Decimal(".05"))


def result():
    return analyze_rows(
        [
            {"Line Item": "Sales", "Budget": 100, "Actual": 120},
            {"Line Item": "Rent", "Budget": 50, "Actual": 70},
        ],
        CFG,
    )


@pytest.mark.parametrize("value", ["1,00", "12$34", "$$100", "(-100)", "(+100)", "1__00", True])
def test_ambiguous_financial_numbers_are_rejected(value):
    with pytest.raises(ValueError):
        parse_decimal(value, field="Budget", line_item="Sales")


def test_accounting_sign_does_not_round_source_digits():
    with localcontext() as ctx:
        ctx.prec = 4
        assert parse_decimal("(123456.78)", field="Budget", line_item="Sales") == Decimal(
            "-123456.78"
        )


def test_json_wrapper_cannot_silently_choose_between_datasets():
    with pytest.raises(ValueError, match="rows.*data|ambiguous"):
        load_json_text('{"rows": [], "data": [{"Line Item":"Sales","Budget":1,"Actual":2}]}')


@pytest.mark.parametrize('opening, closing', [('[', ']'), ('{"nested":', '}')])
def test_excessive_json_nesting_is_a_validation_error(opening, closing):
    payload = opening * 10_000 + '0' + closing * 10_000
    with pytest.raises(ValueError, match='JSON nesting exceeds the supported depth'):
        load_json_value(payload)


@pytest.mark.parametrize('opening, closing', [('[', ']'), ('{"nested":', '}')])
@pytest.mark.parametrize('terminal', ['0', '[]', '{}'])
@pytest.mark.parametrize('depth', [128, 129])
def test_json_container_depth_limit(opening, closing, terminal, depth):
    wrappers = depth - (terminal in ('[]', '{}'))
    payload = opening * wrappers + terminal + closing * wrappers
    if depth == 128:
        assert load_json_value(payload) is not None
    else:
        with pytest.raises(ValueError, match='JSON nesting exceeds the supported depth'):
            load_json_value(payload)


def test_json_depth_limit_ignores_width_and_container_characters_in_strings():
    payload = {'label': '[{"nested":' * 1_000, 'rows': [[], {}] * 128, 'amount': 1.25}
    assert load_json_value(json.dumps(payload)) == {**payload, 'amount': Decimal('1.25')}


@pytest.mark.parametrize('location', ['input', 'type_map'])
def test_cli_rejects_excessive_json_nesting_without_overwriting_outputs(tmp_path, capsys, location):
    nested = '[' * 10_000 + '0' + ']' * 10_000
    source = tmp_path / ('source.json' if location == 'input' else 'source.csv')
    source.write_text(nested if location == 'input' else 'Line Item,Budget,Actual\nSales,100,120\n')
    report, audit = tmp_path / 'report.md', tmp_path / 'audit.json'
    report.write_text('Existing report')
    audit.write_text('Existing audit')
    options = [str(source), '--period', 'Q3', '--dollar-threshold', '10',
               '--percent-threshold', '5', '--output', str(report), '--audit-json', str(audit)]
    if location == 'type_map':
        mapping = tmp_path / 'map.json'
        mapping.write_text(nested)
        options.extend(['--type-map', str(mapping)])
    with pytest.raises(SystemExit) as error:
        main(options)
    assert error.value.code == 2
    assert 'JSON nesting exceeds the supported depth' in capsys.readouterr().err
    assert report.read_text() == 'Existing report'
    assert audit.read_text() == 'Existing audit'


def test_type_map_duplicate_keys_are_rejected(tmp_path):
    mapping = tmp_path / "types.json"
    mapping.write_text('{"Sales":"Revenue","Sales":"Expense"}')
    with pytest.raises(ValueError, match="Duplicate"):
        _load_type_map(str(mapping))


def test_conflicting_type_aliases_are_rejected():
    with pytest.raises(ValueError, match="multiple"):
        analyze_rows(
            [
                {
                    "Line Item": "Sales",
                    "Budget": 100,
                    "Actual": 120,
                    "Type": "Revenue",
                    "Classification": "Expense",
                }
            ],
            CFG,
        )


@pytest.mark.parametrize(
    "corruption",
    [
        "row_percent",
        "row_percent_label",
        "row_status",
        "missing_material",
        "duplicate_material",
        "aggregate_percent",
        "aggregate_status",
        "aggregate_variance",
    ],
)
def test_final_verification_rejects_corrupted_results(corruption):
    analysis = result()
    rows, materials = list(analysis.rows), list(analysis.material_rows)
    revenue = analysis.revenue
    if corruption == "row_percent":
        rows[0] = replace(rows[0], variance_percent=Decimal("999"))
    elif corruption == "row_percent_label":
        rows[0] = replace(rows[0], percent_label="N/A (Unbudgeted)")
    elif corruption == "row_status":
        rows[0] = replace(rows[0], status=Status.UNFAVORABLE)
    elif corruption == "missing_material":
        materials = []
    elif corruption == "duplicate_material":
        materials.append(materials[-1])
    elif corruption == "aggregate_percent":
        revenue = replace(revenue, variance_percent=Decimal("999"))
    elif corruption == "aggregate_status":
        revenue = replace(revenue, status=Status.UNFAVORABLE)
    elif corruption == "aggregate_variance":
        revenue = replace(revenue, variance_dollars=Decimal("999"))
    with pytest.raises(RuntimeError, match="Final verification failed"):
        _verify_result(rows, materials, revenue, analysis.expenses, CFG)


def cli_args(source, report, audit):
    return [
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


def test_invalid_audit_destination_preserves_existing_report(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("Line Item,Budget,Actual\nSales,100,120\n")
    report = tmp_path / "report.md"
    report.write_text("previous report")
    audit = tmp_path / "audit.json"
    audit.mkdir()
    with pytest.raises(SystemExit) as error:
        main(cli_args(source, report, audit))
    assert error.value.code == 2
    assert report.read_text() == "previous report"


def test_missing_excel_extra_is_actionable(tmp_path, monkeypatch, capsys):
    import builtins

    original_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(SystemExit) as error:
        main(
            [
                str(tmp_path / "input.xlsx"),
                "--period",
                "Q3",
                "--dollar-threshold",
                "10",
                "--percent-threshold",
                "5",
            ]
        )
    assert error.value.code == 2
    assert "optional dependency" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$1,234.50", "1234.50"),
        ("-$1,234.50", "-1234.50"),
        ("$-1,234.50", "-1234.50"),
        ("(£1,234.50)", "-1234.50"),
        ("€ .50", ".50"),
        ("+12.5e2", "1250"),
        ("1_000.25", "1000.25"),
    ],
)
def test_supported_number_formats_are_preserved(text, expected):
    assert parse_decimal(text, field="Actual", line_item="Sales") == Decimal(expected)


def test_staging_failure_preserves_both_outputs_and_removes_temporary_files(tmp_path, monkeypatch):
    import tempfile

    source = tmp_path / "source.csv"
    source.write_text("Line Item,Budget,Actual\nSales,100,120\n")
    report, audit = tmp_path / "report.md", tmp_path / "audit.json"
    report.write_text("old report")
    audit.write_text("old audit")
    original_tempfile = tempfile.NamedTemporaryFile
    calls = 0

    def fail_second_stage(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated disk error")
        return original_tempfile(*args, **kwargs)

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", fail_second_stage)
    with pytest.raises(SystemExit) as error:
        main(cli_args(source, report, audit))
    assert error.value.code == 2
    assert report.read_text() == "old report"
    assert audit.read_text() == "old audit"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["audit.json", "report.md", "source.csv"]


def test_failed_atomic_replace_does_not_truncate_existing_file(tmp_path, monkeypatch):
    import os
    from variance_agent.audit import write_audit_json

    destination = tmp_path / "audit.json"
    destination.write_text("original audit")

    def fail_replace(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        write_audit_json(destination, {"test": True})
    assert destination.read_text() == "original audit"
    assert list(tmp_path.iterdir()) == [destination]


def test_output_paths_cannot_contain_one_another(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("Line Item,Budget,Actual\nSales,100,120\n")
    report = tmp_path / "output"
    with pytest.raises(SystemExit) as error:
        main(cli_args(source, report, report / "audit.json"))
    assert error.value.code == 2
    assert not report.exists()


# Limit, benchmark and target need per-row declarations (R13-R15) and have their own oracles in test_bases.py.
@pytest.mark.parametrize("basis", [b for b in ComparisonBasis if b.value not in {"limit", "benchmark", "target"}])
def test_financial_invariants_against_independent_fraction_oracle(basis):
    from fractions import Fraction
    from random import Random
    from variance_agent.comparison import zero_comparison_label
    from variance_agent.models import LineType

    rng = Random(20260928)
    for _ in range(250):
        budget = rng.choice([0, rng.randint(-100000, 100000)])
        actual = rng.randint(-100000, 100000)
        kind = rng.choice([LineType.REVENUE, LineType.EXPENSE, LineType.UNCLASSIFIED])
        dollars = rng.randint(0, 100000)
        cfg = AnalysisConfig("Q3", Decimal(dollars), Decimal(".05"), comparison_basis=basis)
        analyzed = analyze_rows(
            [{"Line Item": "Item", "Budget": budget, "Actual": actual, "Type": kind}], cfg
        )
        row = analyzed.rows[0]
        difference = actual - budget
        ratio = Fraction(difference, abs(budget)) if budget else (Fraction(0) if not actual else None)
        material = abs(difference) > dollars or (ratio is not None and abs(ratio) > Fraction(1, 20))
        expected_status = (
            Status.NEUTRAL
            if not difference
            else Status.UNCLASSIFIED
            if kind == LineType.UNCLASSIFIED
            else Status.FAVORABLE
            if ((difference > 0) == (kind == LineType.REVENUE))
            else Status.UNFAVORABLE
        )
        assert row.variance_dollars == difference
        assert row.material == material
        assert row.status == expected_status
        if ratio is None:
            assert row.variance_percent is None
            assert row.percent_label == zero_comparison_label(basis)
        else:
            assert abs(Fraction(row.variance_percent) - ratio) < Fraction(1, 10**20)
        assert len(analyzed.material_rows) == int(material)


def test_csv_json_and_excel_have_equivalent_analysis_fingerprints(tmp_path):
    from openpyxl import Workbook
    from variance_agent.audit import build_audit_record
    from variance_agent.parsing import load_file

    csv_path, json_path, excel_path = [tmp_path / f"input.{ext}" for ext in ("csv", "json", "xlsx")]
    csv_path.write_text("Line Item,Budget,Actual\nSales,100.25,120.75\nRent,50.25,60.75\n")
    json_path.write_text(
        '[{"Line Item":"Sales","Budget":100.25,"Actual":120.75},'
        '{"Line Item":"Rent","Budget":50.25,"Actual":60.75}]'
    )
    wb = Workbook()
    wb.active.append(["Line Item", "Budget", "Actual"])
    wb.active.append(["Sales", 100.25, 120.75])
    wb.active.append(["Rent", 50.25, 60.75])
    wb.save(excel_path)
    fingerprints = [
        build_audit_record(analyze_rows(load_file(path), CFG))["analysis_fingerprint"]
        for path in (csv_path, json_path, excel_path)
    ]
    assert len(set(fingerprints)) == 1
