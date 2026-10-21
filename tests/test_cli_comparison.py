from __future__ import annotations

import json
from pathlib import Path

import pytest

import variance_agent.cli as cli

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"
J = FIXTURES_DIR / "fixture_j_10k_three_years.csv"
K = FIXTURES_DIR / "fixture_k_forecast.csv"
L = FIXTURES_DIR / "fixture_l_budget_and_forecast.csv"

BASE = ["--period", "FY2025", "--dollar-threshold", "1000", "--percent-threshold", "5"]


def test_strict_compare_to_forecast(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    assert cli.main([str(L), *BASE, "--compare-to", "forecast", "-o", str(out)]) == 0
    assert "| Forecast | Actual |" in out.read_text(encoding="utf-8")


def test_strict_without_compare_to_is_today(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    assert cli.main([str(L), *BASE, "-o", str(out)]) == 0
    assert "| Budget | Actual |" in out.read_text(encoding="utf-8")


def test_assisted_detects_10k(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "report.md"
    audit = tmp_path / "audit.json"
    assert cli.main([str(J), *BASE, "--assisted", "-o", str(out), "--audit-json", str(audit)]) == 0
    assert "comparing FY2025 against FY2024" in capsys.readouterr().err
    assert json.loads(audit.read_text(encoding="utf-8"))["comparison"] == {"basis": "prior_period", "label": "FY2024"}


def test_old_audit_schema_refused_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    audit = tmp_path / "audit.json"
    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(K), *BASE, "--assisted", "--audit-json", str(audit), "--audit-schema-version", "1.5"])
    assert exc_info.value.code == 2
    assert "1.6" in capsys.readouterr().err
    assert not audit.exists()


def test_compare_to_missing_column_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(K), *BASE, "--compare-to", "prior-period", "--check-only"])
    assert exc_info.value.code == 2
    assert "No prior period column found" in capsys.readouterr().err
