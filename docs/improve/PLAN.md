# Improvement pass: plan

Branch `improve/depth-pass`, cut from `main` at `15100c8` on 2026-11-02. The control prompt is `VARIANCE_IMPROVEMENT_PASS_PROMPT.md` (Revision 2), kept outside the repository. This plan plays the rules file's Implementation Plan. It changes only through the Decisions list below. Before an item is edited, it lists the files it touches.

## Status

States: `todo`, `done`, `asked`, `open`, `closed`, `struck`. The ranked backlog, with each item's severity, cost and contract impact, is in [evidence/stop-1/BACKLOG.md](evidence/stop-1/BACKLOG.md). Each item's reproduction is in [evidence/stop-1/audit-findings.md](evidence/stop-1/audit-findings.md). Until STOP 1 answers, every proposed item is `todo`.

| ID | Phase | State | Commit | Files to touch (filled before editing) |
|---|---|---|---|---|
| T1 | 0 (Phase 6 item) | done | `63162aa` | `tests/test_chat_hardening.py` |
| X1 | 2 | done | see `fix(X1)` | `src/variance_agent/intake.py`, `tests/test_amount_forms.py` |
| X2 | 2 | done | see `fix(X2)` | `src/variance_agent/scorecard.py`, `tests/test_scorecard.py` |
| X3 | 2 | done | see `fix(X3)` | `src/variance_agent/pdf_tables.py`, `tests/test_pdf_intake.py` |
| C2 | 2 | done | see `fix(C2)` | `src/variance_agent/comparisons.py`, `tests/test_comparison_captions.py` (new) |
| C5 | 2 | done | see `fix(C5)` | `src/variance_agent/chat/handlers.py`, `tests/test_chat_zero_variance.py` (new) |
| X4 | 2 | done | see `fix(X4)` | `src/variance_agent/intake.py`, `tests/test_unit_scaling.py` |
| X5 | 2 | done | see `fix(X5, X30)` | `src/variance_agent/intake.py`, `ixbrl.py`, `join.py`, `ltm.py`, `metrics.py`, `cli.py`, `comparisons.py`, `api.py`, `chat/handlers.py`, `tests/test_currency_conflicts.py` (new) |
| X6 | 2 | done | see `fix(X6)` | `src/variance_agent/intake.py`, `tests/test_period_choice.py` (new) |
| X7 | 2 | done | see `fix(X7)` | `src/variance_agent/intake.py`, `tests/test_signed_profit_lines.py` (new) |
| X8 | 2 | done | see `fix(X8)` | `src/variance_agent/cli.py`, `comparisons.py`, `report.py`, `tests/test_comparison_path_guards.py` (new) |
| C1 | 2 | done | see `fix(C1)` | `src/variance_agent/parsing.py`, `tests/test_excel_unsaved_formulas_strict.py` (new) |
| C3 | 2 | done | see `test(C3)` | investigated: no change to R5 or the reading; the message part is C3m |
| C3m | 3 | done | see `fix(C3m)` | `src/variance_agent/statement_shape.py`, `intake.py`, `tests/test_statement_sign_ambiguity.py` |
| X30 | 2 | done | see `fix(X5, X30)` | with X5 (one rule, one commit) |
| X41 | 2 | done | see `fix(X41)` | `intake.py`, `comparisons.py`, `tests/test_caption_buffers.py`; asked in [evidence/stop-ask-buffer-scale/ASK.md](evidence/stop-ask-buffer-scale/ASK.md) |
| X9 | — | open | | owned by `claude/per-visitor-sessions-d54fc9` (Decision 12) |
| X10 | 3 | done | see `fix(X10)` | `src/variance_agent/cli.py`, `README.md`, `tests/test_cli_hosted_detection.py` |
| X11 | — | open | | owned by the per-visitor-sessions work (Decision 12) |
| X12 | 3 | done | see `fix(X12)` | `src/variance_agent/chat/server.py`, `tests/test_server_hardening.py` |
| X13 | 3 | done | see `fix(X13)` | `src/variance_agent/cli.py`, `tests/test_cli_output_paths.py` (new) |
| X14 | 3 | done | see `fix(X14)` | `src/variance_agent/audit.py`, `comparisons.py`, `tests/test_comparison_audit_versions.py` (new) |
| X15 | 3 | done | see `fix(X15)` | `src/variance_agent/parsing.py`, `comparisons.py`, `tests/test_tsv_input.py` (new) |
| X16 | 3 | done | see `fix(X16)` | `src/variance_agent/intake.py`, `tests/test_section_headings.py` (new) |
| X17 | 3 | done | see `fix(X17)` | `src/variance_agent/chat/handlers.py`, `parsing.py`, `tests/test_xls_sheets.py` (new) |
| X18 | 3 | done | see `fix(X18)` | `src/variance_agent/comparisons.py`, `tests/test_comparison_headers.py` (new) |
| X19 | 3 | done | see `fix(X19, X26)` | `src/variance_agent/chat/server.py`, `tests/test_server_hardening.py` |
| X20 | 3 | done | see `fix(X20)` | `src/variance_agent/intake.py`, `tests/test_excel_zero_section.py` (new) |
| X21 | 3 | done | see `fix(X21)` | `src/variance_agent/chat/handlers.py`, `tests/test_chat_two_files.py` (new) |
| X22 | 3 | done | see `fix(X22)` | `src/variance_agent/intake.py`, `chat/handlers.py`, `chat/session.py`, `tests/test_chat_unreconciled_total.py` (new) |
| X23 | 3 | done | see `fix(X23)` | `src/variance_agent/intake.py`, `tests/test_header_units.py` (new) |
| X24 | 3 | done (date band open) | see `fix(X24)` | `src/variance_agent/intake.py`, `tests/test_two_row_headers.py` (new) |
| M1 | 3 | done | see `fix(M1)` | `src/variance_agent/ixbrl.py`, `tests/test_ixbrl_statements_elsewhere.py` (new) |
| M2 | 3 | done | see `fix(M2)` | `src/variance_agent/ixbrl.py`, `intake.py`, `tests/test_ixbrl.py` |
| M3 | 3 | done | see `fix(M3)` | `src/variance_agent/intake.py`, `tests/test_excel_bands_and_blocks.py` |
| X25 | 3 | done | see `fix(X25)` | `src/variance_agent/chat/handlers.py`, `tests/test_chat_export_paths.py` (new) |
| X26 | 3 | done | see `fix(X19, X26)` | `src/variance_agent/chat/server.py`, `tests/test_server_hardening.py` |
| X27 | 3 | done | see `fix(X27)` | `src/variance_agent/chat/responses.py`, `chat/handlers.py`, `chat/intent.py`, `tests/test_chat_not_yet_labeled.py` (new) |
| X28 | 3 | done | see `fix(X28)` | `src/variance_agent/mapping.py`, `tests/test_cli_small_refusals.py` (new) |
| X29 | 3 | done | see `fix(X29)` | `src/variance_agent/cli.py`, `tests/test_cli_small_refusals.py` |
| X31 | 3 | done | see `fix(X31)` | `src/variance_agent/intake.py`, `comparisons.py`, `tests/test_percent_formats.py` |
| M4 | 3 | done | see `fix(M4)` | `ixbrl.py`, `intake.py`, `models.py`, `comparison.py`, `comparisons.py`, `report.py`, `cli.py`, `chat/handlers.py`, `tests/test_period_names.py`; asked in [evidence/stop-ask-m4-period-labels/ASK.md](evidence/stop-ask-m4-period-labels/ASK.md) |
| M5 | 3 | done | see `fix(M5)` | `src/variance_agent/intake.py`, `tests/test_ixbrl.py` |
| C4 | 3 | done | see `fix(C4)` | `src/variance_agent/intake.py`, `tests/test_ixbrl.py` |
| M6 | 3 | done | `test(M6)` x2, `fix(M6)` | `scripts/message_inventory.py`, `docs/intake-message-inventory.md`, `tests/test_message_inventory.py`, ten modules' messages |
| X35 | 3 | done | see `fix(X35)` | `src/variance_agent/intake.py`, `chat/handlers.py`, `tests/test_chat_period_chips.py` |
| X36 | 3 | done | see `fix(X36)` | `src/variance_agent/join.py`, `chat/handlers.py`, `chat/session.py`, `docs/audit-contract.md`, `tests/test_join_unbudgeted.py` |
| X42 | 3 | done | see `fix(X42)` | `audience.py`, `measures.py`, `cli.py`, `chat/handlers.py`, `tests/test_measure_source_notes.py` |
| X43 | — | open | | found in X41's tests: a limit, benchmark or target table prints a scaled amount with three decimal places as it holds them ("$89,999.000" from 89.999 in thousands); the value is right, so it is a display finding for the final STOP, not changed here |
| X32 | 5 | todo | | state the rounding on the sheet (Decision 12) |
| X37 | 4 | todo | | |
| X33 | 7 | todo | | |
| X34 | 7 | todo | | |
| X38 | — | open | | cost; not this run except where X17 or X18 touch it |
| X39 | — | open | | memory on the hosted free plan; not this run |
| X40 | — | open | | left to the owner: the deploy pins (Decision 12) |
| S1 | 4 | todo | | |
| S2 | 4 | todo | | |
| S3 | 4 | todo | | |
| S4 | 4 | todo | | |
| N1 | 5 | todo | | |
| N2 | 5 | todo | | |
| T2 | 6 | todo | | |
| T3 | 6 | todo | | |
| D1 | 7 | todo | | |
| D2 | 7 | todo | | |
| D3 | 7 | todo | | |

## Decisions

