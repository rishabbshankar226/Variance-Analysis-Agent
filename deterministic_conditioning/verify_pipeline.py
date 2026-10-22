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


# The curated dataset that dataset_generator writes and that train_dpo_hf, train_unsloth_dpo and the
# Axolotl config read. ``data/dpo_pairs.jsonl`` is an older five-pair export without ``rule_id`` (only
# ``trainer.py`` still defaults to it); it is no longer audited here.
DATA_FILE = Path(__file__).parent / "data" / "dpo_expanded.jsonl"


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
    """Test dynamic router signal extraction and context state inversion.

    Every check is recorded rather than asserted: ``assert`` statements disappear under
    ``python -O`` and an exception would skip the remaining checks and the final verdict.
    """
    print("\n>>> TESTING DYNAMIC PROMPT ROUTER & STATE INVERSION...")
    router = DynamicPromptRouter()
    all_passed = True

    def check(condition: bool, passed_message: str, failed_message: str) -> None:
        nonlocal all_passed
        if condition:
            print(f"  ✓ PASS | {passed_message}")
        else:
            all_passed = False
            print(f"  ✗ FAIL | {failed_message}")

    # Test Case 1: Frustration signal (Rule R1)
    res_r1 = router.route("My pipeline keeps crashing on deploy and it is completely broken!")
    check(res_r1.rule_id == "R1" and "Imperative" in res_r1.required_first_token_pos,
          "Rule R1: Frustration signal correctly routed to Imperative opener.",
          f"Rule R1: expected R1 with an Imperative opener, got {res_r1.rule_id} "
          f"({res_r1.required_first_token_pos}).")

    # Test Case 2: Terse casual signal (Rule R2)
    res_r2 = router.route("hey what's good")
    check(res_r2.rule_id == "R2" and "Fragment" in res_r2.required_first_token_pos,
          "Rule R2: Terse casual input correctly routed to Fragment opener.",
          f"Rule R2: expected R2 with a Fragment opener, got {res_r2.rule_id} "
          f"({res_r2.required_first_token_pos}).")

    # Test Case 3: Direct question (Rule R3)
    res_r3 = router.route("What is Raft consensus?")
    check(res_r3.rule_id == "R3",
          "Rule R3: Direct interrogative correctly routed.",
          f"Rule R3: expected R3, got {res_r3.rule_id}.")

    # Test Case 4: Long analytical query (Rule R4)
    long_query = (
        "We are designing a distributed vector database pipeline and need to evaluate the latency trade-offs "
        "between synchronous raft consensus replication and asynchronous gossip protocols under high concurrency "
        "write loads across multiple cloud regions."
    )
    res_r4 = router.route(long_query)
    check(res_r4.rule_id == "R4" and "Subordinate" in res_r4.required_first_token_pos,
          "Rule R4: Complex architectural prompt routed to Subordinate clause.",
          f"Rule R4: expected R4 with a Subordinate opener, got {res_r4.rule_id} "
          f"({res_r4.required_first_token_pos}).")

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
    expected_inversions = ("FORBID opener: Active Verb", "Invert declarative closure", "Forbid em-dashes")
    missing = [constraint for constraint in expected_inversions if constraint not in inversions]
    check(not missing,
          "Last-Assistant-Turn Inversion: Detected prior Verb opener, declarative period, and em-dash.",
          f"Last-Assistant-Turn Inversion: missing {missing}.")

    return all_passed


def main() -> None:
    config = DeterministicDecodingConfig()

    print("=================================================================")
    print("   DETERMINISTIC LLM CONDITIONING & FINE-TUNING VERIFICATION    ")
    print("=================================================================")
    print(f"Decoding Config: {config.to_dict()}")

    gates_ok = run_gate_audit(DATA_FILE)
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
