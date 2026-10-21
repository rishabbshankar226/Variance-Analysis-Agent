"""Deterministic handler functions for each chatbot intent.

Each handler receives the Session (which holds the AnalysisResult) and
any regex captures from the intent parser.  All financial values come
from the deterministic engine; handlers only perform lookups and
formatting.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from decimal import Decimal, Inexact, InvalidOperation
from pathlib import Path

from variance_agent.analysis import analyze_rows
from variance_agent.audit import build_audit_record, serialize_audit_json, sha256_bytes
from variance_agent.currencies import CURRENCY_SYMBOLS, validate_currency
from variance_agent.limits import display_text
from variance_agent.models import AnalysisConfig, AnalyzedRow, LineType, Status
from variance_agent.numeric import financial_context, ratio
from variance_agent.output import write_text_outputs
from variance_agent.parsing import (
    get_workbook_sheets,
    load_input,
    parse_decimal,
    validate_input_format,
)
from variance_agent.report import render_markdown

from .intent import KNOWLEDGE_INTENTS, ParsedIntent, find_line_item, parse_intent
from .responses import (
    Response,
    format_money,
    format_pct,
    report_places,
    row_to_table_dict,
    safe_inline,
    status_label,
)
from .session import Phase, Session


# ---------------------------------------------------------------------------
# Phase-based message routing
# ---------------------------------------------------------------------------


def handle_message(session: Session, text: str) -> Response:
    """Top-level router: dispatch based on conversation phase and domain intents."""
    text = text.strip()
    if not text:
        return Response(text="Please type a message or upload a file.")

    intent = parse_intent(text)
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
    if intent.intent_id in KNOWLEDGE_INTENTS:
        return _handle_knowledge(session, intent.intent_id)
    if intent.intent_id == "list_sheets":
        return _handle_list_sheets(session)
    if intent.intent_id == "switch_sheet":
        return _handle_switch_sheet(session, intent)

    if session.phase == Phase.AWAITING_FILE:
        return Response(
            text="Please upload a file using the drop zone above. "
                 "Supported formats: CSV, JSON, XLSX, XLSM.",
            phase=session.phase,
        )

    if session.phase == Phase.AWAITING_PERIOD:
        return _handle_period(session, text)

    if session.phase == Phase.AWAITING_THRESHOLDS:
        return _handle_thresholds(session, text)

    if session.phase == Phase.AWAITING_CURRENCY:
        return _handle_currency(session, text)

    if session.phase == Phase.RESOLVE_UNCLASSIFIED:
        return _handle_classify(session, text)

    # Phase.EXPLORING
    return _handle_exploring(session, text)


def handle_upload(
    session: Session, file_bytes: bytes, filename: str, sheet: str | None = None,
) -> Response:
    """Process a file upload and advance the session state."""
    suffix = Path(filename).suffix.lower()
    try:
        validate_input_format(suffix)
        parsed = load_input(file_bytes, suffix, source_name=filename, sheet=sheet)
    except (ValueError, RuntimeError, OSError) as exc:
        return Response(
            text=f"⚠️ {display_text(str(exc))}",
            chips=["Upload a different file"],
            phase=Phase.AWAITING_FILE,
        )

    if not parsed.rows:
        return Response(
            text=f"⚠️ The uploaded file '{safe_inline(filename)}' contains no data rows. "
                 "Please upload a file with at least one row of budget and actual data.",
            chips=["Upload a different file"],
            phase=Phase.AWAITING_FILE,
        )

    session.source_bytes = file_bytes
    session.source_name = filename
    session.source_suffix = suffix
    session.parsed_rows = parsed.rows
    session.worksheet = parsed.worksheet
    session.available_sheets = list(parsed.sheetnames)
    session.phase = Phase.AWAITING_PERIOD

    row_count = len(parsed.rows)
    worksheet_note = ""
    if parsed.worksheet:
        worksheet_note = f" from worksheet '{safe_inline(parsed.worksheet)}'"
        if len(session.available_sheets) > 1:
            worksheet_note += f" ({len(session.available_sheets)} sheets available; switch with `sheet <name>`)"

    return Response(
        text=f"✅ Loaded '{safe_inline(filename)}' ({row_count} data row{'s' if row_count != 1 else ''}){worksheet_note}.\n\n"
             "What reporting period does this analysis cover? (e.g., Q3 2026, October 2026, FY2026)",
        phase=Phase.AWAITING_PERIOD,
    )


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


def _handle_period(session: Session, text: str) -> Response:
    """Accept the reporting period."""
    period = _clean_period_input(text)
    if not period:
        return Response(
            text="The reporting period cannot be blank. Please enter a period (e.g., Q3 2026).",
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
    if raw_lower in ("last", "last item", "last one", "last row", "last line", "bottom", "bottom one", "lowest"):
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


def _handle_thresholds(session: Session, text: str) -> Response:
    """Parse and set materiality thresholds."""
    parsed = _parse_threshold_text(text)
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
        text=f"Thresholds set: **{CURRENCY_SYMBOLS.get(session.currency, '$')}"
             f"{dollar:,.2f}** or **{pct_ratio * 100:.1f}%**\n\n"
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
    currency = _clean_currency_input(text)
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
    assert session.parsed_rows is not None
    assert session.period is not None
    assert session.dollar_threshold is not None
    assert session.percent_threshold is not None

    config = AnalysisConfig(
        period=session.period,
        dollar_threshold=session.dollar_threshold,
        percent_threshold=session.percent_threshold,
        type_map=dict(session.type_map),
        currency=session.currency,
    )

    try:
        with financial_context():
            result = analyze_rows(session.parsed_rows, config)
    except (ValueError, RuntimeError) as exc:
        return Response(
            text=f"⚠️ Analysis failed: {display_text(str(exc))}",
            chips=["Upload a different file", "Help"],
            phase=Phase.AWAITING_FILE,
        )

    session.result = result

    # Check for unclassified rows
    unclassified = [
        row.line_item for row in result.rows
        if row.line_type == LineType.UNCLASSIFIED
    ]

    if unclassified:
        session.unclassified_queue = list(unclassified)
        session.phase = Phase.RESOLVE_UNCLASSIFIED
        item = safe_inline(session.unclassified_queue[0])
        remaining = len(session.unclassified_queue)
        return Response(
            text=f"Analysis complete, but **{remaining}** line item{'s are' if remaining != 1 else ' is'} unclassified.\n\n"
                 f"**'{item}'** is Unclassified. Should it be:",
            chips=["Revenue", "Expense", "Skip", "Skip all"],
            phase=Phase.RESOLVE_UNCLASSIFIED,
        )

    session.phase = Phase.EXPLORING
    return _build_analysis_summary(session)


def _handle_classify(session: Session, text: str) -> Response:
    """Handle classification of an unclassified line item."""
    text_lower = text.strip().lower()

    if text_lower in ("skip all", "done", "skip remaining"):
        session.unclassified_queue.clear()
        session.phase = Phase.EXPLORING
        return _run_analysis(session) if session.type_map else _build_analysis_summary(session)

    if not session.unclassified_queue:
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
        session.unclassified_queue.pop(0)
    else:
        return Response(
            text=f"Please choose Revenue, Expense, or Skip for '{safe_inline(current_item)}'.",
            chips=["Revenue", "Expense", "Skip", "Skip all"],
            phase=Phase.RESOLVE_UNCLASSIFIED,
        )

    if session.unclassified_queue:
        next_item = safe_inline(session.unclassified_queue[0])
        remaining = len(session.unclassified_queue)
        return Response(
            text=f"Got it. {remaining} remaining.\n\n"
                 f"**'{next_item}'** is Unclassified. Should it be:",
            chips=["Revenue", "Expense", "Skip", "Skip all"],
            phase=Phase.RESOLVE_UNCLASSIFIED,
        )

    # All resolved — re-run analysis with updated type_map
    return _run_analysis(session)


def _build_analysis_summary(session: Session) -> Response:
    """Build the initial analysis summary after successful analysis."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)
    symbol = CURRENCY_SYMBOLS[cfg.currency]

    lines = [
        "✅ **Analysis Complete**\n",
        f"**Period:** {safe_inline(cfg.period)}",
        f"**Currency:** {cfg.currency}",
        f"**Thresholds:** {symbol}{cfg.dollar_threshold:,.2f} or "
        f"{cfg.percent_threshold * 100:.1f}%\n",
    ]

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

    if has_revenue and not classification_incomplete:
        lines.append(
            f"**Total Revenue:** {format_money(result.revenue.actual, cfg.currency, places)} vs. "
            f"{format_money(result.revenue.budget, cfg.currency, places)} "
            f"({format_money(result.revenue.variance_dollars, cfg.currency, places)}, "
            f"{format_pct(result.revenue.budget, result.revenue.variance_dollars, result.revenue.percent_label)}, "
            f"{status_label(result.revenue.status)})"
        )
    elif classification_incomplete:
        lines.append("**Total Revenue:** N/A (classification incomplete)")
    else:
        lines.append("**Total Revenue:** N/A (no Revenue rows)")

    if has_expenses and not classification_incomplete:
        lines.append(
            f"**Total Expenses:** {format_money(result.expenses.actual, cfg.currency, places)} vs. "
            f"{format_money(result.expenses.budget, cfg.currency, places)} "
            f"({format_money(result.expenses.variance_dollars, cfg.currency, places)}, "
            f"{format_pct(result.expenses.budget, result.expenses.variance_dollars, result.expenses.percent_label)}, "
            f"{status_label(result.expenses.status)})"
        )
    elif classification_incomplete:
        lines.append("**Total Expenses:** N/A (classification incomplete)")
    else:
        lines.append("**Total Expenses:** N/A (no Expense rows)")

    # Net operating impact
    if not classification_incomplete and has_revenue and has_expenses:
        with financial_context():
            net_impact = result.revenue.variance_dollars - result.expenses.variance_dollars
        direction = "above" if net_impact > 0 else "below" if net_impact < 0 else "in line with"
        lines.append(
            f"\n**Net Operating Impact:** {format_money(net_impact, cfg.currency, places)}, "
            f"{direction} budget"
        )
    else:
        lines.append("\n**Net Operating Impact:** N/A")

    material_count = len(result.material_rows)
    lines.append(f"\n**{material_count}** material variance{'s' if material_count != 1 else ''} found.")

    if result.warnings:
        lines.append(f"\n⚠️ {len(result.warnings)} data quality warning{'s' if len(result.warnings) != 1 else ''}.")

    text = "\n".join(lines)

    # Build table of material variances
    table = None
    if result.material_rows:
        session.last_table_items = [r.line_item for r in result.material_rows]
        session.last_focused_item = session.last_table_items[0]
        table = [
            row_to_table_dict(row, cfg.currency, places)
            for row in result.material_rows
        ]

    # Suggest useful next actions
    chips = []
    if result.material_rows:
        first_item = result.material_rows[0].line_item
        chips.append(f"Why {first_item}?")
    chips.extend(["Show unfavorable", "Summary", "Export report"])
    if result.warnings:
        chips.append("Warnings")

    return Response(text=text, table=table, chips=chips, phase=Phase.EXPLORING)


