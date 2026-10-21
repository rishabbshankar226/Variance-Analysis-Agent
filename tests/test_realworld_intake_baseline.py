"""Baseline tests for Phase 0 measuring current intake friction.

This test suite drives chat.handlers.handle_upload and handle_message against
all 9 synthetic real-world fixtures in tests/fixtures/realworld/.

Each test records today's outcome under commit a3ce6bb:
- Either a "dead end" with the exact first error message shown to Maya,
- Or the count of manual steps (as defined in variance-intake.md) required to reach a summary.

Per variance-intake.md:
- Manual step: 1 action outside the chat (editing/resaving file) or 1 message typed.
  Clicking a suggested chip counts as 0.5 step.
- Dead end: Maya ends up with no analysis and no fix action on screen.
"""

from __future__ import annotations

from pathlib import Path

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_fixture_a_erp_title_block_baseline() -> None:
    """Fixture a: ERP export with 4-row title block above header.
    
    Today's outcome: DEAD END on upload.
    openpyxl iter_rows reads row 1 title text as the header list.
    Row 5 headers ('GL Account', 'Account Description', etc.) trigger a blank-header
    violation because row 1 only populated column A.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_a_erp_title_block.xlsx"
    response = handle_upload(session, path.read_bytes(), path.name)
    
    # Maya ends up with no analysis and is returned to awaiting_file with no fix chip
    assert session.phase == Phase.AWAITING_FILE
    assert response.chips == ["Upload a different file"]
    expected_msg = "⚠️ Excel row 5: data appears under a blank header beyond the header row."
    assert response.text == expected_msg
    # Outcome: Dead end, 0 steps to summary, first message is the blank header error


def test_fixture_b_departmental_subtotals_baseline() -> None:
    """Fixture b: Departmental P&L with nested subtotals.
    
    Subtotals: Total Revenue, Gross Profit, Total Operating Expenses, Net Income.
    Today's outcome: DEAD END on analysis.
    Upload succeeds, but when period, thresholds, and currency are supplied,
    _run_analysis encounters ambiguous subtotal labels ('Total Operating Expenses')
    without a 'Row Kind' column, failing validation.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_b_departmental_subtotals.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert resp_upload.phase == Phase.AWAITING_PERIOD
    
    # Maya answers configuration prompts
    resp_period = handle_message(session, "Q3 2026")
    assert resp_period.phase == Phase.AWAITING_THRESHOLDS
    
    resp_thresh = handle_message(session, "$10,000 or 5%")
    assert resp_thresh.phase == Phase.AWAITING_CURRENCY
    
    resp_curr = handle_message(session, "USD")
    
    # Analysis fails on ambiguous summary label; Maya receives no actionable fix chip
    assert session.phase == Phase.AWAITING_CURRENCY or session.result is None
    expected_prefix = (
        "⚠️ Analysis failed: Total Operating Expenses: ambiguous summary label; "
        "specify Row Kind as Detail, Total, or Subtotal."
    )
    assert resp_curr.text.startswith(expected_prefix)
    assert resp_curr.chips == ["Upload a different file", "Help"]
    # Outcome: Dead end, analysis fails, first error requires manual file edit outside chat


