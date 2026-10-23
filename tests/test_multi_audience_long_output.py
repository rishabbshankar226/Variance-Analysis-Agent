"""Exact long output and spreadsheet formula text boundaries."""
import csv
import json
from decimal import Decimal

import pytest

from variance_agent.api import AudienceOptions, PanelOptions, analyze_panel
from variance_agent.audience import AudienceConfig
from variance_agent.long_output import long_csv, long_jsonl
from variance_agent.models import ComparisonBasis


@pytest.mark.parametrize("text", ["=1+1", "+cmd", "-cmd", "@cmd", " \t=1+1", "\x01@cmd"])
def test_formula_text_and_negative_numbers(text: str) -> None:
    batch = analyze_panel([{"Ticker": text, "Period": "3Q26", "Line Item": text, "Consensus": "-2", "Actual": "-1",
                            "Measure": "Per Share", "Better": "Higher"}], group_by=("Ticker", "Period"),
                          options=PanelOptions(config=AudienceConfig("", Decimal("1"), Decimal(".02"),
                                                                      per_share_threshold=Decimal(".01")),
                                               audience=AudienceOptions(bases=(ComparisonBasis.CONSENSUS,))))
    wire = next(csv.DictReader(long_csv(batch).splitlines()))
    assert wire["Ticker"] == "'" + text
    assert wire["line_item"].startswith("'")
    assert wire["comparison"] == "-2" and wire["actual"] == "-1"
    data = json.loads(long_jsonl(batch))
    assert data["Ticker"] == text
    assert data["comparison"] == "-2"
    assert data["variance_percent"] == "0.5"
    assert data["variance_bps"] is None
    assert data["material"] is True


def test_missing_and_real_zero_with_measure_and_basis_order() -> None:
    from variance_agent.long_output import long_rows
    rows = [{"Ticker": "HALV.FAKE", "Period": "3Q26", "Line Item": label, "Consensus": value,
             "Model": "1", "Actual": "1", "Type": "Revenue"} for label, value in (("Z metric", ""), ("A metric", "0"))]
    batch = analyze_panel(rows, group_by=("Ticker", "Period"), options=PanelOptions(
        config=AudienceConfig("", Decimal("10"), Decimal(".02")),
        audience=AudienceOptions(bases=(ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE))))
    records = long_rows(batch)
    assert [(r["line_item"], r["basis"]) for r in records] == [
        ("Z metric", "consensus"), ("Z metric", "estimate"), ("A metric", "consensus"), ("A metric", "estimate")]
    assert records[0]["comparison"] is None and records[0]["material"] is None
    assert records[2]["comparison"] == "0" and records[2]["material"] is False
    assert records[0]["display_label"] == ""
    assert records[2]["display_label"] == "In line"


def test_long_export_reverifies_derived_values() -> None:
    from dataclasses import replace
    from variance_agent.long_output import long_csv
    batch = analyze_panel([{"Ticker": "HALV.FAKE", "Period": "3Q26", "Line Item": "Revenue", "Consensus": "100",
                            "Actual": "110", "Type": "Revenue"}], group_by=("Ticker", "Period"), options=PanelOptions(
        config=AudienceConfig("", Decimal("10"), Decimal(".02")),
        audience=AudienceOptions(bases=(ComparisonBasis.CONSENSUS,))))
    group = batch.groups[0]
    table = group.analysis
    comparison = table.comparisons[0]
    result = comparison.result
    forged = replace(result, rows=(replace(result.rows[0], variance_dollars=Decimal("99")),))
    batch = replace(batch, groups=(replace(group, analysis=replace(table, comparisons=(replace(comparison, result=forged),))),))
    with pytest.raises(RuntimeError, match="variance mismatch"):
        long_csv(batch)


def test_long_export_refuses_incomplete_metric_index() -> None:
    from dataclasses import replace
    batch = analyze_panel([{"Ticker": "HALV.FAKE", "Period": "3Q26", "Line Item": "Revenue", "Consensus": "100",
                            "Actual": "110", "Type": "Revenue"}], group_by=("Ticker", "Period"), options=PanelOptions(
        config=AudienceConfig("", Decimal("10"), Decimal(".02")),
        audience=AudienceOptions(bases=(ComparisonBasis.CONSENSUS,))))
    group = batch.groups[0]
    with pytest.raises(RuntimeError, match="metric order"):
        long_csv(replace(batch, groups=(replace(group, analysis=replace(group.analysis, metric_order=())),)))
