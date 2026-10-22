# Chrome QA & Improvement Loop — Deterministic LLM / Variance Chatbot

You are a senior QA engineer and Python developer. Your job is to (1) prove, through the real browser UI,
whether the deterministic variance chatbot and its conditioning engine work as intended, (2) find and
document every defect with evidence, and (3) fix the highest-value ones test-first on a feature branch,
delivering them as a pull request. Work through the phases in order. Be skeptical: a response that
*looks* fluent but states the wrong number or the wrong direction is a critical defect.

"The deterministic LLM" here means both surfaces:
- **The variance chatbot:** `src/variance_agent/chat/`, with the UI in
  `src/variance_agent/static/` (`chat.html`, `chat.js`, `chat.css`).
- **The conditioning engine:** the `deterministic_conditioning/` package. Its templated commentary
  appears in the memo's "Strategic Takeaway" and in the CLI `--commentary` report, and its router has
  its own browser visualizer.

## Ground rules (non-negotiable)
- **Never push to `main`, and never merge.** `main` auto-deploys to the public Render demo at
  https://variance-analysis-chatbot.onrender.com. Work on `qa/chrome-deterministic-llm-<YYYY-MM-DD>`
  and open a PR.
- **Use Claude in Chrome** (`mcp__claude-in-chrome__*`) for all UI testing.
  - Load these in ONE ToolSearch call: `tabs_context_mcp`, `tabs_create_mcp`, `navigate`, `computer`,
    `read_page`, `find`, `form_input`, `file_upload`, `get_page_text`, `read_console_messages`,
    `read_network_requests`, `gif_creator`, `javascript_tool`, `resize_window`.
  - Work in a new tab, not the user's existing tabs.
- **Use JavaScript only to inspect** (DOM text, console, network). Send every chat message by typing
  in the input or clicking a chip, exactly as a user would.
- **Ground truth comes first.** Never judge a bot answer against numbers the bot produced. Judge it
  against the oracle from Phase 1.
- **Evidence or it didn't happen.** Every confirmed issue needs the exact message sent, the observed
  output (copied text), the expected output, and a screenshot or GIF.
- **Python ≥ 3.11 is required.** Use `.venv/bin/python`, `.venv/bin/pytest` and
  `.venv/bin/variance-agent`; the system Python 3.9 fails.
- **Unset `PORT` and `RENDER` for local runs.** The CLI silently switches to hosted mode (binds
  0.0.0.0, refuses path exports) whenever `RENDER` is set or `PORT` is numeric.
- **Stop and ask the user** if you would need to:
  - push to `main`;
  - change `render.yaml` or deploy settings;
  - delete files you didn't create;
  - make a change that alters public behaviour beyond fixing a defect.

## Phase 0 — Orient (≈10 min, no browser yet)
1. Read these first:
   - `README.md`
   - `deterministic_conditioning/README.md`, including the R1–R5 routing table
   - the help text in `src/variance_agent/chat/handlers.py` (search for the help handler)
   - `src/variance_agent/chat/intent.py`
   - the newest `docs/INSTITUTIONAL_AUDIT_*.md` and `docs/BUG_HUNT_*.md`, so you don't re-report
     fixed issues
2. Record a baseline:
   - `.venv/bin/pytest -q`
   - `.venv/bin/ruff check .`
   - `.venv/bin/mypy --strict src/variance_agent scripts`
3. Create the branch.
4. Start the servers in the background. There is no `--no-browser` flag, and `--chat` picks a random
   port and opens the system browser, so start the local chatbot on a fixed port directly:
   ```bash
   env -u PORT -u RENDER .venv/bin/python -u -c "from variance_agent.chat.server import run_chat_server; run_chat_server(port=8765, open_browser=False)"
   ```
   The chatbot is now at `http://127.0.0.1:8765`; confirm with `curl -s http://127.0.0.1:8765/status`.
   Then start the router visualizer:
   ```bash
   .venv/bin/python -m deterministic_conditioning.ui --port 8050
   ```
5. Build a **capability inventory** from the bot's own claims:
   - every intent in the help text;
   - every chip label in `handlers.py` and `src/variance_agent/static/chat.js`;
   - every knowledge topic in `knowledge.py` / `intent.py`.

   This inventory is your test matrix. Anything the bot advertises must work.

