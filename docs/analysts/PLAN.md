# Analyst coverage: filings, Excel and every analyst seat (plan)

Spec: `~/Desktop/prompt library/variance-analyst-coverage/VARIANCE_ANALYST_COVERAGE_PROMPT.md`, Revision 1 (read-only). When this plan and the spec disagree, the spec wins, except where a Decision below records an owner answer.

Branch `analysts/filings-and-excel`, cut from `main` at `8a609c4`. Corpus and per-filing results live in `~/vaa-edgar-corpus/` and never in this tree. Every fixture here is fictional.

## Status

| Phase | Task | State | Commit |
|---|---|---|---|
| 0 | Read, measure, plan; E/F items confirmed; STOP-ASK for E1, E2, E7 written | done | `a37c9c9` |
| 1 | Packaging exclusion for `docs/analysts/evidence` | done | `41f6c39` |
| 1 | Preflight layout scan (`inspect_workbook`) | done | `58ec0be` |
| 1 | E7 uncached formulas (R4, with the recalculate-on-open part) | done | `9e25cfc` |
| 1 | E1 display scaling (R2) | done | `3bbc9c4` |
| 1 | E2 hidden rows (R3) | done | `d981b14` |
| 1 | E8 `.xls` by content, `.htm` message | done | `b3bce64` |
| 1 | E6 date headers | done | `de282dc` |
| 1 | E3 EDGAR statement sheets | done | `dd9bea3` |
| 1 | E4 period bands, E5 side-by-side tables | done | `7667b7c` |
| 1 | Workbook examination summary + audit 1.9 | done | `20f3828` |
| 1 | Earnings chat path asks about hidden rows (advisor check) | done | `fdc6508` |
| 2 | Network check, sampler, oracle, sweep, Draw A, baseline sweep | done | `be7d4dc`, `7c7d38e` |
| 3 | `ixbrl.py`, `Financial_Report.xlsx` reader, `.htm` routing; Draw A at zero wrong | done | `cd23bf0` … `13de5e8` |
| 3 | Fresh-eyes fixes: Total Revenue is the filing's revenue; statements end at net income | done | `13a79e1` … `69d8366`, docs `6d7d40c` |
| 3 | STOP 1 | done (owner 2026-10-27: "do what you recommend and continue"; Decision 30) | evidence `docs/analysts/evidence/stop-1/` |
| 3 | Flip the provisional "yet" wording when `.htm` reads: `parsing.web_page_message` (removed), the input-contract `.xls`/`.htm` bullet, and the `--audit-schema-version` help | done | this commit |
| 3 | `ixbrl.py` reader, `.htm` routing (CLI, chat, file API), audit 1.9 `ixbrl` documents | done | `cd23bf0` |
| 3 | `Financial_Report.xlsx` reader fixes from Draw A (breakdowns, binary floats) | done | `d7fd9a2` |
| 4 | Balance sheet / cash flow statements, identities, multi-document input, LTM, F4 (STOP-ASK) | todo | |
| 5 | `limit`, `benchmark`, `target`, `Multiple`, derived metrics; STOP 2 | todo | |
| 6 | Reader surfaces kept at STOP 2 | todo | |
| 7 | Draw B, gates, `REPORT.md` | todo | |

## Baseline (measured 2026-10-26)

- `8a609c4`, Python 3.11.16 (fresh venv, constraints file, `[dev,excel,pdf,release]`): **2100 passed in 42.04 s**. `pip check`: no broken requirements.
- The probes were rebuilt with the prompt folder's `probes/build_probes.py` into `~/vaa-edgar-corpus/probes/` and run with `variance-agent FILE --assisted --period X --dollar-threshold 1 --percent-threshold 1`. Every outcome in the table below reproduced exactly.

## E and F items

| ID | Measured outcome at `8a609c4` | State |
|---|---|---|
| E1 | `($ in thousands)` + `#,##0,` on full stored values: Total Revenue $110,000,000.00 vs $100,000,000.00 (true $110,000), stderr "Amounts scaled from thousands (x1,000)" | confirmed, wrong number |
| E2 | Hidden row 3 (Draft line 5/5) counted: Total Expenses $50.00 vs $45.00, no note; hidden column E unmentioned | confirmed, silent |
| E3 | EDGAR statement shape (title cell, merged `12 Months Ended`, date-text periods): header-row refusal | confirmed |
| E4 | `Q3 2026` / `Q2 2026` bands over Budget/Actual pairs: "Found more than one Actual column (Actual (column C), Actual (column E)); keep one and try again." | confirmed |
| E5 | P&L block + KPI block separated by a blank column: "more than one Actual column (… column C, … column G)" | confirmed |
| E6 | Real Excel dates as period headers: header-row refusal | confirmed |
| E7 | Uncached `=C2+C3` in Actual: "Row 4, Total, Actual column: the amount is blank." | confirmed, misleading |
| E7b | Uncached `=B2-B3` in Budget: "Treated blank budgets as 0 on 1 unbudgeted line", Total Revenue $180.00 vs $100.00 (true budget $160.00) | confirmed, wrong number |
| E8 | `.xls` (renamed `.xlsx`) and `.htm`: "Unsupported input format '.xls'. Use CSV, JSON, XLSX, or XLSM." | confirmed |
| F1 | `read_input_assisted` routes `.pdf` only for filings; `.htm` is refused (E8) | confirmed in code |
| F2 | EDGAR folder contents. **Corrected on Draw A (2026-10-26):** every filing with XBRL lists its instance (`*_htm.xml` for the 33 Inline XBRL filings), `FilingSummary.xml` and R pages. **`Financial_Report.xlsx` is no longer published for recent filings:** it is listed in none of the 34 filings from 2025-2026, and a direct request for one returned HTTP 404 while its `R2.htm` returned 200. All six 2018 filings list it. Seven recent filings have no separate `*_pre.xml` (the linkbase is embedded in the schema or only in the `-xbrl.zip`), so the oracle takes their structure from the R pages. One asset-backed 10-K has no XBRL at all. | corrected |
| F3 | `fixture_o_10k_statements.pdf --sheet "Consolidated Balance Sheets (pp. 5-6)"`: "…lists assets, liabilities and equity, which can't be compared as revenue and expense yet. Choose an income statement instead: Consolidated Statements of Operations (p. 4)." The cash flow text comes from `_NOT_REVENUE_AND_EXPENSE` ("cash coming in and going out") and was not run. | confirmed |
| F4 | `test_realworld_intake_baseline.py:154` pins the header-row message for a budget-only upload | confirmed |

