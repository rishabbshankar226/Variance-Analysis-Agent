"""Bridge connecting variance_agent AnalysisResult to deterministic commentary generation."""

from __future__ import annotations

from decimal import Decimal, Inexact
from typing import TYPE_CHECKING

from deterministic_conditioning.financial_commentary import (
    FinancialAuditSummary,
    FinancialCommentaryConditioner,
)

if TYPE_CHECKING:
    from variance_agent.models import AnalysisResult, AnalyzedRow


def generate_verified_commentary(result: AnalysisResult) -> tuple[str, FinancialAuditSummary]:
    """Extract verified facts from AnalysisResult and generate conditioned commentary.

    Adheres strictly to prompt/variance_report_prompt.md:
    - Never recalculates, rounds, or alters audit facts.
    - Preserves exact currencies and numbers.
    - Enforces 4-22 rhythm and eliminates stock affirmations.

    Net impact and margins come from the category aggregates, which already apply the
    favourable/unfavourable sign convention and exclude subtotals and unclassified rows.
    """
    from variance_agent.models import LineType, Status
    from variance_agent.numeric import financial_context, ratio
    from variance_agent.report import _money, _report_places

    material = [row for row in result.material_rows if not row.excluded_from_aggregation]
    favorable = [row for row in material if row.status == Status.FAVORABLE]
    unfavorable = [row for row in material if row.status == Status.UNFAVORABLE]

    def largest(rows: list[AnalyzedRow]) -> AnalyzedRow | None:
        return max(rows, key=lambda row: abs(row.variance_dollars), default=None)

    top = largest(material)
    top_fav = largest(favorable)
    top_unfav = largest(unfavorable)

    with financial_context() as context:
        context.traps[Inexact] = False
        net_var = result.revenue.variance_dollars - result.expenses.variance_dollars
        budget_profit = result.revenue.budget - result.expenses.budget
        actual_profit = result.revenue.actual - result.expenses.actual
        budget_margin = (ratio(budget_profit, result.revenue.budget) * Decimal(100)
                         if result.revenue.budget != 0 else None)
        actual_margin = (ratio(actual_profit, result.revenue.actual) * Decimal(100)
                         if result.revenue.actual != 0 else None)

    # A material driver model that fails reconciliation leaves an unexplained residual.
    unexplained_residual = any(
        row.driver_evidence is not None and not row.driver_evidence.reconciles for row in material
    )

    audit_summary = FinancialAuditSummary(
        period=result.config.period,
        currency=result.config.currency,
        net_variance_dollars=net_var,
        is_favorable=net_var > 0,
        material_unfavorable_count=len(unfavorable),
        material_favorable_count=len(favorable),
        unexplained_residual_exists=unexplained_residual,
        top_material_item=top.line_item if top else None,
        top_material_variance=top.variance_dollars if top else None,
        revenue_variance_dollars=result.revenue.variance_dollars,
        budget_operating_profit=budget_profit,
        actual_operating_profit=actual_profit,
        budget_margin_percent=budget_margin,
        actual_margin_percent=actual_margin,
        material_item_count=len(material),
        unclassified_item_count=sum(row.line_type == LineType.UNCLASSIFIED for row in result.rows),
        top_favorable_item=top_fav.line_item if top_fav else None,
        top_favorable_variance=top_fav.variance_dollars if top_fav else None,
        top_unfavorable_item=top_unfav.line_item if top_unfav else None,
        top_unfavorable_variance=top_unfav.variance_dollars if top_unfav else None,
        top_unfavorable_is_expense=(top_unfav.line_type == LineType.EXPENSE) if top_unfav else None,
    )

    conditioner = FinancialCommentaryConditioner()
    decision = conditioner.evaluate_audit_posture(audit_summary)
    places = _report_places(result)
    commentary = conditioner.generate_adherent_commentary(
        audit_summary, decision, money=lambda value: _money(value, result.config.currency, places),
    )

    return commentary, audit_summary
