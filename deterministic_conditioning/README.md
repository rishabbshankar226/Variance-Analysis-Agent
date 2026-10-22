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
   Zero tolerance (0 matches) for stock affirmations (*"Certainly!"*), meta-announcements (*"Here is a breakdown:"*), stiff transitions (*"Furthermore,"*), and summary closers (*"In summary,"*). `CurationGates.BANNED_ATTRACTORS` lists every phrase, and `tests/test_curation_gates.py` checks each one.
3. **Gate 3: Sentence Burstiness Score ($\sigma_{\text{lens}}$)**:
   $$\sigma_{\text{lens}} = \sqrt{\frac{1}{N-1}\sum_{k=1}^N (l_k - \bar{l})^2} \ge 6.0 \text{ words}$$
4. **Gate 4: First-Bigram Shannon Entropy Gate**:
   $$H(B_1) = -\sum_{b \in B_1} P(b) \log_2 P(b) \ge \min(2.0,\ 0.9 \log_2 n) \text{ bits}$$
   Guarantees lexical diversity across the opening bigrams of a batch of $n$ chosen responses. The floor scales down for small batches, and a batch of fewer than two responses cannot pass.
5. **Gate 5: Structural Formatting Ratio**:
   Strictly $0$ list markers (`-`, `*` or `1.` at the start of a line) in a conversational pair, which is the default. Pairs marked non-conversational are not checked, and no dataset-wide bullet budget is enforced.

---

## 4. Benchmark Results

[`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md) is generated by `python -m deterministic_conditioning.benchmark` and is the only copy of the numbers; rerun the command after changing the benchmark, the dataset or the commentary instead of copying figures here. It has two parts:

- A comparison of the hand-written chosen and rejected pairs in the DPO dataset (burstiness, short punchy clauses of 3–6 words, compound observations of 18–28 words, type-token and distinct-2 ratios, attractor count). It scores the dataset, not model output.
- A fact check of what `generate_verified_commentary` actually writes over the example and Chrome QA variance files, counting commentaries with no claim that the analysis result contradicts (`benchmark.commentary_contradictions`).

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

# 7. Local visualizer UI (http://127.0.0.1:8050, loopback only)
uv run python -m deterministic_conditioning.ui --port 8050

# 8. Run the package tests
uv run pytest tests/test_deterministic_conditioning.py tests/test_curation_gates.py \
  tests/test_verify_pipeline.py tests/test_conditioning_benchmark.py \
  tests/test_conditioning_client_adapter.py tests/test_conditioning_ui_server.py \
  tests/test_commentary_truthfulness.py
```

---

## 6. Defaults and Boundaries

- **Offline by default.** `DeterministicChatClient` answers from a rule-adhering simulator. It contacts an OpenAI-compatible server (vLLM, TGI) only when you pass `api_base=` or set `LLM_API_BASE` (an `http(s)` URL), with `LLM_API_KEY` as an optional bearer token. `GenerationResult.backend_used` says `remote (<url>)`, `deterministic-simulator`, or `deterministic-simulator (remote unavailable: <error>)`. The vendor sampling fields (`repetition_penalty`, `no_repeat_ngram_size`) are sent at the top level of the JSON body; that format has not been checked against a live server.
- **Visualizer.** `python -m deterministic_conditioning.ui` binds `127.0.0.1`, serves only the page and `POST /api/route`, rejects malformed input with a JSON error, and makes no requests to other hosts.
- **Datasets.** `data/dpo_expanded.jsonl` (eight pairs) is what `dataset_generator` writes and `verify_pipeline` audits, and what `train_dpo_hf.py`, `train_unsloth_dpo.py` and the Axolotl config read. `data/dpo_pairs.jsonl` is an older five-pair export without `rule_id`; only `trainer.py` still defaults to it.
- **Training scripts are not exercised by CI.** They need torch, TRL, Unsloth and a GPU, none of which are installed in the test environment, so these points are suspected from the code and **unverified**:
  - `train_dpo_hf.py` and `train_unsloth_dpo.py` pass `beta`, `max_length`, `max_prompt_length` (and `max_target_length`) and `tokenizer=` to `DPOTrainer`. As far as the TRL release notes go (checked from memory, not against an installed version), recent TRL reads these through `DPOConfig` and takes the tokenizer as `processing_class=`; `max_target_length` no longer exists. `torch_dtype=` is also deprecated in recent transformers.
  - The prompts carry hand-written Llama-3 special tokens (`<|begin_of_text|>`, a trailing `<|eot_id|>`), which can duplicate the BOS and EOS tokens the tokenizer or trainer adds.
  - `learning_rate=5e-7` is a full-fine-tune value used for LoRA adapters, and `val_set_size: 0.1` of eight pairs leaves at most one evaluation example for `eval_steps: 5` and `early_stopping_patience: 3` in `configs/axolotl_dpo.yaml`.

  Pin library versions and run on a GPU host before relying on them; `--dry-run` only checks data formatting.
