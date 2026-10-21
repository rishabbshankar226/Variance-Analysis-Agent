"""Assisted-intake transformations recorded in audits from the chat and the CLI.

Verifies:
- A chat audit export records the header row, unit scale, excluded subtotals and blank
  budget choice that assisted intake detected and Maya confirmed.
- A layout mapping saved in the chat is recorded by digest only while it still describes
  the analysis being exported.
- The shared helper reproduces the CLI's --assisted and --mapping dicts exactly, so CLI
  audits stay byte-identical.

All data here is fictional and synthetic.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Session
from variance_agent.intake import IntakeResult, audit_transformations, read_input_assisted
from variance_agent.mapping import LayoutMapping, load_mapping, mapping_sha256

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "realworld"

# Fictional ERP export: title block, amounts in thousands, two subtotals, one unbudgeted line.
TITLE_BLOCK_CSV = (
    "Fictional Co - Synthetic Data\n"
    "Q3 2026 Budget vs Actual (in thousands)\n"
    "Line Item,Budget,Actual\n"
    "Product Revenue,500,520\n"
    "Service Revenue,200,190\n"
    "Total Revenue,700,710\n"
    "Payroll Expense,300,320\n"
    "Rent Expense,100,100\n"
    "Pilot Program Expense,,25\n"
    "Total Expenses,400,445\n"
).encode("utf-8")


def _validator(version: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / f"audit-{version}.schema.json").read_text("utf-8"))
    return Draft202012Validator(schema)


def _analyze_in_chat(session: Session, data: bytes, blank_choice: str) -> None:
    handle_upload(session, data, "fictional_q3.csv")
    for message in (blank_choice, "Looks right", "Q3 2026", "$10,000 or 5%", "USD"):
        handle_message(session, message)
    assert session.result is not None


def _export_audit(session: Session) -> dict[str, object]:
    response = handle_message(session, "export audit")
    assert response.download is not None
    record: dict[str, object] = json.loads(next(iter(response.download.values())))
    return record


def test_chat_audit_records_confirmed_assisted_intake_transformations() -> None:
    session = Session()
    _analyze_in_chat(session, TITLE_BLOCK_CSV, "Treat blank budgets as 0 (unbudgeted)")

    record = _export_audit(session)

    assert record["schema_version"] == "1.6"
    assert record["transformations"] == {
        "header_row_number": 3,
        "column_mapping": {"line_item": "Line Item", "budget": "Budget", "actual": "Actual"},
        "ignored_columns": [],
        "sign_flip": False,
        "flipped_line_items": [],
        "unit_scale": "1000",
        "zero_reads": {"accounting_dashes": 0, "blank_budgets": 1},
        "excluded_totals": ["Total Revenue", "Total Expenses"],
        "period_selection": None,
        "classification_rules": None,
        "mapping_file_sha256": None,
    }
    _validator("1.6").validate(record)


def test_chat_audit_records_kept_blank_budgets_as_no_zero_reads() -> None:
    session = Session()
    _analyze_in_chat(session, TITLE_BLOCK_CSV, "Keep blank budgets")

    transformations = _export_audit(session)["transformations"]

    assert isinstance(transformations, dict)
    assert transformations["zero_reads"] == {"accounting_dashes": 0, "blank_budgets": 0}
    assert transformations["unit_scale"] == "1000"


def test_chat_audit_records_saved_layout_mapping_digest() -> None:
    session = Session()
    _analyze_in_chat(session, TITLE_BLOCK_CSV, "Treat blank budgets as 0 (unbudgeted)")
    saved = handle_message(session, "Save layout mapping")
    match = re.search(r"```json\n(.*?)\n```", saved.text, re.DOTALL)
    assert match is not None
    mapping = load_mapping(match.group(1))

    record = _export_audit(session)

    transformations = record["transformations"]
    assert isinstance(transformations, dict)
    # The same digest the CLI records when this file is replayed with --mapping.
    assert transformations["mapping_file_sha256"] == mapping_sha256(mapping)
    assert transformations["header_row_number"] == 3
    assert transformations["unit_scale"] == "1000"
    assert transformations["excluded_totals"] == ["Total Revenue", "Total Expenses"]
    assert transformations["period_selection"] == "Q3 2026"
    _validator("1.6").validate(record)


def test_chat_audit_ignores_mapping_saved_for_an_earlier_file() -> None:
    session = Session()
    _analyze_in_chat(session, TITLE_BLOCK_CSV, "Treat blank budgets as 0 (unbudgeted)")
    handle_message(session, "Save layout mapping")
    assert session.layout_mapping is not None

    plain = b"Line Item,Budget,Actual\nProduct Revenue,500,520\nPayroll Expense,300,320\n"
    handle_upload(session, plain, "fictional_plain.csv")
    for message in ("Q3 2026", "$10,000 or 5%", "USD"):
        handle_message(session, message)

    transformations = _export_audit(session)["transformations"]

    assert isinstance(transformations, dict)
    assert transformations["mapping_file_sha256"] is None
    assert transformations["header_row_number"] == 1
    assert transformations["unit_scale"] is None


# The dicts cli.py built before the shared helper existed: the oracle for byte-identity.
def _old_cli_assisted(intake_res: IntakeResult) -> dict[str, object]:
    col_map = {role.value: name for role, name in intake_res.column_mapping.items()}
    return {
        "header_row_number": intake_res.header_row_number,
        "column_mapping": col_map,
        "ignored_columns": intake_res.ignored_columns,
        "sign_flip": intake_res.detected_signed_ledger,
        "flipped_line_items": intake_res.negative_revenue_items if intake_res.detected_signed_ledger else [],
        "unit_scale": str(intake_res.detected_unit_multiplier) if intake_res.detected_unit_multiplier != Decimal("1") else None,
        "zero_reads": {
            "accounting_dashes": 0,
            "blank_budgets": len(intake_res.blank_budget_items),
        },
        "excluded_totals": intake_res.detected_totals,
        "period_selection": None,
        "classification_rules": None,
        "mapping_file_sha256": None,
    }


def _old_cli_mapping(mapping_obj: LayoutMapping, intake_res: IntakeResult) -> dict[str, object]:
    return {
        "header_row_number": mapping_obj.header_row_number,
        "column_mapping": mapping_obj.column_mapping,
        "ignored_columns": intake_res.ignored_columns,
        "sign_flip": mapping_obj.flip_signs,
        "flipped_line_items": intake_res.negative_revenue_items if mapping_obj.flip_signs else [],
        "unit_scale": mapping_obj.unit_scale if mapping_obj.unit_scale != "1" else None,
        "zero_reads": {
            "accounting_dashes": 0,
            "blank_budgets": len(intake_res.blank_budget_items) if mapping_obj.treat_blank_budgets_as_zero else 0,
        },
        "excluded_totals": mapping_obj.exclude_totals,
        "period_selection": mapping_obj.period_column_selection,
        "classification_rules": mapping_obj.classification_rules,
        "mapping_file_sha256": mapping_sha256(mapping_obj),
    }


ASSISTED_SOURCES = (
    ("title block", TITLE_BLOCK_CSV, ".csv"),
    ("subtotals", (FIXTURES_DIR / "fixture_b_departmental_subtotals.csv").read_bytes(), ".csv"),
    ("signed ledger", (FIXTURES_DIR / "fixture_c_signed_ledger.csv").read_bytes(), ".csv"),
    ("forecast", (FIXTURES_DIR / "fixture_k_forecast.csv").read_bytes(), ".csv"),
)


def test_helper_matches_cli_assisted_dict() -> None:
    for name, data, suffix in ASSISTED_SOURCES:
        # The CLI's --assisted path always reads blank budgets as zero.
        intake_res = read_input_assisted(data, suffix, treat_blank_budgets_as_zero=True)
        assert not intake_res.has_fatal_errors, name
        assert audit_transformations(intake_res) == _old_cli_assisted(intake_res), name


def test_helper_matches_cli_mapping_dict() -> None:
    mappings = (
        LayoutMapping(
            column_mapping={"line_item": "Line Item", "budget": "Budget", "actual": "Actual"},
            exclude_totals=["Total Revenue"],
            period_column_selection="Q3 2026",
            classification_rules={"keywords": {"Revenue": "Revenue", "Expense": "Expense"}},
        ),
        LayoutMapping(unit_scale="1000", flip_signs=True, treat_blank_budgets_as_zero=False),
        LayoutMapping(unit_scale="1", header_row_number=3),
        LayoutMapping(unit_scale=None),
    )
    for mapping in mappings:
        for name, data, suffix in ASSISTED_SOURCES:
            intake_res = read_input_assisted(
                data, suffix, treat_blank_budgets_as_zero=mapping.treat_blank_budgets_as_zero,
            )
            assert not intake_res.has_fatal_errors, name
            assert audit_transformations(intake_res, mapping) == _old_cli_mapping(mapping, intake_res), name
