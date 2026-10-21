# Deterministic LLM Conditioning & Post-Training Package

A production conditioning and Direct Preference Optimization (DPO) alignment package that makes a deterministic LLM (running strictly at `temperature = 0.0` / greedy argmax decoding) converse with the natural rhythm, syntactic variety, and human warmth of a non-deterministic model.

---

## 1. Architectural Principles

Under greedy argmax decoding (`temperature = 0.0`), autoregressive decoders reliably fall into **mode-collapse basins**:
- **Greedy Attractors**: Generic affirmations (*"Certainly!"*, *"Great question!"*), meta-announcements (*"Here is a breakdown:"*), and formulaic summaries (*"In summary,"*).
- **Syntactic Monotony**: Every sentence follows a uniform subject-verb-object cadence (~12–15 words per sentence, low standard deviation).
- **Repetitive Looping**: Identical openers and closures across consecutive conversation turns.

This package solves this deterministically without stochastic sampling through **three pillars**:
1. **First-Token POS Routing**: Token 0 ($t_0$) dictates the autoregressive trajectory. Observable features from the user prompt (word count, exclamation, frustration words, technical vocabulary) force distinct opening Parts of Speech (Imperative verbs, conversational fragments, concrete nouns, subordinate clauses).
2. **Context-Window State Inversion**: Inspects the immediate preceding assistant turn ($A_{N-1}$) in the context history and inverts its opening POS, terminal punctuation cadence (`?` vs `.`), and mid-sentence punctuation (em-dashes).
3. **Automated 5-Gate DPO Curation**: Synthetic alignment data is filtered through 5 strict gates enforcing length symmetry ($\le 15\%$), zero banned attractors, sentence burstiness ($\sigma \ge 6.0$), and batch Shannon entropy.

```
                          USER PROMPT + CONTEXT HISTORY
                                        │
                                        ▼
                    ┌───────────────────────────────────────┐
                    │       DynamicPromptRouter             │
                    │  • Observable Signal Extractor        │
                    │  • History State Inverter (A_{N-1})   │
                    │  • Token 0 POS Selection (R1–R5)      │
                    └───────────────────┬───────────────────┘
                                        │ Compiled Dynamic Instructions
                                        ▼
                    ┌───────────────────────────────────────┐
                    │     DeterministicLogitsProcessor      │
                    │  • temperature = 0.0 (Argmax)         │
                    │  • repetition_penalty = 1.10          │
                    │  • frequency_penalty  = 0.20          │
                    │  • presence_penalty   = 0.15          │
                    │  • no_repeat_ngram    = 4             │
                    └───────────────────┬───────────────────┘
                                        │ Token Stream
                                        ▼
                    ┌───────────────────────────────────────┐
                    │    HIGH-BURSTINESS NATURAL DIALOGUE   │
                    │ (0% Attractors, 100% Deterministic)   │
                    └───────────────────────────────────────┘
```

---

## 2. Deterministic Routing & Inversion Rules

### Input-to-Syntax Router Matrix

| Rule | Trigger Conditions | Required Token-0 POS | Cadence Archetype |
|---|---|---|---|
| **R1** | Frustration / Friction (`!`, all-caps, "broken", "failed", "garbage") | **Imperative / Active Verb** (*Check*, *Pull*, *Drop*, *Kill*) | Sentence 1: Action command (3–6w). Sentence 2: Diagnostic mechanism (18–28w). Sentence 3: Concrete mitigation. |
| **R2** | Terse / Casual Opener (<10w, non-technical, no `?`) | **Adverbial Pivot / Fragment** (*Quiet...*, *Depends...*, *Honestly...*) | Sentence 1: Observational fragment (2–5w). Sentence 2: Compound trade-off clause (18–26w). Sentence 3: Redirect question. |
| **R3** | Direct Interrogative (<15w, contains `?`) | **Concrete Noun / Direct Action** (*Picture*, *Latency*, *Skip*) | Sentence 1: Core answer without preamble (4–7w). Sentence 2: Mechanical analogy (18–28w). Sentence 3: Boundary check. |
| **R4** | Analytical Architecture (>30w, technical keywords) | **Subordinate Conjunction** (*While*, *Unless*, *Because*, *Although*) | Sentence 1: Trade-off clause (18–28w). Sentence 2: Punchy thesis (4–6w). Sentences 3+: Technical breakdown. |
| **R5** | Default / General Statement (Catch-all) | **Preposition / Gerund** (*Between*, *Under*, *Running*, *Trading*) | Sentence 1: Context framing (12–16w). Sentence 2: Short verification (3–5w). Sentence 3: Elaborative commentary. |

