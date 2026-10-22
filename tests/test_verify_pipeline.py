"""verify_pipeline must be able to fail, and must audit the dataset the trainers consume."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from deterministic_conditioning import verify_pipeline
from deterministic_conditioning.dataset_generator import EXPANDED_DATASET_SPECS
from deterministic_conditioning.router import DynamicPromptRouter, RoutingDecision

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_SOURCE = ROOT / "deterministic_conditioning" / "verify_pipeline.py"


def write_pairs(path: Path, pairs: list[dict[str, str]]) -> Path:
    path.write_text("".join(json.dumps(pair) + "\n" for pair in pairs), encoding="utf-8")
    return path


def good_pair(number: int, chosen: str) -> dict[str, str]:
    rejected = " ".join(["filler"] * len(chosen.split()))  # same length, so Gate 1 passes
    return {"scenario_id": str(number), "scenario_name": f"case {number}", "chosen": chosen,
            "rejected": rejected}


GOOD_CHOSEN = [
    "Kill the fork. Restarts leave sockets half open and starve the pooler of every slot until "
    "the kernel finally reaps the orphaned child processes holding them. Done.",
    "Quiet morning so far. Depends entirely on what we build today, from the stubborn pipeline bug "
    "to the messy queries nobody wants to touch. Pick one.",
]
STIFF_CHOSEN = GOOD_CHOSEN[0].replace("Kill the fork.", "Kill the fork. Furthermore,")


def test_router_suite_reports_failure_instead_of_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    real_route = DynamicPromptRouter.route

    def misroute(self: DynamicPromptRouter, prompt: str,
                 history: list[dict[str, str]] | None = None) -> RoutingDecision:
        return real_route(self, "what is raft?", history)

    monkeypatch.setattr(DynamicPromptRouter, "route", misroute)
    assert verify_pipeline.run_router_tests() is False


def test_router_suite_passes_against_the_real_router() -> None:
    assert verify_pipeline.run_router_tests() is True


def test_verifier_contains_no_assert_statements() -> None:
    # `python -O` strips asserts, which would turn every router check into a silent pass.
    tree = ast.parse(PIPELINE_SOURCE.read_text(encoding="utf-8"))
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]


def test_gate_audit_fails_on_a_pair_that_breaks_a_gate(tmp_path: Path) -> None:
    path = write_pairs(tmp_path / "pairs.jsonl", [good_pair(1, GOOD_CHOSEN[1]), good_pair(2, STIFF_CHOSEN)])
    assert verify_pipeline.run_gate_audit(path) is False


def test_gate_audit_passes_a_clean_dataset(tmp_path: Path) -> None:
    path = write_pairs(tmp_path / "pairs.jsonl", [good_pair(i, c) for i, c in enumerate(GOOD_CHOSEN, 1)])
    assert verify_pipeline.run_gate_audit(path) is True


def test_gate_audit_fails_on_an_empty_dataset(tmp_path: Path) -> None:
    assert verify_pipeline.run_gate_audit(write_pairs(tmp_path / "empty.jsonl", [])) is False


def test_default_dataset_is_the_one_the_trainers_consume(capsys: pytest.CaptureFixture[str]) -> None:
    assert verify_pipeline.DATA_FILE.name == "dpo_expanded.jsonl"
    assert verify_pipeline.run_gate_audit(verify_pipeline.DATA_FILE) is True
    out = capsys.readouterr().out
    assert out.count("[PASS] Scenario") == len(EXPANDED_DATASET_SPECS)


def test_script_exits_zero_even_with_asserts_stripped() -> None:
    done = subprocess.run([sys.executable, "-O", "-m", "deterministic_conditioning.verify_pipeline"],
                          cwd=ROOT, capture_output=True, text=True, check=False, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "ALL VERIFICATION SUITES PASSED" in done.stdout