# ---------------------------------------------------------------------------
# Exploring phase handlers
# ---------------------------------------------------------------------------


def _handle_exploring(session: Session, text: str) -> Response:
    """Route a message through the intent parser during the EXPLORING phase."""
    intent = parse_intent(text)
    result = session.result
    assert result is not None

    handler_map: dict[str, Callable[[], Response]] = {
        "help": lambda: _handle_help(session),
        "reset": lambda: _handle_reset(session),
        "summary": lambda: _handle_summary(session),
        "material": lambda: _handle_material(session),
        "filter_status_u": lambda: _handle_filter_status(session, Status.UNFAVORABLE),
        "filter_status_f": lambda: _handle_filter_status(session, Status.FAVORABLE),
        "filter_type_rev": lambda: _handle_filter_type(session, LineType.REVENUE),
        "filter_type_exp": lambda: _handle_filter_type(session, LineType.EXPENSE),
        "filter_type_unc": lambda: _handle_filter_type(session, LineType.UNCLASSIFIED),
        "top_n": lambda: _handle_top_n(session, intent),
        "explain": lambda: _handle_explain(session, intent),
        "detail": lambda: _handle_detail(session, intent),
        "set_threshold": lambda: _handle_set_threshold(session, intent),
        "warnings": lambda: _handle_warnings(session),
        "recommendations": lambda: _handle_recommendations(session),
        "totals": lambda: _handle_totals(session),
        "full_report": lambda: _handle_full_report(session),
        "export_report": lambda: _handle_export_report(session, intent),
        "export_audit": lambda: _handle_export_audit(session, intent),
        "export_csv": lambda: _handle_export_csv(session, intent),
        # ── Advanced Analytics ──
        "waterfall": lambda: _handle_waterfall(session),
        "what_if": lambda: _handle_what_if(session, intent),
        "sensitivity": lambda: _handle_sensitivity(session),
        "run_rate": lambda: _handle_run_rate(session, intent),
        "biggest_risks": lambda: _handle_biggest_risks(session),
        "biggest_wins": lambda: _handle_biggest_wins(session),
        "revenue_status": lambda: _handle_revenue_status(session),
        "expense_status": lambda: _handle_expense_status(session),
        "budget_utilization": lambda: _handle_budget_utilization(session),
        "top_percent": lambda: _handle_top_percent(session),
        "metrics_count": lambda: _handle_metrics_count(session),
        "variance_concentration": lambda: _handle_concentration(session),
        "unbudgeted_spend": lambda: _handle_unbudgeted(session),
        "cost_savings": lambda: _handle_cost_savings(session),
        "revenue_misses": lambda: _handle_revenue_misses(session),
        "compare_items": lambda: _handle_compare(session, intent),
        "executive_memo": lambda: _handle_executive_memo(session),
        "driver_summary": lambda: _handle_driver_summary(session),
        "tldr": lambda: _handle_tldr(session),
        "profitability": lambda: _handle_profitability(session),
        "list_sheets": lambda: _handle_list_sheets(session),
        "switch_sheet": lambda: _handle_switch_sheet(session, intent),
    }

    handler = handler_map.get(intent.intent_id)
    if handler is not None:
        return handler()

    return _handle_unknown(session, text)


