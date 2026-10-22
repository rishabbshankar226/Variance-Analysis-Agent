"""Verified commentary must not claim what the analysis result contradicts.

Covers three claims the Chrome QA matrix did not reach: "Balanced performance... no unresolved
variances" on a net-behind period with no material item, "turned negative" when the budget already
was a loss, and a zero-amount outperformance such as "outperformed plan by $0.00" (produced by the
chat TL;DR, so only the detector is exercised here).
"""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from deterministic_conditioning.benchmark import commentary_contradictions
from deterministic_conditioning.financial_commentary import FinancialAuditSummary, FinancialCommentaryConditioner
from deterministic_conditioning.variance_bridge import generate_verified_commentary
from variance_agent.analysis import analyze_rows
from variance_agent.models import AnalysisConfig, AnalysisResult
from variance_agent.numeric import financial_context
from variance_agent.parsing import load_input


def analyse(rows: list[tuple[str, str, int, int]], currency: str = "USD") -> AnalysisResult:
    csv = "Line Item,Type,Budget,Actual\n" + "".join(f"{n},{t},{b},{a}\n" for n, t, b, a in rows)
    parsed = load_input(csv.encode(), ".csv", source_name="case.csv")
    config = AnalysisConfig(period="Q3 2026", dollar_threshold=Decimal("10000"),
                            percent_threshold=Decimal("0.05"), currency=currency)
    with financial_context():
        return analyze_rows(parsed.rows, config)


def commentary(result: AnalysisResult) -> str:
    return generate_verified_commentary(result)[0]


# Net -5,000, but every line is inside both thresholds, so nothing is material.
BEHIND_NO_MATERIAL = [("Sales", "Revenue", 100000, 97000), ("Rent", "Expense", 50000, 52000)]
# Net +4,000 with nothing material.
AHEAD_NO_MATERIAL = [("Sales", "Revenue", 100000, 103000), ("Rent", "Expense", 50000, 49000)]
# Net exactly zero with nothing material.
FLAT_NO_MATERIAL = [("Sales", "Revenue", 100000, 102000), ("Rent", "Expense", 50000, 52000)]
# The budget already is a 30,000 loss; the actual loss is 60,000.
LOSS_WORSENS = [("Sales", "Revenue", 100000, 100000), ("Payroll", "Expense", 130000, 160000)]
# Budgeted profit of 20,000 becomes an actual loss of 20,000.
PROFIT_TURNS_NEGATIVE = [("Sales", "Revenue", 100000, 100000), ("Payroll", "Expense", 80000, 120000)]


@pytest.mark.parametrize("rows", [BEHIND_NO_MATERIAL, AHEAD_NO_MATERIAL])
def test_nonzero_net_with_no_material_item_is_not_called_balanced(rows: list[tuple[str, str, int, int]]) -> None:
    result = analyse(rows)
    assert not result.material_rows
    lower = commentary(result).lower()
    assert "balanced performance" not in lower
    assert "no unresolved variances" not in lower
    assert "tolerance" in lower
    assert commentary_contradictions(commentary(result), result) == []


def test_net_behind_budget_commentary_says_so() -> None:
    text = commentary(analyse(BEHIND_NO_MATERIAL))
    assert "$5,000.00 behind budget" in text


def test_exactly_flat_net_may_still_be_called_balanced() -> None:
    result = analyse(FLAT_NO_MATERIAL)
    text = commentary(result)
    assert "exactly on budget" in text and "Balanced performance." in text
    assert commentary_contradictions(text, result) == []


def test_worsening_budgeted_loss_does_not_claim_profit_turned_negative() -> None:
    result = analyse(LOSS_WORSENS)
    text = commentary(result)
    assert "turned negative" not in text.lower()
    assert "operating loss widened versus budget" in text.lower()
    assert commentary_contradictions(text, result) == []


def test_profit_that_really_turns_negative_still_says_so() -> None:
    result = analyse(PROFIT_TURNS_NEGATIVE)
    text = commentary(result)
    assert "Operating profit turned negative." in text
    assert commentary_contradictions(text, result) == []


