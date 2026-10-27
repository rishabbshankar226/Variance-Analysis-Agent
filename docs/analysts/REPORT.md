# Analyst coverage: report

Branch `analysts/filings-and-excel`, cut from `main` at `8a609c4`, executing `VARIANCE_ANALYST_COVERAGE_PROMPT.md` Revision 1, Part B. The full record is in `PLAN.md`: its status table, Decisions 1-39 and rules R1-R18. Nothing is pushed, merged or tagged. Every committed fixture is fictional (`.FAKE`). Real filings and every per-filing result live in `~/vaa-edgar-corpus/`, and this file names no company.

## What each reader can do now

- **Maya (FP&A)** keeps her path and outputs. Excel workbooks now read as they display:
  - an "in thousands" caption over cells already formatted in thousands is not scaled twice (E1)
  - hidden rows are asked about, never silently counted (E2)
  - a formula Excel never calculated refuses, naming the cell (E7)
  - EDGAR-style statement sheets, period bands, side-by-side tables, date headers and `.xls` files read (E3-E6, E8)
- **Priya, Dan and Wei** keep their paths and outputs. Wei's batch run was not built (Decision 38).
- **[Owen (IB)](owen.md)**
  - Reads a 10-K's or 10-Q's statements straight from EDGAR's Inline XBRL `.htm`.
  - Builds LTM from a 10-K and a 10-Q, with every component cited.
  - Compares declared metrics, such as EBITDA from net income, interest and D&A, with a management case.
  - The report is headed by the filing's own printed totals.
- **[Clara (credit)](clara.md)**
  - Compares balance sheets and cash flow statements year on year, after every subtotal, the balance sheet identity and the cash roll-forward are checked.
  - Tests the ratios she declares against a covenant schedule: Breach, At limit, Near or Within, with headroom.
- **[Marcus (PM)](marcus.md)**
  - Sees drift of each weight from its target in basis points (Over, Under, On target).
  - Gets a holdings scorecard: the book's weight labeled Beat, Miss or In line on one deciding metric against consensus.
- **[Ines (risk)](ines.md)** sees exposures against Max or Min limits by severity, with headroom, headroom as a percentage of the limit, and utilization.
- **[Theo (AM)](theo.md)** sees active return against the benchmark in basis points: Higher than benchmark, Lower than benchmark, or In line within a declared tolerance.
- **The chat** takes every new reader from upload to a first answer with no step beyond confirming and answering its questions (`tests/test_reader_chat.py`).

## Held-out results

The targets (section 5): zero wrong numbers on the held-out draw, and all three face statements read on at least 90% of its Inline XBRL filings that contain statements. A statement counts as read only when every line with an amount is covered and every value is verified against the filing's fact; a printed dash with no fact stays unverified (Decision 35). Rates carry Wilson 95% intervals.

### Draw B (seed `20261029`), as swept once at `3f731a7`, unchanged

| Measure | Draw B (28 Inline XBRL filings) |
|---|---|
| Wrong values, as the sweep scored them | **1**: a revenue subtotal holding interest income. Every line value matched its fact |
| Wrong headline figures found by fresh eyes | **3 more**: two Total Expenses headlines and one "net operating variance", each added up from the lines and not the filing's own total |
| Values verified / unverified | 4,193 / 42 (every unverified one a printed dash or confirmed blank with no fact) |
| All three statements read | **12 of 28 (43%, 27-61%)**: the 90% target is **not reached** |
| All three read without a refusal | 18 of 28 (64%, 46-79%) |
| Refusals | 10: 9 plain, and 1 that named a fix for spreadsheets ("specify Row Kind") |

The two 10-Ks without XBRL in Draw B refused plainly and are outside the denominator. Section 5 sends a wrong number on Draw B to a STOP-ASK. The owner chose to fix and measure on a fresh draw (Decision 39). The evidence is in `evidence/stop-ask-draw-b/`.

### Draw C (seed `20261031`), after the fixes, swept once at `cabf9a8`

Drawn as Draw B was: 15 10-K and 15 10-Q from 2025Q4-2026Q3, one per filer, excluding every Draw A and Draw B accession and filer. It was swept once and informed no code change. Results file sha256 `1e5ffba4c33e513438c664fdaf8b813b5d692f0c8ea0399414d1382b91915fdf`.