def _handle_help(session: Session) -> Response:
    """Show available commands."""
    text = (
        "**Available Commands & Intelligence:**\n\n"
        "**FP&A Analysis & Insights:**\n"
        "• `memo` / `briefing` — Executive Management Briefing & Commentary for CFO/Board (with download)\n"
        "• `waterfall` / `bridge` — Reconciles Budget to Actual Operating Profit step-by-step\n"
        "• `what if [target] [+/-X% or $Y]` — Scenario simulation on profit & margin\n"
        "• `sensitivity` — 5-point stress-test matrix across revenue and expense deviations\n"
        "• `run rate` / `project year end` — Annualized pace and Latest Estimate (LE) projections\n"
        "• `drivers` / `driver summary` — Overview of causal driver models and reconciliation coverage\n"
        "• `biggest risks` — Top material unfavorable variances and mitigation advice\n"
        "• `biggest wins` — Top positive variances and revenue overperformance\n"
        "• `revenue status` — Did we hit revenue targets? Line-by-line beat/miss\n"
        "• `expense status` — Did expenses stay in budget? Top overspend lines\n"
        "• `burn rate` / `budget utilization` — % of expense budget spent\n"
        "• `variance concentration` / `pareto` — % of volatility driven by top 3 accounts\n"
        "• `unbudgeted spend` — Items with actual spend but $0.00 budget\n"
        "• `cost savings` — Accounts operating below planned expense budget\n"
        "• `revenue misses` — Revenue lines that fell short of plan\n"
        "• `highest percent` — Line items with largest relative percentage swings\n"
        "• `compare [item1] vs [item2]` — Side-by-side line comparison or macro (actual vs budget, rev vs exp)\n"
        "• `sheets` / `sheet <name>` — View and switch between Excel worksheets\n"
        "• `metrics` — Total accounts, materiality rate, and portfolio breakdown\n\n"
        "**Financial Concepts & Education (Ask Anytime):**\n"
        "• `what is materiality?` — Dual-threshold noise reduction logic\n"
        "• `favorable vs unfavorable` — Sign conventions for revenue vs. expense\n"
        "• `what is net impact?` — Net operating income formula\n"
        "• `budget vs forecast` — AOP vs. Latest Estimate baseline principles\n"
        "• `timing vs permanent` — Reversible accounting shifts vs. structural run-rates\n"
        "• `operating leverage` — Fixed vs. variable costs and drop-through\n"
        "• `what are financial kpis?` — Key variance performance indicators\n"
        "• `what is driver decomposition?` — Price vs. volume causal analysis\n"
        "• `audit trail` — Cryptographic SHA-256 provenance standards\n\n"
        "**Standard Exploration:**\n"
        "• `summary` — Executive summary with net operating impact\n"
        "• `material` — Show all material variances\n"
        "• `unfavorable` / `favorable` — Filter by status\n"
        "• `revenue` / `expenses` — Filter by type\n"
        "• `top 3` — Show top N variances by absolute amount\n"
        "• `totals` — Aggregate revenue and expense totals\n"
        "• `warnings` — Data quality alerts\n"
        "• `recommendations` — Actionable mitigation & optimization steps\n\n"
        "**Drill Down & Adjustment:**\n"
        "• `why [item]` — Driver breakdown for a line item\n"
        "• `detail [item]` — Full detail for a line item\n"
        "• `threshold $X or Y%` — Re-run analysis with adjusted thresholds\n\n"
        "**Export & Session:**\n"
        "• `export report` — Download Markdown report\n"
        "• `export audit` — Download audit JSON\n"
        "• `report` — View full report inline\n"
        "• `new` — Start over with a new file\n"
        "• `help` — Show this guide"
    )
    return Response(
        text=text,
        chips=["Summary", "Biggest risks", "Biggest wins", "Material"],
        phase=Phase.EXPLORING,
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
        row_to_table_dict(row, cfg.currency, places)
        for row in result.material_rows
    ]

    chips = []
    if result.material_rows:
        chips.append(f"Why {result.material_rows[0].line_item}?")
    chips.extend(["Unfavorable", "Favorable", "Export report"])

    return Response(
        text=f"**Material Variances** (Threshold: {CURRENCY_SYMBOLS[cfg.currency]}"
             f"{cfg.dollar_threshold:,.2f} or {cfg.percent_threshold * 100:.1f}%)",
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

    filtered = [row for row in result.rows if row.status == status]
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

    table = [row_to_table_dict(row, cfg.currency, places) for row in filtered]

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

    filtered = [row for row in result.rows if row.line_type == line_type]

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

    table = [row_to_table_dict(row, cfg.currency, places) for row in filtered]

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
    count = max(1, min(count, len(result.rows)))

    sorted_rows = sorted(result.rows, key=lambda r: abs(r.variance_dollars), reverse=True)
    top = sorted_rows[:count]
    session.last_table_items = [row.line_item for row in top]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [row_to_table_dict(row, cfg.currency, places) for row in top]

    return Response(
        text=f"**Top {count} Variances by Absolute Amount**",
        table=table,
        chips=[f"Why {top[0].line_item}?", "Material", "Summary"],
        phase=Phase.EXPLORING,
    )


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

    if not matches:
        items_list = ", ".join(safe_inline(item) for item in all_items)
        display_q = safe_inline(raw_query or item_query or "unspecified item")
        return Response(
            text=f"No line item matching '{display_q}' was found.\n\n"
                 f"Available items: {items_list}",
            phase=Phase.EXPLORING,
        )

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
    row = next(r for r in result.rows if r.line_item == matched_name)

    lines = [
        f"**Driver Evidence: {safe_inline(row.line_item)}**\n",
        f"Budget: {format_money(row.budget, cfg.currency, places)}",
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
            f"to Budget/Actual. Validate the driver data first."
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
        text="\n".join(lines),
        chips=chips,
        phase=Phase.EXPLORING,
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

    if not matches:
        display_q = safe_inline(raw_query or item_query or "unspecified item")
        return Response(
            text=f"No line item matching '{display_q}' was found.",
            phase=Phase.EXPLORING,
        )

    if len(matches) > 1:
        chips = [f"Detail {m}" for m in matches[:5]]
        return Response(
            text="Multiple matches:\n" + "\n".join(f"• {safe_inline(m)}" for m in matches),
            chips=chips,
            phase=Phase.EXPLORING,
        )

    matched_name = matches[0]
    session.last_focused_item = matched_name
    row = next(r for r in result.rows if r.line_item == matched_name)

    lines = [
        f"**{safe_inline(row.line_item)}**\n",
        f"• Type: {row.line_type}",
        f"• Budget: {format_money(row.budget, cfg.currency, places)}",
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
            response = Response(
                text=response.text + "\n\n" + "\n".join(changes),
                table=response.table,
                chips=response.chips,
                download=response.download,
                phase=response.phase,
            )

    return response


def _handle_warnings(session: Session) -> Response:
    """Show data quality warnings."""
    result = session.result
    assert result is not None

    if not result.warnings:
        return Response(
            text="✅ No data quality warnings.",
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
                    f"• **Mitigation:** Focus the action plan for {safe_inline(unfavorable.line_item)} "
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
                f"• **Optimization:** Focus the action plan for {safe_inline(favorable.line_item)} "
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
            f"{format_money(rev.budget, cfg.currency, places)} budget = "
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
            f"{format_money(exp.budget, cfg.currency, places)} budget = "
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
        chips=["Export report", "Export audit"],
        phase=Phase.EXPLORING,
    )


def _path_export_disabled(path: str, intent: ParsedIntent) -> Response:
    """Refuse a server-side write on hosted deployments and point to the download."""
    chip = {"export_audit": "Export audit", "export_csv": "Export csv"}.get(
        intent.intent_id, "Export report"
    )
    return Response(
        text=(f"⚠️ Saving to `{safe_inline(path)}` is turned off on this hosted version. "
              f"Use **{chip}** to download the file instead."),
        chips=[chip],
        phase=Phase.EXPLORING,
    )


def _handle_export_report(session: Session, intent: ParsedIntent) -> Response:
    """Generate the Markdown report for download."""
    result = session.result
    assert result is not None

    report = render_markdown(result)
    period_slug = result.config.period.replace(" ", "_").lower()
    filename = f"variance_report_{period_slug}.md"

    path = intent.captures.get("path")
    if path and not session.path_exports_enabled:
        return _path_export_disabled(path, intent)
    if path:
        try:
            write_text_outputs({Path(path): report})
            return Response(
                text=f"✅ Report written to `{safe_inline(path)}`.",
                chips=["Export audit", "Summary"],
                phase=Phase.EXPLORING,
            )
        except (ValueError, OSError) as exc:
            return Response(
                text=f"⚠️ Could not write to '{safe_inline(path)}': {display_text(str(exc))}",
                chips=["Export report"],
                phase=Phase.EXPLORING,
            )

    return Response(
        text="📄 Markdown report ready for download.",
        download={filename: report},
        chips=["Export audit", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_export_audit(session: Session, intent: ParsedIntent) -> Response:
    """Generate the audit JSON for download."""
    result = session.result
    assert result is not None

    source_hash = sha256_bytes(session.source_bytes) if session.source_bytes else None
    record = build_audit_record(
        result,
        source_name=session.source_name,
        source_sha256=source_hash,
        source_worksheet=session.worksheet,
    )
    audit_json = serialize_audit_json(record)
    period_slug = result.config.period.replace(" ", "_").lower()
    filename = f"variance_audit_{period_slug}.json"

    path = intent.captures.get("path")
    if path and not session.path_exports_enabled:
        return _path_export_disabled(path, intent)
    if path:
        try:
            write_text_outputs({Path(path): audit_json})
            return Response(
                text=f"✅ Audit JSON written to `{safe_inline(path)}`.",
                chips=["Export report", "Summary"],
                phase=Phase.EXPLORING,
            )
        except (ValueError, OSError) as exc:
            return Response(
                text=f"⚠️ Could not write to '{safe_inline(path)}': {display_text(str(exc))}",
                chips=["Export audit"],
                phase=Phase.EXPLORING,
            )

    return Response(
        text="📋 Audit JSON ready for download.",
        download={filename: audit_json},
        chips=["Export report", "Summary"],
        phase=Phase.EXPLORING,
    )


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
        f"Budget ({cfg.currency})",
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
            row.line_item,
            row.line_type.value,
            str(row.budget),
            str(row.actual),
            str(row.variance_dollars),
            format_pct(row.budget, row.variance_dollars, row.percent_label),
            row.status.value,
            "Yes" if row.material else "No",
            "Yes" if row.excluded_from_aggregation else "No",
            row.classification_source,
            driver_desc,
        ])

    csv_text = output.getvalue()
    period_slug = result.config.period.replace(" ", "_").lower()
    filename = f"variance_data_{period_slug}.csv"

    path = intent.captures.get("path")
    if path and not session.path_exports_enabled:
        return _path_export_disabled(path, intent)
    if path:
        try:
            write_text_outputs({Path(path): csv_text})
            return Response(
                text=f"✅ Analysis CSV written to `{safe_inline(path)}`.",
                chips=["Export report", "Export audit", "Summary"],
                phase=Phase.EXPLORING,
            )
        except (ValueError, OSError) as exc:
            return Response(
                text=f"⚠️ Could not write to '{safe_inline(path)}': {display_text(str(exc))}",
                chips=["Export csv"],
                phase=Phase.EXPLORING,
            )

    return Response(
        text="📊 Analysis CSV ready for download.",
        download={filename: csv_text},
        chips=["Export report", "Export audit", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_knowledge(session: Session, intent_id: str) -> Response:
    """Answer financial domain questions with FP&A precision."""
    from .knowledge import (
        explain_audit_trail,
        explain_budget_vs_forecast,
        explain_budgeting_methods,
        explain_drivers,
        explain_favorable_unfavorable,
        explain_kpis,
        explain_materiality,
        explain_mitigation_actions,
        explain_net_impact,
        explain_operating_leverage,
        explain_supported_formats,
        explain_timing_vs_permanent,
        explain_unclassified,
        explain_variance_analysis,
        explain_ebitda_margin,
        explain_variance_bridge,
    )

    explanations: dict[str, str] = {
        "concept_variance": explain_variance_analysis(),
        "concept_f_vs_u": explain_favorable_unfavorable(),
        "concept_fav": explain_favorable_unfavorable(),
        "concept_unfav": explain_favorable_unfavorable(),
        "concept_materiality": explain_materiality(),
        "concept_net_impact": explain_net_impact(),
        "concept_drivers": explain_drivers(),
        "concept_unclassified": explain_unclassified(),
        "concept_audit": explain_audit_trail(),
        "concept_actions": explain_mitigation_actions(),
        "concept_formats": explain_supported_formats(),
        "concept_budget_forecast": explain_budget_vs_forecast(),
        "concept_timing_permanent": explain_timing_vs_permanent(),
        "concept_operating_leverage": explain_operating_leverage(),
        "concept_kpis": explain_kpis(),
        "concept_budgeting_methods": explain_budgeting_methods(),
        "concept_ebitda_margin": explain_ebitda_margin(),
        "concept_bridge": explain_variance_bridge(),
    }

    text = explanations.get(intent_id, explain_variance_analysis())

    # If currently in a guided setup phase, provide a helpful prompt to continue
    chips = ["Summary", "Material", "Biggest risks", "Help"]
    if session.phase == Phase.AWAITING_FILE:
        text += (
            "\n\n---\n"
            "📁 **Next Step:** Upload your financial file (CSV, JSON, XLSX, or XLSM) using the drop zone above to begin."
        )
        chips = ["Supported file formats", "What is materiality?"]
    elif session.phase == Phase.AWAITING_PERIOD:
        text += (
            "\n\n---\n"
            f"📅 **Next Step:** What reporting period does '{safe_inline(session.source_name or 'your file')}' cover? "
            "(e.g., `Q3 2026`, `October 2026`, `FY2026`)"
        )
        chips = ["Q3 2026", "FY2026", "October 2026"]
    elif session.phase == Phase.AWAITING_THRESHOLDS:
        text += (
            "\n\n---\n"
            "🎯 **Next Step:** Please enter your materiality thresholds (e.g., `$10,000 or 5%`) or pick a preset below:"
        )
        chips = ["$5,000 or 3%", "$10,000 or 5%", "$25,000 or 10%", "$50,000 or 15%"]
    elif session.phase == Phase.AWAITING_CURRENCY:
        text += (
            "\n\n---\n"
            "💱 **Next Step:** What is the reporting currency for this analysis?"
        )
        chips = ["USD", "EUR", "GBP"]
    elif session.phase == Phase.RESOLVE_UNCLASSIFIED:
        current_item = safe_inline(session.unclassified_queue[0]) if session.unclassified_queue else ""
        text += (
            "\n\n---\n"
            f"🏷️ **Next Step:** Classify '{current_item}': is it Revenue, Expense, or Skip?"
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
            text="✅ **No Material Risks Detected**\n\n"
                 "There are zero material unfavorable variances exceeding your thresholds "
                 f"({CURRENCY_SYMBOLS.get(cfg.currency, '$')}{cfg.dollar_threshold:,.2f} or "
                 f"{cfg.percent_threshold * 100:.1f}%). All revenue targets and expense allocations "
                 "performed within budget tolerance.",
            chips=["Summary", "Biggest wins", "Show all material"],
            phase=Phase.EXPLORING,
        )

    lines = [
        f"🚨 **Top Financial Risks ({len(unfavorable)} material unfavorable item{'s' if len(unfavorable) != 1 else ''})**\n\n"
        "These line items represent the most significant negative deviations from budget:\n"
    ]

    for i, row in enumerate(unfavorable[:3], start=1):
        driver_status = "No driver breakdown"
        if row.driver_evidence is not None:
            driver_status = "Supported causal model" if row.driver_evidence.reconciles else "Hypothesis (unreconciled)"

        type_label = "Revenue shortfall" if row.line_type == LineType.REVENUE else "Cost overrun"
        lines.append(
            f"**{i}. {safe_inline(row.line_item)}** ({type_label})\n"
            f"• Actual: {format_money(row.actual, cfg.currency, places)} vs. Budget: {format_money(row.budget, cfg.currency, places)}\n"
            f"• Variance: **{format_money(row.variance_dollars, cfg.currency, places)}** ({format_pct(row.budget, row.variance_dollars, row.percent_label)})\n"
            f"• Evidence: *{driver_status}*\n"
        )

    lines.append(
        "💡 **Recommended Action:** Focus operational reviews on the #1 variance. "
        f"Ask `why {safe_inline(unfavorable[0].line_item)}` to inspect causal drivers."
    )

    chips = [f"Why {unfavorable[0].line_item}?"]
    if len(unfavorable) > 1:
        chips.append(f"Why {unfavorable[1].line_item}?")
    chips.extend(["Action playbook", "Summary"])

    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


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
            text="ℹ️ **No Material Favorable Variances**\n\n"
                 "No line items exceeded the favorable materiality thresholds. "
                 "Check `summary` or lower thresholds with `threshold $X or Y%` to explore smaller variances.",
            chips=["Summary", "Biggest risks", "Material"],
            phase=Phase.EXPLORING,
        )

    lines = [
        f"🏆 **Top Positive Performers ({len(favorable)} material favorable item{'s' if len(favorable) != 1 else ''})**\n\n"
        "These line items drove the strongest positive operating performance:\n"
    ]

    for i, row in enumerate(favorable[:3], start=1):
        nature = "Revenue beat" if row.line_type == LineType.REVENUE else "Cost savings / underspend"
        lines.append(
            f"**{i}. {safe_inline(row.line_item)}** ({nature})\n"
            f"• Actual: {format_money(row.actual, cfg.currency, places)} vs. Budget: {format_money(row.budget, cfg.currency, places)}\n"
            f"• Favorable Variance: **{format_money(row.variance_dollars, cfg.currency, places)}** ({format_pct(row.budget, row.variance_dollars, row.percent_label)})\n"
        )

    lines.append("💡 **Finance Insight:** For cost underspend, verify whether savings are permanent operational efficiencies or simply deferred spend (timing differences).")

    chips = [f"Why {favorable[0].line_item}?", "Summary", "Biggest risks"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_revenue_status(session: Session) -> Response:
    """Analyze revenue performance against budget target."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    revenue_rows = [
        r for r in result.rows
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
            text="⚠️ Total revenue cannot be certified because there are still unclassified line items. Classify them first.",
            chips=["Unclassified", "Summary"],
            phase=Phase.EXPLORING,
        )

    rev = result.revenue
    beat = rev.actual >= rev.budget
    diff = rev.actual - rev.budget

    if beat:
        verdict = f"🎯 **Revenue Target Achieved: Beat Budget by {format_money(diff, cfg.currency, places)} ({format_pct(rev.budget, rev.variance_dollars, rev.percent_label)})**"
    else:
        verdict = f"⚠️ **Revenue Target Missed: Shortfall of {format_money(abs(diff), cfg.currency, places)} ({format_pct(rev.budget, rev.variance_dollars, rev.percent_label)})**"

    lines = [
        verdict + "\n",
        f"• **Budgeted Revenue:** {format_money(rev.budget, cfg.currency, places)}",
        f"• **Actual Revenue:** {format_money(rev.actual, cfg.currency, places)}",
    ]
    if rev.budget != 0:
        rate = ratio(rev.actual, rev.budget) * Decimal("100")
        lines.append(f"• **Achievement Rate:** {rate:.1f}% of budget")
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
        r for r in result.rows
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
            text="⚠️ Total expenses cannot be certified because there are still unclassified line items.",
            chips=["Unclassified", "Summary"],
            phase=Phase.EXPLORING,
        )

    exp = result.expenses
    under_budget = exp.actual <= exp.budget
    diff = exp.actual - exp.budget

    if under_budget:
        verdict = f"✅ **Expenses Remained Under Budget: Saved {format_money(abs(diff), cfg.currency, places)} ({format_pct(exp.budget, exp.variance_dollars, exp.percent_label)})**"
    else:
        verdict = f"🚨 **Expenses Exceeded Budget: Overspend of {format_money(diff, cfg.currency, places)} ({format_pct(exp.budget, exp.variance_dollars, exp.percent_label)})**"

    lines = [
        verdict + "\n",
        f"• **Budgeted Expenses:** {format_money(exp.budget, cfg.currency, places)}",
        f"• **Actual Expenses:** {format_money(exp.actual, cfg.currency, places)}",
    ]
    if exp.budget != 0:
        burn = ratio(exp.actual, exp.budget) * Decimal("100")
        lines.append(f"• **Budget Utilization:** {burn:.1f}%")
    lines.append(f"• **Status:** {status_label(exp.status)}\n")

    overspent = [r for r in expense_rows if r.actual > r.budget]
    if overspent:
        lines.append("**Over-Budget Accounts:**")
        for row in overspent[:5]:
            lines.append(
                f"• **{safe_inline(row.line_item)}:** {format_money(row.variance_dollars, cfg.currency, places)} over "
                f"({format_pct(row.budget, row.variance_dollars, row.percent_label)})"
            )
    else:
        lines.append("All expense accounts operated at or below planned budgets.")

    chips = ["Revenue", "Summary", "Biggest risks"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_budget_utilization(session: Session) -> Response:
    """Compute overall budget execution and spend velocity."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    lines = ["📊 **Budget Execution & Utilization Metrics**\n"]

    if result.expenses.budget != 0:
        util = ratio(result.expenses.actual, result.expenses.budget) * Decimal("100")
        diff = result.expenses.actual - result.expenses.budget
        status_text = f"over budget by {format_money(diff, cfg.currency, places)}" if diff > 0 else f"under budget by {format_money(abs(diff), cfg.currency, places)}"
        lines.append(f"• **Expense Budget Utilization:** **{util:.1f}%** ({status_text})")
    else:
        lines.append("• **Expense Budget Utilization:** N/A (zero budgeted expenses)")

    if result.revenue.budget != 0:
        achieve = ratio(result.revenue.actual, result.revenue.budget) * Decimal("100")
        diff = result.revenue.actual - result.revenue.budget
        status_text = f"beat by {format_money(diff, cfg.currency, places)}" if diff >= 0 else f"shortfall of {format_money(abs(diff), cfg.currency, places)}"
        lines.append(f"• **Revenue Target Achievement:** **{achieve:.1f}%** ({status_text})")

    has_rev = any(r.line_type == LineType.REVENUE and not r.excluded_from_aggregation for r in result.rows)
    has_exp = any(r.line_type == LineType.EXPENSE and not r.excluded_from_aggregation for r in result.rows)
    classification_incomplete = any(r.line_type == LineType.UNCLASSIFIED for r in result.rows)

    if has_rev and has_exp and not classification_incomplete:
        impact = result.revenue.variance_dollars - result.expenses.variance_dollars
        direction = "above budget" if impact > 0 else "below budget" if impact < 0 else "in line with budget"
        lines.append(
            f"• **Net Operating Impact:** {format_money(impact, cfg.currency, places)} ({direction})"
        )

    chips = ["Summary", "Biggest risks", "Biggest wins"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_top_percent(session: Session) -> Response:
    """Show line items sorted by largest percentage variance."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    pct_rows = [r for r in result.rows if r.variance_percent is not None]
    if not pct_rows:
        return Response(
            text="No line items with non-zero budgets were found.",
            chips=["Summary"],
            phase=Phase.EXPLORING,
        )

    pct_rows.sort(key=lambda r: abs(r.variance_percent or Decimal(0)), reverse=True)
    session.last_table_items = [row.line_item for row in pct_rows[:5]]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    table = [
        row_to_table_dict(row, cfg.currency, places)
        for row in pct_rows[:5]
    ]

    return Response(
        text="📈 **Top Line Items by Percentage Variance** (Largest relative swings):\n",
        table=table,
        chips=["Material", "Top 3 by dollars", "Summary"],
        phase=Phase.EXPLORING,
    )


def _handle_metrics_count(session: Session) -> Response:
    """Return a quantitative breakdown of line items and materiality."""
    result = session.result
    assert result is not None

    total_rows = len(result.rows)
    mat_rows = len(result.material_rows)
    mat_pct = (mat_rows / total_rows * 100) if total_rows > 0 else 0

    f_count = sum(1 for r in result.rows if r.status == Status.FAVORABLE)
    u_count = sum(1 for r in result.rows if r.status == Status.UNFAVORABLE)
    n_count = sum(1 for r in result.rows if r.status == Status.NEUTRAL)

    rev_count = sum(1 for r in result.rows if r.line_type == LineType.REVENUE)
    exp_count = sum(1 for r in result.rows if r.line_type == LineType.EXPENSE)
    unc_count = sum(1 for r in result.rows if r.line_type == LineType.UNCLASSIFIED)

    lines = [
        "🔢 **Portfolio Metrics Breakdown**\n",
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
                    "Budget": format_money(result.revenue.budget, cfg.currency, places),
                    "Actual": format_money(result.revenue.actual, cfg.currency, places),
                    f"Variance ({sym})": format_money(rev_var, cfg.currency, places),
                    "Variance (%)": f"{(ratio(rev_var, result.revenue.budget) * 100):+.1f}%" if result.revenue.budget != 0 else "N/A",
                    "Status": "F" if rev_var >= 0 else "U",
                },
                {
                    "Metric": "Total Expenses",
                    "Budget": format_money(result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(result.expenses.actual, cfg.currency, places),
                    f"Variance ({sym})": format_money(exp_var, cfg.currency, places),
                    "Variance (%)": f"{(ratio(exp_var, result.expenses.budget) * 100):+.1f}%" if result.expenses.budget != 0 else "N/A",
                    "Status": "F" if exp_var <= 0 else "U",
                },
                {
                    "Metric": "Operating Profit",
                    "Budget": format_money(base_profit, cfg.currency, places),
                    "Actual": format_money(actual_profit, cfg.currency, places),
                    f"Variance ({sym})": format_money(net_impact, cfg.currency, places),
                    "Variance (%)": f"{(ratio(net_impact, abs(base_profit)) * 100):+.1f}%" if base_profit != 0 else "N/A",
                    "Status": "F" if net_impact >= 0 else "U",
                },
            ]
        status_word = "beat" if net_impact >= 0 else "shortfall"
        return Response(
            text=f"⚖️ **Executive Macro Comparison: Actual vs. Budget**\n\n"
                 f"Operating profit finished at **{format_money(actual_profit, cfg.currency, places)}**, representing a "
                 f"**{format_money(abs(net_impact), cfg.currency, places)} {status_word}** against the budget target of "
                 f"{format_money(base_profit, cfg.currency, places)}.",
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
            margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else Decimal(0)
            cost_ratio = (ratio(result.expenses.actual, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else Decimal(0)

            macro_table = [
                {
                    "Category": "Total Revenue",
                    "Budget": format_money(result.revenue.budget, cfg.currency, places),
                    "Actual": format_money(result.revenue.actual, cfg.currency, places),
                    "Operating Flow": "Top-Line Inflow",
                    "% of Revenue": "100.0%",
                },
                {
                    "Category": "Total Expenses",
                    "Budget": format_money(result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(result.expenses.actual, cfg.currency, places),
                    "Operating Flow": "Operating Outflow",
                    "% of Revenue": f"{cost_ratio:.1f}%",
                },
                {
                    "Category": "Operating Profit (EBITDA)",
                    "Budget": format_money(result.revenue.budget - result.expenses.budget, cfg.currency, places),
                    "Actual": format_money(actual_profit, cfg.currency, places),
                    "Operating Flow": "Net Retained Margin",
                    "% of Revenue": f"{margin:.1f}%",
                },
            ]
        return Response(
            text=f"⚖️ **Macro Financial Comparison: Revenue vs. Expenses**\n\n"
                 f"Actual Revenue of **{format_money(result.revenue.actual, cfg.currency, places)}** offset by Operating Expenses of "
                 f"**{format_money(result.expenses.actual, cfg.currency, places)}** yields an **Operating Profit of {format_money(actual_profit, cfg.currency, places)}** "
                 f"({margin:.1f}% EBITDA margin; cost-to-income ratio of {cost_ratio:.1f}%).",
            table=macro_table,
            chips=["Waterfall", "Run rate", "Sensitivity", "Summary"],
            phase=Phase.EXPLORING,
        )

    matches1 = find_line_item(name1, line_items)
    matches2 = find_line_item(name2, line_items)

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
        table = [row_to_table_dict(row1, cfg.currency, places)]
        return Response(
            text=f"ℹ️ Comparing '**{safe_inline(row1.line_item)}**' against itself. Account details:",
            table=table,
            chips=[f"Why {row1.line_item}?", "Summary"],
            phase=Phase.EXPLORING,
        )

    table = [
        row_to_table_dict(row1, cfg.currency, places),
        row_to_table_dict(row2, cfg.currency, places),
    ]

    diff_var = abs(row1.variance_dollars) - abs(row2.variance_dollars)
    if diff_var > 0:
        lead = f"**{safe_inline(row1.line_item)}** has the larger absolute variance swing by {format_money(diff_var, cfg.currency, places)}."
    elif diff_var < 0:
        lead = f"**{safe_inline(row2.line_item)}** has the larger absolute variance swing by {format_money(abs(diff_var), cfg.currency, places)}."
    else:
        lead = "Both line items have identical absolute variance swings."

    return Response(
        text=f"⚖️ **Side-by-Side Comparison: {safe_inline(row1.line_item)} vs. {safe_inline(row2.line_item)}**\n\n{lead}",
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
        total_abs_var = sum((abs(r.variance_dollars) for r in result.rows), Decimal(0))

    if total_abs_var == Decimal(0):
        return Response(
            text="✅ **Zero Variance Volatility:** All line items performed exactly to budget.",
            chips=["Summary", "Material"],
            phase=Phase.EXPLORING,
        )

    # Sort rows by absolute variance descending
    sorted_rows = sorted(result.rows, key=lambda r: abs(r.variance_dollars), reverse=True)
    top_3 = sorted_rows[:3]
    session.last_table_items = [row.line_item for row in top_3]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    with financial_context():
        top_3_abs = sum((abs(r.variance_dollars) for r in top_3), Decimal(0))
        top_3_pct = ratio(top_3_abs, total_abs_var) * Decimal("100")

    lines = [
        "📊 **Variance Concentration Analysis (Pareto Distribution)**\n",
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
            "\n💡 **FP&A Takeaway:** **High Concentration.** Management attention should focus "
            "almost exclusively on these top 3 drivers (80/20 rule), as resolving them addresses "
            f"{top_3_pct:.1f}% of the portfolio's total variance."
        )
    else:
        insight = (
            "\n💡 **FP&A Takeaway:** **Dispersed Variance.** Discrepancies are spread across multiple "
            "operating accounts, suggesting systemic operational changes or broad baseline recalibration may be needed."
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

    unbudgeted = [r for r in result.rows if r.budget == Decimal(0) and r.actual > Decimal(0)]
    session.last_table_items = [row.line_item for row in unbudgeted]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not unbudgeted:
        return Response(
            text="✅ **No Unbudgeted Spending:** All accounts with actual activity had an approved baseline budget.",
            chips=["Summary", "Material", "Expense status"],
            phase=Phase.EXPLORING,
        )

    lines = [
        f"🚨 **Unbudgeted Spending Detected ({len(unbudgeted)} account{'s' if len(unbudgeted) != 1 else ''})**\n\n"
        "These line items had zero approved budget ($0.00) but incurred realized expenditures:\n"
    ]

    for row in unbudgeted:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** {format_money(row.actual, cfg.currency, places)} realized "
            f"({status_label(row.status)}, Type: {row.line_type})"
        )

    lines.append(
        "\n💡 **Governance Note:** Zero-budget expenditures bypass planned allocations and require VP/CFO authorization."
    )

    chips = [f"Why {unbudgeted[0].line_item}?", "Summary", "Warnings"]
    return Response(text="\n".join(lines), chips=chips, phase=Phase.EXPLORING)


def _handle_cost_savings(session: Session) -> Response:
    """Show expense lines that preserved budget through favorable underspending."""
    result = session.result
    assert result is not None
    cfg = result.config
    places = report_places(result)

    savings_rows = [
        r for r in result.rows
        if r.line_type == LineType.EXPENSE and r.status == Status.FAVORABLE
    ]
    session.last_table_items = [row.line_item for row in savings_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not savings_rows:
        return Response(
            text="ℹ️ **No Cost Savings:** No expense accounts operated below their budgeted allocation.",
            chips=["Summary", "Expense status", "Biggest risks"],
            phase=Phase.EXPLORING,
        )

    savings_rows.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    with financial_context():
        total_savings = sum((abs(r.variance_dollars) for r in savings_rows), Decimal(0))

    lines = [
        f"💰 **Expense Savings & Underspend Summary (Total: {format_money(total_savings, cfg.currency, places)})**\n\n"
        "These expense categories operated below approved spending limits, preserving cash and operating margin:\n"
    ]

    for row in savings_rows[:5]:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** Saved {format_money(abs(row.variance_dollars), cfg.currency, places)} "
            f"(Actual: {format_money(row.actual, cfg.currency, places)} vs. Budget: {format_money(row.budget, cfg.currency, places)}, "
            f"{format_pct(row.budget, row.variance_dollars, row.percent_label)})"
        )

    lines.append(
        "\n💡 **FP&A Verification:** Check whether underspend represents permanent operational efficiency or merely delayed vendor invoicing."
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
        r for r in result.rows
        if r.line_type == LineType.REVENUE and r.status == Status.UNFAVORABLE
    ]
    session.last_table_items = [row.line_item for row in miss_rows]
    if session.last_table_items:
        session.last_focused_item = session.last_table_items[0]

    if not miss_rows:
        return Response(
            text="🎯 **No Revenue Misses:** All revenue accounts met or exceeded planned targets.",
            chips=["Summary", "Revenue status", "Biggest wins"],
            phase=Phase.EXPLORING,
        )

    miss_rows.sort(key=lambda r: abs(r.variance_dollars), reverse=True)
    with financial_context():
        total_shortfall = sum((abs(r.variance_dollars) for r in miss_rows), Decimal(0))

    lines = [
        f"⚠️ **Revenue Shortfall & Misses (Total: {format_money(total_shortfall, cfg.currency, places)})**\n\n"
        "These revenue lines failed to reach approved baseline targets:\n"
    ]

    for row in miss_rows[:5]:
        lines.append(
            f"• **{safe_inline(row.line_item)}:** Shortfall of {format_money(abs(row.variance_dollars), cfg.currency, places)} "
            f"(Actual: {format_money(row.actual, cfg.currency, places)} vs. Budget: {format_money(row.budget, cfg.currency, places)}, "
            f"{format_pct(row.budget, row.variance_dollars, row.percent_label)})"
        )

    lines.append(
        "\n💡 **Action:** Inspect volume vs. pricing drivers to determine whether shortfall is due to lower unit demand or contracted rate discounting."
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
                impact = row.variance_dollars if row.status == Status.FAVORABLE else -abs(row.variance_dollars)
            bridge_items.append((row, impact))

        # Sort items by magnitude of profit impact (largest drivers first)
        bridge_items.sort(key=lambda item: abs(item[1]), reverse=True)

    table_rows: list[dict[str, str]] = [
        {
            "Line Item": "1. Budget Operating Profit",
            "Type": "Baseline",
            "Budget": format_money(budget_profit, cur, places),
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
            "Budget": format_money(row.budget, cur, places),
            "Actual": format_money(row.actual, cur, places),
            f"Var ({sym})": format_money(row.variance_dollars, cur, places),
            f"Profit Impact ({sym})": format_money(impact, cur, places),
            "Status": "F" if impact > 0 else ("U" if impact < 0 else "Neutral"),
        })

    table_rows.append({
        "Line Item": "🏁 Actual Operating Profit",
        "Type": "Summary",
        "Budget": format_money(budget_profit, cur, places),
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
        f"📊 **P&L Variance Bridge (Waterfall Walk)**\n\n"
        f"Reconciling baseline Budget Operating Profit to Actual Operating Profit for **{safe_inline(session.period or '')}**:\n\n"
        f"• **Budget Operating Profit**: {format_money(budget_profit, cur, places)}\n"
        f"• **Revenue Bridge Impact**: {format_money(rev_impact, cur, places)} ({rev_status})\n"
        f"• **Expense Bridge Impact**: {format_money(exp_impact, cur, places)} ({exp_status})\n"
        f"• **Actual Operating Profit**: {format_money(actual_profit, cur, places)}\n"
        f"• **Net Profit Variance**: {format_money(net_var, cur, places)} ({status_text})\n\n"
        "Each line item's contribution to operating profit is displayed in the bridge table below "
        "(positive values expand profit; negative values contract profit):"
    )

    chips = []
    if session.last_table_items:
        chips.append(f"Why {session.last_table_items[0]}?")
    chips.extend(["Biggest risks", "Biggest wins", "Export CSV", "Summary"])

    return Response(text=text, table=table_rows, chips=chips, phase=Phase.EXPLORING)


def _handle_list_sheets(session: Session) -> Response:
    """List available worksheets in the uploaded workbook."""
    if not session.source_bytes or not session.source_name:
        return Response(
            text="No file has been uploaded yet. Please upload an Excel workbook (.xlsx or .xlsm) first.",
            phase=session.phase,
            chips=["Help"],
        )

    suffix = (session.source_suffix or "").lower()
    if suffix not in {".xlsx", ".xlsm"}:
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

    if not sheets:
        return Response(
            text=f"No readable worksheets found in '{safe_inline(session.source_name)}'.",
            phase=session.phase,
        )

    current = session.worksheet or sheets[0]
    sheet_list_md = []
    for idx, s in enumerate(sheets, start=1):
        is_active = (s == current)
        marker = " *(active)*" if is_active else ""
        sheet_list_md.append(f"{idx}. **{safe_inline(s)}**{marker}")

    text = (
        f"📑 **Worksheets in '{safe_inline(session.source_name)}' ({len(sheets)} total):**\n\n"
        + "\n".join(sheet_list_md)
        + "\n\nTo switch worksheets, type `sheet <name>` (e.g., `sheet "
        + safe_inline(sheets[1] if len(sheets) > 1 else sheets[0])
        + "`)."
    )

    other_sheets = [s for s in sheets if s != current]
    chips = [f"sheet {s}" for s in other_sheets[:3]]
    if session.phase == Phase.EXPLORING:
        chips.append("Summary")

    return Response(text=text, chips=chips, phase=session.phase)


def _handle_switch_sheet(session: Session, intent: ParsedIntent) -> Response:
    """Switch the active worksheet and re-analyze or re-intake data."""
    if not session.source_bytes or not session.source_name:
        return Response(
            text="No file has been uploaded yet. Please upload an Excel workbook first.",
            phase=session.phase,
        )

    suffix = (session.source_suffix or "").lower()
    if suffix not in {".xlsx", ".xlsm"}:
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
    if matched_sheet is None:
        candidates = [s for s in sheets if target_sheet.lower() in s.lower()]
        if len(candidates) == 1:
            matched_sheet = candidates[0]

    if matched_sheet is None:
        available_str = ", ".join(f"'{safe_inline(s)}'" for s in sheets)
        return Response(
            text=f"⚠️ Worksheet '{safe_inline(target_sheet)}' was not found in '{safe_inline(session.source_name)}'.\n\n"
                 f"Available worksheets: {available_str}.",
            chips=[f"sheet {s}" for s in sheets[:3]],
            phase=session.phase,
        )

    if matched_sheet == session.worksheet and session.result is not None:
        return Response(
            text=f"Worksheet **'{safe_inline(matched_sheet)}'** is already active.",
            chips=["Summary", "Waterfall", "Material"],
            phase=session.phase,
        )

    try:
        parsed = load_input(
            session.source_bytes, suffix, source_name=session.source_name, sheet=matched_sheet,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        return Response(
            text=f"⚠️ Failed to load worksheet '{safe_inline(matched_sheet)}': {display_text(str(exc))}",
            chips=["Show sheets", "Help"],
            phase=session.phase,
        )

    if not parsed.rows:
        return Response(
            text=f"⚠️ Worksheet '{safe_inline(matched_sheet)}' contains no data rows.",
            chips=["Show sheets", "Help"],
            phase=session.phase,
        )

    session.parsed_rows = parsed.rows
    session.worksheet = parsed.worksheet
    session.sheet = matched_sheet

    if (
        session.phase == Phase.EXPLORING
        and session.period is not None
        and session.dollar_threshold is not None
        and session.percent_threshold is not None
    ):
        resp = _run_analysis(session)
        prefix = f"📑 Switched to worksheet **'{safe_inline(matched_sheet)}'** ({len(parsed.rows)} rows).\n\n"
        return Response(
            text=prefix + resp.text,
            table=resp.table,
            chips=resp.chips,
            phase=resp.phase,
            download=resp.download,
        )

    row_count = len(parsed.rows)
    return Response(
        text=f"📑 Switched to worksheet **'{safe_inline(matched_sheet)}'** ({row_count} data row{'s' if row_count != 1 else ''}).\n\n"
             f"Current reporting period: **{safe_inline(session.period or 'Not set')}**.",
        phase=session.phase,
    )


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

    # Determine sign: negative if drop/decrease/cut/lower/less/fall/down or "-"
    is_negative = (
        direction in ("drops", "dropped", "decreases", "decreased", "falls", "lower", "down", "cut", "cuts", "reduce", "reduced", "shrink", "shrinks", "-")
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

        base_margin = (ratio(base_profit, base_rev) * Decimal(100)) if base_rev != 0 else Decimal(0)
        sim_margin = (ratio(sim_profit, sim_rev) * Decimal(100)) if sim_rev != 0 else Decimal(0)
        margin_delta = sim_margin - base_margin

    sign_str = "-" if delta < 0 else "+"
    change_desc = f"{sign_str}{amount_dec:.1f}%" if is_percent else f"{sign_str}{sym}{abs(delta):,.2f}"
    profit_status = "expansion" if profit_delta > 0 else ("contraction" if profit_delta < 0 else "neutral")
    budget_status = "beat" if sim_vs_budget > 0 else ("shortfall" if sim_vs_budget < 0 else "on track")

    text = (
        f"🔮 **Scenario Analysis (\"What-If\" Simulation)**\n\n"
        f"**Simulation Parameters:**\n"
        f"• Target: **{target_label}** ({target_type})\n"
        f"• Baseline Actual: {format_money(base_val, cur, places)}\n"
        f"• Simulated Change: **{change_desc}**\n"
        f"• Simulated Target Value: **{format_money(sim_val, cur, places)}**\n\n"
        f"**Projected Operating Profit Impact:**\n"
        f"• **Baseline Operating Profit**: {format_money(base_profit, cur, places)}\n"
        f"• **Simulated Operating Profit**: **{format_money(sim_profit, cur, places)}**\n"
        f"• **Profit Delta vs. Baseline**: **{format_money(profit_delta, cur, places)}** ({profit_status})\n"
        f"• **Simulated EBITDA Margin**: **{sim_margin:.1f}%** (vs. {base_margin:.1f}% baseline, {margin_delta:+0.1f} pts)\n"
        f"• **Simulated vs. Budget**: **{format_money(sim_vs_budget, cur, places)}** ({budget_status} vs. planned profit of {format_money(budget_profit, cur, places)})\n"
    )

    table = [
        {
            "Metric": target_label,
            "Budget": format_money(target_budget, cur, places),
            "Baseline Actual": format_money(base_val, cur, places),
            "Simulated Scenario": format_money(sim_val, cur, places),
            "Delta vs Baseline": format_money(delta, cur, places),
            "Status": "F" if (delta >= 0 if target_is_rev else delta <= 0) else "U",
        },
        {
            "Metric": "Total Revenue",
            "Budget": format_money(budget_rev, cur, places),
            "Baseline Actual": format_money(base_rev, cur, places),
            "Simulated Scenario": format_money(sim_rev, cur, places),
            "Delta vs Baseline": format_money(sim_rev - base_rev, cur, places),
            "Status": "F" if sim_rev >= base_rev else "U",
        },
        {
            "Metric": "Total Expenses",
            "Budget": format_money(budget_exp, cur, places),
            "Baseline Actual": format_money(base_exp, cur, places),
            "Simulated Scenario": format_money(sim_exp, cur, places),
            "Delta vs Baseline": format_money(sim_exp - base_exp, cur, places),
            "Status": "F" if sim_exp <= base_exp else "U",
        },
        {
            "Metric": "Operating Profit",
            "Budget": format_money(budget_profit, cur, places),
            "Baseline Actual": format_money(base_profit, cur, places),
            "Simulated Scenario": format_money(sim_profit, cur, places),
            "Delta vs Baseline": format_money(profit_delta, cur, places),
            "Status": "F" if profit_delta >= 0 else "U",
        },
    ]

    chips = ["Sensitivity analysis", "Run rate", "Waterfall", "What if expenses drop 5%?"]
    return Response(text=text, table=table, chips=chips, phase=Phase.EXPLORING)


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
            s_margin = (ratio(s_profit, s_rev) * Decimal(100)) if s_rev != 0 else Decimal(0)
            status = "F" if s_var_budget >= 0 else "U"

            table_rows.append({
                "Scenario": name,
                "Revenue": format_money(s_rev, cur, places),
                "Expenses": format_money(s_exp, cur, places),
                "Operating Profit": format_money(s_profit, cur, places),
                f"Var vs Budget ({sym})": format_money(s_var_budget, cur, places),
                "EBITDA Margin": f"{s_margin:.1f}%",
                "Status": status,
            })

    text = (
        f"📊 **Financial Sensitivity & Scenario Matrix**\n\n"
        f"Evaluating operating profit resilience against volume and cost stress testing "
        f"for **{safe_inline(session.period or '')}**:\n\n"
        f"• **Baseline Operating Profit**: {format_money(base_profit, cur, places)}\n"
        f"• **Planned Budget Profit**: {format_money(budget_profit, cur, places)}\n"
        f"• **Stress Range**: From **{table_rows[0]['Operating Profit']}** (Severe Downside) "
        f"to **{table_rows[-1]['Operating Profit']}** (Strong Upside).\n\n"
        "Explore individual scenarios with `what if revenue drops 5%?` or `what if expenses increase 10%?`."
    )

    chips = ["What if revenue drops 5%?", "What if expenses increase 5%?", "Run rate", "Waterfall"]
    return Response(text=text, table=table_rows, chips=chips, phase=Phase.EXPLORING)


def _detect_period_elapsed_months(period: str) -> tuple[int, str]:
    """Detect elapsed months and period label from session period text."""
    p = period.lower()
    if "q1" in p:
        return 3, "Q1 (3 months elapsed)"
    if "q2" in p:
        return 6, "Q2 (6 months elapsed)"
    if "q3" in p:
        return 9, "Q3 (9 months elapsed)"
    if "q4" in p or "fy" in p or "full year" in p or "annual" in p:
        return 12, "Full Year (12 months)"
    if "h1" in p or "first half" in p:
        return 6, "H1 (6 months elapsed)"
    if "h2" in p or "second half" in p:
        return 12, "H2 (12 months)"

    months = {
        "jan": 1, "january": 1, "feb": 2, "february": 2,
        "mar": 3, "march": 3, "apr": 4, "april": 4,
        "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    for m_name, m_num in months.items():
        if re.search(rf"\b{m_name}\b", p):
            return m_num, f"{m_name.capitalize()} ({m_num} month{'s' if m_num != 1 else ''} elapsed)"

    m_match = re.search(r"\bm(?:onth)?\s*([1-9]|1[0-2])\b", p)
    if m_match:
        m_num = int(m_match.group(1))
        return m_num, f"Month {m_num} ({m_num} month{'s' if m_num != 1 else ''} elapsed)"

    return 3, "Quarterly (3 months assumed)"


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
        rr_margin = (ratio(rr_profit, rr_rev) * Decimal(100)) if rr_rev != 0 else Decimal(0)

        # 2. Corporate FP&A Latest Estimate (LE = Actuals to Date + Remaining Budget)
        remaining_budget_rev = budget_rev * ratio(Decimal(remaining), Decimal(elapsed))
        remaining_budget_exp = budget_exp * ratio(Decimal(remaining), Decimal(elapsed))
        le_rev = actual_rev + remaining_budget_rev
        le_exp = actual_exp + remaining_budget_exp
        le_profit = le_rev - le_exp
        le_var = le_profit - annual_budget_profit
        le_margin = (ratio(le_profit, le_rev) * Decimal(100)) if le_rev != 0 else Decimal(0)

    rr_status = "beat" if rr_var >= 0 else "shortfall"
    le_status = "favorable beat" if le_var >= 0 else "unfavorable shortfall"

    text = (
        f"📈 **Run-Rate & Full-Year (FY) Projections**\n\n"
        f"**Period Basis:** **{period_label}** ({elapsed} of 12 months elapsed; {remaining} months remaining in fiscal year).\n\n"
        f"• **Annualized Operating Profit (Run-Rate)**: **{format_money(rr_profit, cur, places)}**\n"
        f"  *If current operational velocity continues for the full year, profit is projected at {format_money(rr_profit, cur, places)} "
        f"({format_money(rr_var, cur, places)} {rr_status} vs. annual budget of {format_money(annual_budget_profit, cur, places)}).*\n\n"
        f"• **Corporate Latest Estimate (LE = Actuals + Remaining Plan)**: **{format_money(le_profit, cur, places)}**\n"
        f"  *Assuming remaining {remaining} months perform strictly to budget, full-year profit finishes at {format_money(le_profit, cur, places)} "
        f"({format_money(le_var, cur, places)} {le_status} vs. plan).*\n\n"
        f"• **Annualized Revenue Run-Rate**: {format_money(rr_rev, cur, places)} (EBITDA Margin: {rr_margin:.1f}%)\n"
        f"• **Annualized Expense Run-Rate**: {format_money(rr_exp, cur, places)}"
    )

    table = [
        {
            "Projection Model": f"Actuals to Date ({safe_inline(session.period or '')})",
            "Revenue": format_money(actual_rev, cur, places),
            "Expenses": format_money(actual_exp, cur, places),
            "Operating Profit": format_money(actual_profit, cur, places),
            f"Var vs Budget ({sym})": format_money(actual_profit - budget_profit, cur, places),
            "EBITDA Margin": f"{(ratio(actual_profit, actual_rev) * 100):.1f}%" if actual_rev != 0 else "0.0%",
            "Status": "F" if (actual_profit - budget_profit) >= 0 else "U",
        },
        {
            "Projection Model": "Annualized Run-Rate (Current Pace)",
            "Revenue": format_money(rr_rev, cur, places),
            "Expenses": format_money(rr_exp, cur, places),
            "Operating Profit": format_money(rr_profit, cur, places),
            f"Var vs Budget ({sym})": format_money(rr_var, cur, places),
            "EBITDA Margin": f"{rr_margin:.1f}%",
            "Status": "F" if rr_var >= 0 else "U",
        },
        {
            "Projection Model": "Latest Estimate (LE: Actuals + Remaining Plan)",
            "Revenue": format_money(le_rev, cur, places),
            "Expenses": format_money(le_exp, cur, places),
            "Operating Profit": format_money(le_profit, cur, places),
            f"Var vs Budget ({sym})": format_money(le_var, cur, places),
            "EBITDA Margin": f"{le_margin:.1f}%",
            "Status": "F" if le_var >= 0 else "U",
        },
        {
            "Projection Model": "Full-Year Baseline Budget",
            "Revenue": format_money(budget_rev * multiplier, cur, places),
            "Expenses": format_money(budget_exp * multiplier, cur, places),
            "Operating Profit": format_money(annual_budget_profit, cur, places),
            f"Var vs Budget ({sym})": format_money(Decimal(0), cur, places),
            "EBITDA Margin": f"{(ratio(annual_budget_profit, budget_rev * multiplier) * 100):.1f}%" if (budget_rev * multiplier) != 0 else "0.0%",
            "Status": "Neutral",
        },
    ]

    chips = ["Sensitivity analysis", "What if revenue drops 5%?", "Waterfall", "Summary"]
    return Response(text=text, table=table, chips=chips, phase=Phase.EXPLORING)


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
        rev_pct = (ratio(rev_var, rev_budget) * Decimal(100)) if rev_budget != 0 else Decimal(0)

        exp_budget = result.expenses.budget
        exp_actual = result.expenses.actual
        exp_var = exp_actual - exp_budget
        exp_pct = (ratio(exp_var, exp_budget) * Decimal(100)) if exp_budget != 0 else Decimal(0)

        budget_profit = rev_budget - exp_budget
        actual_profit = rev_actual - exp_actual
        net_impact = actual_profit - budget_profit
        net_pct = (ratio(net_impact, abs(budget_profit)) * Decimal(100)) if budget_profit != 0 else Decimal(0)

        budget_margin = (ratio(budget_profit, rev_budget) * Decimal(100)) if rev_budget != 0 else Decimal(0)
        actual_margin = (ratio(actual_profit, rev_actual) * Decimal(100)) if rev_actual != 0 else Decimal(0)
        margin_delta = actual_margin - budget_margin

    # Find top revenue driver & drag
    rev_rows = [r for r in result.rows if r.line_type == LineType.REVENUE]
    top_rev_beat = max((r for r in rev_rows if r.variance_dollars > 0), key=lambda r: r.variance_dollars, default=None)
    top_rev_miss = min((r for r in rev_rows if r.variance_dollars < 0), key=lambda r: r.variance_dollars, default=None)

    # Find largest cost overrun & largest saving
    exp_rows = [r for r in result.rows if r.line_type == LineType.EXPENSE]
    top_exp_over = max((r for r in exp_rows if r.variance_dollars > 0), key=lambda r: r.variance_dollars, default=None)
    top_exp_save = min((r for r in exp_rows if r.variance_dollars < 0), key=lambda r: r.variance_dollars, default=None)

    # Reconciled driver count
    reconciled_count = sum(1 for r in result.material_rows if r.driver_evidence and r.driver_evidence.reconciles)

    status_word = "beat" if net_impact >= 0 else "shortfall"
    sign_word = "expanded" if margin_delta >= 0 else "contracted"

    memo_lines = [
        "# 📑 Executive Management Briefing & Variance Commentary",
        f"**Reporting Period:** {cfg.period}  ",
        f"**Currency:** {cfg.currency}  ",
        f"**Materiality Thresholds:** {format_money(cfg.dollar_threshold, cur, places)} or {cfg.percent_threshold * 100:.1f}%  \n",
        "---",
        "### 1. Executive Summary",
        f"For **{cfg.period}**, Operating Profit finished at **{format_money(actual_profit, cur, places)}**, representing a "
        f"**{format_money(abs(net_impact), cur, places)} {status_word}** ({net_pct:+.1f}%) "
        f"against the planned budget of **{format_money(budget_profit, cur, places)}**. "
        f"EBITDA margin **{sign_word}** from {budget_margin:.1f}% to **{actual_margin:.1f}%** ({margin_delta:+.1f} pts).\n",
        "### 2. Top-Line Performance (Revenue)",
        f"Total Revenue concluded at **{format_money(rev_actual, cur, places)}** vs. Budget of **{format_money(rev_budget, cur, places)}** "
        f"({format_money(rev_var, cur, places)}, {rev_pct:+.1f}%, {'Favorable' if rev_var >= 0 else 'Unfavorable'}).",
    ]

    if top_rev_beat:
        memo_lines.append(f"• **Key Outperformer:** **{safe_inline(top_rev_beat.line_item)}** generated {format_money(top_rev_beat.actual, cur, places)} (+{format_money(top_rev_beat.variance_dollars, cur, places)} above budget).")
    if top_rev_miss:
        memo_lines.append(f"• **Primary Drag:** **{safe_inline(top_rev_miss.line_item)}** delivered {format_money(top_rev_miss.actual, cur, places)} ({format_money(top_rev_miss.variance_dollars, cur, places)} miss vs. budget).")

    memo_lines.extend([
        "\n### 3. Cost Discipline & Overruns (Expenses)",
        f"Total Operating Expenses ended at **{format_money(exp_actual, cur, places)}** vs. Budget of **{format_money(exp_budget, cur, places)}** "
        f"({format_money(exp_var, cur, places)}, {exp_pct:+.1f}%, {'Unfavorable' if exp_var > 0 else 'Favorable'}).",
    ])

    if top_exp_over:
        memo_lines.append(f"• **Primary Cost Risk:** **{safe_inline(top_exp_over.line_item)}** overspent by {format_money(top_exp_over.variance_dollars, cur, places)} (+{format_pct(top_exp_over.budget, top_exp_over.variance_dollars, top_exp_over.percent_label)}).")
    if top_exp_save:
        memo_lines.append(f"• **Key Cost Savings:** **{safe_inline(top_exp_save.line_item)}** saved {format_money(abs(top_exp_save.variance_dollars), cur, places)} vs. allocated budget.")

    memo_lines.extend([
        "\n### 4. Governance & Material Variances",
        f"• **{len(result.material_rows)}** line items breached the materiality hurdle ({format_money(cfg.dollar_threshold, cur, places)} or {cfg.percent_threshold * 100:.1f}%).",
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
        memo_lines.append("2. **Sales Acceleration:** Formulate commercial recovery plans targeting lagging revenue lines.")

    missing = [safe_inline(r.line_item) for r in result.material_rows if not (r.driver_evidence and r.driver_evidence.reconciles)]
    if missing:
        memo_lines.append(f"3. **Data Governance:** Procure granular driver components (rate/volume/mix) for {', '.join(missing[:3])}.")
    else:
        memo_lines.append("3. **Audit Verification:** All material drivers mathematically reconciled and signed off.")

    memo_text = "\n".join(memo_lines)
    period_slug = cfg.period.replace(" ", "_").lower()
    filename = f"executive_memo_{period_slug}.md"

    table_overview = [
        {
            "Section": "1. Top-Line (Revenue)",
            "Budget": format_money(rev_budget, cur, places),
            "Actual": format_money(rev_actual, cur, places),
            f"Variance ({sym})": format_money(rev_var, cur, places),
            "Outcome": "Beat" if rev_var >= 0 else "Miss",
        },
        {
            "Section": "2. Cost (Expenses)",
            "Budget": format_money(exp_budget, cur, places),
            "Actual": format_money(exp_actual, cur, places),
            f"Variance ({sym})": format_money(exp_var, cur, places),
            "Outcome": "Overrun" if exp_var > 0 else "Savings",
        },
        {
            "Section": "3. Bottom-Line (Operating Profit)",
            "Budget": format_money(budget_profit, cur, places),
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
            status_str = "✅ Reconciled" if ev.reconciles else "⚠️ Unreconciled"
            model_label = ev.label
            comps = ", ".join(f"{k}: {format_money(v, cur, places)}" for k, v in ev.components)
        else:
            status_str = "❌ No Driver Data"
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

    text = (
        f"🔬 **Causal Driver Models Overview**\n\n"
        f"• **Reconciled Causal Models:** **{len(rows_reconciled)}** of **{len(result.rows)}** line items "
        f"({len(rows_with_drivers)} have model structures attached).\n"
        f"• **Material Variance Coverage:** **{coverage_pct:.1f}%** of material items have mathematically verified causal drivers.\n\n"
        f"Causal driver models isolate the root mathematical forces (e.g. Price vs. Volume, Rate vs. Volume) behind budget deviations."
    )

    chips = ["Waterfall", "Biggest risks", "Summary", "Export report"]
    return Response(text=text, table=table_data, chips=chips, phase=Phase.EXPLORING)


def _handle_greeting(session: Session) -> Response:
    """Respond politely to conversational greetings with context-aware guidance."""
    if session.phase == Phase.EXPLORING and session.result is not None:
        cfg = session.result.config
        places = report_places(session.result)
        cur = cfg.currency
        net_impact = session.result.revenue.variance_dollars - session.result.expenses.variance_dollars
        status = "favorable beat" if net_impact >= 0 else "unfavorable shortfall"

        text = (
            f"👋 **Hello!** I am ready to explore your **{cfg.period}** financial results.\n\n"
            f"Currently tracking **{cur}** with materiality set at **{format_money(cfg.dollar_threshold, cur, places)} or {cfg.percent_threshold * 100:.1f}%**. "
            f"Overall net operating impact is a **{format_money(abs(net_impact), cur, places)} {status}** against budget.\n\n"
            f"What would you like to review? You can ask for an `executive memo`, a `waterfall` walk, `run rate` projections, or drill down into any account (e.g. `why {safe_inline(session.result.rows[0].line_item)}`)."
        )
        chips = ["Executive memo", "Waterfall", "Biggest risks", "Sensitivity"]
    elif session.phase == Phase.AWAITING_PERIOD:
        text = (
            "👋 **Hello!** Your file has been validated and loaded. "
            "Please tell me which reporting period this data represents (for example: `Q3 2026` or `August 2026`)."
        )
        chips = ["Q3 2026", "FY 2026", "Month ended Sep 30, 2026"]
    elif session.phase == Phase.AWAITING_THRESHOLDS:
        text = (
            "👋 **Hello!** Next, let's configure your materiality tolerance hurdles. "
            "Enter both dollar and percentage hurdles (e.g., `$10,000 or 5%`)."
        )
        chips = ["$5,000 or 5%", "$10,000 or 5%", "$25,000 or 10%"]
    elif session.phase == Phase.AWAITING_CURRENCY:
        text = (
            "👋 **Hello!** What currency are these financial figures reported in? "
            "I support `USD`, `EUR`, and `GBP`."
        )
        chips = ["USD", "EUR", "GBP"]
    elif session.phase == Phase.RESOLVE_UNCLASSIFIED:
        text = (
            "👋 **Hello!** We are currently resolving unclassified line items. "
            "Please select `Revenue`, `Expense`, or `Skip` for the highlighted account."
        )
        chips = ["Revenue", "Expense", "Skip", "Skip all"]
    else:
        text = (
            "👋 **Hello! Welcome to the Variance Analysis Agent.**\n\n"
            "I am an institutional FP&A assistant powered by deterministic 50-digit Decimal arithmetic. "
            "Please drop a CSV, JSON, or Excel workbook above to begin your analysis, or ask me any question about financial variance concepts."
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
    text = (
        "🤖 **Institutional Variance Analysis Agent**\n\n"
        "I am an intelligent, deterministic financial analysis assistant built specifically for FP&A teams, "
        "controllers, and CFO organizations.\n\n"
        "**How I differ from a non-deterministic LLM:**\n"
        "• **100% Deterministic Calculations**: Zero hallucination. Every variance, percentage, and waterfall step is computed with 50-digit exact Decimal precision.\n"
        "• **Cryptographic Provenance**: Every analysis produces a SHA-256 fingerprint for complete auditability.\n"
        "• **Conversational Fluency**: I interpret natural business queries, multi-turn follow-ups, and scenarios, giving you the ease of a conversational AI with the trustworthiness of an audited ledger.\n"
        "• **Zero External Dependencies**: Standard library Python only; your sensitive financial data never leaves your environment."
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
        impact_pct = (ratio(net_impact, abs(budget_profit)) * Decimal(100)) if budget_profit != 0 else Decimal(0)
        margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else Decimal(0)

    beat_word = "beat" if net_impact >= 0 else "shortfall"
    rev_word = "outperformed" if rev_var >= 0 else "underperformed"
    exp_word = "generated savings of" if exp_var <= 0 else "overspent by"

    # Identify top accounts
    rev_rows = [r for r in result.rows if r.line_type == LineType.REVENUE]
    exp_rows = [r for r in result.rows if r.line_type == LineType.EXPENSE]
    top_rev = max(rev_rows, key=lambda r: abs(r.variance_dollars), default=None)
    top_exp = max(exp_rows, key=lambda r: abs(r.variance_dollars), default=None)

    driver_context = ""
    if top_rev and top_exp:
        driver_context = f" Top-line momentum was led by **{safe_inline(top_rev.line_item)}**, while expense variance was dominated by **{safe_inline(top_exp.line_item)}**."

    text = (
        f"⚡ **The Executive TL;DR for {cfg.period}:**\n\n"
        f"Operating Profit finished at **{format_money(actual_profit, cur, places)}**, delivering a **{format_money(abs(net_impact), cur, places)} {beat_word}** "
        f"({impact_pct:+.1f}% vs. planned budget of {format_money(budget_profit, cur, places)}) with EBITDA margin standing at **{margin:.1f}%**. "
        f"Top-line revenue {rev_word} plan by {format_money(abs(rev_var), cur, places)}, while operating expenses {exp_word} {format_money(abs(exp_var), cur, places)}.{driver_context}"
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
        actual_margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)) if result.revenue.actual != 0 else Decimal(0)
        budget_margin = (ratio(budget_profit, result.revenue.budget) * Decimal(100)) if result.revenue.budget != 0 else Decimal(0)
        margin_delta = actual_margin - budget_margin

    is_black = actual_profit >= 0
    stance = "firmly **in the black** (profitable)" if is_black else "currently **in the red** (operating loss)"
    status = "favorable beat" if net_impact >= 0 else "unfavorable shortfall"

    text = (
        f"📊 **Profitability Standing: {cfg.period}**\n\n"
        f"Operations are {stance}!\n\n"
        f"• **Actual Operating Profit:** **{format_money(actual_profit, cur, places)}** (EBITDA margin: **{actual_margin:.1f}%**)\n"
        f"• **Budgeted Operating Profit:** {format_money(budget_profit, cur, places)} (Planned margin: {budget_margin:.1f}%)\n"
        f"• **Variance vs. Budget:** **{format_money(net_impact, cur, places)}** ({status}; margin change: {margin_delta:+.1f} pts)\n\n"
        f"Operating profit reflects gross commercial revenues ({format_money(result.revenue.actual, cur, places)}) "
        f"less total operating expenses ({format_money(result.expenses.actual, cur, places)})."
    )

    table = [
        {
            "Metric": "Total Revenue",
            "Budget": format_money(result.revenue.budget, cur, places),
            "Actual": format_money(result.revenue.actual, cur, places),
            f"Variance ({sym})": format_money(result.revenue.actual - result.revenue.budget, cur, places),
            "Flow": "Inflow",
        },
        {
            "Metric": "Total Expenses",
            "Budget": format_money(result.expenses.budget, cur, places),
            "Actual": format_money(result.expenses.actual, cur, places),
            f"Variance ({sym})": format_money(result.expenses.actual - result.expenses.budget, cur, places),
            "Flow": "Outflow",
        },
        {
            "Metric": "Operating Profit",
            "Budget": format_money(budget_profit, cur, places),
            "Actual": format_money(actual_profit, cur, places),
            f"Variance ({sym})": format_money(net_impact, cur, places),
            "Flow": "Retained Margin",
        },
    ]

    chips = ["Waterfall", "Run rate", "Executive memo", "Summary"]
    return Response(text=text, table=table, chips=chips, phase=Phase.EXPLORING)


def _handle_unknown(session: Session, text: str) -> Response:
    """Fallback for unrecognized queries with intelligent financial keyword detection and conversational guidance."""
    text_lower = text.strip().lower()

    if any(k in text_lower for k in ("margin", "ebitda", "profit", "operating income")):
        return _handle_profitability(session) if (session.phase == Phase.EXPLORING and session.result is not None) else Response(
            text="💡 **FP&A Note:** Net operating impact measures the overall variance contribution toward operating income / EBITDA. "
                 "Under standard financial rules, profit measures are not treated as additive revenue to prevent double-counting. "
                 "Try asking: `summary`, `what is net impact?`, or `totals`.",
            chips=["Summary", "Net impact", "Totals"],
            phase=session.phase,
        )

    if any(k in text_lower for k in ("forecast", "projection", "run rate", "reforecast")):
        return Response(
            text="💡 **FP&A Note:** This analysis evaluates actual performance against the baseline budget for the closed reporting period. "
                 "To project full-year outcomes based on current pace, ask for `run rate` or test scenarios with `what if revenue drops 5%?`.",
            chips=["Run rate", "Sensitivity", "Summary"],
            phase=session.phase,
        )

    # Direct line-item matching for conversational queries (e.g. 'what happened to marketing', 'is office supplies bad')
    if session.result is not None:
        line_items = [r.line_item for r in session.result.rows]
        resolved = _resolve_item_query(text, session)
        matches = find_line_item(resolved, line_items)
        if matches:
            matched_name = matches[0]
            session.last_focused_item = matched_name
            row = next(r for r in session.result.rows if r.line_item == matched_name)
            cfg = session.result.config
            places = report_places(session.result)
            status_desc = "favorable beat" if row.status == Status.FAVORABLE else ("unfavorable cost overrun" if row.line_type == LineType.EXPENSE else "unfavorable revenue shortfall")
            return Response(
                text=f"Here is what happened with **{safe_inline(row.line_item)}** in {cfg.period}:\n\n"
                     f"• **Budget:** {format_money(row.budget, cfg.currency, places)}\n"
                     f"• **Actual:** {format_money(row.actual, cfg.currency, places)}\n"
                     f"• **Variance:** **{format_money(row.variance_dollars, cfg.currency, places)}** "
                     f"({format_pct(row.budget, row.variance_dollars, row.percent_label)}, {status_desc})\n\n"
                     f"Would you like to inspect its causal driver decomposition (`why {safe_inline(row.line_item)}`) or simulate a change (`what if {safe_inline(row.line_item)} drops 5%`)?",
                table=[row_to_table_dict(row, cfg.currency, places)],
                chips=[f"Why {row.line_item}?", f"Detail {row.line_item}?", "Waterfall", "Summary"],
                phase=Phase.EXPLORING,
            )

    first_item = session.result.rows[0].line_item if (session.result and session.result.rows) else "Marketing"
    return Response(
        text=f"I want to make sure I provide the exact figures you need. I couldn't find an account matching \"{safe_inline(text)}\" in your current dataset.\n\n"
             "Here are a few ways we can explore your numbers:\n"
             f"• **Account Driver Breakdown:** Ask `why [Account Name]` (e.g. `why {safe_inline(first_item)}`)\n"
             "• **Profit Waterfall:** Ask for `waterfall` to reconcile budget to actual operating profit\n"
             "• **Scenario Analysis:** Try `what if revenue drops 5%?` or `sensitivity`\n"
             "• **Management Commentary:** Ask for `memo` or `tldr` for executive highlights",
        chips=["Summary", "Waterfall", "Biggest risks", "Help"],
        phase=session.phase,
    )
