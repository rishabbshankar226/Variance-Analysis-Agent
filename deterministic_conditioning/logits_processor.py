"""Standalone deterministic logits processor and greedy decoder emulator.

Applies mathematical logit transformations (repetition penalty, frequency penalty,
presence penalty, and n-gram masking) prior to greedy argmax token selection.
Guarantees 100% deterministic reproducibility without stochastic sampling.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from deterministic_conditioning.config import DeterministicDecodingConfig


@dataclass(frozen=True)
class LogitStepTrace:
    """Diagnostic trace of an individual token decoding step."""

    step: int
    selected_token: int
    raw_argmax_token: int
    was_modified: bool
    top_logits_before: list[tuple[int, float]]
    top_logits_after: list[tuple[int, float]]


class DeterministicLogitsProcessor:
    """Applies deterministic penalties and n-gram constraints to raw logit distributions."""

    def __init__(self, config: DeterministicDecodingConfig | None = None) -> None:
        self.config = config or DeterministicDecodingConfig()

    def process(
        self,
        logits: list[float],
        generated_tokens: Sequence[int],
    ) -> list[float]:
        """Apply repetition, frequency, presence, and no-repeat-ngram modifiers to logits."""
        modified = list(logits)
        vocab_size = len(logits)
        token_counts = Counter(generated_tokens)

        # 1. Multiplicative Repetition Penalty (Keskar et al.)
        if self.config.repetition_penalty != 1.0 and generated_tokens:
            p = self.config.repetition_penalty
            for token_id in set(generated_tokens):
                if 0 <= token_id < vocab_size:
                    val = modified[token_id]
                    modified[token_id] = val / p if val > 0 else val * p

        # 2. Additive Frequency and Presence Penalties
        freq_p = self.config.frequency_penalty
        pres_p = self.config.presence_penalty
        if freq_p > 0.0 or pres_p > 0.0:
            for token_id, count in token_counts.items():
                if 0 <= token_id < vocab_size:
                    penalty = (count * freq_p) + (pres_p if count >= 1 else 0.0)
                    modified[token_id] -= penalty

        # 3. Hard No-Repeat N-Gram Masking
        n = self.config.no_repeat_ngram_size
        if n > 1 and len(generated_tokens) >= n - 1:
            prefix = tuple(generated_tokens[-(n - 1) :])
            # Scan history for instances of prefix
            for i in range(len(generated_tokens) - n + 1):
                ngram = tuple(generated_tokens[i : i + n])
                if ngram[:-1] == prefix:
                    banned_next_token = ngram[-1]
                    if 0 <= banned_next_token < vocab_size:
                        modified[banned_next_token] = -math.inf

        return modified

    def select_argmax(self, logits: Sequence[float]) -> int:
        """Select token with maximum logit value (strict greedy argmax)."""
        max_idx = 0
        max_val = -math.inf
        for idx, val in enumerate(logits):
            if val > max_val:
                max_val = val
                max_idx = idx
        return max_idx

    def decode_step(
        self,
        raw_logits: list[float],
        generated_tokens: Sequence[int],
        step_idx: int = 0,
    ) -> tuple[int, LogitStepTrace]:
        """Process logits and emit next token with diagnostic step trace."""
        raw_best = self.select_argmax(raw_logits)
        modified_logits = self.process(raw_logits, generated_tokens)
        selected = self.select_argmax(modified_logits)

        # Capture top 3 before and after
        top_before = sorted(enumerate(raw_logits), key=lambda x: x[1], reverse=True)[:3]
        top_after = sorted(enumerate(modified_logits), key=lambda x: x[1], reverse=True)[:3]

        trace = LogitStepTrace(
            step=step_idx,
            selected_token=selected,
            raw_argmax_token=raw_best,
            was_modified=(selected != raw_best),
            top_logits_before=top_before,
            top_logits_after=top_after,
        )
        return selected, trace
