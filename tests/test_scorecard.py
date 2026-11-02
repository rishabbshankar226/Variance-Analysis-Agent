"""R18: Marcus's holdings scorecard (docs/analysts/PLAN.md). Every ticker here ends in .FAKE."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.fixtures.analysts.build_analysts import MARCUS_HOLDINGS, MARCUS_PANEL
from variance_agent import cli

ROOT = Path(__file__).resolve().parents[1]


def _argv(tmp_path: Path, holdings: str = MARCUS_HOLDINGS, panel: str = MARCUS_PANEL) -> list[str]:
    (tmp_path / "holdings.csv").write_text(holdings, encoding="utf-8")
    (tmp_path / "panel.csv").write_text(panel, encoding="utf-8")
    return [str(tmp_path / "holdings.csv"), "--assisted", "--panel", str(tmp_path / "panel.csv"), "--join-key", "Ticker",
            "--deciding-metric", "Diluted EPS", "--period", "Q3 2026", "--dollar-threshold", "1",
            "--percent-threshold", "1", "--per-share-threshold", "0.01"]


def _run(tmp_path: Path, **files: str) -> tuple[dict[str, object], str]:
    audit, report = tmp_path / "audit.json", tmp_path / "r.md"
    assert cli.main([*_argv(tmp_path, **files), "--audit-json", str(audit), "-o", str(report)]) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads((ROOT / "schemas/audit-1.9.schema.json").read_text(encoding="utf-8"))).validate(record)
    return record, report.read_text(encoding="utf-8")


def test_each_holding_takes_its_deciding_metric_s_label(tmp_path: Path) -> None:
    record, _ = _run(tmp_path)
    document = record["source"]["document"]  # type: ignore[index]
    labels = {h["key"]: h["label"] for h in document["holdings"]}
    assert labels == {"NORDVIK.FAKE": "Beat", "HALVORSEN.FAKE": "In line", "OSTRAVA.FAKE": "Miss", "BRAVIK.FAKE": None}


def test_weight_shares_over_the_book_and_over_the_covered_holdings(tmp_path: Path) -> None:
    record, report = _run(tmp_path)
    shares = {s["label"]: s for s in record["source"]["document"]["shares"]}  # type: ignore[index]
    book, covered = Fraction("28.30"), Fraction("25.30")
    # Fraction oracle: each label's weight over the whole book and over the covered weight.
    for label, weight in (("Beat", "12.40"), ("In line", "7.90"), ("Miss", "5.00")):
        assert Fraction(shares[label]["weight"]) == Fraction(weight)
        assert abs(Fraction(shares[label]["share_of_book"]) - Fraction(weight) / book) < Fraction(1, 10**25)
        assert abs(Fraction(shares[label]["share_of_covered"]) - Fraction(weight) / covered) < Fraction(1, 10**25)
    assert Fraction(shares["Not covered"]["weight"]) == 3
    assert sum(Fraction(shares[label]["weight"]) for label in ("Beat", "In line", "Miss")) == covered
    assert "| Beat | 12.4% | 43.8% | 49.0% |" in report
    assert "Not covered by the panel for Diluted EPS: BRAVIK.FAKE (3%)" in report
    assert "Left out of the panel: TROLL.FAKE (not a holding in 'holdings.csv')" in report


@pytest.mark.parametrize(("holdings", "panel", "message"), [
    (MARCUS_HOLDINGS + "NORDVIK.FAKE,1.00%\n", MARCUS_PANEL,
     "'NORDVIK.FAKE' appears more than once in 'holdings.csv', so its weight is ambiguous."),
    (MARCUS_HOLDINGS, MARCUS_PANEL + "NORDVIK.FAKE,Diluted EPS,1.30,1.10,Per Share,Higher\n",
     "'NORDVIK.FAKE' has more than one Diluted EPS row in 'panel.csv', so its label is ambiguous."),
    ("Name,Weight\nNORDVIK.FAKE,12%\n", MARCUS_PANEL, "'holdings.csv' has no 'Ticker' column to join on."),
    ("Ticker,Weight\nNORDVIK.FAKE,12%\nHALVORSEN.FAKE,8\n", MARCUS_PANEL,
     "'holdings.csv' mixes weights with and without %; give every weight the same way."),
])
def test_scorecard_refusals_name_the_cause(tmp_path: Path, capsys: pytest.CaptureFixture[str], holdings: str, panel: str,
                                           message: str) -> None:
    with pytest.raises(SystemExit):
        cli.main(_argv(tmp_path, holdings, panel))
    assert message in capsys.readouterr().err.replace("\n", " ")


# X2: a holdings workbook reads its weights as Excel prints them, from the stored decimals.
def _holdings_book(path: Path, cells: list[tuple[str, float, str]]) -> None:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.append(["Ticker", "Weight"])
    for row, (ticker, weight, code) in enumerate(cells, start=2):
        sheet.append([ticker, weight])
        sheet.cell(row=row, column=2).number_format = code
    book.save(path)


def _run_book(tmp_path: Path, cells: list[tuple[str, float, str]]) -> list[str]:
    _argv(tmp_path)  # writes the fictional panel.csv
    _holdings_book(tmp_path / "holdings.xlsx", cells)
    argv = _argv(tmp_path)
    argv[0] = str(tmp_path / "holdings.xlsx")
    return argv


_PERCENT_BOOK = [("NORDVIK.FAKE", 0.124, "0.00%"), ("HALVORSEN.FAKE", 0.079, "0.00%"),
                 ("OSTRAVA.FAKE", 0.05, "0.00%"), ("BRAVIK.FAKE", 0.03, "0.00%")]


def test_percent_formatted_weights_read_as_printed(tmp_path: Path) -> None:
    audit, report = tmp_path / "audit.json", tmp_path / "r.md"
    assert cli.main([*_run_book(tmp_path, _PERCENT_BOOK), "--audit-json", str(audit), "-o", str(report)]) == 0
    text = report.read_text(encoding="utf-8")
    assert "| Beat | 12.4% | 43.8% | 49.0% |" in text
    assert "Not covered by the panel for Diluted EPS: BRAVIK.FAKE (3%)" in text
    holdings = json.loads(audit.read_text(encoding="utf-8"))["source"]["document"]["holdings"]
    # Fraction oracle: each weight is the stored decimal times 100, exactly.
    stored = {"NORDVIK.FAKE": "0.124", "HALVORSEN.FAKE": "0.079", "OSTRAVA.FAKE": "0.05", "BRAVIK.FAKE": "0.03"}
    assert {h["key"]: Fraction(h["weight"]) for h in holdings} == {k: Fraction(v) * 100 for k, v in stored.items()}


def test_general_formatted_weights_read_as_their_stored_value(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    cells = [(ticker, round(weight * 100, 2), "General") for ticker, weight, _ in _PERCENT_BOOK]
    assert cli.main([*_run_book(tmp_path, cells), "-o", str(report)]) == 0
    assert "| Beat | 12.4% | 43.8% | 49.0% |" in report.read_text(encoding="utf-8")


@pytest.mark.parametrize(("cells", "message"), [
    ([("NORDVIK.FAKE", 0.124, "0.00%"), ("HALVORSEN.FAKE", 7.9, "General")],
     "'holdings.xlsx' mixes weights with and without %; give every weight the same way."),
    ([("NORDVIK.FAKE", 12400, "#,##0,"), ("HALVORSEN.FAKE", 7900, "#,##0,")],
     "Cell B2 of 'holdings.xlsx' is shown scaled by its number format ('#,##0,'); "
     "give the figure as it should be read."),
])
def test_workbook_weights_that_cannot_be_read_as_printed_refuse(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], cells: list[tuple[str, float, str]], message: str) -> None:
    with pytest.raises(SystemExit):
        cli.main(_run_book(tmp_path, cells))
    assert message in capsys.readouterr().err.replace("\n", " ")
