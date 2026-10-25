"""Designed views of chat replies: the optional `Response.view` field the page renders as a panel.

A view is built from the same engine objects as the reply's `text`, never parsed out of it, and
`text` keeps every figure and sentence. Values are the file's own labels, unescaped: the page sets
them with `textContent`. Only `lead` is Markdown, and it is the server's own text (escaped where it
quotes a label), rendered by the page's escaping Markdown renderer.

Shape of an intake view (`kind` "intake"):
    {"kind": "intake", "title": str, "lead": str | None,
     "rows": [{"label": str, "value": str}],
     "notes": [{"title": str, "items": [str], "more": int}],
     "question": str}
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from variance_agent.intake import IntakeResult, intake_summary_rows

from .responses import Response

INTAKE_TITLE = "How I read your file"
CONFIRM_QUESTION = "Does this look right?"


def _note(title: str, items: Sequence[str], more: int = 0) -> dict[str, object]:
    return {"title": title, "items": list(items), "more": more}


def intake_view(result: IntakeResult, question: str = CONFIRM_QUESTION) -> dict[str, object]:
    """The intake summary of a budget, forecast or prior-period file."""
    summary = intake_summary_rows(result)
    notes = []
    if summary.adjustments:
        notes.append(_note("Adjustments I made", summary.adjustments))
    if summary.attention:
        notes.append(_note("Needs your attention", summary.attention, summary.more_attention))
    return {
        "kind": "intake",
        "title": INTAKE_TITLE,
        "lead": None,
        "rows": [{"label": label, "value": value} for label, value in summary.rows],
        "notes": notes,
        "question": question,
    }


def earnings_intake_view(
    compared_against: Sequence[str], columns: Sequence[str], measures: Sequence[tuple[str, str]],
    headline_rows: Sequence[str], adjustments: Sequence[str],
) -> dict[str, object]:
    """The intake summary of a file of supplied earnings comparisons."""
    rows = [{"label": "Compared against", "value": ", ".join(compared_against)},
            {"label": "Columns read", "value": ", ".join(columns)}]
    rows += [{"label": line, "value": measure} for line, measure in measures]
    rows.append({"label": "Headline rows", "value": ", ".join(headline_rows)})
    return {
        "kind": "intake",
        "title": INTAKE_TITLE,
        "lead": None,
        "rows": rows,
        "notes": [_note("Adjustments I made", adjustments)] if adjustments else [],
        "question": CONFIRM_QUESTION,
    }


def with_lead(response: Response, lead: str) -> Response:
    """Put `lead` (Markdown) before a reply, in its text and, when it has one, above its view."""
    view = response.view
    if view is not None:
        earlier = view.get("lead")
        view = {**view, "lead": lead.strip() + (f"\n\n{earlier}" if isinstance(earlier, str) and earlier else "")}
    return replace(response, text=lead + response.text, view=view)