| Measure | Draw C (27 Inline XBRL filings) |
|---|---|
| Wrong values (lines and every headline figure scored) | **0** |
| Values verified / unverified | 3,644 / 28 (every unverified one a printed dash or confirmed blank with no fact) |
| All three statements read | **12 of 27 (44%, 28-63%)**: the 90% target is **not reached** |
| All three read without a refusal | 15 of 27 (56%, 37-72%) |
| Read without a refusal, by statement | income 19/25, balance sheet 23/27, cash flow 22/27 |
| Fully read, by statement | income 16/25, balance sheet 20/27, cash flow 19/27 |
| Of the 3 read without a refusal but not fully | all 3 short only by printed dashes or confirmed blanks |
| Refusals | 15: 9 plain; **6 name no fix**, the 3 statements of each of 2 filings |

- **Refusals that name no fix.** Both say "I could not find the financial statements in '…': no table there is titled as … and holds their tagged figures."
  - One is a bank's 10-K whose statements are in its annual-report exhibit; its primary document holds 2 tagged figures.
  - The other is a 10-Q whose statement tables the reader's assembly misses.

  Neither shows a figure. They miss section 5's "reads or refuses plainly" by naming no next step, and stay as measured.
- **Two filings' income statements were not swept.** The oracle found two statements in each, so those filings count as not all-three-read.
- **Three 10-Ks without XBRL** are outside the denominator. Run by hand, each refuses plainly with what to upload.

Draw C's final fresh eyes found label amounts quoted at the filing's printed scale (above). Section 5 sends that to a STOP-ASK, and the owner chose the fix and a fresh draw (Decision 40). Draw C stays here as measured.

### Draw D (seed `20261102`), after Decision 40, swept once at `0f1d284`

Drawn as Draws B and C were, excluding every Draw A, B and C accession and filer. It was swept once and informed no code change. `src/` at `0f1d284` is the same as at `273fd98`. Results file sha256 `b2589644f7bfebd1c2fac405a3959270fbcf9df5dd7fca929d6ed50e8ccc536d`.

| Measure | Draw D (28 Inline XBRL filings) |
|---|---|
| Wrong values (lines and every headline figure scored) | **0** |
| Values verified / unverified | 3,888 / 51 (every unverified one a printed dash or confirmed blank with no fact) |
| All three statements read | **11 of 28 (39%, 24-58%)**: the 90% target is **not reached** |
| All three read without a refusal | 19 of 28 (68%, 49-82%) |
| Read without a refusal, by statement | income 24/28, balance sheet 26/28, cash flow 22/28 |
| Fully read, by statement | income 15/28, balance sheet 21/28, cash flow 15/28 |
| Of the 8 read without a refusal but not fully | 1 short only by printed dashes or confirmed blanks; 7 by an oracle line the reader doesn't cover |
| Refusals | 12, **all plain** |

The two 10-Ks without XBRL are outside the denominator. Run by hand, each refuses plainly with what to upload.

### Draw A, the development set (seed `20261026`, 40 filings; 33 Inline XBRL)

| When | Commit | Wrong | All three read (Inline XBRL) | Without a refusal |
|---|---|---:|---|---|
| Baseline (Phase 2) | `8a609c4` | 39 (`Financial_Report.xlsx` reader) | 0 of 33: every `.htm` refused | 0 |
| STOP 1 (income only) | `69d8366` | 0 | income read 25 of 33 (76%) | |
| STOP 2 | `1d903a6` | 0 | 15 of 33 (45%, 30-62%) | 26 of 33 (79%, 62-89%) |
| Phase 7, after Decision 39 | `1a585fe` | 0 | 14 of 33 (42%, 27-59%) | 25 of 33 (76%, 59-87%) |
| Phase 7, after Decision 40 | `273fd98` | 0 | 14 of 33, every scored row unchanged | 25 of 33 |

The drop from STOP 2 is an investment company's statement of operations. At STOP 2 it counted as fully read, but it read its subtotals as lines: net investment income was typed revenue, and the totals the report computed double-counted. Since Decision 39 its bottom line must add up, so it refuses plainly. The `Financial_Report.xlsx` reader on the six 2018 filings: 169 verified, 7 unverified, 0 wrong.

