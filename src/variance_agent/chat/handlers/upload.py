"""Reading an uploaded file: one file, a budget/actuals pair, an LTM pair or a covenant schedule.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from variance_agent.comparison import basis_noun, zero_comparison_phrase
from variance_agent.models import ComparisonBasis
from variance_agent.intake import (
    CanonicalRole,
    IntakeResult,
    format_intake_summary,
    plain_analysis_error,
    read_input_assisted,
)
from ..responses import Response, safe_inline
from ..session import Phase, Session
from ..views import CONFIRM_QUESTION, intake_view, with_lead
from ._common import _ask_period, _choosable, _sheet_chip


HIDDEN_ROWS_CHIPS = ("Count the hidden rows", "Leave the hidden rows out")


def _comparison_chips(choices: list[ComparisonBasis]) -> list[str]:
    """Offer one 'Compare to ...' chip per basis that resolves the stop, in header order."""
    return [f"Compare to {basis_noun(b)}" for b in choices]


def _looks_like_pasted_table(text: str) -> bool:
    return "\t" in text and ("\n" in text or "\r" in text)


def _blank_wording(basis: ComparisonBasis) -> str:
    return "blank budgets" if basis is ComparisonBasis.BUDGET else f"blank {basis_noun(basis)} values"


def handle_upload(
    session: Session, file_bytes: bytes, filename: str, sheet: str | None = None,
    *, first_visit: bool | None = None,
) -> Response:
    """Process a file upload with assisted reading and plain language."""
    if session.awaiting_ltm_annual and session.source_bytes is not None and session.source_name is not None:
        return _load_ltm_annual(session, file_bytes, filename)
    if session.pending_half is not None:
        return _load_other_half(session, file_bytes, filename, first_visit)
    if session.covenant_step is not None and session.source_bytes is not None:
        return _load_covenant_file(session, file_bytes, filename)
    return _load_file(session, file_bytes, filename, sheet, first_visit)


_COVENANT_ASK = ("Upload your metrics file: a JSON file declaring each ratio's terms (see docs/financial-rules.md, "
                 "Derived metrics). Then I'll ask for the covenant schedule.")


def _handle_covenant_headroom(session: Session) -> Response:
    if session.source_bytes is None or not str(session.source_name or "").lower().endswith((".htm", ".html")):
        return Response(text="Covenant headroom is computed from a filing. Upload the 10-K's or 10-Q's .htm document "
                             "from EDGAR first.", phase=session.phase)
    session.covenant_step, session.covenant_metrics = "metrics", None
    return Response(text=_COVENANT_ASK, phase=session.phase, ask_upload=True)


def _load_covenant_file(session: Session, file_bytes: bytes, filename: str) -> Response:
    """The metrics file, then the covenant schedule: ratios from the filing against each limit (PLAN.md R17, R13)."""
    assert session.source_bytes is not None and session.source_name is not None
    if session.covenant_step == "metrics":
        from ...metrics import load_metrics
        try:
            load_metrics(file_bytes)
        except ValueError as exc:
            return Response(text=str(exc), phase=session.phase, level="error", ask_upload=True)
        session.covenant_metrics, session.covenant_step = file_bytes, "schedule"
        return Response(text="Now upload the covenant schedule: each metric's name, its Limit, and its Limit Kind (Max "
                             "or Min), with a Buffer where you have one.", phase=session.phase, ask_upload=True)
    from ...metrics import compare_metrics
    assert session.covenant_metrics is not None
    session.covenant_step = None
    try:
        intake_res = compare_metrics(session.covenant_metrics, session.source_bytes, session.source_name, file_bytes,
                                     filename, compare_to=ComparisonBasis.LIMIT)
    except ValueError as exc:
        return Response(text=str(exc), phase=session.phase, level="error")
    if intake_res.has_fatal_errors:
        return Response(text=intake_res.fatal_error_message or "I couldn't compare these metrics. Upload the covenant "
                        "schedule again, or type `new` to start over.", phase=session.phase,
                        level="error")
    return _intake_response(session, intake_res, session.source_name)


def _half_request(session: Session, file_bytes: bytes, filename: str) -> Response | None:
    """A file holding only a comparison column, or only actuals: ask for the other file (PLAN.md R12, F4)."""
    from ...join import half_role
    found = half_role(file_bytes, filename)
    if found is None:
        return None
    missing, key = found
    session.pending_half = (file_bytes, filename, missing.value)
    return Response(text=f"'{safe_inline(filename)}' {_half_wording(missing, key)}", phase=session.phase,
                    ask_upload=True)


def _half_wording(missing: CanonicalRole, key: str) -> str:
    """What one half of a pair holds and what to upload next, after its file name."""
    if missing is CanonicalRole.ACTUAL:
        return f"has Budget figures but no Actual column. Upload the file with the actuals, and I'll join the two by {key}."
    return (f"has Actual figures but no Budget column. Upload the file with the budget, forecast or prior period, "
            f"and I'll join the two by {key}.")


def _load_other_half(session: Session, file_bytes: bytes, filename: str, first_visit: bool | None) -> Response:
    """The second file of a pair: join the two, with the actuals file's rows (PLAN.md R12)."""
    from ...join import half_role, join_files
    assert session.pending_half is not None
    session.pending_unbudgeted = None  # a new file answers the offer to read missing lines as 0 (X36)
    held, held_name, missing = session.pending_half
    found = half_role(file_bytes, filename)
    if found is None:
        # A whole file, not the other half: read it on its own; a refused one keeps the pair waiting (X21).
        session.pending_half = None
        response = _load_file(session, file_bytes, filename, None, first_visit)
        if response.level == "error":
            session.pending_half = (held, held_name, missing)
            return response
        return replace(response, text=f"'{safe_inline(filename)}' has both Budget and Actual, so I read it on its own "
                                      f"and set '{safe_inline(held_name)}' aside.\n\n{response.text}")
    if found[0].value == missing:
        # Another file holding the same half replaces the one held (X21).
        session.pending_half = (file_bytes, filename, missing)
        wording = _half_wording(found[0], found[1])
        text = (f"That's '{safe_inline(held_name)}' again. It {wording}" if file_bytes == held
                else f"'{safe_inline(filename)}' replaces '{safe_inline(held_name)}': it {wording}")
        return Response(text=text, phase=session.phase, ask_upload=True)
    session.pending_half = None
    if missing == CanonicalRole.ACTUAL.value:
        actual, actual_name, comparison, comparison_name = file_bytes, filename, held, held_name
    else:
        actual, actual_name, comparison, comparison_name = held, held_name, file_bytes, filename
    intake_res = join_files(actual, actual_name, comparison, comparison_name, treat_blank_budgets_as_zero=False)
    if intake_res.has_fatal_errors:
        session.pending_half = (held, held_name, missing)
        offer = _unbudgeted_offer(session, intake_res, actual, actual_name, comparison, comparison_name)
        if offer is not None:
            return offer
        return Response(text=intake_res.fatal_error_message or _JOIN_FAILED, phase=session.phase, level="error",
                        ask_upload=True)
    return _joined(session, intake_res, actual, actual_name, first_visit)