1. **Worktree cleanup is scoped to this run.** The prompt's "remove finished worktrees before each gates run" covers only worktrees this session creates. The ten worktrees already under `.claude/worktrees/` belong to other branches and sessions and are left alone. `ruff check .` lints 205 files and none of theirs, because `.git/info/exclude` lists `.claude/worktrees/`. If a gate ever reached them, the fix would be an exclude, not a removal.
2. **No side sessions.** Every phase edits this branch in the main clone and depends on the phase before. Subagents run only where the prompt calls for them.
3. **`.scratch/` ignores itself.** A plugin hook in this session blocks shell writes to `.git/info/exclude`. So `.scratch/.gitignore` holds `*`, which makes git, and ruff through git's rules, skip the folder. `/CLAUDE.md` and `.claude/worktrees/` were already in `.git/info/exclude`. `.claude/` holds nothing else, so the only place agent worktrees land is already excluded.
4. **Environment.** The owner chose to rebuild `.venv` on Python 3.11, the floor CI covers. The old Python 3.14 env, which had no pip and no `pdf` or `release` extras, is kept at `.scratch/venv-3.14-old`.
5. **Draw G.** `EDGAR_USER_AGENT` was unset at Phase 0, though `~/vaa-edgar-corpus` exists. The owner sets it; it is raised again at STOP 1 and STOP 2. If it is still unset at Phase 8, Draw G is recorded as not measured. The owner's email goes into no SEC request without their explicit yes.
6. **T1's scope.** Only the test named in section 1 flakes. The subprocess-timed hostile-message tests in the same file (`_assert_quick`, 0.5 s inside a child process) were run under the same load (64 CPU-bound processes on 10 cores): 31 passed. They are left as they are.
7. **T1's method: count the work, not the clock.** Commit `1fc32b8` fixed a 1 to 3 s answer on 20,000 lines. Its cost came from two things: a difflib comparison for every name, and several passes over the names. The test now counts both, at 5,000 and at 20,000 lines. Difflib comparisons must be equal at the two sizes, because the suggestion cap holds whatever the file size. Routing folds may grow by at most three per added name. Three is the current shape, measured by caller: one fold per name in each of `intent._match_key`, `handlers._items_named_in` and the sentence match's word scan. Counting only `handlers` would have shown two. A sanity check confirms the counter is live: at least one fold per name. The counter patches every loaded `variance_agent` module that holds `normalize_for_routing`, so S1's move of the handlers into a package keeps it counting. A wide wall-clock bound was rejected because it would not catch the original regression. That regression took 1 to 3 s, inside any bound wide enough to survive load.

8. **Ranking.** The backlog is ordered by severity: wrong number, exposure, dead end, misleading, unpinned, cost. Within a severity it is ordered by cost (S, M, L). Exposure ranks second because it is a security gap. A finding that is both a wrong number and an exposure (X9) ranks with the wrong numbers.
9. **The shared hosted session (X9, and with it X11).** Open branches already target this: `claude/per-visitor-sessions-d54fc9` and `feat/chat-intro-per-visitor`. Two writers on one design is the collision the comparison-basis run hit, so both items are `asked` at STOP 1 and not started here.
10. **The mutation sample.** One (path, line) pair per branch node. The list is sorted and drawn with `random.Random(20261102).sample(pairs, 25)` (659 branches). The probe worktree was cut at `15100c8`, and its `src/` matches `63162aa`. That worktree and its branch were removed after its files were copied to `.scratch/mutants/`.
11. **Every Phase 1 finding was re-run by the main session**, and every one reproduced. The minor findings listed under the table in BACKLOG.md do not enter the backlog.
12. **STOP 1 (2026-11-02): the owner approved the backlog as recommended.**
    - Phase 2 takes ranks 1-12 plus X30. Phase 3 takes ranks 14-43, except X32 and the doc items.
    - M1 names the second document in its refusal and does not read it.
    - X9 and X11 are left to the open per-visitor-sessions work: `open`, owned elsewhere.
    - C5 covers all 8 chat handlers. At zero, the table says "Neutral" and the text says "in line with budget" (memo, run-rate, compare, utilization, profitability, greeting) or "no change" (what-if, sensitivity).
    - X32 states the rounding on the sheet and changes no cell value.
    - X40 is left to the owner (`open`). X38 and X39 are `open` as proposed.
    - Draw G waits on the owner setting `EDGAR_USER_AGENT`.

## Phase 2 rules (written before each item's test)

**X1, footnote marks beside an amount.** Assisted reading applies NFKC to an amount only to fold full-width forms and odd spaces. A character that is not itself a decimal digit (Unicode category Nd) but folds under NFKC into ASCII digits is a mark beside the number, never part of it. That covers superscripts `¹²³`, subscripts `₁`, circled `①` and `⑩`, parenthesised `⑴`, and digit-with-stop `⒈`. A cell holding one is refused. The refusal names the row, the line, the column and the mark, so the reader can remove the mark. This keeps strict mode's answer, which already refuses such a cell. Silently reading the figure without the mark would be a transformation nobody approved, so the cell is refused instead.

Boundary cases:
- `９５０` (full-width digits, category Nd) still reads 950.
- `950` reads 950.
- `950¹`, `¹950`, `9²50`, `950₁`, `①`, `⑩` (no digit value, but NFKC gives "10"), `950⑴` and `950⒈` are refused.
- NBSP and other spaces fold as before.

**X2, scorecard sheets from a workbook.** The contract says "weights read as printed". For a scorecard's holdings or panel sheet read from `.xlsx` or `.xlsm`:
- Every numeric cell is its stored decimal text (`excel.cell_value`), never a binary float.
- It is read as Excel prints it. A cell whose number format shows a percentage is its stored value times 100, followed by `%`, so 0.124 under `0.00%` reads `12.4%`, exactly what the CSV holds. Times 100 is an exact power-of-ten shift (`scaleb(2)`).
- A cell whose format scales the display by a power of ten that is not a percentage (thousands, millions), or whose format this reader cannot interpret, is refused, naming the cell, since a weight or a per-share figure is never stated in thousands.
- The existing mixing rule then sees a `%` per cell: a percentage-formatted weight beside a General one refuses, as the CSV does.

Boundary cases:
- `0.124` under `0.00%` reads 12.4 (with `%`).
- `12.4` under General reads 12.4 (without `%`).
- `0.124` under General reads 0.124.
- A `#,##0,` weight is refused.
- A sheet mixing percent and General weights is refused.
- Fraction oracle: weight = Fraction(stored text) x 100.

**X3, a PDF statement's unit caption.** A statement's unit caption names thousands, millions or billions. It is read wherever the statement prints it:
- On its own line between the title and the figures, parenthesised ("(In millions)") or not ("In millions, except per share amounts").
- Left of the amount columns on the year header line (today: parenthesised only).
- Inside parentheses on the title line itself ("CONSOLIDATED STATEMENTS OF OPERATIONS (In millions)").

A caption line is never glued onto the column names. A unit parenthetical on the title line does not count against the title's 25-character slack, so a long caption does not cost the title.

Boundary cases:
- Own-line parenthesised, as today: scaled.
- On the title line, short or long: scaled.
- Unparenthesised own line: scaled, and the column reads as FY2025, not "In millions ... FY2025".
- A title line with "(Unaudited)" and no unit is not a caption.
- A non-unit line such as "Year Ended December 31," is not a caption.

**C2, a unit caption on the comparison path.** `comparisons.read_comparison_input` serves `--preset earnings|quant`, comma lists in `--compare-to`, the layout and long-output flags, `api.analyze_file`, `panel_cli` and the chat's earnings flow. For an assisted or mapped CSV or workbook it now reads the unit caption as the FP&A path does: `detect_unit_scale` over the title rows above the header plus the header row.

The caption applies exactly once, to each Currency row's amount columns:
- Actual.
- Every column `basis_for_header` names (Budget, Forecast, Prior Period, Consensus, Guidance, ...).
- Every period column.
- The range and spread columns: Low, High, Consensus Low and High, Guidance Low and High, Std Dev, Dispersion.

It never applies to the line item, Measure, Better, Type, Segment, counts ("# Est", Number of Estimates) or other text. It never applies to a Percent, Per Share, Count or Multiple row.

Cells whose number format already scales them are reconciled by FP&A's own `_reconcile_display`:
- All of them agree with the caption: they are read as stored, with FP&A's note.
- A scaling format without a caption: they are read as stored, with FP&A's "Excel shows some amounts scaled" note.
- A mix: the run is refused, naming the cells.

A stored numeric cell is multiplied exactly. A text cell the strict reader accepts (`$7`, `(8)`, `1234`) is rewritten with its value scaled and its currency symbol kept, so the later currency check still sees the symbol. A text cell the strict reader refuses is left as it is and refuses later, as today.

The note is FP&A's wording: "Amounts scaled from thousands (x1,000). ...". The audit's existing `transformations.unit_scale` field records the multiplier. The strict paths (no `--assisted`, no mapping) are unchanged, as on FP&A. Buffer and Tolerance wait on X41.

Boundary cases: caption alone, scaling format alone, both, and caption with a mix of formats, each on FP&A, earnings and `api.analyze_file`. Also: a Per Share row under a caption stays unscaled; "# Est" stays unscaled; Consensus Low and High scale. Fraction oracle: scaled = Fraction(stored) x 1000.

**C5, a zero variance in the chat.** The engine's rule gives Neutral at exactly zero (`analysis.py`). The chat's totals now follow it. Strictly above or below zero, nothing changes.

**Tables.** A Status cell of F or U reads `Neutral` at zero. This covers the compare macro table's three rows, the what-if table, each sensitivity scenario and the run-rate table's three rows. The memo's Outcome column reads `In line` where it says Beat or Miss and Overrun or Savings, and `Neutral` where it says Favorable or Unfavorable.

**Text.** A zero total is "in line with" the comparison:
- Utilization: "(in line with budget)".
- Compare: "Operating profit finished at A, **in line with** the budget target of B."
- Run-rate: "(in line with annual budget of B)" and "(in line with plan)".
- Memo: "Operating Profit finished at A, **in line with** the planned budget of **B**"; revenue and expense say "in line"; a zero margin change says "Operating margin **held** at **M**".
- Greeting: "Overall net operating impact is **in line with** budget".
- Profitability: "(in line with budget; ...)".

For a basis other than Budget, the basis noun replaces "budget", as these handlers already do. The what-if and sensitivity text already handle zero ("neutral", "on track") and is unchanged.

Two zero cases came out in testing:
- **What-if.** The table's target row and its two total rows compare with `>=` and `<=`. They now go through the same Neutral-at-zero status, by comparison only, with no new arithmetic.
- **Run-rate.** At Q3 the multiplier 12/9 rounds at 50 digits, so the run-rate and Latest Estimate variances came out a hair off zero (F, shown as $0.00). Both are now computed from their exact identities: run-rate variance = (Actual profit - Budget profit) x 12/elapsed; LE variance = LE profit - annualised budget = Actual profit - Budget profit, since remaining/elapsed + 1 = 12/elapsed. The displayed figures are unchanged except at an exact half-cent. Fraction oracle on a nonzero file: the run-rate variance shown is Fraction(Actual - Budget profit) x 12/9, rounded half-even to the cent, and LE's is Fraction(Actual - Budget profit).

Boundary cases: a fictional file whose every line has Actual = Budget gives zero totals and zero for every projection; the same file with one revenue line one cent up gives F and the old words. Both the table cells and the sentences are tested.

**X4, which captions name a unit.** `detect_unit_scale` reads the title rows and the header row. It names a unit only in a caption form, never on a bare letter that happens to follow "in".

Caption forms, case-insensitive, where U is the unit word (thousands, millions, billions):
- "in U", allowing a currency between: "in $ thousands", "in USD millions".
- "(U" and "(in U", allowing a currency before: "($ in thousands)", "(USD thousands)".
- A currency word or code before U: "Dollars in Thousands", "EUR millions", "USD thousands".
- "U of dollars, euros or pounds": "(thousands of dollars)", "Millions of dollars".

