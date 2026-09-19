import json
from pathlib import Path

import variance_agent.cli as cli
from test_audit import _result


def test_cli_writes_report_and_audit_with_source_fingerprint(tmp_path, monkeypatch):
    source = tmp_path / "input.csv"
    source.write_text("Line Item,Budget,Actual\nRevenue,1,2\n", encoding="utf-8")
    monkeypatch.setattr(cli, "load_file", lambda _: [{"dummy": True}])
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
