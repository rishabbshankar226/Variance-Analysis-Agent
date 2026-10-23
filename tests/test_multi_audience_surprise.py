"""Descriptive statistics for fictional Halvorsen Instruments, HALV.FAKE."""
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
import csv
import json
from pathlib import Path

import jsonschema
import pytest

from variance_agent.api import AudienceOptions, analyze_table, analyze_panel, PanelOptions
from variance_agent.audience import AudienceConfig
from variance_agent.comparisons import build_comparison_audit, render_comparisons
from variance_agent.long_output import long_csv, long_jsonl
from variance_agent.models import ComparisonBasis
from variance_agent.surprise import SurpriseOptions, history_from_rows, load_history

HISTORY = Path("tests/fixtures/multi_audience/history.csv")


def config() -> AudienceConfig:
    return AudienceConfig("3Q26", Decimal("10"), Decimal(".02"), per_share_threshold=Decimal(".01"),
                          bps_threshold=Decimal("25"))


def actuals(**extra: object) -> list[dict[str, object]]:
    return [{"Ticker": "HALV.FAKE", "Line Item": "Diluted EPS", "Measure": "Per Share", "Consensus": "0.84",
             "Actual": "0.91", **extra}]


def analyze(history: object, window: int = 8):
    return analyze_table(actuals(), config(), options=AudienceOptions(bases=(ComparisonBasis.CONSENSUS,),
                         surprise=SurpriseOptions(history=history, window=window)))


@pytest.mark.parametrize("window,expected,variance", [(8, "2.8577", Fraction(6, 10000)),
                                                       (4, "2.5420", Fraction(91, 120000))])
def test_scenario_d_and_fraction_sqrt_bracket(window: int, expected: str, variance: Fraction) -> None:
    table = analyze(load_history(HISTORY), window)
    stat = table.statistics[0]
    assert stat.standardized_surprise.quantize(Decimal(".0001")) == Decimal(expected)
    assert stat.prior_count == window and stat.window == window
    deviation = stat.sample_stddev
    unit = Decimal(1).scaleb(deviation.adjusted() - 49)
    assert (Fraction(deviation) - Fraction(unit)) ** 2 < variance < (Fraction(deviation) + Fraction(unit)) ** 2
    if window == 8:
        assert stat.sample_variance == Decimal(".0006")
    assert stat.history_sha256 == load_history(HISTORY).source_sha256
    assert stat.standardized_reason is None


@pytest.mark.parametrize("count,expected", [(3, None), (4, "2.5420")])
def test_four_prior_minimum_straddle(count: int, expected: str | None) -> None:
    history = load_history(HISTORY)
    stat = analyze(replace(history, entries=history.entries[-count:])).statistics[0]
    if expected is None:
        assert stat.standardized_surprise is None
        assert stat.standardized_reason == "fewer than 4 prior surprises"
    else:
        assert stat.standardized_surprise.quantize(Decimal(".0001")) == Decimal(expected)


def test_order_future_exclusion_entity_and_zero_deviation() -> None:
    history = load_history(HISTORY)
    shuffled = replace(history, entries=tuple(reversed(history.entries)))
    assert analyze(shuffled).statistics == analyze(history).statistics
    rows = [{"entity": "HALV.FAKE", "metric": "Diluted EPS", "period": period, "surprise": value}
            for period, value in (("3Q26", "99"), ("4Q26", "99"))]
    future = history_from_rows(rows)
    assert analyze(replace(history, entries=(*history.entries, *future.entries))).statistics == analyze(history).statistics
    zero = history_from_rows([{"entity": "HALV.FAKE", "metric": "Diluted EPS", "period": f"{q}Q25", "surprise": ".01"}
                              for q in range(1, 5)])
    stat = analyze(zero).statistics[0]
    assert stat.sample_variance == 0 and stat.sample_stddev == 0
    assert stat.standardized_surprise is None and stat.standardized_reason == "zero historical deviation"
    other = replace(history, entries=tuple(replace(e, entity="CORD.FAKE") for e in history.entries))
    assert analyze(other).statistics[0].prior_count == 0


def test_history_ambiguities_and_float_refusal() -> None:
    base = {"entity": "HALV.FAKE", "metric": "Diluted EPS", "period": "3Q25", "surprise": ".01"}
    with pytest.raises(ValueError, match="duplicate.*period"):
        history_from_rows([base, base])
    with pytest.raises(ValueError, match="fiscal|calendar"):
        history_from_rows([base, {**base, "period": "F4Q25"}])
    with pytest.raises(ValueError, match="granularity"):
        history_from_rows([base, {**base, "period": "FY2024"}])
    with pytest.raises(ValueError, match="float"):
        history_from_rows([{**base, "surprise": .01}])
    with pytest.raises(ValueError, match="minimum of 4"):
        analyze(load_history(HISTORY), 3)