The short forms:
- Thousands: a currency symbol or code then `000` with an optional apostrophe or `s`, as in `$000`, `£000`, `€000`, `£'000`, `$'000`, `USD '000`, `$000's`; `(000)`, `(000s)`, `(000's)`; `$K` and `(K)`.
- Millions: `$m`, `£m`, `€m`, `$MM`, `($MM)`, `(m)`, `(MM)`; "in m" or "in MM" only when no `&`, apostrophe, letter or full stop follows. So "Costs incurred in M&A review" names no unit.
- Billions: "in billions" and the other word forms; `$bn`, `£bn`, `€bn`, `(bn)`, "in bn".

Millions is checked before billions, and billions before thousands. That keeps today's millions-over-thousands order ("In millions, except shares in thousands").

The FP&A note now names billions too ("Amounts scaled from billions (x1,000,000,000)"). Thousands and millions keep their exact wording.

Boundary cases: every one of the 32 variants in `.scratch/audit-numbers/captions.py`, plus "Costs incurred in M&A review", which is 1, against "(in M)", which is a million. Each existing test case keeps its result.

**X5 and X30, amounts in another currency.** No currency is converted, so an amount marked in one currency is never reported under another.

Intake records the currency each source marks:
- **X5.** Every assisted amount cell whose text carries `$`, `€` or `£`, with its row, line and column.
- **X30.** A filing statement's currency, taken from the ISO code of its monetary facts' units. A per-share unit such as `iso4217:EUR/xbrli:shares` counts as EUR.

`intake.currency_conflict(result, currency)` says why the reporting currency disagrees, or returns None. The two-file join carries both halves' marked cells.

Where the check runs:
- The CLI's assisted and mapped paths, after intake.
- The comparison path's filing read, in the CLI and in `api.analyze_file`.
- The chat, in `_run_analysis`. A conflict there returns to the currency question with a chip for the marked currency, and the analysis does not run.

Refusal wording: "Some amounts in 'x.csv' are marked in EUR, but the reporting currency is USD, and no currency is converted:", then up to 10 cells, then the fix. The CLI says "Run with --currency EUR"; the chat says "Choose EUR". A filing reads "'f.htm' reports its amounts in JPY ...". A currency the tool cannot report in (JPY) says "this tool reports in USD, EUR or GBP only". Mixed marks say "give every amount in one currency".

The LTM build table and the derived-metric citations print in the filing's own currency, never a hard-coded `$`. Once a conflict is refused, that is the reporting currency.

Boundary cases:
- `€100` under EUR reads.
- `€100` under USD refuses, naming the cell.
- An unmarked `100` reads under any currency.
- `$` under USD reads.
- One `£` cell among `$` cells under USD refuses, naming only the `£` cell.
- A USD filing under EUR refuses.
- A JPY filing refuses under every currency.
- An EUR filing under EUR builds an LTM table in `€`.

**X6, a chosen period reads that period's columns.** When the reader has chosen a period (the chat's period chips, `selected_period`) and the header row holds that period's Budget and Actual pair, those two columns are the ones read. That holds even when another pair's names ("Budget YTD", "Actual YTD") are also plain Budget and Actual synonyms. Without a chosen period, or when the row has no pair for it, the header is read as before. The summary's "Analyzed period" and "Columns mapped" then name the same columns.

Boundary cases on one fictional file with Sep-26 and YTD pairs:
- Choosing "Sep-26" reads 55,556 and 60,000.
- Choosing "YTD" reads 500,000 and 540,000.
- No choice keeps today's columns.
- A file with only "Budget YTD" and "Actual YTD" reads them whatever the choice.

**X7, profit lines in a signed ledger.** When intake reads a ledger as signed (revenue stored as negative credits) and turns revenue's sign, the profit lines are decided too. A profit line is any label `classification.is_profit_measure` names: gross, operating or net income, profit, earnings, loss or margin; income before or after anything; pre-tax income; income from operations. For each Currency profit line:
- Turn it when turning makes it add up as a subtotal of the lines above.
- Keep it as stored when only the stored sign adds up, as in an export that prints profit presentation-signed.
- Turn it when neither adds up, since that is the ledger's own convention, and leave it among the line items as today.

The turned profit lines join the flip note ("... for 2 revenue lines and 2 profit lines (Gross Profit, Net Income)") and the audit's `flipped_line_items`. Subtotal detection then excludes the ones that add up, as it does for any subtotal.

Boundary cases:
- A profitable signed ledger (Gross Profit -480,000, Net Income -300,000) turns both, and both are excluded as subtotals.
- A loss-making one (Gross Profit +50 with revenue -100 and costs 150) turns it to -50, which adds up.
- A presentation-signed Gross Profit (+480,000 in a signed ledger) is kept.
- A Gross Profit off by one dollar adds up neither way: it is turned and stays a line.

**X8, what the comparison path cannot do it refuses, and a filing keeps its printed totals there.** Some flags send a run to the comparison path (`_run_comparisons`):
- a comma list or a new basis in `--compare-to`, or a mapping's segment column;
- `--preset` other than fpa;
- `--long-output`, `--long-output-jsonl`, `--history`, `--layout`, `--headline`, `--per-share-lines`.

A run with one of these that also asks for something only the main path does now refuses before reading anything, naming the flags on both sides. The main-path inputs are `--ltm-from` (builds LTM), `--compare-file` (joins a second file), `--metrics` (computes declared metrics), `--panel` (builds a holdings scorecard) and `--compare-to limit|benchmark|target` (reads Limit Kind, Buffer, Better or Tolerance). The message: "--layout can't be combined with --ltm-from yet: it reads the file another way, which doesn't build LTM. Leave out --layout, or leave out --ltm-from." An opt-in basis in a comma list gets the documented one-per-run refusal.

`--multiple-threshold` now reaches the comparison path's configuration, as the per-share, count and bps thresholds already do.

An Inline XBRL income statement read on the comparison path in the standard layout is headed by the filing's own printed totals (`_filing_headline_lines`, Decision 39), never by Total Revenue, Total Expenses and a net variance added up from its lines. `--xlsx` refuses for it, and for a balance sheet or cash flow statement, with the main path's own messages. The earnings layout and the long CSV, which add up nothing, are unchanged.

Boundary cases:
- The LTM run without `--layout` still builds LTM.
- With `--layout` it refuses.
- `ines_limits.csv` with `--compare-to limit` alone reads, with `--long-output` it refuses, and `limit,benchmark` gets the one-per-run refusal.
- A Multiple row with `--multiple-threshold 0.1 --long-output` reads.
- The 10-K with `--long-output` heads the report with its printed totals, and with `--xlsx` refuses.

**C1, uncached formulas in a computed column.** Assisted intake classes a "Var $", "Var %", "Variance" or "% of Budget" column as computed (`intake._IGNORED_COMPUTED_SYNONYMS`) and never reads it. An uncached formula there is noted, not a stop. Strict intake also never uses such a column, since the engine computes the variance itself, and it reads the same file with cached values. So its formula check (R4) now skips the computed columns too, and the two modes agree. Every other named column keeps the stop, as before. An uncached formula in Budget or Actual refuses in both modes, naming the cell.

Boundary cases:
- Uncached formulas only in "Var $": strict and assisted both read, with the same figures.
- An uncached formula in Actual: both refuse.
- An uncached formula in an unrecognised column ("Notes"): strict still refuses, as today.

**C3, the pre-tax refusal: the arithmetic and the decision.** Investigated on Draw C's filing `0001193125-26-344691` in `~/vaa-edgar-corpus/` (probe output in `improve-c3/`, not committed). Every fact carries `decimals` -6. Prior year, $M: Operating income 188, Other expense net (1), Interest expense (15), Interest income 5, against a printed pre-tax income of 178. As printed they sum to 177, $1M under 178. The current year foots exactly: -86 + 0 - 60 + 5 = -141.

*R5 is right.* Each term is +/-0.5, so the sum is 177 +/- 2.0 = [175, 179]. That overlaps 178 +/- 0.5, so R5 calls the subtotal consistent.

*The refusal is the structure search, and it is correct.* `statement_shape` tries both signs for each line between the last subtotal and this one, with tolerance unit x terms / 2 = 2.5. In the prior year, "Other expense, net" (1) fits added (177) or subtracted (179), each 1 from 178. In the current year it is 0, so nothing decides between them. Two readings disagree on a nonzero line, and the shaper refuses rather than guess. That is constraint 2's acceptable outcome, not a wrong number.

The $1M gap is not even the cause. On a synthetic statement of the same shape, the refusal holds with no gap at all (233 against 233), because adding or subtracting a 1-unit line lands within the tolerance either way. It goes away when the line is 5 units.

*Decision.* No change to R5's interval, which would be a STOP-ASK in any case, and none to the reading. What misleads is the message, "I couldn't tell which lines ... adds up": the lines are known, and only one line's sign is not. That wording is C3m in Phase 3. `tests/test_statement_sign_ambiguity.py` pins the behaviour on the synthetic statement.

13. **Phase 2's chat screens are captured in Phase 3's screenshot run.** Phase 2 changed three chat screens: C5's Neutral tables and "in line" text, X5's currency question, and X6's summary. They are shot together with Phase 3's screens into `docs/improve/evidence/phase-3/` before STOP 2, with a scenario added for any screen no scenario reaches.
14. **Revert proofs reverse a saved diff** (`git diff -- <files> > patch; git apply -R patch; test; git apply patch`), never a checkout of the tree. The auto-mode classifier rightly blocked a `git checkout -- .` typed in error, and the X1 work was not lost.
15. **M6 counts the intake messages a chat reader can see.** The rules file defines jargon and fixes for "a message Maya sees". So `scripts/message_inventory.py` lists every intake-workflow message: the old inventory's modules plus the readers added since (`intake.py`, `join.py`, `pdf_tables.py`, `ixbrl.py`, `statement_shape.py`, `ltm.py`, `metrics.py`). It counts only those the chat can show.
    - Listed with their reason but not counted: the command line's own messages, the strict reader (`parsing.load_input` and its helpers, which the chat never calls), the server's protocol replies, internal checks, the engine's checks of API arguments, a raise caught where it is raised, and clauses another message completes.
    - A message shown inside another (an Excel or JSON read error after "Could not read ...", a cell under "Fix these cells ...") is checked for jargon, and its wrapper is scored for the fix.
    - Only errors and refusals are scored for a fix; a confirmation or a question is not.
    - Engine errors are checked as `plain_analysis_error` shows them.
    - The scanner was frozen before any message changed. One refinement followed on the same source, before any edit: it now recognises a fix given after a condition ("If the filing puts them in another document, upload that document"). **Before, at `ff8abcb`'s source:** 228 messages seen, 17 with jargon, 34 of 82 errors with no fix, 48 failing either check. The first run, without the refinement, gave 35 and 49. The hand-written count at `a3ce6bb` (113 messages, 32 jargon, 70 no fix) used other scope and rules, so it is not comparable.
    - Fixing showed two more gaps in the scanner. It now reads text a function assigns to a local name before passing it on (the workbook refusal "could not be opened safely" was missed). It also knows that assisted intake puts its own refusal in place of the workbook check's errors (`excel.inspect_workbook`), which the chat therefore never shows. **The final scanner on the pre-fix source** (`d8542ff`, run in a temporary worktree with that tree's package first on the path, then removed): 235 messages seen, 10 with jargon, 37 of 86 errors with no fix, 44 failing either check. The revert proof reproduces these exactly.
    - **After `fix(M6)`:** 235 seen, 0 with jargon, 0 of 86 errors with no fix, 0 failing. `tests/test_message_inventory.py` now asserts that no message a chat reader sees fails, so a new message that does fails the suite.
    - Two changes went beyond words. A Statement Kind column accepts "Balance Sheet" and "Cash Flow" as well as `balance_sheet` and `cash_flow`, since the message now names the plain forms. An oversized upload's reply names the 32 MiB limit, where it used to say "Request body is too large.".
    - Limits stay (constraint 10). Only the words change.