## Fresh eyes

At each point, five filings were drawn with a seed committed first. A subagent with none of this plan's reasoning checked every figure against the printed filing and its instance, defaulting to "wrong" under doubt.

| Point | Seed | Found | Done |
|---|---|---|---|
| STOP 1 (Draw A) | `20261027` | 4 wrong headline Total Revenue figures in 2 filings: other income counted as revenue | Decisions 28-29: revenue is the printed revenue block; statements end at net income |
| STOP 2 (Draw A) | `20261028` | 4: a sweep artifact, a mislabeled unlabeled subtotal, and a bank's Total Revenue and Total Expenses | Decision 37 |
| Draw B, final | `20261030` | Draw B's wrong revenue subtotal, plus 3 more wrong headline figures; 10 balance sheet and cash flow reports clean | STOP-ASK, then Decision 39 |
| Draw C, final | `20261101` | Every line, change, subtotal and headline matched. 7 wrong figures in one insurer's balance sheet: labels quote amounts in thousands beside whole-dollar columns, with no unit stated. One percent follows the documented half-even rule | STOP-ASK (`evidence/stop-ask-draw-c/`); the class runs through every draw (A 40 labels in 18 filings, B 23 in 8, C 21 in 10); Decision 40 |
| Draw D, final | `20261103` | FRESH_D_FOUND | FRESH_D_DONE |

The lesson from all of them: the sweep scored line values, and every wrong figure fresh eyes found sat elsewhere. Most were headline figures added up from the lines; since Decision 39 a filing's report shows no figure it added up itself, and the sweep scores every headline figure against its fact. The last was an amount inside a line's label, quoted in the filing's unit beside figures shown in full; since Decision 40 every filing report states that unit.

## E and F items, final state

| ID | Measured at `8a609c4` | Final state |
|---|---|---|
| E1 | "in thousands" caption over `#,##0,` cells read ×1,000: $110,000,000 for $110,000 | Fixed (R2): caption and formats reconciled; a conflict refuses naming the cells |
| E2 | A hidden row counted silently | Fixed (R3): asked (`--hidden-rows`, a chat reply, a mapping, an API option); recorded in audit 1.9 |
| E3 | EDGAR statement sheet: header-row refusal | Fixed: read like a statement; several durations by `--sheet "<sheet> (9 Months Ended)"` |
| E4 | Period bands: "more than one Actual column" | Fixed: the newest band (or the one `--period` names) |
| E5 | Side-by-side tables: "more than one Actual column" | Fixed: the first table read, the other named |
| E6 | Excel dates as period headers: header-row refusal | Fixed: dates read as periods |
| E7, E7b | Uncached formulas read as blank, so a budget became 0 | Fixed (R4): refuses, naming each cell and the fix (open, calculate, save), also when the workbook asks Excel to recalculate on open |
| E8 | `.xls` and `.htm` refused | Fixed: `.xls` read by content; `.htm` read as Inline XBRL (Phase 3) |
| F1 | Only `.pdf` routed for filings | Fixed: `.htm` routed on the CLI, the chat and the file API |
| F2 | `Financial_Report.xlsx` assumed published | Corrected: not published for 2025-26 filings (HTTP 404); the reader stays for older filings |
| F3 | Balance sheets and cash flows refused | Fixed for Inline XBRL (R7-R9); PDF and `Financial_Report.xlsx` statements still refuse (Decision 31) |
| F4 | Budget-only upload: header-row refusal | Closed: two files join on a shared key (R12), and a 10-K with a 10-Q builds LTM (R11) |

## Friction scorecard (Phase 1 intake, chat path)

| Probe | Before: dead end / manual steps / first message | After |
|---|---|---|
| E1 | no / 0 / a read with a wrong ×1,000 total | no / 0 / correct read, with a note on why it was not scaled |
| E2 | no / 0 / a read counting a hidden row silently | no / one chip / the question naming row 3 |
| E3 | yes / re-key the statement / header-row message | no / 0 / statement read |
| E4 | yes / delete a band / "more than one Actual column" | no / 0 / newest band read |
| E5 | yes / split the sheet / "more than one Actual column" | no / 0 / first table read, the other named |
| E6 | yes / retype headers / header-row message | no / 0 / dates read as periods |
| E7b | no / 0 / a wrong zero budget | yes, correctly / open and save / names cell B4 and the fix |
| E8 `.xls` | yes / save as / "Unsupported input format" | no / 0 / read with a rename note |
| E8 `.htm` | yes / unclear / "Unsupported input format" | no / 0 / statements read (Phase 3) |

