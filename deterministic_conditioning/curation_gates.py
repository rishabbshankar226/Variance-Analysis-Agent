"""Automated SFT and DPO Dataset Filtering Gates.

Implements binary pass/fail validation gates for synthetic training data to eliminate
greedy attractors, enforce syntactic burstiness, and prevent length bias in DPO pairs.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    """Outcome of an individual validation gate."""

    gate_name: str
    passed: bool
    metric_value: float | str
    threshold: float | str
    details: str


@dataclass(frozen=True)
class PairValidationReport:
    """Consolidated gate results for a single contrastive DPO pair."""

    scenario: str
    all_passed: bool
    results: list[GateResult]


class CurationGates:
    """Binary pass/fail validation gates for synthetic SFT and DPO datasets."""

    # A trailing ``\b`` after ``,`` or ``!`` needs a word character next, so phrases that end in
    # punctuation are matched with the punctuation inside the pattern and no boundary after it.
    BANNED_ATTRACTORS = [
        re.compile(r"\b(?:Certainly|Great question|I'd be happy to|Sure thing|Of course|Good day)\b|\bHello!", re.IGNORECASE),
        re.compile(r"\b(?:Here is a breakdown|Here is what you need to know|Let's dive in|Below are the steps|Here is how to think about this)\b", re.IGNORECASE),
        re.compile(r"\b(?:Furthermore|Moreover|Additionally|In addition|Consequently|Therefore|To begin with),", re.IGNORECASE),
        re.compile(r"\b(?:In summary|In conclusion|Overall),|\b(?:Let me know if you have any questions|Feel free to ask)\b|\bHope this helps!", re.IGNORECASE),
        re.compile(r"^[ \t]*[-*]\s*\*\*[^*]+:\*\*", re.MULTILINE),  # Symmetrical bold bullet template
    ]

    SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
    BULLET_PATTERN = re.compile(r"^[ \t]*(?:[-*]|\d+\.)\s+", re.MULTILINE)

    @staticmethod
    def _tokenize_words(text: str) -> list[str]:
        return text.strip().split()

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        raw_sentences = CurationGates.SENTENCE_SPLIT_PATTERN.split(text.strip())
        return [s.strip() for s in raw_sentences if s.strip()]

    def check_gate_1_length_symmetry(self, chosen: str, rejected: str, max_delta: float = 0.15) -> GateResult:
        """Gate 1: Length-Ratio Symmetry Gate (|L_c - L_r| / max(L_c, L_r) <= 0.15)."""
        words_c = len(self._tokenize_words(chosen))
        words_r = len(self._tokenize_words(rejected))
        max_len = max(words_c, words_r)
        if max_len == 0:
            delta = 0.0
        else:
            delta = abs(words_c - words_r) / max_len

        passed = delta <= max_delta
        return GateResult(
            gate_name="Gate 1: Length-Ratio Symmetry",
            passed=passed,
            metric_value=round(delta, 4),
            threshold=f"<= {max_delta}",
            details=f"Chosen: {words_c} words, Rejected: {words_r} words, Delta: {delta:.2%}",
        )

    def check_gate_2_attractor_audit(self, chosen: str) -> GateResult:
        """Gate 2: Greedy Attractor Regex Audit (zero tolerance)."""
        violations = [match.group(0).strip() for pattern in self.BANNED_ATTRACTORS
                      for match in pattern.finditer(chosen)]

        passed = len(violations) == 0
        return GateResult(
            gate_name="Gate 2: Greedy Attractor Audit",
            passed=passed,
            metric_value=f"{len(violations)} violations",
            threshold="0 violations",
            details="Violations found: " + (", ".join(violations) if violations else "None"),
        )

    def check_gate_3_burstiness(self, chosen: str, min_std_dev: float = 6.0) -> GateResult:
        """Gate 3: Sentence-Length Standard Deviation (Burstiness Score)."""
        sentences = self._split_sentences(chosen)
        lens = [len(self._tokenize_words(s)) for s in sentences]

        if len(lens) < 2:
            return GateResult(
                gate_name="Gate 3: Burstiness Score",
                passed=False,
                metric_value=0.0,
                threshold=f">= {min_std_dev}",
                details="Insufficient sentences (<2) to evaluate sentence length standard deviation.",
            )

        mean = sum(lens) / len(lens)
        variance = sum((x - mean) ** 2 for x in lens) / (len(lens) - 1)
        std_dev = math.sqrt(variance)

        passed = std_dev >= min_std_dev
        return GateResult(
            gate_name="Gate 3: Burstiness Score",
            passed=passed,
            metric_value=round(std_dev, 2),
            threshold=f">= {min_std_dev}",
            details=f"Sentence counts: {lens}, Mean: {mean:.1f}, StdDev: {std_dev:.2f}",
        )

    def check_gate_5_bullet_density(self, chosen: str, is_casual_or_emotional: bool = True) -> GateResult:
        """Gate 5: Structural Formatting Ratio (0% bullets in conversational/emotional context)."""
        has_bullets = bool(self.BULLET_PATTERN.search(chosen))
        if is_casual_or_emotional:
            passed = not has_bullets
            return GateResult(
                gate_name="Gate 5: Structural Formatting Density",
                passed=passed,
                metric_value="Has bullets" if has_bullets else "No bullets",
                threshold="0 bullets in conversational register",
                details="Bullet lists are forbidden in conversational/peer dialogue.",
            )
        else:
            return GateResult(
                gate_name="Gate 5: Structural Formatting Density",
                passed=True,
                metric_value="Prose evaluated",
                threshold="<= 5% dataset rate",
                details="Acceptable formatting.",
            )

    @classmethod
    def check_gate_4_dataset_entropy(cls, chosen_texts: list[str], min_entropy_bits: float = 2.0) -> GateResult:
        """Gate 4: First-Bigram Shannon Entropy across a dataset batch."""
        bigrams: list[tuple[str, str]] = []
        for text in chosen_texts:
            words = [re.sub(r"[^\w]", "", w).lower() for w in text.strip().split() if w]
            if len(words) >= 2:
                bigrams.append((words[0], words[1]))

        if len(bigrams) < 2:
            # One opening has no diversity to measure; the scaled threshold below would be 0 bits.
            return GateResult(
                gate_name="Gate 4: First-Bigram Entropy",
                passed=False,
                metric_value=0.0,
                threshold=f">= {min_entropy_bits}",
                details=f"Need at least 2 samples with an opening bigram, found {len(bigrams)}.",
            )

        total = len(bigrams)
        counts = Counter(bigrams)
        entropy = max(0.0, -sum((cnt / total) * math.log2(cnt / total) for cnt in counts.values()))

        # For smaller benchmark sets (e.g. 5 samples), max theoretical entropy is log2(5) = 2.32 bits.
        # Scaled threshold handles sample size gracefully.
        effective_threshold = min(min_entropy_bits, math.log2(total) * 0.9)
        passed = entropy >= effective_threshold

        return GateResult(
            gate_name="Gate 4: First-Bigram Entropy",
            passed=passed,
            metric_value=round(entropy, 2),
            threshold=f">= {effective_threshold:.2f} bits (batch size {total})",
            details=f"Distinct opening bigrams: {len(counts)}/{total}, Entropy: {entropy:.2f} bits.",
        )

    def validate_pair(
        self, scenario: str, chosen: str, rejected: str, is_casual_or_emotional: bool = True
    ) -> PairValidationReport:
        """Run all per-pair gates on a single DPO sample."""
        results = [
            self.check_gate_1_length_symmetry(chosen, rejected),
            self.check_gate_2_attractor_audit(chosen),
            self.check_gate_3_burstiness(chosen),
            self.check_gate_5_bullet_density(chosen, is_casual_or_emotional),
        ]
        all_passed = all(r.passed for r in results)
        return PairValidationReport(scenario=scenario, all_passed=all_passed, results=results)
