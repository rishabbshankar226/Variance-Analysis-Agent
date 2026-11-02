"""Worksheets, hidden rows and the comparison basis.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from variance_agent.comparison import basis_noun, comparison_heading
from variance_agent.models import ComparisonBasis
from variance_agent.parsing import get_workbook_sheets
from variance_agent.intake import plain_analysis_error, read_input_assisted
from ..intent import ParsedIntent
from ..responses import Response, safe_inline
from ..session import Phase, Session
from ..views import with_lead
from ._common import _MULTI_TABLE_SUFFIXES, _choosable, _is_pdf, _sheet_chip, _sheet_word
from .upload import _intake_confirmation, _intake_response
from .run import _run_analysis


# ---------------------------------------------------------------------------
# Comparison basis wording (Budget, Forecast or Prior Period)
# ---------------------------------------------------------------------------

_CHAT_BASES: dict[str, ComparisonBasis] = {
    "budget": ComparisonBasis.BUDGET,
    "forecast": ComparisonBasis.FORECAST,
    "prior year": ComparisonBasis.PRIOR_PERIOD,
    "last year": ComparisonBasis.PRIOR_PERIOD,
    "prior period": ComparisonBasis.PRIOR_PERIOD,
}


def _handle_list_sheets(session: Session) -> Response:
    """List the worksheets in an uploaded workbook, or the statements in a PDF."""
    if not session.source_bytes or not session.source_name:
        return Response(
            text="No file has been uploaded yet. Please upload an Excel workbook (.xlsx or .xlsm) "
                 "or a PDF filing first.",
            phase=session.phase,
            chips=["Help"],
        )

    suffix = (session.source_suffix or "").lower()
    if suffix not in _MULTI_TABLE_SUFFIXES:
        return Response(
            text=f"The uploaded file **'{safe_inline(session.source_name)}'** is a "
                 f"{suffix.upper().lstrip('.')} file, which contains a single dataset rather than multiple worksheets.",
            phase=session.phase,
            chips=["Summary", "Help"],
        )

    sheets = session.available_sheets
    if not sheets:
        sheets = get_workbook_sheets(session.source_bytes, suffix)
        session.available_sheets = list(sheets)

    word = _sheet_word(session)
    if not sheets:
        return Response(
            text=f"No readable {word}s found in '{safe_inline(session.source_name)}'.",
            phase=session.phase,
        )

    current = session.worksheet or sheets[0]
    sheet_list_md = []
    for idx, s in enumerate(sheets, start=1):
        is_active = (s == current)
        marker = " *(active)*" if is_active else ""
        sheet_list_md.append(f"{idx}. **{safe_inline(s)}**{marker}")

    text = (
        f"**{word.capitalize()}s in '{safe_inline(session.source_name)}' ({len(sheets)} total):**\n\n"
        + "\n".join(sheet_list_md)
        + f"\n\nTo switch {word}s, type `{_sheet_chip(session, '<name>').lower()}` (e.g., `"
        + _sheet_chip(session, safe_inline(sheets[1] if len(sheets) > 1 else sheets[0])).replace(
            "Statement ", "statement ", 1).replace("Sheet ", "sheet ", 1)
        + "`)."
    )

    other_sheets = [s for s in _choosable(session, sheets) if s != current]
    chips = [_sheet_chip(session, s) for s in other_sheets[:3]]
    if session.phase == Phase.EXPLORING:
        chips.append("Summary")

    return Response(text=text, chips=chips, phase=session.phase)


def _handle_switch_sheet(session: Session, intent: ParsedIntent) -> Response:
    """Switch the active worksheet (or PDF statement) and re-analyze or re-intake data."""
    if not session.source_bytes or not session.source_name:
        return Response(
            text="No file has been uploaded yet. Please upload an Excel workbook (.xlsx or .xlsm) "
                 "or a PDF filing first.",
            phase=session.phase,
        )

    suffix = (session.source_suffix or "").lower()
    if suffix not in _MULTI_TABLE_SUFFIXES:
        return Response(
            text=f"The uploaded file **'{safe_inline(session.source_name)}'** is a "
                 f"{suffix.upper().lstrip('.')} file, which does not have multiple worksheets.",
            phase=session.phase,
        )

    target_sheet = intent.captures.get("sheet", "").strip()
    if not target_sheet:
        return _handle_list_sheets(session)

    sheets = session.available_sheets
    if not sheets:
        sheets = get_workbook_sheets(session.source_bytes, suffix)
        session.available_sheets = list(sheets)

    matched_sheet: str | None = None
    for s in sheets:
        if s == target_sheet:
            matched_sheet = s
            break
    if matched_sheet is None:
        for s in sheets:
            if s.lower() == target_sheet.lower():
                matched_sheet = s
                break
    if matched_sheet is None and target_sheet.isdigit() and len(target_sheet) <= 6:
        # "sheet 2" is the second one in the numbered list, not a name that happens to contain a 2
        position = int(target_sheet)
        if 1 <= position <= len(sheets):
            matched_sheet = sheets[position - 1]
    if matched_sheet is None:
        candidates = [s for s in sheets if target_sheet.lower() in s.lower()]
        if len(candidates) == 1:
            matched_sheet = candidates[0]

    word = _sheet_word(session)
    if matched_sheet is None:
        available_str = ", ".join(f"'{safe_inline(s)}'" for s in sheets)
        return Response(
            text=f"{word.capitalize()} '{safe_inline(target_sheet)}' was not found in '{safe_inline(session.source_name)}'.\n\n"
                 f"Available {word}s: {available_str}.",
            chips=[_sheet_chip(session, s) for s in sheets[:3]],
            phase=session.phase,
            level="error",
        )

    if matched_sheet == session.worksheet and session.result is not None:
        return Response(
            text=f"{word.capitalize()} **'{safe_inline(matched_sheet)}'** is already active.",
            chips=["Summary", "Waterfall", "Material"],
            phase=session.phase,
        )

    intake_res = read_input_assisted(
        session.source_bytes,
        suffix,
        filename=session.source_name,
        sheet=matched_sheet,
        treat_blank_budgets_as_zero=False,
        compare_to=session.compare_to,
        hidden_rows=session.hidden_rows,
    )
    if intake_res.has_fatal_errors or not intake_res.rows:
        technical = intake_res.fatal_error_message or "No data rows found"
        session.last_technical_detail = technical
        plain_err = plain_analysis_error(technical)
        if _is_pdf(session):
            # The PDF messages already name the statement; offer the ones that can be read.
            chips = [_sheet_chip(session, s) for s in intake_res.available_sheets
                     if s != session.worksheet][:3]
            return Response(text=plain_err, chips=[*chips, "Show statements"],
                            phase=session.phase, level="error")
        chips = ["Show sheets"]
        if session.last_technical_detail:
            chips.append("Show technical details")
        return Response(
            text=f"Failed to load {word} '{safe_inline(matched_sheet)}': {plain_err}",
            chips=chips,
            phase=session.phase,
            level="error",
        )

    session.parsed_rows = intake_res.rows
    session.worksheet = intake_res.sheet_name or matched_sheet
    session.skipped_items = set()
    session.sheet = matched_sheet
    session.intake_result = intake_res
    if intake_res.available_sheets:
        session.available_sheets = intake_res.available_sheets

    session.last_table_items = []
    session.last_focused_item = None
    session.unclassified_queue = []
    session.pending_gl_rules = []
    if (
        session.phase in (Phase.EXPLORING, Phase.RESOLVE_UNCLASSIFIED)
        and session.period is not None
        and session.dollar_threshold is not None
        and session.percent_threshold is not None
    ):
        resp = _run_analysis(session)
        prefix = f"Switched to {word} **'{safe_inline(matched_sheet)}'** ({len(intake_res.rows)} rows).\n\n"
        return with_lead(resp, prefix)

    if session.phase == Phase.AWAITING_INTAKE_CONFIRMATION:
        chips = ["Looks right", "Change something"]
        if intake_res.available_sheets and len(intake_res.available_sheets) > 1:
            other_sheets = [s for s in _choosable(session, intake_res.available_sheets)
                            if s != matched_sheet]
            if other_sheets:
                chips.insert(1, _sheet_chip(session, other_sheets[0]))
        return with_lead(_intake_confirmation(intake_res, chips),
                         f"Switched to {word} **'{safe_inline(matched_sheet)}'**.\n\n")

    row_count = len(intake_res.rows)
    return Response(
        text=f"Switched to {word} **'{safe_inline(matched_sheet)}'** ({row_count} data row{'s' if row_count != 1 else ''}).\n\n"
             f"Current reporting period: **{safe_inline(session.period or 'Not set')}**.",
        phase=session.phase,
    )


def _handle_hidden_rows(session: Session, intent: ParsedIntent) -> Response:
    """Count or leave out the rows hidden in Excel, re-read the file and confirm it again (R3)."""
    choice = "include" if intent.captures.get("count") else "exclude"
    if session.source_bytes is None or session.source_suffix is None:
        return Response(text="Upload a workbook first; I'll ask about hidden rows if it has any.",
                        phase=session.phase)
    filename = session.source_name or "input"
    if session.earnings_requested:
        from ..earnings import review_upload
        return review_upload(session, session.source_bytes, filename, session.compare_to, session.sheet, hidden_rows=choice)
    session.hidden_rows = choice
    intake_res = read_input_assisted(
        session.source_bytes,
        session.source_suffix,
        filename=filename,
        sheet=session.worksheet,
        treat_blank_budgets_as_zero=False,
        compare_to=session.compare_to,
        hidden_rows=choice,
    )
    return _intake_response(session, intake_res, filename)


def _handle_set_comparison(session: Session, intent: ParsedIntent) -> Response:
    """Choose what Actual is compared against, re-read the file and re-run the analysis."""
    basis = _CHAT_BASES[" ".join(intent.captures.get("basis", "").lower().split())]
    noun = basis_noun(basis)
    if session.source_bytes is None or session.source_suffix is None:
        session.compare_to = basis
        return Response(
            text=f"Got it. I will compare Actual against the {noun} once you upload a file.",
            phase=session.phase,
        )

    filename = session.source_name or "input"
    intake_res = read_input_assisted(
        session.source_bytes,
        session.source_suffix,
        filename=filename,
        sheet=session.worksheet,
        treat_blank_budgets_as_zero=False,
        selected_period=session.period if session.detected_period_pairs else None,
        compare_to=basis,
        hidden_rows=session.hidden_rows,
    )
    if intake_res.has_fatal_errors or not intake_res.rows:
        technical = intake_res.fatal_error_message or "No data rows found"
        session.last_technical_detail = technical
        return Response(
            text=f"Could not compare against the {noun}: {plain_analysis_error(technical)}",
            chips=["Show technical details", "Upload a different file"],
            phase=session.phase,
            level="error",
        )

    session.compare_to = basis
    if not (
        session.phase == Phase.EXPLORING
        and session.period is not None
        and session.dollar_threshold is not None
        and session.percent_threshold is not None
    ):
        return _intake_response(session, intake_res, filename)

    session.parsed_rows = intake_res.rows
    session.worksheet = intake_res.sheet_name
    session.intake_result = intake_res
    if intake_res.available_sheets:
        session.available_sheets = intake_res.available_sheets
    resp = _run_analysis(session)
    heading = safe_inline(comparison_heading(intake_res.comparison_basis, intake_res.comparison_label))
    return with_lead(resp, f"Now comparing Actual against **{heading}**.\n\n")
