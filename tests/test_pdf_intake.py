"""PDF filings through assisted intake, the chatbot and the command line (fictional fixtures)."""

from __future__ import annotations

import csv
import io
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

import variance_agent.cli as cli
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session
from variance_agent.intake import format_intake_summary, rank_statements, read_input_assisted
from variance_agent.models import ComparisonBasis
from variance_agent.pdf_tables import extract_statement_tables
from variance_agent.statement_shape import shape_income_statement

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"
TEN_K = FIXTURES_DIR / "fixture_o_10k_statements.pdf"
TEN_Q = FIXTURES_DIR / "fixture_p_10q_three_and_nine_months.pdf"
COMBINED_10Q = FIXTURES_DIR / "fixture_s_combined_10q.pdf"
SCANNED = FIXTURES_DIR / "fixture_q_scanned_no_text.pdf"
INCOME = "Consolidated Statements of Operations (p. 4)"
BALANCE = "Consolidated Balance Sheets (pp. 5-6)"
BASE = ["--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "5"]

pytestmark = pytest.mark.skipif(
    __import__("importlib").util.find_spec("pdfplumber") is None,
    reason="the optional [pdf] extra is not installed",
)


def _read(path: Path, **kwargs: object):  # type: ignore[no-untyped-def]
    return read_input_assisted(path.read_bytes(), ".pdf", filename=path.name, **kwargs)  # type: ignore[arg-type]


# --- intake -----------------------------------------------------------------


def test_10k_reads_income_statement_as_prior_period_comparison() -> None:
    result = _read(TEN_K)
    assert not result.has_fatal_errors
    assert result.source_kind == "pdf"
    assert result.sheet_name == INCOME
    assert result.source_pages == (4,)
    assert result.available_sheets == [INCOME, BALANCE]
    assert [s.name for s in result.candidate_sheets] == [INCOME, BALANCE]
    assert result.comparison_basis is ComparisonBasis.PRIOR_PERIOD
    assert result.comparison_label == "FY2024"
    assert result.detected_unit_multiplier == Decimal("1000000")
    first = result.rows[0]
    assert (first["line_item"], first["actual"], first["budget"]) == (
        "Product revenue", Decimal("1250400000.0"), Decimal("1100200000.0"))
    assert "Total revenue" in result.detected_totals


def test_reader_notes_lead_the_visible_adjustments() -> None:
    result = _read(TEN_K)
    table = extract_statement_tables(TEN_K.read_bytes(), TEN_K.name)[0]
    shaped = shape_income_statement(table.raw_rows)
    assert result.reader_notes == [*table.notes, *shaped.audit_notes]
    assert result.visible_transformations[0] == f"Read '{INCOME}' from the PDF"
    shown = [*table.notes, *shaped.notes]
    assert result.visible_transformations[1:1 + len(shown)] == shown
    assert "Labeled 'Product revenue' as revenue" in result.reader_notes


def test_statement_lines_are_labeled_and_subtotals_left_out() -> None:
    result = _read(TEN_K)
    assert [(r["line_item"], r["type"]) for r in result.rows] == [
        ("Product revenue", "Revenue"),
        ("Subscription, licensing and other services revenue", "Revenue"),
        ("Cost of revenue", "Expense"),
        ("Research and development", "Expense"),
        ("Selling, general and administrative", "Expense"),
        ("Restructuring charges (1)", "Expense"),
        ("Other income (expense), net", "Revenue"),
        ("Provision for income taxes", "Expense"),
    ]
    assert result.detected_totals[:6] == [
        "Total revenue", "Gross profit", "Total operating expenses", "Operating income",
        "Income before income taxes", "Net income"]


def test_pdf_rows_match_the_same_statement_as_csv() -> None:
    table = extract_statement_tables(TEN_K.read_bytes(), TEN_K.name)[0]
    buffer = io.StringIO()
    csv.writer(buffer).writerows(shape_income_statement(table.raw_rows).rows)
    from_csv = read_input_assisted(buffer.getvalue().encode(), ".csv", filename="same.csv")
    from_pdf = _read(TEN_K)
    assert from_pdf.rows == from_csv.rows
    assert from_pdf.comparison_label == from_csv.comparison_label
    assert from_pdf.detected_unit_multiplier == from_csv.detected_unit_multiplier


def test_sheet_picks_another_income_statement() -> None:
    nine = "Condensed Consolidated Statements of Operations, Nine Months Ended (p. 1)"
    result = _read(TEN_Q, sheet=nine)
    assert result.sheet_name == nine
    assert result.comparison_label == "Sep 2025"
    assert result.detected_unit_multiplier == Decimal("1000")
    assert result.rows[0]["actual"] == Decimal("150880000")


def test_balance_sheet_is_listed_but_not_compared() -> None:
    result = _read(TEN_K, sheet=BALANCE)
    assert result.has_fatal_errors
    assert result.available_sheets == [INCOME]
    assert result.fatal_error_message == (
        f"'{BALANCE}' lists assets, liabilities and equity, which can't be compared as revenue "
        f"and expense yet. Choose an income statement instead: {INCOME}."
    )


def test_unknown_statement_lists_the_ones_found() -> None:
    result = _read(TEN_K, sheet="Cash flows")
    assert result.has_fatal_errors
    assert result.fatal_error_message == (
        f"No statement called 'Cash flows' was found in '{TEN_K.name}'. "
        f"Statements found: {INCOME}, {BALANCE}."
    )


def test_income_statement_is_preferred_wherever_it_appears() -> None:
    ranked = rank_statements([
        "Consolidated Balance Sheets (p. 3)",
        "Consolidated Statements of Cash Flows (p. 4)",
        "Consolidated Statements of Comprehensive Income (p. 5)",
        "Consolidated Statements of Income (p. 6)",
    ])
    assert [s.name for s in ranked] == [
        "Consolidated Statements of Income (p. 6)",
        "Consolidated Balance Sheets (p. 3)",
        "Consolidated Statements of Cash Flows (p. 4)",
        "Consolidated Statements of Comprehensive Income (p. 5)",
    ]
    assert ranked[0].rationale == "income statement"


def test_unreadable_pdf_is_a_plain_fatal_message() -> None:
    result = _read(SCANNED)
    assert result.has_fatal_errors
    assert result.fatal_error_message is not None
    assert "looks like a scanned image" in result.fatal_error_message


def test_missing_pdf_extra_is_a_plain_fatal_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pdfplumber", None)
    result = read_input_assisted(b"%PDF-1.4 not cached", ".pdf", filename="filing.pdf")
    assert result.has_fatal_errors
    assert "pip install 'variance-analysis-agent[pdf]'" in (result.fatal_error_message or "")


def test_summary_names_the_statement_not_a_worksheet() -> None:
    summary = format_intake_summary(_read(TEN_K))
    assert f"- **Statement:** {INCOME}" in summary
    assert "Worksheet" not in summary
    assert "Header row" not in summary


def test_unsupported_format_lists_every_format() -> None:
    result = read_input_assisted(b"x", ".docx", filename="memo.docx")
    assert result.fatal_error_message == (
        "Unsupported input format '.docx'. Please use an Excel workbook (.xlsx, .xlsm), "
        "a CSV, TSV, JSON or PDF file."
    )


# --- chat -------------------------------------------------------------------


def _upload(path: Path) -> tuple[Session, str, list[str]]:
    session = Session()
    response = handle_upload(session, path.read_bytes(), path.name)
    return session, response.text, list(response.chips or [])


def test_chat_upload_shows_the_summary_with_statement_chips() -> None:
    session, text, chips = _upload(TEN_K)
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert f"- **Statement:** {INCOME}" in text
    assert f"Read '{INCOME}' from the PDF" in text
    assert chips == ["Looks right", "Change something"]  # the balance sheet can't be compared
    _, _, combined_chips = _upload(COMBINED_10Q)
    assert combined_chips[:3] == [
        "Looks right",
        "Statement Northwind Fictional Holdings, Inc.: Statements of Consolidated Operations, "
        "Six Months Ended (p. 1)",
        "Change something",
    ]


def test_chat_lists_and_switches_statements() -> None:
    session, _, _ = _upload(TEN_K)
    listing = handle_message(session, "statements")
    assert "**Statements in '" in listing.text and "(2 total)" in listing.text
    assert "worksheet" not in listing.text.lower()
    refused = handle_message(session, "statement balance")
    assert refused.text.startswith(f"⚠️ '{BALANCE}' lists assets")
    assert "Failed to load" not in refused.text
    assert refused.chips == ["Show statements"]  # the only income statement is already open
    assert session.worksheet == INCOME


def test_chat_pdf_runs_to_analysis_and_audit_17() -> None:
    session, _, _ = _upload(COMBINED_10Q)
    handle_message(session, "Looks right")
    handle_message(session, "Q2 2026")
    handle_message(session, "$10 or 5%")
    response = handle_message(session, "USD")
    assert session.phase == Phase.EXPLORING, response.text  # every line labeled; no questions
    assert session.result is not None
    net = session.result.revenue.actual - session.result.expenses.actual
    assert net == Decimal("701000000")  # the filing's net income of 700, off by its rounding
    audit = handle_message(session, "export audit")
    assert audit.download is not None
    record = json.loads(next(iter(audit.download.values())))
    assert record["schema_version"] == "1.7"
    document = record["source"]["document"]
    assert document["kind"] == "pdf"
    assert document["statement"] == session.worksheet
    assert document["pages"] == [1]
    assert "Read column 'Three Months Ended June 30, 2026' as Jun 2026" in document["reader_notes"]


# --- command line -----------------------------------------------------------


def test_cli_assisted_reads_pdf_and_records_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out, audit = tmp_path / "report.md", tmp_path / "audit.json"
    assert cli.main([str(TEN_K), *BASE, "--assisted", "-o", str(out),
                     "--audit-json", str(audit)]) == 0
    err = capsys.readouterr().err
    assert f"[assisted intake] Read '{INCOME}' from the PDF" in err
    assert "[assisted intake] Read column 'Year Ended December 31, 2025' as FY2025" in err
    record = json.loads(audit.read_text(encoding="utf-8"))
    assert record["source"]["worksheet"] == INCOME
    assert record["source"]["document"]["pages"] == [4]
    assert record["comparison"] == {"basis": "prior_period", "label": "FY2024"}


def test_cli_sheet_picks_a_statement(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    nine = "Condensed Consolidated Statements of Operations, Nine Months Ended (p. 1)"
    assert cli.main([str(TEN_Q), *BASE, "--assisted", "--sheet", nine,
                     "--audit-json", str(audit), "-o", str(tmp_path / "r.md")]) == 0
    assert json.loads(audit.read_text(encoding="utf-8"))["source"]["worksheet"] == nine


def test_cli_strict_mode_points_pdf_at_assisted(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(TEN_K), *BASE])
    assert exc_info.value.code == 2
    assert "PDF files are read with --assisted" in capsys.readouterr().err


def test_cli_pdf_refuses_audit_schemas_before_17(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    audit = tmp_path / "audit.json"
    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(TEN_K), *BASE, "--assisted", "--audit-json", str(audit),
                  "--audit-schema-version", "1.6"])
    assert exc_info.value.code == 2
    assert "use --audit-schema-version 1.7 for PDF input" in capsys.readouterr().err
    assert not audit.exists()


