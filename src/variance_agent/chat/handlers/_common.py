"""Helpers every handler family shares: headings, tones, percentages, sheet words and the period question.

Moved from chat/handlers.py in Phase 4 of the improvement pass (S1); the code is unchanged.
"""

from __future__ import annotations

import re
from decimal import Decimal
from variance_agent.comparison import basis_noun, comparison_heading
from variance_agent.models import AnalysisConfig, AnalysisResult, AnalyzedRow, ComparisonBasis, LineType
from variance_agent.numeric import ratio
from variance_agent.intake import title_periods
from ..intent import normalize_for_routing
from ..responses import Response, safe_inline
from ..session import Phase, Session


def _is_budget(cfg: AnalysisConfig) -> bool:
    return cfg.comparison_basis is ComparisonBasis.BUDGET


def _noun(cfg: AnalysisConfig) -> str:
    """Lower-case name of the comparison, as in 'above budget' or 'above forecast'."""
    return basis_noun(cfg.comparison_basis)


def _heading(cfg: AnalysisConfig) -> str:
    """Title-case name of the comparison: 'Budget', 'Forecast' or 'Prior Period (FY2024)'."""
    return safe_inline(comparison_heading(cfg.comparison_basis, cfg.comparison_label))


def _plain_heading(cfg: AnalysisConfig) -> str:
    """`_heading` for a view, which the page sets as text: the label is not Markdown-escaped."""
    return comparison_heading(cfg.comparison_basis, cfg.comparison_label)


def _tone(value: Decimal) -> str:
    """The tone of a signed impact on profit, for a view."""
    return "favorable" if value > 0 else "unfavorable" if value < 0 else "neutral"


def _fu(variance: Decimal, *, higher_is_better: bool = True) -> str:
    """A total's table status: F or U, and Neutral at exactly zero, as the engine has it (C5)."""
    if variance == 0:
        return "Neutral"
    return "F" if (variance > 0) == higher_is_better else "U"


def _fu_between(new: Decimal, old: Decimal, *, higher_is_better: bool = True) -> str:
    """`_fu` for a move from `old` to `new`, by comparison only."""
    return _fu(Decimal((new > old) - (new < old)), higher_is_better=higher_is_better)


def _in_line(cfg: AnalysisConfig) -> str:
    """'in line with budget' (or the basis noun): the words for a total that matches exactly (C5)."""
    return f"in line with {'budget' if _is_budget(cfg) else _noun(cfg)}"


def _planned(cfg: AnalysisConfig) -> str:
    """Label for a comparison amount: 'Budgeted Revenue', 'Forecast Revenue'."""
    return "Budgeted" if _is_budget(cfg) else _heading(cfg)


def _ask_period(session: Session, lead: str = "") -> Response:
    """Ask for the reporting period, offering as chips any the file's title names (X35)."""
    session.phase = Phase.AWAITING_PERIOD
    named = title_periods(session.intake_result.raw_title_text) if session.intake_result is not None else []
    text = lead + "What reporting period does this analysis cover? (e.g., Q3 2026, October 2026, FY2026)"
    if not named:
        return Response(text=text, phase=Phase.AWAITING_PERIOD)
    periods = " and ".join(f"**{safe_inline(period)}**" for period in named)
    return Response(
        text=f"{text}\n\nYour file's title says {periods}: choose {'it' if len(named) == 1 else 'one'} below, "
             "or type a different period.",
        chips=named,
        phase=Phase.AWAITING_PERIOD,
    )


def _file_is_gone(session: Session) -> Response:
    """The stored file is missing, so a question that needs it restarts at the upload."""
    session.phase = Phase.AWAITING_FILE
    return Response(
        text="I no longer have your file. Please upload it again using the drop zone above.",
        chips=["Help"],
        phase=Phase.AWAITING_FILE,
    )


_MULTI_TABLE_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".pdf", ".htm", ".html"}  # an .xls that reads is Excel 2007+ (X17)


def _is_pdf(session: Session) -> bool:
    """Whether the session's file is a filing, whose tables are statements rather than sheets."""
    return (session.source_suffix or "").lower() in {".pdf", ".htm", ".html"}


def _sheet_word(session: Session) -> str:
    """A PDF holds statements where a workbook holds worksheets."""
    return "statement" if _is_pdf(session) else "worksheet"


def _choosable(session: Session, names: list[str]) -> list[str]:
    """Sheets worth offering as chips: in a PDF, only statements that can be compared."""
    result = session.intake_result
    if _is_pdf(session) and result is not None and result.comparable_sheets:
        return [name for name in names if name in result.comparable_sheets]
    return names


def _sheet_chip(session: Session, name: str) -> str:
    return f"{'Statement' if _is_pdf(session) else 'Sheet'} {name}"


def _pct_text(value: Decimal | None, spec: str = ".1f", suffix: str = "%") -> str:
    """Format a percentage, or N/A when its base was zero (the ratio is undefined)."""
    return "N/A" if value is None else f"{value:{spec}}{suffix}"


def _variance_percent(variance: Decimal, comparison: Decimal) -> Decimal | None:
    """Variance as a percent of the absolute comparison amount (the engine's rule), None if it is 0."""
    return None if comparison == 0 else ratio(variance, abs(comparison)) * Decimal(100)


def _pct_change(new: Decimal | None, old: Decimal | None) -> Decimal | None:
    return None if new is None or old is None else new - old


def _unclassified_note(result: AnalysisResult) -> str:
    """Caveat for totals that leave out unclassified rows, or '' when there are none."""
    count = sum(row.line_type == LineType.UNCLASSIFIED for row in _detail_rows(result))
    if not count:
        return ""
    return (f"Excludes {count} unclassified line item{'s' if count != 1 else ''} from these totals; "
            "classify them for complete figures.")


def _with_unclassified_note(text: str, result: AnalysisResult) -> str:
    """Append the unclassified-rows caveat to an answer built from category totals."""
    note = _unclassified_note(result)
    return f"{text}\n\n{note}" if note else text


def _detail_rows(result: AnalysisResult) -> list[AnalyzedRow]:
    """Line items without reconciled subtotal/total rows, which would double count."""
    return [row for row in result.rows if not row.excluded_from_aggregation]


def _period_slug(period: str) -> str:
    """The period as a file-name fragment: letters, digits, '-' and '_' only."""
    return re.sub(r"[^a-z0-9-]+", "_", normalize_for_routing(period).lower()).strip("_") or "period"