def test_dispersion_and_rate_units() -> None:
    table = analyze_table(actuals(**{"Std Dev": ".02"}), config())
    assert table.statistics[0].dispersion_surprise == Decimal("3.5")
    assert table.statistics[0].standardized_reason == "history not supplied"
    table = analyze_table(actuals(**{"Std Dev": "0"}), config())
    assert table.statistics[0].dispersion_surprise is None
    assert table.statistics[0].dispersion_reason == "zero estimate dispersion"
    history = history_from_rows([{"entity": "HALV.FAKE", "metric": "Gross Margin", "period": f"{q}Q25", "surprise": s}
                                 for q, s in enumerate(("10", "20", "30", "40"), 1)])
    rows = [{"Ticker": "HALV.FAKE", "Line Item": "Gross Margin", "Measure": "Percent", "Better": "Higher",
             "Consensus": "41.2%", "Actual": "40.6%", "Std Dev": "0.2%"}]
    result = analyze_table(rows, config(), options=AudienceOptions(surprise=SurpriseOptions(history=history)))
    assert result.statistics[0].surprise == Decimal("-60")
    assert result.statistics[0].dispersion_surprise == Decimal("-3")


def test_statistics_audit_report_long_and_tamper_detection() -> None:
    from variance_agent.comparisons import verify_comparisons
    table = analyze(load_history(HISTORY))
    report = render_comparisons(table)
    assert "Descriptive surprise" in report and "2.8577" in report
    audit = build_comparison_audit(table)
    assert audit["statistics"][0]["standardized_surprise"].startswith("2.857738")
    assert audit["statistics_configuration"]["window"] == 8
    jsonschema.validate(audit, json.loads(Path("schemas/audit-1.8.schema.json").read_text()))
    forged = replace(table, statistics=(replace(table.statistics[0], standardized_surprise=Decimal("99")),))
    with pytest.raises(RuntimeError, match="statistic"):
        verify_comparisons(forged)
    batch = analyze_panel([{**actuals()[0], "Period": "3Q26"}], group_by=("Ticker", "Period"), options=PanelOptions(
        config=replace(config(), period=""), audience=AudienceOptions(surprise=SurpriseOptions(history=load_history(HISTORY)))))
    row = next(csv.DictReader(long_csv(batch).splitlines()))
    assert row["standardized_surprise"].startswith("2.857738")
    assert json.loads(long_jsonl(batch))["prior_surprise_count"] == "8"


def test_cli_scenario_d_and_bad_window(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from variance_agent.cli import main
    target = tmp_path / "audit.json"
    args = ["tests/fixtures/multi_audience/consensus.csv", "--compare-to", "consensus", "--period", "3Q26",
            "--dollar-threshold", "10", "--percent-threshold", "2", "--per-share-threshold", ".01",
            "--count-threshold", "1000", "--bps-threshold", "25", "--history", str(HISTORY), "--audit-json", str(target)]
    assert main(args) == 0
    record = json.loads(target.read_text())
    eps = next(s for s in record["statistics"] if s["line_item"] == "Diluted EPS")
    assert eps["standardized_surprise"].startswith("2.857738")
    with pytest.raises(SystemExit) as failure:
        main([*args, "--surprise-window", "3"])
    assert failure.value.code == 2
    assert "minimum of 4" in capsys.readouterr().err


def test_sqrt_is_independent_of_callers_decimal_context() -> None:
    with localcontext() as ctx:
        ctx.prec = 6
        stat = analyze(load_history(HISTORY)).statistics[0]
    assert str(stat.standardized_surprise).startswith("2.857738033247041114")


def test_exact_square_and_missing_consensus() -> None:
    history = history_from_rows([{"entity": "HALV.FAKE", "metric": "Diluted EPS", "period": f"{q}Q25", "surprise": value}
                                 for q, value in enumerate(("0", "0", "0", "2"), 1)])
    stat = analyze(history).statistics[0]
    assert stat.sample_variance == 1 and stat.sample_stddev == 1
    assert stat.standardized_surprise == Decimal(".07")
    table = analyze_table(actuals(Consensus=""), config(), options=AudienceOptions(
        surprise=SurpriseOptions(history=history)))
    stat = table.statistics[0]
    assert stat.surprise is None and stat.standardized_surprise is None
    assert stat.standardized_reason == "consensus not supplied"
    jsonschema.validate(build_comparison_audit(table), json.loads(Path("schemas/audit-1.8.schema.json").read_text()))


def test_history_caps_and_source_path_protection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import variance_agent.api as api
    monkeypatch.setattr(api, "MAX_ROWS", 1)
    with pytest.raises(ValueError, match="row count"):
        load_history(HISTORY)
    monkeypatch.undo()
    from variance_agent.cli import main
    history = tmp_path / "HALV.FAKE.csv"
    history.write_bytes(HISTORY.read_bytes())
    before = history.read_bytes()
    args = ["tests/fixtures/multi_audience/consensus.csv", "--compare-to", "consensus", "--period", "3Q26",
            "--dollar-threshold", "10", "--percent-threshold", "2", "--per-share-threshold", ".01",
            "--count-threshold", "1000", "--bps-threshold", "25", "--history", str(history), "--long-output", str(history)]
    with pytest.raises(SystemExit) as failure:
        main(args)
    assert failure.value.code == 2
    assert history.read_bytes() == before


def test_statistic_set_children_validate_independently() -> None:
    table = analyze_table(actuals(**{"Model": ".85"}), config(), options=AudienceOptions(
        bases=(ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE), surprise=SurpriseOptions(history=load_history(HISTORY))))
    record = build_comparison_audit(table)
    schema = json.loads(Path("schemas/audit-1.8.schema.json").read_text())
    jsonschema.validate(record, schema)
    for child in record["comparisons"]:
        jsonschema.validate(child, schema)
    assert "statistics" in record["comparisons"][0]
    assert "statistics" not in record["comparisons"][1]
