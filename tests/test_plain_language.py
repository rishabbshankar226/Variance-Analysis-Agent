"""Automated tests ensuring all user-visible intake messages are free of jargon (Phase 1).

Per variance-intake.md, jargon includes:
- snake_case keys or repr() quoting (such as 'budget_ytd' or !r)
- exception names (ValueError, BadZipFile, SyntaxError, etc.)
- CLI flag syntax (--sheet, --currency), unless told it is optional
- forbidden words: normalize, alias, schema, OOXML, archive, XML, DTD, payload, Row Kind, Unclassified
- exit codes (exit code 2, etc.)
"""

from __future__ import annotations

import re
import pytest

FORBIDDEN_WORDS = [
    "normalize",
    "normalizes",
    "alias",
    "aliases",
    "schema",
    "schemas",
    "ooxml",
    "archive",
    "xml",
    "dtd",
    "payload",
    "row kind",
    "unclassified",
]

EXCEPTION_NAMES = [
    "ValueError",
    "RuntimeError",
    "BadZipFile",
    "SyntaxError",
    "KeyError",
    "DecimalException",
    "InvalidOperation",
]


def assert_plain_language(text: str) -> None:
    """Assert that a user-facing message conforms to plain-language requirements."""
    # 1. Check snake_case quoting like 'budget_ytd' or single quoted identifiers
    snake_quote_match = re.search(r"'[a-z0-9]+_[a-z0-9_]+'", text)
    assert not snake_quote_match, f"Found snake_case key in message: {snake_quote_match.group(0)!r} in {text!r}"

    # 2. Check exception names
    for exc in EXCEPTION_NAMES:
        assert exc not in text, f"Found exception name {exc!r} in message: {text!r}"

    # 3. Check CLI flags unless described as optional
    flag_match = re.search(r"--[a-z0-9\-]+", text)
    if flag_match and "optional" not in text.lower():
        pytest.fail(f"Found mandatory CLI flag reference {flag_match.group(0)!r} in message: {text!r}")

    # 4. Check forbidden words (case-insensitive boundary match)
    for word in FORBIDDEN_WORDS:
        word_match = re.search(rf"\b{word}\b", text, re.IGNORECASE)
        assert not word_match, f"Found forbidden jargon word {word!r} in message: {text!r}"

    # 5. Check exit code
    assert "exit code" not in text.lower(), f"Found 'exit code' in message: {text!r}"


def test_intake_summary_plain_language() -> None:
    from variance_agent.intake import format_intake_summary, IntakeResult, CanonicalRole
    from decimal import Decimal

    res = IntakeResult(
        rows=[{"line_item": "Software Subscriptions", "budget": Decimal("100000"), "actual": Decimal("110000")}],
        sheet_name="BvA",
        header_row_number=5,
        column_mapping={
            CanonicalRole.LINE_ITEM: "Account Description",
            CanonicalRole.BUDGET: "Budget YTD",
            CanonicalRole.ACTUAL: "Actual YTD",
            CanonicalRole.ACCOUNT_ID: "GL Account",
        },
        ignored_columns=["Var $", "Var %"],
        rows_read=1,
        rows_skipped_count=4,
        skip_reasons=["4 title block rows above header"],
        visible_transformations=[
            "Ignored computed columns: Var $, Var %",
            "Used 'GL Account' as the account ID",
        ],
    )
    summary_text = format_intake_summary(res)
    assert_plain_language(summary_text)


def test_plain_analysis_error_sanitizes_jargon() -> None:
    from variance_agent.intake import plain_analysis_error

    raw_errors = [
        "ValueError: Row 2: required field 'Line Item' was not found. Accepted names: line_item, account.",
        "RuntimeError: Columns 'budget_amount' and 'budget' normalize to the same key 'budget'.",
        "ValueError: Multiple aliases for 'budget': budget_amount, planned. Supply one column per field.",
        "BadZipFile: Invalid Excel archive: file is not a zip file",
        "ValueError: Total Operating Expenses: ambiguous summary label; specify Row Kind as Detail, Total, or Subtotal.",
        "ValueError: Summary 'Total Expenses' does not reconcile to Expense detail rows; check for missing or overlapping data.",
        "ValueError: Row 4: data appears under a blank header beyond the header row.",
        "ValueError: Worksheet 'Reviewed' was not found; supply an exact --sheet name.",
        "ValueError: Type map value for 'Marketing' must be Revenue, Expense, or Unclassified.",
    ]

    for raw in raw_errors:
        cleaned = plain_analysis_error(raw)
        assert_plain_language(cleaned)


def test_unclassified_prompt_is_plain_language() -> None:
    from variance_agent.chat.handlers import handle_upload, handle_message
    from variance_agent.chat.session import Session, Phase
    from pathlib import Path

    fixture_path = Path(__file__).resolve().parent / "fixtures" / "realworld" / "fixture_h_120_line_gl.csv"
    session = Session()
    handle_upload(session, fixture_path.read_bytes(), fixture_path.name)
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp = handle_message(session, "USD")
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED
    assert_plain_language(resp.text)
