"""Unit and integration tests for deterministic_conditioning package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deterministic_conditioning.client_adapter import DeterministicChatClient
from deterministic_conditioning.config import DeterministicDecodingConfig
from deterministic_conditioning.curation_gates import CurationGates
from deterministic_conditioning.dataset_generator import EXPANDED_DATASET_SPECS
from deterministic_conditioning.financial_commentary import FinancialAuditSummary, FinancialCommentaryConditioner
from deterministic_conditioning.logits_processor import DeterministicLogitsProcessor
from deterministic_conditioning.router import DynamicPromptRouter


class TestDeterministicConfig:
    def test_default_values(self) -> None:
        cfg = DeterministicDecodingConfig()
        assert cfg.temperature == 0.0
        assert cfg.repetition_penalty == 1.10
        assert cfg.frequency_penalty == 0.20
        assert cfg.presence_penalty == 0.15
        assert cfg.no_repeat_ngram_size == 4

    def test_huggingface_export(self) -> None:
        cfg = DeterministicDecodingConfig()
        hf_dict = cfg.to_huggingface_dict()
        assert hf_dict["do_sample"] is False
        assert hf_dict["temperature"] is None
        assert hf_dict["repetition_penalty"] == 1.10
        assert hf_dict["no_repeat_ngram_size"] == 4

    def test_vllm_export(self) -> None:
        cfg = DeterministicDecodingConfig()
        vllm_dict = cfg.to_vllm_dict()
        assert vllm_dict["temperature"] == 0.0
        assert vllm_dict["frequency_penalty"] == 0.20
        assert vllm_dict["presence_penalty"] == 0.15


class TestDynamicPromptRouter:
    @pytest.fixture
    def router(self) -> DynamicPromptRouter:
        return DynamicPromptRouter()

    def test_r1_frustration_signal(self, router: DynamicPromptRouter) -> None:
        decision = router.route("Everything is broken and the database failed on startup!")
        assert decision.rule_id == "R1"
        assert "Imperative" in decision.required_first_token_pos
        assert "Check" in decision.pos_examples

    def test_r1_all_caps_signal(self, router: DynamicPromptRouter) -> None:
        decision = router.route("THE SERVER KEEPS CRASHING NOW")
        assert decision.rule_id == "R1"

    def test_r2_terse_casual_signal(self, router: DynamicPromptRouter) -> None:
        decision = router.route("hey what's up")
        assert decision.rule_id == "R2"
        assert "Fragment" in decision.required_first_token_pos

    def test_r3_interrogative_signal(self, router: DynamicPromptRouter) -> None:
        decision = router.route("How does consensus work?")
        assert decision.rule_id == "R3"
        assert "Predicate" in decision.required_first_token_pos

    def test_r4_long_analytical_signal(self, router: DynamicPromptRouter) -> None:
        prompt = (
            "We are designing a distributed vector database pipeline and need to evaluate the latency trade-offs "
            "between synchronous replication and asynchronous gossip protocols under high concurrency write loads."
        )
        # Note: prompt has >30 words with cloud/cache/distributed terminology
        extended_prompt = prompt + " This is critical across multi-tenant regions."
        decision = router.route(extended_prompt)
        assert decision.rule_id == "R4"
        assert "Subordinate" in decision.required_first_token_pos

    def test_r5_default_framing(self, router: DynamicPromptRouter) -> None:
        decision = router.route("Here is the latest architecture diagram for the user authentication flow.")
        assert decision.rule_id == "R5"

    def test_last_turn_state_inversion(self, router: DynamicPromptRouter) -> None:
        history = [
            {"role": "user", "content": "How do we store tokens safely?"},
            {
                "role": "assistant",
                "content": "Check your storage layer first. Secure cookies isolate tokens cleanly—preventing script access.",
            },
        ]
        decision = router.route("Can JavaScript read HttpOnly cookies?", history)
        inversions = " ".join(decision.inversion_constraints)

        # Prior opened with Verb ("Check")
        assert "FORBID opener: Active Verb" in inversions
        # Prior ended with period (".")
        assert "Invert declarative closure" in inversions
        # Prior used em-dash ("—")
        assert "Forbid em-dashes" in inversions


class TestCurationGates:
    @pytest.fixture
    def gates(self) -> CurationGates:
        return CurationGates()

    def test_gate_1_length_symmetry_pass(self, gates: CurationGates) -> None:
        chosen = "This is a twenty word test string designed to verify that the length symmetry algorithm properly passes valid inputs."
        rejected = "This is another twenty word test string created specifically to verify that the length ratio algorithm properly passes candidates."
        res = gates.check_gate_1_length_symmetry(chosen, rejected, max_delta=0.15)
        assert res.passed is True

    def test_gate_1_length_symmetry_fail(self, gates: CurationGates) -> None:
        chosen = "Short response."
        rejected = "This is a significantly longer response designed to deliberately fail the length symmetry gate."
        res = gates.check_gate_1_length_symmetry(chosen, rejected, max_delta=0.15)
        assert res.passed is False

    def test_gate_2_attractor_audit(self, gates: CurationGates) -> None:
        clean_text = "Check the logs immediately. Sockets are hanging."
        attractor_text = "Certainly! I'd be happy to help with that. Furthermore, here is a breakdown:"
        assert gates.check_gate_2_attractor_audit(clean_text).passed is True
        assert gates.check_gate_2_attractor_audit(attractor_text).passed is False

    def test_gate_3_burstiness(self, gates: CurationGates) -> None:
        # Alternating short (3-4 words) with long (20+ words)
        bursty_text = (
            "Total exposure. While localStorage indeed ignores automatic cookie payloads—dodging forged requests "
            "cleanly—it leaves your raw credentials sitting naked in JavaScript reach. Keys gone in seconds. "
            "One unvetted third-party npm package or malicious injected script reads your token store immediately, "
            "exfiltrating authentication state without touching network proxies. Store tokens in secure cookies instead."
        )
        assert gates.check_gate_3_burstiness(bursty_text, min_std_dev=6.0).passed is True

        # Uniform sentence length
        uniform_text = "This is the first sentence here. This is the second sentence now. This is the third sentence today."
        assert gates.check_gate_3_burstiness(uniform_text, min_std_dev=6.0).passed is False

    def test_gate_5_bullet_density(self, gates: CurationGates) -> None:
        prose_text = "First check the socket timeouts. Then inspect the pooler configuration."
        bullet_text = "Here are the points:\n- Point 1\n- Point 2"
        assert gates.check_gate_5_bullet_density(prose_text, is_casual_or_emotional=True).passed is True
        assert gates.check_gate_5_bullet_density(bullet_text, is_casual_or_emotional=True).passed is False


class TestDatasetIntegrity:
    def test_all_expanded_pairs_pass_gates(self) -> None:
        gates = CurationGates()
        for spec in EXPANDED_DATASET_SPECS:
            report = gates.validate_pair(
                scenario=f"Scenario {spec.scenario_id}: {spec.scenario_name}",
                chosen=spec.chosen,
                rejected=spec.rejected,
            )
            assert report.all_passed, f"Scenario {spec.scenario_id} failed gates: {[r.gate_name for r in report.results if not r.passed]}"

    def test_expanded_dataset_jsonl_matches_specs(self) -> None:
        jsonl_path = Path(__file__).parents[1] / "deterministic_conditioning" / "data" / "dpo_expanded.jsonl"
        assert jsonl_path.exists()
        with open(jsonl_path, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        assert len(lines) == len(EXPANDED_DATASET_SPECS)


class TestDeterministicChatClient:
    def test_multi_turn_simulation(self) -> None:
        client = DeterministicChatClient()
        r1 = client.step("hey what's good today")
        assert r1.history_turn_count == 1
        assert r1.routing_decision.rule_id == "R2"

        r2 = client.step("Can you explain Raft consensus without jargon?")
        assert r2.history_turn_count == 2
        assert r2.routing_decision.rule_id == "R3"
        # Prior turn ended with question, current turn must invert to declarative period
        assert any("Must terminate with a declarative period" in c for c in r2.routing_decision.inversion_constraints)

        client.reset_history()
        assert len(client.history) == 0


class TestDeterministicLogitsProcessor:
    def test_repetition_penalty(self) -> None:
        cfg = DeterministicDecodingConfig(repetition_penalty=1.20, frequency_penalty=0.0, presence_penalty=0.0, no_repeat_ngram_size=0)
        proc = DeterministicLogitsProcessor(cfg)
        logits = [2.0, -1.0, 3.0]
        # Token 0 is in history
        modified = proc.process(logits, generated_tokens=[0])
        # 2.0 / 1.2 = 1.6667
        assert round(modified[0], 3) == round(2.0 / 1.20, 3)
        assert modified[1] == -1.0
        assert modified[2] == 3.0

    def test_frequency_and_presence_penalty(self) -> None:
        cfg = DeterministicDecodingConfig(repetition_penalty=1.0, frequency_penalty=0.5, presence_penalty=0.2, no_repeat_ngram_size=0)
        proc = DeterministicLogitsProcessor(cfg)
        logits = [10.0, 10.0, 10.0]
        # Token 1 emitted twice
        modified = proc.process(logits, generated_tokens=[1, 1])
        # Token 1 penalty: 2 * 0.5 + 0.2 = 1.2 -> 10.0 - 1.2 = 8.8
        assert round(modified[1], 2) == 8.80
        assert modified[0] == 10.0

    def test_no_repeat_ngram_masking(self) -> None:
        import math
        cfg = DeterministicDecodingConfig(no_repeat_ngram_size=3)
        proc = DeterministicLogitsProcessor(cfg)
        # History has [10, 20, 30] earlier, and now ends with [10, 20]
        history = [10, 20, 30, 40, 10, 20]
        logits = [5.0] * 50
        modified = proc.process(logits, generated_tokens=history)
        # Token 30 completes the 3-gram (10, 20, 30) again -> must be -inf
        assert modified[30] == -math.inf
        # Other tokens untouched
        assert modified[29] == 5.0

    def test_decode_step_trace(self) -> None:
        cfg = DeterministicDecodingConfig(repetition_penalty=2.0)
        proc = DeterministicLogitsProcessor(cfg)
        # Raw argmax would be token 0 (logit 10.0), token 1 is 9.0
        # If token 0 was generated before, its logit drops to 5.0, so token 1 wins!
        selected, trace = proc.decode_step(raw_logits=[10.0, 9.0, 1.0], generated_tokens=[0], step_idx=1)
        assert trace.raw_argmax_token == 0
        assert selected == 1
        assert trace.was_modified is True


class TestFinancialCommentaryConditioner:
    from decimal import Decimal
    from deterministic_conditioning.financial_commentary import FinancialAuditSummary, FinancialCommentaryConditioner

    def test_reconciliation_residual_posture(self) -> None:
        from decimal import Decimal
        cond = FinancialCommentaryConditioner()
        audit = FinancialAuditSummary(
            period="Q3-2024",
            currency="USD",
            net_variance_dollars=Decimal("50000"),
            is_favorable=True,
            material_unfavorable_count=0,
            material_favorable_count=2,
            unexplained_residual_exists=True,
        )
        decision = cond.evaluate_audit_posture(audit)
        assert decision.rule_id == "FIN-R1"
        assert "Subordinate" in decision.required_first_token_pos
        commentary = cond.generate_adherent_commentary(audit, decision)
        assert commentary.startswith("While")
        assert "unexplained residual remains" in commentary

    def test_material_unfavorable_posture(self) -> None:
        from decimal import Decimal
        cond = FinancialCommentaryConditioner()
        audit = FinancialAuditSummary(
            period="Q3-2024",
            currency="USD",
            net_variance_dollars=Decimal("-120000"),
            is_favorable=False,
            material_unfavorable_count=3,
            material_favorable_count=0,
            unexplained_residual_exists=False,
            top_material_item="Cloud Infrastructure",
            top_material_variance=Decimal("-85000.00"),
        )
        decision = cond.evaluate_audit_posture(audit)
        assert decision.rule_id == "FIN-R2"
        assert "Imperative" in decision.required_first_token_pos
        commentary = cond.generate_adherent_commentary(audit, decision)
        assert commentary.startswith("Review Cloud Infrastructure immediately")


class TestAutoregressiveSimulation:
    def test_greedy_loop_trapping_and_escape(self) -> None:
        from deterministic_conditioning.simulate_generation import DeterministicTextGenerator, ToyLanguageModel

        model = ToyLanguageModel()

        # Baseline: trapped in loop
        baseline_cfg = DeterministicDecodingConfig(
            repetition_penalty=1.0, frequency_penalty=0.0, presence_penalty=0.0, no_repeat_ngram_size=0
        )
        out_baseline = DeterministicTextGenerator(model, baseline_cfg).generate(max_tokens=18)
        assert out_baseline.has_cyclic_loop is True

        # Conditioned: escaped
        conditioned_cfg = DeterministicDecodingConfig(
            repetition_penalty=1.15, frequency_penalty=0.20, presence_penalty=0.15, no_repeat_ngram_size=4
        )
        out_cond = DeterministicTextGenerator(model, conditioned_cfg).generate(max_tokens=18)
        assert out_cond.has_cyclic_loop is False
        assert any(t.was_modified for t in out_cond.step_traces)


class TestVarianceBridge:
    def test_generate_verified_commentary_with_analysis_result(self) -> None:
        from decimal import Decimal
        from variance_agent.models import Aggregate, AnalysisConfig, AnalysisResult, AnalyzedRow, LineType, Status
        from deterministic_conditioning.variance_bridge import generate_verified_commentary

        config = AnalysisConfig(
            period="Q3-2024",
            dollar_threshold=Decimal("1000.00"),
            percent_threshold=Decimal("0.10"),
            currency="USD",
        )
        row = AnalyzedRow(
            line_item="Hosting Infrastructure",
            line_type=LineType.EXPENSE,
            budget=Decimal("5000.00"),
            actual=Decimal("7500.00"),
            variance_dollars=Decimal("-2500.00"),
            variance_percent=Decimal("-0.50"),
            percent_label="-50.0%",
            status=Status.UNFAVORABLE,
            material=True,
            excluded_from_aggregation=False,
            driver_evidence=None,
            raw={},
        )
        agg_empty = Aggregate(Decimal("0"), Decimal("0"), Decimal("0"), None, None, Status.NEUTRAL)
        agg_exp = Aggregate(Decimal("5000"), Decimal("7500"), Decimal("-2500"), Decimal("-0.50"), "-50.0%", Status.UNFAVORABLE)

        result = AnalysisResult(
            config=config,
            rows=(row,),
            material_rows=(row,),
            revenue=agg_empty,
            expenses=agg_exp,
            warnings=(),
        )

        commentary, summary = generate_verified_commentary(result)
        assert summary.period == "Q3-2024"
        assert summary.is_favorable is False
        assert summary.material_unfavorable_count == 1
        assert "Review Hosting Infrastructure immediately" in commentary


