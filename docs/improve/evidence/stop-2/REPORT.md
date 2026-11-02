# STOP 2: what Phases 2 and 3 changed

Branch `improve/depth-pass`, in the main clone. Nothing is pushed. To review everything since STOP 1's evidence, run `git log -p a80f81f..improve/depth-pass` (49 commits, this report included). Status, Decisions, rules and figures are in [`docs/improve/PLAN.md`](../../PLAN.md).

## Phase 2: wrong numbers

| ID | What a reader now sees |
|---|---|
| X1 | A footnote mark beside an amount (`950¹`) stops intake and names the cell, instead of reading as 9,501. |
| X2 | Scorecard weights from a `0.00%` Excel cell read as printed (12.4%), not 100 times too small. |
| X3 | A PDF statement's "(In millions)" on the title line, or without parentheses, scales the figures. |
| C2 | The earnings, quant and file-API paths apply the unit caption once, as the FP&A path does. |
| C5 | A zero variance is Neutral and "in line", never Favorable or "beat", in every chat handler. |
| X4 | Every common unit caption reads: `(£000)`, `(€000)`, `(000)`, `($MM)`, "in billions"; never "in M&A". |
| X5, X30 | Amounts or a filing marked in another currency are never reported in the chosen one: the chat asks again and offers the marked currency. |
| X6 | A chosen period ("Sep-26") reads its own Budget and Actual columns, not the YTD pair. |
| X7 | In a signed ledger, Gross Profit and Net Income are no longer counted as lines. |
| X8 | An export flag on an LTM, join, metrics, panel or limit-basis run used to drop that input silently; such a run now refuses before reading, naming the flags. `--multiple-threshold` reaches the comparison path, and a filing read there is headed by its printed totals. |
| C1 | Strict and assisted intake agree on uncached formulas in computed columns. |
| C3 | Investigated: R5's rounding interval holds and no tolerance changed. Its misleading message became C3m in Phase 3. |

## Phase 3: refusals and friction

