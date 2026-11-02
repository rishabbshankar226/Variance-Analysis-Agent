"""Running the analysis and labeling lines not yet labeled revenue or expense.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal
from variance_agent.audience import AudienceConfig
from variance_agent.measures import currency_row, measure_kind
from variance_agent.models import MeasureKind
from variance_agent.parsing import is_missing, normalize_row
from variance_agent.analysis import analyze_rows
from variance_agent.comparison import basis_for_header
from variance_agent.models import AnalysisConfig, ComparisonBasis, LineType
from variance_agent.numeric import financial_context
from variance_agent.parsing import parse_decimal
from variance_agent.intake import (
    apply_classification_rules,
    currency_conflict,
    infer_gl_range_rules,
    plain_analysis_error,
)
from ..intent import normalize_for_routing
from ..responses import NOT_YET_LABELED_PHRASE, Response, format_money, safe_inline
from ..session import Phase, Session
from ..views import with_lead
from ._common import _ask_period, _choosable, _file_is_gone, _sheet_chip
from .summary import _build_analysis_summary


_UNRECONCILED_SUMMARY = re.compile(r"Summary (?:'([^']+)'|\"([^\"]+)\") does not reconcile to (\w+) detail rows")


def _unreconciled_total_response(session: Session, technical: str, config: AnalysisConfig) -> Response | None:
    """The engine refused a total that doesn't match its lines: name the figures and offer to leave it out (X22).

    The lines' sum is the engine's own: the analysis of the rows without that total.
    """
    match = _UNRECONCILED_SUMMARY.search(technical)
    if match is None or session.parsed_rows is None:
        return None
    name, line_type = match.group(1) or match.group(2), match.group(3)
    total = next((row for row in session.parsed_rows if str(row.get("line_item", "")).strip() == name), None)
    figures = ", but it doesn't match them"
    try:
        details = analyze_rows([row for row in session.parsed_rows if row is not total], config)
        aggregate = details.expenses if line_type == LineType.EXPENSE.value else details.revenue
        for field, shown, summed in (("Budget", total and total.get("budget"), aggregate.budget),
                                     ("Actual", total and total.get("actual"), aggregate.actual)):
            if isinstance(shown, Decimal) and shown != summed:
                with financial_context():
                    apart = abs(shown - summed)
                figures = (f", but its {field} is {format_money(shown, config.currency, 2)} and those lines add up to "
                           f"{format_money(summed, config.currency, 2)} ({format_money(apart, config.currency, 2)} apart)")
                break
    except (ValueError, RuntimeError):
        pass  # the plain sentence, without figures
    session.pending_total_exclusion = name
    return Response(
        text=(f"'{safe_inline(name)}' looks like the total of the {line_type} lines above it{figures}. A total that "
              "doesn't match its lines can't be checked, so I stopped instead of guessing. Leave it out of the line "
              "items, or upload a corrected file."),
        chips=[f"Leave {name} out", "Upload a different file", "Show technical details"],
        phase=session.phase, level="error")


def _leave_total_out(session: Session) -> Response:
    """Leave the refused total out of the line items, record it, and run the analysis (X22)."""
    name = session.pending_total_exclusion
    assert name is not None and session.parsed_rows is not None
    session.pending_total_exclusion = None
    session.parsed_rows = [row for row in session.parsed_rows if str(row.get("line_item", "")).strip() != name]
    if session.intake_result is not None:
        session.intake_result.rows = session.parsed_rows
        session.intake_result.detected_totals.append(name)  # the audit's excluded totals
        session.intake_result.visible_transformations.append(
            f"Left out '{name}' at your request: it doesn't match the lines it totals.")
    return with_lead(_run_analysis(session), f"Left out '{safe_inline(name)}'.\n\n")


def _run_analysis(session: Session) -> Response:
    """Run the deterministic analysis engine and handle classification."""
    if session.parsed_rows is None:
        return _file_is_gone(session)
    if session.period is None:
        return _ask_period(session)
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
    if intake is not None and session.currency is not None and (conflict := currency_conflict(
            intake, session.currency, session.source_name or "your file")) is not None:
        problem, found = conflict  # no currency is converted (X5, X30): ask again, offering the marked one
        session.phase = Phase.AWAITING_CURRENCY
        fix = (f"Choose {found} to report in {found}, or upload the amounts in {session.currency}." if found
               else "Upload a file whose amounts are all in USD, EUR or GBP.")
        text = "\n".join(f"- {safe_inline(line[2:])}" if line.startswith("- ") else safe_inline(line)
                         for line in problem.splitlines())
        return Response(text=f"{text}\n\n{fix}", chips=[found] if found else ["Upload a different file"],
                        phase=Phase.AWAITING_CURRENCY, level="error")
    config = AnalysisConfig(
        period=session.period,
        dollar_threshold=session.dollar_threshold,
        percent_threshold=session.percent_threshold,
        type_map=dict(session.type_map),
        currency=session.currency,
        comparison_basis=intake.comparison_basis if intake is not None else ComparisonBasis.BUDGET,
        comparison_label=intake.comparison_label if intake is not None else None,
        comparison_name=intake.period_names.get(intake.comparison_label or "") if intake is not None else None,
    )

    if any("measure" in normalize_row(row) or "better" in normalize_row(row) for row in session.parsed_rows):
        config = AudienceConfig(
            config.period, config.dollar_threshold, config.percent_threshold, type_map=config.type_map,
            currency=config.currency, comparison_basis=config.comparison_basis, comparison_label=config.comparison_label,
            comparison_name=config.comparison_name,
            per_share_threshold=session.per_share_threshold, count_threshold=session.count_threshold,
            bps_threshold=session.bps_threshold, percent_values=session.percent_values,
            multiple_threshold=session.multiple_threshold,
            source_notes=tuple(intake.visible_transformations) if intake is not None else (),
        )
    try:
        with financial_context():
            if session.earnings_mode:
                from ..earnings import analyze_review, summary
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
        technical = str(exc)
        session.last_technical_detail = technical
        # On a first analysis only: a rerun after a new label rolls that label back instead.
        if session.result is None and (
                unreconciled := _unreconciled_total_response(session, technical, config)) is not None:
            return unreconciled  # the file and the setup answers stay; the total can be left out (X22)
        session.phase = Phase.AWAITING_FILE
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
        and not row.statement_kind  # balance sheet and cash flow lines are never revenue or expense (R7)
        and row.basis_details is None and row.classification_source != "metric"  # nor limit, target or metric rows
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
                     f"those items stay {NOT_YET_LABELED_PHRASE}.\n\n")


@financial_context()
def _next_measure_question(session: Session) -> Response | None:
    for index, raw in enumerate(session.parsed_rows or []):
        row = normalize_row(raw)
        name = str(row.get("line_item", "Row"))
        kind = measure_kind(row.get("measure"), name)
        question: str | None = None
        chips: list[str] | None = None
        pending = ("", index)
        # A target is neutral and a limit's direction is its Max or Min (PLAN.md R13, R15): neither asks for Better.
        neutral = session.intake_result is not None and session.intake_result.comparison_basis in {
            ComparisonBasis.LIMIT, ComparisonBasis.TARGET}
        if kind in {MeasureKind.PERCENT, MeasureKind.COUNT} and not neutral and not str(row.get("better") or "").strip():
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
                    MeasureKind.PERCENT: "bps_threshold", MeasureKind.MULTIPLE: "multiple_threshold"}.get(kind)
            if flag is not None and getattr(session, flag) is None:
                unit = {MeasureKind.PER_SHARE: "currency per share", MeasureKind.COUNT: "units",
                        MeasureKind.PERCENT: "basis points", MeasureKind.MULTIPLE: "turns (0.25 for 0.25x)"}[kind]
                question = f"What absolute threshold in {unit} should flag {kind} variances? Enter a non-negative number."
                pending = (flag, index)
        if question is not None:
            session.phase, session.measure_pending = Phase.AWAITING_MEASURE_OPTIONS, pending
            return Response(text=question, chips=chips, phase=session.phase)
    return None
