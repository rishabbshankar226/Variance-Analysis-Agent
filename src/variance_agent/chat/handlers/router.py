"""The message router: every reply starts here.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from variance_agent.audience import is_audience_result
from variance_agent.models import ComparisonBasis, LineType, Status
from variance_agent.report import render_markdown
from ..intent import KNOWLEDGE_INTENTS, MAX_ROUTING_CHARS, ParsedIntent, normalize_for_routing, parse_intent
from ..responses import Response
from ..session import Phase, Session
from ._common import _file_is_gone
from .summary import _COMPUTED_TOTALS, _STATEMENT_CHIPS, _filing_summary, _report_text
from .upload import _handle_build_ltm, _handle_covenant_headroom, _join_unbudgeted, _load_file, _looks_like_pasted_table
from .run import _handle_classify, _leave_total_out
from .workbook import _handle_hidden_rows, _handle_list_sheets, _handle_set_comparison, _handle_switch_sheet
from .setup import (
    _handle_blank_budget_confirmation,
    _handle_currency,
    _handle_intake_confirmation,
    _handle_measure_option,
    _handle_period,
    _handle_period_choice,
    _handle_thresholds,
)
from .export import (
    _handle_export_audit,
    _handle_export_csv,
    _handle_export_report,
    _handle_export_xlsx,
    _handle_save_mapping,
)
from .lookup import _handle_detail, _handle_explain
from .explore import (
    _handle_filter_status,
    _handle_filter_type,
    _handle_full_report,
    _handle_help,
    _handle_material,
    _handle_recommendations,
    _handle_reset,
    _handle_set_threshold,
    _handle_summary,
    _handle_top_n,
    _handle_totals,
    _handle_warnings,
)
from .status import (
    _handle_budget_utilization,
    _handle_cost_savings,
    _handle_expense_status,
    _handle_revenue_misses,
    _handle_revenue_status,
    _handle_unbudgeted,
)
from .rankings import (
    _handle_biggest_risks,
    _handle_biggest_wins,
    _handle_compare,
    _handle_concentration,
    _handle_metrics_count,
    _handle_top_percent,
)
from .scenarios import _handle_run_rate, _handle_sensitivity, _handle_waterfall, _handle_what_if
from .narrative import _handle_driver_summary, _handle_executive_memo, _handle_profitability, _handle_tldr
from .conversation import _handle_gratitude, _handle_greeting, _handle_identity, _handle_knowledge, _handle_unknown


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
    if session.pending_total_exclusion is not None and routing_key == (
            f"leave {normalize_for_routing(session.pending_total_exclusion).lower()} out"):
        return _leave_total_out(session)
    if session.pending_unbudgeted is not None and routing_key == (
            normalize_for_routing(session.pending_unbudgeted[4]).lower()):
        return _join_unbudgeted(session, first_visit)
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
        from ..earnings import request_review
        return request_review(session)
    if intent.intent_id in {"earnings_consensus", "earnings_margins", "earnings_guidance"}:
        from ..earnings import handle_question
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
            from ..earnings import explicit_comparison
            return explicit_comparison(session, ComparisonBasis(intent.captures["basis"]))
        if session.earnings_mode:
            from ..earnings import handle_review_choice
            return handle_review_choice(session, text)
        return _handle_set_comparison(session, intent)

    if routing_key in ("show technical details", "technical details"):
        detail = session.last_technical_detail or "No technical details recorded for the current step."
        return Response(
            text=f"**Technical Details:**\n```\n{detail}\n```",
            chips=["Upload a different file", "Help"],
            phase=session.phase,
        )

    if routing_key in {"build ltm", "build an ltm", "ltm"}:
        return _handle_build_ltm(session)
    reader = _reader_question(session, routing_key)
    if reader is not None:
        return reader
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
        from ..earnings import handle_review_choice
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


def _reader_question(session: Session, routing_key: str) -> Response | None:
    """The new readers' questions (PLAN.md Phase 6): a filing's statements, limits, targets, benchmarks."""
    for words, kind in (("balance sheet", "Balance Sheet"), ("cash flow", "Cash Flow")):
        if routing_key in {f"compare {words}s", f"compare the {words}", f"compare {words}"}:
            name = next((s for s in session.available_sheets if kind.lower() in s.lower()), None)
            if name is None:
                return Response(text=f"This file has no {words} to compare. Upload a 10-K or 10-Q from EDGAR, "
                                     "and I'll read its statements.", phase=session.phase)
            return handle_message(session, f"statement {name}")
    asks = {"which limits are breached": ("limit", "Limit", "a Limit column and each row's Limit Kind (Max or Min)"),
            "drift from target": ("target", "Target", "a Target column"),
            "active return": ("benchmark", "Benchmark", "a Benchmark column and each row's Better direction")}
    if routing_key in asks:
        basis, header, needs = asks[routing_key]
        if session.result is not None and session.result.config.comparison_basis.value == basis:
            return Response(text=_report_text(session), chips=list(_STATEMENT_CHIPS), phase=Phase.EXPLORING)
        return Response(text=f"Upload a file with Actual, {needs}, and I'll compare each row against its {header.lower()}.",
                        phase=session.phase)
    if routing_key in {"covenant headroom", "covenant compliance"}:
        return _handle_covenant_headroom(session)
    return None


def _handle_exploring(session: Session, text: str) -> Response:
    """Route a message through the intent parser during the EXPLORING phase."""
    if normalize_for_routing(text).lower() in ("save layout mapping", "save mapping"):
        return _handle_save_mapping(session)

    intent = parse_intent(text)
    if session.earnings_mode and session.table_analysis is not None:
        from ..earnings import explore
        return explore(session, intent.intent_id, intent.captures)
    if session.result is None:
        return _file_is_gone(session)

    if any(row.statement_kind or row.basis_details is not None or row.classification_source == "metric"
           for row in session.result.rows):
        # Each comparison's workbook has the sheets its report describes (N1).
        if intent.intent_id not in {"export_report", "export_audit", "export_xlsx", "help", "reset"}:
            return Response(text=_report_text(session), chips=list(_STATEMENT_CHIPS), phase=Phase.EXPLORING)
    if is_audience_result(session.result) and intent.intent_id not in {
        "summary", "material", "filter_favorable", "filter_unfavorable", "export_report", "export_audit", "export_xlsx",
    }:
        return Response(text=render_markdown(session.result),
                        chips=["Summary", "Material", "Export report", "Export Excel"], phase=Phase.EXPLORING)
    headline = session.intake_result.filing_headline if session.intake_result is not None else None
    if headline is not None and (intent.intent_id in _COMPUTED_TOTALS or (intent.intent_id == "compare_items" and {
            str(intent.captures.get(key, "")).strip().strip("'\"?").lower() for key in ("item1", "item2")}
            & {"actual", "actuals", "act", "budget", "budgeted", "plan", "target", "targets", "bgt"})):
        return _filing_summary(session, headline)
    handler = _EXPLORING_HANDLERS.get(intent.intent_id)
    if handler is not None:
        return handler(session, intent)

    return _handle_unknown(session, text)


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
