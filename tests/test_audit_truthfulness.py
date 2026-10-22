"""The audit's ``transformations`` must describe what intake did, also on --mapping replays."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from variance_agent import cli
from variance_agent.audit import CURRENT_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parent.parent

# Fictional export: title says thousands, header on row 3, one subtotal.
THOUSANDS_CSV = (
    "Fictional Co - Synthetic Data\n"
    "Q3 2026 Budget vs Actual (in thousands)\n"
    "Line Item,Type,Budget,Actual\n"
    "Product Revenue,Revenue,500,520\n"
    "Payroll Expense,Expense,300,320\n"
    "Total Expenses,,300,320\n"
)
# Revenue stored as negative credits in a minority of lines only (not a signed ledger).
SOME_NEGATIVE_CSV = (
    "Line Item,Type,Budget,Actual\n"
    "Product Revenue,Revenue,-500,-520\n"
    "Service Revenue,Revenue,200,210\n"
    "Support Revenue,Revenue,100,110\n"
    "Payroll Expense,Expense,300,320\n"
)
BASE = ["--period", "Q3", "--dollar-threshold", "10", "--percent-threshold", "5"]


def _mapping(tmp_path: Path, **fields: object) -> Path:
    mapping: dict[str, object] = {"column_mapping": {}, "unit_scale": None}
    mapping.update(fields)
    path = tmp_path / "mapping.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _replay(tmp_path: Path, csv_text: str, mapping: Path) -> dict[str, object]:
    source = tmp_path / "in.csv"
    source.write_text(csv_text, encoding="utf-8")
    audit = tmp_path / "audit.json"
    code = cli.main([
        str(source), "--mapping", str(mapping), *BASE,
        "-o", str(tmp_path / "r.md"), "--audit-json", str(audit),
    ])
    assert code == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "schemas" / f"audit-{CURRENT_SCHEMA_VERSION}.schema.json").read_text("utf-8"))
    Draft202012Validator(schema).validate(record)
    transformations = record["transformations"]
    assert isinstance(transformations, dict)
    return transformations


def test_unit_scale_detected_from_the_title_is_recorded_even_if_the_mapping_is_silent(
    tmp_path: Path,
) -> None:
    transformations = _replay(tmp_path, THOUSANDS_CSV, _mapping(tmp_path))
    assert transformations["unit_scale"] == "1000"


def test_mapping_unit_scale_is_recorded_when_the_file_is_silent(tmp_path: Path) -> None:
    csv_text = "Line Item,Type,Budget,Actual\nProduct Revenue,Revenue,500,520\nRent,Expense,100,90\n"
    transformations = _replay(tmp_path, csv_text, _mapping(tmp_path, unit_scale="1000"))
    assert transformations["unit_scale"] == "1000"


def test_header_row_is_the_row_intake_found_not_the_one_the_mapping_claims(tmp_path: Path) -> None:
    transformations = _replay(tmp_path, THOUSANDS_CSV, _mapping(tmp_path, header_row_number=7))
    assert transformations["header_row_number"] == 3
    assert transformations["column_mapping"] == {
        "line_item": "Line Item", "budget": "Budget", "actual": "Actual", "type": "Type",
    }


def test_flipped_items_are_listed_when_the_mapping_flips_signs(tmp_path: Path) -> None:
    transformations = _replay(tmp_path, SOME_NEGATIVE_CSV, _mapping(tmp_path, flip_signs=True))
    assert transformations["sign_flip"] is True
    assert transformations["flipped_line_items"] == ["Product Revenue"]


def test_excluded_totals_include_those_intake_detected(tmp_path: Path) -> None:
    transformations = _replay(tmp_path, THOUSANDS_CSV, _mapping(tmp_path, exclude_totals=["Misc Total"]))
    assert transformations["excluded_totals"] == ["Total Expenses", "Misc Total"]


def test_accounting_dashes_are_counted(tmp_path: Path) -> None:
    csv_text = "Line Item,Type,Budget,Actual\nRent,Expense,100,-\nFees,Expense,-,5\nSales,Revenue,10,10\n"
    transformations = _replay(tmp_path, csv_text, _mapping(tmp_path))
    assert transformations["zero_reads"] == {"accounting_dashes": 2, "blank_budgets": 0}
