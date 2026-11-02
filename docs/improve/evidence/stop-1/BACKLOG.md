# STOP 1: ranked backlog

Phase 1 ran six auditors on 2026-11-02, launched together. None of them edited the tree. Their lenses: wrong numbers, dead ends for Maya, contract drift, code health, test strength, and exposure. Every finding below was re-run by the main session at `63162aa` before it counted, and every one reproduced. The reproduction scripts and their fictional inputs live in the git-ignored `.scratch/` folder, one subfolder per lens. [audit-findings.md](audit-findings.md) gives each item's cause, its command and what it showed.

**Ranking.** Items are ranked by severity, then by cost: S is a few hours, M about a day, L more than a day. The severity order is wrong number, exposure, dead end, misleading, unpinned, cost (PLAN.md Decision 8).

**Contracts.** The 19 contract files pin the strict CLI's report and audit for JSON inputs. No item below changes any of them. The Contract column says "none" unless another pinned output is touched.

**Release 0.2.0.** No item's cause sits on a path that shipped in release 0.2.0 (`5e288bb`; PLAN.md, "Path existed in 0.2.0"). So no item calls for halting at once.

| Rank | ID | Source | Severity | Description | Cost | Phase | Contract |
|---|---|---|---|---|---|---|---|
| 1 | X1 | wrong-number audit | wrong number | A footnote mark or circled digit is folded into the amount: `950¹` reads as 9,501 (assisted CLI and chat). Strict mode refuses the same cell. `intake.py:623` | S | 2 | none |
| 2 | X2 | wrong-number audit | wrong number | Scorecard weights from an `.xlsx` cell formatted `0.00%` come out 100 times too small (12.4% shows as 0.124%). `scorecard.py:31-32` | S | 2 | none |
| 3 | X3 | wrong-number audit | wrong number | A PDF's "(In millions)" on the title line, or without parentheses, is dropped, and $1,250.4M reads as $1,250.40. `pdf_tables.py:399, 413-421` | S | 2 | none |
| 4 | C2 | analysts REPORT | wrong number | The earnings and quant paths apply no unit caption. Re-run: a caption alone reads $1,234.00 against FP&A's $1,234,000.00, with no note. A scaling format alone, or with the caption, is right on both paths. | S | 2 | none |
| 5 | C5 | ui REPORT | wrong number (presentation) | Zero is counted Favorable or "beat". The record names the what-if table and the executive memo; the same `>= 0` pattern is in **8 chat handlers**: budget utilization, compare, what-if, sensitivity, run-rate, executive memo, greeting, profitability (`handlers.py:3122-4809`). | S | 2 | none |
| 6 | X4 | wrong-number audit | wrong number | The caption detector misses `(£000)`, `(€000)`, `(000)`, `($MM)` and "in billions", so those amounts read 1,000 or 1,000,000 times too small. It also fires on "Costs incurred in M&A review", multiplying every amount by 1,000,000. `intake.py:693-694` | M | 2 | none |
| 7 | X5 | code-health audit | wrong number | Assisted intake never checks a cell's currency symbol: `€100` under `--currency USD` reports $100.00 (strict mode refuses it). Same in the chat. `intake.py:3113, 3138` | M | 2 | none |
| 8 | X6 | Maya audit | wrong number | In a file with Sep-26 and YTD columns, choosing "Sep-26" analyses the Budget YTD and Actual YTD columns under a Sep-26 label. `intake.py:1076-1110` | M | 2 | none |
| 9 | X7 | Maya audit | wrong number | In a signed ledger, Gross Profit and Net Income keep their credit sign and become line items, so totals go wrong ("Total Expenses: -$32,000.00 vs. -$50,000.00"). Neither the labeling chips nor Skip recovers. `intake.py:3265-3294` | M | 2 | none |
| 10 | X8 | contract audit | wrong number | Adding `--layout`, `--long-output` or another export flag sends a run down the comparison path, which drops `--ltm-from` (quarter figures under an "LTM" title), `--compare-file`, `--metrics`, `--panel`, `--multiple-threshold` and the filing guards (a filing workbook with totals it does not print). The limit, benchmark and target dead ends share this cause. `cli.py:408-411, 714-823` | M | 2 | none |
| 11 | C1 | analysts REPORT | wrong number | Strict and assisted intake differ on uncached formulas in computed columns. | M | 2 | none |
| 12 | C3 | analysts REPORT | wrong number | A pre-tax subtotal is refused over a $1M gap that should sit inside R5's rounding interval. A change to the interval is a STOP-ASK. | M | 2 | none |
| 13 | X9 | exposure audit | wrong number + exposure | **Hosted mode (live on Render) gives every visitor one shared session.** Visitor B reads, exports or resets visitor A's analysis, and A's answers apply to B's file. `server.py:181, 483-484`. Open branch `claude/per-visitor-sessions-d54fc9` targets this (question 3). | L | ask | none |
| 14 | X10 | contract audit | exposure | An undocumented `RENDER` environment variable binds `--chat` to 0.0.0.0, overriding `--no-browser`. `cli.py:332` | S | 3 | none |
| 15 | X11 | exposure audit | exposure | Staged downloads sit in one process-wide dict under guessable names (`variance_report_q3_2026.md`). Any visitor can fetch any other visitor's file with a GET. `server.py:50, 276-295` | M | 3, or with X9 | none |
| 16 | X12 | exposure audit | exposure | A body that drips one byte every 10 s holds the single-threaded server for as long as it lasts: another client waited 60 s. The 15 s timeout applies per read. `server.py:189-191, 410` | M | 3 | none |
| 17 | X13 | contract audit | dead end (data loss) | `-o` can overwrite the `--compare-file`, `--ltm-from`, `--metrics` or `--panel` input; it exits 0 and the input is gone. `cli.py:301-318` | S | 3 | none |
| 18 | X14 | contract audit | dead end | A filing on the comparison path with `--audit-json`: schema 1.8 says to use 1.9, and 1.9 says it requires 1.8. `audit.py:319`, `comparisons.py:288` | S | 3 | none |
| 19 | X15 | contract audit | dead end | The CLI refuses `.tsv`, which the contract documents. The refusal lists formats that leave out `.xls`, `.pdf` and `.htm`, all of which work. `parsing.py:271-272` | S | 3 | none |
| 20 | X16 | Maya audit | dead end | Section heading rows (REVENUE, OPERATING EXPENSES) are reported as blank amounts to fill in. `intake.py:2816, 2843-2846` | S | 3 | none |
| 21 | X17 | code-health audit | dead end | Chat sheet switching fails for `.xls`: "a single dataset". The suffix sets are written about 15 times. `handlers.py:516`, `parsing.py:392` | S | 3 | none |
| 22 | X18 | code-health audit | dead end | The header synonyms have drifted: `Description` works with one basis but not with `--compare-to budget,forecast`. `comparisons.py:391, 502` vs `intake.py:157-173` | S | 3 | none |
| 23 | X19 | exposure audit | dead end | A failed upload deletes the exports of the analysis that is still current; the Download link gives 404. `server.py:357` | S | 3 | none |
| 24 | X20 | wrong-number audit | dead end | A thousands caption over an Accounting format stops the run when one cell is zero (the `"-"` section), and the message names the cells that agree. `number_formats.py:46-82`, `intake.py:3364` | S | 3 | none |
| 25 | X21 | Maya audit | dead end | After a budget-only upload, every later file is treated as the actuals half, with command-line wording ("without --compare-file") and no way out on screen. `handlers.py:548, 643-646` | M | 3 | none |
| 26 | X22 | Maya audit | dead end | A subtotal's rounding gap shows only after setup, garbled ("detail rows detail rows") and with no fix chip, then drops back to "upload a file". `intake.py:3434-3490, 3578-3588` | M | 3 | none |
| 27 | X23 | Maya audit | dead end | Amount headers carrying a unit or currency ("Budget ($000)", "Budget (USD)") are not recognised: 6 of 12 common forms fail. `intake.py:554-590` | M | 3 | none |
| 28 | X24 | Maya audit | dead end | A two-row header (a band over Budget and Actual) is refused, and a merged date band gives "Could not determine period order for Sep 2026, Sep 2026." This sits next to M3. `intake.py:1047-1110, 1339` | L | 3 | none |
| 29 | M1 | analysts REPORT | dead end | A filing whose statements sit in a second Inline XBRL document refuses with no next step (question 2). | S (name) or L (read) | 3 | none |
| 30 | M2 | analysts REPORT | dead end | A statement continued in an untitled table is not joined, and its refusal can misstate the cause. | M | 3 | none |
| 31 | M3 | analysts REPORT | dead end | Bare-year bands (`2025` / `2026` over Budget and Actual) do not take the period-band path. | M | 3 | none |
| 32 | X25 | exposure audit | misleading | `export report ~/x.md` reports "written to ~/x.md" but creates a folder literally named `~` in the working folder. `rm -rf ~` would then delete the home folder. `handlers.py:2610, 2636` | S | 3 | none |
| 33 | X26 | exposure audit | misleading | The start-up file's first reply is still served after that file is reset or replaced, so a reload shows it as current. `server.py:264-271, 485` | S | 3 | none |
| 34 | X27 | Maya audit | misleading (jargon) | "Unclassified" reaches Maya in table cells, a chip, a heading and the warnings. `responses.py:83-94`, `handlers.py:1526, 2975` | S | 3 | none |
| 35 | X28 | contract audit | misleading | A mapping file that is not valid JSON gives a raw parser error, though the contract promises "Mapping file ...". `mapping.py:203` | S | 3 | none |
| 36 | X29 | contract audit | misleading | `--check-only --long-output` exits 0 and writes nothing; the contract says those flags cannot be combined. `cli.py:356` | S | 3 | none |
| 37 | X30 | wrong-number audit | misleading | A filing's currency is never compared with `--currency`: a JPY-tagged filing reads as USD, and the LTM build table hard-codes $. `ixbrl.py:425`, `ltm.py:199, 255-257` | S | 2 (with X5) | none |
| 38 | X31 | wrong-number audit | misleading | A `0.0%` Excel format on a Percent row is ignored under `--percent-values points`: 40% reads as 0.4%, with no warning. `intake.py:3187-3190` | S | 3 | none |
| 39 | X32 | wrong-number audit | misleading | At an exact tie, Var % in the workbook and the report differ by 0.1 (12.3% against 12.2%). The workbook stores the exact ratio and the report rounds half-even. `xlsx.py:331, 343` | S | 5 (question 5) | none; may edit the legacy workbook golden test |
| 40 | M4 | analysts REPORT | misleading | 10-Q column labels name the end month only. | M | 3 | none (period keys unchanged) |
| 41 | M5 | analysts REPORT | misleading | A label printed twice is numbered (1) and (2), with no word on which is which. | S | 3 | none |
| 42 | C4 | analysts REPORT | misleading | A credit-among-costs note says "credit" where one year is a loss. | S | 3 | none |
| 43 | M6 | inventory | misleading | The message inventory was hand-written at `a3ce6bb`. This builds a script, audits at the current commit and fixes failing messages. | M | 3 | none |
| 44 | X33 | contract audit | misleading (doc) | README says audit 1.0-1.8, but 1.9 is accepted. An export flag alone moves a plain run from 1.7 to 1.8; this is a doc fix only, since changing the default would be a STOP-ASK. | S | 7 | none |
| 45 | X34 | contract audit | misleading (doc) | `input-contract.md` says `--mapping` refuses limit bases; the code accepts them on purpose. | S | 7 | none |
| 46 | T2 | mutation audit | unpinned | Three of 25 mutants survived: `_read_excel_bytes`' `except Exception` (`intake.py:1995`); the earnings sheet choice in `render_comparison_xlsx` (`xlsx.py:777`); and the percent-points note test (`intake.py:3197`). | S | 6 | none |
| 47 | X35 | Maya audit | cost | The period is always typed, even when the title says "Q3 2026"; 16 of 18 runs needed it. Offer it as a chip. `handlers.py:346, 893` | M | 3 | none |
| 48 | X36 | Maya audit | cost | The two-file join refuses unbudgeted lines with "run again" and no chip. The single-file path offers "treat as 0". `join.py:93-100` | M | 3 | none |
| 49 | X37 | code-health audit | cost | Dead code: `_MISSING_MARKERS` (`intake.py:191`) and an unreachable `else` in `_handle_what_if` (`handlers.py:4107-4109`). | S | 4 | none |
| 50 | S1-S4 | prompt | cost | Split `chat/handlers.py` into a package, then split `_process_raw_table`, `cli._run`, `_handle_what_if` and `build_audit_record` ([split-proposal.md](split-proposal.md)). | L | 4 | none |
| 51 | N1 | analysts REPORT | not built | Workbook sheets for statement, limit, benchmark, target, metric and filing income comparisons. | L | 5 | none |
| 52 | N2 | analysts REPORT | not built | Wei's batch run over a folder of filings. | M | 5 | none |
| 53 | T3 | prompt | cost | `pytest --durations=20` and a look at any test over 5 s. | S | 6 | none |
| 54 | D1-D3 | prompt | cost | Move the eight history records into `docs/history/`, update the roadmap, check the README commands. | S | 7 | none |
| — | X38 | code-health audit | cost | Duplicated number grammar, missing markers, k/m/b parsing, column-letter helpers and workbook iteration (four copies with drifted messages). Proposed as **open**: recorded, not this run, except where X17 or X18 touch them. | M | open | none |
| — | X39 | exposure audit | cost | A 4.28 MiB CSV takes the hosted server from 49 to 559 MiB on `export excel` (Render free plan). Proposed as **open**. | L | open | none |
| — | X40 | exposure audit | unpinned | The hosted build installs whatever versions of the file readers' dependencies are newest (`uv.lock` is git-ignored; nothing pins Python on Render). Pinning is a dependency change, so it is a STOP-ASK; proposed **open, for the owner**. | S | open | none |
| — | T1 | analysts REPORT | unpinned (flake) | **Done** in Phase 0 (`63162aa`). | — | 0 | none |

