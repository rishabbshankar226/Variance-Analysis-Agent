# Improvement pass: report

Branch `improve/depth-pass`, cut from `main` at `15100c8`. Nothing is pushed or merged. The plan, every decision and the per-item rules are in [PLAN.md](PLAN.md); the evidence for each stop is under [evidence/](evidence/). This report plays the rules file's Walkthrough (`.agents/rules/variance-intake.md`).

## What changed for Maya

- **No wrong figure on the paths found.** Sixteen ways a report could show a number the file does not support are closed (X1 to X8, X30, X41, X45 to X48, C1, C2). Among them:
  - a footnote mark read as a digit
  - a unit caption applied twice or missed
  - Budget and Actual headings in two units scaled by one multiplier
  - amounts in another currency reported as dollars
  - a chosen period, or columns that run newest first, reading another period's figures
  - a signed ledger's profit lines
  - a rate's tolerance, buffer or headroom read or shown in the wrong unit

  Each one refuses plainly or reads the figure right, with a test.
- **Fewer dead ends.** Over the 24 runs of Phase 1's fictional files, 6 ended with no way forward; now 2 do (an uncalculated formula, which refuses on purpose, and a date band merged over Budget and Actual, left open). Merged headers, section headings, "Budget ($000)" headings, two-row headers and bare-year bands now read.
- **Every refusal says what to do.** All 233 intake messages a chat reader can see are plain and give the next step; before, 44 of 235 failed the rules file's checks.
- **New workbooks and a batch run.** Export Excel and `--xlsx` now write a workbook for limit, benchmark, target, balance sheet, cash flow and filing income comparisons, where they refused, and those results offer it as a chip. `--batch` reads a folder of filings in one command, with a manifest row per filing.
- **Nothing else moved.** The 19 contract fixtures (9 reports, 5 audits and their 5 inputs), audit schemas 1.0 to 1.9 and the financial rules are unchanged.

## Items

Every item in the approved backlog, with its final state. "What it became" is the item's commit subject, or the reason it is left open.

