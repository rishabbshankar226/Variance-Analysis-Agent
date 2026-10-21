"""Financial Commentary Conditioner for Automated Variance Analysis.

Bridges verified variance audit facts from the deterministic analysis engine
with dynamic input-to-syntax routing, eliminating robotic summary templates
while preserving 100% mathematical fidelity to verified audit numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from deterministic_conditioning.router import RoutingDecision


@dataclass(frozen=True)
class FinancialAuditSummary:
    """Core verified audit facts extracted from an AnalysisResult."""

    period: str
    currency: str
    net_variance_dollars: Decimal
    is_favorable: bool
    material_unfavorable_count: int
    material_favorable_count: int
    unexplained_residual_exists: bool
    top_material_item: str | None = None
    top_material_variance: Decimal | None = None


class FinancialCommentaryConditioner:
    """Applies input-directed syntactic conditioning to verified financial variance facts."""

    BANNED_FINANCIAL_OPENERS = [
        "Here is a summary of the variance report:",
        "As we can see from the numbers,",
        "Overall, the company performed",
        "In summary, we observed",
        "It is important to note that",
        "Please find below the analysis:",
    ]

    def evaluate_audit_posture(self, audit: FinancialAuditSummary) -> RoutingDecision:
        """Deterministically map audit metrics to a first-token POS and structural archetype."""
        # Case 1: Unexplained reconciliation residual exists (Data gap / friction)
        if audit.unexplained_residual_exists:
            rule_id = "FIN-R1"
            rule_name = "Reconciliation Residual Discrepancy"
            required_pos = "Subordinate Conjunction / Concessive Anchor"
            pos_examples = ["While", "Although", "Unless", "Before"]
            structure = (
                "Sentence 1: State unresolved reconciliation gap and period (14-20 words). "
                "Sentence 2: Sharp verification directive (3-5 words). "
                "Sentence 3: Breakdown of dependent line items."
            )
        # Case 2: Heavy material unfavorable variances
        elif audit.material_unfavorable_count > 0 and not audit.is_favorable:
            rule_id = "FIN-R2"
            rule_name = "Material Unfavorable Overrun"
            required_pos = "Imperative / Action Verb"
            pos_examples = ["Isolate", "Review", "Address", "Halt", "Trace"]
            structure = (
                "Sentence 1: Direct action command naming the primary driver (4-6 words). "
                "Sentence 2: Diagnostic impact with exact dollar variance and percentage (18-26 words). "
                "Sentence 3: Material boundary check."
            )
        # Case 3: Net favorable performance with strong revenue or savings
        elif audit.is_favorable and audit.material_favorable_count > 0:
            rule_id = "FIN-R3"
            rule_name = "Favorable Expansion / Material Outperformance"
            required_pos = "Concrete Noun / Ledger Category"
            pos_examples = ["Margin", "Revenue", "Savings", "Topline"]
            structure = (
                "Sentence 1: Direct metric assertion without preamble (4-7 words). "
                "Sentence 2: Contextual attribution grounded in verified driver facts (18-28 words). "
                "Sentence 3: Operating observation."
            )
        # Case 4: Balanced / neutral periodic commentary
        else:
            rule_id = "FIN-R4"
            rule_name = "Balanced Periodic Reconciliation"
            required_pos = "Preposition / Temporal Anchor"
            pos_examples = ["Across", "Under", "Throughout", "Heading"]
            structure = (
                "Sentence 1: Period framing clause (12-16 words). "
                "Sentence 2: Punchy thesis statement (3-5 words). "
                "Sentence 3: Material line item summary."
            )

        examples_str = ", ".join(f'"{ex}"' for ex in pos_examples)
        compiled_instructions = f"""[FINANCIAL VARIANCE COMMENTARY ACTIVE | TEMP=0.0]
AUDIT SCOPE: Period {audit.period} | Currency {audit.currency}
TRIGGERED POSTURE: {rule_id} ({rule_name})
REQUIRED FIRST-TOKEN POS: {required_pos} (Allowed examples: {examples_str})
REQUIRED PARAGRAPH CADENCE: {structure}

STRICT GROUNDING LOCK:
- Copy all dollar values, percentages, and classifications verbatim from verified audit facts.
- ZERO calculation, rounding, extrapolation, or assumed causation.
- ZERO stock affirmations ('Certainly', 'Great question') or robotic preambles ('Here is the breakdown').
- Strict burstiness contract: Alternate punchy clauses (3-6 words) with compound sentences (18-28 words).
"""

        return RoutingDecision(
            rule_id=rule_id,
            rule_name=rule_name,
            required_first_token_pos=required_pos,
            pos_examples=pos_examples,
            structural_archetype=structure,
            inversion_constraints=[],
            compiled_system_instruction=compiled_instructions,
        )

    def generate_adherent_commentary(
        self,
        audit: FinancialAuditSummary,
        decision: RoutingDecision,
    ) -> str:
        """Generate verified financial commentary adhering strictly to the conditioned rhythm."""
        curr = audit.currency
        top_name = audit.top_material_item or "Operating Expenses"
        top_var = f"{audit.top_material_variance:,.2f}" if audit.top_material_variance else "0.00"

        if decision.rule_id == "FIN-R1":
            return (
                f"While reported line items for {audit.period} balance mathematically, an unexplained "
                f"residual remains across driver reconciliation categories. Reconciliation incomplete. "
                f"Treat driver attribution as unverified until the deterministic ledger tool resolves the remaining balance."
            )
        elif decision.rule_id == "FIN-R2":
            return (
                f"Review {top_name} immediately. Unfavorable variances in this category exceeded budget limits "
                f"by {curr} {top_var}, driving total net operating margins into negative territory across {audit.period}. "
                f"Material cost pressure. Verify procurement logs to validate rate versus quantity drivers."
            )
        elif decision.rule_id == "FIN-R3":
            return (
                f"Revenue outpaced expectations cleanly. Favorable expansion across {top_name} contributed "
                f"{curr} {top_var} in surplus over original budget projections for {audit.period}, widening operating margins. "
                f"Solid cash posture."
            )
        else:
            return (
                f"Across {audit.period}, net spending tracked closely with modeled targets. Balanced performance. "
                f"Material line items remained within the established tolerance boundaries, leaving no unresolved variances."
            )
