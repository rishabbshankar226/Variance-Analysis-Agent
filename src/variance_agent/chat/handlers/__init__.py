"""Deterministic handler functions for each chatbot intent.

Each handler receives the Session (which holds the AnalysisResult) and
any regex captures from the intent parser.  All financial values come
from the deterministic engine; handlers only perform lookups and
formatting.

The handlers live in one module per family (docs/improve/PLAN.md, S1); this package re-exports
every name imported from `variance_agent.chat.handlers` before the split.
"""

from __future__ import annotations

from ._common import _period_slug
from .upload import _intake_summary_text, handle_upload
from .export import _export_response, _layout_mapping_for
from .scenarios import _detect_period_elapsed_months
from .conversation import _KNOWLEDGE_TEXTS
from .router import handle_message

__all__ = [
    "_KNOWLEDGE_TEXTS",
    "_detect_period_elapsed_months",
    "_export_response",
    "_intake_summary_text",
    "_layout_mapping_for",
    "_period_slug",
    "handle_message",
    "handle_upload",
]
