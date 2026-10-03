import json
from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent.analysis import analyze_rows
from variance_agent.audit import build_audit_record
from variance_agent.cli import main
from variance_agent.models import AnalysisConfig
from variance_agent.report import render_markdown


def test_mixed_currency_reproduction_is_rejected_before_aggregation():
    rows = [{"Line Item":"US Sales", "Budget":"$10", "Actual":"$12"},
            {"Line Item":"EU Sales", "Budget":"€20", "Actual":"€24"}]
    with pytest.raises(ValueError, match="currency"):
        analyze_rows(rows, AnalysisConfig("Q3", Decimal("1"), Decimal(".05")))


def test_cli_currency_conflict_preserves_existing_outputs(tmp_path):
    source = tmp_path / "mixed.csv"
    source.write_text("Line Item,Budget,Actual\nUS Sales,$10,$12\nEU Sales,€20,€24\n",
                      encoding="utf-8")
    report, audit = tmp_path / "report.md", tmp_path / "audit.json"
    report.write_text("prior report")
    audit.write_text("prior audit")
    with pytest.raises(SystemExit) as error:
        main([str(source), "--period", "Q3", "--dollar-threshold", "1",
              "--percent-threshold", "5", "--output", str(report), "--audit-json", str(audit)])
    assert error.value.code == 2
    assert report.read_text() == "prior report"
    assert audit.read_text() == "prior audit"


@pytest.mark.parametrize("code,symbol", [("USD", "$"), ("EUR", "€"), ("GBP", "£")])
def test_selected_currency_applies_to_all_report_and_driver_amounts(code, symbol):
    rows = [{"Line Item":"Sales Revenue", "Currency":code,
             "Budget":f"{symbol}100", "Actual":f"{symbol}132",
             "Budget Units":"10", "Actual Units":"12",
             "Budget Price":f"{symbol}10", "Actual Price":f"{symbol}11"},
            {"Line Item":"Rent Expense", "Budget":"50", "Actual":"40"}]
    result = analyze_rows(rows, AnalysisConfig("Q3", Decimal("1"), Decimal(".05"),
                                             currency=code))
    report = render_markdown(result)
    assert f"Reporting Currency: {code}" in report
    assert f"{symbol}132.00" in report
    assert f"Units effect: {symbol}20.00" in report
    assert f"Var ({symbol})" in report
    assert build_audit_record(result)["currency"] == code
    assert result.revenue.variance_dollars == Decimal("32")


@pytest.mark.parametrize("row", [
    {"Currency":"EUR"}, {"Currency":"CAD"}, {"Currency":False},
    {"Budget":"£10"}, {"Actual":"(€12)"},
    {"Budget Units":"1", "Actual Units":"1", "Budget Price":"€10", "Actual Price":"€12"},
])
def test_currency_conflicts_are_not_silently_reinterpreted(row):
    source = {"Line Item":"Sales", "Budget":"10", "Actual":"12"} | row
    with pytest.raises(ValueError, match="currency|Currency"):
        analyze_rows([source], AnalysisConfig("Q3", Decimal("1"), Decimal(".05")))


def test_cli_euro_report_and_versioned_audit(tmp_path):
    source = tmp_path / "eur.json"
    source.write_text('[{"Line Item":"Sales", "Budget":"€10", "Actual":"€12"}]')
    report, audit = tmp_path / "eur.md", tmp_path / "eur.audit.json"
    assert main([str(source), "--period", "Q3", "--dollar-threshold", "1",
                 "--percent-threshold", "5", "--currency", "EUR",
                 "--output", str(report), "--audit-json", str(audit)]) == 0
    assert "€12.00" in report.read_text()
    assert json.loads(audit.read_text())["currency"] == "EUR"


def test_legacy_audit_cannot_hide_non_usd_currency():
    result = analyze_rows([{"Line Item":"Sales", "Budget":"10", "Actual":"12"}],
                          AnalysisConfig("Q3", Decimal("1"), Decimal(".05"), currency="EUR"))
    with pytest.raises(ValueError, match="1.0.*USD"):
        build_audit_record(result, schema_version="1.0")


@pytest.mark.parametrize("code", ["CAD", "", None, True])
def test_public_api_rejects_unsupported_currency(code):
    with pytest.raises(ValueError, match="currency"):
        analyze_rows([{"Line Item":"Sales", "Budget":"10", "Actual":"12"}],
                     AnalysisConfig("Q3", Decimal("1"), Decimal(".05"), currency=code))


@pytest.mark.parametrize("threshold", ["$1", "€1", "£1"])
def test_thresholds_cannot_discard_currency_symbols(tmp_path, threshold):
    source = tmp_path / "source.csv"
    source.write_text("Line Item,Budget,Actual\nSales,10,12\n")
    with pytest.raises(SystemExit) as error:
        main([str(source), "--period", "Q3", "--dollar-threshold", threshold,
              "--percent-threshold", "5", "--currency", "EUR"])
    assert error.value.code == 2


@pytest.mark.parametrize("code", ["EUR", "GBP"])
def test_full_non_usd_report_golden(code):
    fixtures = Path(__file__).parent / "fixtures" / "contracts"
    payload = json.loads((fixtures / "complete.input.json").read_text("utf-8"))
    result = analyze_rows(payload["rows"], AnalysisConfig("Q3 2026", Decimal("100"),
                                                        Decimal(".05"), currency=code))
    assert render_markdown(result) == (fixtures / f"complete.{code}.report.md").read_text("utf-8")