def test_fixture_c_signed_ledger_baseline() -> None:
    """Fixture c: Signed ledger export (revenue negative credit, expense positive debit).
    
    Today's outcome: REACHES SUMMARY WITH DISTORTED / INVERTED FINANCIAL FACTS.
    Upload and setup succeed. Because revenues are negative numbers, variance
    calculations and favorability rules are reversed (e.g. higher actual revenue is
    marked unfavorable, and total revenue is negative).
    
    Manual step measurement:
    - In-chat setup: 3 typed messages (Period, Thresholds, Currency) = 3.0 steps.
      (Or 1 typed + 2 chips clicked = 2.0 steps).
    - To fix financial correctness under today's tool: Maya must preprocess the file
      outside the tool to flip signs (+1 external file edit step, +1 re-upload).
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_c_signed_ledger.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert resp_upload.phase == Phase.AWAITING_PERIOD
    
    # Step 1: Period
    handle_message(session, "Q3 2026")
    # Step 2: Thresholds
    handle_message(session, "$10,000 or 5%")
    # Step 3: Currency -> triggers analysis
    resp_curr = handle_message(session, "USD")
    assert "Analysis Complete" in resp_curr.text
    
    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    # Verify that without signed-ledger handling, revenue aggregate is negative
    assert session.result.revenue.actual < 0
    # Status of revenue exceeding budget is unfavorable because of negative sign
    row_prod = next(r for r in session.result.rows if "Product Revenue" in r.line_item)
    assert row_prod.status.value == "U"  # -520,000 actual vs -500,000 budget treated as unfavorable
    # Outcome: Reaches distorted summary in 3.0 typed steps (2.0 with chips);
    # requires external file preprocessing (+2 steps) for financial accuracy.


def test_fixture_d_thousands_dashes_blanks_baseline() -> None:
    """Fixture d: Report in thousands ('($000s)' in title) with dashes and blank budgets.
    
    Today's outcome: DEAD END on upload.
    Title in row 1 causes openpyxl header parsing to read row 1 as header.
    Row 2 headers appear as data under blank header beyond row 1.
    Furthermore, accounting dashes ('-') and blank strings are treated as missing
    in parsing.py, raising 'required field is missing'.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_d_thousands_dashes_blanks.xlsx"
    response = handle_upload(session, path.read_bytes(), path.name)
    
    assert session.phase == Phase.AWAITING_FILE
    assert response.chips == ["Upload a different file"]
    expected_msg = "⚠️ Excel row 2: data appears under a blank header beyond the header row."
    assert response.text == expected_msg
    # Outcome: Dead end on upload; first message is blank header error