_JOIN_FAILED = ("I couldn't join these two files. Upload them again, or upload one file that holds both the "
                "comparison and Actual.")


def _joined(session: Session, intake_res: IntakeResult, actual: bytes, actual_name: str,
            first_visit: bool | None) -> Response:
    session.reset()
    session.source_bytes, session.source_name = actual, actual_name
    session.source_suffix = Path(actual_name).suffix.lower()
    return _with_first_upload_intro(session, _intake_response(session, intake_res, actual_name),
                                    intake_res.comparison_basis, first_visit)


def _unbudgeted_offer(session: Session, refused: IntakeResult, actual: bytes, actual_name: str, comparison: bytes,
                      comparison_name: str) -> Response | None:
    """A join refused only for lines the comparison file lacks: offer to read them as 0, as a blank budget is (X36)."""
    from ...join import JOIN_FIX, join_files
    message = refused.fatal_error_message or ""
    if not (message.startswith(f"In '{actual_name}' but not in '{comparison_name}': ") and message.endswith(JOIN_FIX)):
        return None
    joined = join_files(actual, actual_name, comparison, comparison_name, treat_blank_budgets_as_zero=False,
                        unbudgeted_as_zero=True)
    if joined.has_fatal_errors:
        return None  # lines missing the other way too, or a basis where 0 would invent a figure
    basis = joined.comparison_basis or ComparisonBasis.BUDGET
    chip = f"Treat them as 0 ({zero_comparison_phrase(basis)})"
    session.pending_unbudgeted = (actual, actual_name, comparison, comparison_name, chip)
    return Response(
        text=f"{message.removesuffix(JOIN_FIX)}Choose **{chip}** to read them with a {basis_noun(basis)} of 0, "
             "or upload a corrected file.",
        chips=[chip, "Upload a different file"], phase=session.phase, level="error", ask_upload=True)


