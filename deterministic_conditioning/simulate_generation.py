"""Token-Level Autoregressive Simulation of Greedy Decoding vs. Deterministic Penalties.

Provides a mathematical demonstration of how unpenalized argmax search falls into
cyclic attractor basins, and how DeterministicLogitsProcessor breaks the cycle
strictly deterministically (zero stochastic sampling).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from deterministic_conditioning.config import DeterministicDecodingConfig
from deterministic_conditioning.logits_processor import DeterministicLogitsProcessor, LogitStepTrace


@dataclass(frozen=True)
class SimulationOutcome:
    """Outcome of an autoregressive decoding simulation."""

    tokens: list[int]
    decoded_words: list[str]
    has_cyclic_loop: bool
    step_traces: list[LogitStepTrace]


class ToyLanguageModel:
    """A simulated next-token transition matrix modeling a conversational greedy attractor."""

    def __init__(self) -> None:
        self.vocab = [
            "<pad>",      # 0
            "I",          # 1
            "would",      # 2
            "be",         # 3
            "happy",      # 4
            "to",         # 5
            "help",       # 6
            "with",       # 7
            "that.",      # 8
            "Let's",      # 9
            "inspect",    # 10
            "the",        # 11
            "underlying", # 12
            "failure",    # 13
            "trace.",     # 14
        ]
        self.word_to_id = {w: i for i, w in enumerate(self.vocab)}

    def get_raw_logits(self, context: Sequence[int]) -> list[float]:
        """Compute synthetic next-token logit distribution given token history."""
        logits = [0.0] * len(self.vocab)

        if not context:
            # Opener bias: "I" (1) has highest logit
            logits[self.word_to_id["I"]] = 10.0
            logits[self.word_to_id["Let's"]] = 8.5
            return logits

        last_token = context[-1]
        last_word = self.vocab[last_token] if 0 <= last_token < len(self.vocab) else ""

        # Default transition dynamics modeling stock affirmation loop:
        # "I" -> "would" -> "be" -> "happy" -> "to" -> "help" -> "with" -> "that." -> "I" ...
        transitions: dict[str, list[tuple[str, float]]] = {
            "I": [("would", 12.0), ("inspect", 4.0)],
            "would": [("be", 12.0), ("inspect", 3.0)],
            "be": [("happy", 12.0), ("the", 3.0)],
            "happy": [("to", 12.0), ("with", 2.0)],
            "to": [("help", 12.0), ("inspect", 4.0)],
            "help": [("with", 12.0), ("the", 5.0)],
            "with": [("that.", 12.0), ("the", 3.0)],
            "that.": [("I", 11.0), ("Let's", 9.0)],  # Loop attractor: loops back to "I" with higher score than "Let's"
            "Let's": [("inspect", 12.0), ("be", 2.0)],
            "inspect": [("the", 12.0), ("that.", 2.0)],
            "the": [("underlying", 12.0), ("failure", 8.0)],
            "underlying": [("failure", 12.0), ("trace.", 4.0)],
            "failure": [("trace.", 12.0), ("with", 2.0)],
            "trace.": [("that.", 5.0), ("<pad>", 10.0)],
        }

        if last_word in transitions:
            for word, score in transitions[last_word]:
                logits[self.word_to_id[word]] = score
        else:
            logits[self.word_to_id["<pad>"]] = 10.0

        return logits


class DeterministicTextGenerator:
    """Generates text from a language model using DeterministicLogitsProcessor."""

    def __init__(self, model: ToyLanguageModel, config: DeterministicDecodingConfig) -> None:
        self.model = model
        self.processor = DeterministicLogitsProcessor(config)

    def generate(self, max_tokens: int = 18) -> SimulationOutcome:
        """Autoregressively generate tokens until max_tokens or terminal token."""
        tokens: list[int] = []
        traces: list[LogitStepTrace] = []

        for step in range(max_tokens):
            raw_logits = self.model.get_raw_logits(tokens)
            token, trace = self.processor.decode_step(raw_logits, tokens, step_idx=step)
            tokens.append(token)
            traces.append(trace)

            # Break if pad
            if token == 0:
                break

        words = [self.model.vocab[t] for t in tokens]
        # Detect cyclic loop (e.g. repeated bigram or trigram sequences)
        has_loop = self._detect_cycle(tokens)

        return SimulationOutcome(
            tokens=tokens,
            decoded_words=words,
            has_cyclic_loop=has_loop,
            step_traces=traces,
        )

    @staticmethod
    def _detect_cycle(tokens: list[int], max_ngram: int = 8) -> bool:
        """Detect any repeated sequence of tokens of length between 3 and max_ngram."""
        for n in range(3, min(max_ngram + 1, len(tokens) // 2 + 1)):
            for i in range(len(tokens) - 2 * n + 1):
                if tokens[i : i + n] == tokens[i + n : i + 2 * n]:
                    return True
        return False


def run_simulation_comparison() -> None:
    """Compare pure greedy argmax vs. penalized deterministic decoding."""
    model = ToyLanguageModel()

    print("=================================================================")
    print("   AUTOREGRESSIVE GREEDY DECODING LOOP SIMULATION (TEMP = 0.0)   ")
    print("=================================================================")

    # 1. Baseline: Pure greedy argmax (penalties = 1.0 / 0.0)
    baseline_cfg = DeterministicDecodingConfig(
        repetition_penalty=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
        no_repeat_ngram_size=0,
    )
    gen_baseline = DeterministicTextGenerator(model, baseline_cfg)
    out_baseline = gen_baseline.generate(max_tokens=18)

    print("\n[1. UNPENALIZED GREEDY BASELINE]")
    print(f"Decoded Output : {' '.join(out_baseline.decoded_words)}")
    print(f"Cyclic Loop?   : {'YES (TRAPPED IN BASIN)' if out_baseline.has_cyclic_loop else 'NO'}")

    # 2. Conditioned: DeterministicLogitsProcessor active
    conditioned_cfg = DeterministicDecodingConfig(
        repetition_penalty=1.15,
        frequency_penalty=0.20,
        presence_penalty=0.15,
        no_repeat_ngram_size=4,
    )
    gen_conditioned = DeterministicTextGenerator(model, conditioned_cfg)
    out_conditioned = gen_conditioned.generate(max_tokens=18)

    print("\n[2. DETERMINISTIC PENALIZED PIPELINE]")
    print(f"Decoded Output : {' '.join(out_conditioned.decoded_words)}")
    print(f"Cyclic Loop?   : {'YES (TRAPPED)' if out_conditioned.has_cyclic_loop else 'NO (SUCCESSFULLY ESCAPED)'}")

    # 3. Step-by-Step Diagnostic Escape Trace
    print("\n[3. LOGIT STEP TRACE AT DECISION FORK]")
    for trace in out_conditioned.step_traces:
        if trace.was_modified:
            word_raw = model.vocab[trace.raw_argmax_token]
            word_sel = model.vocab[trace.selected_token]
            print(
                f"  Step {trace.step}: Raw greedy token '{word_raw}' (logit {trace.top_logits_before[0][1]:.1f}) "
                f"was penalized -> Deterministically routed to '{word_sel}' (logit {trace.top_logits_after[0][1]:.1f})"
            )
    print("=================================================================\n")


if __name__ == "__main__":
    run_simulation_comparison()
