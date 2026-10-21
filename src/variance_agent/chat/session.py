"""Session state machine for the deterministic chatbot.

Tracks the user's position in the guided conversation and holds all
mutable state in a single object.  Only one session exists at a time
(single-user local tool).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from variance_agent.models import AnalysisResult, LineType


class Phase(StrEnum):
    """Conversation phases in the guided intake flow."""

    AWAITING_FILE = "awaiting_file"
    AWAITING_PERIOD = "awaiting_period"
    AWAITING_THRESHOLDS = "awaiting_thresholds"
    AWAITING_CURRENCY = "awaiting_currency"
    RESOLVE_UNCLASSIFIED = "resolve_unclassified"
    EXPLORING = "exploring"


@dataclass
class Session:
    """Mutable conversation state for one analysis session."""

    phase: Phase = Phase.AWAITING_FILE

    # Populated after file upload
    source_bytes: bytes | None = None
    source_name: str | None = None
    source_suffix: str | None = None
    parsed_rows: list[dict[str, object]] | None = None
    worksheet: str | None = None
    available_sheets: list[str] = field(default_factory=list)

    # Populated during configuration
    period: str | None = None
    dollar_threshold: Decimal | None = None
    percent_threshold: Decimal | None = None
    currency: str = "USD"
    type_map: dict[str, LineType] = field(default_factory=dict)
    sheet: str | None = None

    # Unclassified items pending resolution
    unclassified_queue: list[str] = field(default_factory=list)

    # Populated after analysis
    result: AnalysisResult | None = None

    # Contextual memory for multi-turn drill-down
    last_focused_item: str | None = None
    last_table_items: list[str] = field(default_factory=list)

    # Deployment policy; survives reset(). False on hosted servers.
    path_exports_enabled: bool = True

    def reset(self) -> None:
        self.phase = Phase.AWAITING_FILE
        self.source_bytes = None
        self.source_name = None
        self.source_suffix = None
        self.parsed_rows = None
        self.worksheet = None
        self.available_sheets = []
        self.period = None
        self.dollar_threshold = None
        self.percent_threshold = None
        self.currency = "USD"
        self.type_map = {}
        self.sheet = None
        self.unclassified_queue = []
        self.result = None
        self.last_focused_item = None
        self.last_table_items = []