| ID | What a reader now sees |
|---|---|
| C3m | A one-unit line beside a zero, within the rounding of the printed figures, is refused with the line named ("I couldn't tell whether 'Other expense, net' adds to or takes away from ..."). |
| C4 | A line read among costs with its sign turned is called "a credit" only when it adds to income in every compared year; otherwise the note names the years each way. |
| M1 | A filing whose statements sit in another document names that document (Exhibit 13 and its file). |
| M2 | A statement that runs on into an untitled table of other periods says so when it fails. |
| M3 | Bare-year bands (`2025` / `2026` over Budget and Actual) take the period-band path. |
| M5 | A label printed twice says which numbered copy is which. |
| M6 | `scripts/message_inventory.py` lists every intake message and checks it by the rules file. At the pre-fix source: 235 seen, 10 with jargon, 37 of 86 errors with no fix. After: 0 and 0, and a test now fails on any new message that breaks the rules. |
| X10 | `--no-browser` keeps the chat local even where `RENDER` is set (a bare `--chat` still hosts there, as Render needs), and the help and README name the variable. |
| X12 | A body that drips one byte at a time is cut off at a deadline set by its declared size. |
| X13 | `-o` and the other outputs can no longer overwrite an input file. |
| X14 | A filing on the comparison path writes the audit version that fits it. |
| X15, X17, X18 | `.tsv` works on the CLI, `.xls` sheet switching works in the chat, and the header synonyms agree across bases. |
| X16, X20 | Section headings are left out with a note; a zero in a dash section no longer stops a thousands caption. |
| X19, X26 | A failed upload keeps the current exports, and a reset or replaced start-up file's first reply is no longer served. |
| X21 | After a budget-only upload, a whole file is read on its own and the half set aside, with no command-line wording. |
| X22 | A subtotal's rounding gap shows once, plainly, with a "Leave X out" chip. |
| X23, X24 | "Budget ($000)" and similar headings are recognised, and a two-row header with a band over Budget and Actual reads. The merged date band (Maya's f17) is left open. |
| X25 | `export report ~/x.md` writes to the home folder, not a folder named `~`. |
| X27 | "Unclassified" never reaches the reader: tables, chips and warnings say "Not yet labeled". |
| X28, X29 | A mapping file that isn't JSON says "Mapping file ..."; `--check-only` with an output flag is refused. |
| X31 | A Percent cell formatted `0.0%` reads as the percentage Excel shows (0.4 is 40%), whatever `--percent-values` says. |
| X35 | The period a file's title names is offered as a chip. |
| X36 | Lines the comparison file of a pair lacks can be read as 0, from a chip, as a blank budget can. |

## Gates at the end of Phase 3 (`5bd1a9a`)

All pass:
- ruff;
- `mypy --strict` (72 files);
- compileall;
- pytest: 2751 passed, up from 2505 at Phase 0;
- `pip check`;
- build, twine and `check_distribution.py`;
- the minimal install;
- contracts and schemas: identical to `main`.

The Windows job is CI's.

## Screenshots

[`docs/improve/evidence/phase-3/`](../phase-3/) holds 91 shots of 26 scenarios, light theme, desktop (`_d_`) and mobile (`_m_`), named `<scenario>_light_<size>_<n>_<step>.jpg`. Each scenario uploads a fictional file that a Phase 2 or 3 test pins, and was dry-run through the handlers first. Scenarios: c5-zero-line, x5-currency, x6-month-and-ytd, x1-footnote, x4-pound-caption, x7-signed-ledger, x3-pdf-caption, x16-sections, x20-zero-section, x23-header-units, x24-two-row-header, m3-bare-years, x31-percent-format, x35-period-chip, x21-whole-after-half, x36-unbudgeted, x22-unreconciled-total, x27-not-yet-labeled, m6-empty-file, m6-no-header, m1-statements-elsewhere, m2-runs-on, m5-numbered-copies, c4-credit-by-year, c3m-sign-ambiguity, x30-filing-currency. X25's screen is not shot, because its scenario would write into the real home folder.

## Revert proofs so far

Each fix was reverted alone with its test kept. The result column is what the test said.

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
| T1 | Load, the reason for the change: the old test beside 64 CPU-bound processes, then the new one. | `pytest ...::test_unmatched_questions_on_a_big_file_stay_fast` | old test: "5 failed, 2 passed" on each of 2 runs; new test: "7 passed" on each of 2 runs |

## New at this stop: X42

Found while looking at the outputs. On the measure path (Percent, Count, Multiple rows), the report's "How the file was read" and the audit's `inferences` list only the measure path's own notes, never assisted intake's. So X31's note ("read Budget and Actual as the percentages Excel shows (number format '0.0%')") reaches the chat summary and stderr, but neither the Markdown report nor the audit. Neither traces 40% back to the stored 0.4. Both also say "Read bare Percent values as points." when no bare value was read. The figures are right, so this is a provenance gap, not a wrong number.

**Recommendation:** carry assisted intake's notes into the measure path's notes, so the report and the audit's `inferences` list them, and print the bare-rate line only when a bare rate was read. No contract changes (none has a Percent row), and the audit schema is unchanged (`inferences` is a list of strings).

## Questions

1. **Go on Phase 4 (S1 to S4)?** Each is behaviour-neutral and changes no contract file. S1 makes `chat/handlers.py` a package. S2 splits `_process_raw_table` (now 534 lines). S3 splits `cli._run`. S4 splits `_handle_what_if` and `build_audit_record`. I recommend adding `_handle_executive_memo` to S4: at 152 lines it is the one function to cross 150 since Phase 1.
2. **Go on Phase 5 (N1, N2)?** Neither changes a contract file. N1 adds workbook sheets where `--xlsx` refuses today and leaves every existing workbook as it is. N2 is a new opt-in batch command.
3. **X42:** may the measure report and audit carry intake's notes as recommended above?
4. **Open STOP-ASKs, shown again:**
   - [X41](../stop-ask-buffer-scale/ASK.md): a unit caption scales Limit and Actual but not Buffer or Tolerance. I recommend scaling them with the caption.
   - [M4](../stop-ask-m4-period-labels/ASK.md): a 10-Q's column label is also the audit's `comparison.label` key. I recommend adding the duration as a display name only, keeping every key.
5. **Still open, outside this run:** X9 and X11 (hosted mode's shared session and staged downloads) stay with the per-visitor-sessions work. X38 and X39 are open as proposed, and X40 (deploy pins) is yours.
6. **Draw G:** `EDGAR_USER_AGENT` is still unset. If it is still unset at Phase 8, PLAN records "Draw G: not measured".