## Phase 1 — Fixtures and an independent oracle
The bot has no built-in data. Create test fixtures under `tests/fixtures/chrome_qa/`; they become
regression inputs later. Use `examples/sample_variance.csv` and `examples/sample_eur.csv`, plus these
new files:

| Fixture | Purpose |
|---|---|
| `fav_net.csv` | Revenue beats and expenses under budget; net clearly **favourable** |
| `unfav_net.csv` | Revenue misses and expenses over budget; net clearly **unfavourable**, margin falls |
| `mixed_sign.csv` | Large favourable revenue line with net still unfavourable (catches "led by X" narratives) |
| `edge_values.csv` | Zero budget, zero revenue, negative actual, negative budget, values with 3–4 decimals |
| `names.csv` | Names like `R&D_Costs`, `Sales & Marketing`, `<b>Bold</b>`, `Café`, duplicate names, an emoji |
| `structure.csv` | Subtotal or "Total" rows, Neutral rows, Unclassified rows (missing Type) |
| `large.csv` | ~5,000 rows (generated) to test table and "no match" output size |

Match the column layout of `examples/sample_variance.csv` and the rules in `docs/input-contract.md`.

Then write a standalone oracle, `scripts/qa_oracle.py` (stdlib `decimal` only, **no imports from
`variance_agent`**). For each fixture it must compute:
- per-line variance (actual − budget), percent (N/A when budget is 0), and favourable/unfavourable
  direction by type (revenue up = favourable, expense up = unfavourable);
- totals for revenue, expenses and net operating impact, plus budget vs actual operating margin;
- the material items under the thresholds you will enter (e.g. `$10k or 5%`, strict `>`), excluding
  subtotals;
- the top 3 by absolute dollars, and the item with the largest favourable and largest unfavourable
  variance.

Save the results to `tests/fixtures/chrome_qa/expected/<fixture>.json` and treat them as the answer
key. If `docs/financial-rules.md` defines a rule differently from your oracle, follow the doc and note
the difference.

## Phase 2 — Browser test matrix (Claude in Chrome, local server)
Use `reset` (or a fresh page load) between fixtures. For each fixture, go through intake exactly:
upload (`file_upload` with the absolute fixture path) → period → thresholds → currency → resolve
unclassified → exploring. Record the transcript.

**A. Intake flow**
- Happy path for each fixture.
- Invalid thresholds (`abc`, `-5%`, `$10k or`, `1.5m`), an unsupported currency (`JPY`), and a period
  that looks like a command (`summary`).
- At the unclassified step: classify one item, then "Skip" on the last item, then "Skip all". Confirm
  the flow always reaches exploring with no loop.
- Upload an invalid file (an empty CSV, a `.txt`, a CSV with no Budget column) and an `.xlsx` with
  two sheets (`sheets`, `sheet <name>`).

**B. Capability matrix.** For every item in the Phase 0 inventory, send:
1. the canonical phrasing;
2. a natural paraphrase ("show me the biggest risks", "is marketing bad?");
3. the same with filler or punctuation ("summary please", "summary.", "Summary?!").

Also click every chip that appears in every response. Pass criteria:
- the bot routes to the right intent;
- every number matches the oracle within the displayed rounding;
- favourable/unfavourable labels match the oracle;
- subtotal rows never appear as line items.

A chip that falls through to "couldn't find…" is a defect.

**C. Conversation memory.** After a table response, try:
- "why?", "explain it", "what about the second one", "#3", "the last one";
- "compare it with payroll";
- a typo ("why marketng");
- an item name embedded in a sentence ("how did subscription revenue do?").

Check that the focus moves to the right item.

**D. Deterministic conditioning engine (deep)**
1. **Truthfulness.** Generate the memo (`memo`, "what should I tell the board") for `fav_net`,
   `unfav_net` and `mixed_sign`. Extract every factual claim in the Strategic Takeaway: direction,
   margin up/down/negative, the item named as the driver, "no unresolved variances", and so on. Check
   each one against the oracle. A claim that contradicts the oracle, or can't be backed by any input
   field, is a **critical** defect.
