"""X14: a comparison audit that needs 1.9 is written at 1.9, not refused both ways (fictional filing and data)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from variance_agent import cli

ROOT = Path(__file__).resolve().parents[1]
TEN_K = ROOT / "tests" / "fixtures" / "analysts" / "hal-20250927.htm"
EARNINGS = ["--assisted", "--preset", "earnings", "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold",
            "1", "--per-share-threshold", "0.01", "--count-threshold", "1"]


def _schema(version: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((ROOT / f"schemas/audit-{version}.schema.json").read_text(encoding="utf-8")))


def test_a_filing_s_earnings_audit_is_written_at_1_9(tmp_path: Path) -> None:
    audit = tmp_path / "a.json"
    assert cli.main([str(TEN_K), *EARNINGS, "--audit-json", str(audit), "-o", str(tmp_path / "r.md")]) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    assert record["schema_version"] == "1.9"
    _schema("1.9").validate(record)


def test_asking_for_1_8_names_what_needs_1_9(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main([str(TEN_K), *EARNINGS, "--audit-json", str(tmp_path / "a.json"), "--audit-schema-version", "1.8",
                  "-o", str(tmp_path / "r.md")])
    assert ("Audit schema 1.8 cannot record how the filing was read; use --audit-schema-version 1.9."
            in capsys.readouterr().err)


def test_a_spreadsheet_earnings_audit_stays_1_8(tmp_path: Path) -> None:
    data, audit = tmp_path / "c.csv", tmp_path / "a.json"
    data.write_text("Line Item,Actual,Consensus\nFictional Revenue,120,100\n", encoding="utf-8")
    assert cli.main([str(data), "--preset", "earnings", "--compare-to", "consensus", "--period", "Q3",
                     "--dollar-threshold", "1", "--percent-threshold", "1", "--audit-json", str(audit),
                     "-o", str(tmp_path / "r.md")]) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    assert record["schema_version"] == "1.8"
    _schema("1.8").validate(record)
