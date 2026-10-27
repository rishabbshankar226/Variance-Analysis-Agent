"""R12 (F4): budget and actuals in two files, joined on a key both carry. Every file here is fictional."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from variance_agent import cli
from variance_agent.chat.handlers import handle_upload
from variance_agent.chat.session import Phase, Session

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "realworld"
ACTUALS = FIXTURES / "fixture_f_actuals_separate.csv"
BUDGET = FIXTURES / "fixture_f_budget_separate.csv"


def _run(actuals: Path, budget: Path, *extra: str) -> list[str]:
    return [str(actuals), "--assisted", "--compare-file", str(budget), "--period", "Oct 2026",
            "--dollar-threshold", "1", "--percent-threshold", "1", *extra]


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_the_two_fixture_files_join_by_gl_account(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    assert cli.main(_run(ACTUALS, BUDGET, "--audit-json", str(audit))) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads((ROOT / "schemas/audit-1.9.schema.json").read_text(encoding="utf-8"))).validate(record)
    rows = {row["line_item"]: (Decimal(row["comparison"]), Decimal(row["actual"])) for row in record["measure_rows"]}
    assert rows == {"SaaS Subscriptions": (Decimal(120000), Decimal(128000)),
                    "Professional Consulting Fees": (Decimal(45000), Decimal(42000)),
                    "Salaries and Wages": (Decimal(75000), Decimal(79000)),
                    "Cloud Hosting & Bandwidth": (Decimal(30000), Decimal(34000)),
                    "Marketing Campaigns": (Decimal(20000), Decimal(23000))}
    document = record["source"]["document"]
    assert (document["kind"], document["key"]) == ("join", "GL Account")
    assert [(d["name"], d["role"]) for d in document["documents"]] == [
        ("fixture_f_actuals_separate.csv", "actual"), ("fixture_f_budget_separate.csv", "comparison")]
    assert {"line_item": "SaaS Subscriptions", "key": "4010", "comparison_line_item": "SaaS Subscription Revenue"} in (
        document["lines"])
    assert ("Joined 'fixture_f_budget_separate.csv' to 'fixture_f_actuals_separate.csv' by 'GL Account': 5 lines, each "
            "in both files") in document["reader_notes"]


def test_a_line_in_one_file_only_refuses_naming_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    budget = _write(tmp_path, "budget.csv", BUDGET.read_text(encoding="utf-8") + "5040,Travel,9000,Fictional\n")
    with pytest.raises(SystemExit):
        cli.main(_run(ACTUALS, budget))
    assert ("In 'budget.csv' but not in 'fixture_f_actuals_separate.csv': 5040 (Travel). Joining without them would "
            "change the totals without a trace. Add each line to the other file, or remove it, and run again.") in (
        capsys.readouterr().err.replace("\n", " "))


def test_a_repeated_key_refuses(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    budget = _write(tmp_path, "budget.csv", BUDGET.read_text(encoding="utf-8") + "4010,Extra subscriptions,1000,Fictional\n")
    with pytest.raises(SystemExit):
        cli.main(_run(ACTUALS, budget))
    assert "'4010' appears more than once in 'budget.csv', so I can't tell which row to join" in (
        capsys.readouterr().err.replace("\n", " "))


def test_without_an_account_column_the_join_uses_the_exact_label(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    actuals = _write(tmp_path, "actuals.csv", "Line Item,Actual\nRevenue,110\nCOGS,45\n")
    budget = _write(tmp_path, "budget.csv", "Line Item,Budget\nRevenue,100\nCost of goods sold,40\n")
    with pytest.raises(SystemExit):
        cli.main(_run(actuals, budget))
    assert "In 'actuals.csv' but not in 'budget.csv': COGS." in capsys.readouterr().err.replace("\n", " ")
    budget.write_text("Line Item,Budget\nRevenue,100\nCOGS,40\n", encoding="utf-8")
    assert cli.main(_run(actuals, budget)) == 0


def test_each_file_s_unit_caption_scales_only_its_own_figures(tmp_path: Path) -> None:
    actuals = _write(tmp_path, "actuals.csv", "Line Item,Actual\nRevenue,110000\nCOGS,45000\n")
    budget = _write(tmp_path, "budget.csv", "Budget (in thousands)\nLine Item,Budget\nRevenue,100\nCOGS,40\n")
    audit = tmp_path / "audit.json"
    assert cli.main(_run(actuals, budget, "--audit-json", str(audit))) == 0
    rows = {r["line_item"]: Decimal(r["comparison"]) for r in json.loads(audit.read_text(encoding="utf-8"))["measure_rows"]}
    assert rows == {"Revenue": Decimal(100000), "COGS": Decimal(40000)}


def test_a_comparison_file_with_actuals_is_not_a_half(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    budget = _write(tmp_path, "budget.csv", "Line Item,Budget,Actual\nRevenue,100,110\n")
    actuals = _write(tmp_path, "actuals.csv", "Line Item,Actual\nRevenue,110\n")
    with pytest.raises(SystemExit):
        cli.main(_run(actuals, budget))
    assert ("'budget.csv' already has an Actual column, so it isn't the comparison half of a pair. Run it on its own, "
            "without --compare-file.") in capsys.readouterr().err.replace("\n", " ")


def test_compare_file_needs_assisted(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main([str(ACTUALS), "--compare-file", str(BUDGET), "--period", "Oct", "--dollar-threshold", "1",
                  "--percent-threshold", "1"])
    assert "--compare-file needs --assisted" in capsys.readouterr().err


def test_the_chat_asks_for_the_other_file_and_joins_them() -> None:
    session = Session()
    first = handle_upload(session, BUDGET.read_bytes(), BUDGET.name)
    assert session.phase == Phase.AWAITING_FILE
    assert first.text == ("'fixture\\_f\\_budget\\_separate.csv' has Budget figures but no Actual column. Upload the file with "
                          "the actuals, and I'll join the two by 'GL Account'.")
    second = handle_upload(session, ACTUALS.read_bytes(), ACTUALS.name)
    assert "Joined 'fixture_f_budget_separate.csv' to 'fixture_f_actuals_separate.csv' by 'GL Account'" in second.text
    assert session.intake_result is not None and len(session.intake_result.rows) == 5


def test_the_chat_asks_for_the_comparison_when_actuals_come_first() -> None:
    session = Session()
    first = handle_upload(session, ACTUALS.read_bytes(), ACTUALS.name)
    assert first.text == ("'fixture\\_f\\_actuals\\_separate.csv' has Actual figures but no Budget column. Upload the file with "
                          "the budget, forecast or prior period, and I'll join the two by 'GL Account'.")


def test_a_request_for_the_other_file_shows_the_drop_zone() -> None:
    assert handle_upload(Session(), BUDGET.read_bytes(), BUDGET.name).ask_upload is True
    script = (ROOT / "src/variance_agent/static/chat.js").read_text("utf-8")
    assert "data.ask_upload === true ||" in script
