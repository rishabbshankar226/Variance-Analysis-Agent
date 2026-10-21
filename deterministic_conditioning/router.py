"""Deterministic Input-to-Syntax Router & Context-Window State Inverter.

Extracts observable user prompt features and context history to dynamically
condition token 0 Part of Speech (POS), paragraph cadence, and syntactic structure
under temperature=0 greedy decoding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ObservableSignals:
    """Extracted observable lexical and structural properties from the user prompt."""

    word_count: int
    has_question: bool
    has_exclamation: bool
    has_frustration: bool
    has_all_caps: bool
    has_technical_terms: bool
    raw_prompt: str


@dataclass(frozen=True)
class PriorTurnState:
    """State analysis of the immediately preceding assistant turn (A_{N-1})."""

    exists: bool
    opening_word: str
    opening_pos_type: str  # "verb", "subordinate", "gerund", "fragment", "noun", "other"
    closing_punctuation: str  # "?", ".", "!", or "none"
    used_em_dash: bool
    used_bullet_list: bool
    raw_text: str


@dataclass(frozen=True)
class RoutingDecision:
    """Deterministic routing decision forcing first-token POS and structural archetype."""

    rule_id: str
    rule_name: str
    required_first_token_pos: str
    pos_examples: list[str]
    structural_archetype: str
    inversion_constraints: list[str]
    compiled_system_instruction: str


class DynamicPromptRouter:
    """Infers prompt features, inverts context history, and compiles dynamic conditioning."""

    FRUSTRATION_PATTERN = re.compile(
        r"\b(broken|fail|failed|failing|stuck|wasted|garbage|ridiculous|terrible|hang|crashed|crashing|error|bug|died|freeze|freezing)\b",
        re.IGNORECASE,
    )
    TECHNICAL_PATTERN = re.compile(
        r"\b(postgres|database|connection|pool|latency|vector|schema|concurrency|cluster|consensus|raft|distributed|cache|pipeline|orchestrator|thread|mutex|lock|memory|jwt|csrf|xss|cookie|httponly|session|api|endpoint|token|query)\b",
        re.IGNORECASE,
    )
    ALL_CAPS_PATTERN = re.compile(r"\b[A-Z]{3,}\b")

    SUBORDINATE_WORDS = {"while", "unless", "because", "although", "since", "if", "though", "whereas"}
    GERUND_ENDINGS = ("ing",)

    def extract_signals(self, prompt: str) -> ObservableSignals:
        """Extract deterministic features from user input."""
        words = prompt.strip().split()
        word_count = len(words)
        has_question = "?" in prompt
        has_exclamation = "!" in prompt
        has_frustration = bool(self.FRUSTRATION_PATTERN.search(prompt)) or prompt.count("!") >= 2
        has_all_caps = bool(self.ALL_CAPS_PATTERN.search(prompt))
        has_technical_terms = bool(self.TECHNICAL_PATTERN.search(prompt))

        return ObservableSignals(
            word_count=word_count,
            has_question=has_question,
            has_exclamation=has_exclamation,
            has_frustration=has_frustration or has_all_caps,
            has_all_caps=has_all_caps,
            has_technical_terms=has_technical_terms,
            raw_prompt=prompt,
        )

    def analyze_prior_turn(self, history: list[dict[str, str]]) -> PriorTurnState:
        """Analyze the immediately preceding assistant turn (A_{N-1})."""
        last_assistant_msg = ""
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                last_assistant_msg = msg.get("content", "").strip()
                break

        if not last_assistant_msg:
            return PriorTurnState(
                exists=False,
                opening_word="",
                opening_pos_type="none",
                closing_punctuation="none",
                used_em_dash=False,
                used_bullet_list=False,
                raw_text="",
            )

        words = last_assistant_msg.split()
        opening_word = re.sub(r"[^\w]", "", words[0]).lower() if words else ""

        # Classify opening POS roughly
        if opening_word in self.SUBORDINATE_WORDS:
            pos_type = "subordinate"
        elif opening_word.endswith("ing"):
            pos_type = "gerund"
        elif opening_word in {"check", "kill", "drop", "pull", "skip", "look", "set", "run", "verify"}:
            pos_type = "verb"
        elif opening_word in {"quiet", "depends", "honestly", "fair", "wild"}:
            pos_type = "fragment"
        else:
            pos_type = "noun"

        # Check closing punctuation
        stripped = last_assistant_msg.strip()
        closing_punct = stripped[-1] if stripped and stripped[-1] in {".", "?", "!"} else "."

        used_em_dash = "—" in last_assistant_msg or "--" in last_assistant_msg
        used_bullet_list = bool(re.search(r"\n\s*[-*]\s+", last_assistant_msg))

        return PriorTurnState(
            exists=True,
            opening_word=opening_word,
            opening_pos_type=pos_type,
            closing_punctuation=closing_punct,
            used_em_dash=used_em_dash,
            used_bullet_list=used_bullet_list,
            raw_text=last_assistant_msg,
        )

    def route(
        self, prompt: str, history: list[dict[str, str]] | None = None
    ) -> RoutingDecision:
        """Evaluate observable signals and context history to generate conditioning."""
        history = history or []
        signals = self.extract_signals(prompt)
        prior = self.analyze_prior_turn(history)

        inversion_constraints: list[str] = []
        if prior.exists:
            # Opener inversion
            if prior.opening_pos_type in {"verb", "imperative"}:
                inversion_constraints.append("FORBID opener: Active Verb. MUST use Subordinate Conjunction, Noun, or Preposition.")
            elif prior.opening_pos_type == "subordinate":
                inversion_constraints.append("FORBID opener: Subordinate Conjunction. MUST use Active Verb or Concrete Noun.")
            elif prior.opening_pos_type == "gerund":
                inversion_constraints.append("FORBID opener: Gerund/Participle. MUST use Active Verb, Noun, or Subordinate Clause.")

            # Terminal punctuation inversion
            if prior.closing_punctuation == "?":
                inversion_constraints.append("TERMINAL CADENCE: Must terminate with a declarative period (.). Never ask a consecutive closing question.")
            elif prior.closing_punctuation == ".":
                inversion_constraints.append("TERMINAL CADENCE: Invert declarative closure; conclude with open inquiry (?), elliptical check, or forward observation.")

            # Mid-sentence formatting inversion
            if prior.used_em_dash:
                inversion_constraints.append("PUNCTUATION: Forbid em-dashes (—). Substitute parentheticals or semicolons.")
            if prior.used_bullet_list:
                inversion_constraints.append("STRUCTURE: Forbid bullet points or numbered lists; use strictly flowing prose.")

        # Determine Primary Rule R1 - R5
        if signals.has_frustration:
            rule_id = "R1"
            rule_name = "Frustration / Friction Intervention"
            required_pos = "Imperative / Active Verb"
            pos_examples = ["Check", "Kill", "Drop", "Pull", "Look", "Verify"]
            structure = "Sentence 1: Direct action command (3-6 words). Sentence 2: Diagnostic explanation of mechanism (18-28 words). Sentence 3: Concrete mitigation step."
        elif signals.word_count < 10 and not signals.has_question and not signals.has_technical_terms:
            rule_id = "R2"
            rule_name = "Terse / Casual Opener"
            required_pos = "Adverbial Pivot / Conversational Fragment"
            pos_examples = ["Quiet...", "Depends...", "Honestly...", "Fair...", "Wild..."]
            structure = "Sentence 1: Observational fragment (2-5 words). Sentence 2: Compound clause exploring two paths (18-26 words). Sentence 3: Grounded redirect question (4-7 words)."
        elif signals.word_count < 15 and signals.has_question:
            rule_id = "R3"
            rule_name = "Direct Interrogative / Technical Ingestion"
            required_pos = "Predicate / Concrete Noun / Direct Action"
            pos_examples = ["Picture", "Latency", "Skip", "Memory", "Trading"]
            structure = "Sentence 1: Direct core answer without preamble (4-7 words). Sentence 2: Mechanical illustration or analogy (18-28 words). Sentence 3: Boundary condition."
        elif signals.word_count > 30 and signals.has_technical_terms:
            rule_id = "R4"
            rule_name = "Analytical / Architecture Query"
            required_pos = "Subordinate Conjunction"
            pos_examples = ["While", "Unless", "Because", "Although"]
            structure = "Sentence 1: Subordinate clause framing trade-offs (18-28 words). Sentence 2: Punchy thesis statement (4-6 words). Sentences 3+: Technical breakdown."
        else:
            rule_id = "R5"
            rule_name = "Default Conversational Framing"
            required_pos = "Preposition / Gerund / Framing Clause"
            pos_examples = ["Between", "Under", "Running", "Taking", "Trading"]
            structure = "Sentence 1: Contextual framing clause (12-16 words). Sentence 2: Short verification (3-5 words). Sentence 3: Elaborative commentary."

        # Compile dynamic system instruction
        inversion_block = "\n".join(f"- {c}" for c in inversion_constraints) if inversion_constraints else "- None (Initial turn; establish base cadence)."
        examples_str = ", ".join(f'"{ex}"' for ex in pos_examples)

        compiled_prompt = f"""[DETERMINISTIC INFERENCE ROUTER ACTIVE | TEMP=0.0]
TRIGGERED RULE: {rule_id} ({rule_name})
REQUIRED FIRST-TOKEN POS: {required_pos} (Allowed examples: {examples_str})
REQUIRED PARAGRAPH STRUCTURE: {structure}

LAST-ASSISTANT-TURN INVERSION DIRECTIVES:
{inversion_block}

BURSTINESS & REGISTER CONTRACT:
- Alternate short punchy clauses (3-6 words) with long compound sentences (18-28 words).
- Contractions mandatory (it's, you'd, there's, don't).
- ZERO stock affirmations ('Certainly', 'Great question', 'Sure thing').
- ZERO meta-announcements ('Here is a breakdown', 'Let's dive in').
- ZERO summary closers ('In summary', 'Overall', 'Hope this helps').
"""

        return RoutingDecision(
            rule_id=rule_id,
            rule_name=rule_name,
            required_first_token_pos=required_pos,
            pos_examples=pos_examples,
            structural_archetype=structure,
            inversion_constraints=inversion_constraints,
            compiled_system_instruction=compiled_prompt,
        )
