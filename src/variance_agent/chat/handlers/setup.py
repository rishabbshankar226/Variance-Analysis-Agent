"""The guided questions: how the file was read, the period, thresholds, currency and measures.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

import re
from variance_agent.parsing import normalize_row
from variance_agent.comparison import zero_comparison_phrase
from variance_agent.currencies import validate_currency
from variance_agent.models import ComparisonBasis
from variance_agent.parsing import parse_decimal
from variance_agent.intake import read_input_assisted
from ..intent import ParsedIntent, normalize_for_routing, parse_intent
from ..responses import Response, format_threshold_amount, format_threshold_pct, safe_inline
from ..session import Phase, Session
from ._common import _ask_period, _choosable, _file_is_gone, _sheet_chip, _sheet_word
from ._thresholds import _parse_threshold_text
from .upload import _blank_wording, _intake_confirmation
from .run import _run_analysis
from .workbook import _handle_switch_sheet


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
        return _ask_period(session)

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

            return _ask_period(session, f"Loaded '{safe_inline(session.source_name or 'file')}' ({row_count} data "
                                        f"row{'s' if row_count != 1 else ''}){worksheet_note}.\n\n")

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


# ---------------------------------------------------------------------------
# Configuration phase handlers
# ---------------------------------------------------------------------------


def _clean_period_input(text: str) -> str:
    """Extract clean reporting period from conversational user input."""
    cleaned = text.strip()
    prefix_pattern = re.compile(
        # "Period ended September 30, 2026" is itself a period, not a lead-in to one (X35).
        r"^(?:(?:this\s+is|it\s+is|it\'s|the\s+period\s+is|period(?!\s+end(?:ed|ing)\b)\s*(?:is|:)?|covers?|for)\s+)+",
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
