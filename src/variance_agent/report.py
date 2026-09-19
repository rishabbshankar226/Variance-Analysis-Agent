from __future__ import annotations

from decimal import Decimal

from .models import Aggregate, AnalysisResult, AnalyzedRow, Status


def _money(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def _pct(value: Decimal | None, label: str | None = None) -> str:
    if label:
        return label
    if value is None:
        return "N/A"
    return f"{value * Decimal('100'):.1f}%"


def _aggregate_line(label: str, aggregate: Aggregate) -> str:
    return (
        f"- {label}: {_money(aggregate.actual)} vs. {_money(aggregate.budget)} "
        f"({_money(aggregate.variance_dollars)}, "
        f"{_pct(aggregate.variance_percent, aggregate.percent_label)}, {aggregate.status})"
    )


def _largest_by_status(rows: tuple[AnalyzedRow, ...], status: Status) -> AnalyzedRow | None:
    return next((row for row in rows if row.status == status), None)


def _bottom_line(result: AnalysisResult) -> str:
    impact = result.revenue.variance_dollars - result.expenses.variance_dollars
    direction = "above" if impact > 0 else "below" if impact < 0 else "in line with"
    sentence_one = (
        f"Revenue and expense variances imply a net operating variance of {_money(impact)}, "
        f"{direction} budget on this simplified revenue-less-expense basis."
    )

    top = result.material_rows[0] if result.material_rows else None
    if top is None:
        sentence_two = "No line item exceeded either configured materiality threshold."
    else:
        sentence_two = (
            f"The largest material variance is {top.line_item} at "
            f"{_money(top.variance_dollars)} ({top.status})."
        )
    return f"{sentence_one} {sentence_two}"


def _driver_sentence(row: AnalyzedRow) -> str:
    evidence = row.driver_evidence
    if evidence and evidence.reconciles:
        components = "; ".join(f"{name}: {_money(value)}" for name, value in evidence.components)
        return f"**{row.line_item} — Supported driver:** {evidence.label} decomposition reconciles; {components}."

    likely_metrics = {
        "Revenue": "volume/units, price/rate, customer count, and mix",
        "Expense": "units/headcount, rate, vendor pricing, and timing",
    }.get(str(row.line_type), "an explicit Revenue/Expense classification plus operating driver metrics")

    if evidence and not evidence.reconciles:
        return (
            f"**{row.line_item} — Hypothesis:** No causal claim is supported because the supplied "
            f"{evidence.label} fields do not reconcile to Budget/Actual. Validate the driver data first."
        )
    return (
        f"**{row.line_item} — Hypothesis:** No causal driver is asserted from the supplied data. "
        f"To validate a cause, provide {likely_metrics}."
    )


def _recommendation(result: AnalysisResult, status: Status, kind: str) -> str:
    row = _largest_by_status(result.material_rows, status)
    if row is None:
        return f"- {kind}: No material {status.value} variance is available for a data-backed action."

    evidence = row.driver_evidence
    if evidence and evidence.reconciles:
        largest_component = max(evidence.components, key=lambda pair: abs(pair[1]))
        return (
            f"- {kind}: Focus the action plan for {row.line_item} on its {largest_component[0].lower()} "
            f"({_money(largest_component[1])}), the largest reconciled component of the variance."
        )

    return (
        f"- {kind}: {row.line_item} is the largest material {status.value} variance, but the dataset "
        "does not support a causal corrective action; obtain the missing operating driver data before "
        "assigning a cause-specific intervention."
    )


def render_markdown(result: AnalysisResult, *, top_root_causes: int = 5) -> str:
    cfg = result.config
    lines: list[str] = [
        f"# FP&A Variance Report: {cfg.period}",
        "",
        "## Executive Summary",
        _aggregate_line("Total Revenue", result.revenue),
        _aggregate_line("Total Expenses", result.expenses),
        f"- Bottom Line Impact: {_bottom_line(result)}",
    ]
    if result.warnings:
        lines.append("- Data Quality Note: " + " ".join(result.warnings))

    lines += [
        "",
        "## Material Variances",
        (
            f"Thresholds: {_money(cfg.dollar_threshold)} or "
            f"{cfg.percent_threshold * Decimal('100'):.1f}%"
        ),
        "",
        "| Line Item | Type | Budget | Actual | Var ($) | Var (%) | Status |",
        "|---|---|---:|---:|---:|---:|---|",
    ]

    if result.material_rows:
        for row in result.material_rows:
            lines.append(
                "| "
                + " | ".join(
                    [
                        row.line_item.replace("|", r"\|"),
                        str(row.line_type),
                        _money(row.budget),
                        _money(row.actual),
                        _money(row.variance_dollars),
                        _pct(row.variance_percent, row.percent_label),
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
        lines.extend(f"- {_driver_sentence(row)}" for row in top_rows)
    else:
        lines.append("- No material variance requires root-cause analysis.")

    missing_metrics = []
    for row in top_rows:
        if not (row.driver_evidence and row.driver_evidence.reconciles):
            missing_metrics.append(row.line_item)
    if missing_metrics:
        data_request = (
            "Provide reconciled operating driver metrics for: " + ", ".join(missing_metrics) + "."
        )
    else:
        data_request = "No additional driver data is required for the analyzed top material variances."

    lines += [
        "",
        "## Strategic Recommendations",
        _recommendation(result, Status.UNFAVORABLE, "Mitigation"),
        _recommendation(result, Status.FAVORABLE, "Optimization"),
        f"- Data Request: {data_request}",
        "",
    ]
    return "\n".join(lines)
