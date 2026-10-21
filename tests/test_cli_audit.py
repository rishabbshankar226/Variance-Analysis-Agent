import json
import pytest
import variance_agent.cli as cli
from test_audit import _result
from variance_agent.parsing import ParsedInput


def test_cli_help_prints_percentage_example_and_exits_successfully(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(["--help"])
    assert error.value.code == 0
    assert "5%" in capsys.readouterr().out


def test_cli_writes_report_and_audit_with_source_fingerprint(tmp_path, monkeypatch):
    source = tmp_path / "input.csv"
    source.write_text("Line Item,Budget,Actual\nRevenue,1,2\n", encoding="utf-8")
    monkeypatch.setattr(cli, "load_input", lambda *args, **kwargs: ParsedInput([{"dummy": True}]))
    monkeypatch.setattr(cli, "analyze_rows", lambda rows, config: _result())
    monkeypatch.setattr(cli, "render_markdown", lambda result: "# report\n")

    report = tmp_path / "nested" / "report.md"
    audit = tmp_path / "nested" / "audit" / "record.json"
    rc = cli.main([
        str(source),
        "--period", "Q3 2026",
        "--dollar-threshold", "100",
        "--percent-threshold", "5",
        "--output", str(report),
        "--audit-json", str(audit),
    ])

    assert rc == 0
    assert report.read_text(encoding="utf-8") == "# report\n"
    payload = json.loads(audit.read_text(encoding="utf-8"))
    assert payload["source"]["name"] == "input.csv"
    assert len(payload["source"]["sha256"]) == 64
    assert payload["analysis_fingerprint"]


def test_cli_includes_executive_commentary_when_flag_present(capsys):
    rc = cli.main([
        "examples/sample_variance.csv",
        "--period", "Q3-2024",
        "--dollar-threshold", "1000",
        "--percent-threshold", "5",
        "--commentary",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# Executive Commentary" in out
    assert "Revenue outpaced expectations cleanly." in out


def test_cli_assisted_flag_processes_messy_fixture(capsys):
    fixture_path = "tests/fixtures/realworld/fixture_a_erp_title_block.xlsx"
    # 1. Without --assisted: fails because header is on row 5, not row 1
    with pytest.raises(SystemExit) as exc_info:
        cli.main([
            fixture_path,
            "--period", "Q3 2026",
            "--dollar-threshold", "1000",
            "--percent-threshold", "5",
        ])
    assert exc_info.value.code == 2

    # 2. With --assisted: succeeds, analyzes rows, and logs adjustments to stderr
    rc = cli.main([
        fixture_path,
        "--assisted",
        "--period", "Q3 2026",
        "--dollar-threshold", "1000",
        "--percent-threshold", "5",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    assert "# FP&A Variance Report" in captured.out
    assert "[assisted intake]" in captured.err
    assert "GL Account" in captured.err
