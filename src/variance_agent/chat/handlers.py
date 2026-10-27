"""Deterministic handler functions for each chatbot intent.

Each handler receives the Session (which holds the AnalysisResult) and
any regex captures from the intent parser.  All financial values come
from the deterministic engine; handlers only perform lookups and
formatting.
"""

from __future__ import annotations

import csv
import difflib
import io
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal, Inexact, InvalidOperation
from pathlib import Path

from variance_agent.audience import AudienceConfig, is_audience_result
from variance_agent.measures import currency_row, measure_kind
from variance_agent.models import MeasureKind
from variance_agent.parsing import normalize_row, is_missing
from variance_agent.analysis import analyze_rows
from variance_agent.audit import build_audit_record, serialize_audit_json, sha256_bytes
from variance_agent.comparison import (
    basis_noun,
    basis_for_header,
    comparison_heading,
    display_outcome,
    extended_heading,
    zero_comparison_phrase,
)
from variance_agent.measures import format_measure
from variance_agent.currencies import CURRENCY_SYMBOLS, validate_currency
from variance_agent.limits import display_text
from variance_agent.models import AnalysisConfig, AnalysisResult, AnalyzedRow, ComparisonBasis, LineType, Status
from variance_agent.numeric import financial_context, ratio
from variance_agent.output import write_text_outputs
from variance_agent.parsing import (
    get_workbook_sheets,
    parse_decimal,
)
from variance_agent.intake import (
    IntakeResult,
    apply_classification_rules,
    audit_transformations,
    format_intake_summary,
    infer_gl_range_rules,
    plain_analysis_error,
    read_input_assisted,
)
from variance_agent.mapping import (
    LayoutMapping,
    compute_layout_fingerprint,
    save_mapping,
)
from variance_agent.report import render_markdown
from variance_agent.xlsx import render_xlsx

from . import knowledge
from .intent import (
    KNOWLEDGE_INTENTS,
    MAX_ROUTING_CHARS,
    ParsedIntent,
    find_line_item,
    normalize_for_routing,
    parse_intent,
)
from .responses import (
    Response,
    format_money,
    format_pct,
    format_threshold_amount,
    format_threshold_pct,
    report_places,
    row_to_table_dict,
    safe_inline,
    status_label,
)
from .session import Phase, Session
from .views import CONFIRM_QUESTION, figure, figures_view, intake_view, pair, with_lead


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


def _is_budget(cfg: AnalysisConfig) -> bool:
    return cfg.comparison_basis is ComparisonBasis.BUDGET


def _noun(cfg: AnalysisConfig) -> str:
    """Lower-case name of the comparison, as in 'above budget' or 'above forecast'."""
    return basis_noun(cfg.comparison_basis)


def _heading(cfg: AnalysisConfig) -> str:
    """Title-case name of the comparison: 'Budget', 'Forecast' or 'Prior Period (FY2024)'."""
    return safe_inline(comparison_heading(cfg.comparison_basis, cfg.comparison_label))


def _plain_heading(cfg: AnalysisConfig) -> str:
    """`_heading` for a view, which the page sets as text: the label is not Markdown-escaped."""
    return comparison_heading(cfg.comparison_basis, cfg.comparison_label)


def _tone(value: Decimal) -> str:
    """The tone of a signed impact on profit, for a view."""
    return "favorable" if value > 0 else "unfavorable" if value < 0 else "neutral"


def _planned(cfg: AnalysisConfig) -> str:
    """Label for a comparison amount: 'Budgeted Revenue', 'Forecast Revenue'."""
    return "Budgeted" if _is_budget(cfg) else _heading(cfg)


def _action_plan(cfg: AnalysisConfig) -> str:
    """'the action plan' on Budget runs; elsewhere 'plan' would read as the comparison."""
    return "the action plan" if _is_budget(cfg) else "the response"


@dataclass(frozen=True)
class _UnbudgetedWording:
    heading: str
    empty_state: str
    intro: str  # '{zero}' is the zero amount in the report money format
    note: str
    revenue_heading: str
    revenue_intro: str  # '{zero}' as above


_UNBUDGETED_WORDING: dict[ComparisonBasis, _UnbudgetedWording] = {
    ComparisonBasis.BUDGET: _UnbudgetedWording(
        heading="Unbudgeted Spending",
        empty_state="All accounts with actual activity had an approved baseline budget.",
        intro="These line items had zero approved budget ({zero}) but incurred realized expenditures:",
        note="These lines had spending with no budget allocated to them.",
        revenue_heading="Unbudgeted revenue",
        revenue_intro="earned with a zero plan ({zero}); favorable, but confirm it belongs in this period:",
    ),
    ComparisonBasis.FORECAST: _UnbudgetedWording(
        heading="Spending Not in Forecast",
        empty_state="All accounts with actual activity had a forecast amount.",
        intro="These line items had a zero forecast ({zero}) but incurred realized expenditures:",
        note="These lines had spending the latest forecast did not include.",
        revenue_heading="Revenue not in forecast",
        revenue_intro="earned with a zero forecast ({zero}); favorable, but confirm it belongs in this period:",
    ),
    ComparisonBasis.PRIOR_PERIOD: _UnbudgetedWording(
        heading="New Spending This Period",
        empty_state="All accounts with actual activity also had activity in the prior period.",
        intro="These line items had zero activity ({zero}) in the prior period but incurred realized expenditures:",
        note="These lines had spending with none in the prior period; the file does not say whether it is one-off or recurring.",
        revenue_heading="New revenue this period",
        revenue_intro="earned with no prior-period activity ({zero}); favorable, but confirm it belongs in this period:",
    ),
}


HIDDEN_ROWS_CHIPS = ("Count the hidden rows", "Leave the hidden rows out")


def _comparison_chips(choices: list[ComparisonBasis]) -> list[str]:
    """Offer one 'Compare to ...' chip per basis that resolves the stop, in header order."""
    return [f"Compare to {basis_noun(b)}" for b in choices]


# ---------------------------------------------------------------------------
# Phase-based message routing
# ---------------------------------------------------------------------------


def handle_message(session: Session, text: str, *, first_visit: bool | None = None) -> Response:
    """Top-level router: dispatch based on conversation phase and domain intents.

    ``first_visit`` is the page saying whether its visitor has seen the intro yet;
    see ``_with_first_upload_intro``.
    """
    text = text.strip()
    if not text:
        return Response(text="Please type a message or upload a file.")

    # A table pasted from a spreadsheet is thousands of characters; it is data, not a command,
    # so it is read before the message-length cap that protects intent parsing.
    if session.phase == Phase.AWAITING_FILE and _looks_like_pasted_table(text):
        return _load_file(
            session, text.encode("utf-8"), "pasted_data.tsv", None, first_visit, pasted=True,
        )

    intent = parse_intent(text)
    if intent.intent_id == "too_long":
        return Response(
            text=f"That message is too long for me to read as a question (limit {MAX_ROUTING_CHARS} "
                 "characters). Ask a shorter question. To load data, paste a table before any file is "
                 "loaded, or type `new` and use the drop zone.",
            phase=session.phase,
        )
    routing_key = normalize_for_routing(text).lower()
    if intent.intent_id == "reset":
        return _handle_reset(session)
    if intent.intent_id == "greeting":
        return _handle_greeting(session)
    if intent.intent_id == "gratitude":
        return _handle_gratitude(session)
    if intent.intent_id == "identity":
        return _handle_identity(session)
    if intent.intent_id == "help":
        return _handle_help(session)
    if intent.intent_id == "earnings_review":
        from .earnings import request_review
        return request_review(session)
    if intent.intent_id in {"earnings_consensus", "earnings_margins", "earnings_guidance"}:
        from .earnings import handle_question
        return handle_question(session, intent.intent_id)
    if intent.intent_id in KNOWLEDGE_INTENTS:
        return _handle_knowledge(session, intent.intent_id)
    if intent.intent_id == "list_sheets":
        return _handle_list_sheets(session)
    if intent.intent_id == "switch_sheet":
        return _handle_switch_sheet(session, intent)
    if intent.intent_id == "set_hidden_rows":
        return _handle_hidden_rows(session, intent)
    if intent.intent_id == "set_comparison":
        if intent.captures.get("basis") in {"consensus", "estimate", "guidance"}:
            from .earnings import explicit_comparison
            return explicit_comparison(session, ComparisonBasis(intent.captures["basis"]))
        if session.earnings_mode:
            from .earnings import handle_review_choice
            return handle_review_choice(session, text)
        return _handle_set_comparison(session, intent)

    if routing_key in ("show technical details", "technical details"):
        detail = session.last_technical_detail or "No technical details recorded for the current step."
        return Response(
            text=f"**Technical Details:**\n```\n{detail}\n```",
            chips=["Upload a different file", "Help"],
            phase=session.phase,
        )

    if routing_key in _UPLOAD_ANOTHER_FILE:
        # The page shows its drop zone for a reply in the awaiting_file phase. The session itself
        # is left alone: the new file replaces it only once it has been read successfully.
        return Response(
            text="Choose the new file in the drop zone below. It replaces the current one once it "
                 "has been read successfully; until then you can keep working with the current file.",
            chips=["Help"],
            phase=Phase.AWAITING_FILE,
        )

    if session.phase in {Phase.AWAITING_EARNINGS_REVIEW, Phase.AWAITING_COMPARISON_CHOICE}:
        from .earnings import handle_review_choice
        return handle_review_choice(session, text)
    if session.phase == Phase.AWAITING_FILE:
        return Response(
            text="Please upload a file using the drop zone above, or paste a table copied from a spreadsheet.",
            phase=session.phase,
        )

    if session.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION:
        return _handle_blank_budget_confirmation(session, text)

    if session.phase == Phase.AWAITING_PERIOD_CHOICE:
        return _handle_period_choice(session, text)

    if session.phase == Phase.AWAITING_INTAKE_CONFIRMATION:
        return _handle_intake_confirmation(session, text)

    if session.phase == Phase.AWAITING_PERIOD:
        return _handle_period(session, text)

    if session.phase == Phase.AWAITING_THRESHOLDS:
        return _handle_thresholds(session, text)

    if session.phase == Phase.AWAITING_MEASURE_OPTIONS:
        return _handle_measure_option(session, text)

    if session.phase == Phase.AWAITING_CURRENCY:
        return _handle_currency(session, text)

    if session.phase == Phase.RESOLVE_UNCLASSIFIED:
        return _handle_classify(session, text)

    # Phase.EXPLORING
    return _handle_exploring(session, text)


_UPLOAD_ANOTHER_FILE = frozenset({
    "upload a different file", "upload different file", "upload another file", "upload a new file",
})


def _looks_like_pasted_table(text: str) -> bool:
    return "\t" in text and ("\n" in text or "\r" in text)


_PERIOD_HINT = re.compile(
    r"\b(q[1-4]|fy\s*\d{2,4}|\d{4}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
)
_QUESTION_OPENERS = re.compile(
    r"^(?:can|could|may|might|would|should|will|what|why|how|is|are|do|does|did|please|i|we)\b",
)


def _looks_like_typed_period(lower: str) -> bool:
    """A short label such as 'Q3 2026', not a question that happens to contain 'may' or 'sep'."""
    return (
        len(lower) <= 40
        and "?" not in lower
        and _QUESTION_OPENERS.match(lower) is None
        and _PERIOD_HINT.search(lower) is not None
    )


def _handle_intake_confirmation(session: Session, text: str) -> Response:
    """Handle confirmation of the 'Here's how I read your file' summary."""
    lower = normalize_for_routing(text).lower()
    if lower in ("looks right", "yes", "confirm", "looks good", "correct", "proceed", "looks_right", "1"):
        if session.period is not None:
            if session.dollar_threshold is not None and session.percent_threshold is not None:
                return _run_analysis(session)
            session.phase = Phase.AWAITING_THRESHOLDS
            return Response(
                text=f"Period set to: **{safe_inline(session.period)}**\n\n"
                     "Now set the materiality thresholds. Enter a dollar amount and a percentage, "
                     "for example: `$10,000 or 5%`\n\n"
                     "Or choose a preset below:",
                chips=["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%", "$50,000 or 15%"],
                phase=Phase.AWAITING_THRESHOLDS,
            )
        session.phase = Phase.AWAITING_PERIOD
        return Response(
            text="What reporting period does this analysis cover? (e.g., Q3 2026, October 2026, FY2026)",
            phase=Phase.AWAITING_PERIOD,
        )

    if lower in ("change something", "no", "edit", "change", "2"):
        chips = []
        if session.available_sheets and len(session.available_sheets) > 1:
            for s in _choosable(session, session.available_sheets)[:4]:
                chips.append(_sheet_chip(session, s))
        chips.append("Upload a different file")
        return Response(
            text=f"What would you like to change? You can choose a different {_sheet_word(session)} "
                 "or upload a different file.",
            chips=chips,
            phase=Phase.AWAITING_INTAKE_CONFIRMATION,
        )

    # Check for direct sheet switch requests
    if lower.startswith(("sheet ", "statement ")) or (
            session.available_sheets and text in session.available_sheets):
        sheet_target = text.split(" ", 1)[1] if lower.startswith(("sheet ", "statement ")) else text
        return _handle_switch_sheet(session, ParsedIntent("switch_sheet", captures={"sheet": sheet_target}))

    # The user may type the period instead of clicking 'Looks right'.
    if not lower.startswith("upload") and len(text.strip()) > 1:
        if session.detected_period_pairs:
            # The columns were read for one chosen period, so a typed period must be another one
            # found in the file; anything else would disagree with the data on screen.
            wanted = normalize_for_routing(_clean_period_input(text)).lower()
            if any(normalize_for_routing(p.period).lower() == wanted for p in session.detected_period_pairs):
                return _handle_period_choice(session, text)
        elif _looks_like_typed_period(lower):
            session.period = text.strip()
            session.phase = Phase.AWAITING_THRESHOLDS
            return Response(
                text=f"Period set to: **{safe_inline(session.period)}**\n\n"
                     "Now set the materiality thresholds. Enter a dollar amount and a percentage, "
                     "for example: `$10,000 or 5%`\n\n"
                     "Or choose a preset below:",
                chips=["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%", "$50,000 or 15%"],
                phase=Phase.AWAITING_THRESHOLDS,
            )

    return Response(
        text="Please confirm if the layout looks right, or choose to change something.",
        chips=["Looks right", "Change something"],
        phase=Phase.AWAITING_INTAKE_CONFIRMATION,
    )


def _blank_wording(basis: ComparisonBasis) -> str:
    return "blank budgets" if basis is ComparisonBasis.BUDGET else f"blank {basis_noun(basis)} values"


def _handle_blank_budget_confirmation(session: Session, text: str) -> Response:
    """Confirm that blank comparison amounts are read as 0 (the only reading the engine has)."""
    lower = normalize_for_routing(text).lower()
    basis = session.intake_result.comparison_basis if session.intake_result is not None else ComparisonBasis.BUDGET
    blanks = _blank_wording(basis)
    treat = f"Treat {blanks} as 0 ({zero_comparison_phrase(basis)})"
    confirmed = "0" in lower or "unbudgeted" in lower or "treat" in lower or "yes" in lower
    if not confirmed:
        refused = lower.startswith(("keep", "leave", "no", "don't", "dont")) or "blank" in lower
        return Response(
            text=(
                f"{blanks.capitalize()} cannot stay blank in the analysis: a line with no amount "
                f"is read as 0 ({zero_comparison_phrase(basis)}). "
                if refused else "Please choose how to read the blank amounts. "
            ) + f"Choose **{treat}** to continue, or upload a corrected file.",
            chips=[treat, "Upload a different file"],
            phase=Phase.AWAITING_BLANK_BUDGET_CONFIRMATION,
        )
    if session.source_bytes is not None and session.source_suffix is not None:
        intake_res = read_input_assisted(
            session.source_bytes,
            session.source_suffix,
            filename=session.source_name or "input",
            sheet=session.worksheet,
            treat_blank_budgets_as_zero=True,
            compare_to=session.compare_to,
            hidden_rows=session.hidden_rows,
        )
        session.parsed_rows = intake_res.rows
        session.worksheet = intake_res.sheet_name
        session.available_sheets = intake_res.available_sheets
        session.intake_result = intake_res

        if intake_res.detected_period_pairs and len(intake_res.detected_period_pairs) > 1 and session.period is None:
            session.phase = Phase.AWAITING_PERIOD_CHOICE
            session.detected_period_pairs = intake_res.detected_period_pairs
            period_chips = [p.period for p in intake_res.detected_period_pairs]
            return Response(
                text="Found data for multiple periods in your file.\n\nWhich period would you like to analyze?",
                chips=period_chips,
                phase=Phase.AWAITING_PERIOD_CHOICE,
            )

        if not intake_res.has_transformations:
            session.phase = Phase.AWAITING_PERIOD
            row_count = len(intake_res.rows)
            worksheet_note = ""
            if intake_res.sheet_name:
                worksheet_note = f" from worksheet '{safe_inline(intake_res.sheet_name)}'"
                if len(session.available_sheets) > 1:
                    worksheet_note += f" ({len(session.available_sheets)} sheets available; switch with `sheet <name>`)"

            return Response(
                text=f"Loaded '{safe_inline(session.source_name or 'file')}' ({row_count} data row{'s' if row_count != 1 else ''}){worksheet_note}.\n\n"
                     "What reporting period does this analysis cover? (e.g., Q3 2026, October 2026, FY2026)",
                phase=Phase.AWAITING_PERIOD,
            )

        session.phase = Phase.AWAITING_INTAKE_CONFIRMATION
        return _intake_confirmation(intake_res, ["Looks right", "Change something"])
    session.phase = Phase.AWAITING_FILE
    return Response(
        text="Please upload a file using the drop zone above.",
        chips=["Upload a different file"],
        phase=Phase.AWAITING_FILE,
    )


def _handle_period_choice(session: Session, text: str) -> Response:
    """Handle user selection of which period to analyze from multi-period columns."""
    options = [p.period for p in session.detected_period_pairs]
    wanted = normalize_for_routing(_clean_period_input(text)).lower()
    chosen_period = next((o for o in options if normalize_for_routing(o).lower() == wanted), None)
    if chosen_period is None:
        return Response(
            text="Please choose which period you would like to analyze. "
                 "Pick one of the periods found in your file.",
            chips=options,
            phase=Phase.AWAITING_PERIOD_CHOICE,
        )
    if session.source_bytes is None or session.source_suffix is None:
        return _file_is_gone(session)

    session.period = chosen_period

    intake_res = read_input_assisted(
        session.source_bytes,
        session.source_suffix,
        filename=session.source_name or "input",
        sheet=session.worksheet,
        treat_blank_budgets_as_zero=False,
        selected_period=chosen_period,
        compare_to=session.compare_to,
        hidden_rows=session.hidden_rows,
    )
    session.parsed_rows = intake_res.rows
    session.worksheet = intake_res.sheet_name
    session.available_sheets = intake_res.available_sheets
    session.intake_result = intake_res

    session.phase = Phase.AWAITING_INTAKE_CONFIRMATION
    return _intake_confirmation(intake_res, ["Looks right", "Change something"])


def _file_is_gone(session: Session) -> Response:
    """The stored file is missing, so a question that needs it restarts at the upload."""
    session.phase = Phase.AWAITING_FILE
    return Response(
        text="I no longer have your file. Please upload it again using the drop zone above.",
        chips=["Help"],
        phase=Phase.AWAITING_FILE,
    )


_MULTI_TABLE_SUFFIXES = {".xlsx", ".xlsm", ".pdf"}


def _is_pdf(session: Session) -> bool:
    return (session.source_suffix or "").lower() == ".pdf"


def _sheet_word(session: Session) -> str:
    """A PDF holds statements where a workbook holds worksheets."""
    return "statement" if _is_pdf(session) else "worksheet"


def _choosable(session: Session, names: list[str]) -> list[str]:
    """Sheets worth offering as chips: in a PDF, only statements that can be compared."""
    result = session.intake_result
    if _is_pdf(session) and result is not None and result.comparable_sheets:
        return [name for name in names if name in result.comparable_sheets]
    return names


def _sheet_chip(session: Session, name: str) -> str:
    return f"{'Statement' if _is_pdf(session) else 'Sheet'} {name}"


def handle_upload(
    session: Session, file_bytes: bytes, filename: str, sheet: str | None = None,
    *, first_visit: bool | None = None,
) -> Response:
    """Process a file upload with assisted reading and plain language."""
    return _load_file(session, file_bytes, filename, sheet, first_visit)


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
        from .earnings import review_upload
        return review_upload(session, file_bytes, filename, None, sheet)
    if compare_to in {ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE, ComparisonBasis.GUIDANCE}:
        from .earnings import review_upload
        return review_upload(session, file_bytes, filename, compare_to, sheet)
    intake_res = read_input_assisted(
        file_bytes,
        suffix,
        filename=filename,
        sheet=sheet,
        treat_blank_budgets_as_zero=False,
        compare_to=compare_to,
    )
    failed = intake_res.has_fatal_errors or not intake_res.rows
    awaiting_answer = (bool(intake_res.comparison_choices) or len(intake_res.available_sheets) > 1
                       or intake_res.needs_hidden_rows_choice)
    if failed and not awaiting_answer:
        from .earnings import offer_review
        proposal = offer_review(session, file_bytes, filename)
        if proposal is not None:
            return proposal
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

        return Response(
            text=f"Loaded '{safe_inline(filename)}' ({row_count} data row{'s' if row_count != 1 else ''}){worksheet_note}.\n\n"
                 "What reporting period does this analysis cover? (e.g., Q3 2026, October 2026, FY2026)",
            phase=Phase.AWAITING_PERIOD,
        )

    session.phase = Phase.AWAITING_INTAKE_CONFIRMATION

    chips = ["Looks right", "Change something"]
    if intake_res.available_sheets and len(intake_res.available_sheets) > 1:
        other_sheets = [s for s in _choosable(session, intake_res.available_sheets)
                        if s != intake_res.sheet_name]
        if other_sheets:
            chips.insert(1, _sheet_chip(session, other_sheets[0]))

    return _intake_confirmation(intake_res, chips)


# ---------------------------------------------------------------------------
# Configuration phase handlers
# ---------------------------------------------------------------------------


def _clean_period_input(text: str) -> str:
    """Extract clean reporting period from conversational user input."""
    cleaned = text.strip()
    prefix_pattern = re.compile(
        r"^(?:(?:this\s+is|it\s+is|it\'s|the\s+period\s+is|period\s*(?:is|:)?|covers?|for)\s+)+",
        re.IGNORECASE,
    )
    cleaned = prefix_pattern.sub("", cleaned).strip()
    cleaned = cleaned.rstrip(".!?,")
    return cleaned or text.strip()