16. **STOP 2 (2026-11-02): the owner answered "Approve as recommended".** That reply came to the report's questions 1 to 4, so it approves each as recommended there:
    - Phase 4's S1 to S4, with `_handle_executive_memo` added to S4.
    - Phase 5's N1 and N2.
    - X42: intake's notes reach the measure report and the audit's `inferences`, and the bare-rate note appears only when a bare rate was read.
    - The two open STOP-ASKs: X41 scales a Currency row's Buffer and Tolerance with the caption or declared unit, and M4 adds the duration as a display name only, keeping every key.
    - The three behaviour changes (X42, X41, M4) land first, each with its own rule, test and revert proof, before Phase 4 starts, so no refactor commit shares a change of behaviour (constraint 8).

## Phase 3 rules

**X10, the `RENDER` variable.** `RENDER` in the environment still implies hosted mode for a bare `--chat`. The Render platform sets it, and `test_render_environment_implies_hosted` pins that design. An explicit `--no-browser`, though, asks for a local URL, so it now wins: `RENDER=1 variance-agent --chat --no-browser` serves on 127.0.0.1. The `--hosted` help and the README name the variable.

Boundary cases:
- With `RENDER` and `--chat`: hosted (unchanged).
- With `RENDER`, `--chat` and `--no-browser`: local.
- Without `RENDER`: local (unchanged).

**X12, a body dripped slowly.** A request body is read in chunks against one deadline: 20 seconds plus 1 second for each MiB declared, so even the 32 MiB cap gets about 52 seconds. Past the deadline the server answers 408 with "The upload arrived too slowly. Please try again." and closes the connection, so a client sending a byte every few seconds no longer holds the single worker indefinitely. The per-read 15 second timeout stays. A body that ends early is returned short, as before.

Boundary cases, with the deadline narrowed in the test:
- A whole body sent at once reads.
- A body dripped past the deadline gets 408 and does not wait for the rest.

A slow drip of the header lines is left as suspected and not fixed: the standard library reads headers itself, and the audit did not reproduce it.

**X13, an output path over an input.** Every file a run reads is an input that no output may overwrite: the source, `--type-map`, `--mapping`, `--history`, and now also `--compare-file`, `--ltm-from`, `--metrics` and `--panel`. That includes symlink, hardlink and case aliases, through the existing `_same_path`. The refusal keeps its existing wording ("Input, type-map, report, audit, and workbook output paths must be distinct.") and the input stays untouched.

Boundary cases:
- `-o` equal to each of the four new inputs refuses.
- `-o` to a fresh path reads, as before.

**X14, a comparison audit that needs 1.9.** `audit.needs_schema_19` is the one test of whether a record needs audit 1.9. It covers a workbook examination; a filing, LTM, join, metrics or scorecard source; an opt-in basis; or a Multiple measure. `build_audit_record` uses it as before. A comparison set (`build_comparison_audit`) now uses it too: with no version asked, the set and every child are 1.9 when any comparison needs it, otherwise 1.8 as today, and an explicit 1.9 is accepted. Schema 1.9 already describes comparison sets, so no schema changes.

The refusal names what needs 1.9 instead of always blaming a workbook examination: "how the filing was read", "the LTM build", "the two-file join", "the derived metrics", "the holdings scorecard". A workbook keeps "what the workbook examination found".

Boundary cases:
- A 10-K under `--preset earnings` with `--audit-json`: a 1.9 record that validates against `audit-1.9.schema.json`.
- The same with `--audit-schema-version 1.8`: "Audit schema 1.8 cannot record how the filing was read; use --audit-schema-version 1.9."
- A CSV earnings run: 1.8, as today.

**X15, tab-separated files.** With `--assisted`, a `.tsv` or `.txt` file is read by assisted intake's own delimited reader, the one the chat's paste path uses, on the FP&A and the comparison path alike. Without `--assisted` it refuses: "Tab-separated files are read with --assisted, which detects the delimiter and lists every adjustment it makes." That matches the PDF and HTML wording. An unknown format names everything that works: "Unsupported input format '.docx'. Use CSV, JSON, XLSX, XLSM or XLS; with --assisted, also TSV, PDF or an EDGAR .htm filing."

Boundary cases:
- The fictional pasted TSV fixture reads with `--assisted`, and with `--preset earnings --assisted` on a consensus copy.
- It refuses without `--assisted`.
- `.docx` refuses with the full list.

**X28, a mapping file that is not JSON.** The contract promises a malformed mapping a message that starts "Mapping file", never a parser error.
- Text that is not valid JSON: "Mapping file is not valid JSON at line L, column C. Save it again from the chat ("save mapping"), or fix the JSON there."
- Bytes that are not UTF-8: "Mapping file is not UTF-8 text."
- Structural errors keep their messages.

**X29, `--check-only` with a long output.** `--check-only` writes nothing, so `--long-output` and `--long-output-jsonl` refuse beside it, as `-o`, `--audit-json` and `--xlsx` already do: "--check-only cannot be combined with --output, --audit-json, --xlsx, --long-output or --long-output-jsonl."

Boundary cases:
- `{oops` refuses with line 1, column 2.
- `[]` keeps "Mapping file must be a JSON object."
- `--check-only` alone validates.
- `--check-only --long-output x.csv` refuses and writes no file.

**X16, section heading rows.** A row whose line item stands alone, with no value in any other column except an account ID, is a section heading (REVENUE, OPERATING EXPENSES). It is left out of the line items with a visible note: "Left out 2 section heading rows with no amounts in any column: Row 2 (REVENUE), Row 4 (OPERATING EXPENSES)." It is not reported as an amount to fill in. A row with a label and any amount keeps today's handling, so a blank Actual beside a Budget still stops, naming the cell.

Boundary cases:
- Headings with every other cell blank are left out with the note.
- The same label with a Budget and a blank Actual still refuses "Row 5, Rent, Actual column: the amount is blank."

**X17, sheets of an `.xls` workbook in the chat.** An `.xls` upload that intake reads is an Excel 2007+ workbook saved under the old extension; a real legacy `.xls` is refused at upload, as before. Its sheets are listed and switched like an `.xlsx` workbook's: `.xls` joins the chat's multi-table suffixes and `get_workbook_sheets`.

Boundary cases:
- "list sheets" and "sheet Data" work on such an `.xls`.
- A `.csv` still answers that it holds a single dataset.

**X18, one set of header names.** The comparison path recognises every line-item and Actual name that assisted intake does (`intake._LINE_ITEM_SYNONYMS`, `_ACTUAL_SYNONYMS`): "Description", "GL Account Name", "Account Title", "Line Item Name", "GL Description", "YTD Actual". The names it knew before keep their precedence, and the further names are used only when none of those is present. So a file with both "Account" and "Description" still takes "Account" as today, never a new ambiguity refusal. A test pins the two lists together, so they cannot drift again.

Boundary cases:
- `Description,Budget,Forecast,Actual` reads with `--compare-to budget,forecast`.
- `Line Item,Budget,Forecast,YTD Actual` reads.
- `Account,Description,...` still takes Account.

**X20, a zero under a scaled Accounting format.** A zero amount shows the same in any unit, and an Accounting format shows it through its `"-"` section, which has no digits. So a zero cell neither agrees nor disagrees with a unit caption, and it is left out of the caption-against-format reconciliation (E1). The other cells decide, as before.

Boundary cases, under a "($ in thousands)" caption and the format `_(* #,##0,_);_(* (#,##0,);_(* "-"_);_(@_)`:
- With one zero Actual, the book reads as stored ("not scaled again"), and the zero reads 0.
- A nonzero cell in General beside the scaled ones still refuses, as before.

**X19 and X26, what an upload replaces.** An upload replaces the session's file only when it reads. A refused one keeps the earlier file and its analysis, which `handle_upload` already does. The server now follows the same fact, whether `session.source_bytes` changed:
- **X19.** Staged downloads are discarded only when the file was replaced, so a Download link already in the conversation still works after a refused upload.
- **X26.** The start-up file's first reply (`initial_response`, served by `/status` for a page reload) is dropped when the file is replaced or the session is reset, so a reload never shows it as current. A refused upload keeps it, since its file is still the current one.

Boundary cases:
- A refused upload keeps both the downloads and the start-up reply.
- A successful upload drops both.
- A reset drops both.

**X21, the next upload after one half of a pair.** While one half is waiting:
- **A whole file** (both Budget and Actual) is read on its own: "'f.xlsx' has both Budget and Actual, so I read it on its own and set 'bud.xlsx' aside." If that file is refused, the half keeps waiting.
- **Another file of the same half** replaces the one held, and the request is repeated: "'bud2.csv' replaces 'bud.csv': it has Budget figures but no Actual column. Upload the file with the actuals, ...". The same file again is named as such: "That's 'bud.csv' again. ...".
- **The missing half** is joined, as before.

So the chat never shows the join's command-line wording ("without --compare-file"), and nothing traps Maya.

Boundary cases:
- budget, then a whole file;
- budget, then the same budget;
- budget, then another budget;
- budget, then actuals (the join, unchanged);
- budget, then a broken file (refused, budget kept).