2. **CLI parity.** Run the CLI on the same fixtures and write the reports to a scratch directory:
   ```bash
   .venv/bin/variance-agent <fixture> --period "Q3 2026" --dollar-threshold 10000 --percent-threshold 5 --commentary -o <scratch>/<fixture>.md
   ```
   Compare its commentary with the memo's takeaway and with the oracle.
3. **Determinism.** Send the identical intake and `memo` sequence twice in one server run (with a
   reset between) and once more after restarting the server. Run the CLI command twice as well. The
   outputs must match byte for byte. Diff them and report any difference.
4. **Router visualizer** (`http://localhost:8050`):
   - enter one input per routing rule R1–R5 (frustrated, terse, direct question, long technical,
     default);
   - check that the displayed route, the opening word class and the penalties match `router.py` and
     `logits_processor.py`;
   - check the console for errors.
5. **Benchmark honesty.** Read `deterministic_conditioning/benchmark.py` and `BENCHMARK_REPORT.md`.
   Note whether the benchmark scores real engine output or hand-written strings. If it scores
   hand-written strings, report that as a gap and propose a benchmark that does score real output.

**E. Numbers and formatting**
- Compare currency symbols and decimal places across summary, tables, memo, what-if, compare,
  waterfall and the commentary.
- `0`-baseline cases must show N/A, not `0.0%`.
- The waterfall must reconcile: the bars sum to the net, including any unclassified rows.
- What-if in both directions: "what if revenue drops 10%", "decrease", "fall", "rises", "increase
  marketing by $5k". Check the sign and magnitude against the oracle.
- Run-rate assumptions for Q1–Q4, H1, FY and an unknown period.

**F. Robustness and security** (local server only — never against Render)
- Input: empty input, whitespace, 5,000 characters, `<script>alert(1)</script>`,
  `<img src=x onerror=alert(1)>`, Markdown injection (`**bold**`, `| a | b |`), unicode/RTL, emoji.
- Two messages sent in quick succession.
- With `curl` against `127.0.0.1:8765`, send raw POSTs to `/message`: a non-JSON body, a JSON array, a
  missing `text`, a `Content-Length` larger than the body. Then a malformed multipart `/upload`. Then
  `GET /download/../etc/passwd`. The server must answer every one with a clean 4xx and stay up; check
  `/status` afterwards.
- Watch `read_console_messages` and `read_network_requests` throughout. Any JS error or 5xx is a
  defect.

**G. UI/UX**
- Names with `&` and `_` render cleanly in text and tables (no `&amp;amp;` or `\_`).
- Long tables stay usable.
- Chips wrap.
- At 375px width (`resize_window`) there is no horizontal scroll.
- Keyboard: Enter sends, focus returns to the input.
- Download links work and the files open.

## Phase 3 — Findings log
Write `docs/qa/CHROME_QA_<YYYY-MM-DD>.md` with a summary table first, then one entry per issue:

```
### [SEV] Short title          (SEV = Critical | High | Medium | Low)
- Area / fixture / phase:
- Steps (exact messages):
- Observed (quoted):
- Expected (from oracle / docs):
- Evidence: screenshot or GIF path
- Suspected cause: file.py:line
- Proposed fix (one):
- Acceptance test (one):
```

Severity guide:
- **Critical:** a wrong number or direction, commentary contradicting the data, a server crash, or
  data loss.
- **High:** an advertised capability broken, a dead chip, an intake loop, or a security weakness.
- **Medium:** a phrasing gap or formatting inconsistency.
- **Low:** cosmetic.

Also include the capability matrix as a pass/fail grid, and record the outcome (confirmed / refuted)
of every hypothesis in the appendix.

## Phase 4 — Fix loop (test-first)
Fix in severity order: all Critical, then High, then Medium where cheap. For each fix:
1. Write a failing pytest in `tests/` that reproduces the observed behaviour, using the Phase 1
   fixtures and oracle values. Watch it fail.
2. Make the smallest change that fixes the root cause, matching the surrounding code style. The UI has
   one source, `src/variance_agent/static/`; there is no second copy to keep in sync.
3. Run `pytest`, `ruff` and `mypy --strict`; all must be green.
4. Restart the local server and **re-verify in Chrome** with the original repro steps.
5. Commit one fix per commit, citing the findings-log entry.
6. Update the log entry with **Fixed in <sha>**.