_MAX_PERIOD_CHARS = 100


def _handle_period(session: Session, text: str) -> Response:
    """Accept the reporting period."""
    period = _clean_period_input(text)
    if not period:
        return Response(
            text="The reporting period cannot be blank. Please enter a period (e.g., Q3 2026).",
            phase=Phase.AWAITING_PERIOD,
        )
    if len(period) > _MAX_PERIOD_CHARS:
        return Response(
            text=f"Please enter a short period label of up to {_MAX_PERIOD_CHARS} characters "
                 "(e.g., Q3 2026, October 2026, FY2026).",
            chips=["Q3 2026", "FY2026", "October 2026"],
            phase=Phase.AWAITING_PERIOD,
        )
    if parse_intent(text).intent_id != "unknown":
        return Response(
            text=f"'{safe_inline(period)}' looks like a command, not a reporting period. "
                 "Enter the period this file covers first (e.g., Q3 2026, October 2026, FY2026).",
            chips=["Q3 2026", "FY2026", "October 2026"],
            phase=Phase.AWAITING_PERIOD,
        )

    session.period = period
    session.phase = Phase.AWAITING_THRESHOLDS

    return Response(
        text=f"Period set to: **{safe_inline(period)}**\n\n"
             "Now set the materiality thresholds. Enter a dollar amount and a percentage, "
             "for example: `$10,000 or 5%`\n\n"
             "Or choose a preset below:",
        chips=["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%", "$50,000 or 15%"],
        phase=Phase.AWAITING_THRESHOLDS,
    )


_THRESHOLD_RE = re.compile(
    r"(?:(?:\$|dollar[s]?\s*[:=]?\s*)"
    r"(?P<dollar>[0-9][0-9,_.]*(?:[kKmMbB])?)"
    r"(?:"
    r"(?:\s+(?:or|and)\s+(?P<pct>[0-9][0-9,_.]*)\s*%?)"
    r"|"
    r"(?:\s*(?:/|&|,)\s*(?P<pct3>[0-9][0-9,_.]*)\s*(?:%|percent|pct))"
    r")"
    r"|"
    r"(?P<pct2>[0-9][0-9,_.]*)\s*(?:%|percent|pct)"
    r"\s*(?:or|and|/|,|&)\s*"
    r"(?:\$|dollar[s]?\s*[:=]?\s*)"
    r"(?P<dollar2>[0-9][0-9,_.]*(?:[kKmMbB])?))",
    re.IGNORECASE,
)


def _parse_threshold_amount(val_str: str, field: str) -> Decimal:
    """Parse a dollar threshold value supporting k/m/b shorthand multipliers."""
    clean = val_str.replace(",", "").replace("_", "").strip()
    multiplier = Decimal(1)
    if clean.lower().endswith("k"):
        multiplier = Decimal(1000)
        clean = clean[:-1].strip()
    elif clean.lower().endswith("m"):
        multiplier = Decimal(1000000)
        clean = clean[:-1].strip()
    elif clean.lower().endswith("b"):
        multiplier = Decimal(1000000000)
        clean = clean[:-1].strip()
    return parse_decimal(clean, field=field, line_item="Materiality") * multiplier


def _parse_threshold_text(text: str) -> tuple[Decimal, Decimal] | None:
    """Extract dollar and percent thresholds from natural text."""
    match = _THRESHOLD_RE.search(text)
    if match:
        dollar_str = match.group("dollar") or match.group("dollar2")
        pct_str = match.group("pct") or match.group("pct3") or match.group("pct2")
        if dollar_str and pct_str:
            pct_str = pct_str.replace(",", "").replace("_", "")
            try:
                dollar = _parse_threshold_amount(dollar_str, field="dollar_threshold")
                pct = parse_decimal(pct_str, field="percent_threshold", line_item="Materiality")
                return (dollar, pct / Decimal("100"))
            except (ValueError, InvalidOperation):
                return None
    return None


_SINGLE_DOLLAR_RE = re.compile(
    r"(?:(?:\$|dollar[s]?\s*[:=]?\s*)(?P<dollar>[0-9][0-9,_.]*(?:[kKmMbB])?)|(?P<dollar2>[0-9][0-9,_.]*(?:[kKmMbB])?)\s*(?:dollars?))",
    re.IGNORECASE,
)
_SINGLE_PCT_RE = re.compile(
    r"(?:(?P<pct>[0-9][0-9,_.]*)\s*%|(?:percent|percentage|pct)\s*[:=]?\s*(?P<pct2>[0-9][0-9,_.]*))",
    re.IGNORECASE,
)


def _parse_partial_threshold_text(text: str) -> tuple[Decimal | None, Decimal | None]:
    """Extract dollar and/or percent thresholds from text, supporting partial adjustments."""
    both = _parse_threshold_text(text)
    if both is not None:
        return both

    dollar: Decimal | None = None
    pct: Decimal | None = None

    d_match = _SINGLE_DOLLAR_RE.search(text)
    if d_match:
        d_str = d_match.group("dollar") or d_match.group("dollar2")
        if d_str:
            try:
                dollar = _parse_threshold_amount(d_str, field="dollar_threshold")
            except (ValueError, InvalidOperation):
                pass

    p_match = _SINGLE_PCT_RE.search(text)
    if p_match:
        p_str = p_match.group("pct") or p_match.group("pct2")
        if p_str:
            p_str = p_str.replace(",", "").replace("_", "")
            try:
                parsed_pct = parse_decimal(p_str, field="percent_threshold", line_item="Materiality")
                pct = parsed_pct / Decimal("100")
            except (ValueError, InvalidOperation):
                pass

    return (dollar, pct)


_ORDINAL_MAP: dict[str, int] = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "4th": 3,
    "fifth": 4,
    "5th": 4,
    "sixth": 5,
    "6th": 5,
    "seventh": 6,
    "7th": 6,
    "eighth": 7,
    "8th": 7,
    "ninth": 8,
    "9th": 8,
    "tenth": 9,
    "10th": 9,
}

_POSITIONAL_RE = re.compile(
    r"^(?:(?:the\s+)?(?:number|no\.?|num\.?|#|item|row|line)\s*)?(?P<num>\d+)(?:st|nd|rd|th)?$",
    re.IGNORECASE,
)


def _resolve_item_query(query: str, session: Session) -> str:
    """Resolve pronouns, ordinals, and numerical references against session context."""
    raw = query.strip().rstrip("?").strip("'\"`[]").strip()
    raw_lower = raw.lower()

    # Determine candidate items from most recent table or analysis result
    candidate_items = session.last_table_items
    if not candidate_items and session.result is not None:
        candidate_items = [r.line_item for r in session.result.material_rows]
    if not candidate_items and session.result is not None:
        candidate_items = [r.line_item for r in session.result.rows]

    # 1. Empty query or demonstratives ("it", "this", "that", "that one", "did that happen", etc.)
    if not raw or raw_lower in (
        "it", "this", "that", "current", "same", "the item", "the line",
        "that one", "this one", "the current one", "did that happen",
        "did this happen", "that happened", "this happened", "is that",
        "is this", "there", "here", "to that", "to this",
    ):
        if session.last_focused_item:
            return session.last_focused_item
        if candidate_items:
            return candidate_items[0]
        return raw

    # 2. "last", "last item", "last one", "last row", "bottom", "bottom one", "lowest"
    if re.sub(r"^the\s+", "", raw_lower) in ("last", "last item", "last one", "last row", "last line", "bottom", "bottom one", "lowest"):
        if candidate_items:
            return candidate_items[-1]
        if session.last_focused_item:
            return session.last_focused_item
        return raw

    # 3. Ordinals ("first", "the first one", "2nd", "top one", etc.)
    ordinal_key = re.sub(r"^the\s+", "", raw_lower).strip()
    ordinal_key = re.sub(r"\s+one$", "", ordinal_key).strip()
    if ordinal_key in ("top", "highest", "biggest"):
        if candidate_items:
            return candidate_items[0]
    if ordinal_key in _ORDINAL_MAP:
        idx = _ORDINAL_MAP[ordinal_key]
        if 0 <= idx < len(candidate_items):
            return candidate_items[idx]
        return raw

    # 4. Positional indices ("#1", "1", "item 2", "number 3", "row 1")
    pos_match = _POSITIONAL_RE.match(raw)
    if pos_match:
        idx = int(pos_match.group("num")) - 1
        if 0 <= idx < len(candidate_items):
            return candidate_items[idx]
        return raw

    return raw


# Words too common in account names to identify one on their own.
_GENERIC_ITEM_WORDS = frozenset({
    "revenue", "revenues", "expense", "expenses", "cost", "costs", "total", "sales", "income", "other",
})


# Words that are never an account name when they stand alone in a sentence ("is it over budget").
_SENTENCE_STOPWORDS = frozenset({
    "it", "is", "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "we", "us", "our", "up",
})
_WORD_RE = re.compile(r"[\w&]+")


def _items_named_in(text: str, items: list[str]) -> list[str]:
    """Line items whose whole name appears in the sentence as whole words, longest name first."""
    padded = f" {' '.join(_WORD_RE.findall(normalize_for_routing(text).lower()))} "
    named: list[str] = []
    for item in dict.fromkeys(items):
        words = _WORD_RE.findall(normalize_for_routing(item).lower())
        if not words or (len(words) == 1 and words[0] in _SENTENCE_STOPWORDS):
            continue
        if f" {' '.join(words)} " in padded:
            named.append(item)
    return sorted(named, key=len, reverse=True)


def _item_in_sentence(text: str, items: list[str], named: list[str] | None = None) -> str | None:
    """Find the one line item a free-form sentence names, e.g. 'is marketing bad?'.

    ``named`` is the result of ``_items_named_in`` when the caller already has it.
    """
    if named is None:
        named = _items_named_in(text, items)
    if named:
        return named[0]
    words = set(_WORD_RE.findall(normalize_for_routing(text).lower()))
    hits = [
        item for item in dict.fromkeys(items)
        if any(len(word) >= 4 and word not in _GENERIC_ITEM_WORDS and word in words
               for word in _WORD_RE.findall(normalize_for_routing(item).lower()))
    ]
    return hits[0] if len(hits) == 1 else None


# Spelling suggestions compare the query with every account name, so both sides are bounded:
# real account names are short, and a file can have a hundred thousand lines.
_SUGGEST_MAX_QUERY = 40
_SUGGEST_MAX_ITEMS = 2000


def _suggest_items(query: str, items: list[str], limit: int = 3) -> list[str]:
    """Close spellings of a line item (whole name or any word of it); deterministic."""
    q = normalize_for_routing(query).lower()
    if not 3 <= len(q) <= _SUGGEST_MAX_QUERY:
        return []
    scored: list[tuple[float, str]] = []
    for item in list(dict.fromkeys(items))[:_SUGGEST_MAX_ITEMS]:
        name = normalize_for_routing(item).lower()[:200]
        score = 0.0
        for candidate in [name, *name.split()]:
            matcher = difflib.SequenceMatcher(None, q, candidate)
            if matcher.real_quick_ratio() >= 0.75 and matcher.quick_ratio() >= 0.75:
                score = max(score, matcher.ratio())
        if score >= 0.75:
            scored.append((-score, item))
    return [item for _, item in sorted(scored)[:limit]]


def _not_found(display_q: str, query: str, items: list[str], verb: str) -> Response:
    """No-match reply with a bounded 'did you mean' for likely typos."""
    suggestions = _suggest_items(query, items)
    if suggestions:
        names = " or ".join(f"**{safe_inline(item)}**" for item in suggestions)
        return Response(
            text=f"No line item matching '{display_q}' was found. Did you mean {names}?",
            chips=[f"{verb} {item}?" for item in suggestions],
            phase=Phase.EXPLORING,
        )
    items_list = ", ".join(safe_inline(item) for item in items[:20])
    if len(items) > 20:
        items_list += f", and {len(items) - 20} more"
    return Response(
        text=f"No line item matching '{display_q}' was found.\n\nAvailable items: {items_list}",
        phase=Phase.EXPLORING,
    )


def _handle_thresholds(session: Session, text: str) -> Response:
    """Parse and set materiality thresholds."""
    parsed = _parse_threshold_text(normalize_for_routing(text))
    if parsed is None:
        return Response(
            text="I couldn't parse those thresholds. Please enter them as: `$10,000 or 5%`",
            chips=["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%"],
            phase=Phase.AWAITING_THRESHOLDS,
        )

    dollar, pct_ratio = parsed
    session.dollar_threshold = dollar
    session.percent_threshold = pct_ratio
    session.phase = Phase.AWAITING_CURRENCY

    return Response(
        text=f"Thresholds set: **{format_threshold_amount(dollar, session.currency)}** "
             f"or **{format_threshold_pct(pct_ratio)}**\n\n"
             "What is the reporting currency?",
        chips=["USD", "EUR", "GBP"],
        phase=Phase.AWAITING_CURRENCY,
    )


def _clean_currency_input(text: str) -> str:
    """Extract standard ISO currency code from conversational user input."""
    cleaned = text.strip().upper()
    if cleaned in ("DEFAULT", ""):
        return "USD"
    if "$" in text:
        return "USD"
    if "€" in text:
        return "EUR"
    if "£" in text:
        return "GBP"
    match = re.search(r"\b(USD|EUR|GBP)\b", cleaned)
    if match:
        return match.group(1)
    return cleaned


def _handle_currency(session: Session, text: str) -> Response:
    """Set the reporting currency and run the initial analysis."""
    currency = _clean_currency_input(normalize_for_routing(text))
    try:
        validate_currency(currency)
    except ValueError:
        return Response(
            text="Please choose a supported currency: USD, EUR, or GBP.",
            chips=["USD", "EUR", "GBP"],
            phase=Phase.AWAITING_CURRENCY,
        )

    session.currency = currency
    return _run_analysis(session)


def _run_analysis(session: Session) -> Response:
    """Run the deterministic analysis engine and handle classification."""
    if session.parsed_rows is None:
        return _file_is_gone(session)
    if session.period is None:
        session.phase = Phase.AWAITING_PERIOD
        return Response(
            text="What reporting period does this analysis cover? (e.g., Q3 2026, October 2026, FY2026)",
            phase=Phase.AWAITING_PERIOD,
        )
    if session.dollar_threshold is None or session.percent_threshold is None:
        session.phase = Phase.AWAITING_THRESHOLDS
        return Response(
            text="I need your materiality thresholds first. Enter a dollar amount and a percentage, "
                 "for example: `$10,000 or 5%`",
            chips=["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%", "$50,000 or 15%"],
            phase=Phase.AWAITING_THRESHOLDS,
        )

    measure_question = _next_measure_question(session)
    if measure_question is not None:
        return measure_question
    intake = session.intake_result
    config = AnalysisConfig(
        period=session.period,
        dollar_threshold=session.dollar_threshold,
        percent_threshold=session.percent_threshold,
        type_map=dict(session.type_map),
        currency=session.currency,
        comparison_basis=intake.comparison_basis if intake is not None else ComparisonBasis.BUDGET,
        comparison_label=intake.comparison_label if intake is not None else None,
    )

    if any("measure" in normalize_row(row) or "better" in normalize_row(row) for row in session.parsed_rows):
        config = AudienceConfig(
            config.period, config.dollar_threshold, config.percent_threshold, type_map=config.type_map,
            currency=config.currency, comparison_basis=config.comparison_basis, comparison_label=config.comparison_label,
            per_share_threshold=session.per_share_threshold, count_threshold=session.count_threshold,
            bps_threshold=session.bps_threshold, percent_values=session.percent_values,
        )
    try:
        with financial_context():
            if session.earnings_mode:
                from .earnings import analyze_review, summary
                session.table_analysis = analyze_review(session, config)
                first = next((comparison.result for comparison in session.table_analysis.comparisons
                              if comparison.result is not None), None)
                if first is None:
                    session.result = None
                    session.phase = Phase.EXPLORING
                    return summary(session)
                result = first
            else:
                result = analyze_rows(session.parsed_rows, config)
    except (ValueError, RuntimeError) as exc:
        session.phase = Phase.AWAITING_FILE
        technical = str(exc)
        session.last_technical_detail = technical
        plain_err = plain_analysis_error(technical)
        chips = ["Upload a different file"]
        if session.available_sheets and len(session.available_sheets) > 1:
            for s in _choosable(session, session.available_sheets)[:2]:
                if s != session.worksheet:
                    chips.append(_sheet_chip(session, s))
        chips.append("Show technical details")
        return Response(
            text=plain_err,
            chips=chips,
            phase=Phase.AWAITING_FILE,
            level="error",
        )

    session.result = result

    # Ask only about unclassified rows the user has not already decided to skip
    unclassified = list(dict.fromkeys(
        row.line_item for row in result.rows
        if row.line_type == LineType.UNCLASSIFIED and currency_row(row) and row.better is None
        and row.line_item not in session.skipped_items
    ))

    if unclassified:
        session.unclassified_queue = list(unclassified)
        session.phase = Phase.RESOLVE_UNCLASSIFIED

        gl_rules = infer_gl_range_rules(unclassified)
        if gl_rules:
            session.pending_gl_rules = gl_rules
            lines = ["Found account numbers. Proposed classification rules:\n"]
            for r in gl_rules:
                lbl = "Revenue" if r.line_type == LineType.REVENUE else "Expense"
                lines.append(f"- Accounts {r.min_account}–{r.max_account}: {lbl} ({r.match_count} lines)")
            lines.append("\nDoes this look right?")
            return Response(
                text="\n".join(lines),
                chips=["Looks right", "Label all as Expense", "Label all as Revenue", "Skip all"],
                phase=Phase.RESOLVE_UNCLASSIFIED,
            )

        item = safe_inline(session.unclassified_queue[0])
        remaining = len(session.unclassified_queue)
        chips = ["Revenue", "Expense"]
        if remaining > 1:
            chips.extend(["Label all as Expense", "Label all as Revenue"])
        chips.extend(["Skip", "Skip all"])
        return Response(
            text=f"Analysis complete, but **{remaining}** line item{'s are' if remaining != 1 else ' is'} not yet labeled revenue or expense.\n\n"
                 f"**'{item}'** is not yet labeled revenue or expense. Should it be:",
            chips=chips,
            phase=Phase.RESOLVE_UNCLASSIFIED,
        )

    session.phase = Phase.EXPLORING
    return _build_analysis_summary(session)


def _handle_classify(session: Session, text: str) -> Response:
    """Handle classification of an unclassified line item."""
    text_lower = normalize_for_routing(text).lower()

    if text_lower in ("skip all", "done", "skip remaining"):
        session.skipped_items.update(session.unclassified_queue)
        session.unclassified_queue.clear()
        session.pending_gl_rules = []
        session.phase = Phase.EXPLORING
        return _rerun_after_classification(session) if session.type_map else _build_analysis_summary(session)

    if session.pending_gl_rules and text_lower in (
        "looks right", "yes", "confirm", "looks good", "correct", "proceed", "looks_right", "1"
    ):
        applied = apply_classification_rules(session.unclassified_queue, session.pending_gl_rules)
        session.type_map.update(applied)
        session.pending_gl_rules = []
        session.unclassified_queue = [
            itm for itm in session.unclassified_queue if itm not in applied
        ]
        if not session.unclassified_queue:
            return _run_analysis(session)
        item = safe_inline(session.unclassified_queue[0])
        remaining = len(session.unclassified_queue)
        chips = ["Revenue", "Expense"]
        if remaining > 1:
            chips.extend(["Label all as Expense", "Label all as Revenue"])
        chips.extend(["Skip", "Skip all"])
        return Response(
            text=f"Rules applied! **{remaining}** item{'s' if remaining != 1 else ''} remaining.\n\n"
                 f"**'{item}'** is not yet labeled revenue or expense. Should it be:",
            chips=chips,
            phase=Phase.RESOLVE_UNCLASSIFIED,
        )

    if text_lower in ("label all as expense", "all expense", "all expenses", "everything expense"):
        for itm in session.unclassified_queue:
            session.type_map[itm] = LineType.EXPENSE
        session.unclassified_queue.clear()
        session.pending_gl_rules = []
        return _run_analysis(session)

    if text_lower in ("label all as revenue", "all revenue", "everything revenue"):
        for itm in session.unclassified_queue:
            session.type_map[itm] = LineType.REVENUE
        session.unclassified_queue.clear()
        session.pending_gl_rules = []
        return _run_analysis(session)

    if not session.unclassified_queue:
        session.pending_gl_rules = []
        session.phase = Phase.EXPLORING
        return _build_analysis_summary(session)

    current_item = session.unclassified_queue[0]

    if text_lower in ("revenue", "income", "sales", "rev", "1"):
        session.type_map[current_item] = LineType.REVENUE
        session.unclassified_queue.pop(0)
    elif text_lower in ("expense", "expenses", "cost", "costs", "exp", "2"):
        session.type_map[current_item] = LineType.EXPENSE
        session.unclassified_queue.pop(0)
    elif text_lower in ("skip", "3", "ignore"):
        session.skipped_items.add(session.unclassified_queue.pop(0))
    else:
        chips = ["Revenue", "Expense"]
        if len(session.unclassified_queue) > 1:
            chips.extend(["Label all as Expense", "Label all as Revenue"])
        chips.extend(["Skip", "Skip all"])
        return Response(
            text=f"Please choose Revenue, Expense, or Skip for '{safe_inline(current_item)}'.",
            chips=chips,
            phase=Phase.RESOLVE_UNCLASSIFIED,
        )

    if session.unclassified_queue:
        next_item = safe_inline(session.unclassified_queue[0])
        remaining = len(session.unclassified_queue)
        chips = ["Revenue", "Expense"]
        if remaining > 1:
            chips.extend(["Label all as Expense", "Label all as Revenue"])
        chips.extend(["Skip", "Skip all"])
        return Response(
            text=f"Got it. {remaining} remaining.\n\n"
                 f"**'{next_item}'** is not yet labeled revenue or expense. Should it be:",
            chips=chips,
            phase=Phase.RESOLVE_UNCLASSIFIED,
        )

    # All resolved — re-run analysis with updated type_map
    return _rerun_after_classification(session)