**X25, `~` in a local export path.** In local mode, a path that starts with `~` means the home folder, as in a shell. It is expanded before writing (`Path.expanduser`), and the reply names where the file landed. So `export report ~/r.md` writes `<home>/r.md` and never creates a folder named `~` in the working folder. A relative path writes where it did, and hosted mode still refuses every path. A home folder that cannot be found refuses through the existing "Could not write to ..." reply.

Boundary cases:
- `~/r.md` lands in home.
- `out/r.md` lands under the working folder, as before.

**X27, "Unclassified" in the chat.** The rules file names "Unclassified" as jargon and gives the words to use. In everything the chat shows, an unclassified line is:
- "Not yet labeled" in a table's Type or Status cell, the filter chip and the filter heading;
- "not yet labeled revenue or expense" in a sentence, which covers the summary's classification count, the skip notice, the type and status in a line's details, and each engine warning as the chat displays it.

The "Not yet labeled" chip routes to the same filter as the word "unclassified", which still works. The engine, the reports, the audit and the CSV export, which are data with contracts, are unchanged.

Boundary cases:
- After "Skip all", the material table's cells, the warnings reply and the chips hold no "Unclassified".
- The chip "Not yet labeled" lists the same rows as typing "unclassified".
- A CLI report keeps its warning text.

**X22, a total that doesn't match its lines.** When the engine refuses a category total that does not reconcile (`analysis.py`: "Summary ... does not reconcile to ... detail rows"), the chat keeps the file and every setup answer. It no longer drops back to "upload a file". It says what is wrong with the arithmetic from intake's own record (`UnreconciledTotal`, figures already scaled): "'Total Opex' looks like the total of the Expense lines above it, but its Budget is $251,000.00 and those lines add up to $250,000.00 ($1,000.00 apart). A total that doesn't match its lines can't be checked, so I stopped instead of guessing." The chips are "Leave Total Opex out", "Upload a different file" and "Show technical details".

"Leave Total Opex out" removes that one row. It records the exclusion like any excluded total (the audit's `excluded_totals`, and the summary's transformations: "Left out 'Total Opex' at your request: it doesn't match the lines it totals"). Then it runs the analysis. Without intake's record, the message falls back to the plain sentence without figures. The garbled "detail rows detail rows" in `plain_analysis_error` rule 6 is fixed, and the CLI keeps rule 6's corrected sentence.

Fraction oracle: the apart figure is Fraction(total) - Fraction(sum of lines).

This applies to a first analysis only. A rerun after a new label already rolls that label back when it breaks a total (`_rerun_after_classification`), and that stays.

Boundary cases on a fictional thousands report:
- Total Opex 251 against lines 250: refused with the figures and the chip.
- The chip leaves it out, the analysis runs, and the Expense total is 250,000.
- Total Opex 250 reconciles and is excluded silently, as today.

**X23, a unit or currency in an amount heading.** An amount heading may end in a unit or currency qualifier: "Budget ($000)", "Budget $000", "Budget ($K)", "Budget (in thousands)", "Budget ($ in thousands)", "Actual (000s)", "Budget $", "Budget (USD)". It is recognised as Budget or Actual by the words before the qualifier. Only those qualifiers are set aside, so "Budget (Q3)" is not.

The qualifier stays in the header text the caption detector reads (X4), so "($000)" scales by 1,000 with the usual visible note. A currency it names (`$`, `€`, `£`, USD, EUR or GBP) is recorded like a marked cell (X5): "Budget (EUR)" refuses under USD, naming "the 'Budget (EUR)' column heading". The comparison path's header names are not widened here; that is X18's list.

Boundary cases:
- The 6 forms that failed now read.
- "Budget ($000)" scales by 1,000.
- "Budget (USD)" reads unscaled under USD and refuses under EUR.
- "Budget (Q3)" stays unrecognised.

**C3m, naming the line whose sign can't be told.** When two or more sign readings of the lines under a subtotal fit within the printed figures' rounding, the shaper records the lines the readings disagree on (`ShapedStatement.ambiguous`). The filing refusal then names them: "I couldn't tell whether 'Other expense, net' adds to or takes away from 'Income before income taxes' in the Consolidated Statements of Operations: within the rounding of the printed figures, both readings add up, so I stopped instead of guessing. Upload a CSV or Excel copy ..." A subtotal that nothing above it adds up to keeps today's sentence. The reading itself is unchanged (C3's decision).

Boundary cases:
- C3's synthetic shape names "Other expense, net".
- The 5-unit case still matches, so there is no refusal.

**M3, bare-year bands.** A band of bare years above Budget and Actual (2025, 2026, merged or running right across blanks) is a period band, like "Sep-26" or "FY2025" (E4). The years join the columns below ("2026 Budget"), the newest is read unless the reader chooses, and the usual note names the headings. Period-pair detection takes a bare year (19xx or 20xx) when no other period form is in the heading, so "2026 Budget" pairs with "2026 Actual".

Boundary cases:
- Merged 2025 | 2026 bands read 2026 by default and 2025 when chosen.
- Unmerged bands that run right across blanks read the same.
- A band of one year alone is not a period band (E4 needs two), as before.

**X24, a header split over two rows.** When no single row is a header, two adjacent rows are read together: a name on the upper row stands for the blank cell below it. That covers "Account Description" in A1 merged down to A2, or "Type" in B1 over a blank B2. The pair is the header when the combined row is. The data starts below the lower row, and the note names what came from where: "Read the column names from rows 1 and 2 together: 'Account Description', 'Type' (row 1) above blank cells of row 2." A band over the amounts ("Year to Date" over Budget and Actual) stays above the header, as any title row does. A file that has a single-row header reads as before.

Boundary cases:
- A1:A2 merged with a band over C1:D1 reads.
- Unmerged names on row 1 over a blank row-2 cell read.
- A file whose lower row has no Budget or Actual still refuses, as today.

