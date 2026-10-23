from __future__ import annotations

from decimal import Decimal, Inexact, ROUND_HALF_EVEN

from .models import Aggregate, AnalysisResult, AnalyzedRow, LineType, Status, MeasureKind
from .audience import is_audience_result
from .measures import currency_row, format_measure
from .numeric import financial_context
from .currencies import CURRENCY_SYMBOLS
from .analysis import verify_result
from .limits import display_text
from .comparison import basis_noun, comparison_heading, display_outcome, extended_heading
from .models import ComparisonBasis


def _safe_inline(value: object) -> str:
    text = display_text(str(value))
    replacements = (
        ("&", "&amp;"),
        ("\\", r"\\"),
        ("|", r"\|"),
        ("`", r"\`"),
        ("*", r"\*"),
        ("_", r"\_"),
        ("~", r"\~"),
        ("[", r"\["),
        ("]", r"\]"),
        ("<", "&lt;"),
        (">", "&gt;"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


_STATUS_WORDS = {
    Status.FAVORABLE: "Favorable",
    Status.UNFAVORABLE: "Unfavorable",
    Status.NEUTRAL: "Neutral",
    Status.UNCLASSIFIED: "Unclassified",
}


def _status_text(status: Status, plain: bool) -> str:
    """Status code (F/U) for Markdown, the full word for plain-text outputs."""
    return _STATUS_WORDS[status] if plain else status.value


def _inline(value: object, plain: bool) -> str:
    """Escape for Markdown, or only neutralize controls for plain-text outputs."""
    return display_text(str(value)) if plain else _safe_inline(value)


def _money(value: Decimal, currency: str = "USD", places: int = 2) -> str:
    with financial_context() as context:
        context.prec = max(context.prec, value.adjusted() + places + 2)
        context.traps[Inexact] = False
        rounded = value.quantize(Decimal("1").scaleb(-places), rounding=ROUND_HALF_EVEN)
    sign = "-" if rounded < 0 else ""
    return f"{sign}{CURRENCY_SYMBOLS[currency]}{rounded.copy_abs():,.{places}f}"


def _pct(budget: Decimal, variance: Decimal, label: str | None = None) -> str:
    if label:
        return label
    if budget == 0:
        return "0.0%" if variance == 0 else "N/A"
    numerator, numerator_scale = variance.as_integer_ratio()
    denominator, denominator_scale = abs(budget).as_integer_ratio()
    scaled = numerator * denominator_scale * 1000
    divisor = numerator_scale * denominator
    tenths, remainder = divmod(abs(scaled), abs(divisor))
    if 2 * remainder > abs(divisor) or (2 * remainder == abs(divisor) and tenths % 2):
        tenths += 1
    sign = "-" if tenths and (scaled < 0) else ""
    return f"{sign}{tenths // 10}.{tenths % 10}%"


def _report_places(result: AnalysisResult) -> int:
    values = [amount for row in result.rows
              for amount in (row.budget, row.actual, row.variance_dollars)]
    values.extend(amount for row in result.rows if row.driver_evidence is not None
                  for _, amount in row.driver_evidence.components)
    places = 2
    for value in values:
        exponent = value.normalize().as_tuple().exponent
        if isinstance(exponent, int):
            places = max(places, -exponent)
    return places


def _threshold_number(value: Decimal, minimum_places: int, scale: int = 0) -> str:
    """Keep every significant fractional digit in the configured cutoff."""
    whole, _, fraction = format(value.copy_abs(), 'f').partition('.')
    if scale:
        whole += fraction.ljust(scale, '0')[:scale]
        fraction = fraction[scale:]
    whole = format(int(whole), ',')
    fraction = fraction.rstrip('0').ljust(minimum_places, '0')
    return f"{whole}.{fraction}"


def _aggregate_line(
    label: str, aggregate: Aggregate, currency: str = "USD", places: int = 2
) -> str:
    return (
        f"- {label}: {_money(aggregate.actual, currency, places)} vs. "
        f"{_money(aggregate.budget, currency, places)} "
        f"({_money(aggregate.variance_dollars, currency, places)}, "
        f"{_pct(aggregate.budget, aggregate.variance_dollars, aggregate.percent_label)}, "
        f"{aggregate.status})"
    )


def _incomplete_aggregate_line(
    label: str, aggregate: Aggregate, currency: str = "USD", places: int = 2
) -> str:
    return (
        f"- {label}: N/A (classification incomplete; classified subtotal: "
        f"{_money(aggregate.actual, currency, places)} vs. {_money(aggregate.budget, currency, places)}, "
        f"{_money(aggregate.variance_dollars, currency, places)}, "
        f"{_pct(aggregate.budget, aggregate.variance_dollars, aggregate.percent_label)}, "
        f"{aggregate.status})"
    )


def _largest_by_status(
    rows: tuple[AnalyzedRow, ...], status: Status
) -> AnalyzedRow | None:
    return next((row for row in rows if row.status == status), None)


def _bottom_line(
    result: AnalysisResult,
    *,
    classification_incomplete: bool,
    has_revenue: bool,
    has_expenses: bool,
    places: int = 2,
    plain: bool = False,
) -> str:
    top = result.material_rows[0] if result.material_rows else None
    if classification_incomplete:
        sentence_one = (
            "Net operating impact is N/A because one or more rows are Unclassified; "
            "Revenue and Expense totals are incomplete."
        )
    elif not has_revenue or not has_expenses:
        missing = []
        if not has_revenue:
            missing.append("Revenue")
        if not has_expenses:
            missing.append("Expense")
        sentence_one = (
            "Net operating impact is N/A because the dataset does not contain "
            + " and ".join(missing)
            + " rows."
        )
    else:
        impact = result.revenue.variance_dollars - result.expenses.variance_dollars
        direction = "above" if impact > 0 else "below" if impact < 0 else "in line with"
        sentence_one = (
            f"Revenue and expense variances imply a net operating variance of "
            f"{_money(impact, result.config.currency, places)}, "
            f"{direction} {basis_noun(result.config.comparison_basis)} on this simplified revenue-less-expense basis."
        )

    if top is None:
        sentence_two = "No line item exceeded either configured materiality threshold."
    else:
        sentence_two = (
            f"The largest material variance is {_inline(top.line_item, plain)} at "
            f"{_money(top.variance_dollars, result.config.currency, places)} "
            f"({_status_text(top.status, plain)})."
        )
    return f"{sentence_one} {sentence_two}"


def _driver_sentence(
    row: AnalyzedRow,
    currency: str = "USD",
    places: int = 2,
    heading: str = "Budget",
    *,
    plain: bool = False,
) -> str:
    line_item = _inline(row.line_item, plain)
    strong = "" if plain else "**"
    evidence = row.driver_evidence
    if evidence and evidence.reconciles:
        components = "; ".join(
            f"{_inline(name, plain)}: {_money(value, currency, places)}"
            for name, value in evidence.components
        )
        return (
            f"{strong}{line_item} (Supported driver):{strong} {_inline(evidence.label, plain)} "
            "decomposition reconciles; "
            f"{components}."
        )

    likely_metrics = {
        "Revenue": "volume/units, price/rate, customer count, and mix",
        "Expense": "units/headcount, rate, vendor pricing, and timing",
    }.get(
        str(row.line_type),
        "an explicit Revenue/Expense classification plus operating driver metrics",
    )

    if evidence and not evidence.reconciles:
        return (
            f"{strong}{line_item} (Hypothesis):{strong} No causal claim is supported because the supplied "
            f"{_inline(evidence.label, plain)} fields do not reconcile to {heading}/Actual. "
            "Validate the driver data first."
        )
    return (
        f"{strong}{line_item} (Hypothesis):{strong} No causal driver is asserted from the supplied data. "
        f"To validate a cause, provide {likely_metrics}."
    )


def _recommendation(
    result: AnalysisResult, status: Status, kind: str, places: int = 2, *, plain: bool = False
) -> str:
    row = _largest_by_status(result.material_rows, status)
    label = _status_text(status, plain).lower() if plain else status.value
    if row is None:
        return f"- {kind}: No material {label} variance is available for a data-backed action."

    line_item = _inline(row.line_item, plain)
    evidence = row.driver_evidence
    if evidence and evidence.reconciles:
        largest_component = max(evidence.components, key=lambda pair: abs(pair[1]))
        if largest_component[0] == "Unexplained residual":
            return (f"- {kind}: Reconcile the unexplained residual for {line_item} before "
                    "assigning a cause-specific action.")
        return (
            f"- {kind}: Focus the action plan for {line_item} on its "
            f"{_inline(largest_component[0].lower(), plain)} "
            f"({_money(largest_component[1], result.config.currency, places)}), "
            "the largest reconciled component of the variance."
        )

    return (
        f"- {kind}: {line_item} is the largest material {label} variance, but the dataset "
        "does not support a causal corrective action; obtain the missing operating driver data before "
        "assigning a cause-specific intervention."
    )


def _data_request(top_rows: tuple[AnalyzedRow, ...], *, plain: bool = False) -> str:
    missing_metrics = [
        _inline(row.line_item, plain)
        for row in top_rows
        if not (row.driver_evidence and row.driver_evidence.reconciles)
        or any(name == "Unexplained residual" for name, _ in row.driver_evidence.components)
    ]
    if missing_metrics:
        return (
            "Provide reconciled operating driver metrics for: "
            + ", ".join(missing_metrics)
            + "."
        )
    return "No additional driver data is required for the analyzed top material variances."


@financial_context()
def render_markdown(result: AnalysisResult, *, top_root_causes: int = 5) -> str:
    verify_result(result)
    if isinstance(top_root_causes, bool) or not isinstance(top_root_causes, int) or top_root_causes < 1:
        raise ValueError("top_root_causes must be a positive integer.")
    if is_audience_result(result):
        return render_measure_report(result)
    cfg = result.config
    places = _report_places(result)
    heading = _safe_inline(comparison_heading(cfg.comparison_basis, cfg.comparison_label))
    classification_incomplete = any(
        row.line_type == LineType.UNCLASSIFIED for row in result.rows
    )
    has_revenue = any(
        row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
        for row in result.rows
    )
    has_expenses = any(
        row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
        for row in result.rows
    )

    if classification_incomplete:
        revenue_line = _incomplete_aggregate_line("Total Revenue", result.revenue, cfg.currency, places)
        expense_line = _incomplete_aggregate_line("Total Expenses", result.expenses, cfg.currency, places)
    else:
        revenue_line = (
            _aggregate_line("Total Revenue", result.revenue, cfg.currency, places)
            if has_revenue
            else "- Total Revenue: N/A (no Revenue rows supplied)"
        )
        expense_line = (
            _aggregate_line("Total Expenses", result.expenses, cfg.currency, places)
            if has_expenses
            else "- Total Expenses: N/A (no Expense rows supplied)"
        )

    bottom_line = _bottom_line(
        result,
        classification_incomplete=classification_incomplete,
        has_revenue=has_revenue,
        has_expenses=has_expenses,
        places=places,
    )
    lines: list[str] = [
        f"# FP&A Variance Report: {_safe_inline(cfg.period)}",
        "",
        "## Executive Summary",
        f"- Reporting Currency: {cfg.currency}",
        *([] if cfg.comparison_basis is ComparisonBasis.BUDGET
          else [f"- Compared Against: {heading}"]),
        revenue_line,
        expense_line,
        f"- Bottom Line Impact: {bottom_line}",
    ]
    if result.warnings:
        lines.append(
            "- Data Quality Note: "
            + " ".join(_safe_inline(warning) for warning in result.warnings)
        )
    if places > 2:
        lines.append(f"- Reporting Precision: {places} decimal places preserve fractional "
                     "amounts and exact detail-to-total reconciliation.")

    lines += [
        "",
        "## Material Variances",
        (
            f"Thresholds: {CURRENCY_SYMBOLS[cfg.currency]}"
            f"{_threshold_number(cfg.dollar_threshold, 2)} or "
            f"{_threshold_number(cfg.percent_threshold, 1, scale=2)}%"
        ),
        "",
        f"| Line Item | Type | {heading} | Actual | Var ({CURRENCY_SYMBOLS[cfg.currency]}) "
        "| Var (%) | Status |",
        "|---|---|---:|---:|---:|---:|---|",
    ]

    if result.material_rows:
        for row in result.material_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _safe_inline(row.line_item),
                        str(row.line_type),
                        _money(row.budget, cfg.currency, places),
                        _money(row.actual, cfg.currency, places),
                        _money(row.variance_dollars, cfg.currency, places),
                        _pct(row.budget, row.variance_dollars, row.percent_label),
                        str(row.status),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| _No material variances_ | — | — | — | — | — | — |")

    lines += ["", "## Root Cause Analysis"]
    top_rows = result.material_rows[:top_root_causes]
    if top_rows:
        lines.extend(f"- {_driver_sentence(row, cfg.currency, places, heading)}" for row in top_rows)
    else:
        lines.append("- No material variance requires root-cause analysis.")

    data_request = _data_request(top_rows)

    lines += [
        "",
        "## Strategic Recommendations",
        _recommendation(result, Status.UNFAVORABLE, "Mitigation", places),
        _recommendation(result, Status.FAVORABLE, "Optimization", places),
        f"- Data Request: {data_request}",
        "",
    ]
    return "\n".join(lines)


@financial_context()
def render_measure_report(result: AnalysisResult, *, segment_view: bool = False) -> str:
    """Describe declared metrics without adding incompatible units."""
    cfg = result.config
    if not segment_view and any(row.segment_declared for row in result.rows):
        from dataclasses import replace
        from .analysis import _aggregate
        lines = [f"# Variance Report: {_safe_inline(cfg.period)}", "",
                 "Totals are scoped to each supplied segment; no consolidated total is synthesized.", ""]
        for segment in dict.fromkeys(row.segment for row in result.rows):
            rows = tuple(row for row in result.rows if row.segment == segment)
            view = replace(result, rows=rows, material_rows=tuple(row for row in result.material_rows if row.segment == segment),
                           revenue=_aggregate(list(rows), LineType.REVENUE, cfg.comparison_basis, segment=segment),
                           expenses=_aggregate(list(rows), LineType.EXPENSE, cfg.comparison_basis, segment=segment))
            lines.extend(["## Segment: " + (_safe_inline(segment) if segment else "Unsegmented"), "",
                          "\n".join(render_measure_report(view, segment_view=True).splitlines()[4:])])
        return "\n".join(lines)
    heading = _safe_inline(extended_heading(cfg))
    lines = [f"# Variance Report: {_safe_inline(cfg.period)}", "", f"Reporting currency: {cfg.currency}", ""]
    money = tuple(row for row in result.rows if currency_row(row))
    complete = (all(row.line_type is not LineType.UNCLASSIFIED for row in money)
                and any(row.line_type is LineType.REVENUE for row in money)
                and any(row.line_type is LineType.EXPENSE for row in money))
    lines.extend(["## Currency totals", ""])
    if complete:
        lines.extend([_aggregate_line("Total Revenue", result.revenue, cfg.currency),
                      _aggregate_line("Total Expenses", result.expenses, cfg.currency),
                      "- Net operating variance: " + _money(result.revenue.variance_dollars -
                                                             result.expenses.variance_dollars, cfg.currency)])
    else:
        lines.append("Currency totals are incomplete; net operating impact is unavailable.")
    for label, rows in (("Currency variances", money),
                        ("Other measures", tuple(row for row in result.rows if not currency_row(row)))):
        if not rows:
            continue
        lines.extend(["", "## " + label, "", f"| Line Item | Measure | {heading} | Actual | Variance | Var (%) | Status | Material |",
                      "|---|---|---:|---:|---:|---:|---|---|"])
        row_notes = []
        for row in rows:
            variance = row.variance_bps if row.measure is MeasureKind.PERCENT else row.variance_dollars
            assert variance is not None
            cells = [_safe_inline(row.line_item), str(row.measure), format_measure(row.budget, row.measure, cfg.currency),
                     format_measure(row.actual, row.measure, cfg.currency),
                     format_measure(variance, row.measure, cfg.currency, variance=True),
                     _pct(row.budget, row.variance_dollars, row.percent_label),
                     display_outcome(row, cfg.comparison_basis), "Yes" if row.material else "No"]
            lines.append("| " + " | ".join(cells) + " |")
            if row.comparison_details is not None:
                detail = row.comparison_details
                if detail.guidance_position:
                    row_notes.append(f"- {_safe_inline(row.line_item)}: {detail.guidance_position}.")
                if detail.consensus_range_position:
                    row_notes.append(f"- {_safe_inline(row.line_item)}: {detail.consensus_range_position}.")
        if row_notes:
            lines.extend(["", *row_notes])
    if result.warnings:
        lines.extend(["", "## How the file was read", *["- " + _safe_inline(note) for note in result.warnings]])
    return "\n".join([*lines, ""])
