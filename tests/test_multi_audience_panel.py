"""Deterministic failure isolation for entirely fictional entities."""
import csv
import hashlib
import json
from pathlib import Path
from decimal import Decimal

import pytest

from variance_agent.api import analyze_panel, AudienceOptions, PanelOptions
from variance_agent.audience import AudienceConfig
from variance_agent.models import ComparisonBasis
from variance_agent.cli import main
from variance_agent.long_output import long_csv, long_jsonl, errors_csv

FIXTURE = Path("tests/fixtures/multi_audience/panel.csv")


def options(period: str = "") -> PanelOptions:
    return PanelOptions(config=AudienceConfig(period, Decimal("10"), Decimal(".02")),
                        audience=AudienceOptions(bases=(ComparisonBasis.CONSENSUS,)))


def test_scenario_c_api_and_cli(tmp_path: Path) -> None:
    from variance_agent.parsing import load_input
    payload = FIXTURE.read_bytes()
    rows = load_input(payload, ".csv").rows
    batch = analyze_panel(rows, group_by=("Ticker", "Period"), options=options())
    assert len([g for g in batch.groups if g.analysis is not None]) == 5
    bad = [g for g in batch.groups if g.error]
    assert len(bad) == 1
    assert bad[0].keys == ("CORD.FAKE", "3Q26")
    assert "TBD" in bad[0].error
    assert len(list(csv.DictReader(long_csv(batch).splitlines()))) == 5
    assert len(errors_csv(batch).splitlines()) == 2
    assert all(row["source_sha256"] is None for row in map(json.loads, long_jsonl(batch).splitlines()))
    args = [str(FIXTURE), "--group-by", "Ticker,Period", "--compare-to", "consensus",
            "--dollar-threshold", "10", "--percent-threshold", "2", "--long-output", str(tmp_path / "long.csv"),
            "--long-output-jsonl", str(tmp_path / "long.jsonl"), "--errors-output", str(tmp_path / "errors.csv")]
    assert main(args) == 3
    before = [p.read_bytes() for p in sorted(tmp_path.iterdir())]
    assert main(args) == 3
    assert before == [p.read_bytes() for p in sorted(tmp_path.iterdir())]
    records = [json.loads(line) for line in (tmp_path / "long.jsonl").read_text().splitlines()]
    assert len(records) == 5
    assert {r["source_sha256"] for r in records} == {hashlib.sha256(payload).hexdigest()}
    halv = next(r for r in records if r["Ticker"] == "HALV.FAKE")
    assert halv["comparison"] == "1250.0"
    assert halv["variance"] == "37.5"
    assert halv["display_label"] == "Beat"
    assert halv["material"] is True


def test_period_rules_and_global_key_errors() -> None:
    rows = [{"Ticker": "HALV.FAKE", "Period": "3Q26", "Line Item": "Revenue", "Consensus": "1", "Actual": "2"}]
    with pytest.raises(ValueError, match="Period.*configured period"):
        analyze_panel(rows, group_by=("Ticker", "Period"), options=options("3Q26"))
    with pytest.raises(ValueError, match="period.*required"):
        analyze_panel(rows, group_by=("Ticker",), options=options())
    with pytest.raises(ValueError, match="group key.*Missing"):
        analyze_panel(rows, group_by=("Missing",), options=options("3Q26"))
    with pytest.raises(ValueError, match="distinct"):
        analyze_panel(rows, group_by=("Ticker", "ticker"), options=options("3Q26"))
    with pytest.raises(ValueError, match="no data"):
        analyze_panel([], group_by=("Ticker",), options=options("3Q26"))


def test_every_failed_group_has_one_error() -> None:
    rows = [{"Ticker": "HALV.FAKE", "Period": "3Q26", "Line Item": "EPS", "Consensus": "1", "Actual": "TBD"}]
    batch = analyze_panel(rows, group_by=("Ticker", "Period"), options=options())
    assert len(batch.groups) == 1 and batch.groups[0].analysis is None
    assert "TBD" in batch.groups[0].error
    assert len(long_jsonl(batch).splitlines()) == 0
    assert len(errors_csv(batch).splitlines()) == 2


def cli_args(source: Path, destination: Path) -> list[str]:
    return [str(source), "--group-by", "Ticker,Period", "--compare-to", "consensus", "--dollar-threshold", "10",
            "--percent-threshold", "2", "--long-output", str(destination), "--errors-output", str(destination.with_suffix(".errors"))]