Not covered: a date band merged over Budget and Actual ("Could not determine period order for Sep 2026, Sep 2026", Maya's f17) fails inside the single-row period path, before any header is tried. It stays `open` under X24 with this note.

**M1, statements in another document.** When a filing holds no statement table, the refusal names the next step. If the document links to an exhibit 13 file (an `href` whose plain file name, letters, digits, `.`, `_` and `-` only, says ex13, ex-13 or exhibit13), it names that file: "The financial statements aren't in 'f.htm' itself: it points to Exhibit 13 ('fake-20261231ex13.htm'), the annual report that holds them. Upload that document from the same EDGAR filing, or the statements as Excel or CSV." If the text only mentions Exhibit 13, it says so without a file name. Otherwise it keeps today's cause and adds the step: "... If the filing puts them in another document (often Exhibit 13, the annual report), upload that document from the same EDGAR filing; otherwise upload the statements as Excel or CSV." The second document is not read (Decision 12). Only a plain file name from the untrusted HTML is quoted.

Boundary cases:
- A linked `...ex13.htm` is named.
- A plain mention of "Exhibit 13" is named without a file.
- Neither gives the generic next step.
- A link with path characters is not quoted.

**M2, a statement that runs on into an untitled table of other periods.** Such a table is still not joined, as the existing test pins. The statement it follows is marked (`Statement.runs_on`). When that statement then fails its checks (income footing, or the balance sheet and cash flow checks), the refusal states the likely cause instead of a footing message that misstates it: "The Consolidated Balance Sheets seems to run on into the next table, which shows other periods, so I couldn't read it whole and stopped instead of guessing. Upload a CSV or Excel copy of the statement, or the filing's PDF." A marked statement that reads keeps reading.

Boundary cases:
- A balance sheet whose liabilities sit in an untitled table of other periods gets the runs-on refusal.
- A complete balance sheet followed by such a table reads, as in the existing test.

**M5, which numbered line is which.** A label printed more than once, where no open section names the copies, is still numbered by its place ("Deferred income taxes (1)", "(2)"). The keys stay with the line by position. A reading note now says which is which by the printed line each follows: "'Deferred income taxes' is printed twice with no section to tell the copies apart: (1) is the one after 'Depreciation', (2) the one after 'Other liabilities'." It sits in the report's "How the filing was read" and the audit's reader notes. A copy at the top of the statement is "the first line". Names given by section are unchanged.

Boundary cases:
- Two unnamed copies get the note.
- Copies each in their own section keep their section names, with no note.

**C4, a line among costs that is a credit in one year only.** A line outside the filing's revenue that adds to income is read among the costs with its sign turned, as before; the values and status are unchanged. The note calls it "a credit" only when it adds to income in every compared year it prints. When it reduces income in a compared year (a loss that year), the note names the years each way: "Read 'Other income, net' among costs with its sign turned: it adds to income in FY2025 and reduces it in FY2024, and the filing's revenue is 'Net sales' (us-gaap:Revenues), which it is not part of." The check runs on the two compared values, after the comparison pair is chosen, so a third year the statement prints doesn't change it. The audit note becomes "Labeled ... as expense, among costs with its sign turned". The zero-line filter (Decision 41) recognises both wordings.

Boundary cases:
- +50 and +40 keep "a credit among costs" (the existing test).
- +50 and -40 take the new wording.
- A line that reduces income in both compared years says "it reduces income in FY2025 and FY2024".

**X31, a Percent cell Excel shows as a percentage.** Excel stores 40% as 0.4 and shows it as 40% under a format such as `0.0%`. On a Percent row, a cell whose number format shows a percentage is read as the percentage Excel shows, so 0.4 becomes "40%". The value is the stored value times 100, exactly, with a Fraction oracle. It then reads like a typed "40%", whatever `--percent-values` says. That flag goes on governing bare rates in General or number formats, as before. Both readers do this: FP&A intake (`_process_raw_table`, which the chat also uses) and the measure path (`read_comparison_input`). Each cell read so gets a note: "Gross margin: read Budget and Actual as the percentages Excel shows (number format '0.0%')." The rules are unchanged, since this is how a row reaches them (rules file 7). A Currency row under a percent format still stops as before (R2), and the path did not exist in 0.2.0.

Boundary cases:
- `0.0%` cells read as 40% and 42.5% under `points`, `fractions` and no flag; before the fix, `points` gave 0.4%.
- A cell in General beside a `0.0%` cell stays a bare rate, so the flag decides it.
- 0 reads as 0%, and a negative stored rate keeps its sign.

**X35, the period a title names, offered as a chip.** When the chat asks for the reporting period and the file's title rows name one, the question offers it as a chip and says where it came from: "Your file's title says **Q3 2026**: choose it below, or type a different period." The question itself is unchanged, and nothing is chosen for the analyst; a chip is sent as if typed. Up to three distinct periods are offered, in the order the title prints them. The forms read are:
- a duration ended on a date: "Nine months ended September 30, 2026"; "For the period ended September 30, 2026" offers "Period ended September 30, 2026";
- a quarter: "Q3 2026", "Q3 FY2026" or "FY2026 Q3";
- a half: "H1 2026";
- a fiscal year: "FY2026";
- a month and year: "October 2026".

All four places that ask for the period use this. The CLI still requires `--period`, because changing a CLI default is a STOP-ASK.

Boundary cases:
- A title naming no period offers no chips, and the question reads exactly as before.
- "Q3 FY2026" is one chip, not "Q3 FY2026" and "FY2026".
- Clicking "Period ended September 30, 2026" sets that whole period. The typed-period cleaner used to drop a leading "period" there, leaving "ended September 30, 2026", so it now keeps "period" when "ended" or "ending" follows. "period is Q3 2026" still reads as "Q3 2026".

**X36, lines the comparison file lacks, offered as 0.** The chat refuses a two-file join with a line in the actuals file that the comparison file lacks. That refusal now offers the reading the single-file path offers for a blank budget: a chip "Treat them as 0 (unbudgeted)" ("not in forecast", "new this period" for those bases). The refusal text keeps its list of lines, and its last sentence becomes "Choose **Treat them as 0 (unbudgeted)** to read them with a budget of 0, or upload a corrected file." Nothing is read as 0 until the analyst chooses it.

Once chosen, each such line joins with a comparison figure of 0, and the reader notes say: "Read 1 line in 'act.csv' but not in 'bud.csv' as 0 (unbudgeted): 5040 (Travel)". In the join record, that line's `comparison_line_item` is `""`, since there is no line in the other file. The schema is unchanged (a string), and `docs/audit-contract.md` gains one sentence saying so.

Boundary cases:
- A line in the comparison file but not in the actuals still refuses with no chip, because reading an actual as 0 is not offered on either path.
- When lines are missing both ways, the refusal is as before, with no chip.
- Limit, benchmark, target, consensus, estimate and guidance get no chip, since a zero limit or consensus would invent a figure. Today a half can carry only a budget, forecast or prior period, so the guard in `join_results` is tested directly.
- Uploading a corrected file instead clears the offer and joins as usual.
- The CLI's `--compare-file` refusal is unchanged.

**X42, intake's notes in the measure report and audit.** On the measure path (an `AudienceConfig` run, which a Measure column, a non-FP&A preset or a Percent row selects), the notes on how the file was read come from one function, `measures.metric_inferences`. It feeds the report's "How the file was read", the audit's `inferences` and the CLI's `[measure intake]` lines.
- Assisted intake's notes (its visible transformations) now reach that function through a new `AudienceConfig.source_notes`, set by the CLI's assisted path and by the chat. They come first, in intake's order.
- An intake note that only restates a row note the function writes itself is dropped, so nothing is said twice: "read Measure as", "read Better as/to" and "read % values as percentage points".
- "Read bare Percent values as points." (or fractions) now appears only when a Percent row holds a bare rate: a value in its Actual or comparison column without a % sign.
- No figure, status or contract changes, and the audit schema is unchanged, because `inferences` is a list of strings. The audit's `audience` object names its fields one by one, so the new field doesn't appear in it.

Boundary cases:
- X31's file (both cells formatted `0.0%`) under `--percent-values points` lists "Gross margin: read Budget and Actual as the percentages Excel shows (number format '0.0%')." in the report and the audit, and no bare-rate line.
- The same file with Budget left in General keeps the bare-rate line, since that one cell is bare.
- A run with no assisted intake (strict input) adds nothing.

**X41, Buffer and Tolerance under a unit caption.** `docs/financial-rules.md` states a Buffer and a Tolerance "in the row's unit". So when a caption (or a mapping's declared unit) scales a Currency row's amounts, its Buffer and Tolerance are scaled by the same exact multiplication, in the same place, on both readers: intake's `scale_rows_by_unit` and the comparison path's `_apply_unit_caption`. The cell is read with the engine's own `parse_decimal`; one it can't read is left as it was, for the engine to refuse as before. The scaling note names them: "Amounts scaled from thousands (x1,000), Buffer included." (or "Tolerance included", or "Buffer and Tolerance included"); a file with neither keeps the note word for word. Percent, Per Share, Count and Multiple rows stay unscaled, as their amounts do. When the cells already hold full amounts (R2's display check), nothing is scaled, Buffer and Tolerance included. Every financial rule is unchanged: the values now reach the rules in the unit the rules assume.

Boundary cases, at the scaled values, in thousands:
- Limit 100, Max, Buffer 10: Actual 90 leaves headroom $10,000.00, equal to the buffer, so Near; Actual 89.999 leaves $10,001.00, so Within; the X41 file (Actual 95) is Near.
- Benchmark 100, Higher, Tolerance 10: Actual 110 is In line; 110.001 is Higher than benchmark.
- Target 100, Tolerance 10: Actual 110 is On target; 110.001 is Over.
- A Percent row's Tolerance of 1 under the same caption stays 1 percentage point.
- Buffer 10.5 becomes exactly 10,500 (Fraction oracle).

**M4, a filing column's duration in display text only.** An Inline XBRL column label names a duration by its end month ("Mar 2026"). That label is a key: it is the comparison label, the audit's `comparison.label` and the long outputs' label. So it stays as it is. The duration goes into a separate display name, "3 months ended Mar 2026", built by the reader for each duration column whose label names only its end month. A fiscal-year label ("FY2025") and a balance sheet's instant ("Mar 2026", as of that day) keep their label as their name, and a 12-month duration labelled by its end month (Decision 39's 52/53-week years) reads "12 months ended Jan 2026".

Where the name shows:
- the statement's note "Read the column for the 3 months ended 2026-03-28 as Mar 2026";
- intake's "Comparing 3 months ended Mar 2026 against 3 months ended Mar 2025 (prior period).";
- the chat's "How I read your file" rows "Prior Period (3 months ended Mar 2025)" and "Actual (3 months ended Mar 2026)";
- the report headings, through a new display-only `AnalysisConfig.comparison_name`, which the CLI's paths and the chat set from intake and which defaults to `None`, so every contract run renders as before.

The audit records `comparison.label` as "Mar 2025", as before. `comparison_name` is in no audit field and no fingerprint (the fingerprint hashes the record, not the config), and the long CSV and JSONL are unchanged; a test asserts all three.

Boundary cases:
- The 3-month and 6-month income statements of the same 10-Q show different names for the same label.
- An annual filing's "FY2025" columns show no "months ended".
- A strict or spreadsheet run has no names and renders exactly as before.

## Existing assertions to edit

| Test | Assertion | Reason |
|---|---|---|
| `tests/test_chat_hardening.py::test_unmatched_questions_on_a_big_file_stay_fast` (7 cases) | `assert time.perf_counter() - start < 0.5` is replaced by the work counts of Decision 7. `assert response.text` stays. | T1. The bound failed under load. Measured here: 5 of 7 cases failed on each of two runs beside 64 CPU-bound processes. The work counts pin the same fix without a clock. |
| `tests/test_interface_design.py::test_status_words_mirror_the_servers_map` | the page shows `'Unclassified'` as `{"word": "Unclassified", "tone": None}`; it becomes `{"word": "Not yet labeled", "tone": None}` | X27 (approved at STOP 1). The test checks that the page's word map mirrors the server's `status_label`, and X27 changes that label. Its mirror check stays as it is. |
| `tests/test_ixbrl.py` (the declared-entity refusal, line 200) | the expected text "'hal-20250927.htm' declares an XML entity or document type subset, which this reader refuses. " becomes "'hal-20250927.htm' declares entities of its own, which filings on EDGAR don't, so this reader refuses it. " | M6: "XML" is a forbidden word in the rules file; the refusal and its fix are otherwise unchanged |
| `tests/test_excel_archive_hardening.py::test_a_dtd_after_a_long_prolog_comment_is_still_refused` and `::test_a_dtd_straddling_a_read_boundary_is_still_found` | `pytest.raises(ValueError, match="DTD")` becomes `match="declares entities of its own"`; each test still asserts the declaration is refused | M6: "DTD" is a forbidden word in the rules file |
| `tests/test_pdf_intake.py::test_unknown_statement_lists_the_ones_found` | the expected refusal gains its last sentence, " Choose one of those statements." | M6: the refusal named the statements but gave no step; the same refusal for a filing already ends so (intake.py, the Inline XBRL path) |
| `tests/test_filing_headlines.py::test_consecutive_52_53_week_years_are_named_by_their_end_month_not_as_a_gap` | "Read the column for 2026-01-03 as Jan 2026" becomes "Read the column for the 12 months ended 2026-01-03 as Jan 2026"; the label "Jan 2026" and the no-"FY2026" assertion stay | M4: the note names a duration labelled by its end month |
| `tests/test_multi_audience_api.py::test_new_public_signatures_and_legacy_constructors` and `tests/test_multi_audience_measures.py::test_existing_public_constructors_and_functions_keep_their_parameters` | `AnalysisConfig`'s pinned parameters gain a trailing `"comparison_name"`; the seven existing names keep their order | M4: a trailing keyword with a default, so every existing call, positional or by name, works as before |

## Phase 0 figures (Python 3.11.16, macOS, 10 cores)

Gates, summary lines as printed:

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed! |
| `mypy --strict src/variance_agent scripts deterministic_conditioning` | Success: no issues found in 71 source files |
| `compileall -q src tests scripts deterministic_conditioning` | exit 0 |
| `pytest -q` | 2505 passed in 48.53s |
| `pip check` | No broken requirements found. |
| `build` / `twine check` / `check_distribution.py` | built `variance_analysis_agent-0.3.0.tar.gz` and `-py3-none-any.whl`; both PASSED; "Wheel/sdist contents, license, Python support, and entry point verified" |
| minimal install: `check_installation.py --without-excel --without-pdf`, `pip check` | "Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified"; No broken requirements found. |
| Windows output-contract job | not runnable here; covered by CI only |

Size table, measured by `.scratch/size_table.py` (an `ast` walk, counting from the `def` line). It matches the prompt's section 1: 732 functions in `src/`, 36 over 80 lines, 9 over 150. `chat/handlers.py` has 5,082 lines and `intake.py` 3,627.

| Function | File | Lines |
|---|---|---|
| `_process_raw_table` | `intake.py` | 477 |
| `_run` | `cli.py` | 348 |
| `_handle_what_if` | `chat/handlers.py` | 243 |
| `build_audit_record` | `audit.py` | 232 |
| `analyze_rows` | `analysis.py` | 223 |
| `_handle_compare` | `chat/handlers.py` | 171 |
| `_read_excel_bytes` | `intake.py` | 170 |
| `read_comparison_input` | `comparisons.py` | 161 |
| `shape_income_statement` | `statement_shape.py` | 155 |

Contracts: 19 files in `tests/fixtures/contracts/`. Schemas: `audit-1.0` to `audit-1.9`. Docs root: 17 Markdown files.

T1 under load: `pytest tests/test_chat_hardening.py::test_unmatched_questions_on_a_big_file_stay_fast` beside 64 runs of `.scratch/burn.py`, a 150 s busy loop. Both runs printed "5 failed, 2 passed" with, for example, `assert (1110104.490578166 - 1110103.815566125) < 0.5`. Beside 16 such processes, three runs passed. Unloaded, each question takes 0.04 to 0.09 s.

## Phase 1 figures

- Six auditors. Findings returned, then kept after the main session's re-run: wrong numbers 8, then 8; Maya 10, then 10; contract drift 10 plus 4 small, then 10 plus 1; code health 10, then 4 kept (6 cost items merged as X37 and X38, and F10 is no defect); exposure 8, then 8. That makes 40 X items.
- Test strength: 3 of 25 mutants survived; the baseline for T2.
- Maya's scorecard over 25 fictional files:
  - 6 dead ends.
  - 3 runs reach an analysis with a wrong figure (f14, f19, f23).
  - One manual step (typing the period) in 16 of the 18 runs that reach an analysis.

## Looking at the outputs, Phase 0 and 1

- Report: no output changed. The re-run LTM report with `--layout` (`.scratch/rerun-contract/ltm_layout.md`) puts quarter figures under an "LTM Mar 2026" title.
- Workbook: unchanged. A filing's `--layout --xlsx` workbook carries totals the filing does not print.
- Chat reply: unchanged. The Sep-26 reply for f23 names Sep-26 and maps the YTD columns in the same summary.

## Phase 2 figures (end of phase, `6851252`)

Gates:
- `ruff check .`: All checks passed!
- `mypy --strict`: Success: no issues found in 71 source files.
- compileall: exit 0.
- `pytest -q`: 2630 passed in 52.12s, up from 2505.
- `pip check`: No broken requirements found.
- build, twine (2 PASSED) and `check_distribution.py`: verified.
- Minimal install: "Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified"; `pip check` clean.
- Contracts and schemas: `git diff main -- tests/fixtures/contracts schemas` is empty, and the contract tests pass (104 passed).

Items:
- Done: X1, X2, X3, C2, C5, X4, X5 and X30, X6, X7, X8, C1.
- C3: investigated, no code change; its message moves to Phase 3 as C3m.
- Asked: X41 (STOP-ASK).

## Looking at the outputs, Phase 2

- Report: a "($ in thousands)" earnings workbook now reports Revenue $1,234,000.00 against $1,200,000.00, Beat, the same as the FP&A path.
- Workbook: the comparison workbook for the same file shows $1,234,000.00 on both its Earnings and Measures sheets. Its cells hold formatted text, not numbers, which is existing behaviour and something for N1 to keep in mind.
- Chat reply: an on-budget file's board memo reads "Operating Profit finished at **$75,000.00**, **in line with** the planned budget of **$75,000.00**. Operating margin **held** at **50.0%** (+0.0 pts)."

## Phase 3 figures (end of phase, `5bd1a9a`)

Gates:
- `ruff check .`: All checks passed!
- `mypy --strict src/variance_agent scripts deterministic_conditioning`: Success: no issues found in 72 source files.
- compileall: exit 0.
- `pytest -q`: 2751 passed in 58.63s, up from 2630 at the end of Phase 2.
- `pip check`: No broken requirements found.
- build (sdist and wheel), twine (2 PASSED) and `check_distribution.py`: "Wheel/sdist contents, license, Python support, and entry point verified".
- Minimal install, the new wheel reinstalled offline into `.scratch/minimal-env`: "Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified"; `pip check` clean.
- Contracts and schemas: `git diff main -- tests/fixtures/contracts schemas` is empty; `pytest -k contract` gives 181 passed. That selection is wider than Phase 2's count of 104, which named the contract files alone.
- Windows output-contract job: covered by CI only.

Size table, by the same `ast` walk: 768 functions in `src/`, 37 over 80 lines and 10 over 150, against Phase 0's 732, 36 and 9. `_process_raw_table` grew from 477 to 534 lines across Phases 2 and 3. `_handle_executive_memo` (152) is the new function over 150. `chat/handlers.py` has 5,260 lines and `intake.py` 3,939.

Items:
- Done in Phase 3: X10, X12 to X29 (X24 with its merged date band left open), M1, M2, M3, M5, M6, C3m, C4, X31, X35, X36.
- Asked: M4 (STOP-ASK). New at STOP 2: X42.
- Screenshots: 91, in `docs/improve/evidence/phase-3/`, 26 scenarios, light theme, desktop and mobile. The harness `shots_phase3.py` dry-runs each scenario through the handlers first (`--check`). The chat servers it started were stopped.

## Looking at the outputs, Phase 3

- Report: X31's workbook (Gross margin stored 0.4 and 0.425 under `0.0%`), run with `--percent-values points`, reports "| Gross margin | Percent | 40% | 42.5% | 250 bps | N/A (rate) | F | Yes |". The figures are right. Its "How the file was read" section lists the measure path's own notes, not intake's, so the new "read Budget and Actual as the percentages Excel shows" note reaches the chat summary and stderr only. Neither the Markdown report nor the audit's `inferences` records it, so neither traces 40% back to the stored 0.4. The report and audit also say "Read bare Percent values as points." when no bare value was read. Measure reports have never carried intake's notes, so this is a provenance gap, not a wrong figure. It is raised at STOP 2 as X42, since changing what an existing report or audit says needs approval.
- Workbook: the same run's `--xlsx` Measures sheet holds "40%", "42.5%" and "250 bps" as formatted text, matching the report. These measure cells are text, as Phase 2 noted, which N1 should keep in mind.
- Chat reply: after X36's chip, the joined summary reads "Joined 'bud.csv' to 'act.csv' by 'GL Account': 6 lines, 5 in both files" and "Read 1 line in 'act.csv' but not in 'bud.csv' as 0 (unbudgeted): 5040 (Travel)", so the summary says which line was read as 0 before the analyst confirms.

## Revert proofs

| ID | Fix reverted | Test run | Result with the fix reverted |
|---|---|---|---|
| T1 | The test checks `1fc32b8`'s fix, so the proof re-introduces that fix's two costs one at a time. (a) `_SUGGEST_MAX_ITEMS = 10**9`: the suggestion cap removed. | `pytest tests/test_chat_hardening.py -k stay_fast` | 3 failed, 4 passed: `assert 120000 == 30000`, difflib comparisons growing with the file |
| T1 | (b) `_item_in_sentence` ignores the caller's `named` and recomputes the scan: an extra pass over the names. | same | 1 failed, 6 passed: `assert (80009 - 20009) <= (3 * (20000 - 5000))` |
| X1 | `_footnote_marks` and its check in `parse_assisted_decimal` removed (git checkout of `intake.py`), tests kept | `pytest tests/test_amount_forms.py` | 9 failed: `Failed: DID NOT RAISE ValueError` for each mark, and the intake test's message assertion fails |
| X2 | `_printed` and `_workbook_cells` removed (`git apply -R` of the scorecard diff), tests kept | `pytest tests/test_scorecard.py` | 3 failed: the report reads `In line \| 0.079%` instead of `12.4%`, and both refusals give `DID NOT RAISE SystemExit` |
| X3 | `_UNIT_CAPTION_RE`, `_TITLE_UNIT_RE` and their uses removed (`git apply -R`), tests kept | `pytest tests/test_pdf_intake.py -k unit_caption` | 3 failed, 3 passed: on-title and unparenthesised read `1250.4`; the long title caption gives "We couldn't find an income statement" |
| C2 | `_apply_unit_caption` and the display capture removed from `comparisons.py` (`git apply -R`), tests kept | `pytest tests/test_comparison_captions.py` | 6 failed, 4 passed: caption-alone earnings reads `$1,234.00`, no scale note or audit `unit_scale`, no "not scaled again" note, the mixed-format earnings run does not refuse, and CSV cells stay unscaled. The passing four are the format-alone and both cases and the FP&A refusal, which held before. |
| C5 | `_fu`, `_fu_between`, `_in_line`, the zero branches and the run-rate identities removed (`git apply -R`), tests kept | `pytest tests/test_chat_zero_variance.py` | 11 failed, 5 passed: zero totals show F in the compare, run-rate and what-if tables, the sensitivity baseline is F, and every "in line" sentence is missing. The one-cent controls and the run-rate oracle pass either way, as designed. |
| X4 | `_unit_caption_re`, `_BILLIONS_RE` and the billions label removed; the old two patterns restored (`git apply -R`), tests kept | `pytest tests/test_unit_scaling.py` | 23 failed, 20 passed: the 20 missed forms read 1, "in M&A" and "in M." read 1,000,000, and the billions file is unscaled |
| X5, X30 | `currency_conflict`, the marked-cell and statement-currency records, the CLI, API and chat checks, and the LTM and metrics currency removed across eight modules (`git apply -R`), tests kept | `pytest tests/test_currency_conflicts.py` | 9 failed, 4 passed: euro, pound and filing-currency runs all exit 0 under the wrong currency, the chat analyses EUR cells as USD, and the euro LTM table prints `$4,300,000,000.00`. The four that pass read in their own currency or are unmarked. |
| X6 | the chosen-pair override after `detect_comparison_columns` removed (`git apply -R`), tests kept | `pytest tests/test_period_choice.py` | 2 failed, 3 passed: choosing Sep-26 reads 500,000 / 540,000 (the YTD cells), and the chat summary maps 'Budget YTD'. The no-choice and one-pair controls pass either way. |
| X7 | `_signed_profit_lines` and its use in the flip removed (`git apply -R`), tests kept | `pytest tests/test_signed_profit_lines.py` | 4 failed, 1 passed: Gross Profit and Net Income stay among the lines with their credit sign, the chat totals are wrong, and the off-by-one line keeps -480,001. The presentation-signed control passes either way. |
| X8 | `_refuse_main_path_inputs`, the comparison path's multiple threshold, `_refuse_filing_workbook` there, and the filing headline in `render_measure_report` removed (`git apply -R`), tests kept | `pytest tests/test_comparison_path_guards.py` | 7 failed, 1 passed: LTM plus `--layout` or `--long-output` exits 0 with quarter figures, the limit run gives "No Limit column found", `--multiple-threshold` is ignored, the 10-K report sums Total Revenue, and the filing workbook is written. The plain LTM control passes either way. |
| C1 | the computed-column skip in strict's formula check removed (`git apply -R`), tests kept | `pytest tests/test_excel_unsaved_formulas_strict.py` | 1 failed, 4 passed: strict stops on "Var $" formulas that assisted reads. The amount-column and "Notes" stops hold either way. |
| X10 | the `not args.no_browser` condition removed (`git apply -R`), test kept | `pytest tests/test_cli_hosted_detection.py` | 1 failed, 5 passed: with RENDER set, `--chat --no-browser` binds 0.0.0.0 |
| X12 | the body deadline and chunked read removed (`git apply -R`), tests kept | `pytest tests/test_server_hardening.py -k "dripped or sent_whole"` | 1 failed, 1 passed: the deadline settings don't exist, and the server waits out the drip |
| X13 | the four second files removed from `_validate_output_paths` (`git apply -R`), tests kept | `pytest tests/test_cli_output_paths.py` | 4 failed, 1 passed: `-o bud.csv` overwrites the compare file, and the other three reach later checks instead of the path refusal |
| X14 | `needs_schema_19`, its use in `build_comparison_audit` and the worded refusal removed (`git apply -R`), tests kept | `pytest tests/test_comparison_audit_versions.py` | 2 failed, 1 passed: the 10-K earnings audit refuses (1.8 says use 1.9), and the 1.8 refusal still blames a workbook examination. The CSV 1.8 control passes either way. |
| X15 | the `.tsv`/`.txt` branch and the fuller list removed from `validate_input_format`, and the comparison reader's TSV case (`git apply -R`), tests kept | `pytest tests/test_tsv_input.py` | 4 failed: every case gets "Unsupported input format '.tsv'. Use CSV, JSON, XLSX, or XLSM." |
| X28 | the decode and JSON-error wrapping in `load_mapping` removed (`git apply -R`), tests kept | `pytest tests/test_cli_small_refusals.py -k mapping` | 2 failed, 1 passed: `{oops` gives "Expecting property name enclosed in double quotes...", and non-UTF-8 bytes give a decode error. The `[]` control passes either way. |
| X29 | the long outputs removed from the `--check-only` refusal (`git apply -R`), tests kept | `pytest tests/test_cli_small_refusals.py -k check_only` | 2 failed, 1 passed: `--check-only --long-output x.csv` exits 0 with "Validation passed" and writes nothing |
| X16 | the section-heading skip and its note removed (`git apply -R`), tests kept | `pytest tests/test_section_headings.py` | 1 failed, 1 passed: "Row 2, REVENUE, Actual column: the amount is blank" stops intake. The blank-cell control passes either way. |
| X17 | `.xls` removed from the chat's multi-table suffixes and from `get_workbook_sheets` (`git apply -R`), tests kept | `pytest tests/test_xls_sheets.py` | 1 failed, 2 passed: `book.xls` answers "contains a single dataset". The `.xlsx` and `.csv` controls pass either way. |
| X18 | the fallback name lists and their uses removed (`git apply -R`), tests kept | `pytest tests/test_comparison_headers.py` | 3 failed, 1 passed: "Could not find a Line Item and Actual header" for Description and YTD Actual, and the drift guard finds no lists. The Account precedence control passes either way. |
| X20 | the zero exclusion removed from the currency-cell count (`git apply -R`), tests kept | `pytest tests/test_excel_zero_section.py` | 1 failed, 1 passed: one zero Actual gives "number formats don't agree". The General control refuses either way. |
| X19, X26 | the replaced-file condition and both `initial_response` clears removed (`git apply -R`), tests kept | `pytest tests/test_server_hardening.py -k "refused_upload or start_up_reply"` | 3 failed: a refused upload gives the download a 404, and `/status` still serves the start-up reply after a new upload and after a reset |
| X21 | the whole-file and same-half branches and `_half_wording` removed from `_load_other_half` (`git apply -R`), tests kept | `pytest tests/test_chat_two_files.py` | 3 failed, 2 passed: a whole file gets "...isn't the actuals half of a pair. Run it on its own, without --compare-file.", and the same budget again gets "Could not find a header row". The join and broken-file controls pass either way. |
| X25 | the `expanduser` and the named landing path removed (`git apply -R`), tests kept | `pytest tests/test_chat_export_paths.py` | 1 failed, 1 passed: `~/r.md` creates `work/~/r.md`, and home stays empty. The relative-path control passes either way. |
| X27 | the display words, the chip's intent words and the page's word removed across four files (`git apply -R`), tests kept | `pytest tests/test_chat_not_yet_labeled.py tests/test_interface_design.py` | 3 failed, 62 passed: "Unclassified" shows in the material table and the warnings, the "Not yet labeled" chip doesn't route, and the page's word map no longer mirrors the edited assertion |
| X22 | the refusal response, the leave-out handler and route, the session field and the rule 6 pattern removed (`git apply -R`), tests kept | `pytest tests/test_chat_unreconciled_total.py` | 3 failed, 1 passed: "...Expense detail rows detail rows", the chat drops to "upload a file", and "Leave Total Opex out" does not route. The matching-total control passes either way. |
| X23 | `_HEADER_QUALIFIER`, the qualifier retry in `match_column_synonym` and the heading currency mark removed (`git apply -R`), tests kept | `pytest tests/test_header_units.py` | 10 failed, 1 passed: every qualified heading is unknown, and the file has no Budget column. The "(Q3)" control passes either way. |
| C3m | `ShapedStatement.ambiguous` and the named-line refusal removed (`git apply -R`), test kept | `pytest tests/test_statement_sign_ambiguity.py` | 1 failed, 3 passed: the shaper has no `ambiguous` record, and the refusal says "couldn't tell which lines ... adds up". The C3 pins pass either way. |
| M3 | `_BARE_YEAR_RE` and its two uses removed (`git apply -R`), tests kept | `pytest tests/test_excel_bands_and_blocks.py -k bare_year` | 3 failed: "Found more than one Actual column (Actual (column D), Actual (column F))" for both band shapes and the chosen year |
| X24 | `_two_row_header` and its use in header detection removed (`git apply -R`), tests kept | `pytest tests/test_two_row_headers.py` | 2 failed, 1 passed: "Could not find a header row with Line Item, Budget, and Actual" for the merged and unmerged two-row headers. The no-amounts control refuses either way. |
| M1 | `_statements_elsewhere` and both new refusal wordings removed (`git apply -R`), tests kept | `pytest tests/test_ixbrl_statements_elsewhere.py` | 3 failed, 1 passed: the refusal names no document and no next step. The path-characters guard passes either way. |
| M2 | `Statement.runs_on`, its marking and `_runs_on_refusal` removed (`git apply -R`), test kept | `pytest tests/test_ixbrl.py -k runs_on` | 1 failed: the statement has no `runs_on`, and the refusal is the balance-sheet check's own message |
| M5 | `_numbered_notes` and its two uses removed (`git apply -R`), test kept | `pytest tests/test_ixbrl.py -k which_is_which` | 1 failed: the reader notes don't say which numbered copy is which |
| C4 | `_credits_by_year` and its call removed (`git apply -R`), tests kept | `pytest tests/test_ixbrl.py -k "loss_in_one_year or only_in_a_year_not_compared or credit_on_the_cost_side"` | 2 failed, 1 passed: both new cases still say "as a credit among costs"; the same-sign credit test passes either way |
| X31 | `percent_shown`, its use in `_process_raw_table` and `_percent_as_shown` removed (`git apply -R`), tests kept | `pytest tests/test_percent_formats.py` | 14 failed: `points` reads 0.4% and 0.425%, no flag stops with "bare rate in Budget needs --percent-values", and the cells stay Decimal 0.4 |
| X35 | `title_periods`, `_ask_period` and the cleaner's look-ahead removed (`git apply -R`), tests kept | `pytest tests/test_chat_period_chips.py` | 16 failed, 3 passed: no chips, no "title says" line; the 3 that pass are the no-period and lead-in guards |
| X36 | `unbudgeted_as_zero`, `ZERO_OFFERED`, the session field and the chat offer removed (`git apply -R`), tests kept | `pytest tests/test_join_unbudgeted.py` | 6 failed, 2 passed: `join_files` takes no such option, and the chat refuses with "run again" and no chip; the 2 that pass are the unchanged-refusal guards |
| M6 | every source rewording removed (`git apply -R` of the `src` diff), tests and script kept | `pytest tests/test_message_inventory.py`; `python scripts/message_inventory.py` | 1 failed, 5 passed: the gate lists 44 messages; the script prints 235 seen, 10 with jargon, 37 errors with no fix, 44 failing, matching the worktree's before |
| X42 | `source_notes`, `_bare_rate` and their wiring removed (`git apply -R`), tests kept | `pytest tests/test_measure_source_notes.py` | 4 failed, 1 passed: the report and audit lack the format note and keep "Read bare Percent values as points."; the strict-run guard passes either way |
| X41 | `UNIT_DECLARATIONS`, `scaled_declaration`, `scaling_note` and their uses removed (`git apply -R`), tests kept | `pytest tests/test_caption_buffers.py` | 13 failed, 1 passed: Buffer and Tolerance stay $10.00, so the X41 file reads Within, and 110 against a benchmark of 100 reads Higher than benchmark; the Percent-row guard passes either way |
| M4 | `period_name`, `Statement.names`, `period_names`, `comparison_name` and their uses removed (`git apply -R`), tests kept | `pytest tests/test_period_names.py` | 7 failed: the notes say "Read the column for 2026-03-28 as Mar 2026", the chat reads "Prior Period (Mar 2025)" and the report heading has no duration |
| T1 | Load, the reason for the change: the old test beside 64 CPU-bound processes, then the new one. | `pytest ...::test_unmatched_questions_on_a_big_file_stay_fast` | old test: "5 failed, 2 passed" on each of 2 runs; new test: "7 passed" on each of 2 runs |

## Path existed in 0.2.0

The repository has no release tag. Released 0.2.0 is taken as `5e288bb` (2026-10-02), the last commit whose `version.py` reads `0.2.0`; the next commit, `ebda726`, sets `0.3.0`. Its `src/variance_agent/` holds only `__init__`, `analysis`, `audit`, `cli`, `currencies`, `models`, `numeric`, `output`, `parsing`, `report` and `version` (`git ls-tree --name-only 5e288bb src/variance_agent/`). There is no `comparisons.py`, `intake.py`, `excel.py`, chat or filing reader.

- **C2**: not in 0.2.0. `comparisons.read_comparison_input`, the earnings preset and `api.analyze_file` came later.
- **C3**: not in 0.2.0. There was no filing reader.
- **C1**: `parsing.py` existed at `5e288bb`, but the uncached-formula stop it relaxes (R4) came with 0.3.0, and the fix changes a refusal, not a figure.
- A finding counts as on a 0.2.0 path only when the cause sits in one of the eleven modules above, on a CLI path that 0.2.0 already offered.

Post-T1 suite: 2505 passed in 47.31s (count unchanged).

## Looking at the outputs

One sentence each per phase, on one report, one workbook and one chat reply the phase changed.
