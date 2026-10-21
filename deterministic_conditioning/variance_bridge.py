"""Bridge connecting variance_agent AnalysisResult to deterministic commentary generation."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from deterministic_conditioning.financial_commentary import (
    FinancialAuditSummary,
    FinancialCommentaryConditioner,
)

if TYPE_CHECKING:
    from variance_agent.models import AnalysisResult


def generate_verified_commentary(result: AnalysisResult) -> tuple[str, FinancialAuditSummary]:
    """Extract verified facts from AnalysisResult and generate conditioned commentary.

    Adheres strictly to prompt/variance_report_prompt.md:
    - Never recalculates, rounds, or alters audit facts.
    - Preserves exact currencies and numbers.
    - Enforces 4-22 rhythm and eliminates stock affirmations.
    """
    from variance_agent.comparison import basis_noun
    from variance_agent.models import Status

    period = result.config.period
    currency = result.config.currency

    # Calculate net material variance
    net_var = Decimal("0")
    mat_unfav_count = 0
    mat_fav_count = 0
    top_item: str | None = None
    top_var: Decimal | None = None
    max_abs_var = Decimal("-1")

    for row in result.material_rows:
        net_var += row.variance_dollars
        if row.status == Status.UNFAVORABLE:
            mat_unfav_count += 1
        elif row.status == Status.FAVORABLE:
            mat_fav_count += 1

        abs_var = abs(row.variance_dollars)
        if abs_var > max_abs_var:
            max_abs_var = abs_var
            top_item = row.line_item
            top_var = row.variance_dollars

    # Check for unexplained driver residuals or reconciliation gaps
    unexplained_residual = False
    if hasattr(result, "drivers") and result.drivers:
        for driver in result.drivers:
            if not getattr(driver, "reconciles", True):
                unexplained_residual = True
                break

    is_fav = net_var >= Decimal("0") if result.material_rows else True

    audit_summary = FinancialAuditSummary(
        period=period,
        currency=currency,
        net_variance_dollars=net_var,
        is_favorable=is_fav,
        material_unfavorable_count=mat_unfav_count,
        material_favorable_count=mat_fav_count,
        unexplained_residual_exists=unexplained_residual,
        top_material_item=top_item,
        top_material_variance=top_var,
    )

    conditioner = FinancialCommentaryConditioner()
    decision = conditioner.evaluate_audit_posture(audit_summary)
    commentary = conditioner.generate_adherent_commentary(
        audit_summary, decision, basis_noun(result.config.comparison_basis)
    )

    return commentary, audit_summary