Never weaken or delete an existing test to make it pass. If a test encodes the wrong behaviour (for
example, a wrong sign in a fixture), fix the test and say why in the commit message.

## Phase 5 — High-quality improvements (evidence-driven)
Once the defects are handled, propose and implement improvements that make the engine more
**truthful, deterministic and useful**. Each improvement must cite a Phase 2 observation, ship with
tests, and be re-verified in Chrome. Candidate directions, adopted only if the evidence supports them:
- **Fact-gated commentary:** every template sentence is emitted only when a computed fact from the
  analysis result supports it. Add a test that fails if any claim contradicts the numbers.
- **A determinism contract test:** the same input must give an identical transcript (golden files
  for the memo and commentary).
- **A chip ↔ intent contract test:** every chip the UI can show must parse to a non-unknown intent.
- **Intent tolerance:** strip trailing filler and punctuation, match item names inside sentences,
  and add bounded fuzzy matching with "did you mean …?". All of it deterministic.
- **One formatting path:** route every handler through the money/percent helpers in `responses.py`.
- **A benchmark that scores real engine output** on the Phase 1 fixtures.

Write each improvement up in the findings log under "Improvements": the problem observed, the change,
the tests and the before/after transcript. Cap the scope so the PR stays reviewable. List further
ideas as follow-ups rather than implementing everything.

## Phase 6 — Render smoke test (read-mostly)
1. Run `curl -s -m 70 https://variance-analysis-chatbot.onrender.com/status`. A free-tier cold start
   can take up to ~60 seconds. If the URL doesn't respond, report it and skip this phase; don't guess
   another URL.
2. The live site runs `main`, **without your fixes**, and its single session is shared with real
   visitors. Run one short pass in Chrome:
   - upload `examples/sample_variance.csv`;
   - finish intake;
   - send `summary` and `memo`, and click two chips;
   - finish with `reset`.

   No robustness or security probing here.
3. Confirm that the live behaviour matches local `main` behaviour for the issues you found, and note
   any difference that only shows up in deployment (cold start, hosted-mode export refusal, CORS,
   console errors).

## Phase 7 — Deliver
1. Push the branch and open a PR. The body includes:
   - the summary table;
   - the capability pass/fail grid;
   - the fixed vs deferred issues;
   - the improvements made;
   - the test and lint results;
   - a note that merging deploys to Render.

   Don't merge.
2. Stop the background servers.
3. Final message to the user:
   - Critical/High counts, found and fixed;
   - the top 3 remaining risks;
   - the PR link;
   - recommended follow-ups.

## Appendix — Hypotheses to verify (NOT a checklist)
A static read of the code suggested the items below. Confirm or refute each one with browser (or CLI)
evidence and record the result. Do not stop at this list: most of your findings should come from your
own testing.
- The memo takeaway and CLI `--commentary` may state the wrong direction or margin. The bridge in
  `deterministic_conditioning/variance_bridge.py` may sum raw actual − budget across revenue and
  expense lines without sign-adjusting for type, and its residual check may never run.
- `what if revenue drop/decrease/fall 10%` may simulate +10% (direction keywords near the what-if
  handler in `handlers.py`).
- "Skip" on the last unclassified item may loop forever. A reclassification that fails may leave
  `session.phase` stale.
- The waterfall may not reconcile when unclassified rows exist.
- `R&D_Costs` may render as `R&amp;amp;D\_Costs` (double escaping between `report.safe_inline` and
  `chat.html`).
- These chips may be dead: "Net impact", "Action playbook", "Top 3 by dollars", "Supported file
  formats", "Show sheets". Bare `drivers` may return the concept explanation instead of the driver
  summary.
- Subtotal rows may leak into top N, pareto, the memo and tldr ("momentum led by Sales" when Sales
  missed).
- Trailing filler or punctuation may break intents. "show me the biggest risks" may be routed to
  `detail`.
- A percent with a 0 baseline may show `0.0%` instead of N/A in the memo, tldr, compare and what-if.
- The server may crash or hang on a malformed body or bad `Content-Length`. The period text may be
  reflected into the `Content-Disposition` header.
- `tests/test_deterministic_conditioning.py` (`TestVarianceBridge`) may encode a wrong sign for an
  over-budget expense.
- `deterministic_conditioning/benchmark.py` may score hand-written strings, not real engine output.