def _rerun_after_classification(session: Session) -> Response:
    """Re-run analysis with the new classifications, rolling them back if the engine rejects them."""
    previous = session.result
    added = [
        item for item in session.type_map
        if previous is not None and any(
            row.line_item == item and row.line_type == LineType.UNCLASSIFIED for row in previous.rows
        )
    ]
    response = _run_analysis(session)
    if response.phase != Phase.AWAITING_FILE or previous is None:
        return response

    # e.g. classifying a row as Revenue can break a reconciled 'Total Revenue' subtotal
    for item in added:
        del session.type_map[item]
        session.skipped_items.add(item)
    session.result = previous
    session.unclassified_queue.clear()
    session.phase = Phase.EXPLORING
    summary = _build_analysis_summary(session)
    names = ", ".join(f"'{safe_inline(item)}'" for item in added)
    return with_lead(replace(summary, phase=Phase.EXPLORING),
                     f"{response.text}\n\nThe classification of {names} was not applied; "
                     "those items stay Unclassified.\n\n")


def _audience_summary(result: AnalysisResult) -> Response:
    """A comparison set: the report as text, and the same rows as a results view and one table."""
    cfg = result.config
    heading = extended_heading(cfg)
    money = [row for row in result.rows if currency_row(row)]
    complete = (all(row.line_type is not LineType.UNCLASSIFIED for row in money)
                and any(row.line_type is LineType.REVENUE for row in money)
                and any(row.line_type is LineType.EXPENSE for row in money))
    figures: list[dict[str, object]] = []
    notes: list[str] = []
    if complete:
        for label, total in (("Revenue", result.revenue), ("Expenses", result.expenses)):
            figures.append(figure(label, format_money(total.actual, cfg.currency),
                                  f"{heading} {format_money(total.budget, cfg.currency)}",
                                  f"Variance {format_money(total.variance_dollars, cfg.currency)}, "
                                  f"{format_pct(total.budget, total.variance_dollars, total.percent_label)}",
                                  status_label(total.status)))
        with financial_context():
            net = result.revenue.variance_dollars - result.expenses.variance_dollars
        figures.append(figure("Net operating variance", format_money(net, cfg.currency), tone=_tone(net)))
    else:
        notes.append("Currency totals are incomplete; net operating impact is unavailable.")
    segmented = any(row.segment_declared for row in result.rows)
    table: list[dict[str, str]] = []
    for row in result.rows:
        variance = row.variance_bps if row.measure is MeasureKind.PERCENT else row.variance_dollars
        assert variance is not None
        record = {"Line Item": row.line_item}
        if segmented:
            record["Segment"] = row.segment
        record.update({"Measure": str(row.measure), heading: format_measure(row.budget, row.measure, cfg.currency),
                       "Actual": format_measure(row.actual, row.measure, cfg.currency),
                       "Variance": format_measure(variance, row.measure, cfg.currency, variance=True),
                       "Var (%)": format_pct(row.budget, row.variance_dollars, row.percent_label),
                       "Status": display_outcome(row, cfg.comparison_basis), "Material": "Yes" if row.material else "No"})
        table.append(record)
        detail = row.comparison_details
        for position in (detail.guidance_position, detail.consensus_range_position) if detail is not None else ():
            if position:
                notes.append(f"{row.line_item}: {position}.")
    view = figures_view(
        f"{cfg.period} against {heading}",
        context=[pair("Currency", cfg.currency)],
        figures=figures,
        sections=[("How the file was read", [pair(*note.split(": ", 1)) if ": " in note else pair("Note", note)
                                             for note in result.warnings])] if result.warnings else (),
        notes=notes,
        table_title=f"{len(table)} line{'s' if len(table) != 1 else ''}, each in its own unit",
    )
    return Response(text=render_markdown(result), table=table, chips=["Summary", "Export Excel", "Export audit"],
                    phase=Phase.EXPLORING, view=view)


def _build_analysis_summary(session: Session) -> Response:
    """Build the initial analysis summary after successful analysis."""
    if session.earnings_mode and session.table_analysis is not None:
        from .earnings import summary
        return summary(session)
    result = session.result
    assert result is not None
    if is_audience_result(result):
        return _audience_summary(result)
    cfg = result.config
    places = report_places(result)

    lines = [
        "**Analysis Complete**\n",
        f"**Period:** {safe_inline(cfg.period)}",
        f"**Currency:** {cfg.currency}",
        f"**Thresholds:** {format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or "
        f"{format_threshold_pct(cfg.percent_threshold)}\n",
    ]
    heading = _plain_heading(cfg)
    figures: list[dict[str, object]] = []
    notes: list[str] = []

    # Revenue summary
    has_revenue = any(
        row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
        for row in result.rows
    )
    has_expenses = any(
        row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
        for row in result.rows
    )
    classification_incomplete = any(
        row.line_type == LineType.UNCLASSIFIED for row in result.rows
    )

    for label, total, present, missing in (
        ("Revenue", result.revenue, has_revenue, "no Revenue rows"),
        ("Expenses", result.expenses, has_expenses, "no Expense rows"),
    ):
        if present and not classification_incomplete:
            actual = format_money(total.actual, cfg.currency, places)
            compared = format_money(total.budget, cfg.currency, places)
            variance = format_money(total.variance_dollars, cfg.currency, places)
            pct = format_pct(total.budget, total.variance_dollars, total.percent_label)
            word = status_label(total.status)
            lines.append(f"**Total {label}:** {actual} vs. {compared} ({variance}, {pct}, {word})")
            figures.append(figure(label, actual, f"{heading} {compared}", f"Variance {variance}, {pct}", word))
        else:
            reason = "classification incomplete" if classification_incomplete else missing
            lines.append(f"**Total {label}:** N/A ({reason})")
            figures.append(figure(label, "N/A", reason.capitalize()))

    # Net operating impact
    if not classification_incomplete and has_revenue and has_expenses:
        with financial_context():
            net_impact = result.revenue.variance_dollars - result.expenses.variance_dollars
        direction = "above" if net_impact > 0 else "below" if net_impact < 0 else "in line with"
        net_text = format_money(net_impact, cfg.currency, places)
        lines.append(f"\n**Net Operating Impact:** {net_text}, {direction} {_noun(cfg)}")
        figures.append(figure("Net operating impact", net_text, f"{direction.capitalize()} {_noun(cfg)}",
                              tone=_tone(net_impact)))
    else:
        lines.append("\n**Net Operating Impact:** N/A")
        figures.append(figure("Net operating impact", "N/A"))

    material_count = len(result.material_rows)
    material_text = f"{material_count} material variance{'s' if material_count != 1 else ''}"
    lines.append(f"\n**{material_count}** material variance{'s' if material_count != 1 else ''} found.")

    if classification_incomplete:
        notes.append("Totals wait until every line is labeled revenue or expense.")
    if result.warnings:
        warned = f"{len(result.warnings)} data quality warning{'s' if len(result.warnings) != 1 else ''}."
        lines.append(f"\n{warned}")
        notes.append(warned)

    text = "\n".join(lines)

    # Build table of material variances
    table = None
    if result.material_rows:
        session.last_table_items = [r.line_item for r in result.material_rows]
        session.last_focused_item = session.last_table_items[0]
        table = [
            row_to_table_dict(row, cfg.currency, places, _heading(cfg))
            for row in result.material_rows
        ]
    view = figures_view(
        f"{cfg.period} against {_noun(cfg)}",
        context=[pair("Currency", cfg.currency),
                 pair("Material at", f"{format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or "
                                     f"{format_threshold_pct(cfg.percent_threshold)}"),
                 pair("Lines read", str(len(result.rows)))],
        figures=figures, notes=notes,
        table_title=material_text.capitalize() if table else f"No {material_text[2:]}" if material_count == 0 else None,
    )

    # Suggest useful next actions
    chips = []
    if result.material_rows:
        first_item = result.material_rows[0].line_item
        chips.append(f"Why {first_item}?")
    chips.extend(["Show unfavorable", "Summary", "Export report", "Save layout mapping"])
    if result.warnings:
        chips.append("Warnings")

    return Response(text=text, table=table, chips=chips, phase=Phase.EXPLORING, view=view)


# ---------------------------------------------------------------------------
# Exploring phase handlers
# ---------------------------------------------------------------------------


def _saved_comparison_basis(session: Session) -> ComparisonBasis | None:
    """The basis a saved mapping replays: an explicit choice, else a detected non-Budget basis."""
    if session.compare_to is not None:
        return session.compare_to
    intake_res = session.intake_result
    if intake_res is not None and intake_res.comparison_basis is not ComparisonBasis.BUDGET:
        return intake_res.comparison_basis
    return None


def _layout_mapping_for(session: Session) -> LayoutMapping:
    """The layout mapping that replays the session's confirmed layout choices."""
    intake_res = session.intake_result
    col_mapping: dict[str, str] = {}
    header_row = 1
    unit_scale = None
    flip_signs = False
    hidden_rows: str | None = None
    excluded_totals: list[str] = []
    fingerprint = ""

    if intake_res is not None:
        header_row = intake_res.header_row_number
        col_mapping = {role.value: name for role, name in intake_res.column_mapping.items()}
        if intake_res.detected_unit_multiplier != Decimal("1"):
            unit_scale = str(intake_res.detected_unit_multiplier)
        flip_signs = intake_res.detected_signed_ledger
        excluded_totals = list(intake_res.detected_totals)
        hidden_rows = intake_res.hidden_rows_choice
        if intake_res.raw_headers:
            fingerprint = compute_layout_fingerprint(intake_res.raw_headers)

    classification_rules: dict[str, object] | None = None
    if session.type_map:
        classification_rules = {
            "keywords": {k: v.value.capitalize() for k, v in session.type_map.items()}
        }

    return LayoutMapping(
        mapping_version="1.5",
        layout_fingerprint=fingerprint,
        header_row_number=header_row,
        sheet_name=session.worksheet,
        column_mapping=col_mapping,
        unit_scale=unit_scale,
        flip_signs=flip_signs,
        treat_blank_budgets_as_zero=True,
        exclude_totals=excluded_totals,
        period_column_selection=session.period,
        classification_rules=classification_rules,
        comparison_basis=_saved_comparison_basis(session),
        comparison_bases=session.comparison_bases if len(session.comparison_bases) > 1 else (),
        measure_options={key: str(value) for key in ("per_share_threshold", "count_threshold", "bps_threshold", "percent_values")
                         if (value := getattr(session, key)) is not None} or None,
        better_directions={str(row.get("line_item", "")): str(row["better"])
                           for raw in session.parsed_rows or [] if (row := normalize_row(raw)).get("better")},
        hidden_rows=hidden_rows,
    )


def _handle_save_mapping(session: Session) -> Response:
    """Export confirmed layout choices as a JSON mapping file."""
    mapping = _layout_mapping_for(session)
    session.layout_mapping = mapping
    mapping_json = save_mapping(mapping)
    return Response(
        text=(
            "**Layout Mapping Saved**\n\n"
            "Here are your confirmed layout settings. You can reuse this mapping in future months with `--mapping <file>`:\n\n"
            f"```json\n{mapping_json}\n```"
        ),
        chips=["Summary", "Export report", "Show unfavorable"],
        phase=Phase.EXPLORING,
    )


def _pct_text(value: Decimal | None, spec: str = ".1f", suffix: str = "%") -> str:
    """Format a percentage, or N/A when its base was zero (the ratio is undefined)."""
    return "N/A" if value is None else f"{value:{spec}}{suffix}"


def _variance_percent(variance: Decimal, comparison: Decimal) -> Decimal | None:
    """Variance as a percent of the absolute comparison amount (the engine's rule), None if it is 0."""
    return None if comparison == 0 else ratio(variance, abs(comparison)) * Decimal(100)


def _pct_change(new: Decimal | None, old: Decimal | None) -> Decimal | None:
    return None if new is None or old is None else new - old


def _unclassified_note(result: AnalysisResult) -> str:
    """Caveat for totals that leave out unclassified rows, or '' when there are none."""
    count = sum(row.line_type == LineType.UNCLASSIFIED for row in _detail_rows(result))
    if not count:
        return ""
    return (f"Excludes {count} unclassified line item{'s' if count != 1 else ''} from these totals; "
            "classify them for complete figures.")


def _with_unclassified_note(text: str, result: AnalysisResult) -> str:
    """Append the unclassified-rows caveat to an answer built from category totals."""
    note = _unclassified_note(result)
    return f"{text}\n\n{note}" if note else text


def _detail_rows(result: AnalysisResult) -> list[AnalyzedRow]:
    """Line items without reconciled subtotal/total rows, which would double count."""
    return [row for row in result.rows if not row.excluded_from_aggregation]


def _handle_exploring(session: Session, text: str) -> Response:
    """Route a message through the intent parser during the EXPLORING phase."""
    if normalize_for_routing(text).lower() in ("save layout mapping", "save mapping"):
        return _handle_save_mapping(session)

    intent = parse_intent(text)
    if session.earnings_mode and session.table_analysis is not None:
        from .earnings import explore
        return explore(session, intent.intent_id, intent.captures)
    if session.result is None:
        return _file_is_gone(session)

    if is_audience_result(session.result) and intent.intent_id not in {
        "summary", "material", "filter_favorable", "filter_unfavorable", "export_report", "export_audit", "export_xlsx",
    }:
        return Response(text=render_markdown(session.result),
                        chips=["Summary", "Material", "Export report", "Export Excel"], phase=Phase.EXPLORING)
    handler = _EXPLORING_HANDLERS.get(intent.intent_id)
    if handler is not None:
        return handler(session, intent)

    return _handle_unknown(session, text)


def _handle_help(session: Session) -> Response:
    """What the tool does and everything you can ask it."""
    text = (
        "**What you can ask**\n\n"
        "I compare each line's Actual against your budget, forecast or prior period, flag the gaps "
        "big enough to matter, and say whether each one helped or hurt profit. Every figure comes from "
        "exact, repeatable calculations, never estimates. It is built for FP&A analysts, controllers and "
        "anyone preparing a month-end or quarter-end variance review.\n\n"
        "**Analysis**\n"
        "• `memo` / `briefing`: a management briefing on the period, with a download\n"
        "• `waterfall` / `bridge`: the walk from budget to actual operating profit, step by step\n"
        "• `what if [line] [+/-X% or $Y]`: profit and margin if one line changes\n"
        "• `sensitivity`: operating profit under five revenue and expense swings\n"
        "• `run rate` / `project year end`: the annualised pace and a latest-estimate projection\n"
        "• `drivers` / `driver summary`: which lines have driver data, and whether it reconciles\n"
        "• `biggest risks`: the largest material unfavorable variances\n"
        "• `biggest wins`: the largest favorable variances\n"
        "• `revenue status`: revenue against budget, line by line\n"
        "• `expense status`: expenses against budget, and the largest overspends\n"
        "• `burn rate` / `budget utilization`: the share of the expense budget spent\n"
        "• `variance concentration` / `pareto`: the share of the total variance in the top three lines\n"
        "• `unbudgeted spend`: lines with spending and no budget\n"
        "• `cost savings`: expense lines below budget\n"
        "• `revenue misses`: revenue lines below budget\n"
        "• `highest percent`: the largest variances in percentage terms\n"
        "• `compare [line] vs [line]`: two lines side by side, actual against budget, or revenue against expenses\n"
        "• `sheets` / `sheet <name>`: list and switch Excel worksheets or PDF statements\n"
        "• `metrics`: line counts, the material share and the mix of lines\n\n"
        "**Concepts, any time**\n"
        "• `what is materiality?`: the dollar-or-percent test for what needs explaining\n"
        "• `favorable vs unfavorable`: why a revenue gain and an expense saving are both favorable\n"
        "• `what is net impact?`: how net operating impact is worked out\n"
        "• `budget vs forecast`: how a budget and a latest estimate differ\n"
        "• `timing vs permanent`: variances that reverse and variances that last\n"
        "• `operating leverage`: fixed and variable costs, and drop-through\n"
        "• `what are financial kpis?`: the measures a variance review reports\n"
        "• `what is driver decomposition?`: splitting a variance into price and volume\n"
        "• `audit trail`: what the audit file records, including source fingerprints\n\n"
        "**Exploring the results**\n"
        "• `summary`: the headline figures and net operating impact\n"
        "• `material`: every material variance\n"
        "• `unfavorable` / `favorable`: one status only\n"
        "• `revenue` / `expenses`: one type only\n"
        "• `top 3`: the largest variances by amount\n"
        "• `totals`: revenue and expense totals\n"
        "• `warnings`: data quality notes\n"
        "• `recommendations`: suggested next steps for the largest variances\n\n"
        "**One line in detail**\n"
        "• `why [line]`: what drove one line's variance\n"
        "• `detail [line]`: everything recorded for one line\n"
        "• `threshold $X or Y%`: run again with different materiality thresholds\n\n"
        "**Export and session**\n"
        "• `export report`: download the Markdown report\n"
        "• `export excel`: download the Excel workbook\n"
        "• `export csv`: download every row as CSV\n"
        "• `export audit`: download the audit file (JSON)\n"
        "• `report`: show the full report here\n"
        "• `new`: start over with a new file\n"
        "• `help`: show this list"
    )
    # Result questions only once there is a result; before that, offer what works without a file.
    chips = (["Summary", "Biggest risks", "Biggest wins", "Material"] if session.result is not None
             else ["Supported file formats", "What is materiality?", "Budget vs forecast"])
    return Response(
        text=text,
        chips=chips,
        phase=session.phase,
    )


def _handle_reset(session: Session) -> Response:
    """Reset the session for a new analysis."""
    session.reset()
    return Response(
        text="Session cleared. Upload a new file to begin.",
        phase=Phase.AWAITING_FILE,
    )


def _handle_summary(session: Session) -> Response:
    """Show executive summary."""
    return _build_analysis_summary(session)


def _handle_material(session: Session) -> Response:
    """Show all material variances."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    if not result.material_rows:
        return Response(
            text="No line item exceeded either configured materiality threshold.",
            chips=["Summary", "Show all revenue", "Show all expenses"],
            phase=Phase.EXPLORING,
        )

    session.last_table_items = [row.line_item for row in result.material_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [
        row_to_table_dict(row, cfg.currency, places, _heading(cfg))
        for row in result.material_rows
    ]

    chips = []
    if result.material_rows:
        chips.append(f"Why {result.material_rows[0].line_item}?")
    chips.extend(["Unfavorable", "Favorable", "Export report"])

    return Response(
        text=f"**Material Variances** (Threshold: {format_threshold_amount(cfg.dollar_threshold, cfg.currency)}"
             f" or {format_threshold_pct(cfg.percent_threshold)})",
        table=table,
        chips=chips,
        phase=Phase.EXPLORING,
    )


def _handle_filter_status(session: Session, status: Status) -> Response:
    """Filter rows by favorable/unfavorable status."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    filtered = [row for row in _detail_rows(result) if row.status == status]
    label = status_label(status)

    if not filtered:
        return Response(
            text=f"No {label.lower()} variances found.",
            chips=["Material", "Summary"],
            phase=Phase.EXPLORING,
        )

    # Sort by absolute variance descending
    filtered.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    session.last_table_items = [row.line_item for row in filtered]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in filtered]

    chips = [f"Why {filtered[0].line_item}?"]
    if status == Status.UNFAVORABLE:
        chips.append("Favorable")
    else:
        chips.append("Unfavorable")
    chips.append("Material")

    return Response(
        text=f"**{label} Variances** ({len(filtered)} item{'s' if len(filtered) != 1 else ''})",
        table=table,
        chips=chips,
        phase=Phase.EXPLORING,
    )


def _handle_filter_type(session: Session, line_type: LineType) -> Response:
    """Filter rows by Revenue/Expense/Unclassified type."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    filtered = [row for row in _detail_rows(result) if row.line_type == line_type]

    if not filtered:
        return Response(
            text=f"No {line_type.value} rows found.",
            chips=["Material", "Summary"],
            phase=Phase.EXPLORING,
        )

    filtered.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    session.last_table_items = [row.line_item for row in filtered]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in filtered]

    return Response(
        text=f"**{line_type.value} Items** ({len(filtered)} row{'s' if len(filtered) != 1 else ''})",
        table=table,
        chips=["Material", "Summary", "Export report"],
        phase=Phase.EXPLORING,
    )


def _handle_top_n(session: Session, intent: ParsedIntent) -> Response:
    """Show top N variances by absolute amount."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    count = int(intent.captures.get("count", "5"))
    if count < 1:
        return Response(
            text="Please ask for at least 1 line, for example `top 3`.",
            chips=["Top 3", "Top 5", "Summary"],
            phase=Phase.EXPLORING,
        )

    kind = intent.captures.get("kind", "").lower()
    line_type = (
        LineType.EXPENSE if kind.startswith(("expense", "cost"))
        else LineType.REVENUE if kind.startswith(("revenue", "sales", "income"))
        else None
    )
    rows = [row for row in _detail_rows(result) if line_type is None or row.line_type == line_type]
    if not rows:
        return Response(
            text=f"No {line_type.value if line_type else 'line item'} rows found.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )
    count = min(count, len(rows))

    sorted_rows = sorted(rows, key=lambda r: abs(r.variance_dollars), reverse=True)
    top = sorted_rows[:count]
    session.last_table_items = [row.line_item for row in top]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in top]

    return Response(
        text=f"**Top {count} {line_type.value + ' ' if line_type else ''}Variances by Absolute Amount**",
        table=table,
        chips=[f"Why {top[0].line_item}?", "Material", "Summary"],
        phase=Phase.EXPLORING,
    )


def _rows_named(result: AnalysisResult, name: str) -> list[AnalyzedRow]:
    """Every row with this exact line-item name (a name can repeat, e.g. one per department)."""
    return [row for row in result.rows if row.line_item == name]


def _explain_lines(cfg: AnalysisConfig, row: AnalyzedRow, places: int) -> list[str]:
    """The driver-evidence answer for one row."""
    lines = [
        f"**Driver Evidence: {safe_inline(row.line_item)}**\n",
        f"{_heading(cfg)}: {format_money(row.budget, cfg.currency, places)}",
        f"Actual: {format_money(row.actual, cfg.currency, places)}",
        f"Variance: {format_money(row.variance_dollars, cfg.currency, places)} "
        f"({format_pct(row.budget, row.variance_dollars, row.percent_label)}, "
        f"{status_label(row.status)})\n",
    ]

    evidence = row.driver_evidence
    if evidence is not None and evidence.reconciles:
        lines.append(f"**Model:** {safe_inline(evidence.label)} decomposition reconciles.\n")
        for name, amount in evidence.components:
            lines.append(f"• **{safe_inline(name)}:** {format_money(amount, cfg.currency, places)}")
        lines.append("\nStatus: **Supported driver.**")
    elif evidence is not None and not evidence.reconciles:
        lines.append(
            f"**Status: Hypothesis (Unsupported).**\n\n"
            f"The supplied {safe_inline(evidence.label)} fields do not reconcile "
            f"to {_heading(cfg)}/Actual. Validate the driver data first."
        )
    else:
        likely_metrics = {
            "Revenue": "volume/units, price/rate, customer count, and mix",
            "Expense": "units/headcount, rate, vendor pricing, and timing",
        }.get(
            str(row.line_type),
            "an explicit Revenue/Expense classification plus operating driver metrics",
        )
        lines.append(
            f"**Status: No driver data provided.**\n\n"
            f"To support a causal claim, provide: {likely_metrics}."
        )
    return lines


