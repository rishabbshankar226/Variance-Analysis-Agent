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


def test_strict_prior_period_blank_cell_names_prior_period(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "py.csv"
    src.write_text("Line Item,Type,Prior Year,Actual\nRent Expense,Expense,,130\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(src), *BASE, "--compare-to", "prior-period", "--check-only"])
    assert exc_info.value.code == 2
    error_line = capsys.readouterr().err.strip().splitlines()[-1]  # after argparse's usage text
    assert "'Prior Period' is missing" in error_line
    assert "budget" not in error_line.lower()


# --- Final review I4: saved layout mappings record the comparison basis ---

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_variance.csv"
RERUN_HINT = "Rerun with --compare-to budget|forecast|prior-period."


def _chat_saved_mapping(fixture: Path, choice: str | None) -> str:
    from variance_agent.chat.handlers import handle_message, handle_upload
    from variance_agent.chat.session import Phase, Session
    from variance_agent.mapping import save_mapping

    session = Session()
    handle_upload(session, fixture.read_bytes(), fixture.name)
    if choice is not None:
        handle_message(session, choice)
    answers = {
        Phase.AWAITING_INTAKE_CONFIRMATION: "Looks right",
        Phase.AWAITING_PERIOD: "FY2025",
        Phase.AWAITING_THRESHOLDS: "$1,000 or 5%",
        Phase.AWAITING_CURRENCY: "USD",
    }
    while session.phase in answers:
        handle_message(session, answers[session.phase])
    assert session.phase == Phase.EXPLORING
    handle_message(session, "Save layout mapping")
    assert session.layout_mapping is not None
    return save_mapping(session.layout_mapping)


def test_chat_saved_forecast_mapping_replays_in_cli(tmp_path: Path) -> None:
    mapping_json = _chat_saved_mapping(L, "Compare to forecast")
    assert json.loads(mapping_json)["comparison_basis"] == "forecast"
    mapping = tmp_path / "mapping.json"
    mapping.write_text(mapping_json, encoding="utf-8")
    out = tmp_path / "report.md"
    assert cli.main([str(L), *BASE, "--mapping", str(mapping), "-o", str(out)]) == 0
    assert "| Forecast | Actual |" in out.read_text(encoding="utf-8")


def test_compare_to_overrides_saved_mapping_basis(tmp_path: Path) -> None:
    mapping = tmp_path / "mapping.json"
    mapping.write_text(_chat_saved_mapping(L, "Compare to forecast"), encoding="utf-8")
    out = tmp_path / "report.md"
    assert cli.main([str(L), *BASE, "--mapping", str(mapping), "--compare-to", "budget", "-o", str(out)]) == 0
    assert "| Budget | Actual |" in out.read_text(encoding="utf-8")


def test_budget_mapping_has_no_comparison_basis_key() -> None:
    data = json.loads(_chat_saved_mapping(SAMPLE, None))
    assert "comparison_basis" not in data


def test_mapping_without_comparison_basis_still_loads_and_runs(tmp_path: Path) -> None:
    from variance_agent.mapping import load_mapping

    old = {
        "mapping_version": "1.5",
        "layout_fingerprint": "",
        "header_row_number": 1,
        "column_mapping": {"line_item": "Line Item", "budget": "Budget", "actual": "Actual"},
        "treat_blank_budgets_as_zero": True,
    }
    loaded = load_mapping(json.dumps(old))
    assert loaded.comparison_basis is None
    assert "comparison_basis" not in loaded.to_dict()
    mapping = tmp_path / "old.json"
    mapping.write_text(json.dumps(old), encoding="utf-8")
    out = tmp_path / "report.md"
    assert cli.main([str(SAMPLE), *BASE, "--mapping", str(mapping), "-o", str(out)]) == 0
    assert "| Budget | Actual |" in out.read_text(encoding="utf-8")


def test_mapping_rejects_unknown_comparison_basis() -> None:
    from variance_agent.mapping import load_mapping

    with pytest.raises(ValueError, match="comparison_basis"):
        load_mapping(json.dumps({"comparison_basis": "target"}))


def test_strict_compare_to_budget(tmp_path: Path) -> None:
    out = tmp_path / "report.md"
    assert cli.main([str(L), *BASE, "--compare-to", "budget", "-o", str(out)]) == 0
    report = out.read_text(encoding="utf-8")
    assert "| Budget | Actual |" in report and "100,000" in report


# --- Final review M1: CLI stop-and-ask messages say how to choose ---


def _exit_2_error(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(argv)
    assert exc_info.value.code == 2
    return capsys.readouterr().err.strip().splitlines()[-1]


def test_assisted_ambiguous_file_names_compare_to(capsys: pytest.CaptureFixture[str]) -> None:
    error = _exit_2_error([str(L), *BASE, "--assisted", "--check-only"], capsys)
    assert "Which should Actual be compared against?" in error
    assert error.endswith(RERUN_HINT)


def test_strict_forecast_only_file_names_compare_to(capsys: pytest.CaptureFixture[str]) -> None:
    error = _exit_2_error([str(K), *BASE, "--check-only"], capsys)
    assert "required field 'Budget' was not found" in error
    assert error.endswith(RERUN_HINT)


def test_strict_budget_file_missing_budget_has_no_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "no_budget.csv"
    src.write_text("Line Item,Type,Actual\nRent Expense,Expense,130\n", encoding="utf-8")
    error = _exit_2_error([str(src), *BASE, "--check-only"], capsys)
    assert "required field 'Budget' was not found" in error and "--compare-to" not in error


def test_duplicate_forecast_columns_have_no_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "two_fcst.csv"
    src.write_text("Line Item,Type,Forecast,Fcst,Actual\nRent Expense,Expense,1,2,3\n", encoding="utf-8")
    error = _exit_2_error([str(src), *BASE, "--assisted", "--compare-to", "forecast", "--check-only"], capsys)
    assert "more than one forecast column" in error and "--compare-to" not in error


ASSISTED_YEAR_HINT = (
    "This file has year columns (FY2025, FY2024, FY2023); rerun with --assisted to compare "
    "the newest year against the one before it (add --compare-to prior-period to require that)."
)


def test_strict_year_only_file_suggests_assisted(capsys: pytest.CaptureFixture[str]) -> None:
    error = _exit_2_error([str(J), *BASE, "--check-only"], capsys)
    assert "required field 'Budget' was not found" in error
    assert error.endswith(ASSISTED_YEAR_HINT)


def test_strict_compare_to_prior_period_on_year_file_suggests_assisted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    error = _exit_2_error([str(J), *BASE, "--compare-to", "prior-period", "--check-only"], capsys)
    assert "No prior period column found" in error
    assert error.endswith(ASSISTED_YEAR_HINT)


def test_suggested_assisted_rerun_works(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(J), *BASE, "--assisted", "--compare-to", "prior-period", "--check-only"]) == 0
    assert "comparing FY2025 against FY2024" in capsys.readouterr().err