### Context State Inversion ($A_{N-1}$)
- **Opening POS Inversion**: If $A_{N-1}$ opened with a Verb, $A_N$ is forbidden from starting with a Verb (must use Noun, Conjunction, or Preposition).
- **Terminal Cadence Inversion**: If $A_{N-1}$ ended in `?`, $A_N$ must end in a definitive period (`.`). If $A_{N-1}$ ended in `.`, $A_N$ inverts to an open inquiry or forward check.
- **Punctuation Inversion**: If $A_{N-1}$ used em-dashes (`—`), $A_N$ is forbidden from using em-dashes (substitutes parentheticals or semicolons).

---

## 3. Automated SFT/DPO Curation Gates

Every candidate synthetic sample must pass all 5 gates before being accepted into the training set:

1. **Gate 1: Length-Ratio Symmetry Gate**:
   $$\Delta L = \frac{|L_{\text{chosen}} - L_{\text{rejected}}|}{\max(L_{\text{chosen}}, L_{\text{rejected}})} \le 0.15$$
   Prevents DPO loss from optimizing for length bias rather than syntactic naturalness.
2. **Gate 2: Greedy Attractor Regex Audit**:
   Zero tolerance (0 matches) for stock affirmations (*"Certainly!"*), meta-announcements (*"Here is a breakdown:"*), stiff transitions (*"Furthermore,"*), and summary closers (*"In summary,"*).
3. **Gate 3: Sentence Burstiness Score ($\sigma_{\text{lens}}$)**:
   $$\sigma_{\text{lens}} = \sqrt{\frac{1}{N-1}\sum_{k=1}^N (l_k - \bar{l})^2} \ge 6.0 \text{ words}$$
4. **Gate 4: First-Bigram Shannon Entropy Gate**:
   $$H(B_1) = -\sum_{b \in B_1} P(b) \log_2 P(b) \ge 4.5 \text{ bits}$$
   Guarantees lexical diversity across opening bigrams across batches.
5. **Gate 5: Structural Formatting Ratio**:
   $\le 5\%$ bullet lists overall; strictly $0.0\%$ in casual, emotional, or advisory dialogues.

---

## 4. Benchmark Results

Measured across verified test corpora ([`BENCHMARK_REPORT.md`](file:///Users/rishabbshankar/Desktop/projects/Automated%20Variance%20Analysis/Variance%20Analysis%20Agent/deterministic_conditioning/BENCHMARK_REPORT.md)):

| Metric | Unconditioned Baseline (`temp=0.0`) | Conditioned Pipeline (`temp=0.0`) | Relative Delta |
|---|:---:|:---:|:---:|
| **Burstiness Score ($\sigma_{\text{lens}}$)** | 6.53 words | **10.05 words** | **+53.9%** |
| **Short Punchy Clauses (3–6w)** | 5.7% | **40.0%** | **+34.3%** |
| **Compound Observations (18–28w)** | 22.9% | **43.3%** | **+20.4%** |
| **Type-Token Ratio (TTR)** | 0.6441 | **0.7483** | **+16.2%** |
| **Distinct-2 Bigram Ratio** | 0.9618 | **0.9908** | **+3.0%** |
| **Greedy Attractors Detected** | 2 violations | **0 violations** | **-100% (Clean)** |

---

## 5. CLI & Execution Commands

```bash
# 1. Interactive terminal chat with live router & state inversion traces
uv run python -m deterministic_conditioning.chat_cli

# 2. Automated multi-turn demo showing state inversion
uv run python -m deterministic_conditioning.chat_cli --demo

# 3. 5-Gate Curation Audit Suite
uv run python -m deterministic_conditioning.verify_pipeline

# 4. Regenerate and filter synthetic DPO dataset
uv run python -m deterministic_conditioning.dataset_generator

# 5. Hugging Face TRL DPO training pre-flight dry run
uv run python -m deterministic_conditioning.train_dpo_hf --dry-run

# 6. Quantitative benchmark evaluation
uv run python -m deterministic_conditioning.benchmark

# 7. Run full unit and integration test suite
uv run pytest tests/test_deterministic_conditioning.py
```