def test_shaped_signs_are_not_flipped_again_as_a_signed_ledger(tmp_path: Path) -> None:
    """A gain printed negative in one year is a resolved sign, not a credit-ledger revenue."""
    from tests.fixtures.realworld.minipdf import Page, write_pdf

    page = Page()
    page.text(72, 40, "FICTIONAL SYNTHETIC DATA - NORTHWIND FICTIONAL HOLDINGS, INC.")
    page.text(72, 60, "Consolidated Statements of Comprehensive Income", size=10)
    page.text(72, 78, "(millions)")
    page.right(460, 78, "2025")
    page.right(540, 78, "2024")
    for i, (label, now, before) in enumerate([
        ("Net earnings", "4,091", "4,138"),
        ("Pension benefit liabilities", "22", "(23)"),
        ("Currency translation adjustment", "(20)", "(18)"),
        ("Other comprehensive income / (loss)", "2", "(41)"),
        ("Comprehensive income", "4,093", "4,097"),
    ]):
        page.text(72, 96 + i * 13, label)
        page.right(460, 96 + i * 13, now)
        page.right(540, 96 + i * 13, before)
    path = tmp_path / "comprehensive.pdf"
    write_pdf(path, [page])

    result = _read(path)
    assert not result.detected_signed_ledger
    pension = next(r for r in result.rows if r["line_item"] == "Pension benefit liabilities")
    assert (pension["type"], pension["actual"], pension["budget"]) == (
        "Revenue", Decimal("22000000"), Decimal("-23000000"))


def test_shaped_lines_are_not_mistaken_for_sums(tmp_path: Path) -> None:
    """A line that happens to equal the sum of the two above it stays a line."""
    from tests.fixtures.realworld.minipdf import Page, write_pdf

    page = Page()
    page.text(72, 40, "FICTIONAL SYNTHETIC DATA - NORTHWIND FICTIONAL HOLDINGS, INC.")
    page.text(72, 60, "Consolidated Statements of Operations", size=10)
    page.text(72, 78, "(In millions)")
    page.right(460, 78, "2025")
    page.right(540, 78, "2024")
    for i, (label, now, before) in enumerate([
        ("Net sales", "1,000", "900"),
        ("Rent expense", "10", "20"),
        ("Freight expense", "15", "25"),
        ("Insurance expense", "25", "45"),
        ("Operating income", "950", "810"),
    ]):
        page.text(72, 96 + i * 13, label)
        page.right(460, 96 + i * 13, now)
        page.right(540, 96 + i * 13, before)
    path = tmp_path / "sums.pdf"
    write_pdf(path, [page])

    result = _read(path)
    assert [r["line_item"] for r in result.rows] == [
        "Net sales", "Rent expense", "Freight expense", "Insurance expense"]
    assert result.detected_totals == ["Operating income"]
