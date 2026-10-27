"""R17: derived metrics declared in a mapping file, never assumed (docs/analysts/PLAN.md). Every file is fictional."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing, quarter_all_filing
from variance_agent import cli

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "analysts"
COVENANTS = ("Line Item,Limit,Limit Kind,Buffer,Measure\nGross leverage,1.25x,Max,0.50,Multiple\n"
             "Interest cover,4.00x,Min,1.00,Multiple\n")
CASE = "Management case (in millions)\nLine Item,Budget\nLTM revenue,4250\nLTM EBITDA,1750\n"


def _clara(tmp_path: Path, *extra: str, metrics: Path | None = None, covenants: str = COVENANTS) -> list[str]:
    annual, schedule = tmp_path / "hal-20250927.htm", tmp_path / "covenants.csv"
    annual.write_bytes(all_statements_filing())
    schedule.write_text(covenants, encoding="utf-8")
    return [str(annual), "--assisted", "--metrics", str(metrics or FIXTURES / "clara_metrics.json"), "--compare-file",
            str(schedule), "--compare-to", "limit", "--period", "FY2025", "--dollar-threshold", "1",
            "--percent-threshold", "1", "--multiple-threshold", "0.1", *extra]


def _audit(argv: list[str], tmp_path: Path) -> tuple[dict[str, object], str]:
    audit, report = tmp_path / "audit.json", tmp_path / "r.md"
    assert cli.main([*argv, "--audit-json", str(audit), "-o", str(report)]) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads((ROOT / "schemas/audit-1.9.schema.json").read_text(encoding="utf-8"))).validate(record)
    return record, report.read_text(encoding="utf-8")


def test_clara_s_ratios_meet_her_covenant_limits(tmp_path: Path) -> None:
    record, report = _audit(_clara(tmp_path), tmp_path)
    rows = {r["line_item"]: r for r in record["measure_rows"]}  # type: ignore[union-attr, index]
    # Fraction oracle: debt 1,500 over EBITDA (1,450 + 50 interest added back + 200 D&A) = 1,700; cover 1,700 / 50.
    assert abs(Fraction(str(rows["Gross leverage"]["actual"])) - Fraction(1500, 1700)) < Fraction(1, 10**25)
    assert Fraction(str(rows["Interest cover"]["actual"])) == 34
    outcomes = {d["line_item"]: d["outcome"] for d in record["basis_details"]}  # type: ignore[union-attr, index]
    assert outcomes == {"Gross leverage": "Near", "Interest cover": "Within"}
    document = record["source"]["document"]  # type: ignore[index]
    assert document["kind"] == "metrics"
    leverage = next(m for m in document["metrics"] if m["name"] == "Gross leverage")
    assert leverage["formula"] == ("(Long-term debt [balance sheet, instant]) / (Net income [income, fy] - Interest expense "
                                   "[income, fy] + Depreciation and amortization [cash flow, fy])")
    assert [(t["document"], t["column"], t["context"], t["value"]) for t in leverage["terms"]][0] == (
        "hal-20250927.htm", "Sep 2025", "I25", "1500000000")
    assert ("Gross leverage = 0.88x = (Long-term debt \\[balance sheet, instant\\]) / (Net income \\[income, fy\\]"
            in report)


def test_a_metric_missing_a_term_is_left_out_by_name(tmp_path: Path) -> None:
    covenants = COVENANTS + "Fixed charge cover,1.50x,Min,,Multiple\n"
    record, report = _audit(_clara(tmp_path, covenants=covenants), tmp_path)
    notes = record["source"]["document"]["reader_notes"]  # type: ignore[index]
    message = ("Left out 'Fixed charge cover': no line with us-gaap:OperatingLeasePayments on the cash flow statement "
               "for fy, so it can't be computed")
    assert message in notes and message in report
    assert "Fixed charge cover" not in {r["line_item"] for r in record["measure_rows"]}  # type: ignore[union-attr, index]


def test_a_non_positive_denominator_is_nm_with_its_reason(tmp_path: Path) -> None:
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps({"metrics": [
        {"name": "Interest cover", "measure": "Multiple",
         "numerator": [{"concept": "us-gaap:NetIncomeLoss", "statement": "income", "period": "fy", "sign": 1}],
         "denominator": [{"concept": "us-gaap:InterestExpense", "statement": "income", "period": "fy", "sign": 1}]},
        {"name": "Gross leverage", "measure": "Multiple",
         "numerator": [{"concept": "us-gaap:LongTermDebtNoncurrent", "statement": "balance_sheet", "period": "instant",
                        "sign": 1}],
         "denominator": [{"concept": "us-gaap:NetIncomeLoss", "statement": "income", "period": "fy", "sign": 1}]}]}))
    record, report = _audit(_clara(tmp_path, metrics=metrics, covenants=COVENANTS), tmp_path)
    nm = "Interest cover: NM, because its denominator is -$50,000,000 (zero or negative)"
    assert nm in record["source"]["document"]["reader_notes"] and nm in report  # type: ignore[index]


def test_owen_s_ltm_revenue_and_ebitda_against_the_case(tmp_path: Path) -> None:
    quarter, annual, case = tmp_path / "hal-20260328.htm", tmp_path / "hal-20250927.htm", tmp_path / "case.csv"
    quarter.write_bytes(quarter_all_filing())
    annual.write_bytes(all_statements_filing())
    case.write_text(CASE, encoding="utf-8")
    metrics = tmp_path / "owen.json"
    definitions = json.loads((FIXTURES / "owen_metrics.json").read_text(encoding="utf-8"))
    for metric in definitions["metrics"]:
        metric["better"] = "Higher"
    metrics.write_text(json.dumps(definitions), encoding="utf-8")
    record, _ = _audit([str(quarter), "--assisted", "--ltm-from", str(annual), "--metrics", str(metrics),
                        "--compare-file", str(case), "--period", "LTM Mar 2026", "--dollar-threshold", "1",
                        "--percent-threshold", "1"], tmp_path)
    rows = {r["line_item"]: r for r in record["measure_rows"]}  # type: ignore[union-attr, index]
    # Fraction oracle: LTM = FY + YTD - prior YTD per term; EBITDA = net income + interest + D&A (from the cash flow).
    assert Fraction(str(rows["LTM revenue"]["actual"])) == (4100 + 2200 - 2000) * 10**6
    assert Fraction(str(rows["LTM EBITDA"]["actual"])) == ((1450 + 815 - 730) + (50 + 25 - 20) + (200 + 110 - 100)) * 10**6
    assert Fraction(str(rows["LTM EBITDA"]["comparison"])) == 1750 * 10**6
    assert (rows["LTM revenue"]["status"], rows["LTM EBITDA"]["status"], record["totals"]) == ("F", "F", None)


@pytest.mark.parametrize(("change", "message"), [
    ({"surprise": 1}, "Metrics file: unknown key 'surprise' in metric 'Gross leverage'."),
    ({"numerator": [{"concept": "us-gaap:Assets", "statement": "balance_sheet", "period": "quarterly", "sign": 1}]},
     "Metrics file: period must be instant, fy, ytd or ltm (metric 'Gross leverage')."),
    ({"numerator": [{"concept": "us-gaap:Assets", "statement": "balance_sheet", "period": "instant", "sign": 2}]},
     "Metrics file: sign must be 1 or -1 (metric 'Gross leverage')."),
])
def test_the_metrics_file_is_a_closed_structure(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                change: dict[str, object], message: str) -> None:
    definitions = json.loads((FIXTURES / "clara_metrics.json").read_text(encoding="utf-8"))
    definitions["metrics"][0].update(change)
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps(definitions), encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(_clara(tmp_path, metrics=metrics))
    assert message in capsys.readouterr().err.replace("\n", " ")


def test_metrics_need_a_comparison_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    annual = tmp_path / "hal-20250927.htm"
    annual.write_bytes(all_statements_filing())
    with pytest.raises(SystemExit):
        cli.main([str(annual), "--assisted", "--metrics", str(FIXTURES / "clara_metrics.json"), "--period", "FY2025",
                  "--dollar-threshold", "1", "--percent-threshold", "1"])
    assert ("--metrics needs --compare-file: the metrics are compared with the case or covenant schedule that file holds."
            in capsys.readouterr().err.replace("\n", " "))


def test_a_cash_balance_is_not_an_ltm_term(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    quarter, annual, case = tmp_path / "q.htm", tmp_path / "k.htm", tmp_path / "case.csv"
    quarter.write_bytes(quarter_all_filing())
    annual.write_bytes(all_statements_filing())
    case.write_text("Line Item,Budget\nLTM cash,1\n", encoding="utf-8")
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps({"metrics": [{"name": "LTM cash", "measure": "Currency", "better": "Higher", "numerator": [
        {"label": "Cash at end of period", "statement": "cash_flow", "period": "ltm", "sign": 1}]}]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(quarter), "--assisted", "--ltm-from", str(annual), "--metrics", str(metrics), "--compare-file",
                  str(case), "--period", "LTM", "--dollar-threshold", "1", "--percent-threshold", "1"])
    assert ("Left out 'LTM cash': 'Cash at end of period' is a cash balance, which doesn't add across periods, so it "
            "can't be an LTM term") in capsys.readouterr().err.replace("\n", " ")