def test_fixture_e_wide_monthly_baseline() -> None:
    """Fixture e: Wide monthly layout ('Jul-26 Budget', 'Jul-26 Actual', etc.).
    
    Today's outcome: DEAD END on analysis.
    Upload succeeds, but column names do not strictly match accepted aliases
    ('budget', 'plan', 'actual', etc.).
    Analysis fails with 'required field Budget was not found'.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_e_wide_monthly.xlsx"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert resp_upload.phase == Phase.AWAITING_PERIOD
    
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")
    
    expected_prefix = (
        "⚠️ Analysis failed: Row 2: required field 'Budget' was not found. "
        "Accepted names: budget, budget_amount, plan, planned."
    )
    assert resp_curr.text.startswith(expected_prefix)
    assert resp_curr.chips == ["Upload a different file", "Help"]
    # Outcome: Dead end; requires manual unpivoting / column renaming outside chat


def test_fixture_f_budget_actuals_separate_baseline() -> None:
    """Fixture f: Budget and actuals as two separate files.
    
    Today's outcome: DEAD END.
    Uploading the budget file fails during analysis because there is no 'Actual' column.
    There is no capability in today's chat to upload a second file or join by GL account.
    """
    session = Session()
    path_bgt = FIXTURES_DIR / "fixture_f_budget_separate.csv"
    handle_upload(session, path_bgt.read_bytes(), path_bgt.name)
    assert session.phase == Phase.AWAITING_PERIOD
    
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")
    
    # Analysis fails on missing line item or actual
    assert "required field" in resp_curr.text
    assert resp_curr.chips == ["Upload a different file", "Help"]
    # Outcome: Dead end; requires manual Excel VLOOKUP/join before tool intake


def test_fixture_g_cover_page_active_baseline() -> None:
    """Fixture g: Second sheet has BvA data, but active sheet is a cover page.
    
    Today's outcome:
    - Default upload path: Reads cover page, fails analysis with missing columns (DEAD END).
    - Manual sheet command: If Maya notices '(2 sheets available; switch with sheet <name>)',
      she can type 'sheet BvA' before entering period.
      Takes 4 manual steps (type sheet command, type period, type thresholds, type currency).
    """
    # Case 1: Maya does not switch sheet and answers guided prompts
    session_default = Session()
    path = FIXTURES_DIR / "fixture_g_cover_page_active.xlsx"
    handle_upload(session_default, path.read_bytes(), path.name)
    handle_message(session_default, "Q3 2026")
    handle_message(session_default, "$10,000 or 5%")
    resp_fail = handle_message(session_default, "USD")
    assert "required field 'Line Item' was not found" in resp_fail.text
    assert resp_fail.chips == ["Upload a different file", "Help"]
    
    # Case 2: Maya explicitly switches sheets using CLI-style command
    session_switched = Session()
    handle_upload(session_switched, path.read_bytes(), path.name)
    # Manual step 1: type sheet switch command
    resp_sw = handle_message(session_switched, "sheet BvA")
    assert session_switched.worksheet == "BvA"
    assert "Switched to worksheet **'BvA'**" in resp_sw.text
    # Manual step 2: period
    handle_message(session_switched, "Q3 2026")
    # Manual step 3: thresholds
    handle_message(session_switched, "$10,000 or 5%")
    # Manual step 4: currency
    resp_ok = handle_message(session_switched, "USD")
    assert "Analysis Complete" in resp_ok.text
    assert session_switched.phase == Phase.EXPLORING
    assert session_switched.result is not None
    # Outcome: Dead end by default; 4.0 manual typed steps if Maya discovers 'sheet BvA' command


def test_fixture_h_120_line_gl_unclassified_friction_baseline() -> None:
    """Fixture h: 120-line GL export with account numbers and no Type column.
    
    Today's outcome: MASSIVE FRICTION (120 one-by-one classification questions).
    Upload and configuration succeed, but because account numbers (4000-4999, 5000-8999)
    are not recognized by keyword regex, all 120 rows enter RESOLVE_UNCLASSIFIED.
    
    Maya must answer 120 sequential questions:
    - 3 setup steps (period, thresholds, currency)
    - 120 classification prompts:
      - If typed: 120 * 1.0 = 120 steps -> 123 total steps.
      - If clicking chips: 120 * 0.5 = 60 steps -> 63 total steps.
      - If 'Skip all' chip clicked: 0.5 step -> 3.5 total steps (all rows excluded).
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_h_120_line_gl.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert resp_upload.phase == Phase.AWAITING_PERIOD
    
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")
    
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED
    assert len(session.unclassified_queue) == 120
    assert "Analysis complete, but **120** line items are unclassified." in resp_curr.text
    assert resp_curr.chips == ["Revenue", "Expense", "Skip", "Skip all"]
    
    # Case 1: If Maya classifies an item, and then clicks "Skip all",
    # current handlers.py:_handle_classify re-runs analysis with non-empty type_map,
    # which detects the remaining 119 unclassified lines and loops back to RESOLVE_UNCLASSIFIED!
    resp_step1 = handle_message(session, "Revenue")
    assert len(session.unclassified_queue) == 119
    assert "Got it. 119 remaining." in resp_step1.text

    resp_step2 = handle_message(session, "Skip all")
    # Current behavior: "Skip all" after partial classification re-populates the queue!
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED
    assert len(session.unclassified_queue) == 119
    assert "Analysis complete, but **119** line items are unclassified." in resp_step2.text

    # Case 2: Immediate "Skip all" before any item is classified (type_map empty)
    session_immediate_skip = Session()
    handle_upload(session_immediate_skip, path.read_bytes(), path.name)
    handle_message(session_immediate_skip, "Q3 2026")
    handle_message(session_immediate_skip, "$10,000 or 5%")
    handle_message(session_immediate_skip, "USD")
    assert len(session_immediate_skip.unclassified_queue) == 120
    resp_imm_skip = handle_message(session_immediate_skip, "Skip all")
    assert "Analysis Complete" in resp_imm_skip.text
    assert session_immediate_skip.phase == Phase.EXPLORING
    assert session_immediate_skip.result is not None
    # All 120 rows remain unclassified and excluded from revenue/expense totals
    assert len(session_immediate_skip.result.material_rows) == 0
    # Outcome: Reaching full classification requires 120 sequential answers (123 manual typed steps,
    # or 63 chip clicks). Partial classification breaks "Skip all" into a loop.


def test_fixture_i_pasted_tsv_baseline() -> None:
    """Fixture i: Tab-separated block pasted directly into chat.
    
    Today's outcome: DEAD END.
    In Phase.AWAITING_FILE, handle_message rejects any raw text that is not
    a system intent (reset, help, etc.), instructing Maya to upload a file instead.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_i_pasted_tsv.txt"
    pasted_text = path.read_text(encoding="utf-8")
    
    response = handle_message(session, pasted_text)
    
    assert session.phase == Phase.AWAITING_FILE
    expected_msg = "Please upload a file using the drop zone above. Supported formats: CSV, JSON, XLSX, XLSM."
    assert response.text == expected_msg
    # Outcome: Dead end; pasted tabular data is rejected outright