| Item | Phase | State | What it became | Commits |
|---|---|---|---|---|
| T1 | 0 (Phase 6 item) | done | Count the work an unmatched question does instead of timing it | `63162aa` |
| X1 | 2 | done | Refuse a footnote mark beside an amount instead of reading it as a digit | `85b9e52` |
| X2 | 2 | done | Read scorecard workbooks as printed, from stored decimals | `e87c1d6` |
| X3 | 2 | done | Read a PDF statement's unit caption on the title line or without parentheses | `dcac927` |
| C2 | 2 | done | Apply the unit caption once on the earnings, quant and file-API paths | `3cc1a93` |
| C5 | 2 | done | A zero total is Neutral, in line with budget, in every chat handler | `bb29038` |
| X4 | 2 | done | Read every common unit caption, and never 'in M&A' | `75d0e09` |
| X5 | 2 | done | Never report amounts marked in another currency | `a4b3f0e` |
| X6 | 2 | done | A chosen period reads its own Budget and Actual columns | `6991da0` |
| X7 | 2 | done | Turn a signed ledger's profit lines with revenue when that adds up | `97a00b9` |
| X8 | 2 | done | Refuse what the comparison path cannot do; a filing keeps its printed totals | `6cd2d81` |
| C1 | 2 | done | Strict and assisted agree on uncached formulas in a computed column | `52ba872` |
| C3 | 2 | closed | Did not reproduce as a tolerance defect: the subtotal holds under R5 and the refusal is a sign ambiguity; the message part is C3m. | `6851252` |
| C3m | 3 | done | A filing refusal names the line whose sign the printed figures can't tell | `3e7c966` |
| X30 | 2 | done | Never report amounts marked in another currency | `a4b3f0e` |
| X41 | 2 | done | A unit caption scales a Currency row's Buffer and Tolerance with its amounts (asked as a STOP-ASK, approved at STOP 2) | `bc392a7`, `3938eb9` |
| X9 | none | open | Hosted mode shares one session between visitors; the per-visitor-sessions branches own it (Decision 9). | none |
| X10 | 3 | done | --no-browser keeps the chat local even where RENDER is set | `b98c4d2` |
| X11 | none | open | Staged downloads sit under guessable names; owned with X9 by the per-visitor-sessions work. | none |
| X12 | 3 | done | Cut off a request body that arrives too slowly; its test reads the whole 408 reply and bounds the drip by bytes | `a563ca2`, `5b7f793` |
| X13 | 3 | done | No output may overwrite --compare-file, --ltm-from, --metrics or --panel | `4d770a8` |
| X14 | 3 | done | A comparison audit that needs 1.9 is written at 1.9 | `78f413f` |
| X15 | 3 | done | Read a .tsv with --assisted, and name every format that works | `f439e6c` |
| X16 | 3 | done | Leave out section heading rows with a note, not as blank amounts | `4945550` |
| X17 | 3 | done | List and switch the sheets of an .xls workbook in the chat | `ebd3f5e` |
| X18 | 3 | done | The comparison path knows every header name assisted intake knows | `c3d1d4e` |
| X19 | 3 | done | Only an upload that replaces the file discards what belonged to it | `3daac41` |
| X20 | 3 | done | A zero under a scaled Accounting format no longer stops the run | `e4ea82e` |
| X21 | 3 | done | After one half of a pair, a whole file or the same half never traps the reader | `4661ee4` |
| X22 | 3 | done | A total that doesn't match its lines is named with its figures, and can be left out | `f4ae7f3` |
| X23 | 3 | done | Read 'Budget ($000)' and other amount headings with a unit or currency | `05318af` |
| X24 | 3 | done (date band open) | Read a header split over two rows. The merged date band stays open. | `f33241e` |
| M1 | 3 | done | A filing without statement tables names the document to upload next | `568c4af` |
| M2 | 3 | done | A statement that runs on into an untitled table says so when it fails | `433f5bb` |
| M3 | 3 | done | Bare-year bands (2025 / 2026 over Budget/Actual) are period bands | `afae8ab` |
| X25 | 3 | done | '~' in a local export path is the home folder | `7f85c93` |
| X26 | 3 | done | Only an upload that replaces the file discards what belonged to it | `3daac41` |
| X27 | 3 | done | The chat says 'not yet labeled revenue or expense', never 'Unclassified' | `024c371` |
| X28 | 3 | done | A mapping file that is not JSON says so, with its line and column | `a75f0d7` |
| X29 | 3 | done | --check-only refuses --long-output and --long-output-jsonl too | `ea42235` |
| X31 | 3 | done | Read a Percent cell Excel shows as a percentage as that percentage | `338b199` |
| M4 | 3 | done | A filing column's duration shows in its headings, and every key keeps the label (asked as a STOP-ASK, approved at STOP 2) | `49e2cc9`, `4eaf602`, `a00ddf0` |
| M5 | 3 | done | Say which numbered copy of a repeated filing label is which | `83c0b48` |
| C4 | 3 | done | A line among costs that is a loss in a compared year is not called a credit | `cabc424` |
| M6 | 3 | done | A script lists every intake message and checks it by the rules file; every message a chat reader sees is plain and gives the next step | `cf2f548`, `d8542ff`, `a23a953`, `1a78954` |
| X35 | 3 | done | Offer the period a file's title names as a chip | `4473b5d` |
| X36 | 3 | done | Offer to read lines the comparison file lacks as 0 in a two-file join | `ff8abcb` |
| X42 | 3 | done | A measure report and audit say how assisted intake read the file | `77fbfcb` |
| X43 | after the final STOP | done | A scaled amount shows its cents, not the caption's trailing zeros (Decision 19) | `bc9bd49` |
| X44 | 8 | done | The sdist leaves out this run's review evidence, as it does the others' (found in Phase 8) | `226a82e` |
| X45 | 8 | done | Amount headings in different units refuse instead of sharing one multiplier (found in Phase 8, STOP-ASK) | `6c87e91` |
| X48 | 8 | done | A file with a pair per period reads the pair named, else the newest (found in Phase 8, STOP-ASK); on the command line, `--period` also picks a band workbook's band | `6c935e3`, `6dd312a` |
| X46 | 8 | done | A percent-formatted Tolerance or Buffer reads as the percentage Excel shows (found in Phase 8, STOP-ASK) | `88fa7c5` |
| X47 | 8 | done | A Percent limit row shows its headroom and buffer in basis points (found in Phase 8, STOP-ASK) | `27a9bf4` |
| X49 | after the final STOP | asked | A unit named only by a heading that isn't Budget or Actual ("Headcount (000s)") scales the amounts: STOP-ASK, not fixed | none |
| X50 | after the final STOP | asked | A statement's "Basic EPS" and "Diluted EPS" lines are read as money and scaled by its caption: STOP-ASK, not fixed | none |
| X51 | after the final STOP | done | Limit, statement and filing results offer the Export excel chip (Decision 19) | `118010d` |
| X52 | after the final STOP | done | A long note in a results panel wraps on a phone (Decision 19) | `c70c5ac` |
| X32 | 5 (done in 7) | done | Sheets with percentage cells say how a tie rounds; no cell value changes (done in Phase 7) | `6c13d36` |
| X37 | 4 (done in 7) | done | Remove an unused constant and a branch that repeats its neighbour (done in Phase 7) | `51e1de8` |
| X33 | 7 | done | The README names audit 1.9 and what a long output does to a plain run | `c43b49f` |
| X34 | 7 | done | The input contract says --mapping reads limit, benchmark and target bases | `00db697` |
| X38 | none | open | Four copies of the number grammar and workbook helpers, with drifted messages; recorded, not this run. | none |
| X39 | none | open | `export excel` on a 4.28 MiB CSV takes the hosted server from 49 to 559 MiB; recorded, not this run. | none |
| X40 | none | open | The hosted build installs the newest reader dependencies; pinning is a dependency change, left to the owner. | none |
| S1 | 4 | done | `chat/handlers.py` becomes the package `chat/handlers/`, 17 modules, with the E501 exemption gone | `43733b4`, `3bc6c0a`, `45834f6`, `d59c8fa`, `ef868ae` |
| S2 | 4 | done | `_process_raw_table` splits into named stages, each under 80 lines | `6dfcc95`, `dba3a7b` |
| S3 | 4 | done | `cli._run` splits into parse, read, analyse and write stages | `c46dd7e`, `eefa968` |
| S4 | 4 | done | `_handle_what_if`, `build_audit_record`, `_handle_executive_memo`, `analyze_rows`, `_handle_compare`, `read_comparison_input`, `shape_income_statement` and `_read_excel_bytes` split, each new function under 80 lines | `a9c3713`, `ce0bb2b`, `57d37c5`, `efa75ff`, `52b120d`, `53d13a9`, `0b25455`, `4c74e90` |
| N1 | 5 | done | A workbook for limit, benchmark, target, covenant, statement and filing income comparisons; a filing's Change % reads the audit's stored figure | `27c13f9`, `154337b`, `c3793f6`, `5e8ccc7`, `9dd88db` |
| N2 | 5 | done | `--batch FOLDER --manifest FILE`: every filing in a folder read as a single run, with one manifest row per filing. It also needs `--long-output`, `--period` and the thresholds | `059a2d6`, `fa85643` |
| T2 | 6 | done | Three tests kill Phase 1's three surviving mutants; the 25 probes re-run with none surviving | `2038d4a`, `4d4affe` |
| T3 | 6 | done | The one test over 5 seconds reads 4,000 rows instead of 10,000 and still catches both regressions it guards | `1a604e8` |
| D1 | 7 | done | The eight earlier records move to `docs/history/`, with an index, and every link is fixed | `8604d1d` |
| D2 | 7 | done | The roadmap records what this pass closed and what stays open | `5e8a0fc` |
| D3 | 7 | done | Every README command runs from a clean clone; nothing to fix | `32dfd03` |

