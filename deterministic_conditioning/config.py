"""Deterministic decoding configuration and logit modifier specifications.

Preserves 100% deterministic reproducibility (identical input -> identical output)
while eliminating greedy argmax loops and degenerate token basins.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DeterministicDecodingConfig:
    """Exact logit modifier parameters for deterministic greedy decoding.

    Attributes:
        temperature: Set strictly to 0.0 for pure greedy argmax selection.
        repetition_penalty: Multiplicative logit penalty (Keskar et al.) applied to
            previously generated tokens in the output buffer. Recommended: 1.10.
        frequency_penalty: Additive linear penalty proportional to token count.
            Recommended: 0.20.
        presence_penalty: Additive one-off penalty if token count >= 1.
            Recommended: 0.15.
        no_repeat_ngram_size: Hard logit masking (-inf) for completing an identical
            n-gram already emitted in the current output. Recommended: 4.
    """

    temperature: float = 0.0
    repetition_penalty: float = 1.10
    frequency_penalty: float = 0.20
    presence_penalty: float = 0.15
    no_repeat_ngram_size: int = 4

    def to_huggingface_dict(self) -> dict[str, object]:
        """Convert to Hugging Face transformers GenerationConfig parameter dictionary."""
        return {
            "do_sample": False,
            "temperature": None,  # Bypassed when do_sample=False
            "repetition_penalty": self.repetition_penalty,
            "no_repeat_ngram_size": self.no_repeat_ngram_size,
        }

    def to_vllm_dict(self) -> dict[str, object]:
        """Convert to vLLM SamplingParams parameter dictionary."""
        return {
            "temperature": 0.0,
            "repetition_penalty": self.repetition_penalty,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
        }

    def to_dict(self) -> dict[str, object]:
        """Export as standard dictionary."""
        return asdict(self)
