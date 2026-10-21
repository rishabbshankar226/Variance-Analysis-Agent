"""Real-world intake tests measuring Phase 1 improvements against the 9 synthetic fixtures.

Per Phase 1 acceptance criteria:
- Fixtures a, d, g and i reach the "Here's how I read your file" summary with no dead end.
- The jargon test passes.
- Every contract fixture report and audit is byte-identical through the CLI.
- Each visible transformation has a test proving it appears in the summary.
"""

from __future__ import annotations

from pathlib import Path

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"


def test_fixture_a_erp_title_block_intake() -> None:
    """Fixture a: ERP export with 4-row title block above header.
    
    Phase 1 outcome: NO DEAD END.
    HeaderDetector identifies Row 5 as the true header row, skips rows 1-4,
    maps 'Account Description' to Line Item, 'Sep-26 Budget' to Budget, and 'Sep-26 Actual' to Actual.
    Presents 'Here's how I read your file' summary with 'Looks right' chip.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_a_erp_title_block.xlsx"
    response = handle_upload(session, path.read_bytes(), path.name)
    
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Here's how I read your file:" in response.text
    assert "Header row:** Row 5" in response.text
    assert "4 title block rows above header" in response.text
    assert "Line item from 'Account Description'" in response.text
    assert "Budget from 'Budget YTD'" in response.text
    assert "Actual from 'Actual YTD'" in response.text
    assert "Account ID from 'GL Account'" in response.text
    assert "Looks right" in (response.chips or [])

    # Confirming proceeds directly to period prompt
    resp_confirm = handle_message(session, "Looks right")
    assert resp_confirm.phase == Phase.AWAITING_PERIOD
    assert "What reporting period does this analysis cover?" in resp_confirm.text


def test_fixture_b_departmental_subtotals_baseline() -> None:
    """Fixture b: Departmental P&L with nested subtotals.
    
    Phase 2 outcome: Subtotals detected and proposed for exclusion.
    Reaches EXPLORING with clean analysis.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_b_departmental_subtotals.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert resp_upload.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Detected 4 subtotal/total rows" in resp_upload.text
    assert "Looks right" in (resp_upload.chips or [])
    
    handle_message(session, "Looks right")
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")
    if session.phase == Phase.RESOLVE_UNCLASSIFIED:
        resp_curr = handle_message(session, "Expense")
    
    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert "Analysis Complete" in resp_curr.text


def test_fixture_c_signed_ledger_baseline() -> None:
    """Fixture c: Signed ledger export (revenue negative credit, expense positive debit).
    
    Phase 2 outcome: Detects negative revenue credits, proposes sign flip.
    Reaches EXPLORING with positive revenue.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_c_signed_ledger.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert resp_upload.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "positive-cost convention" in resp_upload.text
    assert "Looks right" in (resp_upload.chips or [])
    
    handle_message(session, "Looks right")
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")
    assert "Analysis Complete" in resp_curr.text
    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert session.result.revenue.actual > 0


def test_fixture_d_thousands_dashes_blanks_intake() -> None:
    """Fixture d: Report in thousands with accounting dashes and blank budgets.
    
    Phase 1 outcome: NO DEAD END.
    1. Prompts Maya: 'Treat blank budgets as 0 (unbudgeted)?'
    2. After confirmation, reads dashes as 0, treats blank budgets as 0,
       and presents 'Here's how I read your file' summary.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_d_thousands_dashes_blanks.xlsx"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    
    # Step 1: Blank budget confirmation prompt
    assert session.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
    assert "Treat blank budgets as 0 (unbudgeted)?" in resp_upload.text
    assert "Treat blank budgets as 0 (unbudgeted)" in (resp_upload.chips or [])

    # Step 2: Confirm treat blank budgets as zero
    resp_confirm = handle_message(session, "Treat blank budgets as 0 (unbudgeted)")
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Here's how I read your file:" in resp_confirm.text
    assert "Header row:** Row 2" in resp_confirm.text
    assert "Read accounting dashes ('-') as 0" in resp_confirm.text
    assert "Treated blank budgets as 0" in resp_confirm.text
    assert "Looks right" in (resp_confirm.chips or [])

    # Step 3: Maya confirms layout -> proceeds to period
    resp_period = handle_message(session, "Looks right")
    assert resp_period.phase == Phase.AWAITING_PERIOD


