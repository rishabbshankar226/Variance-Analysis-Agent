"""Per-pattern tests for the SFT/DPO curation gates.

Gate 2 used `\\b(Furthermore,|...|Hello!)\\b`. A word boundary after `,` or `!` needs a word
character next, so every phrase that ends in punctuation could never match and the gate waved
through text it was written to reject.
"""

from __future__ import annotations

import pytest

from deterministic_conditioning.curation_gates import CurationGates

# Every alternative of every BANNED_ATTRACTORS pattern, spelled the way the gate documents it.
STOCK_AFFIRMATIONS = ["Certainly", "Great question", "I'd be happy to", "Sure thing", "Of course",
                      "Hello!", "Good day"]
META_ANNOUNCEMENTS = ["Here is a breakdown", "Here is what you need to know", "Let's dive in",
                      "Below are the steps", "Here is how to think about this"]
STIFF_TRANSITIONS = ["Furthermore,", "Moreover,", "Additionally,", "In addition,", "Consequently,",
                     "Therefore,", "To begin with,"]
SUMMARY_CLOSERS = ["In summary,", "In conclusion,", "Overall,", "Hope this helps!",
                   "Let me know if you have any questions", "Feel free to ask"]
ALL_PHRASES = STOCK_AFFIRMATIONS + META_ANNOUNCEMENTS + STIFF_TRANSITIONS + SUMMARY_CLOSERS


@pytest.fixture
def gates() -> CurationGates:
    return CurationGates()


@pytest.mark.parametrize("phrase", ALL_PHRASES)
def test_gate_2_rejects_every_listed_phrase_mid_text(gates: CurationGates, phrase: str) -> None:
    text = f"Kill the stuck fork first. {phrase} the pooler keeps ten idle sockets open."
    result = gates.check_gate_2_attractor_audit(text)
    assert result.passed is False, phrase
    assert phrase.lower() in result.details.lower()


@pytest.mark.parametrize("phrase", ALL_PHRASES)
def test_gate_2_rejects_every_listed_phrase_at_the_start_in_any_case(
    gates: CurationGates, phrase: str
) -> None:
    result = gates.check_gate_2_attractor_audit(f"{phrase.upper()} the pooler keeps ten idle sockets open.")
    assert result.passed is False, phrase


@pytest.mark.parametrize("text", [
    "Check the logs immediately. Sockets are hanging.",
    "Overallocation of sockets is the usual cause.",  # `Overall` only counts when followed by a comma
    "Sure thingamajig, but the pooler is fine.",
    "Certainlyville is a place, not an opener.",
    "Therefore the pooler is fine.",  # the documented phrase is `Therefore,`
    "Print Hello World! from the sample program.",  # only the bare `Hello!` opener is banned
])
def test_gate_2_does_not_flag_clean_or_lookalike_text(gates: CurationGates, text: str) -> None:
    result = gates.check_gate_2_attractor_audit(text)
    assert result.passed is True, result.details


def test_gate_2_reports_every_occurrence_not_just_the_first_per_pattern(gates: CurationGates) -> None:
    result = gates.check_gate_2_attractor_audit("Certainly. Of course. Sure thing.")
    assert result.metric_value == "3 violations"


@pytest.mark.parametrize("text", [
    "Intro line.\n- **Latency:** slow",
    "- **Latency:** slow\nrest",  # the template can open the text
    "Intro line.\n  * **Cost:** high",
])
def test_gate_2_rejects_the_bold_bullet_template(gates: CurationGates, text: str) -> None:
    assert gates.check_gate_2_attractor_audit(text).passed is False


def test_validate_pair_fails_on_a_punctuation_terminated_attractor(gates: CurationGates) -> None:
    chosen = "Kill it. Furthermore, restarts leave sockets half open and starve the pooler of slots. Done."
    rejected = "Kill it. Restarts leave sockets half open and starve the pooler of slots. Done too."
    report = gates.validate_pair("scenario", chosen, rejected)
    assert report.all_passed is False
    assert [r.gate_name for r in report.results if not r.passed] == ["Gate 2: Greedy Attractor Audit"]


@pytest.mark.parametrize("text", ["- only point", "1. only step", "* only point", "  - indented only point"])
def test_gate_5_catches_a_list_that_opens_the_text(gates: CurationGates, text: str) -> None:
    assert gates.check_gate_5_bullet_density(text, is_casual_or_emotional=True).passed is False


@pytest.mark.parametrize("text", [
    "Revenue grew 3.5 percent. Margins held.",
    "Costs rose *sharply* in June.",
    "Wrote -5 and 2. in passing, mid-sentence.",
])
def test_gate_5_ignores_prose_that_only_looks_like_a_marker(gates: CurationGates, text: str) -> None:
    assert gates.check_gate_5_bullet_density(text, is_casual_or_emotional=True).passed is True


def test_gate_5_allows_bullets_outside_the_conversational_register(gates: CurationGates) -> None:
    assert gates.check_gate_5_bullet_density("- a\n- b", is_casual_or_emotional=False).passed is True


def test_gate_4_cannot_pass_on_a_single_sample(gates: CurationGates) -> None:
    result = gates.check_gate_4_dataset_entropy(["Quiet morning so far. Depends on the stack."])
    assert result.passed is False
    assert "at least 2" in result.details


def test_gate_4_cannot_pass_on_an_empty_batch(gates: CurationGates) -> None:
    assert gates.check_gate_4_dataset_entropy([]).passed is False


def test_gate_4_rejects_a_batch_that_always_opens_the_same_way(gates: CurationGates) -> None:
    result = gates.check_gate_4_dataset_entropy(["Quiet morning so far."] * 4)
    assert result.passed is False
    assert result.metric_value == 0.0
    assert not str(result.metric_value).startswith("-")


def test_gate_4_accepts_distinct_openings_and_scales_the_threshold_to_the_batch(
    gates: CurationGates,
) -> None:
    result = gates.check_gate_4_dataset_entropy(["Quiet morning so far.", "Kill the fork now."])
    assert result.passed is True
    assert "batch size 2" in str(result.threshold)


def test_gate_4_large_diverse_batch_is_held_to_the_two_bit_floor(gates: CurationGates) -> None:
    openers = [f"Opener{i} variety {i}." for i in range(40)]
    assert gates.check_gate_4_dataset_entropy(openers).passed is True
    two_openers = ["Quiet morning so far."] * 20 + ["Kill the fork now."] * 20
    result = gates.check_gate_4_dataset_entropy(two_openers, min_entropy_bits=2.0)
    assert result.passed is False  # 1 bit of entropy against a 2.0 bit floor