## Decisions

1. **Worktree.** The main checkout is shared with another agent that commits there, so all work happens in `.claude/worktrees/analysts-coverage` (`git worktree add … -b analysts/filings-and-excel 8a609c4`). This deviates from Part A step 1.
2. **Venv.** The worktree has its own Python 3.11 `.venv`, built with the constraints file. The checkout's `.venv` is 3.14 and is not used.
3. **`CLAUDE.md` exclusion** goes in `$(git rev-parse --git-common-dir)/info/exclude`, since `.git` is a file in a worktree.
4. **No Claude attribution** on any commit or PR in this repository. This is the owner's standing rule.
5. **One stop for the three Phase 1 STOP-ASKs.** E1, E2 and E7 are written up together at the end of Phase 0, and none lands before the owner answers. F4 keeps its own STOP-ASK in Phase 4.
6. **Prompt folder is read-only.** Probes build into `~/vaa-edgar-corpus/probes/`.
7. **EDGAR contact.** The owner chose the account contact for `EDGAR_USER_AGENT`. It is exported inline on each corpus command and never written into this tree.
8. **Gates.** Every phase runs `sh docs/ui/evidence/gates.sh` (ruff, mypy, pytest, compileall, pip check, contracts). The dist variant (`… gates.sh dist`) runs at each STOP and at the end. The browser check uses `~/.venvs/vaa-shots/bin/python docs/ui/evidence/shots.py`, which exists. The script's contracts gate compares with `822e522`; the contract files are identical at `8a609c4`, and `git diff 8a609c4 -- tests/fixtures/contracts` is checked too.
9. **Packaging lands first in Phase 1.** `/docs/analysts/evidence` goes into the sdist `exclude` in `pyproject.toml`, with an assertion in `scripts/check_distribution.py`. Phase 0 may not touch `scripts/`. Until then the evidence folder is only this plan's README and is not released.
10. **Three Excel readers exist.** They are `parsing.py` (strict), `intake.py::_read_excel_bytes` (assisted, `--mapping`, chat) and `comparisons.py` (file API). Layout facts (hidden rows and columns with outline level, merged ranges, formulas without stored results, error cells, external links, defined tables, `calcPr`) are collected once in `excel.py`, in the same bounded stdlib pass that already reads every worksheet for stored decimals. That pass runs behind the existing limits and the DOCTYPE/ENTITY refusal. `inspect_archive` keeps its return type, and a sibling returns the new facts. Number formats come from openpyxl's read-only `number_format` (no second load).
11. **Rules-file drift.** `.agents/rules/variance-intake.md` still names schema 1.5, two `chat.html` copies, commit `a3ce6bb` and `intake/phase-N` branches. The prompt's overrides apply: audit 1.9, one packaged page, this branch.
12. **Audit 1.9 timing.** E1 and E2 land before the 1.9 schema. Until 1.9 exists, they record only what 1.7 can already hold (the unit multiplier actually applied). The examination summary commit then adds 1.9 and records the display-format reconciliation and the hidden-row choice. A file with no finding keeps its 1.7 audit (constraint 6).
13. **Owner answer to the E1/E2/E7 STOP-ASK (2026-10-26): "do what you recommend".** E1, E2 and E7 land as R2, R3 and R4. E7 keeps the `fullCalcOnLoad` part. Strict mode stays unchanged for E2. This part matters more than the STOP-ASK said: XlsxWriter stores 0 as every formula's result and sets this same flag, so without the rule such a workbook reads as zeros.
14. **The examination summary appears only with a finding.** A finding is a fact that changes or could change the read of the chosen sheet: hidden data rows, hidden read columns, error cells, formulas without saved results, display-scaled amount cells, a merged header band that was read, external links, or a recalculate-on-open flag on a workbook with formulas. Sheets with their visibility, defined tables and outline levels are listed only beside a finding. A clean workbook's stderr, chat reply and 1.7 audit are byte-identical to today, and hidden worksheets alone are not a finding (they are already ranked last).

15. **E3 durations by sheet name.** An EDGAR-style sheet with several durations reads the first and names the others. `--sheet "<sheet> (9 Months Ended)"` (and the same text in chat) picks one. The same `"<sheet> (columns E-G)"` form picks a side-by-side table (E5). Phase 3's `Financial_Report.xlsx` reader may refine this.
16. **E4 defaults to the newest band.** With bands, a `--period` that names a band picks it, and otherwise the newest band is read (not the last, as the wide monthly layout does). The note names the pair read.
17. **E1 on the file API.** `comparisons.read_comparison_input` applies no caption scaling at all (checked: no `detect_unit_scale` call), so E1 has nothing to reconcile there. Caption scaling on the earnings/quant paths is a pre-existing gap, left as is and listed for the report.
18. **`--hidden-rows` needs assisted or mapped intake.** Strict mode reads every row (Decision 13), so the flag is refused there rather than silently ignored. It is also refused on CSV, JSON and PDF, as `--sheet` is. The file API's `hidden_rows` follows the same rule.
19. **Hidden lines on an EDGAR statement sheet.** These are asked about like other hidden rows. "Include" reads the statement whole. "Exclude" refuses, because a statement's subtotals foot over every line.
20. **Comparison-set audits stay 1.8.** The structured `workbook` group is recorded on single-basis records (CLI default, assisted and mapping runs, chat export). Comparison sets carry the same notes as `inferences`, which 1.8 already copies into every child.
21. **The 1.9 schema is generated from 1.8** by a one-off script (scratch, not committed). The script asserts that the 1.8 file round-trips byte for byte, so 1.8 is unchanged.
22. **A finding makes the chat confirm the read.** `IntakeResult.has_transformations` is true when the examination has a finding, so the chat shows the summary before analysis instead of going straight to the period question. A clean workbook is unaffected.

