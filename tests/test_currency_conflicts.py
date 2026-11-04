"""X5, X30: no currency is converted, so amounts marked in one currency never report under another (fictional data)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tests.chat_helpers import ask
from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing, quarter_all_filing
from variance_agent import analyze_file, cli
from variance_agent.api import AudienceOptions
from variance_agent.audience import AudienceConfig
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session
from variance_agent.models import ComparisonBasis

EURO_FILE = "Line Item,Type,Budget,Actual\nFictional Sales,Revenue,€100,€120\nFictional Rent,Expense,€50,€55\n"
BASE = ["--period", "Q3 2026", "--dollar-threshold", "1", "--percent-threshold", "1"]


def _run(tmp_path: Path, name: str, text: str | bytes, *extra: str) -> tuple[int | None, str, str]:
    path = tmp_path / name
    path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    report = tmp_path / "r.md"
    try:
        code = cli.main([str(path), "--assisted", *BASE, *extra, "-o", str(report)])
    except SystemExit as stop:
        code = int(stop.code) if isinstance(stop.code, int) else 2
    return code, report.read_text(encoding="utf-8") if report.exists() else "", ""


def test_amounts_marked_in_euros_refuse_under_dollars_naming_each_cell(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, _ = _run(tmp_path, "eur.csv", EURO_FILE, "--currency", "USD")
    err = capsys.readouterr().err.replace("\n", " ")
    assert code == 2
    assert ("Some amounts in 'eur.csv' are marked in EUR, but the reporting currency is USD, and no currency is "
            "converted:") in err
    assert "- Row 2, Fictional Sales, Budget column: €100" in err
    assert "Run with --currency EUR, or give every amount in USD." in err


def test_the_same_amounts_read_in_their_own_currency(tmp_path: Path) -> None:
    code, report, _ = _run(tmp_path, "eur.csv", EURO_FILE, "--currency", "EUR")
    assert code == 0
    assert "€120.00" in report


@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP"])
def test_unmarked_amounts_read_under_any_currency(tmp_path: Path, currency: str) -> None:
    code, _, _ = _run(tmp_path, "plain.csv", EURO_FILE.replace("€", ""), "--currency", currency)
    assert code == 0


def test_one_pound_cell_among_dollars_is_the_one_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = EURO_FILE.replace("€", "$").replace("$55", "£55")
    code, _, _ = _run(tmp_path, "mixed.csv", text, "--currency", "USD")
    err = capsys.readouterr().err
    assert code == 2
    assert "marked in GBP" in err and "- Row 3, Fictional Rent, Actual column: £55" in err
    assert "Row 2" not in err


def test_the_chat_returns_to_the_currency_question_with_a_chip() -> None:
    session = Session()
    handle_upload(session, EURO_FILE.encode("utf-8"), "eur.csv")
    for answer in ("Looks right", "Q3 2026", "$1 or 1%"):
        handle_message(session, answer)
    response = handle_message(session, "USD")
    assert response.phase == Phase.AWAITING_CURRENCY and session.phase == Phase.AWAITING_CURRENCY
    assert "Some amounts in 'eur.csv' are marked in EUR, but the reporting currency is USD" in response.text
    assert "Choose EUR to report in EUR, or upload the amounts in USD." in response.text
    assert response.chips is not None and "EUR" in response.chips
    assert session.result is None
    assert handle_message(session, "EUR").phase == Phase.EXPLORING
    assert "€120.00" in ask(session, "summary").text


def test_a_join_carries_the_marked_cells_of_both_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    actual, budget = tmp_path / "act.csv", tmp_path / "bud.csv"
    actual.write_text("Line Item,Actual\nFictional Sales,120\n", encoding="utf-8")
    budget.write_text("Line Item,Budget\nFictional Sales,€100\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(actual), "--assisted", "--compare-file", str(budget), *BASE, "-o", str(tmp_path / "r.md")])
    assert "Some amounts in 'bud.csv' are marked in EUR" in capsys.readouterr().err


def _filing(tmp_path: Path, name: str, data: bytes, unit: str) -> Path:
    path = tmp_path / name
    path.write_bytes(data.replace(b"iso4217:USD", f"iso4217:{unit}".encode()))
    return path


@pytest.mark.parametrize("extra", [[], ["--preset", "earnings", "--per-share-threshold", "0.01", "--count-threshold", "1"]],
                         ids=["fpa", "earnings"])
def test_a_dollar_filing_refuses_under_euros(tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str]) -> None:
    path = _filing(tmp_path, "filing.htm", all_statements_filing(), "USD")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "1",
                  "--currency", "EUR", *extra, "-o", str(tmp_path / "r.md")])
    err = capsys.readouterr().err.replace("\n", " ")
    assert "'filing.htm' reports its amounts in USD, but the reporting currency is EUR, and no currency is converted." in err
    assert "Run with --currency USD." in err


def test_a_yen_filing_refuses_under_every_currency(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _filing(tmp_path, "filing.htm", all_statements_filing(), "JPY")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "1",
                  "-o", str(tmp_path / "r.md")])
    assert ("'filing.htm' reports its amounts in JPY. This tool reports in USD, EUR or GBP only and converts no "
            "currency.") in capsys.readouterr().err.replace("\n", " ")


def test_the_file_api_refuses_a_filing_in_another_currency(tmp_path: Path) -> None:
    path = _filing(tmp_path, "filing.htm", all_statements_filing(), "USD")
    with pytest.raises(ValueError, match="'filing.htm' reports its amounts in USD, but the reporting currency is EUR"):
        analyze_file(path, AudienceConfig("FY2025", Decimal("1"), Decimal("0.01"), currency="EUR"),
                     options=AudienceOptions(assisted=True, bases=(ComparisonBasis.PRIOR_PERIOD,)))


def test_a_euro_filing_builds_its_ltm_table_in_euros(tmp_path: Path) -> None:
    quarter = _filing(tmp_path, "q.htm", quarter_all_filing(), "EUR")
    annual = _filing(tmp_path, "k.htm", all_statements_filing(), "EUR")
    report = tmp_path / "r.md"
    assert cli.main([str(quarter), "--assisted", "--ltm-from", str(annual), "--period", "LTM Mar 2026",
                     "--dollar-threshold", "1", "--percent-threshold", "1", "--currency", "EUR", "-o", str(report)]) == 0
    text = report.read_text(encoding="utf-8")
    build = text[text.index("## LTM build"):].split("\n## ", 1)[0]  # the section, up to the next heading
    assert "| Net sales | €4,100,000,000.00 | €2,200,000,000.00 | €2,000,000,000.00 | €4,300,000,000.00 |" in build
    assert "$" not in build