def _explain_view(cfg: AnalysisConfig, row: AnalyzedRow, places: int) -> dict[str, object]:
    """The drill-down of `_explain_lines` as a view: the three figures, then the driver evidence."""
    word = status_label(row.status)
    figures = [
        figure(_plain_heading(cfg), format_money(row.budget, cfg.currency, places)),
        figure("Actual", format_money(row.actual, cfg.currency, places)),
        figure("Variance", format_money(row.variance_dollars, cfg.currency, places), None,
               format_pct(row.budget, row.variance_dollars, row.percent_label), word),
    ]
    evidence = row.driver_evidence
    sections: list[tuple[str, list[dict[str, str]]]] = []
    if evidence is not None and evidence.reconciles:
        sections.append((f"{evidence.label.capitalize()} decomposition reconciles",
                         [pair(name, format_money(amount, cfg.currency, places)) for name, amount in evidence.components]))
        notes = ["Supported driver."]
    elif evidence is not None:
        notes = [f"Hypothesis, not supported: the supplied {evidence.label} fields do not reconcile to "
                 f"{_plain_heading(cfg)} and Actual. Check the driver data first."]
    else:
        likely = {"Revenue": "volume or units, price or rate, customer count, and mix",
                  "Expense": "units or headcount, rate, vendor pricing, and timing"}.get(
            str(row.line_type), "a revenue or expense label plus operating driver figures")
        notes = [f"No driver data in the file. A breakdown needs {likely}."]
    return figures_view(f"Driver evidence: {row.line_item}", context=[pair("Type", str(row.line_type))],
                        figures=figures, sections=sections, notes=notes)