## Phase 2 corpus settings (committed before the draw)

- **Network check, 2026-10-26:** `www.sec.gov` folder `index.json` returned HTTP 200 (10,170 bytes). `data.sec.gov` submissions returned HTTP 200 (163,917 bytes). The contact header was sent inline.
- **Draw A seed: `20261026`.** Quarters: the four most recent complete ones, 2025 QTR4, 2026 QTR1, QTR2 and QTR3, plus 2018 QTR1 for the six pre-Inline-XBRL filings.
- **Draw rules.** `form.idx` rows are confirmed against the header line, keyed by accession, and sorted before any random call. Forms match exactly (`10-K`, `10-Q`, `10-K/A`). Each pool is shuffled with one `random.Random(seed)`, and filings are taken in shuffled order, skipping any filer already drawn. Strata take the first shuffled candidate whose submissions record matches, so a filing can never count twice. The draw order is fixed: 14 10-K, 14 10-Q, banks, insurers, REITs, a large accelerated filer, a smaller reporting company, a `10-K/A`, then 3 10-K and 3 10-Q from 2018 QTR1.
- **Also fetched:** the label linkbase `*_lab.xml`. The structure oracle needs each line's printed label to match readers that carry no XBRL key (PDF and `Financial_Report.xlsx`). It is cheap and public, so this is an addition, not a substitution.

- **SIC ranges, checked 2026-10-26** against the SEC's SIC code list (now at `/search-filings/standard-industrial-classification-sic-code-list`; the old path returns 404). 6021 national commercial banks, 6022 state commercial banks, 6035 savings institutions (federally chartered) and 6036 savings institutions (not federally chartered) are the bank stratum. The list also has 6029, commercial banks NEC, which the spec's stratum leaves out, and this run keeps the spec's four. 6311-6399 covers exactly the insurance carriers: 6311 life, 6321 accident and health, 6324 hospital and medical service plans, 6331 fire, marine and casualty, 6351 surety, 6361 title and 6399 carriers NEC. Agents and brokers, 6411, fall outside. 6798 is real estate investment trusts.
- **Index sizes:** the four recent quarters hold 6,723 10-K, 17,313 10-Q and 616 10-K/A rows, and 2018 QTR1 holds 4,868 10-K and 1,399 10-Q.
- **Statement rule (oracle).** From `FilingSummary.xml`'s `Statements` category, the first report of each kind is taken by title. Parenthetical reports are dropped. "cash flow(s)" is the cash flow statement. "balance sheet(s)", "financial position", "financial condition", "statement(s) of condition" or "statement(s) of assets and liabilities" (a business development company's balance sheet, found on Draw A) is the balance sheet. An equity statement is dropped unless it also names operations or earnings. A standalone comprehensive income statement is dropped. Otherwise "operations", "income", "earnings" or "loss" is the income statement. Lines come from that report's presentation-linkbase role (depth-first in arc order, with the preferred label from the label linkbase), or from the R page's `defref_` anchors when there is no linkbase.
- **Sweep command.** It is the spec's fixed command plus `--audit-schema-version 1.9`, so every line is in the audit's `measure_rows` and not only the material ones (1.7 keeps material rows only). `--period` is the filing's `reportDate` from its submissions record. `--period` only names the report: assisted intake picks columns itself, so this choice cannot change a read. `-o` writes the Markdown beside the audit in the corpus.

## Known limits left by Phase 1 (for REPORT.md)

- Bare-year bands (`2025` / `2026` merged over Budget/Actual) do not take the E4 path. `_PERIOD_RE` has no bare-year form, and `detect_period_pairs` would not pair them. Such a sheet still stops with "more than one Actual column".
- Strict intake refuses an uncached formula in any headed column, `Var %` included. Assisted intake exempts ignored computed columns. This is approved (R4 "every column the read uses", where strict reads every headed column), but the two paths are inconsistent, and the report says so.
- The earnings/quant CLI and file-API paths (`read_comparison_input`) apply no unit caption at all. This was already so before this run. E1 has nothing to reconcile there.
- E3 has only met synthetic shapes. Real `Financial_Report.xlsx` sheets (title merged A1:A2, footnote-mark columns, `(Parenthetical)` sheets, abstract rows) are tried on Draw A at the end of Phase 2, with hit and miss counts in the corpus folder.

## Known limits left by Phase 3 (for REPORT.md)

- A filing with a blank amount refuses with the shared message "Fix these cells and upload the file again", which is the wrong fix for an EDGAR filing. Two Draw A income statements stop this way.
- Five Draw A income statements stop on a subtotal whose lines the reader cannot trace (net income, pre-tax income, other income/expense, gross profit). Each refuses plainly. Reading them is structure work, not a sign or scale question.
- Other income on a bank or insurer with no printed revenue total keeps the shaper's labels (Decision 28). A $1k securities loss on one bank therefore sits among expenses, which the fresh-eyes reviewer noted and did not count as wrong.
- A line printed with dashes in every column and no tag at all is not listed (one Draw A line). It is zero, so no figure changes.

## Rules written before code

### R1. Sign and scale (constraint 10), for Phase 3

For one `ix:nonFraction`: let `t` be its text after the declared `format` transform. `t` is non-negative by the Inline XBRL spec; a minus inside the element makes the fact invalid, and it is refused. Define:

