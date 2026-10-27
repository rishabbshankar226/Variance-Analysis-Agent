"""R16: the Multiple measure (3.25x), its own cutoff in turns (docs/analysts/PLAN.md). Every figure is fictional."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from variance_agent import cli

ROOT = Path(__file__).resolve().parents[1]
HEADER = "Line Item,Budget,Actual,Measure,Better\n"


def _run(tmp_path: Path, rows: str, *extra: str) -> tuple[dict[str, object], str]:
    path = tmp_path / "input.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    audit, report = tmp_path / "audit.json", tmp_path / "r.md"
    assert cli.main([str(path), "--assisted", "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "50",
                     "--audit-json", str(audit), "-o", str(report), *extra]) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads((ROOT / "schemas/audit-1.9.schema.json").read_text(encoding="utf-8"))).validate(record)
    return record, report.read_text(encoding="utf-8")


def test_a_leverage_multiple_reads_in_turns_with_its_own_cutoff(tmp_path: Path) -> None:
    record, report = _run(tmp_path, "Net leverage,2.50x,3.25x,Multiple,Lower\n", "--multiple-threshold", "0.5")
    row = record["measure_rows"][0]  # type: ignore[index]
    assert (record["schema_version"], row["measure"], row["status"], row["material"]) == ("1.9", "Multiple", "U", True)
    assert Fraction(str(row["variance"])) == Fraction("3.25") - Fraction("2.50")  # Fraction oracle
    assert record["audience"]["multiple_threshold"] == "0.5"  # type: ignore[index]
    assert "| Net leverage | Multiple | 2.5x | 3.25x | 0.75x |" in report


@pytest.mark.parametrize(("actual", "material"), [("3.00x", False), ("3.01x", True)])
def test_materiality_in_turns_is_strictly_greater_than(tmp_path: Path, actual: str, material: bool) -> None:
    record, _ = _run(tmp_path, f"Net leverage,2.50x,{actual},Multiple,Lower\n", "--multiple-threshold", "0.5")
    assert record["measure_rows"][0]["material"] is material  # type: ignore[index]


@pytest.mark.parametrize(("rows", "extra", "message"), [
    ("Net leverage,2.50x,3.25x,Multiple,Lower\n", (), "Net leverage: supply --multiple-threshold for Multiple rows."),
    ("Net leverage,2.50x,3.25x,Multiple,\n", ("--multiple-threshold", "0.5"),
     "Net leverage: is Higher or Lower better? Supply Better as Higher or Lower."),
    ("Revenue,2.50x,3.25x,Currency,\n", ("--multiple-threshold", "0.5"),
     "Row 2, Revenue, Budget column: '2.50x' is not an amount I can read."),
])
def test_multiple_rows_need_their_cutoff_and_direction(tmp_path: Path, capsys: pytest.CaptureFixture[str], rows: str,
                                                      extra: tuple[str, ...], message: str) -> None:
    path = tmp_path / "input.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "5", *extra])
    assert message in capsys.readouterr().err.replace("\n", " ")


def test_a_bare_number_with_measure_multiple_reads_as_turns(tmp_path: Path) -> None:
    record, _ = _run(tmp_path, "Interest cover,4.0,3.5,Multiple,Higher\n", "--multiple-threshold", "0.25")
    row = record["measure_rows"][0]  # type: ignore[index]
    assert (row["status"], Fraction(str(row["variance"]))) == ("U", Fraction("-0.5"))
