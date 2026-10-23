"""Fictional metric layout replay without new defaults on old mappings."""
import json
import pytest
from variance_agent.cli import main
from variance_agent.mapping import load_mapping, save_mapping


def test_mapping_replays_rate_scale_direction_and_threshold(tmp_path, capsys):
    source = tmp_path / "fictional.csv"
    source.write_text("Line Item,Measure,Budget,Actual\nGross Margin,Percent,0.412,0.406\n")
    mapping = tmp_path / "layout.json"
    mapping.write_text(json.dumps({"measure_options": {"percent_values": "fractions", "bps_threshold": "25"},
                                   "better_directions": {"Gross Margin": "Higher"}}))
    args = [str(source), "--mapping", str(mapping), "--period", "3Q26", "--dollar-threshold", "10", "--percent-threshold", "2"]
    assert main(args) == 0
    assert "-60 bps" in capsys.readouterr().out
    saved = json.loads(save_mapping(load_mapping(mapping.read_bytes())))
    assert saved["measure_options"]["percent_values"] == "fractions"
    assert saved["better_directions"] == {"Gross Margin": "Higher"}
    assert main([*args, "--percent-values", "points"]) == 0
    assert "-0.6 bps" in capsys.readouterr().out


def test_mapping_rejects_unsafe_or_unknown_measure_options():
    with pytest.raises(ValueError, match="Mapping file.*measure_options"):
        load_mapping(b'{"measure_options":{"arbitrary":"data"}}')


def test_bad_mapping_threshold_is_a_plain_cli_input_error(tmp_path, capsys):
    source = tmp_path / "fictional.csv"
    source.write_text("Line Item,Measure,Better,Budget,Actual\nFictional Units,Count,Higher,10,11\n")
    mapping = tmp_path / "layout.json"
    mapping.write_text('{"measure_options":{"count_threshold":"TBD"}}')
    with pytest.raises(SystemExit) as error:
        main([str(source), "--mapping", str(mapping), "--period", "3Q26", "--dollar-threshold", "10", "--percent-threshold", "2"])
    assert error.value.code == 2
    assert "Mapping file" in capsys.readouterr().err