- Magnitude `m = Decimal(t).scaleb(scale)`, exact in `financial_context`, with `scale` defaulting to 0.
- Stored `v = -m` when `sign="-"`, else `m`. `v` is what the oracle compares. Printed parentheses never enter `v`.
- Display negation `n` is true when, in the same table row, the text between the previous fact (or the label cell) and this element ends with `(` and the text after it, up to the next fact or the row end, begins with `)`. It is also true when the preceding text ends with `-` or U+2212. Whitespace, NBSP and currency symbols are ignored when reading that text. Cell boundaries do not matter, because EDGAR tables often put `$`, `(` and `)` in their own `<td>`. An opening `(` without a closing `)`, or the reverse, makes the line ambiguous, and the read refuses that line.
- Displayed `d = -m` when `n`, else `m`. `d` never uses the `sign` attribute. Subtotals foot on `d`, figures are shown as `d`, and `Financial_Report.xlsx` cells (displayed values in the caption unit) are compared with `d / 10^caption`.
- `xsi:nil="true"`: no value. It is missing, never zero.
- `decimals` (`INF` or an integer) is kept for the footing tolerance only. It never rounds `v` or `d`.

Boundary cases, one test each: `sign="-"` with parentheses (v<0, d<0); `sign="-"` without parentheses (v<0, d>0, e.g. a "Net loss" line printed positive); parentheses without `sign` (v>0, d<0, e.g. treasury stock); `(` and `)` in separate cells; `$` between `(` and the number; an unbalanced parenthesis (refuse); `scale` of -2, 0, 3, 6 and 9; dash and zero transforms (`fixed-zero`, `zerodash`) giving 0 with `n` false; a minus inside the element (refuse); `nil`; comma-decimal and dot-decimal transforms.

### R2. E1: display scaling against the caption

