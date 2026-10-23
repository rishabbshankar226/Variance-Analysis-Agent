"""Earnings presentation over verified comparisons; no parallel financial rules."""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from .audience import effective_layout, effective_per_share_lines
from .comparison import comparison_heading, display_outcome, extended_heading
from .measures import format_measure
from .models import AnalyzedRow, ComparisonBasis, LineType, MeasureKind
from .numeric import financial_context
from .report import _pct, _safe_inline

if TYPE_CHECKING:
    from .comparisons import TableAnalysis, UnavailableComparison

Identity = tuple[str, str, MeasureKind]


def headline_keys(table: TableAnalysis) -> set[Identity]:
    choices = {name.strip().casefold() for name in table.config.headline_items}
    names = {identity[0] for identity in table.metric_order}
    if choices - names:
        raise ValueError("Headline line item was not found: " + ", ".join(sorted(choices - names)) + ".")
    if choices:
        return {identity for identity in table.metric_order if identity[0] in choices}
    keys = set()
    for comparison in table.comparisons:
        for row in comparison.result.rows if comparison.result else ():
            if (row.line_type is LineType.REVENUE or row.measure is MeasureKind.PER_SHARE
                    or (row.measure is MeasureKind.PERCENT and "margin" in row.line_item.casefold())):
                keys.add((row.line_item.strip().casefold(), row.segment.strip().casefold(), row.measure))
        for absent in comparison.unavailable:
            if absent.measure is MeasureKind.PER_SHARE or "revenue" in absent.line_item.casefold() or (
                    absent.measure is MeasureKind.PERCENT and "margin" in absent.line_item.casefold()):
                keys.add((absent.line_item.strip().casefold(), absent.segment.strip().casefold(), absent.measure))
    return keys


def layout_note(table: TableAnalysis) -> str | None:
    if effective_layout(table.config) != "earnings":
        return None
    keys = headline_keys(table)
    names = list(dict.fromkeys(identity[0] for identity in table.metric_order if identity in keys))
    selected = "selected" if table.config.headline_items else "read"
    return (f"Using earnings layout; {selected} headline rows: {', '.join(names) or '(none)'}. "
            f"Per-share filing lines {'on' if effective_per_share_lines(table.config) else 'off'}.")


@financial_context()
def display_rows(table: TableAnalysis) -> list[dict[str, str]]:
    """Plain text cells for safe table widgets and escaped Markdown/Excel writers."""
    from .comparisons import _identity
    maps = []
    for comparison in table.comparisons:
        current: dict[Identity, list[AnalyzedRow | UnavailableComparison]] = defaultdict(list)
        for row in comparison.result.rows if comparison.result else ():
            current[_identity(row)].append(row)
        for absent in comparison.unavailable:
            current[(absent.line_item.strip().casefold(), absent.segment.strip().casefold(), absent.measure)].append(absent)
        if comparison.unavailable and any(len(entries) > 1 for entries in current.values()):
            raise ValueError("Missing comparisons and repeated metric identities need an explicit mapping to distinct line items.")
        maps.append(current)
    gaps = {(gap.line_item.casefold(), gap.segment.casefold(), gap.measure): gap for gap in table.estimate_vs_consensus}
    counters: dict[tuple[int, Identity], int] = defaultdict(int)
    output = []
    for identity in table.metric_order:
        entries = []
        for index, mapping in enumerate(maps):
            candidates = mapping.get(identity, [])
            offset = counters[(index, identity)]
            entries.append(candidates[offset] if offset < len(candidates) else None)
            counters[(index, identity)] += 1
        first = next((entry for entry in entries if entry is not None), None)
        if first is None:
            raise RuntimeError("Earnings metric order does not match analyzed rows.")
        kind = first.measure
        record = {"Line Item": first.line_item, "Segment": first.segment, "Measure": str(kind),
                  "Actual": format_measure(first.actual, kind, table.config.currency)}
        for comparison, entry in zip(table.comparisons, entries, strict=True):
            title = (extended_heading(comparison.result.config) if comparison.result is not None
                     else comparison_heading(comparison.basis, comparison.label))
            percent_column = title + (" YoY %" if title.startswith("Prior Year") else " % / bps")
            if isinstance(entry, AnalyzedRow):
                delta = entry.variance_bps if kind is MeasureKind.PERCENT else entry.variance_dollars
                assert delta is not None
                record.update({title + " comparison": format_measure(entry.budget, kind, table.config.currency),
                               title + " variance": format_measure(delta, kind, table.config.currency, variance=True),
                               percent_column: format_measure(delta, kind, variance=True) if kind is MeasureKind.PERCENT else
                               _pct(entry.budget, entry.variance_dollars, entry.percent_label),
                               title + " outcome": display_outcome(entry, comparison.basis)})
            else:
                record.update({title + " comparison": entry.reason if entry is not None else "",
                               title + " variance": "", percent_column: "", title + " outcome": ""})
            if comparison.basis is ComparisonBasis.GUIDANCE:
                detail = entry.comparison_details if entry is not None else None
                record["Guidance position"] = detail.guidance_position if detail and detail.guidance_position else ""
        if table.estimate_vs_consensus:
            gap = gaps.get(identity)
            record["Estimate - Consensus"] = format_measure(gap.variance, kind, table.config.currency) if gap else ""
            record["Estimate - Consensus % / bps"] = (
                format_measure(gap.variance_bps, kind, variance=True) if gap and gap.variance_bps is not None else
                _pct(gap.consensus, gap.variance, "N/A" if gap.consensus == 0 else None) if gap else "")
        output.append(record)
    return output


def _table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["No supplied rows in this section.", ""]
    columns = list(rows[0])
    return ["| " + " | ".join(_safe_inline(key) for key in columns) + " |",
            "|" + "|".join("---" for _ in columns) + "|",
            *["| " + " | ".join(_safe_inline(row[key]) for key in columns) + " |" for row in rows], ""]


@financial_context()
def render_earnings(table: TableAnalysis) -> str:
    rows = display_rows(table)
    keys = headline_keys(table)
    head = [row for row, key in zip(rows, table.metric_order, strict=True) if key in keys]
    other = [row for row, key in zip(rows, table.metric_order, strict=True) if key not in keys]
    lines = [f"# Earnings Review: {_safe_inline(table.config.period)}", "", "## Headline comparisons", "", *_table(head)]
    guidance = [row for row in rows if row.get("Guidance position")]
    if guidance:
        lines.extend(["## Guidance position", "", *_table(guidance)])
    if any(comparison.basis is ComparisonBasis.PRIOR_PERIOD for comparison in table.comparisons):
        lines.extend(["## Prior year / prior period", "", *_table(rows)])
    segments = list(dict.fromkeys(row["Segment"] for row in rows if row["Segment"]))
    if segments:
        lines.extend(["## Segments", "", "No consolidated total is synthesized.", ""])
        for segment in segments:
            lines.extend(["### " + _safe_inline(segment), "", *_table([row for row in rows if row["Segment"] == segment])])
    lines.extend(["## Other KPIs", "", *_table(other), "## How the file was read", ""])
    notes = [*table.inferences, *[warning for comparison in table.comparisons if comparison.result is not None
                                for warning in comparison.result.warnings]]
    lines.extend("- " + _safe_inline(note) for note in dict.fromkeys(notes))
    return "\n".join([*lines, ""])