def _join_unbudgeted(session: Session, first_visit: bool | None) -> Response:
    """The analyst chose to read the lines the comparison file lacks as 0 (X36)."""
    from ...join import join_files
    assert session.pending_unbudgeted is not None
    actual, actual_name, comparison, comparison_name, _ = session.pending_unbudgeted
    session.pending_unbudgeted = None
    intake_res = join_files(actual, actual_name, comparison, comparison_name, treat_blank_budgets_as_zero=False,
                            unbudgeted_as_zero=True)
    if intake_res.has_fatal_errors:
        return Response(text=intake_res.fatal_error_message or _JOIN_FAILED, phase=session.phase, level="error",
                        ask_upload=True)
    return _joined(session, intake_res, actual, actual_name, first_visit)


_LTM_ASK = ("Upload the 10-K whose fiscal year this 10-Q continues. I'll build LTM as that fiscal year plus this year "
            "to date less last year to date, line by line by XBRL concept, and compare it with the fiscal year.")


def _offers_ltm(session: Session, intake_res: IntakeResult) -> bool:
    """A 10-Q's income statement read from Inline XBRL (a duration shorter than a year), not yet built into LTM."""
    if intake_res.source_kind != "ixbrl" or intake_res.statement_kind or intake_res.ltm is not None or session.ltm_annual:
        return False
    for line in intake_res.xbrl_lines:
        for column in line.get("columns", []):  # type: ignore[attr-defined]
            period = column.get("period") if isinstance(column, dict) else None
            if isinstance(period, list) and len(period) == 3 and period[0] == "duration":
                from datetime import date
                days = (date.fromisoformat(str(period[2])) - date.fromisoformat(str(period[1]))).days
                return days < 330  # under a fiscal year, 52/53-week years included
    return False


def _handle_build_ltm(session: Session) -> Response:
    if session.source_bytes is None or not str(session.source_name or "").lower().endswith((".htm", ".html")):
        return Response(text="LTM is built from a 10-Q and a 10-K filed on EDGAR. Upload the 10-Q's .htm document first.",
                        phase=session.phase)
    session.awaiting_ltm_annual = True
    return Response(text=_LTM_ASK, phase=session.phase, ask_upload=True)


def _load_ltm_annual(session: Session, file_bytes: bytes, filename: str) -> Response:
    """The second upload of an LTM build: the 10-K. The 10-Q stays the session's file (PLAN.md R10)."""
    from ...ltm import build_ltm
    assert session.source_bytes is not None and session.source_name is not None
    session.awaiting_ltm_annual = False
    intake_res = build_ltm(session.source_bytes, session.source_name, file_bytes, filename)
    if intake_res.has_fatal_errors:
        return Response(text=intake_res.fatal_error_message or "I couldn't build LTM from these two filings.",
                        chips=["Build LTM"], phase=session.phase, level="error", ask_upload=False)
    session.ltm_annual = (file_bytes, filename)
    return _intake_response(session, intake_res, session.source_name)


