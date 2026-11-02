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
| C3m | 3 | todo | | the refusal names the line whose sign the printed figures can't tell |
| X30 | 2 | done | see `fix(X5, X30)` | with X5 (one rule, one commit) |
| X41 | 2 | asked | | STOP-ASK: [evidence/stop-ask-buffer-scale/ASK.md](evidence/stop-ask-buffer-scale/ASK.md) |
| X9 | — | open | | owned by `claude/per-visitor-sessions-d54fc9` (Decision 12) |
| X10 | 3 | done | see `fix(X10)` | `src/variance_agent/cli.py`, `README.md`, `tests/test_cli_hosted_detection.py` |
| X11 | — | open | | owned by the per-visitor-sessions work (Decision 12) |
| X12 | 3 | done | see `fix(X12)` | `src/variance_agent/chat/server.py`, `tests/test_server_hardening.py` |
| X13 | 3 | done | see `fix(X13)` | `src/variance_agent/cli.py`, `tests/test_cli_output_paths.py` (new) |
| X14 | 3 | todo | | |
| X15 | 3 | todo | | |
| X16 | 3 | todo | | |
| X17 | 3 | todo | | |
| X18 | 3 | todo | | |
| X19 | 3 | todo | | |
| X20 | 3 | todo | | |
| X21 | 3 | todo | | |
| X22 | 3 | todo | | |
| X23 | 3 | todo | | |
| X24 | 3 | todo | | |
| M1 | 3 | todo | | name the second document only (Decision 12) |
| M2 | 3 | todo | | |
| M3 | 3 | todo | | |
| X25 | 3 | todo | | |
| X26 | 3 | todo | | |
| X27 | 3 | todo | | |
| X28 | 3 | todo | | |
| X29 | 3 | todo | | |
| X31 | 3 | todo | | |
| M4 | 3 | todo | | |
| M5 | 3 | todo | | |
| C4 | 3 | todo | | |
| M6 | 3 | todo | | |
| X35 | 3 | todo | | |
| X36 | 3 | todo | | |
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

## Existing assertions to edit

| Test | Assertion | Reason |
|---|---|---|
| `tests/test_chat_hardening.py::test_unmatched_questions_on_a_big_file_stay_fast` (7 cases) | `assert time.perf_counter() - start < 0.5` is replaced by the work counts of Decision 7. `assert response.text` stays. | T1. The bound failed under load. Measured here: 5 of 7 cases failed on each of two runs beside 64 CPU-bound processes. The work counts pin the same fix without a clock. |

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