def test_loss_wording_follows_the_comparison_basis_noun() -> None:
    audit = FinancialAuditSummary(
        period="Q3", currency="USD", net_variance_dollars=Decimal("-30000"), is_favorable=False,
        material_unfavorable_count=1, material_favorable_count=0, unexplained_residual_exists=False,
        top_unfavorable_item="Payroll", top_unfavorable_variance=Decimal("30000"),
        budget_operating_profit=Decimal("-30000"), actual_operating_profit=Decimal("-60000"),
        top_unfavorable_is_expense=True,
    )
    conditioner = FinancialCommentaryConditioner()
    decision = conditioner.evaluate_audit_posture(audit)
    assert decision.rule_id == "FIN-R2"
    text = conditioner.generate_adherent_commentary(audit, decision, comparison_noun="forecast")
    assert "operating loss widened versus the forecast" in text.lower()
    unknown_budget = FinancialAuditSummary(**{**audit.__dict__, "budget_operating_profit": None})
    text = conditioner.generate_adherent_commentary(unknown_budget, decision)
    assert "turned negative" not in text and "Operating profit is negative." in text


# ---------------------------------------------------------------------------
# The detector itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("rows", "claim"), [
    (BEHIND_NO_MATERIAL, "Across Q3 2026, net operating impact finished $5,000.00 behind budget. Balanced performance."),
    (BEHIND_NO_MATERIAL, "Material line items remained within tolerance, leaving no unresolved variances."),
    (AHEAD_NO_MATERIAL, "Balanced performance. Nothing to review."),
    (AHEAD_NO_MATERIAL, "Leaving no unresolved variances."),
    (LOSS_WORSENS, "Operating profit turned negative."),
    (LOSS_WORSENS, "Operating profit slid into negative territory."),
])
def test_detector_flags_the_new_contradictions(rows: list[tuple[str, str, int, int]], claim: str) -> None:
    assert commentary_contradictions(claim, analyse(rows)), claim


@pytest.mark.parametrize("claim", [
    "Top-line revenue outperformed plan by $0.00.",
    "Revenue delivered a $0.00 beat.",
    "A shortfall of USD 0.00 against budget.",
    "Results finished €0.00 ahead of budget.",
    "Net operating impact finished £0 behind budget.",
])
def test_detector_flags_a_zero_amount_outperformance_or_shortfall(claim: str) -> None:
    assert any("zero" in problem for problem in commentary_contradictions(claim, analyse(PROFIT_TURNS_NEGATIVE))), claim


@pytest.mark.parametrize("claim", [
    "Top-line revenue outperformed plan by $3,000.00.",
    "Net operating impact finished exactly on budget.",
    "Revenue beat plan by $10.05, a shortfall of $0.50 elsewhere.",
    "Payroll sits at $0.00 budget with an overrun of $1,200.00.",
])
def test_detector_does_not_flag_nonzero_amounts(claim: str) -> None:
    problems = [p for p in commentary_contradictions(claim, analyse(PROFIT_TURNS_NEGATIVE)) if "zero" in p]
    assert problems == [], claim


def test_detector_still_flags_the_known_old_wording() -> None:
    result = analyse(BEHIND_NO_MATERIAL)
    assert commentary_contradictions("Revenue outpaced expectations cleanly. Solid cash posture.", result)


# ---------------------------------------------------------------------------
# Seeded sweep: whatever the data, the engine's own commentary stays truthful
# ---------------------------------------------------------------------------

def random_rows(rng: random.Random) -> list[tuple[str, str, int, int]]:
    rows: list[tuple[str, str, int, int]] = []
    for kind, count in (("Revenue", rng.randint(1, 3)), ("Expense", rng.randint(1, 3))):
        for index in range(count):
            budget = rng.choice([0, 1000, 5000, 20000, 50000, 100000, 250000])
            factor = rng.choice([0.5, 0.9, 0.97, 1.0, 1.03, 1.1, 1.5])
            rows.append((f"{kind} {index + 1}", kind, budget, round(budget * factor)))
    return rows


def test_commentary_is_truthful_across_a_seeded_sweep() -> None:
    rng = random.Random(20261021)
    postures: set[str] = set()
    failures: list[str] = []
    for case in range(300):
        rows = random_rows(rng)
        result = analyse(rows)
        text, summary = generate_verified_commentary(result)
        postures.add(FinancialCommentaryConditioner().evaluate_audit_posture(summary).rule_id)
        failures += [f"case {case} {rows}: {problem} :: {text}" for problem in commentary_contradictions(text, result)]
    assert postures >= {"FIN-R2", "FIN-R3", "FIN-R4"}, postures
    assert failures == [], "\n".join(failures[:5])