Items that ran out of their phase's order:
- X32 and X37 were missed in their own phases (5 and 4) and done in Phase 7, after T3 and D1.
- N1's and N2's docs (`154337b`, `fa85643`) came after X33 and X34.
- N1's Change % test and fix (`c3793f6`, `5e8ccc7`) came after D2 and D3, and its two exact-text checks (`9dd88db`) after the Phase 8 review.
- X44 to X48 were found in Phase 8. X45 to X48 were STOP-ASKs, approved on 2026-11-03.
- X43, X51 and X52 were done after the final STOP, under Decision 19, and X49 and X50 were found then and asked.

Every other item ran in its phase's order.

## Revert proofs

For every C, M, X and T1 fix: the fix removed with its tests kept, and what failed. Doc items (X33, X34) carry none. X37 removes code that nothing reaches: `_MISSING_MARKERS` has no reference in `src`, tests, scripts or `deterministic_conditioning`, and the merged branch sits after `_what_if_target`'s guard (`chat/handlers/scenarios.py:229`), which answers an Unclassified line before any simulation, so no test can fail on its revert. S items carry a characterization, an `ast.dump` check and a fresh-eyes review instead ([PLAN.md, Phase 4 reviews](PLAN.md)); T2 carries its recorded mutants.

Each proof ran when its fix landed. Phase 4 moved the code around X6, X10 and X41, so their saved diffs no longer reverse at HEAD. At `48614d5`, X6 and X10 were reverted by hand and gave the results below ("2 failed, 3 passed" and "1 failed, 5 passed"). X41 was not re-run at HEAD.

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
| X32 | `_ROUNDING_NOTE` and its four uses in `xlsx.py` removed (`git apply -R` of the `src` diff), tests and goldens kept | `pytest tests/test_workbook_rounding_note.py tests/test_xlsx.py` | 5 failed, 21 passed: the four sheets that should carry the note do not (the Summary's last two cells are `[None, ...the existing note]`), and the sample golden lacks Summary A18. The benchmark and target cases pass either way, as they should |
| X44 | the sdist exclude not yet added (the sdist built at `7049fac`), with the gate's new assertion | `python scripts/check_distribution.py .scratch/dist-final` | `AssertionError: docs/improve/evidence in the sdist`; with the exclude, the rebuilt sdist passes |
| X45 | `heading_unit`, `_heading_units`, `_heading_units_differ` and their use in `_unit_scale` removed (`git apply -R` of the `src` diff), tests kept | `pytest tests/test_header_unit_conflicts.py` | 9 failed, 7 passed: the five mixed-unit files and the title-against-heading file read with one multiplier and don't refuse; two "(USD m)" headings read 250 and 275 unscaled; "($ in millions)" over two "($000)" headings reads millions; and the command line writes the report. The 7 that pass are the same-unit, title-over-bare, "($)" beside a bare heading, "(USD)" and half-file controls |
| X48 | `chosen_period_pair` and its two uses in `intake.py`, and `_named_pair_read` and its two uses in `cli.py`, removed (`git apply -R` of the `src` diff), tests kept | `pytest tests/test_period_pair_choice.py tests/test_intake_comparison.py::test_wide_fiscal_year_layout_stays_budget` | 8 failed, 6 passed: newest-first 2026, Sep 2026 and FY2026 files read the older pair, under the `--period` heading too; `--period jan-26` reads Feb-26; Jan-26 and Feb-26 under `--period "Feb 2026"` exit 0 with Feb-26's figures; and the edited FY test reads FY2024. The 6 that pass are the ascending, unordered and chosen-period controls, `--period 2025` and `Feb-26` (each already the last pair), and the mapping's period |
| X48, bands | `_named_pair_read` made to return what intake read (a hand edit, reversed from its saved diff), test kept | `pytest tests/test_period_pair_choice.py -k band` | 1 failed, 2 passed: `--period "Q2 2026"` on a band workbook reads Q3's $100.00 and $110.00 under the Q2 heading. `Q3 2026` and a `--period` that names no band read Q3 either way |
| X46 | `percent_points` and the declared-cell reads in `_apply_measure` and `_percent_as_shown` removed (`git apply -R` of the `src` diff), tests kept | `pytest tests/test_percent_declarations.py` | 13 failed, 4 passed: both readers keep 0.0025 and 0.005 as stored; the Fraction oracle fails for every nonzero value; every target row shows a tolerance a hundredth of its size ("0.25 bps" for 25 bps); and the two Near limit rows read Within. The 4 that pass are the General-cell and Currency-row controls, the zero value, and the 0.0029 row, which is Within either way |
| X47 | `spread` and its two uses in `basis_table` removed (`git apply -R` of the `src` diff), tests kept | `pytest tests/test_limit_rate_units.py` | 4 failed, 1 passed: the three Percent rows show "1 bps", "-0.5 bps" and "-0.25 bps" of headroom and "0.5 bps" buffers, and the Limits sheet reads "1 bps" and "0.5 bps". The Currency row passes either way |
| X43 | `_places` and its two uses in `format_measure` removed (`git apply -R` of the `src` diff), tests kept | `pytest tests/test_money_places.py` | 5 failed, 5 passed: 89999.000, 1.230 per share, 0.000 and -10.500 show their stored trailing zeros ("$89,999.000"), and the captioned limit row reads "$89,999.000". The 5 that pass hold no trailing zeros past the cents |
| X51 | the chip removed from `_basis_summary`, `_STATEMENT_CHIPS` and `_filing_summary` (`git apply -R` of the `src` diff), tests kept | `pytest tests/test_export_excel_chip.py` and the two edited tests | 5 failed: a limit, a balance sheet and a filing's income statement offer only Export report and Export audit, and both edited checks fail on the missing chip |
| X52 | the `.view-section .facts` column put back to `max-content` (`git apply -R` of the `src` diff), test kept | `pytest tests/test_interface_design.py -k long_note` | 1 failed: the rule reads `1fr max-content`. The phone shots before and after (`evidence/phase-8/`, `evidence/phase-8/x51-x52/`) show the same screen cut off, then wrapped |

## Before and after

| Figure | Before | After |
|---|---|---|
| Functions in `src/` (an `ast` walk, `.scratch/size_table.py`) | 732 | 873 |
| Functions over 80 lines | 36 | 26 |
| Functions over 150 lines | 9 (longest `_process_raw_table`, 477) | 0 (longest `_read_ixbrl_bytes`, 149) |
| `chat/handlers.py` | one module of 5,082 lines | the package `chat/handlers/`, 17 modules |
| Message inventory: intake messages a chat reader sees | 235 seen, 10 with jargon, 37 of 86 errors with no fix, 44 failing: the final scanner run on `d8542ff`'s source, before M6. The scanner as frozen before M6 gave 228 seen, 17 with jargon, 34 of 82 with no fix and 48 failing at `ff8abcb` (PLAN.md, Decision 15) | 233 seen, 0 with jargon, 0 errors with no fix, 0 failing, at `c70c5ac`. The scanner does not see X45's refusal, which a helper builds; its three forms were checked with the scanner's own rules and pass. X48's refusal is the command line's own |
| Test strength: Phase 1's 25 seeded mutants | 3 survive (`63162aa`) | 0 survive |
| Suite | 2505 passed in 48.53s (Phase 0) | 2882 passed in 47.40s at `c70c5ac`, at load average 19.2 to 11.1 from processes not this run's; 2810 passed in 51.82s in D3's clean clone |
| Slowest test (the worksheet-scan memory test) | about 10 s run alone; 21.94 s in the suite at load average 5.66 (`8a558f4`) | 2.87 s run alone; 7.68 s in the suite at load average 16.16 (PLAN.md, Phase 6 figures) |
| Maya's 24 runs over Phase 1's fictional files | 6 dead ends, 18 analyses | 2 dead ends, 22 analyses (at `7049fac`; re-run at `ebd1912` and `c70c5ac`, all 31 rows the same) |
| Contract fixtures and audit schemas | 19 files; 1.0 to 1.9 | the same bytes (`git diff main -- tests/fixtures/contracts schemas` is empty) |
| sdist, built by `python -m build` | 6,627,852 bytes (with this run's evidence) | 1,946,420 bytes after X44; 1,977,950 bytes at `c70c5ac` (the wheel 447,706) |

The suite's duration could not be measured on a quiet machine: other projects' processes held the load average between 5 and 34 through Phase 8, so the durations do not compare.

## Assertions edited

Every existing assertion, golden or snapshot this run changed. Each was listed in PLAN.md before the edit, except S1's change to the glyph check, which PLAN.md recorded only after it (its row says so). No test was deleted.

| Test | Assertion | Reason |
|---|---|---|
| `tests/test_chat_hardening.py::test_unmatched_questions_on_a_big_file_stay_fast` (7 cases) | `assert time.perf_counter() - start < 0.5` is replaced by the work counts of Decision 7. `assert response.text` stays. | T1. The bound failed under load. Measured here: 5 of 7 cases failed on each of two runs beside 64 CPU-bound processes. The work counts pin the same fix without a clock. |
| `tests/test_interface_design.py::test_status_words_mirror_the_servers_map` | the page shows `'Unclassified'` as `{"word": "Unclassified", "tone": None}`; it becomes `{"word": "Not yet labeled", "tone": None}` | X27 (approved at STOP 1). The test checks that the page's word map mirrors the server's `status_label`, and X27 changes that label. Its mirror check stays as it is. |
| `tests/test_ixbrl.py` (the declared-entity refusal, line 200) | the expected text "'hal-20250927.htm' declares an XML entity or document type subset, which this reader refuses. " becomes "'hal-20250927.htm' declares entities of its own, which filings on EDGAR don't, so this reader refuses it. " | M6: "XML" is a forbidden word in the rules file; the refusal and its fix are otherwise unchanged |
| `tests/test_excel_archive_hardening.py::test_a_dtd_after_a_long_prolog_comment_is_still_refused` and `::test_a_dtd_straddling_a_read_boundary_is_still_found` | `pytest.raises(ValueError, match="DTD")` becomes `match="declares entities of its own"`; each test still asserts the declaration is refused | M6: "DTD" is a forbidden word in the rules file |
| `tests/test_pdf_intake.py::test_unknown_statement_lists_the_ones_found` | the expected refusal gains its last sentence, " Choose one of those statements." | M6: the refusal named the statements but gave no step; the same refusal for a filing already ends so (intake.py, the Inline XBRL path) |
| `tests/test_filing_headlines.py::test_consecutive_52_53_week_years_are_named_by_their_end_month_not_as_a_gap` | "Read the column for 2026-01-03 as Jan 2026" becomes "Read the column for the 12 months ended 2026-01-03 as Jan 2026"; the label "Jan 2026" and the no-"FY2026" assertion stay | M4: the note names a duration labelled by its end month |
| `tests/test_multi_audience_api.py::test_new_public_signatures_and_legacy_constructors` and `tests/test_multi_audience_measures.py::test_existing_public_constructors_and_functions_keep_their_parameters` | `AnalysisConfig`'s pinned parameters gain a trailing `"comparison_name"`; the seven existing names keep their order | M4: a trailing keyword with a default, so every existing call, positional or by name, works as before |
| `tests/test_bases.py::test_a_limit_run_refuses_a_workbook`, renamed `test_a_limit_run_writes_its_workbook` | the refusal (`SystemExit`, "--xlsx isn't available for a limit ...") becomes exit 0 and a workbook whose only sheet is "Limits" | N1: the workbook this comparison now gets |
| `tests/test_comparison_path_guards.py::test_a_filing_workbook_refuses_on_the_comparison_path`, renamed `test_a_filing_workbook_on_the_comparison_path_has_its_own_sheets` | the refusal and "no workbook written" become exit 0 and the FP&A sheets with a Summary headed by the filing's totals | N1, on the comparison path too |
| `tests/test_filing_headlines.py::test_the_workbook_refuses_for_a_filings_income_statement`, renamed `test_the_workbook_for_a_filings_income_statement_is_written` | `SystemExit` and "no workbook" become exit 0 and the four sheets | N1 |
| `tests/test_filing_headlines.py::test_the_chat_offers_no_workbook_for_a_filing`, renamed `test_the_chat_exports_a_filings_workbook` | the refusal text becomes "Excel workbook ready for download: Summary, Material Variances, Root Causes & Actions, and All Rows sheets."; the chips assertion stays. N1 wrote the new check as a prefix (`startswith`), looser than the exact text it replaced; `9dd88db` restores the exact check | N1 |
| `tests/test_ixbrl_statements.py::test_the_cli_refuses_a_workbook_for_a_statement_comparison`, renamed `test_the_cli_writes_a_statement_workbook` | the refusal becomes exit 0 and a workbook whose only sheet is "Lines" | N1 |
| `tests/test_ixbrl_statements.py::test_the_chat_compares_a_balance_sheet_without_asking_for_labels` | its last assertion, the refusal text, becomes "Excel workbook ready for download: Lines sheet."; every other assertion stays. Written as a prefix by N1, as above, and made exact again by `9dd88db` | N1 |
| `tests/test_xlsx.py::test_every_value_and_address_is_unchanged_by_the_redesign[sample]` (its golden `tests/fixtures/xlsx_values/sample.json`) | the Summary sheet gains one entry, the X32 note in the row after the existing note; every other address and value stays | X32 (approved at STOP 1, BACKLOG question 5): the golden pins every cell of the sample workbook, so a new note row is a new entry. `consensus.json` and `comparison_set.json` are comparison workbooks and do not change |
| `tests/test_characterization_s3.py::test_every_documented_command_runs_as_before_the_split` (its snapshot `tests/fixtures/characterization/s3_cli.json`) | one value: the README quick start's `reports/q3-2026.xlsx` part `xl/worksheets/sheet1.xml` (the Summary sheet) takes its new digest; every other command, file and part stays | X32: the snapshot pins each written workbook part's digest, and the Summary gains the note's row. Found by the full suite after the fix, and listed here before the snapshot was edited |
| `tests/test_excel_archive_hardening.py::test_the_worksheet_scan_keeps_little_beyond_the_numbers_it_returns` | no assertion changes: `peak < 1.3 * budget` stays. Its sheet shrinks from 10,000 rows of 10 to 4,000 rows of 10, and the comment records why that size still pins the bound | T3: 21.94s in the suite, the only test over 5 seconds, almost all of it tracemalloc tracing 100,000 cells. `.scratch/t3_probe.py` puts back the two regressions the test guards (the per-cell coordinate set `405b2fd` removed, and the worksheet read whole before parsing) and measures peak over kept. Python 3.11, 10,000 rows: clean 1.108, set 1.398, whole read 1.352. 4,000 rows: 1.128, 1.527, 1.390. Python 3.14, 4,000 rows: 1.135, 1.589, 1.559. At 4,000 rows both regressions miss the 1.3 bound by more than at 10,000, and the clean scan stays under it. At 1,000 rows the clean scan reaches 1.307 and fails, so the sheet stops at 4,000 |
| `tests/test_interface_design.py::test_reply_text_built_by_chat_has_no_glyphs` (9 cases) | no assert line changes. `3bc6c0a` takes the cases from `_chat_modules()` and the text from `_chat_source(module)`, which reads a package (`chat/handlers/`) whole under its old module's name; the 9 case ids and the count stay | S1: without it, the check would stop reading the handler code the move put in a folder. Recorded in PLAN.md only after the commit, which the Phase 8 REPORT reviewer found |
| `tests/test_intake_comparison.py::test_wide_fiscal_year_layout_stays_budget` (and its helper) | the FY2025-then-FY2024 file's expected pair, FY2024 (Budget 3, Actual 4), becomes FY2025 (Budget 1, Actual 2); the helper takes the expected amounts as arguments, defaulting to 3 and 4, and the basis checks stay | X48 (Decision 18): the file runs newest first, and the test pinned the last pair by position, the cause X48 removes |
| `tests/test_filing_headlines.py::test_the_chat_exports_a_filings_workbook` | `assert "Export Excel" not in (reply.chips or [])` becomes `assert reply.chips is not None and "Export excel" in reply.chips` | X51 (Decision 19): it pinned the chip as absent; its capitalised spelling would have passed vacuously beside the lower-case chip |
| `tests/test_ixbrl_statements.py::test_the_chat_compares_a_balance_sheet_without_asking_for_labels` | `reply.chips == ["Export report", "Export audit"]` becomes `["Export report", "Export excel", "Export audit"]` | X51 (Decision 19): the statement result now offers its workbook |

## Friction scorecard

Each fixture driven through the chat as Maya would, by Phase 1's policy (`evidence/stop-3/scorecard/drive.py`: a chip where one is offered, "Q3 2026" typed for a period question). A typed answer counts 1 step, a chip 0.5, a confirmation 0. The policy was extended by one rule only, for X22's new offer: Maya clicks "Leave ... out" (0.5). Before is `main` at `15100c8` in a detached worktree; after is `7049fac`. Script, policy, file builder and rows: [evidence/stop-3/scorecard/](evidence/stop-3/scorecard/), with the steps to reproduce in [its README](evidence/stop-3/README.md).

The M items, per fixture:

| Item | Fixture | Dead end, before → after | Steps to analysis | First message shown, before → after |
|---|---|---|---|---|
| M1 | `hal-elsewhere-20250927.htm` | yes → yes | none | "I could not find the financial statements in '…': no table there is titled as an income statement, balance sheet or cash flow statement" → "The financial statements aren't in '…' itself: it points to Exhibit 13 ('fake-20261231ex13.htm'), the annual report that holds them. Up[load that document]" |
| M2 | `hal-runs-on-20250927.htm` | yes → yes | none | "I couldn't find both total assets and total liabilities and equity in the Consolidated Balance Sheets, so I can't check that it balances…" → "The Consolidated Balance Sheets seems to run on into the next table, which shows other periods, so I couldn't read it whole and stopped instead of guessing. Up[load …]" |
| M3 | `years.xlsx` | yes → **no** | none → 1.5 | "Found more than one Actual column (Actual (column D), Actual (column F)); keep one and try again." → the intake summary |
| M4 | `hal-20260328.htm` (a 10-Q) | no → no | 2.0 → 2.0 | the intake summary, both; its headings now read "3 months ended Mar 2026" |
| M5 | `hal-copies-20250927.htm` | no → no | 2.0 → 2.0 | the intake summary, both; it now says which numbered copy of a repeated label is which |
| M6 | `empty.csv` | yes → yes | none | "The file 'empty.csv' contains no data." → the same, then "Upload a file with a header row (such as Line Item, Budget, Actual) and at least one line." |
| M6 | `no_header.csv` | yes → yes | none | "Could not find a header row with Line Item, Budget, and Actual columns in 'no_header.csv' (…)" → the same, then "Add a heade[r row …]" |

A refusal stays a dead end in the chat's flow; what changed for M1, M2 and M6 is that it now names the cause and the next step. Maya's 24 runs, the files that changed:

| File | Before | After |
|---|---|---|
| `f01_title_block.xlsx` | analysis, 2.5 steps | analysis, 2.0 |
| `f03_thousands_caption.xlsx` | analysis, 2.0 | analysis, 1.5 |
| `f09_merged_header.xlsx` | dead end ("Could not find a header row …") | analysis, 2.0 |
| `f14_realistic_combo.xlsx` | analysis, 4.0 | analysis, 2.5 |
| `f19_signed_subtotals.xlsx` | analysis, 3.0 | analysis, 2.0 |
| `f20_rounded_thousands.xlsx` | dead end after 2.0 | analysis, 2.0 (X22's "Leave Total Opex out") |
| `f21_section_headers.xlsx` | dead end ("I could not read every amount …") | analysis, 2.0 |
| `f24_header_000.xlsx` | dead end ("Could not find a header row …") | analysis, 2.0 |

Still dead ends: `f08_formula_no_cache.xlsx` (an uncalculated formula refuses by rule R4, naming the cell) and `f17_date_headers.xlsx` (X24's merged date band, open). The step counts measure Maya's clicks, not whether each figure is right. Phase 1 traced the wrong figures it found in f14 and f19 to X7 and in f23 to X6; both are done, each with a test on a synthetic file of the same shape.

## Stops and decisions

- **STOP 1 (2026-11-02):** the owner approved the backlog as recommended. M1 names the second document rather than reading it; X32 states the rounding on the sheet; X40 is left to the owner; X9 and X11 stay with the per-visitor-sessions branches.
- **STOP-ASK X41** (`evidence/stop-ask-buffer-scale/`): a unit caption left Buffer and Tolerance unscaled. Approved at STOP 2: scale them with the amounts.
- **STOP-ASK M4** (`evidence/stop-ask-m4-period-labels/`): a 10-Q's column label is also the audit's key. Approved at STOP 2: the duration goes into display names only, and every key keeps its label.
- **STOP 2:** the owner approved S1 to S4 (with `_handle_executive_memo` added to S4), N1, N2 and X42 as recommended.
- **STOP-ASKs X45 to X48** (`evidence/stop-ask-heading-units/`, `stop-ask-percent-declarations/`, `stop-ask-limit-rate-units/`, `stop-ask-period-pair/`): four wrong numbers the Phase 8 reviewer found, none on a 0.2.0 path. The owner answered "Approve all four" on 2026-11-03, so each took its recommendation (Decision 18).
- **After the final STOP**, the owner answered "do what you recommend and continue" (Decision 19). That covered the items the final STOP left open and named: X43, the Export excel chip (X51) and the mobile notes (X52), all done. Reproducing the two wrong numbers the Phase 8 reviewer had suspected found both. They are STOP-ASKs under the owner's own rule, not fixed:
  - **X49** (`evidence/stop-ask-other-heading-units/`): a "Headcount (000s)" heading scales a $250,000 budget to $250,000,000, on the branch and on `main`.
  - **X50** (`evidence/stop-ask-eps-lines/`): a statement's "Basic EPS" of 6.10 under "$ in Millions" shows as $6,100,000.00, on the branch and on `main`.
- Two STOP-ASKs are open, X49 and X50. No dependency, CLI default, contract fixture, audit schema or financial rule changed.
- The decisions taken along the way are PLAN.md's Decisions 1 to 19.

## Gates at `c70c5ac`

The summary lines, as printed in [evidence/stop-3/gates.txt](evidence/stop-3/gates.txt) (`.scratch/gates/final.sh`). The commits after `c70c5ac` change only docs: REPORT.md, the CHANGELOG, the inventory's commit stamp and the final STOP's evidence.

```
ruff check .                     All checks passed!
mypy --strict src/variance_agent scripts deterministic_conditioning
                                 Success: no issues found in 90 source files
compileall -q src tests scripts deterministic_conditioning
                                 exit 0
pytest -q                        2882 passed in 47.40s
pytest -q -k contract            181 passed, 2701 deselected in 4.72s
pip check                        No broken requirements found.
build                            Successfully built variance_analysis_agent-0.3.0.tar.gz and variance_analysis_agent-0.3.0-py3-none-any.whl
twine check                      PASSED (wheel), PASSED (sdist)
check_distribution.py            Wheel/sdist contents, license, Python support, and entry point verified
minimal install (Python 3.11):   Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified
                                 No broken requirements found.
contracts and schemas vs main    identical
size table                       functions=873 over80=26 over150=0
```

D3 ran every README command from a clean clone at `5e8a0fc`; all exit 0 except the panel run's documented 3.

## Screenshots

- Phase 3: 91 screenshots of 26 scenarios, every chat screen Phases 2 and 3 changed, in `evidence/phase-3/` (light theme, desktop and mobile).
- Phase 5: 16 screenshots of the three export replies N1 changed (a limit run, a balance sheet and a filing's income statement), in `evidence/phase-5/`.
- Phase 8: 7 screenshots of the three chat screens X45, X46 and X47 changed (the mixed-unit refusal, a target row's 25 bps tolerance, and a limit row's headroom and buffer in basis points), in `evidence/phase-8/`. X48 leaves the chat's screens as they were: the chat asks which period when a file has more than one pair.
- After the final STOP: 5 screenshots of the same two results screens with X51's chip and X52's wrapped notes, in `evidence/phase-8/x51-x52/`.

## Draw G

Draw G: not measured. The corpus `~/vaa-edgar-corpus` exists, but `EDGAR_USER_AGENT` is unset, and it is the owner's to set; no SEC request was made.

## Not verified

- The Windows output-contract job, and Python 3.12 to 3.14 (apart from T3's measurement on a local 3.14): not run. CI runs them, but the branch has never been pushed, so CI has not run on it.
- Real Excel. The workbooks were read back with openpyxl, and X32's tie was rendered in LibreOffice 26.8.1, not Excel.
- Safari and Firefox. The screenshots are Playwright's Chromium.
- Real analysts. The scorecard is a scripted policy over fictional files.
- Draw G, above.
- Hosted mode on Render: not exercised by this run.

## Left open, for the owner

- **X9, X11:** hosted mode shares one session, and staged downloads sit under guessable names. The per-visitor-sessions branches own both.
- **X24's merged date band:** "Could not determine period order for Sep 2026, Sep 2026." (`f17_date_headers.xlsx`).
- **X38, X39, X40:** duplicated number grammar; `export excel`'s memory on the free plan; the hosted build's unpinned dependencies.
- **X49 and X50, asked:** two wrong numbers, both on `main` too, each with its evidence and a recommendation (Stops and decisions, above). They wait on the owner's answer.

## PR description

**Improvement pass: wrong numbers, dead ends, structure, two features, tests and docs**

What changed:
- Sixteen ways a report could show a figure the file does not support now refuse plainly or read the figure right. Four of them were found by a final review and fixed with the owner's approval.
- Six of Maya's 24 sample runs used to stop with no way forward; two still do. Every message a chat reader sees says what to do next.
- Export Excel works for limit, benchmark, target, balance sheet, cash flow and filing income results. A new batch run reads a folder of filings in one command.
- The largest functions are split (none over 150 lines), and the chat's handler module is now a package. Four fresh-eyes reviewers, one per refactor item, found no behaviour change.
- Tests: a timing test that load can't break, every seeded mutant killed, and the one test over 5 seconds now under 3 seconds alone.
- Docs: earlier audit records moved to `docs/history/`; the README, input contract and roadmap describe what the tool does now.

Unchanged: the 19 contract fixtures (9 reports, 5 audits and their inputs), audit schemas 1.0 to 1.9, the financial rules and every default. No dependency was added.

Open: two wrong numbers found at the very end, X49 and X50, both also on `main`, wait on the owner with their evidence.

Not verified: the Windows CI job, real Excel, Safari and Firefox, real analysts, and Draw G (`EDGAR_USER_AGENT` unset).

Details, revert proofs and every edited assertion: `docs/improve/REPORT.md`.

Generated with [Claude Code](https://claude.com/claude-code)