## Rules (full text in PLAN.md)

- **R1.** Sign and scale: each fact is kept as the instance stores it and as printed; values are checked stored, footed and shown printed.
- **R2.** E1: display scaling reconciled with the caption.
- **R3.** E2: hidden rows are a confirmed choice.
- **R4.** E7: a formula without a saved result refuses.
- **R5.** Subtotal footing within each fact's rounding interval (Calculations 1.1).
- **R6.** One-axis facts on a face statement are printed lines.
- **R7.** Balance sheet and cash flow lines compare as Increase or Decrease. Decisions 38 and 39 add the "larger/smaller negative" cue where both figures are negative.
- **R8.** A cash flow's beginning and ending cash take its duration columns by date.
- **R9.** Footing, the balance sheet identity and the cash roll-forward, before any comparison.
- **R10.** Multi-document input is opt-in.
- **R11.** LTM = fiscal year + year to date - prior year to date, by concept, with continuity checked.
- **R12.** Budget and actuals in two files join on a shared key; a key in one file only refuses.
- **R13.** `limit`: Breach, At limit, Near (declared buffer only), Within; headroom, headroom % and utilization.
- **R14.** `benchmark`: Higher than benchmark, Lower than benchmark, In line within a declared tolerance.
- **R15.** `target`: Over, Under, On target; neutral.
- **R16.** `Multiple` measure with `--multiple-threshold` in turns.
- **R17.** Derived metrics from declared formulas over stored XBRL values, with LTM terms.
- **R18.** Marcus's holdings scorecard: one deciding metric against consensus, with weights shared by label.

## Decisions (full text in PLAN.md)