def _handle_explain(session: Session, intent: ParsedIntent) -> Response:
    """Explain the driver decomposition for a specific line item."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    raw_query = intent.captures.get("item", "")
    item_query = _resolve_item_query(raw_query, session)
    all_items = [row.line_item for row in result.rows]
    matches = find_line_item(item_query, all_items)
    if not matches and raw_query:
        named = _item_in_sentence(raw_query, all_items)  # "why is marketing over budget?"
        matches = [named] if named else []

    if not matches:
        display_q = safe_inline(raw_query or item_query or "unspecified item")
        return _not_found(display_q, item_query, all_items, "Why")

    if len(matches) > 1:
        chips = [f"Why {m}?" for m in matches[:5]]
        return Response(
            text="Multiple matches found. Which one?\n\n"
                 + "\n".join(f"• {safe_inline(m)}" for m in matches),
            chips=chips,
            phase=Phase.EXPLORING,
        )

    matched_name = matches[0]
    session.last_focused_item = matched_name
    named_rows = _rows_named(result, matched_name)

    sections = ["\n".join(_explain_lines(cfg, row, places)) for row in named_rows]
    lines = [sections[0]] if len(sections) == 1 else [
        f"{len(named_rows)} line items are named '{safe_inline(matched_name)}'; here is each one.\n",
        *[f"**Row {i} of {len(named_rows)}**\n\n{section}" for i, section in enumerate(sections, 1)],
    ]

    chips = ["Material", "Summary"]
    # Suggest explaining the next material item
    material_items = [r.line_item for r in result.material_rows]
    try:
        idx = material_items.index(matched_name)
        if idx + 1 < len(material_items):
            chips.insert(0, f"Why {material_items[idx + 1]}?")
    except ValueError:
        pass

    return Response(
        text="\n\n".join(lines),
        chips=chips,
        phase=Phase.EXPLORING,
        view=_explain_view(cfg, named_rows[0], places) if len(named_rows) == 1 else None,
    )


def _handle_detail(session: Session, intent: ParsedIntent) -> Response:
    """Show full detail for a specific line item."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    raw_query = intent.captures.get("item", "") or intent.captures.get("item2", "")
    item_query = _resolve_item_query(raw_query, session)
    all_items = [row.line_item for row in result.rows]
    matches = find_line_item(item_query, all_items)
    if not matches and raw_query:
        named = _item_in_sentence(raw_query, all_items)  # "details on how marketing is doing"
        matches = [named] if named else []

    if not matches:
        display_q = safe_inline(raw_query or item_query or "unspecified item")
        return _not_found(display_q, item_query, all_items, "Detail")

    if len(matches) > 1:
        chips = [f"Detail {m}" for m in matches[:5]]
        return Response(
            text="Multiple matches:\n" + "\n".join(f"• {safe_inline(m)}" for m in matches),
            chips=chips,
            phase=Phase.EXPLORING,
        )

    matched_name = matches[0]
    session.last_focused_item = matched_name
    named_rows = _rows_named(result, matched_name)
    if len(named_rows) > 1:
        return Response(
            text=f"{len(named_rows)} line items are named '{safe_inline(matched_name)}'; here is each one.",
            table=[row_to_table_dict(r, cfg.currency, places, _heading(cfg)) for r in named_rows],
            chips=[f"Why {matched_name}?", "Material", "Summary"],
            phase=Phase.EXPLORING,
        )
    row = named_rows[0]

    lines = [
        f"**{safe_inline(row.line_item)}**\n",
        f"• Type: {row.line_type}",
        f"• {_heading(cfg)}: {format_money(row.budget, cfg.currency, places)}",
        f"• Actual: {format_money(row.actual, cfg.currency, places)}",
        f"• Variance: {format_money(row.variance_dollars, cfg.currency, places)}",
        f"• Variance %: {format_pct(row.budget, row.variance_dollars, row.percent_label)}",
        f"• Status: {status_label(row.status)}",
        f"• Material: {'Yes' if row.material else 'No'}",
        f"• Classification Source: {row.classification_source}",
    ]

    if row.excluded_from_aggregation:
        lines.append("• Excluded from aggregation (summary/subtotal row)")

    return Response(
        text="\n".join(lines),
        chips=[f"Why {row.line_item}?", "Material", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_set_threshold(session: Session, intent: ParsedIntent) -> Response:
    """Re-run analysis with new materiality thresholds (supports partial adjustments)."""
    spec = intent.captures.get("spec", "")
    parsed = _parse_partial_threshold_text(spec)
    dollar_part, pct_part = parsed
    if dollar_part is None and pct_part is None:
        return Response(
            text="I couldn't parse those thresholds. Use: `threshold $10,000 or 5%`, "
                 "or adjust one: `threshold $25,000` or `threshold 8%`",
            chips=["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%"],
            phase=Phase.EXPLORING,
        )

    dollar = dollar_part if dollar_part is not None else session.dollar_threshold
    pct_ratio = pct_part if pct_part is not None else session.percent_threshold
    if dollar is None or pct_ratio is None:
        return Response(
            text="Materiality thresholds are not fully specified. Please enter both: `$10,000 or 5%`",
            chips=["$5,000 or 3%", "$10,000 or 5%"],
            phase=Phase.EXPLORING,
        )

    old_material = set(
        row.line_item for row in (session.result.material_rows if session.result else ())
    )

    session.dollar_threshold = dollar
    session.percent_threshold = pct_ratio

    response = _run_analysis(session)

    # Report what changed
    if session.result is not None:
        new_material = set(row.line_item for row in session.result.material_rows)
        entered = new_material - old_material
        exited = old_material - new_material

        changes = []
        if entered:
            changes.append("**Newly material:** " + ", ".join(safe_inline(i) for i in sorted(entered)))
        if exited:
            changes.append("**No longer material:** " + ", ".join(safe_inline(i) for i in sorted(exited)))
        if changes:
            response = replace(response, text=response.text + "\n\n" + "\n".join(changes))

    return response


def _handle_warnings(session: Session) -> Response:
    """Show data quality warnings."""
    result = session.result
    assert result is not None

    if not result.warnings:
        return Response(
            text="No data quality warnings.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )

    lines = ["**Data Quality Warnings:**\n"]
    for warning in result.warnings:
        lines.append(f"• {safe_inline(warning)}")

    return Response(
        text="\n".join(lines),
        chips=["Summary", "Material"],
        phase=Phase.EXPLORING,
    )


def _handle_recommendations(session: Session) -> Response:
    """Show strategic recommendations based on material variances."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    lines = ["**Strategic Recommendations**\n"]

    # Mitigation (largest unfavorable)
    unfavorable = next(
        (row for row in result.material_rows if row.status == Status.UNFAVORABLE), None,
    )
    if unfavorable:
        evidence = unfavorable.driver_evidence
        if evidence and evidence.reconciles:
            largest_component = max(evidence.components, key=lambda pair: abs(pair[1]))
            if largest_component[0] == "Unexplained residual":
                lines.append(
                    f"• **Mitigation:** Reconcile the unexplained residual for "
                    f"{safe_inline(unfavorable.line_item)} before assigning a cause-specific action."
                )
            else:
                lines.append(
                    f"• **Mitigation:** Focus {_action_plan(cfg)} for {safe_inline(unfavorable.line_item)} "
                    f"on its {safe_inline(largest_component[0].lower())} "
                    f"({format_money(largest_component[1], cfg.currency, places)}), "
                    f"the largest reconciled component."
                )
        else:
            lines.append(
                f"• **Mitigation:** {safe_inline(unfavorable.line_item)} is the largest material "
                f"unfavorable variance, but the dataset does not support a causal corrective action; "
                f"obtain the missing operating driver data first."
            )
    else:
        lines.append("• **Mitigation:** No material unfavorable variance is available.")

    # Optimization (largest favorable)
    favorable = next(
        (row for row in result.material_rows if row.status == Status.FAVORABLE), None,
    )
    if favorable:
        evidence = favorable.driver_evidence
        if evidence and evidence.reconciles:
            largest_component = max(evidence.components, key=lambda pair: abs(pair[1]))
            lines.append(
                f"• **Optimization:** Focus {_action_plan(cfg)} for {safe_inline(favorable.line_item)} "
                f"on its {safe_inline(largest_component[0].lower())} "
                f"({format_money(largest_component[1], cfg.currency, places)}), "
                f"the largest reconciled component."
            )
        else:
            lines.append(
                f"• **Optimization:** {safe_inline(favorable.line_item)} is the largest material "
                f"favorable variance; obtain driver data to validate the cause."
            )
    else:
        lines.append("• **Optimization:** No material favorable variance is available.")

    # Data request
    missing_drivers = [
        safe_inline(row.line_item)
        for row in result.material_rows
        if not (row.driver_evidence and row.driver_evidence.reconciles)
    ]
    if missing_drivers:
        lines.append(
            f"• **Data Request:** Provide reconciled operating driver metrics for: "
            f"{', '.join(missing_drivers)}."
        )
    else:
        lines.append(
            "• **Data Request:** No additional driver data is required for the analyzed "
            "top material variances."
        )

    return Response(
        text="\n".join(lines),
        chips=["Summary", "Material", "Export report"],
        phase=Phase.EXPLORING,
    )


def _handle_totals(session: Session) -> Response:
    """Show Revenue and Expense aggregate totals."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    lines = ["**Aggregate Totals**\n"]

    has_revenue = any(
        row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
        for row in result.rows
    )
    has_expenses = any(
        row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
        for row in result.rows
    )

    if has_revenue:
        rev = result.revenue
        lines.append(
            f"• **Revenue:** {format_money(rev.actual, cfg.currency, places)} actual vs. "
            f"{format_money(rev.budget, cfg.currency, places)} {_noun(cfg)} = "
            f"{format_money(rev.variance_dollars, cfg.currency, places)} "
            f"({format_pct(rev.budget, rev.variance_dollars, rev.percent_label)}, "
            f"{status_label(rev.status)})"
        )
    else:
        lines.append("• **Revenue:** N/A (no Revenue rows)")

    if has_expenses:
        exp = result.expenses
        lines.append(
            f"• **Expenses:** {format_money(exp.actual, cfg.currency, places)} actual vs. "
            f"{format_money(exp.budget, cfg.currency, places)} {_noun(cfg)} = "
            f"{format_money(exp.variance_dollars, cfg.currency, places)} "
            f"({format_pct(exp.budget, exp.variance_dollars, exp.percent_label)}, "
            f"{status_label(exp.status)})"
        )
    else:
        lines.append("• **Expenses:** N/A (no Expense rows)")

    return Response(
        text="\n".join(lines),
        chips=["Summary", "Material", "Net impact"],
        phase=Phase.EXPLORING,
    )


def _handle_full_report(session: Session) -> Response:
    """Show the full Markdown report inline."""
    result = session.result
    assert result is not None

    report = render_markdown(result)
    return Response(
        text=report,
        chips=["Export report", "Export excel", "Export audit"],
        phase=Phase.EXPLORING,
    )


def _export_response(
    session: Session, intent: ParsedIntent, content: str | bytes, filename: str, *,
    written: str, ready: str, retry_chip: str, written_chips: list[str], ready_chips: list[str],
) -> Response:
    """Write an export to the path the user named, or hand it over as a download.

    A path is only honoured where the deployment allows it (not on the hosted server).
    """
    path = _export_path(intent)
    if path and not session.path_exports_enabled:
        return _path_export_disabled(path, intent)
    if path:
        try:
            write_text_outputs({Path(path): content})
            return Response(
                text=f"{written} written to `{safe_inline(path)}`.",
                chips=written_chips,
                phase=Phase.EXPLORING,
            )
        except (ValueError, OSError) as exc:
            return Response(
                text=f"Could not write to '{safe_inline(path)}': {display_text(str(exc))}",
                chips=[retry_chip],
                phase=Phase.EXPLORING,
                level="error",
            )
    return Response(
        text=ready,
        download={filename: content},
        chips=ready_chips,
        phase=Phase.EXPLORING,
    )


def _period_slug(period: str) -> str:
    """The period as a file-name fragment: letters, digits, '-' and '_' only."""
    return re.sub(r"[^a-z0-9-]+", "_", normalize_for_routing(period).lower()).strip("_") or "period"


_PATH_CHARACTERS = re.compile(r"[/\\.~]")


def _export_path(intent: ParsedIntent) -> str | None:
    """The file path an export asked for, if the words after 'export report' are one.

    "download report now" names no file; a path has a separator, an extension or a '~'.
    """
    path = intent.captures.get("path", "").strip().strip("'\"`")
    return path if path and _PATH_CHARACTERS.search(path) else None


def _path_export_disabled(path: str, intent: ParsedIntent) -> Response:
    """Refuse a server-side write on hosted deployments and point to the download."""
    chip = {
        "export_audit": "Export audit", "export_csv": "Export csv", "export_xlsx": "Export excel",
    }.get(
        intent.intent_id, "Export report"
    )
    return Response(
        text=(f"Saving to `{safe_inline(path)}` is turned off on this hosted version. "
              f"Use **{chip}** to download the file instead."),
        chips=[chip],
        phase=Phase.EXPLORING,
        level="error",
    )


def _handle_export_report(session: Session, intent: ParsedIntent) -> Response:
    """Generate the Markdown report for download."""
    result = session.result
    assert result is not None

    report = render_markdown(result)
    period_slug = _period_slug(result.config.period)
    filename = f"variance_report_{period_slug}.md"

    return _export_response(
        session, intent, report, filename,
        written="Report", ready="Markdown report ready for download.", retry_chip="Export report",
        written_chips=["Export audit", "Summary"], ready_chips=["Export excel", "Export audit", "Summary"],
    )


def _handle_export_audit(session: Session, intent: ParsedIntent) -> Response:
    """Generate the audit JSON for download."""
    result = session.result
    assert result is not None

    source_hash = sha256_bytes(session.source_bytes) if session.source_bytes else None
    transformations: dict[str, object] | None = None
    if session.intake_result is not None:
        # A mapping saved for an earlier file, sheet or comparison no longer describes this audit.
        saved = session.layout_mapping
        mapping = saved if saved is not None and saved == _layout_mapping_for(session) else None
        transformations = audit_transformations(session.intake_result, mapping)
    record = build_audit_record(
        result,
        source_name=session.source_name,
        source_sha256=source_hash,
        source_worksheet=session.worksheet,
        transformations=transformations,
        source_document=(session.intake_result.source_document()
                         if session.intake_result is not None else None),
    )
    audit_json = serialize_audit_json(record)
    period_slug = _period_slug(result.config.period)
    filename = f"variance_audit_{period_slug}.json"

    return _export_response(
        session, intent, audit_json, filename,
        written="Audit JSON", ready="Audit JSON ready for download.", retry_chip="Export audit",
        written_chips=["Export report", "Summary"], ready_chips=["Export report", "Summary"],
    )


_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def _csv_text(value: str) -> str:
    """Keep a text cell from being run as a formula when the CSV is opened in a spreadsheet.

    Applied to label cells only; the numeric columns are written as numbers ('-100' stays one).
    """
    return f"'{value}" if value.startswith(_FORMULA_STARTS) else value


def _handle_export_csv(session: Session, intent: ParsedIntent) -> Response:
    """Generate RFC 4180 compliant CSV export of the analysis data rows."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow([
        "Line Item",
        "Type",
        f"{comparison_heading(cfg.comparison_basis, cfg.comparison_label)} ({cfg.currency})",
        f"Actual ({cfg.currency})",
        f"Variance ({cfg.currency})",
        "Variance (%)",
        "Status",
        "Material",
        "Excluded From Aggregation",
        "Classification Source",
        "Driver Evidence",
    ])

    for row in result.rows:
        driver_desc = ""
        if row.driver_evidence:
            comp_str = "; ".join(
                f"{k}: {format_money(v, cfg.currency, places)}"
                for k, v in row.driver_evidence.components
            )
            rec_str = "Reconciles" if row.driver_evidence.reconciles else "Unreconciled"
            driver_desc = f"{row.driver_evidence.label} ({rec_str}): {comp_str}"

        writer.writerow([
            _csv_text(row.line_item),
            row.line_type.value,
            str(row.budget),
            str(row.actual),
            str(row.variance_dollars),
            format_pct(row.budget, row.variance_dollars, row.percent_label),
            row.status.value,
            "Yes" if row.material else "No",
            "Yes" if row.excluded_from_aggregation else "No",
            _csv_text(row.classification_source),
            _csv_text(driver_desc),
        ])

    csv_text = output.getvalue()
    period_slug = _period_slug(result.config.period)
    filename = f"variance_data_{period_slug}.csv"

    return _export_response(
        session, intent, csv_text, filename,
        written="Analysis CSV", ready="Analysis CSV ready for download.", retry_chip="Export csv",
        written_chips=["Export report", "Export audit", "Summary"], ready_chips=["Export excel", "Export report", "Summary"],
    )


def _handle_export_xlsx(session: Session, intent: ParsedIntent) -> Response:
    """Generate the formatted Excel workbook for download."""
    result = session.result
    assert result is not None

    workbook = render_xlsx(result)
    period_slug = _period_slug(result.config.period)
    filename = f"variance_workbook_{period_slug}.xlsx"

    return _export_response(
        session, intent, workbook, filename,
        written="Excel workbook", ready=("Excel workbook ready for download: Summary, Material Variances, "
              "Root Causes & Actions, and All Rows sheets."), retry_chip="Export excel",
        written_chips=["Export report", "Export audit", "Summary"], ready_chips=["Export report", "Export audit", "Summary"],
    )


def _handle_knowledge(session: Session, intent_id: str) -> Response:
    """Answer financial domain questions with FP&A precision."""
    text = _KNOWLEDGE_TEXTS.get(intent_id, knowledge.explain_variance_analysis)()

    # If currently in a guided setup phase, provide a helpful prompt to continue
    chips = ["Summary", "Material", "Biggest risks", "Help"]
    if session.phase == Phase.AWAITING_FILE:
        text += (
            "\n\n---\n"
            "**Next:** Upload your financial file (CSV, JSON, XLSX, XLSM or a PDF filing) "
            "with the drop zone above."
        )
        chips = ["Supported file formats", "What is materiality?"]
    elif session.phase == Phase.AWAITING_PERIOD:
        text += (
            "\n\n---\n"
            f"**Next:** What reporting period does '{safe_inline(session.source_name or 'your file')}' cover? "
            "(e.g., `Q3 2026`, `October 2026`, `FY2026`)"
        )
        chips = ["Q3 2026", "FY2026", "October 2026"]
    elif session.phase == Phase.AWAITING_THRESHOLDS:
        text += (
            "\n\n---\n"
            "**Next:** Enter your materiality thresholds (for example `$10,000 or 5%`), or choose a preset below."
        )
        chips = ["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%", "$50,000 or 15%"]
    elif session.phase == Phase.AWAITING_CURRENCY:
        text += (
            "\n\n---\n"
            "**Next:** What is the reporting currency for this analysis?"
        )
        chips = ["USD", "EUR", "GBP"]
    elif session.phase == Phase.RESOLVE_UNCLASSIFIED:
        current_item = safe_inline(session.unclassified_queue[0]) if session.unclassified_queue else ""
        text += (
            "\n\n---\n"
            f"**Next:** Classify '{current_item}': is it Revenue, Expense or Skip?"
        )
        chips = ["Revenue", "Expense", "Skip", "Skip all"]

    return Response(text=text, chips=chips, phase=session.phase)


def _handle_biggest_risks(session: Session) -> Response:
    """Identify the top material unfavorable variances and mitigation paths."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    unfavorable = [
        row for row in result.material_rows if row.status == Status.UNFAVORABLE
    ]
    session.last_table_items = [row.line_item for row in unfavorable]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not unfavorable:
        return Response(
            text="**No Material Risks Detected**\n\n"
                 "There are zero material unfavorable variances exceeding your thresholds "
                 f"({format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or "
                 f"{format_threshold_pct(cfg.percent_threshold)}). "
                 + ("All revenue targets and expense allocations " if _is_budget(cfg)
                    else "All revenue and expense lines ")
                 + f"performed within {_noun(cfg)} tolerance.",
            chips=["Summary", "Biggest wins", "Show all material"],
            phase=Phase.EXPLORING,
        )

    lines = [
        f"**Top Financial Risks ({len(unfavorable)} material unfavorable item{'s' if len(unfavorable) != 1 else ''})**\n\n"
        f"These line items represent the most significant negative deviations from {_noun(cfg)}:\n"
    ]

    for i, row in enumerate(unfavorable[:3], start=1):
        driver_status = "No driver breakdown"
        if row.driver_evidence is not None:
            driver_status = "Supported causal model" if row.driver_evidence.reconciles else "Hypothesis (unreconciled)"

        type_label = "Revenue shortfall" if row.line_type == LineType.REVENUE else "Cost overrun"
        lines.append(
            f"**{i}. {safe_inline(row.line_item)}** ({type_label})\n"
            f"• Actual: {format_money(row.actual, cfg.currency, places)} vs. {_heading(cfg)}: {format_money(row.budget, cfg.currency, places)}\n"
            f"• Variance: **{format_money(row.variance_dollars, cfg.currency, places)}** ({format_pct(row.budget, row.variance_dollars, row.percent_label)})\n"
            f"• Evidence: *{driver_status}*\n"
        )

    lines.append(
        f"The largest is **{safe_inline(unfavorable[0].line_item)}**. "
        f"Ask `why {safe_inline(unfavorable[0].line_item)}` to see what drove it."
    )

    chips = [f"Why {unfavorable[0].line_item}?"]
    if len(unfavorable) > 1:
        chips.append(f"Why {unfavorable[1].line_item}?")
    chips.extend(["Drivers", "Summary"])

    shown = unfavorable[:3]
    count = f"{len(unfavorable)} material unfavorable variance{'s' if len(unfavorable) != 1 else ''}"
    view = figures_view(
        "Top financial risks",
        context=[pair("Compared with", _plain_heading(cfg))],
        notes=[f"The largest is {unfavorable[0].line_item}. Ask \u201cwhy {unfavorable[0].line_item}\u201d to see what drove it."],
        table_title=count.capitalize() + (f", the largest {len(shown)} shown" if len(unfavorable) > len(shown) else ""),
    )
    table = [row_to_table_dict(row, cfg.currency, places, _heading(cfg)) for row in shown]
    return Response(text="\n".join(lines), table=table, chips=chips, phase=Phase.EXPLORING, view=view)


def _handle_biggest_wins(session: Session) -> Response:
    """Highlight the largest material favorable variances."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    favorable = [
        row for row in result.material_rows if row.status == Status.FAVORABLE
    ]
    session.last_table_items = [row.line_item for row in favorable]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not favorable:
        return Response(
            text="**No Material Favorable Variances**\n\n"
                 "No line items exceeded the favorable materiality thresholds. "
                 "Check `summary` or lower thresholds with `threshold $X or Y%` to explore smaller variances.",
            chips=["Summary", "Biggest risks", "Material"],
            phase=Phase.EXPLORING,
        )

    lines = [
        f"**Top Positive Performers ({len(favorable)} material favorable item{'s' if len(favorable) != 1 else ''})**\n\n"
        "These line items drove the strongest positive operating performance:\n"
    ]

    for i, row in enumerate(favorable[:3], start=1):
        nature = "Revenue beat" if row.line_type == LineType.REVENUE else "Cost savings / underspend"
        lines.append(
            f"**{i}. {safe_inline(row.line_item)}** ({nature})\n"
            f"• Actual: {format_money(row.actual, cfg.currency, places)} vs. {_heading(cfg)}: {format_money(row.budget, cfg.currency, places)}\n"
            f"• Favorable Variance: **{format_money(row.variance_dollars, cfg.currency, places)}** ({format_pct(row.budget, row.variance_dollars, row.percent_label)})\n"
        )

    lines.append(f"**Note:** An expense below {_noun(cfg)} can be a lasting saving or spending that moves to a later period; the figures alone do not say which.")

    chips = [f"Why {favorable[0].line_item}?", "Summary", "Biggest risks"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_revenue_status(session: Session) -> Response:
    """Analyze revenue performance against budget target."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    revenue_rows = [
        r for r in _detail_rows(result)
        if r.line_type == LineType.REVENUE and not r.excluded_from_aggregation
    ]
    session.last_table_items = [row.line_item for row in revenue_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not revenue_rows:
        return Response(
            text="No classified Revenue rows exist in this dataset.",
            chips=["Summary", "Expenses"],
            phase=Phase.EXPLORING,
        )

    if any(r.line_type == LineType.UNCLASSIFIED for r in result.rows):
        return Response(
            text="Total revenue cannot be certified because there are still unclassified line items. Classify them first.",
            chips=["Unclassified", "Summary"],
            phase=Phase.EXPLORING,
            level="error",
        )

    rev = result.revenue
    beat = rev.actual >= rev.budget
    diff = rev.actual - rev.budget

    pct_text = format_pct(rev.budget, rev.variance_dollars, rev.percent_label)
    if beat:
        achieved = "Revenue Target Achieved" if _is_budget(cfg) else f"Revenue Ahead of {_heading(cfg)}"
        verdict = f"**{achieved}: Beat {_heading(cfg)} by {format_money(diff, cfg.currency, places)} ({pct_text})**"
    else:
        missed = "Revenue Target Missed" if _is_budget(cfg) else f"Revenue Behind {_heading(cfg)}"
        verdict = f"**{missed}: Shortfall of {format_money(abs(diff), cfg.currency, places)} ({pct_text})**"

    lines = [
        verdict + "\n",
        f"• **{_planned(cfg)} Revenue:** {format_money(rev.budget, cfg.currency, places)}",
        f"• **Actual Revenue:** {format_money(rev.actual, cfg.currency, places)}",
    ]
    if rev.budget > 0:
        rate = ratio(rev.actual, rev.budget) * Decimal("100")
        lines.append(f"• **Achievement Rate:** {rate:.1f}% of {_noun(cfg)}")
    elif rev.budget < 0:
        lines.append(f"• **Achievement Rate:** N/A (the {_noun(cfg)} is negative, so a ratio is not meaningful)")
    lines.append(f"• **Status:** {status_label(rev.status)}\n")
    lines.append("**Revenue Breakdown:**")

    for row in revenue_rows:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** {format_money(row.actual, cfg.currency, places)} vs. "
            f"{format_money(row.budget, cfg.currency, places)} "
            f"({format_money(row.variance_dollars, cfg.currency, places)}, {status_label(row.status)})"
        )

    chips = ["Expenses", "Summary", "Show all revenue"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_expense_status(session: Session) -> Response:
    """Analyze expense performance against budget allocation."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    expense_rows = [
        r for r in _detail_rows(result)
        if r.line_type == LineType.EXPENSE and not r.excluded_from_aggregation
    ]
    session.last_table_items = [row.line_item for row in expense_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not expense_rows:
        return Response(
            text="No classified Expense rows exist in this dataset.",
            chips=["Summary", "Revenue"],
            phase=Phase.EXPLORING,
        )

    if any(r.line_type == LineType.UNCLASSIFIED for r in result.rows):
        return Response(
            text="Total expenses cannot be certified because there are still unclassified line items.",
            chips=["Unclassified", "Summary"],
            phase=Phase.EXPLORING,
            level="error",
        )

    exp = result.expenses
    under_budget = exp.actual <= exp.budget
    diff = exp.actual - exp.budget

    if under_budget:
        verdict = f"**Expenses Remained Under {_heading(cfg)}: Saved {format_money(abs(diff), cfg.currency, places)} ({format_pct(exp.budget, exp.variance_dollars, exp.percent_label)})**"
    else:
        verdict = f"**Expenses Exceeded {_heading(cfg)}: Overspend of {format_money(diff, cfg.currency, places)} ({format_pct(exp.budget, exp.variance_dollars, exp.percent_label)})**"

    lines = [
        verdict + "\n",
        f"• **{_planned(cfg)} Expenses:** {format_money(exp.budget, cfg.currency, places)}",
        f"• **Actual Expenses:** {format_money(exp.actual, cfg.currency, places)}",
    ]
    utilization = "Budget Utilization" if _is_budget(cfg) else f"Spend vs. {_heading(cfg)}"
    if exp.budget > 0:
        burn = ratio(exp.actual, exp.budget) * Decimal("100")
        lines.append(f"• **{utilization}:** {burn:.1f}%")
    elif exp.budget < 0:
        lines.append(f"• **{utilization}:** N/A (the {_noun(cfg)} is negative, so a ratio is not meaningful)")
    lines.append(f"• **Status:** {status_label(exp.status)}\n")

    overspent = sorted(
        (r for r in expense_rows if r.actual > r.budget),
        key=lambda r: r.variance_dollars, reverse=True,
    )
    if overspent:
        over_heading = "Over-Budget Accounts" if _is_budget(cfg) else f"Accounts Over {_heading(cfg)}"
        lines.append(f"**{over_heading}:**")
        for row in overspent[:5]:
            lines.append(
                f"• **{safe_inline(row.line_item)}:** {format_money(row.variance_dollars, cfg.currency, places)} over "
                f"({format_pct(row.budget, row.variance_dollars, row.percent_label)})"
            )
    else:
        lines.append(
            "All expense accounts operated at or below planned budgets."
            if _is_budget(cfg)
            else f"All expense accounts operated at or below the {_noun(cfg)}."
        )

    chips = ["Revenue", "Summary", "Biggest risks"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_budget_utilization(session: Session) -> Response:
    """Compute overall budget execution and spend velocity."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    noun = _noun(cfg)
    if _is_budget(cfg):
        title = "Budget Execution & Utilization Metrics"
        utilization = "Expense Budget Utilization"
        zero_note = "zero budgeted expenses"
    else:
        title = f"Spend vs. {_heading(cfg)} Metrics"
        utilization = f"Expense Spend vs. {_heading(cfg)}"
        zero_note = f"zero {noun} expenses"
    lines = [f"**{title}**\n"]

    if result.expenses.budget < 0:
        lines.append(f"• **{utilization}:** N/A (negative {noun} expenses; a utilization ratio is not meaningful)")
    elif result.expenses.budget != 0:
        util = ratio(result.expenses.actual, result.expenses.budget) * Decimal("100")
        diff = result.expenses.actual - result.expenses.budget
        status_text = f"over {noun} by {format_money(diff, cfg.currency, places)}" if diff > 0 else f"under {noun} by {format_money(abs(diff), cfg.currency, places)}"
        lines.append(f"• **{utilization}:** **{util:.1f}%** ({status_text})")
    else:
        lines.append(f"• **{utilization}:** N/A ({zero_note})")

    if result.revenue.budget > 0:
        achieve = ratio(result.revenue.actual, result.revenue.budget) * Decimal("100")
        diff = result.revenue.actual - result.revenue.budget
        status_text = f"beat by {format_money(diff, cfg.currency, places)}" if diff >= 0 else f"shortfall of {format_money(abs(diff), cfg.currency, places)}"
        achievement = "Revenue Target Achievement" if _is_budget(cfg) else f"Revenue vs. {_heading(cfg)}"
        lines.append(f"• **{achievement}:** **{achieve:.1f}%** ({status_text})")

    has_rev = any(r.line_type == LineType.REVENUE and not r.excluded_from_aggregation for r in result.rows)
    has_exp = any(r.line_type == LineType.EXPENSE and not r.excluded_from_aggregation for r in result.rows)
    classification_incomplete = any(r.line_type == LineType.UNCLASSIFIED for r in result.rows)

    if has_rev and has_exp and not classification_incomplete:
        impact = result.revenue.variance_dollars - result.expenses.variance_dollars
        direction = f"above {noun}" if impact > 0 else f"below {noun}" if impact < 0 else f"in line with {noun}"
        lines.append(
            f"• **Net Operating Impact:** {format_money(impact, cfg.currency, places)} ({direction})"
        )

    chips = ["Summary", "Biggest risks", "Biggest wins"]
    return Response(text=_with_unclassified_note("\n".join(lines), result), chips=chips, phase=Phase.EXPLORING)


def _handle_top_percent(session: Session) -> Response:
    """Show line items sorted by largest percentage variance."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    pct_rows = [r for r in _detail_rows(result) if r.variance_percent is not None]
    if not pct_rows:
        return Response(
            text=(
                "No line items with non-zero budgets were found."
                if _is_budget(cfg)
                else f"No line items with a non-zero {_noun(cfg)} were found."
            ),
            chips=["Summary"],
            phase=Phase.EXPLORING,
        )

    pct_rows.sort(key=lambda r: abs(r.variance_percent or Decimal(0)), reverse=True)
    session.last_table_items = [row.line_item for row in pct_rows[:5]]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [
        row_to_table_dict(row, cfg.currency, places, _heading(cfg))
        for row in pct_rows[:5]
    ]

    return Response(
        text="**Top Line Items by Percentage Variance** (Largest relative swings):\n",
        table=table,
        chips=["Material", "Top 3 by dollars", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_metrics_count(session: Session) -> Response:
    """Return a quantitative breakdown of line items and materiality."""
    result = session.result
    assert result is not None

    rows = _detail_rows(result)
    total_rows = len(rows)
    mat_rows = len(result.material_rows)
    mat_pct = (mat_rows / total_rows * 100) if total_rows > 0 else 0

    f_count = sum(1 for r in rows if r.status == Status.FAVORABLE)
    u_count = sum(1 for r in rows if r.status == Status.UNFAVORABLE)
    n_count = sum(1 for r in rows if r.status == Status.NEUTRAL)

    rev_count = sum(1 for r in rows if r.line_type == LineType.REVENUE)
    exp_count = sum(1 for r in rows if r.line_type == LineType.EXPENSE)
    unc_count = sum(1 for r in rows if r.line_type == LineType.UNCLASSIFIED)

    lines = [
        "**Portfolio Metrics Breakdown**\n",
        f"• **Total Line Items:** {total_rows}",
        f"• **Material Variances:** {mat_rows} ({mat_pct:.1f}% of total items)",
        f"• **Direction:** {f_count} Favorable, {u_count} Unfavorable, {n_count} Neutral",
        f"• **Classification:** {rev_count} Revenue, {exp_count} Expense, {unc_count} Unclassified",
        f"• **Data Warnings:** {len(result.warnings)} issue{'s' if len(result.warnings) != 1 else ''}",
    ]

    chips = ["Material", "Summary", "Biggest risks"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_compare(session: Session, intent: ParsedIntent) -> Response:
    """Compare two line items side-by-side."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    line_items = [r.line_item for r in result.rows]

    name1 = intent.captures.get("item1", "").strip().strip("'\"?")
    name2 = intent.captures.get("item2", "").strip().strip("'\"?")
    name1_lower = name1.lower()
    name2_lower = name2.lower()

    # Macro Case 1: Actual vs Budget
    actual_terms = {"actual", "actuals", "act"}
    budget_terms = {"budget", "budgeted", "plan", "target", "targets", "bgt"}
    if (name1_lower in actual_terms and name2_lower in budget_terms) or (name1_lower in budget_terms and name2_lower in actual_terms):
        with financial_context() as context:
            context.traps[Inexact] = False
            base_profit = result.revenue.budget - result.expenses.budget
            actual_profit = result.revenue.actual - result.expenses.actual
            net_impact = actual_profit - base_profit
            rev_var = result.revenue.actual - result.revenue.budget
            exp_var = result.expenses.actual - result.expenses.budget
            sym = CURRENCY_SYMBOLS.get(cfg.currency, "$")

            macro_table = [
                {
                    "Metric": "Total Revenue",
                    _heading(cfg): format_money(result.revenue.budget, cfg.currency, places),
                    "Actual": format_money(result.revenue.actual, cfg.currency, places),
                    f"Variance ({sym})": format_money(rev_var, cfg.currency, places),
                    "Variance (%)": _pct_text(_variance_percent(rev_var, result.revenue.budget), "+.1f"),
                    "Status": "F" if rev_var >= 0 else "U",
                },
                {
                    "Metric": "Total Expenses",
                    _heading(cfg): format_money(result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(result.expenses.actual, cfg.currency, places),
                    f"Variance ({sym})": format_money(exp_var, cfg.currency, places),
                    "Variance (%)": _pct_text(_variance_percent(exp_var, result.expenses.budget), "+.1f"),
                    "Status": "F" if exp_var <= 0 else "U",
                },
                {
                    "Metric": "Operating Profit",
                    _heading(cfg): format_money(base_profit, cfg.currency, places),
                    "Actual": format_money(actual_profit, cfg.currency, places),
                    f"Variance ({sym})": format_money(net_impact, cfg.currency, places),
                    "Variance (%)": f"{(ratio(net_impact, abs(base_profit)) * 100):+.1f}%" if base_profit != 0 else "N/A",
                    "Status": "F" if net_impact >= 0 else "U",
                },
            ]
        status_word = "beat" if net_impact >= 0 else "shortfall"
        target = "budget target" if _is_budget(cfg) else _noun(cfg)
        return Response(
            text=_with_unclassified_note(
                f"**Executive Macro Comparison: Actual vs. {_heading(cfg)}**\n\n"
                f"Operating profit finished at **{format_money(actual_profit, cfg.currency, places)}**, representing a "
                f"**{format_money(abs(net_impact), cfg.currency, places)} {status_word}** against the {target} of "
                f"{format_money(base_profit, cfg.currency, places)}.", result),
            table=macro_table,
            chips=["Waterfall", "Run rate", "Sensitivity", "Summary"],
            phase=Phase.EXPLORING,
        )

    # Macro Case 2: Revenue vs Expenses
    rev_terms = {"revenue", "revenues", "sales", "topline", "top line", "rev"}
    exp_terms = {"expense", "expenses", "cost", "costs", "spend", "opex", "exp"}
    if (name1_lower in rev_terms and name2_lower in exp_terms) or (name1_lower in exp_terms and name2_lower in rev_terms):
        with financial_context() as context:
            context.traps[Inexact] = False
            actual_profit = result.revenue.actual - result.expenses.actual
            margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else None
            cost_ratio = (ratio(result.expenses.actual, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else None

            macro_table = [
                {
                    "Category": "Total Revenue",
                    _heading(cfg): format_money(result.revenue.budget, cfg.currency, places),
                    "Actual": format_money(result.revenue.actual, cfg.currency, places),
                    "Operating Flow": "Top-Line Inflow",
                    "% of Revenue": "100.0%" if result.revenue.actual != 0 else "N/A",
                },
                {
                    "Category": "Total Expenses",
                    _heading(cfg): format_money(result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(result.expenses.actual, cfg.currency, places),
                    "Operating Flow": "Operating Outflow",
                    "% of Revenue": _pct_text(cost_ratio),
                },
                {
                    "Category": "Operating Profit",
                    _heading(cfg): format_money(result.revenue.budget - result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(actual_profit, cfg.currency, places),
                    "Operating Flow": "Net Retained Margin",
                    "% of Revenue": _pct_text(margin),
                },
            ]
        return Response(
            text=_with_unclassified_note(
                f"**Macro Financial Comparison: Revenue vs. Expenses**\n\n"
                f"Actual Revenue of **{format_money(result.revenue.actual, cfg.currency, places)}** offset by Operating Expenses of "
                f"**{format_money(result.expenses.actual, cfg.currency, places)}** yields an **Operating Profit of {format_money(actual_profit, cfg.currency, places)}** "
                f"({_pct_text(margin)} operating margin; cost-to-income ratio of {_pct_text(cost_ratio)}).", result),
            table=macro_table,
            chips=["Waterfall", "Run rate", "Sensitivity", "Summary"],
            phase=Phase.EXPLORING,
        )

    matches1 = find_line_item(_resolve_item_query(name1, session), line_items)
    matches2 = find_line_item(_resolve_item_query(name2, session), line_items)

    if not matches1:
        return Response(
            text=f"Could not find a line item matching '{safe_inline(name1)}'.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )
    if not matches2:
        return Response(
            text=f"Could not find a line item matching '{safe_inline(name2)}'.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )

    if len(matches1) > 1:
        return Response(
            text=f"Multiple matches for '{safe_inline(name1)}': {', '.join(matches1)}. Please be more specific.",
            chips=["Summary"],
            phase=Phase.EXPLORING,
        )
    if len(matches2) > 1:
        return Response(
            text=f"Multiple matches for '{safe_inline(name2)}': {', '.join(matches2)}. Please be more specific.",
            chips=["Summary"],
            phase=Phase.EXPLORING,
        )

    row1 = next(r for r in result.rows if r.line_item == matches1[0])
    row2 = next(r for r in result.rows if r.line_item == matches2[0])
    session.last_table_items = [row1.line_item, row2.line_item]
    session.last_focused_item = row1.line_item

    if row1.line_item == row2.line_item:
        table = [row_to_table_dict(row1, cfg.currency, places, _heading(cfg))]
        return Response(
            text=f"Comparing '**{safe_inline(row1.line_item)}**' against itself. Account details:",
            table=table,
            chips=[f"Why {row1.line_item}?", "Summary"],
            phase=Phase.EXPLORING,
        )

    table = [
        row_to_table_dict(row1, cfg.currency, places, _heading(cfg)),
        row_to_table_dict(row2, cfg.currency, places, _heading(cfg)),
    ]

    diff_var = abs(row1.variance_dollars) - abs(row2.variance_dollars)
    if diff_var > 0:
        lead = f"**{safe_inline(row1.line_item)}** has the larger absolute variance swing by {format_money(diff_var, cfg.currency, places)}."
    elif diff_var < 0:
        lead = f"**{safe_inline(row2.line_item)}** has the larger absolute variance swing by {format_money(abs(diff_var), cfg.currency, places)}."
    else:
        lead = "Both line items have identical absolute variance swings."

    return Response(
        text=f"**Side-by-Side Comparison: {safe_inline(row1.line_item)} vs. {safe_inline(row2.line_item)}**\n\n{lead}",
        table=table,
        chips=[f"Why {row1.line_item}?", f"Why {row2.line_item}?", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_concentration(session: Session) -> Response:
    """Analyze variance concentration using Pareto distribution (80/20 rule)."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    with financial_context():
        total_abs_var = sum((abs(r.variance_dollars) for r in _detail_rows(result)), Decimal(0))

    if total_abs_var == Decimal(0):
        return Response(
            text=f"**Zero Variance Volatility:** All line items performed exactly to {_noun(cfg)}.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )

    # Sort rows by absolute variance descending
    sorted_rows = sorted(_detail_rows(result), key=lambda r: abs(r.variance_dollars), reverse=True)
    top_3 = sorted_rows[:3]
    session.last_table_items = [row.line_item for row in top_3]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    with financial_context():
        top_3_abs = sum((abs(r.variance_dollars) for r in top_3), Decimal(0))
        top_3_pct = ratio(top_3_abs, total_abs_var) * Decimal("100")

    lines = [
        "**Variance Concentration Analysis (Pareto Distribution)**\n",
        f"• **Total Portfolio Absolute Variance:** {format_money(total_abs_var, cfg.currency, places)}",
        f"• **Top 3 Concentration:** **{top_3_pct:.1f}%** of all variance volatility is driven by just 3 line items:\n",
    ]

    for i, row in enumerate(top_3, start=1):
        with financial_context():
            row_share = ratio(abs(row.variance_dollars), total_abs_var) * Decimal("100")
        lines.append(
            f"  {i}. **{safe_inline(row.line_item)}:** {format_money(row.variance_dollars, cfg.currency, places)} "
            f"({row_share:.1f}% of total volatility, {status_label(row.status)})"
        )

    if top_3_pct >= Decimal("70"):
        insight = (
            "\n**High concentration.** These three lines account for "
            f"{top_3_pct:.1f}% of the total variance."
        )
    else:
        insight = (
            "\n**Spread out.** The variance is spread across many lines rather than held in a few."
        )
    lines.append(insight)

    chips = [f"Why {top_3[0].line_item}?", "Biggest risks", "Summary"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_unbudgeted(session: Session) -> Response:
    """Identify accounts that incurred actual spending with zero approved budget."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    unbudgeted = [r for r in _detail_rows(result) if r.budget == Decimal(0) and r.actual > Decimal(0)]
    session.last_table_items = [row.line_item for row in unbudgeted]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    wording = _UNBUDGETED_WORDING[cfg.comparison_basis]
    if not unbudgeted:
        return Response(
            text=f"**No {wording.heading}:** {wording.empty_state}",
            chips=["Summary", "Material", "Expense status"],
            phase=Phase.EXPLORING,
        )

    zero = format_money(Decimal(0), cfg.currency, places)
    spending = [row for row in unbudgeted if row.line_type != LineType.REVENUE]
    revenue = [row for row in unbudgeted if row.line_type == LineType.REVENUE]
    lines: list[str] = []
    if spending:
        lines.append(
            f"**{wording.heading} Detected ({len(spending)} account{'s' if len(spending) != 1 else ''})**\n\n"
            f"{wording.intro.format(zero=zero)}\n"
        )
        for row in spending:
            lines.append(
                f"• **{safe_inline(row.line_item)}:** {format_money(row.actual, cfg.currency, places)} realized "
                f"({status_label(row.status)}, Type: {row.line_type})"
            )
        lines.append(f"\n**Note:** {wording.note}")
    if revenue and not spending and not _is_budget(cfg):
        # Forecast/Prior Period: say plainly there is no such spending before listing revenue.
        lines.append(f"**No {wording.heading}.**\n")
    if revenue:
        lines.append(
            f"{chr(10) if spending else ''}**{wording.revenue_heading} ({len(revenue)} line{'s' if len(revenue) != 1 else ''}):** "
            f"{wording.revenue_intro.format(zero=zero)}\n"
        )
        for row in revenue:
            lines.append(f"• **{safe_inline(row.line_item)}:** {format_money(row.actual, cfg.currency, places)} earned")

    chips = [f"Why {unbudgeted[0].line_item}?", "Summary", "Warnings"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_cost_savings(session: Session) -> Response:
    """Show expense lines that preserved budget through favorable underspending."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    savings_rows = [
        r for r in _detail_rows(result)
        if r.line_type == LineType.EXPENSE and r.status == Status.FAVORABLE
    ]
    session.last_table_items = [row.line_item for row in savings_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not savings_rows:
        return Response(
            text=(
                "**No Cost Savings:** No expense accounts operated below their budgeted allocation."
                if _is_budget(cfg)
                else f"**No Cost Savings:** No expense accounts operated below the {_noun(cfg)}."
            ),
            chips=["Summary", "Expense status", "Biggest risks"],
            phase=Phase.EXPLORING,
        )

    savings_rows.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    with financial_context():
        total_savings = sum((abs(r.variance_dollars) for r in savings_rows), Decimal(0))

    lines = [
        f"**Expense Savings & Underspend Summary (Total: {format_money(total_savings, cfg.currency, places)})**\n\n"
        "These expense categories operated below approved spending limits, preserving cash and operating margin:\n"
    ]

    for row in savings_rows[:5]:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** Saved {format_money(abs(row.variance_dollars), cfg.currency, places)} "
            f"(Actual: {format_money(row.actual, cfg.currency, places)} vs. {_heading(cfg)}: {format_money(row.budget, cfg.currency, places)}, "
            f"{format_pct(row.budget, row.variance_dollars, row.percent_label)})"
        )

    lines.append(
        "\n**Note:** An underspend can be a lasting saving or an invoice that arrives in a later period; the figures alone do not say which."
    )

    chips = [f"Why {savings_rows[0].line_item}?", "Expenses", "Summary"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_revenue_misses(session: Session) -> Response:
    """Highlight revenue accounts that failed to meet their targets."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    miss_rows = [
        r for r in _detail_rows(result)
        if r.line_type == LineType.REVENUE and r.status == Status.UNFAVORABLE
    ]
    session.last_table_items = [row.line_item for row in miss_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not miss_rows:
        return Response(
            text=(
                "**No Revenue Misses:** All revenue accounts met or exceeded planned targets."
                if _is_budget(cfg)
                else f"**No Revenue Misses:** All revenue accounts met or exceeded the {_noun(cfg)}."
            ),
            chips=["Summary", "Revenue status", "Biggest wins"],
            phase=Phase.EXPLORING,
        )

    miss_rows.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    with financial_context():
        total_shortfall = sum((abs(r.variance_dollars) for r in miss_rows), Decimal(0))

    lines = [
        f"**Revenue Shortfall & Misses (Total: {format_money(total_shortfall, cfg.currency, places)})**\n\n"
        + ("These revenue lines failed to reach approved baseline targets:\n" if _is_budget(cfg)
           else f"These revenue lines fell short of the {_noun(cfg)}:\n")
    ]

    for row in miss_rows[:5]:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** Shortfall of {format_money(abs(row.variance_dollars), cfg.currency, places)} "
            f"(Actual: {format_money(row.actual, cfg.currency, places)} vs. {_heading(cfg)}: {format_money(row.budget, cfg.currency, places)}, "
            f"{format_pct(row.budget, row.variance_dollars, row.percent_label)})"
        )

    lines.append(
        "\n**Note:** `why [line]` splits a shortfall into volume and price when the file has those columns."
    )

    chips = [f"Why {miss_rows[0].line_item}?", "Revenue status", "Summary"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_waterfall(session: Session) -> Response:
    """Generate a step-by-step P&L bridge / waterfall walk reconciling budget to actual profit."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    with financial_context():
        budget_rev = result.revenue.budget
        budget_exp = result.expenses.budget
        budget_profit = budget_rev - budget_exp

        actual_rev = result.revenue.actual
        actual_exp = result.expenses.actual
        actual_profit = actual_rev - actual_exp

        net_var = actual_profit - budget_profit
        rev_impact = actual_rev - budget_rev
        exp_impact = budget_exp - actual_exp

        # Collect individual line items contributing to the bridge
        bridge_items: list[tuple[AnalyzedRow, Decimal]] = []
        for row in result.rows:
            if row.excluded_from_aggregation:
                continue
            if row.line_type == LineType.REVENUE:
                impact = row.actual - row.budget
            elif row.line_type == LineType.EXPENSE:
                impact = row.budget - row.actual
            else:
                # Unclassified rows sit outside the category totals, so they cannot move the bridge.
                impact = Decimal(0)
            bridge_items.append((row, impact))

        # Sort items by magnitude of profit impact (largest drivers first)
        bridge_items.sort(key=lambda item: abs(item[1]), reverse=True)

    table_rows: list[dict[str, str]] = [
        {
            "Line Item": f"1. {_heading(cfg)} Operating Profit",
            "Type": "Baseline",
            _heading(cfg): format_money(budget_profit, cur, places),
            "Actual": format_money(budget_profit, cur, places),
            f"Var ({sym})": format_money(Decimal(0), cur, places),
            f"Profit Impact ({sym})": format_money(Decimal(0), cur, places),
            "Status": "Neutral",
        }
    ]

    for row, impact in bridge_items:
        table_rows.append({
            "Line Item": safe_inline(row.line_item),
            "Type": str(row.line_type),
            _heading(cfg): format_money(row.budget, cur, places),
            "Actual": format_money(row.actual, cur, places),
            f"Var ({sym})": format_money(row.variance_dollars, cur, places),
            f"Profit Impact ({sym})": format_money(impact, cur, places),
            "Status": (str(row.status) if row.line_type == LineType.UNCLASSIFIED
                       else "F" if impact > 0 else ("U" if impact < 0 else "Neutral")),
        })

    table_rows.append({
        "Line Item": "Actual Operating Profit",
        "Type": "Summary",
        _heading(cfg): format_money(budget_profit, cur, places),
        "Actual": format_money(actual_profit, cur, places),
        f"Var ({sym})": format_money(net_var, cur, places),
        f"Profit Impact ({sym})": format_money(net_var, cur, places),
        "Status": "F" if net_var > 0 else ("U" if net_var < 0 else "Neutral"),
    })

    session.last_table_items = [row.line_item for row, _ in bridge_items]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    status_text = "favorable beat" if net_var > 0 else ("unfavorable shortfall" if net_var < 0 else "neutral")
    rev_status = "beat" if rev_impact > 0 else ("shortfall" if rev_impact < 0 else "flat")
    exp_status = "savings" if exp_impact > 0 else ("overrun" if exp_impact < 0 else "on track")

    text = (
        f"**P&L Variance Bridge (Waterfall Walk)**\n\n"
        f"Reconciling baseline {_heading(cfg)} Operating Profit to Actual Operating Profit for **{safe_inline(session.period or '')}**:\n\n"
        f"• **{_heading(cfg)} Operating Profit**: {format_money(budget_profit, cur, places)}\n"
        f"• **Revenue Bridge Impact**: {format_money(rev_impact, cur, places)} ({rev_status})\n"
        f"• **Expense Bridge Impact**: {format_money(exp_impact, cur, places)} ({exp_status})\n"
        f"• **Actual Operating Profit**: {format_money(actual_profit, cur, places)}\n"
        f"• **Net Profit Variance**: {format_money(net_var, cur, places)} ({status_text})\n\n"
        "Each line item's contribution to operating profit is displayed in the bridge table below "
        "(positive values expand profit; negative values contract profit):"
    )
    unclassified = [row for row, _ in bridge_items if row.line_type == LineType.UNCLASSIFIED]
    if unclassified:
        text += (
            f"\n\n{len(unclassified)} unclassified line item{'s are' if len(unclassified) != 1 else ' is'} "
            "excluded from operating profit and shown with zero impact until classified."
        )

    chips = []
    if session.last_table_items:
        chips.append(f"Why {session.last_table_items[0]}?")
    chips.extend(["Biggest risks", "Biggest wins", "Export CSV", "Summary"])

    return Response(text=text, table=table_rows, chips=chips, phase=Phase.EXPLORING)


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
        from .earnings import review_upload
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


def _handle_what_if(session: Session, intent: ParsedIntent) -> Response:
    """Simulate scenario impact on revenue, expenses, and operating profit."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    raw_target = intent.captures.get("target", "").strip()
    target_clean = re.sub(r"^(?:our|the|line\s+item)\s+", "", raw_target, flags=re.IGNORECASE).strip()
    raw_amount = intent.captures.get("amount", "").strip()
    direction = (intent.captures.get("direction") or "").lower()
    suffix = (intent.captures.get("suffix") or "").lower()

    if not raw_amount:
        return Response(
            text="Please specify a simulation amount or percentage (e.g., `what if revenue drops 5%?` or `what if marketing increases $20,000?`).",
            chips=["What if revenue drops 5%?", "What if expenses increase 10%?", "Sensitivity analysis"],
            phase=Phase.EXPLORING,
        )

    # Determine sign from the verb stem so every inflection (drop/drops/dropped, fall/falls, ...) agrees
    is_negative = (
        direction.startswith(("drop", "decreas", "fall", "cut", "reduc", "shrink", "lower", "down", "-"))
        or suffix in ("lower", "down", "less")
        or raw_amount.startswith("-")
    )

    amount_clean = raw_amount.lstrip("+-").strip()
    is_percent = "%" in amount_clean
    amount_num_str = amount_clean.replace("%", "").replace(sym, "").replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()

    multiplier = Decimal(1)
    if not is_percent:
        if amount_num_str.lower().endswith("k"):
            multiplier = Decimal(1000)
            amount_num_str = amount_num_str[:-1].strip()
        elif amount_num_str.lower().endswith("m"):
            multiplier = Decimal(1000000)
            amount_num_str = amount_num_str[:-1].strip()
        elif amount_num_str.lower().endswith("b"):
            multiplier = Decimal(1000000000)
            amount_num_str = amount_num_str[:-1].strip()

    try:
        amount_dec = parse_decimal(amount_num_str, field="amount", line_item="what_if") * multiplier
    except (ValueError, InvalidOperation):
        return Response(
            text=f"Could not parse numeric amount from '{safe_inline(raw_amount)}'.",
            chips=["What if revenue drops 5%?", "Sensitivity analysis"],
            phase=Phase.EXPLORING,
        )

    if amount_dec < 0:
        amount_dec = abs(amount_dec)
        is_negative = True

    if is_negative and is_percent and amount_dec > Decimal(100):
        return Response(
            text=f"A drop of more than 100% would take {safe_inline(target_clean)} below zero, "
                 "which is not a meaningful scenario. Try a smaller percentage or a dollar amount.",
            chips=["What if revenue drops 5%?", "What if expenses drop 10%?", "Sensitivity analysis"],
            phase=Phase.EXPLORING,
        )

    # Identify target: aggregate revenue, aggregate expense, or specific line item
    is_rev_agg = target_clean.lower() in ("revenue", "revenues", "sales", "topline", "top line")
    is_exp_agg = target_clean.lower() in ("expense", "expenses", "costs", "spend", "opex")

    matched_row: AnalyzedRow | None = None
    if not is_rev_agg and not is_exp_agg:
        line_items = [r.line_item for r in result.rows]
        resolved = _resolve_item_query(target_clean, session)
        matches = find_line_item(resolved, line_items)
        if matches:
            for r in result.rows:
                if r.line_item == matches[0]:
                    matched_row = r
                    break
        if matched_row is None:
            return Response(
                text=f"Could not identify target '{safe_inline(target_clean)}'. "
                     "You can simulate `revenue`, `expenses`, or a specific line item from your data.",
                chips=["What if revenue drops 5%?", "What if expenses increase 10%?", "Summary"],
                phase=Phase.EXPLORING,
            )

    if matched_row is not None and matched_row.line_type == LineType.UNCLASSIFIED:
        return Response(
            text=f"**{safe_inline(matched_row.line_item)}** is not classified as Revenue or Expense, so I "
                 "cannot tell whether a change helps or hurts profit. Classify it first: type `new`, "
                 "upload the file again and label it when asked, or add a Type column to your file.",
            chips=["What if revenue drops 5%?", "What if expenses increase 10%?", "Summary"],
            phase=Phase.EXPLORING,
        )

    with financial_context() as context:
        context.traps[Inexact] = False
        base_rev = result.revenue.actual
        base_exp = result.expenses.actual
        base_profit = base_rev - base_exp
        budget_rev = result.revenue.budget
        budget_exp = result.expenses.budget
        budget_profit = budget_rev - budget_exp

        if is_rev_agg:
            target_label = "Total Revenue"
            target_type = "Aggregate Revenue"
            target_budget = budget_rev
            target_is_rev = True
            base_val = base_rev
            delta = (base_rev * ratio(amount_dec, Decimal(100))) if is_percent else amount_dec
            if is_negative:
                delta = -delta
            sim_rev = base_rev + delta
            sim_exp = base_exp
            sim_val = sim_rev
        elif is_exp_agg:
            target_label = "Total Expenses"
            target_type = "Aggregate Expense"
            target_budget = budget_exp
            target_is_rev = False
            base_val = base_exp
            delta = (base_exp * ratio(amount_dec, Decimal(100))) if is_percent else amount_dec
            if is_negative:
                delta = -delta
            sim_rev = base_rev
            sim_exp = base_exp + delta
            sim_val = sim_exp
        else:
            assert matched_row is not None
            target_label = safe_inline(matched_row.line_item)
            target_type = str(matched_row.line_type)
            target_budget = matched_row.budget
            target_is_rev = (matched_row.line_type == LineType.REVENUE)
            base_val = matched_row.actual
            delta = (base_val * ratio(amount_dec, Decimal(100))) if is_percent else amount_dec
            if is_negative:
                delta = -delta
            sim_val = base_val + delta

            if matched_row.line_type == LineType.REVENUE:
                sim_rev = base_rev + delta
                sim_exp = base_exp
            elif matched_row.line_type == LineType.EXPENSE:
                sim_rev = base_rev
                sim_exp = base_exp + delta
            else:
                sim_rev = base_rev
                sim_exp = base_exp + delta

        sim_profit = sim_rev - sim_exp
        profit_delta = sim_profit - base_profit
        sim_vs_budget = sim_profit - budget_profit

        base_margin = (ratio(base_profit, base_rev) * Decimal(100)) if base_rev != 0 else None
        sim_margin = (ratio(sim_profit, sim_rev) * Decimal(100)) if sim_rev != 0 else None
        margin_delta = _pct_change(sim_margin, base_margin)

    sign_str = "-" if delta < 0 else "+"
    change_desc = f"{sign_str}{amount_dec:.1f}%" if is_percent else f"{sign_str}{sym}{abs(delta):,.2f}"
    profit_status = "expansion" if profit_delta > 0 else ("contraction" if profit_delta < 0 else "neutral")
    budget_status = "beat" if sim_vs_budget > 0 else ("shortfall" if sim_vs_budget < 0 else "on track")

    text = (
        f"**Scenario Analysis (\"What-If\" Simulation)**\n\n"
        f"**Simulation Parameters:**\n"
        f"• {'Target' if _is_budget(cfg) else 'Line'}: **{target_label}** ({target_type})\n"
        f"• Baseline Actual: {format_money(base_val, cur, places)}\n"
        f"• Simulated Change: **{change_desc}**\n"
        f"• Simulated {'Target ' if _is_budget(cfg) else ''}Value: **{format_money(sim_val, cur, places)}**\n\n"
        f"**Projected Operating Profit Impact:**\n"
        f"• **Baseline Operating Profit**: {format_money(base_profit, cur, places)}\n"
        f"• **Simulated Operating Profit**: **{format_money(sim_profit, cur, places)}**\n"
        f"• **Profit Delta vs. Baseline**: **{format_money(profit_delta, cur, places)}** ({profit_status})\n"
        f"• **Simulated Operating Margin**: **{_pct_text(sim_margin)}** (vs. {_pct_text(base_margin)} baseline, {_pct_text(margin_delta, '+.1f', ' pts')})\n"
        f"• **Simulated vs. {_heading(cfg)}**: **{format_money(sim_vs_budget, cur, places)}** ({budget_status} vs. {'planned' if _is_budget(cfg) else _noun(cfg)} profit of {format_money(budget_profit, cur, places)})\n"
    )

    target_row = [] if matched_row is None else [
        {
            "Metric": target_label,
            _heading(cfg): format_money(target_budget, cur, places),
            "Baseline Actual": format_money(base_val, cur, places),
            "Simulated Scenario": format_money(sim_val, cur, places),
            "Delta vs Baseline": format_money(delta, cur, places),
            "Status": "F" if (delta >= 0 if target_is_rev else delta <= 0) else "U",
        },
    ]
    # Aggregate targets are already the Total Revenue / Total Expenses rows below.
    table = target_row + [
        {
            "Metric": "Total Revenue",
            _heading(cfg): format_money(budget_rev, cur, places),
            "Baseline Actual": format_money(base_rev, cur, places),
            "Simulated Scenario": format_money(sim_rev, cur, places),
            "Delta vs Baseline": format_money(sim_rev - base_rev, cur, places),
            "Status": "F" if sim_rev >= base_rev else "U",
        },
        {
            "Metric": "Total Expenses",
            _heading(cfg): format_money(budget_exp, cur, places),
            "Baseline Actual": format_money(base_exp, cur, places),
            "Simulated Scenario": format_money(sim_exp, cur, places),
            "Delta vs Baseline": format_money(sim_exp - base_exp, cur, places),
            "Status": "F" if sim_exp <= base_exp else "U",
        },
        {
            "Metric": "Operating Profit",
            _heading(cfg): format_money(budget_profit, cur, places),
            "Baseline Actual": format_money(base_profit, cur, places),
            "Simulated Scenario": format_money(sim_profit, cur, places),
            "Delta vs Baseline": format_money(profit_delta, cur, places),
            "Status": "F" if profit_delta >= 0 else "U",
        },
    ]

    chips = ["Sensitivity analysis", "Run rate", "Waterfall", "What if expenses drop 5%?"]
    raw_label = matched_row.line_item if matched_row is not None else target_label
    heading = _plain_heading(cfg)
    view = figures_view(
        f"Scenario: {raw_label} {change_desc}",
        context=[pair("Line" if not _is_budget(cfg) else "Target", f"{raw_label} ({target_type})"),
                 pair("Baseline actual", format_money(base_val, cur, places)),
                 pair("Simulated value", format_money(sim_val, cur, places))],
        figures=[
            figure("Operating profit", format_money(sim_profit, cur, places),
                   f"Baseline {format_money(base_profit, cur, places)}",
                   f"{format_money(profit_delta, cur, places)} vs. baseline ({profit_status})", tone=_tone(profit_delta)),
            figure("Operating margin", _pct_text(sim_margin), f"Baseline {_pct_text(base_margin)}",
                   _pct_text(margin_delta, "+.1f", " pts")),
            figure(f"Against {heading.lower() if _is_budget(cfg) else heading}", format_money(sim_vs_budget, cur, places),
                   f"{heading} profit {format_money(budget_profit, cur, places)}", budget_status.capitalize(),
                   tone=_tone(sim_vs_budget)),
        ],
        notes=[note for note in (_unclassified_note(result).replace("unclassified line item",
                                                                    "line item not yet labeled revenue or expense"),)
               if note],
        table_title="The scenario line by line",
    )
    return Response(text=_with_unclassified_note(text, result), table=table, chips=chips, phase=Phase.EXPLORING,
                    view=view)


def _handle_sensitivity(session: Session) -> Response:
    """Generate a multi-scenario sensitivity matrix across revenue and expense deviations."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    with financial_context() as context:
        context.traps[Inexact] = False
        base_rev = result.revenue.actual
        base_exp = result.expenses.actual
        base_profit = base_rev - base_exp
        budget_profit = result.revenue.budget - result.expenses.budget

        scenarios = [
            ("Severe Downside (-10% Rev, +5% Exp)", Decimal("-0.10"), Decimal("0.05")),
            ("Moderate Downside (-5% Rev, +2% Exp)", Decimal("-0.05"), Decimal("0.02")),
            ("Baseline Actuals (Current)", Decimal("0.00"), Decimal("0.00")),
            ("Moderate Upside (+5% Rev, -2% Exp)", Decimal("0.05"), Decimal("-0.02")),
            ("Strong Upside (+10% Rev, -5% Exp)", Decimal("0.10"), Decimal("-0.05")),
        ]

        table_rows: list[dict[str, str]] = []
        for name, rev_pct, exp_pct in scenarios:
            s_rev = base_rev * (Decimal(1) + rev_pct)
            s_exp = base_exp * (Decimal(1) + exp_pct)
            s_profit = s_rev - s_exp
            s_var_budget = s_profit - budget_profit
            s_margin = (ratio(s_profit, s_rev) * Decimal(100)) if s_rev != 0 else None
            status = "F" if s_var_budget >= 0 else "U"

            table_rows.append({
                "Scenario": name,
                "Revenue": format_money(s_rev, cur, places),
                "Expenses": format_money(s_exp, cur, places),
                "Operating Profit": format_money(s_profit, cur, places),
                f"Var vs {_heading(cfg)} ({sym})": format_money(s_var_budget, cur, places),
                "Operating Margin": _pct_text(s_margin),
                "Status": status,
            })

    text = (
        f"**Financial Sensitivity & Scenario Matrix**\n\n"
        f"Evaluating operating profit resilience against volume and cost stress testing "
        f"for **{safe_inline(session.period or '')}**:\n\n"
        f"• **Baseline Operating Profit**: {format_money(base_profit, cur, places)}\n"
        f"• **{'Planned Budget' if _is_budget(cfg) else _heading(cfg)} Profit**: {format_money(budget_profit, cur, places)}\n"
        f"• **Stress Range**: From **{table_rows[0]['Operating Profit']}** (Severe Downside) "
        f"to **{table_rows[-1]['Operating Profit']}** (Strong Upside).\n\n"
        "Explore individual scenarios with `what if revenue drops 5%?` or `what if expenses increase 10%?`."
    )

    chips = ["What if revenue drops 5%?", "What if expenses increase 5%?", "Run rate", "Waterfall"]
    return Response(text=_with_unclassified_note(text, result), table=table_rows, chips=chips, phase=Phase.EXPLORING)


_UNRECOGNISED_PERIOD = "Quarterly (3 months assumed)"


_MONTH_NUMBERS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_NAME = re.compile(r"\b(" + "|".join(sorted(_MONTH_NUMBERS, key=len, reverse=True)) + r")\b")
_QUARTER = re.compile(r"(?<![a-z\d])q([1-4])(?!\d)")
_HALF = re.compile(r"(?<![a-z\d])h([12])(?!\d)")


def _detect_period_elapsed_months(period: str) -> tuple[int, str]:
    """Detect elapsed months and period label from session period text.

    The period names the end of the year-to-date span: a quarter or half by its number, a
    month (or the last month of a range such as 'Jan-Jun 2026') by its position in the year.
    """
    p = normalize_for_routing(period).lower()
    quarter = _QUARTER.search(p)
    if quarter:
        number = int(quarter.group(1))
        if number == 4:
            return 12, "Full Year (12 months)"
        return 3 * number, f"Q{number} ({3 * number} months elapsed)"
    half = _HALF.search(p)
    if half or "first half" in p or "second half" in p:
        if (half is not None and half.group(1) == "2") or "second half" in p:
            return 12, "H2 (12 months)"
        return 6, "H1 (6 months elapsed)"
    if re.search(r"\b(?:fy|fiscal\s+year|year)\s+end", p):
        return 12, "Full Year (12 months)"

    month_hits = _MONTH_NAME.findall(p)
    if month_hits:
        m_name = month_hits[-1]
        m_num = _MONTH_NUMBERS[m_name]
        return m_num, f"{m_name.capitalize()} ({m_num} month{'s' if m_num != 1 else ''} elapsed)"

    if re.search(r"\bfy|full\s+year|annual", p):
        return 12, "Full Year (12 months)"

    m_match = re.search(r"\bm(?:onth)?\s*([1-9]|1[0-2])\b", p)
    if m_match:
        m_num = int(m_match.group(1))
        return m_num, f"Month {m_num} ({m_num} month{'s' if m_num != 1 else ''} elapsed)"

    return 3, _UNRECOGNISED_PERIOD


def _handle_run_rate(session: Session, intent: ParsedIntent) -> Response:
    """Project annualized run-rate and corporate Latest Estimate (LE) year-end outcomes."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    elapsed, period_label = _detect_period_elapsed_months(session.period or "")
    remaining = 12 - elapsed

    with financial_context() as context:
        context.traps[Inexact] = False
        actual_rev = result.revenue.actual
        actual_exp = result.expenses.actual
        actual_profit = actual_rev - actual_exp

        budget_rev = result.revenue.budget
        budget_exp = result.expenses.budget
        budget_profit = budget_rev - budget_exp

        multiplier = ratio(Decimal(12), Decimal(elapsed))

        # 1. Pace-based annualized run-rate
        rr_rev = actual_rev * multiplier
        rr_exp = actual_exp * multiplier
        rr_profit = rr_rev - rr_exp
        annual_budget_profit = budget_profit * multiplier
        rr_var = rr_profit - annual_budget_profit
        rr_margin = (ratio(rr_profit, rr_rev) * Decimal(100)) if rr_rev != 0 else None

        # 2. Corporate FP&A Latest Estimate (LE = Actuals to Date + Remaining Budget)
        remaining_budget_rev = budget_rev * ratio(Decimal(remaining), Decimal(elapsed))
        remaining_budget_exp = budget_exp * ratio(Decimal(remaining), Decimal(elapsed))
        le_rev = actual_rev + remaining_budget_rev
        le_exp = actual_exp + remaining_budget_exp
        le_profit = le_rev - le_exp
        le_var = le_profit - annual_budget_profit
        le_margin = (ratio(le_profit, le_rev) * Decimal(100)) if le_rev != 0 else None

    rr_status = "beat" if rr_var >= 0 else "shortfall"
    le_status = "favorable beat" if le_var >= 0 else "unfavorable shortfall"

    remaining_label = "Remaining Plan" if _is_budget(cfg) else f"Remaining {_heading(cfg)}"
    text = (
        f"**Run-Rate & Full-Year (FY) Projections**\n\n"
        f"**Period Basis:** **{period_label}** ({elapsed} of 12 months elapsed; {remaining} months remaining in fiscal year).\n"
        f"*Assumption: the figures are year-to-date through this period, so they are annualized over {elapsed} months.*\n"
        + (f"Period '{safe_inline(session.period or '')}' was not recognised, so {elapsed} elapsed months are assumed; "
           "name it like `Q3 2026`, `H1 2026`, `FY2026` or `October 2026` for an exact basis.\n"
           if period_label == _UNRECOGNISED_PERIOD else "")
        + "\n"
        f"• **Annualized Operating Profit (Run-Rate)**: **{format_money(rr_profit, cur, places)}**\n"
        f"  *If current operational velocity continues for the full year, profit is projected at {format_money(rr_profit, cur, places)} "
        f"({format_money(rr_var, cur, places)} {rr_status} vs. annual {_noun(cfg)} of {format_money(annual_budget_profit, cur, places)}).*\n\n"
        f"• **Corporate Latest Estimate (LE = Actuals + {remaining_label})**: **{format_money(le_profit, cur, places)}**\n"
        f"  *Assuming remaining {remaining} months perform strictly to {_noun(cfg)}, full-year profit finishes at {format_money(le_profit, cur, places)} "
        f"({format_money(le_var, cur, places)} {le_status} vs. {'plan' if _is_budget(cfg) else _noun(cfg)}).*\n\n"
        f"• **Annualized Revenue Run-Rate**: {format_money(rr_rev, cur, places)} (Operating Margin: {_pct_text(rr_margin)})\n"
        f"• **Annualized Expense Run-Rate**: {format_money(rr_exp, cur, places)}"
    )

    table = [
        {
            "Projection Model": f"Actuals to Date ({safe_inline(session.period or '')})",
            "Revenue": format_money(actual_rev, cur, places),
            "Expenses": format_money(actual_exp, cur, places),
            "Operating Profit": format_money(actual_profit, cur, places),
            f"Var vs {_heading(cfg)} ({sym})": format_money(actual_profit - budget_profit, cur, places),
            "Operating Margin": f"{(ratio(actual_profit, actual_rev) * 100):.1f}%" if actual_rev != 0 else "N/A",
            "Status": "F" if (actual_profit - budget_profit) >= 0 else "U",
        },
        {
            "Projection Model": "Annualized Run-Rate (Current Pace)",
            "Revenue": format_money(rr_rev, cur, places),
            "Expenses": format_money(rr_exp, cur, places),
            "Operating Profit": format_money(rr_profit, cur, places),
            f"Var vs {_heading(cfg)} ({sym})": format_money(rr_var, cur, places),
            "Operating Margin": _pct_text(rr_margin),
            "Status": "F" if rr_var >= 0 else "U",
        },
        {
            "Projection Model": f"Latest Estimate (LE: Actuals + {remaining_label})",
            "Revenue": format_money(le_rev, cur, places),
            "Expenses": format_money(le_exp, cur, places),
            "Operating Profit": format_money(le_profit, cur, places),
            f"Var vs {_heading(cfg)} ({sym})": format_money(le_var, cur, places),
            "Operating Margin": _pct_text(le_margin),
            "Status": "F" if le_var >= 0 else "U",
        },
        {
            "Projection Model": f"Full-Year Baseline {_heading(cfg)}",
            "Revenue": format_money(budget_rev * multiplier, cur, places),
            "Expenses": format_money(budget_exp * multiplier, cur, places),
            "Operating Profit": format_money(annual_budget_profit, cur, places),
            f"Var vs {_heading(cfg)} ({sym})": format_money(Decimal(0), cur, places),
            "Operating Margin": f"{(ratio(annual_budget_profit, budget_rev * multiplier) * 100):.1f}%" if (budget_rev * multiplier) != 0 else "N/A",
            "Status": "Neutral",
        },
    ]

    chips = ["Sensitivity analysis", "What if revenue drops 5%?", "Waterfall", "Summary"]
    return Response(text=_with_unclassified_note(text, result), table=table, chips=chips, phase=Phase.EXPLORING)


def _handle_executive_memo(session: Session) -> Response:
    """Generate an executive-ready variance briefing memo suitable for CFO and board reporting."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    with financial_context() as context:
        context.traps[Inexact] = False
        rev_budget = result.revenue.budget
        rev_actual = result.revenue.actual
        rev_var = rev_actual - rev_budget
        rev_pct = _variance_percent(rev_var, rev_budget)

        exp_budget = result.expenses.budget
        exp_actual = result.expenses.actual
        exp_var = exp_actual - exp_budget
        exp_pct = _variance_percent(exp_var, exp_budget)

        budget_profit = rev_budget - exp_budget
        actual_profit = rev_actual - exp_actual
        net_impact = actual_profit - budget_profit
        net_pct = (ratio(net_impact, abs(budget_profit)) * Decimal(100)) if budget_profit != 0 else None

        budget_margin = (ratio(budget_profit, rev_budget) * Decimal(100)) if rev_budget != 0 else None
        actual_margin = (ratio(actual_profit, rev_actual) * Decimal(100)) if rev_actual != 0 else None
        margin_delta = _pct_change(actual_margin, budget_margin)

    # Find top revenue driver & drag
    rev_rows = [r for r in _detail_rows(result) if r.line_type == LineType.REVENUE]
    top_rev_beat = max((r for r in rev_rows if r.variance_dollars > 0), key=lambda r: r.variance_dollars, default=None)
    top_rev_miss = min((r for r in rev_rows if r.variance_dollars < 0), key=lambda r: r.variance_dollars, default=None)

    # Find largest cost overrun & largest saving
    exp_rows = [r for r in _detail_rows(result) if r.line_type == LineType.EXPENSE]
    top_exp_over = max((r for r in exp_rows if r.variance_dollars > 0), key=lambda r: r.variance_dollars, default=None)
    top_exp_save = min((r for r in exp_rows if r.variance_dollars < 0), key=lambda r: r.variance_dollars, default=None)

    # Reconciled driver count
    reconciled_count = sum(1 for r in result.material_rows if r.driver_evidence and r.driver_evidence.reconciles)

    status_word = "beat" if net_impact >= 0 else "shortfall"
    sign_word = "moved" if margin_delta is None else "expanded" if margin_delta >= 0 else "contracted"

    # Same fact-gated builder as the CLI --commentary report, so both surfaces agree;
    # it names the comparison basis (budget, forecast or prior period).
    from deterministic_conditioning.variance_bridge import generate_verified_commentary
    narrative_takeaway = safe_inline(generate_verified_commentary(result)[0])

    memo_lines = [
        "# Executive Management Briefing & Variance Commentary",
        f"**Reporting Period:** {cfg.period}  ",
        f"**Currency:** {cfg.currency}  ",
        f"**Materiality Thresholds:** {format_threshold_amount(cfg.dollar_threshold, cur)} or {format_threshold_pct(cfg.percent_threshold)}  \n",
        "---",
        "### 1. Executive Summary",
        f"**Strategic Takeaway:** {narrative_takeaway}\n",
        *([f"{_unclassified_note(result)}\n"] if _unclassified_note(result) else []),
        f"For **{cfg.period}**, Operating Profit finished at **{format_money(actual_profit, cur, places)}**, representing a "
        f"**{format_money(abs(net_impact), cur, places)} {status_word}** ({_pct_text(net_pct, '+.1f')}) "
        f"against the {'planned budget' if _is_budget(cfg) else _noun(cfg)} of **{format_money(budget_profit, cur, places)}**. "
        f"Operating margin **{sign_word}** from {_pct_text(budget_margin)} to **{_pct_text(actual_margin)}** ({_pct_text(margin_delta, '+.1f', ' pts')}).\n",
        "### 2. Top-Line Performance (Revenue)",
        f"Total Revenue concluded at **{format_money(rev_actual, cur, places)}** vs. {_heading(cfg)} of **{format_money(rev_budget, cur, places)}** "
        f"({format_money(rev_var, cur, places)}, {_pct_text(rev_pct, '+.1f')}, {'Favorable' if rev_var >= 0 else 'Unfavorable'}).",
    ]

    if top_rev_beat:
        memo_lines.append(f"• **Key Outperformer:** **{safe_inline(top_rev_beat.line_item)}** generated {format_money(top_rev_beat.actual, cur, places)} (+{format_money(top_rev_beat.variance_dollars, cur, places)} above {_noun(cfg)}).")
    if top_rev_miss:
        memo_lines.append(f"• **Primary Drag:** **{safe_inline(top_rev_miss.line_item)}** delivered {format_money(top_rev_miss.actual, cur, places)} ({format_money(top_rev_miss.variance_dollars, cur, places)} miss vs. {_noun(cfg)}).")

    memo_lines.extend([
        "\n### 3. Cost Discipline & Overruns (Expenses)",
        f"Total Operating Expenses ended at **{format_money(exp_actual, cur, places)}** vs. {_heading(cfg)} of **{format_money(exp_budget, cur, places)}** "
        f"({format_money(exp_var, cur, places)}, {_pct_text(exp_pct, '+.1f')}, {'Unfavorable' if exp_var > 0 else 'Favorable'}).",
    ])

    if top_exp_over:
        memo_lines.append(f"• **Primary Cost Risk:** **{safe_inline(top_exp_over.line_item)}** overspent by {format_money(top_exp_over.variance_dollars, cur, places)} ({'+' if top_exp_over.variance_percent is not None else ''}{format_pct(top_exp_over.budget, top_exp_over.variance_dollars, top_exp_over.percent_label)}).")
    if top_exp_save:
        memo_lines.append(f"• **Key Cost Savings:** **{safe_inline(top_exp_save.line_item)}** saved {format_money(abs(top_exp_save.variance_dollars), cur, places)} vs. {'allocated budget' if _is_budget(cfg) else _noun(cfg)}.")

    memo_lines.extend([
        "\n### 4. Governance & Material Variances",
        f"• **{len(result.material_rows)}** line items breached the materiality hurdle ({format_threshold_amount(cfg.dollar_threshold, cur)} or {format_threshold_pct(cfg.percent_threshold)}).",
        f"• **Net Flow-Through:** {format_money(net_impact, cur, places)} retained in net operating profit.",
        f"• **Driver Evidence Coverage:** {reconciled_count} of {len(result.material_rows)} material items verified by mathematical driver decomposition.",
        "\n### 5. Prioritized Management Action Items",
    ])

    if top_exp_over:
        memo_lines.append(f"1. **Cost Remediation:** Initiate immediate operational review on **{safe_inline(top_exp_over.line_item)}** to stabilize cost trajectory.")
    else:
        memo_lines.append("1. **Cost Discipline:** Maintain expense ceiling caps across all departmental allocations.")

    if top_rev_beat:
        memo_lines.append(f"2. **Revenue Scaling:** Protect and expand pipeline investments supporting **{safe_inline(top_rev_beat.line_item)}**.")
    else:
        memo_lines.append(
            "2. **Sales Acceleration:** Formulate commercial recovery plans targeting lagging revenue lines."
            if _is_budget(cfg)
            else "2. **Sales Acceleration:** Formulate commercial recovery actions for lagging revenue lines."
        )

    missing = [safe_inline(r.line_item) for r in result.material_rows if not (r.driver_evidence and r.driver_evidence.reconciles)]
    if missing:
        memo_lines.append(f"3. **Data Governance:** Procure granular driver components (rate/volume/mix) for {', '.join(missing[:3])}.")
    else:
        memo_lines.append("3. **Audit Verification:** All material drivers mathematically reconciled and signed off.")

    memo_text = "\n".join(memo_lines)
    period_slug = _period_slug(cfg.period)
    filename = f"executive_memo_{period_slug}.md"

    table_overview = [
        {
            "Section": "1. Top-Line (Revenue)",
            _heading(cfg): format_money(rev_budget, cur, places),
            "Actual": format_money(rev_actual, cur, places),
            f"Variance ({sym})": format_money(rev_var, cur, places),
            "Outcome": "Beat" if rev_var >= 0 else "Miss",
        },
        {
            "Section": "2. Cost (Expenses)",
            _heading(cfg): format_money(exp_budget, cur, places),
            "Actual": format_money(exp_actual, cur, places),
            f"Variance ({sym})": format_money(exp_var, cur, places),
            "Outcome": "Overrun" if exp_var > 0 else "Savings",
        },
        {
            "Section": "3. Bottom-Line (Operating Profit)",
            _heading(cfg): format_money(budget_profit, cur, places),
            "Actual": format_money(actual_profit, cur, places),
            f"Variance ({sym})": format_money(net_impact, cur, places),
            "Outcome": "Favorable" if net_impact >= 0 else "Unfavorable",
        },
    ]

    return Response(
        text=memo_text,
        table=table_overview,
        chips=["Waterfall", "Export report", "Export csv", "Summary"],
        download={filename: memo_text},
        phase=Phase.EXPLORING,
    )


def _handle_driver_summary(session: Session) -> Response:
    """Provide an overview of all causal driver decompositions in the dataset."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency

    rows_with_drivers = [r for r in result.rows if r.driver_evidence is not None]
    rows_reconciled = [r for r in rows_with_drivers if r.driver_evidence and r.driver_evidence.reconciles]

    table_data: list[dict[str, str]] = []
    for r in result.rows:
        if r.driver_evidence is not None:
            ev = r.driver_evidence
            status_str = "Reconciled" if ev.reconciles else "Not reconciled"
            model_label = ev.label
            comps = ", ".join(f"{k}: {format_money(v, cur, places)}" for k, v in ev.components)
        else:
            status_str = "No driver data"
            model_label = "None"
            comps = "—"

        table_data.append({
            "Line Item": safe_inline(r.line_item),
            "Variance": format_money(r.variance_dollars, cur, places),
            "Model": model_label,
            "Reconciliation": status_str,
            "Driver Components": comps,
        })

    coverage_pct = (ratio(Decimal(len(rows_reconciled)), Decimal(len(result.material_rows))) * Decimal(100)) if result.material_rows else Decimal(100)

    with_data = f"{len(rows_with_drivers)} with driver data"
    text = (
        f"**Causal Driver Models Overview**\n\n"
        f"• **Lines with a reconciled driver model:** **{len(rows_reconciled)}** of **{len(result.rows)}** "
        f"({with_data}).\n"
        f"• **Material variances covered:** **{coverage_pct:.1f}%** have a reconciled driver breakdown.\n\n"
        f"A driver model splits a variance from {_noun(cfg)} into its causes, such as price and volume, "
        "or rate and volume."
    )
    view = figures_view(
        "Driver data",
        figures=[figure("Reconciled driver models", f"{len(rows_reconciled)} of {len(result.rows)}", with_data.capitalize()),
                 figure("Material variances covered", f"{coverage_pct:.1f}%")],
        notes=[f"A driver model splits a variance from {_noun(cfg)} into its causes, such as price and volume, "
               "or rate and volume."],
        table_title="Driver data by line",
    )

    chips = ["Waterfall", "Biggest risks", "Summary", "Export report"]
    return Response(text=text, table=table_data, chips=chips, phase=Phase.EXPLORING, view=view)


def _handle_greeting(session: Session) -> Response:
    """Respond politely to conversational greetings with context-aware guidance."""
    if session.phase == Phase.EXPLORING and session.result is not None:
        cfg = session.result.config
        places = report_places(session.result)
        cur = cfg.currency
        net_impact = session.result.revenue.variance_dollars - session.result.expenses.variance_dollars
        status = "favorable beat" if net_impact >= 0 else "unfavorable shortfall"

        text = (
            f"I am ready to explore your **{cfg.period}** financial results.\n\n"
            f"Currently tracking **{cur}** with materiality set at **{format_threshold_amount(cfg.dollar_threshold, cur)} or {format_threshold_pct(cfg.percent_threshold)}**. "
            f"Overall net operating impact is a **{format_money(abs(net_impact), cur, places)} {status}** against {_noun(cfg)}.\n\n"
            f"What would you like to review? You can ask for an `executive memo`, a `waterfall` walk, `run rate` projections, or drill down into any account (e.g. `why {safe_inline(session.result.rows[0].line_item)}`)."
        )
        chips = ["Executive memo", "Waterfall", "Biggest risks", "Sensitivity"]
    elif session.phase == Phase.AWAITING_PERIOD:
        text = (
            "Your file has been validated and loaded. "
            "Which reporting period does it cover? For example `Q3 2026` or `August 2026`."
        )
        chips = ["Q3 2026", "FY 2026", "Month ended Sep 30, 2026"]
    elif session.phase == Phase.AWAITING_THRESHOLDS:
        text = (
            "Next come the materiality thresholds: a dollar amount and a percentage, "
            "for example `$10,000 or 5%`."
        )
        chips = ["$5,000 or 5%", "$10,000 or 5%", "$25,000 or 10%"]
    elif session.phase == Phase.AWAITING_CURRENCY:
        text = (
            "What currency are these figures reported in? "
            "For example `USD`, `EUR` or `GBP`."
        )
        chips = ["USD", "EUR", "GBP"]
    elif session.phase == Phase.RESOLVE_UNCLASSIFIED:
        text = (
            "Some lines are not yet labeled revenue or expense. "
            "Choose `Revenue`, `Expense` or `Skip` for the line named above."
        )
        chips = ["Revenue", "Expense", "Skip", "Skip all"]
    else:
        text = (
            "**Welcome to the Variance Analysis Agent.**\n\n"
            "Every figure comes from exact, repeatable calculations. "
            "Drop a CSV, JSON or Excel workbook above to start, or ask about a variance concept."
        )
        chips = ["Supported file formats", "What is materiality?", "Budget vs forecast"]

    return Response(text=text, chips=chips, phase=session.phase)


def _handle_gratitude(session: Session) -> Response:
    """Respond gracefully to user pleasantries and acknowledgments."""
    text = (
        "You're very welcome! Always glad to assist with institutional FP&A rigor. "
        "Feel free to test scenario simulations (e.g. `what if revenue drops 5%?`), "
        "inspect causal drivers, or export the executive commentary memo whenever you're ready."
    )
    chips = ["Executive memo", "Waterfall", "Sensitivity", "Summary"] if session.phase == Phase.EXPLORING else ["Help"]
    return Response(text=text, chips=chips, phase=session.phase)


def _handle_identity(session: Session) -> Response:
    """Explain agent identity, institutional purpose, and deterministic guarantees."""
    where = (
        "On this shared hosted version your file is processed on the host's server, so do not "
        "upload confidential data; run the app locally for sensitive files."
        if not session.path_exports_enabled
        else "Run locally, your file is read on your own machine."
    )
    text = (
        "**Institutional Variance Analysis Agent**\n\n"
        "I am an intelligent, deterministic financial analysis assistant built specifically for FP&A teams, "
        "controllers, and CFO organizations.\n\n"
        "**How I differ from a non-deterministic LLM:**\n"
        "• **100% Deterministic Calculations**: Zero hallucination. Every variance, percentage, and waterfall step is computed with 50-digit exact Decimal precision.\n"
        "• **Source Fingerprints**: Every analysis produces a SHA-256 fingerprint of the file it came from, for traceability.\n"
        "• **Conversational Fluency**: I interpret natural business queries, multi-turn follow-ups, and scenarios, giving you the ease of a conversational AI with the trustworthiness of an audited ledger.\n"
        "• **No AI Model In The Loop**: The calculations use standard-library Python and no language model sees or computes your numbers. "
        + where
    )
    chips = ["Summary", "Executive memo", "What is materiality?", "Help"] if session.phase == Phase.EXPLORING else ["Supported file formats", "Help"]
    return Response(text=text, chips=chips, phase=session.phase)


def _handle_tldr(session: Session) -> Response:
    """Provide a punchy, conversational 2-sentence executive takeaway."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency

    with financial_context() as context:
        context.traps[Inexact] = False
        rev_var = result.revenue.actual - result.revenue.budget
        exp_var = result.expenses.actual - result.expenses.budget
        actual_profit = result.revenue.actual - result.expenses.actual
        budget_profit = result.revenue.budget - result.expenses.budget
        net_impact = actual_profit - budget_profit
        impact_pct = (ratio(net_impact, abs(budget_profit)) * Decimal(100)) if budget_profit != 0 else None
        margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else None

    basis = "plan" if _is_budget(cfg) else f"the {_noun(cfg)}"
    # A zero difference is neither a beat nor a saving: say it is on plan.
    if net_impact == 0:
        outcome = (f"exactly matching {'the planned budget' if _is_budget(cfg) else _noun(cfg)} "
                   f"of {format_money(budget_profit, cur, places)}")
    else:
        beat_word = "beat" if net_impact > 0 else "shortfall"
        outcome = (f"delivering a **{format_money(abs(net_impact), cur, places)} {beat_word}** "
                   f"({_pct_text(impact_pct, '+.1f')} vs. {'planned budget' if _is_budget(cfg) else _noun(cfg)} "
                   f"of {format_money(budget_profit, cur, places)})")
    if rev_var == 0:
        revenue_clause = f"Top-line revenue came in exactly on {basis}"
    else:
        rev_word = "outperformed" if rev_var > 0 else "underperformed"
        revenue_clause = f"Top-line revenue {rev_word} {basis} by {format_money(abs(rev_var), cur, places)}"
    if exp_var == 0:
        expense_clause = f"operating expenses came in exactly on {basis}"
    else:
        exp_word = "generated savings of" if exp_var < 0 else "overspent by"
        expense_clause = f"operating expenses {exp_word} {format_money(abs(exp_var), cur, places)}"

    # Identify top accounts
    rev_rows = [r for r in _detail_rows(result) if r.line_type == LineType.REVENUE]
    exp_rows = [r for r in _detail_rows(result) if r.line_type == LineType.EXPENSE]
    top_rev = max(rev_rows, key=lambda r: abs(r.variance_dollars), default=None)
    top_exp = max(exp_rows, key=lambda r: abs(r.variance_dollars), default=None)

    def described(row: AnalyzedRow) -> str:
        if row.status == Status.NEUTRAL:
            on_basis = "on budget" if _is_budget(cfg) else f"in line with the {_noun(cfg)}"
            return f"**{safe_inline(row.line_item)}** ({on_basis})"
        if row.line_type == LineType.REVENUE:
            word = "beat" if row.variance_dollars > 0 else "miss"
        else:
            word = "overrun" if row.variance_dollars > 0 else "saving"
        return f"**{safe_inline(row.line_item)}** ({word} of {format_money(abs(row.variance_dollars), cur, places)})"

    driver_context = ""
    if top_rev and top_exp:
        driver_context = (f" The largest revenue swing was {described(top_rev)}; "
                          f"the largest expense swing was {described(top_exp)}.")
    note = _unclassified_note(result)
    if note:
        driver_context += f"\n\n{note}"

    text = (
        f"**The Executive TL;DR for {cfg.period}:**\n\n"
        f"Operating Profit finished at **{format_money(actual_profit, cur, places)}**, {outcome} "
        f"with operating margin standing at **{_pct_text(margin)}**. "
        f"{revenue_clause}, while {expense_clause}.{driver_context}"
    )

    chips = ["Executive memo", "Waterfall", "Sensitivity", "Summary"]
    return Response(text=text, chips=chips, phase=Phase.EXPLORING)


def _handle_profitability(session: Session) -> Response:
    """Deliver a clear, conversational evaluation of bottom-line profitability and black vs. red standing."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    cur = cfg.currency
    sym = CURRENCY_SYMBOLS.get(cur, "$")

    with financial_context() as context:
        context.traps[Inexact] = False
        actual_profit = result.revenue.actual - result.expenses.actual
        budget_profit = result.revenue.budget - result.expenses.budget
        net_impact = actual_profit - budget_profit
        actual_margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else None
        budget_margin = (ratio(budget_profit, result.revenue.budget) * Decimal(100)) if result.revenue.budget != 0 else None
        margin_delta = _pct_change(actual_margin, budget_margin)

    is_black = actual_profit >= 0
    stance = "firmly **in the black** (profitable)" if is_black else "currently **in the red** (operating loss)"
    status = "favorable beat" if net_impact >= 0 else "unfavorable shortfall"

    text = (
        f"**Profitability Standing: {cfg.period}**\n\n"
        f"Operations are {stance}!\n\n"
        f"• **Actual Operating Profit:** **{format_money(actual_profit, cur, places)}** (operating margin: **{_pct_text(actual_margin)}**)\n"
        f"• **{_planned(cfg)} Operating Profit:** {format_money(budget_profit, cur, places)} ({'Planned' if _is_budget(cfg) else _heading(cfg)} margin: {_pct_text(budget_margin)})\n"
        f"• **Variance vs. {_heading(cfg)}:** **{format_money(net_impact, cur, places)}** ({status}; margin change: {_pct_text(margin_delta, '+.1f', ' pts')})\n\n"
        f"Operating profit reflects gross commercial revenues ({format_money(result.revenue.actual, cur, places)}) "
        f"less total operating expenses ({format_money(result.expenses.actual, cur, places)})."
    )

    table = [
        {
            "Metric": "Total Revenue",
            _heading(cfg): format_money(result.revenue.budget, cur, places),
            "Actual": format_money(result.revenue.actual, cur, places),
            f"Variance ({sym})": format_money(result.revenue.actual - result.revenue.budget, cur, places),
            "Flow": "Inflow",
        },
        {
            "Metric": "Total Expenses",
            _heading(cfg): format_money(result.expenses.budget, cur, places),
            "Actual": format_money(result.expenses.actual, cur, places),
            f"Variance ({sym})": format_money(result.expenses.actual - result.expenses.budget, cur, places),
            "Flow": "Outflow",
        },
        {
            "Metric": "Operating Profit",
            _heading(cfg): format_money(budget_profit, cur, places),
            "Actual": format_money(actual_profit, cur, places),
            f"Variance ({sym})": format_money(net_impact, cur, places),
            "Flow": "Retained Margin",
        },
    ]

    chips = ["Waterfall", "Run rate", "Executive memo", "Summary"]
    return Response(text=_with_unclassified_note(text, result), table=table, chips=chips, phase=Phase.EXPLORING)


def _describe_item_reply(session: Session, matched_name: str) -> Response:
    """Conversational reply for a line item the user mentioned in passing."""
    assert session.result is not None
    session.last_focused_item = matched_name
    row = next(r for r in session.result.rows if r.line_item == matched_name)
    cfg = session.result.config
    places = report_places(session.result)
    if row.status == Status.FAVORABLE:
        status_desc = "favorable beat"
    elif row.status == Status.UNFAVORABLE:
        status_desc = ("unfavorable cost overrun" if row.line_type == LineType.EXPENSE
                       else "unfavorable revenue shortfall")
    elif row.status == Status.NEUTRAL:
        status_desc = "in line with budget" if _is_budget(cfg) else f"in line with the {_noun(cfg)}"
    else:
        status_desc = "unclassified, so no favorable/unfavorable direction"
    return Response(
        text=f"Here is what happened with **{safe_inline(row.line_item)}** in {cfg.period}:\n\n"
             f"• **{_heading(cfg)}:** {format_money(row.budget, cfg.currency, places)}\n"
             f"• **Actual:** {format_money(row.actual, cfg.currency, places)}\n"
             f"• **Variance:** **{format_money(row.variance_dollars, cfg.currency, places)}** "
             f"({format_pct(row.budget, row.variance_dollars, row.percent_label)}, {status_desc})\n\n"
             f"Would you like to inspect its causal driver decomposition (`why {safe_inline(row.line_item)}`) or simulate a change (`what if {safe_inline(row.line_item)} drops 5%`)?",
        table=[row_to_table_dict(row, cfg.currency, places, _heading(cfg))],
        chips=[f"Why {row.line_item}?", f"Detail {row.line_item}?", "Waterfall", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_unknown(session: Session, text: str) -> Response:
    """Fallback for unrecognized queries with intelligent financial keyword detection and conversational guidance."""
    text_lower = normalize_for_routing(text).lower()

    # An account named in full ("Profit Sharing looks high") outranks the keywords below.
    named: list[str] = []
    if session.result is not None:
        named = _items_named_in(text, [r.line_item for r in session.result.rows])
        if named:
            return _describe_item_reply(session, named[0])

    if any(k in text_lower for k in ("margin", "ebitda", "profit", "operating income")):
        return _handle_profitability(session) if (session.phase == Phase.EXPLORING and session.result is not None) else Response(
            text="**Note:** Net operating impact measures the overall variance contribution toward operating profit. "
                 "Under standard financial rules, profit measures are not treated as additive revenue to prevent double-counting. "
                 "Try asking: `summary`, `what is net impact?`, or `totals`.",
            chips=["Summary", "Net impact", "Totals"],
            phase=session.phase,
        )

    noun = _noun(session.result.config) if session.result is not None else "budget"
    if any(k in text_lower for k in ("forecast", "projection", "run rate", "reforecast")):
        baseline = "the baseline budget" if noun == "budget" else f"the {noun}"
        return Response(
            text=f"**Note:** This analysis evaluates actual performance against {baseline} for the closed reporting period. "
                 "To project full-year outcomes based on current pace, ask for `run rate` or test scenarios with `what if revenue drops 5%?`.",
            chips=["Run rate", "Sensitivity", "Summary"],
            phase=session.phase,
        )

    # Direct line-item matching for conversational queries (e.g. 'what happened to marketing', 'is office supplies bad')
    if session.result is not None:
        line_items = [r.line_item for r in session.result.rows]
        resolved = _resolve_item_query(text, session)
        matches = find_line_item(resolved, line_items)
        if not matches:
            named_item = _item_in_sentence(text, line_items, named)
            matches = [named_item] if named_item else []
        if matches:
            return _describe_item_reply(session, matches[0])

    first_item = session.result.rows[0].line_item if (session.result and session.result.rows) else "Marketing"
    return Response(
        text=f"I want to make sure I provide the exact figures you need. I couldn't find an account matching \"{safe_inline(text if len(text) <= 80 else text[:80] + '…')}\" in your current dataset.\n\n"
             "Here are a few ways we can explore your numbers:\n"
             f"• **Account Driver Breakdown:** Ask `why [Account Name]` (e.g. `why {safe_inline(first_item)}`)\n"
             f"• **Profit Waterfall:** Ask for `waterfall` to reconcile {noun} to actual operating profit\n"
             "• **Scenario Analysis:** Try `what if revenue drops 5%?` or `sensitivity`\n"
             "• **Management Commentary:** Ask for `memo` or `tldr` for executive highlights",
        chips=["Summary", "Waterfall", "Biggest risks", "Help"],
        phase=session.phase,
    )


# Intent id -> the explanation it asks for; each is built only when asked.
_KNOWLEDGE_TEXTS: dict[str, Callable[[], str]] = {
    "concept_consensus": knowledge.explain_consensus,
    "concept_surprise": knowledge.explain_surprise,
    "concept_beat_miss": knowledge.explain_beat_miss,
    "concept_bps": knowledge.explain_bps,
    "concept_guidance_range": knowledge.explain_guidance_ranges,
    "concept_standardized_surprise": knowledge.explain_standardized_surprise,
    "concept_variance": knowledge.explain_variance_analysis,
    "concept_f_vs_u": knowledge.explain_favorable_unfavorable,
    "concept_fav": knowledge.explain_favorable_unfavorable,
    "concept_unfav": knowledge.explain_favorable_unfavorable,
    "concept_materiality": knowledge.explain_materiality,
    "concept_net_impact": knowledge.explain_net_impact,
    "concept_drivers": knowledge.explain_drivers,
    "concept_unclassified": knowledge.explain_unclassified,
    "concept_audit": knowledge.explain_audit_trail,
    "concept_actions": knowledge.explain_mitigation_actions,
    "concept_formats": knowledge.explain_supported_formats,
    "concept_budget_forecast": knowledge.explain_budget_vs_forecast,
    "concept_timing_permanent": knowledge.explain_timing_vs_permanent,
    "concept_operating_leverage": knowledge.explain_operating_leverage,
    "concept_kpis": knowledge.explain_kpis,
    "concept_budgeting_methods": knowledge.explain_budgeting_methods,
    "concept_ebitda_margin": knowledge.explain_ebitda_margin,
    "concept_bridge": knowledge.explain_variance_bridge,
    "comparison_types": knowledge.explain_comparison_types,
}


# Intent id -> handler for the exploring phase, built once rather than on every message.
_EXPLORING_HANDLERS: dict[str, Callable[[Session, ParsedIntent], Response]] = {
    "help": lambda session, intent: _handle_help(session),
    "reset": lambda session, intent: _handle_reset(session),
    "summary": lambda session, intent: _handle_summary(session),
    "material": lambda session, intent: _handle_material(session),
    "filter_status_u": lambda session, intent: _handle_filter_status(session, Status.UNFAVORABLE),
    "filter_status_f": lambda session, intent: _handle_filter_status(session, Status.FAVORABLE),
    "filter_type_rev": lambda session, intent: _handle_filter_type(session, LineType.REVENUE),
    "filter_type_exp": lambda session, intent: _handle_filter_type(session, LineType.EXPENSE),
    "filter_type_unc": lambda session, intent: _handle_filter_type(session, LineType.UNCLASSIFIED),
    "top_n": lambda session, intent: _handle_top_n(session, intent),
    "explain": lambda session, intent: _handle_explain(session, intent),
    "detail": lambda session, intent: _handle_detail(session, intent),
    "set_threshold": lambda session, intent: _handle_set_threshold(session, intent),
    "warnings": lambda session, intent: _handle_warnings(session),
    "recommendations": lambda session, intent: _handle_recommendations(session),
    "totals": lambda session, intent: _handle_totals(session),
    "full_report": lambda session, intent: _handle_full_report(session),
    "export_report": lambda session, intent: _handle_export_report(session, intent),
    "export_audit": lambda session, intent: _handle_export_audit(session, intent),
    "export_csv": lambda session, intent: _handle_export_csv(session, intent),
    "export_xlsx": lambda session, intent: _handle_export_xlsx(session, intent),
    # ── Advanced Analytics ──
    "waterfall": lambda session, intent: _handle_waterfall(session),
    "what_if": lambda session, intent: _handle_what_if(session, intent),
    "sensitivity": lambda session, intent: _handle_sensitivity(session),
    "run_rate": lambda session, intent: _handle_run_rate(session, intent),
    "biggest_risks": lambda session, intent: _handle_biggest_risks(session),
    "biggest_wins": lambda session, intent: _handle_biggest_wins(session),
    "revenue_status": lambda session, intent: _handle_revenue_status(session),
    "expense_status": lambda session, intent: _handle_expense_status(session),
    "budget_utilization": lambda session, intent: _handle_budget_utilization(session),
    "top_percent": lambda session, intent: _handle_top_percent(session),
    "metrics_count": lambda session, intent: _handle_metrics_count(session),
    "variance_concentration": lambda session, intent: _handle_concentration(session),
    "unbudgeted_spend": lambda session, intent: _handle_unbudgeted(session),
    "cost_savings": lambda session, intent: _handle_cost_savings(session),
    "revenue_misses": lambda session, intent: _handle_revenue_misses(session),
    "compare_items": lambda session, intent: _handle_compare(session, intent),
    "executive_memo": lambda session, intent: _handle_executive_memo(session),
    "driver_summary": lambda session, intent: _handle_driver_summary(session),
    "tldr": lambda session, intent: _handle_tldr(session),
    "profitability": lambda session, intent: _handle_profitability(session),
    "list_sheets": lambda session, intent: _handle_list_sheets(session),
    "switch_sheet": lambda session, intent: _handle_switch_sheet(session, intent),
}


@financial_context()
def _next_measure_question(session: Session) -> Response | None:
    for index, raw in enumerate(session.parsed_rows or []):
        row = normalize_row(raw)
        name = str(row.get("line_item", "Row"))
        kind = measure_kind(row.get("measure"), name)
        question: str | None = None
        chips: list[str] | None = None
        pending = ("", index)
        if kind in {MeasureKind.PERCENT, MeasureKind.COUNT} and not str(row.get("better") or "").strip():
            question = f"For **{safe_inline(name)}**, is Higher or Lower better?"
            chips, pending = ["Higher", "Lower"], ("better", index)
        elif kind is MeasureKind.PERCENT and session.percent_values is None:
            bare = [v for k, v in row.items()
                    if (k in {"budget", "actual"} or (session.earnings_mode and (
                        basis_for_header(k, extended=True) is not None or k in {
                            "guidance_low", "guidance_high", "guide_low", "guide_high", "low", "high", "dispersion", "std_dev",
                            "standard_deviation"})))
                    and not is_missing(v) and not str(v).strip().endswith("%")]
            if bare:
                example = parse_decimal(bare[0], field="Rate", line_item=name)
                percent = format(example * Decimal("100"), "f")
                if "." in percent:
                    percent = percent.rstrip("0").rstrip(".")
                question = (f"For **{safe_inline(name)}**, read {safe_inline(bare[0])} as {percent}%? "
                            "Confirm fractions, or keep bare numbers as percentage points.")
                chips = ["Read bare rates as fractions", "Read bare rates as percentage points"]
                pending = ("percent_values", index)
        if question is None:
            flag = {MeasureKind.PER_SHARE: "per_share_threshold", MeasureKind.COUNT: "count_threshold",
                    MeasureKind.PERCENT: "bps_threshold"}.get(kind)
            if flag is not None and getattr(session, flag) is None:
                unit = {MeasureKind.PER_SHARE: "currency per share", MeasureKind.COUNT: "units",
                        MeasureKind.PERCENT: "basis points"}[kind]
                question = f"What absolute threshold in {unit} should flag {kind} variances? Enter a non-negative number."
                pending = (flag, index)
        if question is not None:
            session.phase, session.measure_pending = Phase.AWAITING_MEASURE_OPTIONS, pending
            return Response(text=question, chips=chips, phase=session.phase)
    return None


def _handle_measure_option(session: Session, text: str) -> Response:
    pending = session.measure_pending
    assert pending is not None and session.parsed_rows is not None
    choice, index = pending
    lower = normalize_for_routing(text).lower()
    if choice == "better":
        if lower not in {"higher", "lower"}:
            return Response(text="Choose Higher or Lower for this measure.", chips=["Higher", "Lower"], phase=session.phase)
        row = normalize_row(session.parsed_rows[index])
        row["better"] = lower.capitalize()
        session.parsed_rows[index] = row
    elif choice == "percent_values":
        scales = {"read bare rates as fractions": "fractions", "read bare rates as percentage points": "points"}
        if lower not in scales:
            return Response(text="Choose how to read bare rates before the analysis.",
                            chips=list(scales), phase=session.phase)
        session.percent_values = scales[lower]
    else:
        try:
            value = parse_decimal(text, field="Threshold", line_item="Materiality")
            if value < 0:
                raise ValueError("Threshold must be non-negative.")
        except ValueError:
            return Response(text="Enter a non-negative numeric threshold, such as 25.", phase=session.phase)
        setattr(session, choice, value)
    session.measure_pending = None
    return _run_analysis(session)