def _load_file(
    session: Session, file_bytes: bytes, filename: str, sheet: str | None,
    first_visit: bool | None, *, pasted: bool = False,
) -> Response:
    """Read a file first, and replace the session's file only once it was read.

    A successful read starts a fresh session for that file: everything the user said about
    an earlier file (period, thresholds, currency, type choices, ...) is dropped, and only
    deployment policy survives. A failed read leaves the earlier file, analysis and phase as
    they were, except when the file stopped on a question its chips answer (which comparison
    to use, which sheet to read); that file becomes the session's file so the answer has
    something to re-read.
    """
    suffix = Path(filename).suffix.lower()
    # A comparison choice belongs to the file it was made for; a replacement file is
    # detected afresh. A choice made before the first upload still applies to it.
    compare_to = None if session.source_bytes is not None else session.compare_to
    if session.earnings_requested and session.source_bytes is None:
        from ..earnings import review_upload
        return review_upload(session, file_bytes, filename, None, sheet)
    if compare_to in {ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE, ComparisonBasis.GUIDANCE}:
        from ..earnings import review_upload
        return review_upload(session, file_bytes, filename, compare_to, sheet)
    intake_res = read_input_assisted(
        file_bytes,
        suffix,
        filename=filename,
        sheet=sheet,
        treat_blank_budgets_as_zero=False,
        compare_to=compare_to,
    )
    if (intake_res.has_fatal_errors or not intake_res.rows) and compare_to is None and intake_res.opt_in_hint is not None:
        # A Limit, Benchmark or Target column: read the file against it, as the reader meant (PLAN.md R13-R15).
        header, basis = intake_res.opt_in_hint
        again = read_input_assisted(file_bytes, suffix, filename=filename, sheet=sheet,
                                    treat_blank_budgets_as_zero=False, compare_to=basis)
        if not again.has_fatal_errors and again.rows:
            again.visible_transformations.insert(0, f"Read the '{header}' column as each row's {basis.value}, with each "
                                                    "row's own declarations beside it")
            intake_res, compare_to = again, basis
    failed = intake_res.has_fatal_errors or not intake_res.rows
    awaiting_answer = (bool(intake_res.comparison_choices) or len(intake_res.available_sheets) > 1
                       or intake_res.needs_hidden_rows_choice)
    if failed and not awaiting_answer:
        from ..earnings import offer_review
        proposal = offer_review(session, file_bytes, filename)
        if proposal is not None:
            return proposal
        half = _half_request(session, file_bytes, filename)
        if half is not None:
            return half
        return _fatal_upload_response(session, intake_res, filename, pasted=pasted)

    session.reset()
    session.compare_to = compare_to
    session.source_bytes = file_bytes
    session.source_name = filename
    session.source_suffix = suffix
    if failed:
        return _fatal_upload_response(session, intake_res, filename, pasted=pasted)
    return _with_first_upload_intro(
        session, _intake_response(session, intake_res, filename), intake_res.comparison_basis, first_visit,
    )


def _fatal_upload_response(
    session: Session, intake_res: IntakeResult, filename: str, *, pasted: bool = False,
) -> Response:
    """Explain why a file could not be read, in the phase the session is still in."""
    technical = intake_res.fatal_error_message or (
        f"The uploaded file '{safe_inline(filename)}' contains no data rows. "
        f"Please upload a file with at least one row of {basis_noun(intake_res.comparison_basis)} and actual data."
    )
    session.last_technical_detail = technical
    chips = list(HIDDEN_ROWS_CHIPS) if intake_res.needs_hidden_rows_choice else []
    chips.extend(_comparison_chips(intake_res.comparison_choices))
    if intake_res.available_sheets and len(intake_res.available_sheets) > 1:
        for s in intake_res.available_sheets[:3]:
            chips.append(_sheet_chip(session, s))
    chips.extend(["Upload a different file", "Show technical details"])

    text = plain_analysis_error(technical)
    if pasted:
        text += "\n\nPaste a table with a header row (such as Line Item, Budget, Actual), or upload a file."
    return Response(text=text, chips=chips, phase=session.phase, level="error")


def _intake_summary_text(intake_res: IntakeResult) -> str:
    """`format_intake_summary` for the chat, with the question, and without its warning sign."""
    text = format_intake_summary(intake_res).replace("\n\u26a0\ufe0f **Items needing attention:**",
                                                      "\n**Items needing attention:**")
    return text + f"\n\n{CONFIRM_QUESTION}"


def _intake_confirmation(intake_res: IntakeResult, chips: list[str]) -> Response:
    """Ask the analyst to confirm how the file was read, as text and as a panel."""
    return Response(
        text=_intake_summary_text(intake_res),
        chips=chips,
        phase=Phase.AWAITING_INTAKE_CONFIRMATION,
        view=intake_view(intake_res),
    )


def _first_upload_intro(basis: ComparisonBasis) -> str:
    """A short welcome for a visitor's first file, worded for the file's comparison basis.

    Forecast and prior-period sessions never say budget, plan or target. What the tool can do
    lives in the Help reply, so the file summary and the next question come straight after.
    """
    noun = basis_noun(basis)
    if basis in {ComparisonBasis.LIMIT, ComparisonBasis.BENCHMARK, ComparisonBasis.TARGET}:
        outcome = {"limit": "whether each is a Breach, At limit, Near or Within",
                   "benchmark": "whether each is higher or lower than its benchmark",
                   "target": "whether each is over, under or on target"}[basis.value]
        return (f"Welcome to the Variance Analysis Agent. I compare each line's Actual against its {noun} and say "
                f"{outcome}. Type `help` for everything you can ask.\n\n")
    return (
        "Welcome to the Variance Analysis Agent. I compare each line's Actual against your "
        f"{noun}, flag the gaps big enough to matter, and say whether each one helped or hurt "
        "profit. Type `help` for everything you can ask.\n\n"
    )


