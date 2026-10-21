"""Automated verification pipeline for the deterministic conditioning package.

Validates the DPO pairs against all 5 curation gates and tests the dynamic
prompt router and state inverter across all operational conditions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from deterministic_conditioning.config import DeterministicDecodingConfig
from deterministic_conditioning.curation_gates import CurationGates
from deterministic_conditioning.router import DynamicPromptRouter


def run_gate_audit(data_path: Path) -> bool:
    """Run full 5-gate audit on the DPO dataset."""
    print("\n>>> RUNNING 5-GATE SFT/DPO DATASET AUDIT...")
    gates = CurationGates()

    with open(data_path, "r", encoding="utf-8") as f:
        pairs = [json.loads(line) for line in f if line.strip()]

    all_passed = True
    chosen_texts: list[str] = []

    for item in pairs:
        scenario = f"Scenario {item['scenario_id']}: {item['scenario_name']}"
        chosen = item["chosen"]
        rejected = item["rejected"]
        chosen_texts.append(chosen)

        report = gates.validate_pair(scenario, chosen, rejected)
        print(f"\n[{'PASS' if report.all_passed else 'FAIL'}] {scenario}")
        for r in report.results:
            status = "✓ PASS" if r.passed else "✗ FAIL"
            print(f"    {status} | {r.gate_name:<32} | Value: {r.metric_value} (Limit: {r.threshold})")
            if not r.passed:
                print(f"          Details: {r.details}")
                all_passed = False

    # Gate 4: Dataset-wide First-Bigram Shannon Entropy
    g4_result = gates.check_gate_4_dataset_entropy(chosen_texts)
    status_g4 = "✓ PASS" if g4_result.passed else "✗ FAIL"
    print(f"\n[{'PASS' if g4_result.passed else 'FAIL'}] Dataset-Level Metrics:")
    print(f"    {status_g4} | {g4_result.gate_name:<32} | Value: {g4_result.metric_value} (Limit: {g4_result.threshold})")
    print(f"          Details: {g4_result.details}")
    if not g4_result.passed:
        all_passed = False

    return all_passed


def run_router_tests() -> bool:
    """Test dynamic router signal extraction and context state inversion."""
    print("\n>>> TESTING DYNAMIC PROMPT ROUTER & STATE INVERSION...")
    router = DynamicPromptRouter()
    all_passed = True

    # Test Case 1: Frustration signal (Rule R1)
    res_r1 = router.route("My pipeline keeps crashing on deploy and it is completely broken!")
    assert res_r1.rule_id == "R1", f"Expected R1, got {res_r1.rule_id}"
    assert "Imperative" in res_r1.required_first_token_pos
    print("  ✓ PASS | Rule R1: Frustration signal correctly routed to Imperative opener.")

    # Test Case 2: Terse casual signal (Rule R2)
    res_r2 = router.route("hey what's good")
    assert res_r2.rule_id == "R2", f"Expected R2, got {res_r2.rule_id}"
    assert "Fragment" in res_r2.required_first_token_pos
    print("  ✓ PASS | Rule R2: Terse casual input correctly routed to Fragment opener.")

    # Test Case 3: Direct question (Rule R3)
    res_r3 = router.route("What is Raft consensus?")
    assert res_r3.rule_id == "R3", f"Expected R3, got {res_r3.rule_id}"
    print("  ✓ PASS | Rule R3: Direct interrogative correctly routed.")

    # Test Case 4: Long analytical query (Rule R4)
    long_query = (
        "We are designing a distributed vector database pipeline and need to evaluate the latency trade-offs "
        "between synchronous raft consensus replication and asynchronous gossip protocols under high concurrency "
        "write loads across multiple cloud regions."
    )
    res_r4 = router.route(long_query)
    assert res_r4.rule_id == "R4", f"Expected R4, got {res_r4.rule_id}"
    assert "Subordinate" in res_r4.required_first_token_pos
    print("  ✓ PASS | Rule R4: Complex architectural prompt routed to Subordinate clause.")

    # Test Case 5: State Inversion over history
    history = [
        {"role": "user", "content": "How do cookies work?"},
        {
            "role": "assistant",
            "content": "Check your browser headers first. They handle credentials cleanly—never expose raw tokens.",
        },
    ]
    res_inv = router.route("Can we read them with JS?", history)
    inversions = " ".join(res_inv.inversion_constraints)

    # Prior opened with "Check" (Verb), ended with "." and used an em-dash
    assert "FORBID opener: Active Verb" in inversions
    assert "Invert declarative closure" in inversions
    assert "Forbid em-dashes" in inversions
    print("  ✓ PASS | Last-Assistant-Turn Inversion: Detected prior Verb opener, declarative period, and em-dash.")

    return all_passed


def main() -> None:
    data_file = Path(__file__).parent / "data" / "dpo_pairs.jsonl"
    config = DeterministicDecodingConfig()

    print("=================================================================")
    print("   DETERMINISTIC LLM CONDITIONING & FINE-TUNING VERIFICATION    ")
    print("=================================================================")
    print(f"Decoding Config: {config.to_dict()}")

    gates_ok = run_gate_audit(data_file)
    router_ok = run_router_tests()

    print("\n=================================================================")
    if gates_ok and router_ok:
        print(">>> ALL VERIFICATION SUITES PASSED (100% COMPLIANT).")
        print("=================================================================\n")
        sys.exit(0)
    else:
        print(">>> VERIFICATION FAILED.")
        print("=================================================================\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
