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
    # Facts that gate individual commentary clauses; a clause is omitted when its fact is unknown.
    revenue_variance_dollars: Decimal | None = None
    budget_operating_profit: Decimal | None = None
    actual_operating_profit: Decimal | None = None
    budget_margin_percent: Decimal | None = None
    actual_margin_percent: Decimal | None = None
    material_item_count: int | None = None
    unclassified_item_count: int = 0
    top_favorable_item: str | None = None
    top_favorable_variance: Decimal | None = None
    top_unfavorable_item: str | None = None
    top_unfavorable_variance: Decimal | None = None
    top_unfavorable_is_expense: bool | None = None

    @property
    def margin_direction(self) -> str | None:
        """'up', 'down' or 'flat' when both margins are known, otherwise None."""
        if self.budget_margin_percent is None or self.actual_margin_percent is None:
            return None
        if self.actual_margin_percent > self.budget_margin_percent:
            return "up"
        if self.actual_margin_percent < self.budget_margin_percent:
            return "down"
        return "flat"


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
        elif (audit.material_unfavorable_count > 0 and not audit.is_favorable
              and audit.net_variance_dollars < 0):
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
        elif (audit.is_favorable and audit.material_favorable_count > 0
              and audit.net_variance_dollars > 0):
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
        """Generate verified commentary; every clause is emitted only when a supplied fact supports it."""
        curr = audit.currency

        def amount(value: Decimal) -> str:
            return f"{curr} {abs(value):,.2f}"

        material = audit.material_item_count
        if material is None:
            material = audit.material_unfavorable_count + audit.material_favorable_count
        net = audit.net_variance_dollars
        margin = audit.margin_direction

        sentences: list[str]
        if decision.rule_id == "FIN-R1":
            sentences = [
                f"While reported line items for {audit.period} balance mathematically, an unexplained "
                "residual remains across driver reconciliation categories.",
                "Reconciliation incomplete.",
                "Treat driver attribution as unverified until the deterministic ledger tool resolves the remaining balance.",
            ]
        elif decision.rule_id == "FIN-R2":
            name = audit.top_unfavorable_item or audit.top_material_item
            variance = audit.top_unfavorable_variance
            if variance is None and audit.top_unfavorable_item is None:
                variance = audit.top_material_variance
            sentences = [f"Review {name} immediately." if name else "Review the unfavorable variances immediately."]
            detail = f"Its unfavorable variance reached {amount(variance)}" if name and variance is not None else ""
            shortfall = f"net operating shortfall of {amount(net)} across {audit.period}"
            sentences.append(f"{detail}, against a {shortfall}." if detail else f"Results show a {shortfall}.")
            if audit.actual_operating_profit is not None and audit.actual_operating_profit < 0:
                sentences.append("Operating profit turned negative.")
            elif margin == "down":
                sentences.append(
                    f"Operating margin narrowed from {audit.budget_margin_percent:.1f}% "
                    f"to {audit.actual_margin_percent:.1f}%."
                )
            if audit.top_unfavorable_is_expense is True:
                sentences += ["Material cost pressure.",
                              "Verify procurement logs to validate rate versus quantity drivers."]
            elif audit.top_unfavorable_is_expense is False:
                sentences += ["Material revenue shortfall.",
                              "Verify pipeline and pricing data to validate volume versus rate drivers."]
        elif decision.rule_id == "FIN-R3":
            name = audit.top_favorable_item or audit.top_material_item
            variance = audit.top_favorable_variance
            if variance is None and audit.top_favorable_item is None:
                variance = audit.top_material_variance
            revenue_up = audit.revenue_variance_dollars is not None and audit.revenue_variance_dollars > 0
            sentences = ["Revenue outpaced expectations cleanly." if revenue_up else "Results beat budget."]
            if name and variance is not None:
                clause = (f"Favorable variance across {name} contributed {amount(variance)} "
                          f"over original budget projections for {audit.period}")
            else:
                clause = f"Net operating impact finished {amount(net)} ahead of budget for {audit.period}"
            if margin == "up":
                clause += ", improving operating margin"
            elif margin == "down":
                clause += ", although operating margin still narrowed"
            sentences.append(clause + ".")
            sentences.append(f"Net operating beat: {amount(net)}.")
        else:
            if net > 0:
                position = f"{amount(net)} ahead of budget"
            elif net < 0:
                position = f"{amount(net)} behind budget"
            else:
                position = "exactly on budget"
            sentences = [f"Across {audit.period}, net operating impact finished {position}."]
            if material == 0:
                sentences += [
                    "Balanced performance.",
                    "Material line items remained within the established tolerance boundaries, "
                    "leaving no unresolved variances.",
                ]
            else:
                plural = "s" if material != 1 else ""
                sentences += [
                    "Offsetting variances.",
                    f"{material} material line item{plural} still need review before sign-off.",
                ]

        if audit.unclassified_item_count:
            plural = "s" if audit.unclassified_item_count != 1 else ""
            sentences.append(
                f"Excludes {audit.unclassified_item_count} unclassified line item{plural} from the net."
            )
        return " ".join(sentences)