def _with_first_upload_intro(
    session: Session, response: Response, basis: ComparisonBasis, first_visit: bool | None,
) -> Response:
    """Open a visitor's first successfully read file with what the chatbot is for.

    Hosted visitors share one session, so the page says whether its visitor has seen
    the intro (``first_visit``). Callers that don't say get it once per session.
    """
    if response.phase == Phase.AWAITING_FILE:
        return response
    show = not session.intro_shown if first_visit is None else first_visit
    session.intro_shown = True
    if not show:
        return response
    return with_lead(response, _first_upload_intro(basis))


def _intake_response(session: Session, intake_res: IntakeResult, filename: str) -> Response:
    """Continue the conversation from a fresh read of the uploaded file."""
    if intake_res.has_fatal_errors or not intake_res.rows:
        return _fatal_upload_response(session, intake_res, filename)

    # Check for blank budgets needing confirmation
    if intake_res.blank_budget_items:
        session.intake_result = intake_res
        session.available_sheets = intake_res.available_sheets
        session.worksheet = intake_res.sheet_name
        session.phase = Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
        count = len(intake_res.blank_budget_items)
        sample = intake_res.blank_budget_items[0]
        basis = intake_res.comparison_basis
        # The analysis needs a number, so a blank can only be read as 0: the one choice offered
        # (besides fixing the file) is to confirm that, and the summary then records it.
        blanks = _blank_wording(basis)
        treat = f"Treat {blanks} as 0 ({zero_comparison_phrase(basis)})"
        return Response(
            text=(
                f"Found **{count}** line item{'s' if count != 1 else ''} with {blanks} "
                f"(such as {safe_inline(sample)}).\n\n"
                f"Blank amounts cannot stay blank in the analysis, so they are read as 0.\n\n"
                f"{treat}?"
            ),
            chips=[treat, "Upload a different file"],
            phase=Phase.AWAITING_BLANK_BUDGET_CONFIRMATION,
        )

    # Check for multi-period columns
    if intake_res.detected_period_pairs and len(intake_res.detected_period_pairs) > 1 and session.period is None:
        session.intake_result = intake_res
        session.available_sheets = intake_res.available_sheets
        session.worksheet = intake_res.sheet_name
        session.detected_period_pairs = intake_res.detected_period_pairs
        session.phase = Phase.AWAITING_PERIOD_CHOICE
        period_chips = [p.period for p in intake_res.detected_period_pairs]
        return Response(
            text="Found data for multiple periods in your file.\n\nWhich period would you like to analyze?",
            chips=period_chips,
            phase=Phase.AWAITING_PERIOD_CHOICE,
        )

    session.parsed_rows = intake_res.rows
    session.worksheet = intake_res.sheet_name
    session.available_sheets = intake_res.available_sheets
    session.intake_result = intake_res
    session.skipped_items = set()

    if not intake_res.has_transformations:
        session.phase = Phase.AWAITING_PERIOD
        row_count = len(intake_res.rows)
        worksheet_note = ""
        if intake_res.sheet_name:
            worksheet_note = f" from worksheet '{safe_inline(intake_res.sheet_name)}'"
            if len(session.available_sheets) > 1:
                worksheet_note += f" ({len(session.available_sheets)} sheets available; switch with `sheet <name>`)"

        return _ask_period(session, f"Loaded '{safe_inline(filename)}' ({row_count} data "
                                    f"row{'s' if row_count != 1 else ''}){worksheet_note}.\n\n")

    session.phase = Phase.AWAITING_INTAKE_CONFIRMATION

    chips = ["Looks right", "Change something"]
    if intake_res.available_sheets and len(intake_res.available_sheets) > 1:
        other_sheets = [s for s in _choosable(session, intake_res.available_sheets)
                        if s != intake_res.sheet_name]
        if other_sheets:
            chips.insert(1, _sheet_chip(session, other_sheets[0]))
    if _offers_ltm(session, intake_res):
        chips.insert(1, "Build LTM")

    return _intake_confirmation(intake_res, chips)