def test_fixture_e_wide_monthly_baseline() -> None:
    """Fixture e: Wide monthly layout ('Jul-26 Budget', 'Jul-26 Actual', etc.).
    
    Phase 2 outcome: Detects multi-period columns and prompts for period selection.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_e_wide_monthly.xlsx"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert session.phase == Phase.AWAITING_PERIOD_CHOICE
    assert "Found data for multiple periods in your file" in resp_upload.text
    assert "Q3" in (resp_upload.chips or [])
    
    resp_q3 = handle_message(session, "Q3")
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Analyzed period:** Q3" in resp_q3.text
    assert "Looks right" in (resp_q3.chips or [])


def test_fixture_f_budget_actuals_separate_baseline() -> None:
    """Fixture f: Budget and actuals as two separate files.
    
    Phase 1 baseline measurement: Plain language missing columns error.
    """
    session = Session()
    path_bgt = FIXTURES_DIR / "fixture_f_budget_separate.csv"
    resp_upload = handle_upload(session, path_bgt.read_bytes(), path_bgt.name)
    assert session.phase == Phase.AWAITING_FILE
    assert "Could not find a header row with Line Item, Budget, and Actual columns" in resp_upload.text


def test_fixture_g_cover_page_active_intake() -> None:
    """Fixture g: Active sheet is a cover page; second sheet ('BvA') has data.
    
    Phase 1 outcome: NO DEAD END.
    SheetRanker identifies 'BvA' as the primary data worksheet over 'Cover Page',
    and loads it automatically with an explanatory visible transformation note.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_g_cover_page_active.xlsx"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Here's how I read your file:" in resp_upload.text
    assert "Worksheet:** BvA" in resp_upload.text
    assert "Selected worksheet 'BvA'" in resp_upload.text
    assert "over 'Cover Page'" in resp_upload.text
    assert "Looks right" in (resp_upload.chips or [])

    # Confirm and complete flow
    handle_message(session, "Looks right")
    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")
    assert "Analysis Complete" in resp_curr.text
    assert session.phase == Phase.EXPLORING
    assert session.result is not None


def test_fixture_h_120_line_gl_unclassified_friction() -> None:
    """Fixture h: 120-line GL export with account numbers and no Type column.

    Phase 2 outcome: Inferred GL range rules classify 120 lines in 1 click!
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_h_120_line_gl.csv"
    resp_upload = handle_upload(session, path.read_bytes(), path.name)
    assert resp_upload.phase == Phase.AWAITING_PERIOD

    handle_message(session, "Q3 2026")
    handle_message(session, "$10,000 or 5%")
    resp_curr = handle_message(session, "USD")

    assert session.phase == Phase.RESOLVE_UNCLASSIFIED
    assert "Found account numbers. Proposed classification rules:" in resp_curr.text
    assert "Accounts 4000–4999: Revenue (40 lines)" in resp_curr.text
    assert "Accounts 5000–8999: Expense (80 lines)" in resp_curr.text
    assert "Looks right" in (resp_curr.chips or [])

    # Confirm rules in 1 click -> all 120 lines classified!
    resp_confirm = handle_message(session, "Looks right")
    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert "Analysis Complete" in resp_confirm.text
    assert len(session.type_map) == 120


def test_fixture_i_pasted_tsv_intake() -> None:
    """Fixture i: Tab-separated block pasted directly into chat.
    
    Phase 1 outcome: NO DEAD END.
    handle_message in Phase.AWAITING_FILE parses the pasted TSV,
    extracts the data, maps headers, and presents the intake summary.
    """
    session = Session()
    path = FIXTURES_DIR / "fixture_i_pasted_tsv.txt"
    pasted_text = path.read_text(encoding="utf-8")
    
    response = handle_message(session, pasted_text)
    
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert "Here's how I read your file:" in response.text
    assert "Read data from pasted tab-separated text" in response.text
    assert "Columns mapped:" in response.text
    assert "Looks right" in (response.chips or [])

    # Confirm proceeds to period
    resp_confirm = handle_message(session, "Looks right")
    assert resp_confirm.phase == Phase.AWAITING_PERIOD
