"""Finding the line item a question names.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

import difflib
import re
from variance_agent.models import AnalysisResult, AnalyzedRow
from ..intent import normalize_for_routing
from ..responses import Response, safe_inline
from ..session import Phase, Session


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
    if re.sub(r"^the\s+", "", raw_lower) in ("last", "last item", "last one", "last row", "last line", "bottom", "bottom one", "lowest"):
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


# Words too common in account names to identify one on their own.
_GENERIC_ITEM_WORDS = frozenset({
    "revenue", "revenues", "expense", "expenses", "cost", "costs", "total", "sales", "income", "other",
})


# Words that are never an account name when they stand alone in a sentence ("is it over budget").
_SENTENCE_STOPWORDS = frozenset({
    "it", "is", "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "we", "us", "our", "up",
})
_WORD_RE = re.compile(r"[\w&]+")


def _items_named_in(text: str, items: list[str]) -> list[str]:
    """Line items whose whole name appears in the sentence as whole words, longest name first."""
    padded = f" {' '.join(_WORD_RE.findall(normalize_for_routing(text).lower()))} "
    named: list[str] = []
    for item in dict.fromkeys(items):
        words = _WORD_RE.findall(normalize_for_routing(item).lower())
        if not words or (len(words) == 1 and words[0] in _SENTENCE_STOPWORDS):
            continue
        if f" {' '.join(words)} " in padded:
            named.append(item)
    return sorted(named, key=len, reverse=True)


def _item_in_sentence(text: str, items: list[str], named: list[str] | None = None) -> str | None:
    """Find the one line item a free-form sentence names, e.g. 'is marketing bad?'.

    ``named`` is the result of ``_items_named_in`` when the caller already has it.
    """
    if named is None:
        named = _items_named_in(text, items)
    if named:
        return named[0]
    words = set(_WORD_RE.findall(normalize_for_routing(text).lower()))
    hits = [
        item for item in dict.fromkeys(items)
        if any(len(word) >= 4 and word not in _GENERIC_ITEM_WORDS and word in words
               for word in _WORD_RE.findall(normalize_for_routing(item).lower()))
    ]
    return hits[0] if len(hits) == 1 else None


# Spelling suggestions compare the query with every account name, so both sides are bounded:
# real account names are short, and a file can have a hundred thousand lines.
_SUGGEST_MAX_QUERY = 40
_SUGGEST_MAX_ITEMS = 2000


def _suggest_items(query: str, items: list[str], limit: int = 3) -> list[str]:
    """Close spellings of a line item (whole name or any word of it); deterministic."""
    q = normalize_for_routing(query).lower()
    if not 3 <= len(q) <= _SUGGEST_MAX_QUERY:
        return []
    scored: list[tuple[float, str]] = []
    for item in list(dict.fromkeys(items))[:_SUGGEST_MAX_ITEMS]:
        name = normalize_for_routing(item).lower()[:200]
        score = 0.0
        for candidate in [name, *name.split()]:
            matcher = difflib.SequenceMatcher(None, q, candidate)
            if matcher.real_quick_ratio() >= 0.75 and matcher.quick_ratio() >= 0.75:
                score = max(score, matcher.ratio())
        if score >= 0.75:
            scored.append((-score, item))
    return [item for _, item in sorted(scored)[:limit]]


def _not_found(display_q: str, query: str, items: list[str], verb: str) -> Response:
    """No-match reply with a bounded 'did you mean' for likely typos."""
    suggestions = _suggest_items(query, items)
    if suggestions:
        names = " or ".join(f"**{safe_inline(item)}**" for item in suggestions)
        return Response(
            text=f"No line item matching '{display_q}' was found. Did you mean {names}?",
            chips=[f"{verb} {item}?" for item in suggestions],
            phase=Phase.EXPLORING,
        )
    items_list = ", ".join(safe_inline(item) for item in items[:20])
    if len(items) > 20:
        items_list += f", and {len(items) - 20} more"
    return Response(
        text=f"No line item matching '{display_q}' was found.\n\nAvailable items: {items_list}",
        phase=Phase.EXPLORING,
    )


def _rows_named(result: AnalysisResult, name: str) -> list[AnalyzedRow]:
    """Every row with this exact line-item name (a name can repeat, e.g. one per department)."""
    return [row for row in result.rows if row.line_item == name]
