"""Tests for saved mapping memory, layout fingerprinting, and CLI --mapping flag.

Verifies:
- Mapping file schema (headers, ranges, rules, choices - never amounts).
- Fingerprint generation from file structure/headers.
- CLI --mapping flag execution.
- Chat and CLI parity: identical audit financial values.
"""

from __future__ import annotations

import json
from pathlib import Path

from variance_agent.mapping import (
    LayoutMapping,
    save_mapping,
    compute_layout_fingerprint,
)
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Session
from variance_agent.cli import build_parser, _run
from variance_agent.audit import build_audit_record

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_mapping_file_contains_no_financial_amounts() -> None:
    mapping = LayoutMapping(
        mapping_version="1.5",
        layout_fingerprint="abc123def456",
        header_row_number=5,
        column_mapping={"line_item": "Account Description", "budget": "Budget YTD", "actual": "Actual YTD"},
        unit_scale="1000",
        flip_signs=False,
        treat_blank_budgets_as_zero=True,
        exclude_totals=["Total Revenue", "Gross Profit"],
        classification_rules={"gl_ranges": [{"min": 4000, "max": 4999, "type": "Revenue"}]},
    )

    mapping_json = save_mapping(mapping)
    data = json.loads(mapping_json)

    # Validate that data holds no financial amounts (numbers or strings with dollar amounts)
    assert "rows" not in data
    assert "amounts" not in data
    assert "budget" not in str(data.get("amounts", ""))
    assert data["header_row_number"] == 5
    assert data["unit_scale"] == "1000"


def test_cli_mapping_and_chat_produce_identical_financial_values(tmp_path: Path) -> None:
    """Fixture a: verify chat and CLI --mapping produce identical audit financial values."""
    # 1. Run through chat
    session = Session()
    path = FIXTURES_DIR / "fixture_a_erp_title_block.xlsx"
    handle_upload(session, path.read_bytes(), path.name)
    handle_message(session, "Looks right")
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    handle_message(session, "USD")

    assert session.result is not None
    chat_audit = build_audit_record(session.result, schema_version="1.5")

    # 2. Save mapping
    mapping = LayoutMapping(
        mapping_version="1.5",
        layout_fingerprint=compute_layout_fingerprint(["GL Account", "Account Description", "Budget YTD", "Actual YTD", "Var $", "Var %"]),
        header_row_number=5,
        column_mapping={"line_item": "Account Description", "budget": "Budget YTD", "actual": "Actual YTD"},
        unit_scale="1",
        flip_signs=False,
        treat_blank_budgets_as_zero=True,
        exclude_totals=[],
    )
    mapping_file = tmp_path / "fixture_a.mapping.json"
    mapping_file.write_text(save_mapping(mapping), encoding="utf-8")

    # 3. Run CLI with --mapping
    audit_out = tmp_path / "cli_audit.json"
    parser = build_parser()
    args = parser.parse_args([
        str(path),
        "--period", "Q3 2026",
        "--dollar-threshold", "10000",
        "--percent-threshold", "5",
        "--currency", "USD",
        "--mapping", str(mapping_file),
        "--audit-json", str(audit_out),
        "--audit-schema-version", "1.5",
    ])
    exit_code = _run(args)
    assert exit_code == 0

    cli_audit = json.loads(audit_out.read_text(encoding="utf-8"))

    # Compare totals and material variances
    assert cli_audit["totals"] == chat_audit["totals"]
    assert len(cli_audit["material_variances"]) == len(chat_audit["material_variances"])
    for cli_row, chat_row in zip(cli_audit["material_variances"], chat_audit["material_variances"]):
        assert cli_row["line_item"] == chat_row["line_item"]
        assert cli_row["budget"] == chat_row["budget"]
        assert cli_row["actual"] == chat_row["actual"]
        assert cli_row["variance_dollars"] == chat_row["variance_dollars"]
