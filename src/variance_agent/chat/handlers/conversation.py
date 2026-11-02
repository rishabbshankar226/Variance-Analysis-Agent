"""Greetings, identity, knowledge answers and questions the chat can't route.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from variance_agent.models import LineType, Status
from .. import knowledge
from ..intent import find_line_item, normalize_for_routing
from ..responses import (
    Response,
    format_money,
    format_pct,
    format_threshold_amount,
    format_threshold_pct,
    report_places,
    row_to_table_dict,
    safe_inline,
)
from ..session import Phase, Session
from ._common import _heading, _is_budget, _noun
from ._items import _item_in_sentence, _items_named_in, _resolve_item_query
from .narrative import _handle_profitability


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


def _handle_greeting(session: Session) -> Response:
    """Respond politely to conversational greetings with context-aware guidance."""
    filing = session.intake_result is not None and session.intake_result.filing_headline is not None
    if session.phase == Phase.EXPLORING and session.result is not None and filing:
        return Response(text=f"I am ready to explore **{safe_inline(session.result.config.period)}** from this filing. "
                             "Type `summary` for its own printed totals, or drill into any line (e.g. "
                             f"`why {safe_inline(session.result.rows[0].line_item)}`).", phase=session.phase)
    if session.phase == Phase.EXPLORING and session.result is not None:
        cfg = session.result.config
        places = report_places(session.result)
        cur = cfg.currency
        net_impact = session.result.revenue.variance_dollars - session.result.expenses.variance_dollars
        status = "favorable beat" if net_impact >= 0 else "unfavorable shortfall"

        text = (
            f"I am ready to explore your **{cfg.period}** financial results.\n\n"
            f"Currently tracking **{cur}** with materiality set at **{format_threshold_amount(cfg.dollar_threshold, cur)} or {format_threshold_pct(cfg.percent_threshold)}**. "
            + (f"Overall net operating impact is **in line with** {_noun(cfg)}.\n\n" if net_impact == 0 else
               f"Overall net operating impact is a **{format_money(abs(net_impact), cur, places)} {status}** against {_noun(cfg)}.\n\n")
            +
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