Minor, recorded but not ranked: the "Flipped signs ... for 3 revenue lines" note counts the excluded Total Revenue row. A message body of 100,000 nested `[` gives a generic 500, with the traceback on stderr only. Costs printed in parentheses are not flipped; that follows the documented positive-cost convention.

## Questions for the owner

1. **Approve, strike or reorder** the table. By default Phase 2 takes ranks 1-12 plus X30, and Phase 3 takes ranks 14-43, except X32 and the doc items.
2. **M1:** should the run read the second Inline XBRL document through rule R10's multi-document path, or only name it in the refusal? Recommendation: **only name it**. That is the minimum the prompt sets, and it is S against L. Reading it widens the filing reader for 2 filings in Draw C.
3. **X9 and X11, the shared hosted session and downloads.** The live Render service lets any visitor see another's upload. The open branches `claude/per-visitor-sessions-d54fc9` and `feat/chat-intro-per-visitor` target this. Recommendation: **leave X9 to that work** to avoid two writers on one design, and record it here as open. Ship X11 here only if you want a stopgap: download names carrying a random token.
4. **C5's wider scope.** Recommendation: fix all 8 handlers. At zero, the table says "Neutral" and the text says "in line with budget" (memo, run-rate, compare) or "no change" (what-if).
5. **X32**: write the report's rounded Var % into the workbook cell (changes `--xlsx` cell values, a path not in 0.2.0, and may edit the legacy-workbook golden test), or keep the exact ratio and state it on the sheet? Recommendation: **state it on the sheet**, since the workbook already says the audit is the exact record.
6. **X40**: pin the Render build (commit a constraints file), or leave it to you? Recommendation: **leave it to you**, since it changes the deploy.
7. **Draw G**: `EDGAR_USER_AGENT` is still unset. Set it in `~/.zshrc` before Phase 8 if you want Draw G measured.
