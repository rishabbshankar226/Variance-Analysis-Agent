"""Fictional multi-comparison joins and independently verifiable child audits."""
from decimal import Decimal
import json
from pathlib import Path
from jsonschema import Draft202012Validator
import pytest

from variance_agent.comparisons import analyze_comparisons, build_comparison_audit, render_comparisons
from variance_agent.models import ComparisonBasis as Basis
from variance_agent.cli import main
from test_multi_audience_measures import config


def test_set_preserves_basis_order_and_estimate_against_consensus():
    table = analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "Consensus": "100", "Our Est.": "105",
                                 "Prior Year": "90", "Actual": "110"}], config(), (Basis.CONSENSUS, Basis.ESTIMATE, Basis.PRIOR_PERIOD))
    assert [c.basis for c in table.comparisons] == [Basis.CONSENSUS, Basis.ESTIMATE, Basis.PRIOR_PERIOD]
    assert table.estimate_vs_consensus[0].variance == Decimal("5")
    assert table.estimate_vs_consensus[0].variance_percent == Decimal("0.05")
    text = render_comparisons(table)
    assert text.count("| Line Item |") == 1
    assert "Estimate" in text and "Consensus" in text and "Prior Period" in text
    record = build_comparison_audit(table)
    schema = json.loads((Path(__file__).parents[1] / "schemas/audit-1.8.schema.json").read_text())
    Draft202012Validator(schema).validate(record)
    assert len(record["comparisons"]) == 3
    for child in record["comparisons"]:
        Draft202012Validator(schema).validate(child)
        assert child["comparisons"] == []


def test_set_does_not_pair_ambiguous_duplicate_metrics():
    rows = [{"Line Item": "Revenue", "Consensus": "100", "Model": "105", "Actual": "110"}] * 2
    with pytest.raises(ValueError, match="Revenue.*unique"):
        analyze_comparisons(rows, config(), (Basis.CONSENSUS, Basis.ESTIMATE))


def test_cli_comma_list_and_legacy_metadata_are_opt_in(tmp_path, capsys):
    source = tmp_path / "fictional.csv"
    source.write_text("Line Item,Type,Budget,Consensus,Model,Actual\nRevenue,Revenue,90,100,105,110\n")
    common = [str(source), "--period", "3Q26", "--dollar-threshold", "10", "--percent-threshold", "2"]
    assert main(common) == 0
    assert "Consensus" not in capsys.readouterr().out
    assert main([*common, "--compare-to", "consensus,estimate"]) == 0
    output = capsys.readouterr()
    assert "Consensus" in output.out and "Estimate" in output.out


def test_missing_only_audit_validates_and_forged_estimate_gaps_are_rejected():
    from dataclasses import replace
    missing = analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "Consensus": "", "Actual": "110"}],
                                 config(), (Basis.CONSENSUS,))
    schema = json.loads((Path(__file__).parents[1] / "schemas/audit-1.8.schema.json").read_text())
    Draft202012Validator(schema).validate(build_comparison_audit(missing))
    table = analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "Consensus": "100", "Model": "105", "Actual": "110"}],
                               config(), (Basis.CONSENSUS, Basis.ESTIMATE))
    forged = replace(table, estimate_vs_consensus=(replace(table.estimate_vs_consensus[0], variance=Decimal("6")),))
    with pytest.raises(RuntimeError, match="Estimate.*Consensus.*mismatch"):
        build_comparison_audit(forged)


def test_assisted_csv_mapping_preserves_raw_estimator_identity_and_missing_cells(tmp_path, capsys):
    import hashlib
    source = tmp_path / "fictional.csv"
    source.write_text("Fictional Halvorsen Instruments\nLine Item,Type,Est.,# Est.,Actual\n"
                      "Revenue,Revenue,100,12,110\nOther Revenue,Revenue,,12,5\n")
    mapping = tmp_path / "layout.json"
    mapping.write_text(json.dumps({"comparison_basis": "consensus", "column_mapping": {"consensus": "Est.", "estimator_count": "# Est."}}))
    audit = tmp_path / "audit.json"
    assert main([str(source), "--mapping", str(mapping), "--period", "3Q26", "--dollar-threshold", "10", "--percent-threshold", "2",
                 "--audit-json", str(audit)]) == 0
    record = json.loads(audit.read_text())
    assert record["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert record["comparison_details"][0]["estimator_count"] == 12
    assert record["unavailable_comparisons"][0]["line_item"] == "Other Revenue"
    assert "No consensus" in capsys.readouterr().out


def test_earnings_preset_detects_guidance_range(tmp_path, capsys):
    source = Path(__file__).parent / "fixtures/multi_audience/guidance.csv"
    assert main([str(source), "--preset", "earnings", "--period", "3Q26", "--dollar-threshold", "10", "--percent-threshold", "2"]) == 0
    assert "Above range" in capsys.readouterr().out


def test_mapping_can_choose_model_and_guidance_point_over_other_candidates(tmp_path, capsys):
    source = tmp_path / "fictional.csv"
    source.write_text("Line Item,Type,Our Est.,Model,Guide,Guidance Low,Guidance High,Actual\nRevenue,Revenue,101,105,108,90,110,112\n")
    mapping = tmp_path / "layout.json"
    mapping.write_text(json.dumps({"comparison_bases": ["estimate", "guidance"],
                                   "column_mapping": {"estimate": "Model", "guidance": "Guide"}}))
    assert main([str(source), "--mapping", str(mapping), "--period", "3Q26", "--dollar-threshold", "10", "--percent-threshold", "2"]) == 0
    out = capsys.readouterr()
    assert "Estimate" in out.out and "$105.00" in out.out and "$108.00" in out.out


def test_combined_workbook_includes_estimate_against_consensus():
    import io
    from zipfile import ZipFile
    from variance_agent.xlsx import render_comparison_xlsx
    table = analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "Consensus": "100", "Model": "105", "Actual": "110"}],
                               config(), (Basis.CONSENSUS, Basis.ESTIMATE))
    with ZipFile(io.BytesIO(render_comparison_xlsx(table))) as archive:
        xml = archive.read("xl/worksheets/sheet1.xml").decode()
    assert "Estimate - Consensus" in xml and "$5.00" in xml