@pytest.mark.parametrize("kind", ["same", "symlink", "hardlink"])
def test_panel_outputs_cannot_replace_input(tmp_path: Path, kind: str) -> None:
    source = tmp_path / "input.csv"
    source.write_bytes(FIXTURE.read_bytes())
    destination = source if kind == "same" else tmp_path / "alias.csv"
    if kind == "symlink":
        destination.symlink_to(source)
    elif kind == "hardlink":
        import os
        os.link(source, destination)
    before = source.read_bytes()
    with pytest.raises(SystemExit) as failure:
        main(cli_args(source, destination))
    assert failure.value.code == 2
    assert source.read_bytes() == before


def test_duplicate_output_and_period_rejected_before_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "existing.csv"
    destination.write_text("preserve me")
    args = cli_args(FIXTURE, destination)
    args[-1] = str(destination)
    with pytest.raises(SystemExit) as failure:
        main(args)
    assert failure.value.code == 2
    assert "distinct" in capsys.readouterr().err
    assert destination.read_text() == "preserve me"
    with pytest.raises(SystemExit) as failure:
        main([*cli_args(FIXTURE, destination), "--period", "3Q26"])
    assert failure.value.code == 2
    assert "--period" in capsys.readouterr().err
    assert destination.read_text() == "preserve me"


def test_one_ambiguous_group_does_not_prompt_or_sink_another() -> None:
    rows = [{"Ticker": name, "Period": "3Q26", "Line Item": "Margin", "Consensus": "40%", "Actual": "41%",
             "Measure": "Percent", "Better": better} for name, better in (("HALV.FAKE", "Higher"), ("CORD.FAKE", ""))]
    cfg = AudienceConfig("", Decimal("10"), Decimal(".02"), bps_threshold=Decimal("25"))
    batch = analyze_panel(rows, group_by=("Ticker", "Period"), options=PanelOptions(config=cfg,
                            audience=AudienceOptions(bases=(ComparisonBasis.CONSENSUS,))))
    assert len([g for g in batch.groups if g.error]) == 1
    assert "Better" in batch.groups[0].error
    success = next(g for g in batch.groups if g.analysis)
    assert success.analysis.comparisons[0].result.rows[0].variance_bps == Decimal("100")


def test_staging_failure_preserves_existing_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import variance_agent.output as output
    destination = tmp_path / "existing.csv"
    errors = destination.with_suffix(".errors")
    destination.write_text("original report")
    errors.write_text("original errors")
    original = output.tempfile.NamedTemporaryFile
    calls = 0
    def fail_second(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("fictional staging failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(output.tempfile, "NamedTemporaryFile", fail_second)
    with pytest.raises(SystemExit) as failure:
        main(cli_args(FIXTURE, destination))
    assert failure.value.code == 2
    assert destination.read_text() == "original report"
    assert errors.read_text() == "original errors"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["existing.csv", "existing.errors"]


def test_unclassified_currency_group_requires_explicit_direction_or_type() -> None:
    rows = [{"Ticker": "HALV.FAKE", "Period": "3Q26", "Line Item": "Mystery Metric", "Consensus": "1", "Actual": "2"}]
    batch = analyze_panel(rows, group_by=("Ticker", "Period"), options=options())
    assert batch.groups[0].analysis is None
    assert "Type or Better" in batch.groups[0].error


@pytest.mark.parametrize("group_by", [("status",), ("error",)])
def test_reserved_group_columns_refused(group_by: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="reserved"):
        analyze_panel([{"status": "HALV.FAKE", "error": "HALV.FAKE", "Actual": "1", "Consensus": "0", "Line Item": "Revenue"}],
                      group_by=group_by, options=options("3Q26"))


def test_missing_threshold_and_duplicate_identity_fail_their_groups() -> None:
    row = {"Ticker": "HALV.FAKE", "Period": "3Q26", "Line Item": "EPS", "Consensus": "1", "Actual": "2",
           "Measure": "Per Share"}
    batch = analyze_panel([row], group_by=("Ticker", "Period"), options=options())
    assert "--per-share-threshold" in batch.groups[0].error
    money = {**row, "Measure": "Currency", "Type": "Revenue"}
    batch = analyze_panel([money, money], group_by=("Ticker", "Period"), options=options())
    assert "Duplicate line item" in batch.groups[0].error


def test_cli_explicit_segment_mapping_enables_flat_groups(tmp_path: Path) -> None:
    source = tmp_path / "HALV.FAKE.csv"
    source.write_text("Line Item,Budget,Actual,Type,Area\nRevenue,100,110,Revenue,North\nRevenue,200,210,Revenue,South\n")
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"column_mapping": {"line_item": "Line Item", "budget": "Budget", "actual": "Actual",
                                                        "type": "Type", "segment": "Area"}}))
    output = tmp_path / "report.md"
    assert main([str(source), "--period", "3Q26", "--dollar-threshold", "10", "--percent-threshold", "2",
                 "--mapping", str(mapping), "-o", str(output)]) == 0
    assert "Segment: North" in output.read_text()
    assert "Segment: South" in output.read_text()
