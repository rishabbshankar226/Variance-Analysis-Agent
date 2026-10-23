"""Final adapter checks using fictional Halvorsen Instruments, HALV.FAKE."""
from decimal import Decimal
import json
from pathlib import Path

import jsonschema
import pytest

from variance_agent.api import AudienceOptions, analyze_file
from variance_agent.audience import AudienceConfig
from variance_agent.audit import payload_sha256
from variance_agent.cli import main
from variance_agent.comparisons import build_comparison_audit
from variance_agent.models import ComparisonBasis


@pytest.mark.parametrize("suffix", [".csv", ".json"])
@pytest.mark.parametrize("bases", [(ComparisonBasis.CONSENSUS,), (ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE)])
def test_file_mapping_and_notes_reach_each_audit(tmp_path: Path, suffix: str, bases: tuple[ComparisonBasis, ...]) -> None:
    path = tmp_path / ("HALV.FAKE" + suffix)
    row = {"Metric": "Revenue", "StreetMean": "100", "ModelValue": "101", "Actual": "110", "Type": "Revenue"}
    path.write_text(("Fictional Halvorsen Instruments HALV.FAKE\nMetric,StreetMean,ModelValue,Actual,Type\n"
                     "Revenue,100,101,110,Revenue\n") if suffix == ".csv" else json.dumps([row]))
    mapping = {"line_item": "Metric", "consensus": "StreetMean", "estimate": "ModelValue"}
    table = analyze_file(path, AudienceConfig("3Q26", Decimal("10"), Decimal(".02")),
                         options=AudienceOptions(bases=bases, assisted=True, column_mapping=mapping))
    record = build_comparison_audit(table)
    children = record["comparisons"] if len(bases) > 1 else [record]
    schema = json.loads(Path("schemas/audit-1.8.schema.json").read_text())
    jsonschema.validate(record, schema)
    for child in children:
        assert child["transformations"]["column_mapping"] == mapping
        assert any("mapping" in note for note in child["inferences"])
        if suffix == ".csv":
            assert child["transformations"]["header_row_number"] == 2
            assert any("header row 2" in note for note in child["inferences"])
        assert payload_sha256(child) == child["payload_sha256"]
        jsonschema.validate(child, schema)


@pytest.mark.parametrize("panel", [False, True])
def test_explicit_statistics_options_apply_without_history(tmp_path: Path, panel: bool) -> None:
    source = tmp_path / "HALV.FAKE.csv"
    source.write_text("Ticker,Period,Line Item,Measure,Consensus,Actual,Std Dev\n"
                      "HALV.FAKE,3Q26,Diluted EPS,Per Share,.84,.91,.02\n")
    output = tmp_path / "output.jsonl"
    args = [str(source), "--compare-to", "consensus", "--dollar-threshold", "10", "--percent-threshold", "2",
            "--per-share-threshold", ".01", "--surprise-window", "4", "--entity", "HALV.FAKE",
            "--long-output-jsonl", str(output)]
    if panel:
        args.extend(["--group-by", "Ticker,Period", "--errors-output", str(tmp_path / "errors.csv")])
    else:
        args.extend(["--period", "3Q26", "--audit-json", str(tmp_path / "audit.json")])
    assert main(args) == 0
    wire = json.loads(output.read_text())
    assert wire["surprise_window"] == "4"
    assert wire["dispersion_surprise"] == "3.5"
    if not panel:
        record = json.loads((tmp_path / "audit.json").read_text())
        assert record["statistics_configuration"]["window"] == 4
        assert record["statistics_configuration"]["entity"] == "HALV.FAKE"