- **Format parse.** Split the format code into up to four `;` sections, ignoring separators inside `"…"`, after `\`, and inside `[…]`. In each section, skip quoted literals, the character after `\`, `_` or `*`, and bracketed tokens (`[Red]`, `[$-409]`). A comma that follows a digit placeholder (`0`, `#`, `?`) and has no integer-part placeholder after it divides the display by 1,000. That covers the end of the number (`#,##0,`, `0.0,`) and a comma just before the decimal point (`#,##0,.00`, which shows 1,234,567 as 1,234.57). A comma that sits between integer-part placeholders is grouping. Any other comma (inside the fractional digits) makes D unknown. ECMA-376 Part 1 §18.8.31 reads "a comma that follows a digit placeholder scales the number by a thousand". **Checked in Phase 1 (2026-10-26)** with headless LibreOffice's "save as shown" CSV export on 1,234,567,890. Every other case below rendered as R2 predicts, but `#,##0,.00` and `0,.0` rendered unscaled, as General. With no reference agreeing, a comma just before the decimal point makes D unknown: the read refuses under a caption and reads stored amounts with a note without one. Neither way gives a wrong number. Each unquoted `%` multiplies the display by 100. Display divisor `D = 1000^k / 100^p`. `General` gives D = 1. A section with a condition (`[>=1000]`) cannot be read, and the cell's D is unknown.
- **Section for a cell.** Positive values use section 1. Negative values use section 2 when present, otherwise 1. Zero uses section 3 when present, otherwise 1.
- **Reconcile.** Only numeric Currency amount cells in the comparison and Actual columns of data rows count. Text amounts are not formatted numbers. Let C be the caption multiplier (`detect_unit_scale`, or a mapping's declared unit, which is treated as a caption), and S the set of D values.
  - C = 1: amounts are read as stored, unchanged. If any D ≠ 1, a note says which cells Excel displays scaled.
  - C > 1 and S ⊆ {1}: the existing ×C applies, unchanged.
  - C > 1 and S = {C}: no multiplier, because the cells already store full amounts. A note says so.
  - Otherwise (a D outside {1, C}, S containing both 1 and C, or an unknown D): refuse. The message names up to ten cells (existing "…and N more") and gives the fix: make the amounts use one number format, or change the caption.
  - A `%` format on a Currency amount under a caption refuses with its own fix: the row is a rate, so mark its Measure as Percent or leave the row out.
- **Tests (straddling k = 0, 1, 2, 3).** Each of these gets a test: `#,##0,` + thousands (probe E1, $110,000); `#,##0` + thousands (×1,000, unchanged); `#,##0,,` + millions; `#,##0,,` + thousands (refuse); `#,##0,` + millions (refuse); `#,##0,` with no caption (stored, note); `#,##0,,,` with no caption (stored, note) and with a caption (refuse); mixed `#,##0,` / `#,##0` under thousands (refuse); `0.0,`; `#,##0,.00` and `0,.0` (scaling before the decimal point); `#,##0","` and `#,##0\,` (literal comma, D = 1); `#,##0,;(#,##0,)` on a negative value; `#,##0,;(#,##0)` mixed by sign (refuse under a caption); `_(* #,##0,_)` accounting; `[Red]#,##0,`; a conditional section (refuse under a caption); `0%` on Currency under a caption (refuse); Percent rows untouched.

### R3. E2: hidden rows and columns

- A row is hidden when its `<row>` has `hidden="1"`, or a custom height of 0. It was collapsed by an outline group when it is hidden and `outlineLevel ≥ 1`. Otherwise it was hidden one by one. A column is hidden by `<col … hidden="1">` or a width of 0.
- A **hidden data row** is a hidden row below the header row with any non-blank cell. One or more hidden data rows make inclusion a confirmed choice:
  - CLI: `--hidden-rows include|exclude`. Without it, intake exits 2: "Rows 3 (Draft line) … are hidden in Excel but have amounts. Rerun with --hidden-rows include to count them or --hidden-rows exclude to leave them out." The flag on a file with no hidden data rows is a no-op. On CSV, JSON or PDF it is refused, as `--sheet` is.
  - Chat: two replies, "Count the hidden rows" and "Leave the hidden rows out". The summary then states the choice and names the rows.
  - Mapping file: optional `hidden_rows` field. Older mappings without it ask.
  - File API (`analyze_file`, panels): these never prompt, so they take an explicit `hidden_rows="include"|"exclude"` option. Without it, a workbook with hidden data rows is refused with the rows named, as other undeclared choices are.
  - Exclusion happens before subtotal detection. Inclusion keeps today's arithmetic and adds the note.
- Hidden rows above the header and hidden columns are listed only, in "Here's how I read your file" and later in the examination summary. A hidden column that intake reads (Line Item, the comparison, Actual) is named as hidden in that list.
- Tests: 0 hidden data rows (output byte-identical to today) against 1 (asks); include and exclude totals (probe E2: Total Expenses $50.00 against $45.00, versus $45.00 against $40.00); outline-collapsed against one-by-one wording; a zero-height row; a hidden title-block row (listed, no question); a hidden Actual column (named, read); the flag on CSV (refused); mapping replay.

### R4. E7: formulas without stored results

- A cell has no stored result when it has an `<f>` child and either no `<v>`, or an empty `<v>` on a non-`str` cell. A cached empty string (`t="str"`, `<v></v>`) is a real result. This covers shared and array formula dependents.
- Every column the read uses (header row and data rows of Line Item, the comparison, Actual, account, period, currency, type, measure, better, segment and pass-through columns such as drivers) refuses on such a cell. The message: "These cells hold formulas that Excel never calculated, so the file has no saved result for them: Row 4, Other income, Budget column; … Open the file in Excel, let it calculate, save it, and upload it again." A blank budget is never inferred from a formula. Ignored computed columns (`Var $`, `Var %`) and title-block cells are listed only.
- **Stale caches** (recommended as part of E7, and droppable): when `workbook.xml` sets `calcPr fullCalcOnLoad="1"`, the producer asked Excel to recalculate on open, so saved results may be stale. Formula cells in read columns refuse with the same fix. openpyxl sets this flag on every workbook it writes (checked on the E7 probe: `<calcPr calcId="124519" fullCalcOnLoad="1" />`), but it writes formulas with an empty `<v />`, which already refuse under the rule above. So this part bites only on files that hold formula cells with saved results *and* the flag, the output of producers that write both.
- Tests: Budget formula (probe E7b, no longer $180 against $100); Actual formula (probe E7, the new wording); Line Item formula; a driver-column formula; a `Var $` formula (listed, the read proceeds); a cached formula (read as today); a cached empty string; a shared-formula dependent; `fullCalcOnLoad` 0 against 1; eleven cells ("…and 1 more").

### R5. Subtotal footing for filing reads (identity, constraint 2), confirmed against Calculations 1.1

- **Confirmed 2026-10-26** against XBRL Calculations 1.1 (REC 2023-02-22, sections 5.2 and 5.2.3, round-to-nearest mode). The specification does not re-round terms to a common `decimals`, so the spec's shorthand ("round each term and the total to the least precise decimals") is replaced by the specification's interval rule. Each fact with finite `decimals` d is the closed interval [v - 0.5*10^-d, v + 0.5*10^-d]; `INF` is the point v. The calculated total is the sum of the weighted term intervals. The subtotal is consistent when that sum overlaps the reported total's interval, touching endpoints included.
- Applied to the displayed values (constraint 10): for each subtotal the statement shaper matches, with the weights (+1/-1) it found, in every period column. The precision recorded is each fact's own `decimals`.
- A matched subtotal that fails the check, or a subtotal-named line the shaper cannot match to any lines above it, refuses the statement plainly, naming the line. Lines the arithmetic leaves unlabeled (several sign readings fit) are asked about, as for PDFs.
- The shaper finds structure with a single tolerance unit, 10^-d at the statement's least precise `decimals`. The interval rule then decides consistency with per-fact precision.
- Boundary tests: foots exactly; off by less than the summed half-widths; off by exactly the summed half-widths (consistent: closed intervals); off by more (refuse); mixed `decimals` (-6 and -3) on one subtotal; `INF` decimals.

### R6. Dimensional facts on a face statement

- **Amended in Phase 3 (Draw A).** Leaving one-axis lines out removed the components of totals such as "Total revenues" and "Total cost of revenues", so those totals could not foot. A total whose components were all dimensional would have been dropped as a subtotal, a wrong-total risk. Now a face line printed only with one-axis facts (revenue by product, cost by segment) is read as a printed line, keyed by concept, axis and member. R5 makes its total foot over it, so a breakdown that does not add up refuses the statement. These lines are not written into the Segment column, which the FP&A path does not read as segments; that is a STOP 1 question. The summary notes how many lines are breakdowns.
- A line's dimensionless facts win over its dimensional ones. Facts on two or more axes are always left out and listed.
- When a fact appears on the face and again in a note, the face table's copy is read: the first table in document order that holds the statement.

### R7. Balance sheets and cash flow statements are compared as Increase or Decrease (Phase 4)

- **Scope.** Inline XBRL reads. The PDF and `Financial_Report.xlsx` readers keep refusing these statements plainly (Decision 31).
- **Rows.** Every printed line, details and subtotals alike, at its displayed value (constraint 10). Each row carries its statement kind and a Row Kind (Detail or Total). Lines after the statement's closing line (a balance sheet's total liabilities and equity; a cash flow statement's ending cash) are supplemental disclosures. They are listed as left out and recorded as read, like Decision 29.
- **Comparison.** The newest column against the column `--compare-to` and `--period` choose, as for income statements. Variance is actual minus comparison on displayed values. The percentage is taken against the comparison's absolute value, as today.
- **Label.** Increase when the variance is above 0, Decrease below 0, No change at 0. The label describes the printed figure, so a cash outflow printed (600) against (500) is a Decrease of 100, and the report says so once. F or U appears only for a line the user gives a Better direction (the mapping's `better_directions`, the 1.8 mechanism), from the variance's sign as for any declared row.
- **No totals or advice.** These statements have no revenue, expense or net operating totals, and the report shows the identity checks in their place. No recommendation section (constraint 9).
- **Boundaries (tests).** Variance exactly 0 is No change. A comparison of 0 with a nonzero actual takes today's percent label. A subtotal is a row like any other, never summed into a total. Better Higher with a variance of -1 is U, and Lower with -1 is F.

### R8. A cash flow statement's beginning and ending cash take its duration columns

- Its columns are its duration periods. A line whose facts are instants is placed by date. An instant equal to a column's end date is that column's ending balance. An instant one day before a column's start is its beginning balance. Every instant on a line must place the same way (all ending or all beginning), or the statement refuses, naming the line. A column with no placed instant is blank, which refuses as unreadable unless a dash prints there.
- The instant-only column group of such a statement is not offered as a statement of its own.
- **Boundaries (tests).** A 52/53-week year, where the day before the start is exact. A 10-Q's year-to-date columns, whose beginning is the prior fiscal year end. A line with one beginning and one ending instant refuses. An instant on neither date leaves the cell blank.

### R9. Footing and identities for balance sheets and cash flows (constraint 2)

- **Subtotals.** A line is a subtotal when its label starts with "Total", or names the net cash from an activity or the net change in cash, or its concept is a balance sheet or cash flow total (`Assets`, `AssetsCurrent`, `AssetsNoncurrent`, `Liabilities`, `LiabilitiesCurrent`, `LiabilitiesNoncurrent`, `LiabilitiesAndStockholdersEquity`, `StockholdersEquity`, `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`, `NetCashProvidedByUsedIn…Activities…`, `…PeriodIncreaseDecrease…`), or it is the ending cash balance (R8).
- **Footing.** Each subtotal must equal the plain sum of a run of lines and earlier subtotals ending just above it, under R5's intervals in every column, longest run first. Failing that, the same is tried with lines labeled "Less …" subtracted. A subtotal that no run foots refuses the statement, naming it. The income shaper's chained running subtotals are not used here: a balance sheet restarts at each section, so "Total liabilities" is not checked against "Total assets".
- **Balance sheet identity.** The total assets line (`us-gaap:Assets`, or a "Total assets" label) and the total liabilities and equity line (`us-gaap:LiabilitiesAndStockholdersEquity`, or its label) both foot, and their intervals overlap in every column. The parts of the second may include temporary (mezzanine) equity and noncontrolling interests, and no total liabilities line is required. If either line is missing, the read refuses: it cannot check that the balance sheet balances.
- **Cash flow identity.** The ending balance foots on a run that includes the beginning balance plus the flows printed between them: the net change, the exchange-rate effect, discontinued operations. A missing beginning or ending balance refuses.
- **Recorded.** Audit 1.9 records each identity checked, its lines, and the `decimals` used per term and column.
- **Boundaries (tests).** Total assets equal to total liabilities and equity exactly; off within the summed half-widths; off by exactly the half-widths (consistent); off beyond them (refuse). Mezzanine equity and noncontrolling interests between total liabilities and total equity. No total liabilities line. "Less accumulated depreciation" printed without parentheses. Exchange-rate effect before the net change. Beginning cash printed before the net change. No net change line. Missing beginning cash (refuse). A subtotal with nothing above it (refuse).

### Phase 3 decisions (2026-10-26)

23. **DOCTYPE (constraint 3).** `html.parser` never reads a DTD, so the Inline XBRL reader refuses an `ENTITY` declaration or a `DOCTYPE` with an internal subset, but reads a plain `<!DOCTYPE html …>` (the four 2018 HTML 10-Ks carry one). Every XML parse in `src/` (the workbook preflight) still refuses any DOCTYPE. This is a STOP 1 question.
24. **Statement assembly.** A statement is the first table, in document order, titled by the text before it (2,000 characters, with spans joined as printed and block elements as breaks), by its own leading rows, or by a figure-less header table before it. It must also print three or more dimensionless money facts. An untitled following table continues it only when it prints the same periods.
25. **Subtotals.** Lines are subtotals by the shared shaper's labels, by filing-only labels (`… before income taxes` forms), and by a curated set of us-gaap total concepts, offered as hints. A hint that adds up from nothing is a detail line and is read as one. A subtotal-named first figure is read as a line. No subtotal is left out unless it is shown to foot, or the statement refuses. Each of these is a shaper option the PDF reader does not pass, so its reading is unchanged.
26. **Blank and nil.** A column with no fact is blank, which refuses as unreadable, unless the line prints an untagged dash, which reads as 0. `xsi:nil` (any prefix) is blank.
27. **`Financial_Report.xlsx` reads** stop at the first breakdown section and read amounts at the precision their formats show (Phase 3 fixes from Draw A). The SEC no longer publishes the workbook for recent filings (F2), so this reader matters for older filings only.

28. **Revenue on filing reads (from STOP 1's fresh-eyes review).** Where a statement prints its revenue (a revenue concept, or a total that sums such lines), only that block is revenue. Other lines that add to income (other income, equity earnings, gains printed as credits inside costs) are credits among costs, with their sign turned and a note, which leaves net income and the net variance unchanged. Without a printed revenue, the shaper's labels stand.
29. **The bottom line.** An income statement ends at its first net-income line, found by concept (`NetIncomeLoss`, `ProfitLoss`) or by a bare "Net income" or "Net (loss) income" label. Lines below it attribute net income and are listed as left out, recorded in audit 1.9 as read but not analysed. A separate comprehensive-income statement is not cut.

30. **STOP 1 answers (owner, 2026-10-27: "do what you recommend and continue").**
    - **The 90% target stays** as section 5 sets it. Reading work on Draw A's income misses (subtotals the reader cannot trace, blank amounts, a missed income statement) continues inside Phase 4, where balance sheets and cash flows share the same assembly. It is measured on Draw A only. Draw B is reported as measured, with Wilson intervals, pass or fail.
    - **The Phase 4 plan** is as listed at STOP 1: balance sheet and cash flow comparisons with their identities, opt-in multi-document input, LTM, then the F4 join behind its STOP-ASK.
    - **Draw B is drawn exactly as section 5 says.** Cross-reader agreement cannot be measured on recent filings: EDGAR carries no PDFs for them, and the SEC no longer publishes `Financial_Report.xlsx`. It goes on REPORT.md's "Not verified" list. The `Financial_Report.xlsx` reader stays for older filings, unchanged.
    - **R6 (amended), 23, 28 and 29 are confirmed.**
    - A blank amount in a filing gets a refusal that names a fix for filings, and a line printed only as dashes, with no tag, is listed in the notes. Both are done in Phase 4.

31. **Statements beyond income: Inline XBRL only.** A balance sheet or cash flow statement from a PDF or a `Financial_Report.xlsx` sheet keeps refusing plainly. A PDF figure carries no `decimals` and no concept, so the identities (R9) would rest on guessed tolerances and guessed line roles. The workbook is not published for recent filings (F2). Section 5's 90% target counts Inline XBRL filings only.

## STOP 1 settings (committed before the sample is drawn)

- Fresh-eyes seed: `20261027`. The five Draw A filings are `random.Random(20261027).sample` of Draw A's Inline XBRL accessions, sorted. The reviewer gets the sweep table, those filings and the tool's outputs, and none of this plan's reasoning.

## Existing assertions expected to change

Phase 1 (grep of `tests/` on 2026-10-26):

- **E1, E2, E7: none.** No committed workbook (5 files, scanned) and no test-built workbook uses a display-scaling or `%` number format, a hidden row or column, or a formula. Hidden worksheets (`test_operator_controls.py:52`, `test_engine_polish.py:156,179`) are outside E2.
- **E8:** the messages for `.xls` and `.htm` change; no existing test pins them. These stay unchanged: `test_pdf_intake.py:168` (the full `.docx` message) and `test_chat.py:320` ("Unsupported input format" for `.docx`).
- **E3 to E6** must not change: `test_intake_ambiguous_columns.py:27` (unbanded `Actual` + `Actual YTD` stays ambiguous), `test_intake_comparison.py:269` (`Name,Amount` keeps the header-row refusal), `test_intake_comparison.py:263`, `test_chat_blank_budgets.py:76` and `test_realworld_intake_baseline.py:119` (true blank budgets still read as 0 with the note).

Phase 4: `test_realworld_intake_baseline.py:154`. Old: a budget-only upload fails with "Could not find a header row with Line Item, Budget, and Actual columns". New: written at the F4 STOP-ASK.

## STOP-ASK: E1, E2, E7 (written 2026-10-26, awaiting the owner)

**E1. Recommendation: reconcile each amount's number format with the caption (R2).** The unit caption describes what Excel shows. A cell formatted `#,##0,` shows its stored value divided by 1,000. A file captioned "in thousands" whose cells store full amounts under that format is therefore already at full scale, and multiplying again overstates it 1,000 times (probe E1: $110,000,000 for a true $110,000). I recommend R2: no second scaling when caption and format agree, today's scaling when the cells carry no display scaling, an unchanged read with a note when there is no caption, and a refusal naming the cells when caption and formats conflict or are mixed. Existing output changes only for workbooks whose amount cells carry a scaling comma or a `%` format. The change applies to assisted CLI runs, `--mapping` replays and the chat. It applies to the file API only where that API applies caption scaling: `comparisons.py` makes no `detect_unit_scale` call, and Phase 1 checks this. Strict mode reads no captions and is untouched. No existing test changes. The audit records the multiplier actually applied (1.7) and, once 1.9 lands, the reconciliation.

**E2. Recommendation: hidden data rows become a confirmed choice (R3), asked by default.** Today a row the analyst hid in Excel, often a draft or a superseded line, is counted without a word (probe E2: Total Expenses $50.00 against $45.00, including the hidden 5/5 line). I recommend asking, not picking a default. Excel's own `SUM` includes hidden rows and `SUBTOTAL(109, …)` excludes them, so neither default is right for every file. The analyst answers once: with `--hidden-rows include|exclude` on the CLI, with a reply in the chat, through a saved mapping, or through a `hidden_rows` option on the file API, which never prompts and refuses without one. Hidden columns and hidden rows outside the table are listed, not asked about. Existing output changes only for workbooks with hidden data rows, and their CLI runs now stop until the flag is given. **Strict mode** keeps reading every row, as its contract promises; making it refuse too would change a CLI default, and I do not recommend that in this run. No existing test changes. The choice is recorded in audit 1.9.

**E7. Recommendation: a formula with no saved result is its own state and always refuses (R4).** The workbook is read with saved formula results (`data_only=True`), and a formula Excel never calculated has none. Today that reads as a blank: a budget then becomes 0 (probe E7b: Total Revenue $180.00 against a true $160.00 budget), and an Actual says "the amount is blank", which sends the analyst to the wrong fix. I recommend refusing in every column the read uses. The message names each cell and gives the one fix that works: open the file in Excel, let it calculate, and save it. This applies on every path, strict included. Strict mode already refuses these files, so for it only the wording changes, and a driver column now refuses where it silently dropped the driver evidence. `docs/input-contract.md`'s "Missing caches remain missing input values" becomes "…stop intake and name the cells". **Droppable part:** also treat formula results as unsaved when the workbook asks Excel to recalculate on open (`fullCalcOnLoad`), because a producer that sets that flag may have saved stale results. No existing test changes.

## Phase records

### Phase 0

- Read: README, the rules file, `input-contract.md` (amounts, assisted, comparison, PDF and filing EPS sections), `financial-rules.md`, `audit-contract.md` (intro and 1.8), `excel.py`, `models.py`, `measures.py`, `audience.py`, `statement_shape.py`, `numeric.py`, and `intake.py` around `_read_excel_bytes`, `_read_pdf_bytes`, `detect_header_row`, `detect_unit_scale`, `read_input_assisted` and `_process_raw_table`. Also `MULTI_AUDIENCE_2026-10.md`'s interpretation and boundary sections, and the strict and API Excel reads (`parsing.py`, `comparisons.py`).
- Looked at: the E1 probe report states the overstated totals with a confident thousands note. Nothing in the read says the cells were already full-scale. Phase 0 changed no report, workbook or chat reply.

### Phase 3 (2026-10-26)

- **Fresh eyes (STOP 1):** 4 wrong figures in two filings, all headline Total Revenue, from the shaper labeling other income as revenue. They were fixed (Decisions 28-29), the sweep gained a Total Revenue check, and the re-sweep at `69d8366` (sha256 `6805a39a…`; dist gates 2317 passed) has zero wrong figures: 1,041 verified, 13 unverified. Income: 25 of 33 read (76%, 59-87%), 21 fully (64%, 47-78%).
- **Draw A, after the first round (sweep at `3439e0e`, file sha256 `c520ca97…`, in the corpus):** zero wrong line values on both readers. Inline XBRL primary documents: 677 lines verified, 13 unverified, 0 wrong; 20 statements fully read; all 91 refusals plain. These are mostly balance sheets and cash flows, refused until Phase 4, plus 6 non-Inline-XBRL documents. Income statements of the 33 Inline XBRL filings: 24 read (73%, Wilson 95% 56-85%), 20 fully verified and covered (61%, 44-75%), and the other 9 refuse plainly (unmatched subtotals, blank cells). `Financial_Report.xlsx` on the six 2018 filings: 169 verified, 7 unverified, 0 wrong.
- **Before (the baseline):** every `.htm` refused, and the Phase 1 workbook reader produced 15 wrong values (39 under the first scoring).
- Each wrong value or misread found on Draw A became a synthetic fixture before its fix: breakdown sections and binary floats in workbooks; nil prefixes; split, inline and header-table titles; continuation tables; hidden-reference depth; wrapped labels; untagged dashes; breakdown totals; unchecked subtotals.
- Looked at: the chat shows an HTML filing as a Statement (the panel said Worksheet until `13de5e8`), the hidden-rows question with its two answers, and the formula refusal at 1280 and 375 px (screenshots in `docs/analysts/evidence/stop-1/shots/`). Report: an HTML income statement reads at full scale, with the flipped interest-expense note. No workbook changed this phase.

### Phase 2 (2026-10-26)

- Exit: `manifest.csv` holds 40 Draw A rows with per-file sizes and sha256s. The oracle indexes all 39 instances (the 40th filing, an asset-backed 10-K, has no XBRL) with no parse error, and finds all three face statements in 38 filings. The baseline aggregate is `docs/analysts/evidence/draw_A_baseline.json` (seed, tool commit, file checksums, no company or accession).
- Baseline: 116 of 116 primary-document statement runs are refused plainly (the E8 web-page message). The Phase 1 EDGAR-sheet reader on the six 2018 `Financial_Report.xlsx` workbooks reads 5 income statements and refuses 12 balance-sheet, cash-flow and unreadable runs plainly, with 210 lines verified, 15 unverified and **39 wrong**. Those 39 are Phase 3's first work. One visible cause: the workbook stores binary floats, so 78.1 (millions) reads as 78,099,999.99999999.
- Gates: `gates.sh` PASS on all six; `mypy --strict docs/analysts/evidence/` is clean.
- Looked at: this phase changed no report, workbook or chat reply. The corpus run's reports confirm the `.htm` refusal text.

### Phase 1 (2026-10-26)

- **Failing first, per item.** Each item's tests were written and run red before the change: E7 13 failing, E1 12 (+33 format-parser cases on a new module), E2 18, E8 15, E6 1, E3 4, E4/E5 5. The two to four that passed at first were the regression guards (calculated formulas, plain formats, CSV unaffected and so on).
- **Gates at the Phase 1 exit:** `gates.sh` reports ruff, mypy (64 files), pytest **2239 passed**, compileall, pip check and contracts (19 unchanged) all PASS. `git diff 8a609c4 -- tests/fixtures/contracts` is empty. No existing assertion was edited.
- **Probes after Phase 1:** E1 reads Total Revenue $110,000.00 vs $100,000.00. E2 asks, then $45 vs $40 (exclude) or $50 vs $45 (include). E3 reads the statement, Revenue $4.1B vs $3.9B. E4 reads the Q3 2026 band. E5 reads columns A-C and names E-G. E6 compares Sep 2026 with Sep 2025. E7 and E7b refuse, naming the cells and the fix. The renamed `.xls` reads, and the `.htm` refusal names the PDF and `Financial_Report.xlsx`.
- **Looked at.** Report: the E1 report's totals and material rows are at full scale, and the stderr note says why they were not scaled again. Workbook: the E1 `--xlsx` Summary sheet carries 100000/110000, matching the report. Chat reply: the E2 upload asks with two answer chips, and the answer's summary lists the left-out row under adjustments and the hidden row and column under "What I noticed in the workbook". The question uses the error style that the existing comparison-basis stops also use.
- **Friction scorecard for the Phase 1 intake changes** (for REPORT.md; chat path, one probe each):

| Probe | Before: dead end / manual steps / first message | After |
|---|---|---|
| E1 | no / 0 / a read with a wrong ×1,000 total | no / 0 / correct read, note on why it was not scaled |
| E2 | no / 0 / a read counting a hidden row silently | no / 0.5 (one chip) / the question naming row 3 |
| E3 | yes / re-key the statement / header-row message | no / 0 / statement read |
| E4 | yes / delete a band / "more than one Actual column" | no / 0 / newest band read |
| E5 | yes / split the sheet / "more than one Actual column" | no / 0 / first table read, other named |
| E6 | yes / retype headers / header-row message | no / 0 / dates read as periods |
| E7b | no / 0 / a wrong zero budget | yes (correctly: no saved result) / open-and-save / names cell B4 and the fix |
| E8 `.xls` | yes / save as / "Unsupported input format" | no / 0 / read with a rename note |
| E8 `.htm` | yes / unclear / "Unsupported input format" | yes until Phase 3 / upload the PDF or `Financial_Report.xlsx` / names both |