1. Work in a worktree, since the main checkout is shared.
2. Its own Python 3.11 venv.
3. `CLAUDE.md` excluded in the common git dir.
4. No Claude attribution on commits (owner's rule).
5. One stop for the E1/E2/E7 STOP-ASKs.
6. The prompt folder is read-only.
7. The EDGAR contact is the owner's, sent inline only.
8. Gates per phase; dist gates at stops.
9. The evidence folder is excluded from the sdist.
10. Workbook layout facts are collected once, in the bounded preflight.
11. Rules-file drift is overridden by the prompt.
12. Audit 1.9 timing.
13. The owner approved E1, E2 and E7 (strict mode unchanged for E2).
14. The workbook examination appears only with a finding.
15. E3 durations are chosen by sheet name.
16. E4 defaults to the newest band.
17. E1 on the file API.
18. `--hidden-rows` needs assisted or mapped intake.
19. Hidden lines on an EDGAR statement sheet.
20. Comparison-set audits stay 1.8.
21. The 1.9 schema is generated from 1.8, which round-trips byte for byte.
22. A finding makes the chat confirm the read.
23. DOCTYPE handling in the HTML reader.
24. Statement assembly.
25. Subtotals by label, filing label and total concept.
26. Blank and nil.
27. `Financial_Report.xlsx` reads.
28. Revenue on filing reads is the printed revenue block.
29. A statement ends at net income.
30. STOP 1 answers.
31. Statements beyond income: Inline XBRL only.
32. No workbook for statement comparisons.
33. Nil-only concepts are not monetary lines in the oracle.
34. LTM statements for income only.
35. A printed dash stays unverified.
36. Phase 5's opt-in rules are not STOP-ASKs.
37. STOP 2 fresh-eyes fixes.
38. STOP 2 answers: At limit, the benchmark words, Phase 6 kept (a), (b), (e) and the scorecard, and dropped (c) and (d).
39. Draw B STOP-ASK answers: net income by concept; revenue on final types; filing refusals; 52/53-week labels; the headline from the filing's own totals; reading notes in the report; small fixes; chat panels and tables; the oracle title rule; Draw C.
40. Draw C STOP-ASK answer: every filing report states the unit the filing prints in and that label amounts are quoted as printed; Draw D.

## Existing assertions edited, with reasons

- **Phase 4, F4 (approved at its STOP-ASK):** `test_realworld_intake_baseline.py:154`. A budget-only upload now asks for its actuals instead of refusing the header row.
- **Phase 5, scope only, no assertion changed:**
  - `test_comparison_basis.py::test_numbers_identical_across_bases` and `test_quality_audit.py::test_financial_invariants_against_independent_fraction_oracle` now loop over the bases without per-row declarations.
  - Limit, benchmark and target refuse rows without their declarations, and have their own Fraction oracles.
- **Phase 7, Decision 39** (old and new text in PLAN.md):
  - The filing-refusal wording in `test_ixbrl.py` (two cases) and `test_ixbrl_statements.py` (one): a CSV or Excel copy before a PDF.
  - `test_ixbrl_statements.py`:
    - the R7 cue case where one figure is 0
    - the balance sheet workbook refusal, which no longer suggests the income statement, since that refuses too
  - `test_reader_chat.py`: Owen's LTM line, which is now the filing's own Net sales.
  - `test_frontend_contract.py`: the allowed generated tags gain the table tags.

The 19 contract fixtures and schemas 1.0-1.8 are byte-identical to `8a609c4`.

## Gates

`sh docs/ui/evidence/gates.sh dist` on the final code (`src/` as at `273fd98`), on macOS with Python 3.11.16. All PASS:
- ruff
- mypy, strict, 71 files: `src/variance_agent`, `scripts` and `deterministic_conditioning` (the evidence tools pass `mypy --strict docs/analysts/evidence` separately)
- pytest: **2,497 passed**, up from 2,100 at `8a609c4`; this includes the Windows-path tests, which run on every platform
- compileall
- pip check
- contracts: 19 fixtures unchanged
- build, twine and `check_distribution.py`
- both artifacts installed without the Excel and PDF extras, each passing `check_installation.py` and pip check
- the wheel installed with the PDF extra alone

The log is at `~/vaa-edgar-corpus/final-d/gates_dist.log`.

## Browser check

`evidence/final/shots/` holds 124 images, retaken on the final code, at 1280 and 375 px of every chat screen changed since STOP 2, all from fictional files (`evidence/shots_analysts.py`):
- a filing headed by its own printed totals, a question about computed totals, and the exported report
- each new reader from upload to a first answer: limits, benchmark, target and covenant headroom
- the balance sheet report, with its table rendered
- Build LTM

This check found two problems, both fixed:
- **Raw Markdown tables in replies.** Found at the Draw B STOP-ASK; they had been there since Phase 4 and I missed them at STOP 2. Fixed in `84f0429`.
- **Four headline cards overflowing at 1280 px.** Fixed in `cabf9a8`.

`evidence/stop-ask-draw-b/shots/` keeps the screens as they were at that stop.

## Known limits

- **Income statements the reader refuses**, plainly:
  - a subtotal whose lines it can't trace
  - an investment company's statement of operations, whose net investment income subtracts a subtotal (Decision 39)
  - a blank amount no subtotal confirms

  These are why the 90% target is not reached.
- **PDF and `Financial_Report.xlsx` income reads** carry no facts. They keep the summary of totals added up from their lines, which Decision 39 removed for Inline XBRL.
- **Unlabeled filing lines in the chat.** When the arithmetic can't place a filing line, the chat asks the analyst to label it. The answer is theirs, and it changes no headline figure.
- **Bare-year bands** (`2025` / `2026` over Budget/Actual) don't take the E4 path.
- **Strict and assisted intake differ on uncached formulas** in computed columns.
- **Captions on the earnings path.** The earnings and quant CLI and file-API paths apply no unit caption, as before this run.
- **10-Q column labels name the end month only.** A three-month income statement and a nine-month cash flow statement of one 10-Q both read "Jul 2026"; the statement's name carries its duration only where the filing prints more than one.
- **A statement continued in an untitled table on the next page** with a different layout is not joined. Its refusal can misstate the cause (Draw C).
- **Statements in a second document.** A filing whose statements sit in a second Inline XBRL document (a bank's annual report) refuses with "I could not find the financial statements", naming no fix. That message names no next step for any filing without statement tables (Draw C: 6 refusals in 2 filings).
- **A pre-tax subtotal refused over a $1M gap** that should sit inside R5's rounding interval (Draw C fresh eyes). Not investigated: Draw C informs no change.
- **A timing test flaked once.** `test_chat_hardening.py::test_unmatched_questions_on_a_big_file_stay_fast` failed twice in one gates run under load. It passed alone and on the rerun.

## Not built (Decision 38)

- Workbook sheets for statement, limit, benchmark, target, metric and filing income comparisons. `--xlsx` and the chat's Export Excel refuse plainly for them.
- Wei's batch run over many filings.

## Not verified

- **The 90% target.** It is not reached on Draw B, C or D under Decision 35's strict definition (above).
- **Cross-reader agreement.** EDGAR carries no PDFs for recent filings, and the SEC no longer publishes `Financial_Report.xlsx` (F2), so the readers could not be compared on the same recent filing (Decision 30).
- **The new comparisons on real filings.** The sweeps measure one statement per run. LTM, derived metrics and covenants, two-file joins, the limit, benchmark and target bases, and the holdings scorecard were exercised on fictional fixtures and in the guides, never on a drawn filing.
- **Real analysts.** The per-reader reviews at STOP 2 were subagents given each seat's row of section 3, not people in those seats.
- **Windows and Python 3.12-3.14.** These run only in CI, and nothing was pushed, so no CI result was seen. Every gate here ran on macOS with Python 3.11.16.
- **Browsers.** The screenshots come from the Playwright harness in Chromium at 1280 and 375 px, not from Safari, Firefox or a physical phone.
- **The chat on real filings.** It was driven with fictional files only.

## Walkthrough

1. `variance-agent <10-K .htm> --assisted --period FY2025 --dollar-threshold 1 --percent-threshold 1`:
   - reads the income statement
   - checks every subtotal against its rounding
   - heads the report with the filing's own revenue, total expenses, operating income and net income
   - writes an audit (`--audit-json`) whose every line carries its XBRL fact
2. Add `--sheet "Consolidated Balance Sheets" --compare-to prior-period` for Clara's balance sheet, or `--ltm-from <10-K>` on a 10-Q for Owen's LTM.
3. `--compare-to limit|benchmark|target` reads Ines's, Theo's and Marcus's files. `--metrics` with `--compare-file` tests declared ratios against a schedule. `--panel` builds Marcus's scorecard.
4. In the chat, upload the same files. Each reader's guide lists the questions to type.

## PR description

**Analyst coverage: SEC filings, Excel as displayed, and five new readers**

- **Excel.**
  - Workbooks read as they display: no double scaling.
  - Hidden rows are asked about.
  - Uncalculated formulas refuse, naming the cell.
  - EDGAR statement sheets, period bands, side-by-side tables, date headers and `.xls` read.
- **SEC filings.**
  - A 10-K's or 10-Q's Inline XBRL `.htm` is read fact by fact, after every subtotal foots within the facts' rounding.
  - Balance sheets and cash flows compare as Increase or Decrease once the identity and the cash roll-forward hold.
  - A filing's income report is headed by the filing's own printed totals, never totals added up from its lines.
- **New readers.** All opt-in and recorded in audit 1.9 only:
  - LTM from a 10-K and a 10-Q, every component cited
  - budget and actuals in two files
  - limit, benchmark and target comparisons
  - the `Multiple` measure
  - declared derived metrics against a case or covenant schedule
  - a holdings scorecard
  - chat routing for each reader's first questions
- **Measured.**
  - Draw B: 1 wrong figure, plus 3 headline figures found by fresh eyes, all added up from the lines. Fixed under Decision 39.
  - Draw C: 0 wrong values, but its fresh eyes found label amounts quoted at the filing's unit with no unit stated. Fixed under Decision 40.
  - Draw D, the last held-out draw: 0 wrong values, every headline figure scored.
  - All three statements read on 39% (24-58%) of Draw D, short of the 90% target.
- **Unchanged.** The 19 contract fixtures and schemas 1.0-1.8. No new dependency.
