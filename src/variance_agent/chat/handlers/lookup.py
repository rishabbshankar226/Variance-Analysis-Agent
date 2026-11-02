"""Explaining one line item.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

from variance_agent.models import AnalysisConfig, AnalyzedRow
from ..intent import ParsedIntent, find_line_item
from ..responses import (
    Response,
    format_money,
    format_pct,
    report_places,
    row_to_table_dict,
    safe_inline,
    status_label,
    type_label,
)
from ..session import Phase, Session
from ..views import figure, figures_view, pair
from ._common import _heading, _plain_heading
from ._items import _item_in_sentence, _not_found, _resolve_item_query, _rows_named


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
        f"• Type: {type_label(row.line_type)}",
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
