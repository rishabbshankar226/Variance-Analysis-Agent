# Interface redesign: plan and state

Spec: `VARIANCE_UI_DESIGN_PROMPT.md`, Revision 1 (the owner's prompt library). Branch `ui/professional-design`, cut from `822e522`.
This file is the rules file's "approved Implementation Plan" for this run (spec section 2, constraint 1).

## Status

| Phase | Task | State | Commit |
|---|---|---|---|
| 0 | Read, baseline, harness, before screenshots, renders, this plan, `DESIGN.md` skeleton, `CLAUDE.md` | done | `9bcf130` |
| 1 | Design system: `DESIGN.md` in full, results mock + blur check, tokens light and dark, icon helper, `tests/test_interface_design.py`, contrast helpers per theme | done | `c978cf1` |
| 2 | Shell, mark, favicon, first screen, chips (T7), first reply after upload (T6), `level` field and the `⚠️` migration | done | (this commit) |
| — | **STOP 1** (evidence in `docs/ui/evidence/stop-1/`) | done: approved | (this commit) |
| 3 | Intake panel (sibling of `format_intake_summary` returning rows) | done | `0995c16` |
| 4 | Results `view` (T5, T8, T9, print), drill-down, driver breakdown | done | `8f30c42` |
| 5 | Earnings and equity views; emoji allowlist empty | done | `35759be` |
| 6 | Workbook styles (raw SpreadsheetML), openpyxl value-equality test | done | `d3ad507` |
| — | **STOP 2** | done: "do what you recommend and continue" | `43f60fa` |
| 7 | Command line help (droppable at STOP 2) | done | `34bf0b9` |
| 8 | Hardening, `REPORT.md`, CHANGELOG, README screenshots | done | (this commit) |

## Baseline (against `822e522`)

- `pytest -q`: **1964 passed in 39.17s** (Python 3.11.16, `.venv` built with `-c requirements-typecheck.txt -e '.[dev,excel,pdf,release]'`). A later run: 1964 passed in 30.67s.
- ruff "All checks passed!"; mypy "Success: no issues found in 62 source files"; compileall, pip check, build, twine, `check_distribution.py`, both installation checks: pass.
- T1 recount (Emoji_Presentation plus U+2190–21FF, U+2600–27BF, U+2B00–2BFF), lines carrying one: `chat.html` 3 (↺ ➤ 📊), `chat.js` 13 (↕ ⚠ ⬇ 📁 📎 🔍 and the sort arrows), `chat/handlers.py` 89, `chat/knowledge.py` 4 (⚠ 💡), `intake.py` 1 (⚠, line 2124). `earnings.py`, `responses.py`, `intent.py` and `server.py`: 0. (The spec's 85 for `handlers.py` used a narrower set.)
- `chat.css`: 11 font sizes, 3 weights, 7 radii, one `--shadow`, 4 gradients, a glow variable, no light theme, no `@media print`, no `forced-colors`.

## Gates

One list, run by `sh docs/ui/evidence/gates.sh` (core) and `sh docs/ui/evidence/gates.sh dist` (core plus distribution). Taken from `.github/workflows/ci.yml` plus the rules file's `--without-excel` check.

Core, every phase: `ruff check .` · `mypy --strict src/variance_agent scripts deterministic_conditioning` · `pytest -q` · `python -m compileall -q src tests scripts deterministic_conditioning` · `pip check` · the 19 contract fixtures unchanged since `822e522`.

Distribution, every phase that touches an asset: `python -m build` · `twine check` · `scripts/check_distribution.py` · each artifact installed in a fresh venv with `check_installation.py --without-excel --without-pdf` and `pip check` · `wheel[pdf]` with `check_installation.py --without-excel`.

Every phase also runs `shots.py` at 1280 and 375 px and every image is opened.

## Screen inventory (before)

Captured by `docs/ui/evidence/shots.py` into `docs/ui/evidence/before/`, dark only (the page has no light theme yet), at 1280×800 (`d`), 768×1024 (`t`) and 375×760 (`m`): **130 JPEGs, 7.4 MiB** (`du`: 7.6M). Every image was opened. A shot whose reply is taller than the log gets a second `-end` shot at the bottom of the log. One sentence per screen, with size-specific notes.

| Screen | Before (desktop) | What it shows |
|---|---|---|
| First screen | `first_dark_d_01_first.jpg` | A 📊 tile, "Deterministic Financial Assistant", a 720 px card holding a welcome paragraph and a dashed 📁 drop zone, three violet pill chips and an empty page below; on the phone the header takes two rows (124 px) and the drop zone fills the card. |
| Help | `first_dark_d_02_help.jpg`, `_03_help-end` | A long "Available Commands & Intelligence" list of mono code pills with dash glosses, including advice wording ("mitigation advice", "Actionable mitigation & optimization steps"), ending in a second drop zone and four chips. |
| Upload (first reply) | `sample_dark_d_01_upload.jpg`, `_02_upload-end` | 👋 plus a capability essay (What it's for / Who it's for / What you can do) pushes the actual question, "What reporting period…", below the fold at every size (T6). |
| Period | `sample_dark_d_02_upload-end.jpg` | The period question is the last line of the essay card, with ✅ "Loaded 'sample_variance.csv' (5 data rows)". |
| Thresholds | `sample_dark_d_03_thresholds.jpg` | "Period set to: Q3 2026" card and four preset chips; the earlier chips stay full-colour above it. |
| Currency | `sample_dark_d_04_currency.jpg` | A narrow card and USD/EUR/GBP chips; the threshold chips from the turn before still look live (T7). |
| Results | `sample_dark_d_05_results.jpg`, `_06_results-end` | ✅ "Analysis Complete" as a bubble: bold-label text block, then a mono uppercase table with ↕ sort marks, a 🔍 filter, F/U single letters coloured green/red, a coloured left rule per row and red/green bars under the variance (T5, T9); the next-step chips are cut off by the input bar at 1280×800. |
| Results, tablet | `sample_dark_t_04_results.jpg` | The bubble stops at about 45% of the 768 px width and the table scrolls sideways inside it, cutting Var ($) in half. |
| Results, phone | `sample_dark_m_05_results.jpg`, `_06_results-end` | Only Line item and Type are visible; every amount is off to the right (T8). |
| Drill-down | `sample_dark_d_07_drilldown.jpg` | "Driver Evidence: Subscription Revenue" as plain lines and bullets (volume effect, price effect), no table and no visual tie to the row. |
| Driver breakdown | `sample_dark_d_08_drivers.jpg` | 🔬 heading, ✅/❌ status cells in a mono table, "None" in the model column and "mathematically verified causal drivers" copy. |
| Biggest risks | `sample_dark_d_09_risks.jpg`, `_10_risks-end` | 🚨 heading, a numbered list with one bullet per figure and wide empty gaps between bullets, ending in 💡 "Recommended Action: Focus operational reviews…" (advice; see Risks). |
| What-if | `sample_dark_d_11_whatif.jpg`, `_12_whatif-end` | 🔮 heading, ten bulleted figures, then a table whose every row carries a green left rule and "F", including the Total Revenue row with a $0.00 change. |
| Summary | `sample_dark_d_13_summary.jpg`, `_14_summary-end` | A repeat of the results bubble. |
| Blank-budget question | `intake_dark_d_01_blank-budget.jpg`, `_02_blank-budget-end` | The essay again, then "Found 1 line item with blank budgets…" and two chips at the very bottom. |
| Intake summary | `intake_dark_d_03_intake-summary.jpg` | "Here's how I read your file:" as a bulleted list with double-spaced bullets (Worksheet, Header row, Columns mapped, Rows read, Visible adjustments) and Looks right / Change something chips. |
| Period after intake | `intake_dark_d_04_period.jpg` | The period question as a one-line bubble. |
| Period choice | `period-choice_dark_d_01_period-choice.jpg`, `_02_period-choice-end` | The essay pushes "Which period would you like to analyze?" and its Jul-26/Aug-26/Sep-26/Q3 chips below the fold. |
| Comparison choice | `comparison_dark_d_01_comparison-choice.jpg` | ⚠️ in front of a plain question ("Which should Actual be compared against?"), so a choice reads as a warning. |
| Unreadable file | `error_dark_d_01_unreadable.jpg` | ⚠️ text in the same bubble as every other reply, with Upload a different file / Show technical details chips; nothing marks it as an error except the emoji. |
| Unclassified review | `unclassified_dark_d_05_unclassified.jpg`, `_06_unclassified-next` | "'Widget Program (Fictional)' is not yet labeled revenue or expense. Should it be:" with six chips; the previous item's six chips stay live above the next question. |
| Earnings offer | `earnings_dark_d_01_offer.jpg` | A one-line offer and two chips; 📎 in the user's file bubble. |
| Earnings intake summary | `earnings_dark_d_02_intake-summary.jpg` | Bullets such as "Revenue: Measure Currency." that read as field dumps. |
| Measure question | `earnings_dark_d_03_measure.jpg` | "What absolute threshold in basis points should flag Percent variances? Enter a non-negative number." with no chips; placeholder "Choose a direction, scale, or threshold…". |
| Earnings review | `earnings_dark_d_04_review.jpg` | A mono table with uppercase heads ("CONSENSUS % / BPS"), an empty Segment column, values left-aligned under Consensus while Actual is right-aligned; no status column and no rule colour; on the phone only Line item and Segment show. |
| Comparison set intake | `comparison-set_dark_d_01_intake-summary.jpg`, `_02_intake-summary-end` | The essay, then the intake bullets. |
| Comparison set result | `comparison-set_dark_d_03_result.jpg`, `_04_result-end` | **Defect:** the reply is the Markdown report, and its tables render as raw pipe text (`| Line Item | Measure | … |`, `|---|---:|`), because `renderMarkdown` has no table rule. |
| PDF intake summary | `pdf_dark_d_01_intake-summary.jpg`, `_02_intake-summary-end` | The essay, then twelve "Left out…"/"Read column…" bullets. |
| PDF results | `pdf_dark_d_05_results.jpg` | The results bubble with "Prior Period (FY2025)" left-aligned while Actual is right-aligned. |

Tablet and phone images exist for every row (`*_t_*`, `*_m_*`). Across them: the phone header wraps to two rows; bubbles keep a max width that wastes the tablet's width; every table is cut on the phone after the first one or two columns; old chips keep full colour at every size.

Other surfaces, rendered from `examples/sample_variance.csv` and `tests/fixtures/multi_audience/consensus.csv` (outside the repository, in the session scratchpad):

- **Workbook** (`--xlsx`, converted to PDF with LibreOffice and looked at): a violet title band and navy header bands as plain fills; Status cells filled green or red; on the earnings sheet "In line" for Operating Expenses is red-filled, so the fill says unfavourable where the text says in line; header and number alignment disagree; the All Rows sheet uses a tiny type size and has an `explicit_type` column (a cell value, so it stays); no print header or footer.
- **Report** (Markdown): read for reference only; its bytes are contract and do not change.
- **CLI `--help`**: 104 lines, one ungrouped "options" list, with the surprise-history flags first.

## Phase 1 record

- **Mock.** `docs/ui/evidence/mock/results.html` and `mock.css`, built from the sample's real strings, shot in both themes at 1280 and 375 px and blurred (Gaussian, radius 6): the three headline figures still read first, then the title, then the table rows. A 375 px overflow (the page grew to 812 px) and a mark that read as a menu icon were fixed before porting.
- **Port.** `chat.css` is a full replacement of the token layer: 4 gradients, the glow, 7 radii, 11 sizes and every transition removed. The page and script lose every emoji and arrow: an icon helper (`ICONS`, `ICON_SIZES`, `iconParts`, `createIcon`) draws the mark, sort, search, upload and download icons. Client-side warnings pass a `level` instead of the `⚠️` prefix.
- **Interim, until Phase 2's `level` field.** `chat.js` still marks a server reply as a warning when its text starts with U+26A0, and it writes that as the escape `⚠`, so the glyph itself is not in the asset.
- **Screenshots.** `docs/ui/evidence/phase-1/`: 100 JPEGs (first, sample, error, earnings and comparison-set scenarios × light and dark × 1280 and 375 px), every one opened. The first screen reads the same in both themes. One defect was found and fixed: the phone header's title ran into Help; it now truncates (Phase 2 redesigns the shell). Still to come, as planned: the capability essay (Phase 2), raw Markdown tables in the comparison-set reply (Phase 5), single-letter F/U status (Phase 4), phone tables that scroll sideways (Phase 4).
- **Tabular figures** checked in Chromium with the page stylesheet: "111,111.11" and "000,000.00" both 77.36 px wide (57.27 and 75.17 px proportional), so the system stack delivers them and no font is bundled.
- **Design hook.** The impeccable hook flags `#000000` on `#1b1b1a` in `chat.html`. Computed styles show that pair never renders: print is `#000000` on `#ffffff` in both themes, and dark screen text is `#edece8` on `#1b1b1a`. The hook offers only a file-wide ignore for this rule, which would hide real findings, so the finding is left standing and recorded here.
- **Tests.** `tests/frontend_helpers.py` holds the stylesheet readers (theme blocks, `var()` resolution, contrast); `test_frontend_contract.py` imports them and its two contrast tests now run per theme. `tests/test_interface_design.py`: 72 cases. The emoji allowlist starts as `handlers.py` and `knowledge.py`: `earnings.py` and `responses.py` already carry no T1 glyph, and the test fails if an allowlisted file is already clean. The T1 check is a superset of the spec's ranges (it adds U+2300–23FF, U+25A0–25FF and U+FE0F).
- **Gates** (`sh docs/ui/evidence/gates.sh dist`): ruff, mypy (62 files), **2036 passed in 36.74s**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, both installation checks: all PASS. `check_distribution.py` now also asserts that no `docs/ui/evidence` path is in the sdist.

## Phase 2 record

- **Error level.** `Response.level: Literal["error"] | None`, filled at the ten reply sites that opened with `⚠️` (fatal upload, analysis error, write failure, hosted save, revenue and expense certification refusals, sheet not found, statement refused, sheet load failure, comparison switch failure). `/message` and `/upload` send `level` only when set; `/status` sends it inside `initial_response`. `chat.js` styles a reply as `is-error` from the field alone; the U+26A0 fallback is gone. One value covers both a refusal and a stop that asks (the comparison choice): both are replies the analysis could not continue past, and the text says which. The seven inline `⚠️` inside successful replies (data quality count, unclassified notes, revenue shortfall headings, run-rate period note, driver status) are T1 work for Phases 4 and 5.
- **First reply after upload (T6).** `_first_upload_intro` is one short paragraph (name, what it compares, `help`); the capability list moved into `_handle_help`, rewritten in plain sentences without the advice wording ("mitigation advice", "Actionable mitigation & optimization steps"). The `first_visit` protocol and `intro_shown` are unchanged.
- **Chips (T7).** At each new user message, earlier `.chips` groups get `is-retired`, an `aria-label` saying they are no longer available, and every chip `disabled`; they stay as a record and are set as small muted text. Table drill-downs and download links are not touched.
- **Shell (T11).** Drawn mark, wordmark "Variance Analysis Agent" (the name the tests and the page title use), the step as plain text after a hairline, Help and Start over with drawn icons. At 420 px and below the step moves to a second row and the two buttons show only icons, keeping their words for screen readers. `favicon.svg` (the mark on the accent) is allowlisted in `_STATIC_TYPES`, both lists of `check_distribution.py` and the served-assets test, in this commit.
- **Loading.** Nothing for 100 ms, then dots plus "Working on it" or "Reading the file", then after another 900 ms a flat three-bar skeleton at two opacities; both timers are cleared when the reply lands.
- **Copy.** Phase labels and placeholders are sentence case without ellipses; the first screen says what the file needs and what happens next; Markdown no longer leaves an empty line after each bullet.
- **Screenshots.** `docs/ui/evidence/phase-2/`: 138 JPEGs (first, sample, intake, period choice, error, comparison, unclassified, earnings, PDF × light and dark × 1280 and 375 px), every one opened. Fixed before the commit: the ✅ on the "Loaded" line of the first reply. Seen and left for their phases: the result as Markdown with ✅, 🔬, 🚨, 🔮, 💡 headings and single-letter F/U (Phase 4); "Recommended Action" advice copy (Phase 4, a pinned sentence: STOP-ASK); earnings and comparison-set tables (Phase 5); phone tables cut after two columns (Phase 4).
- **Gates** (`sh docs/ui/evidence/gates.sh dist`): ruff, mypy (62 files), **2050 passed in 39.03s**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, both installation checks: all PASS.

## Fresh-eyes review (end of Phase 4)

Verdict: "the individual blocks are designed ... the container around them is still a generated chat app"; held back most by results arriving as new turns in an append-only thread. Triage:

- Fixed: inline code no longer breaks inside a command; headline change lines are labelled ("Variance $12,500.00, 8.3%"); print gets page margins and leaves out the analyst's one-word turns.
- Decided, not changed: a persistent results panel beside the conversation was the layout rejected in Phase 1 (`DESIGN.md`, Decisions) and the owner approved the one-column direction at STOP 1; raised again as an option at STOP 2. Retired chips stay as "Offered:" (T7, decided at STOP 1). The short welcome is the T6 outcome the spec asks for. A clean file skips the confirmation step by the existing flow, which Phase 3 does not change.
- Constraint 2, not changed: no K/M scaling or dropped cents; the $0.00 what-if line is "Favorable" by the handler's rule; the net impact figure carries a tone and its direction words, with no status word, because the engine gives it none.
- Low, left: chip rows wrapping on a phone; the sticky column clipping scrolled header text (the divider and cue mark it).

## Evidence kept

Pruned before merge: the per-phase screenshot folders (`phase-1` to `phase-5`, most of `phase-4` and `phase-6`) and the stop images were removed to keep the repository light. They remain in the branch history; for example `git show 8f30c42:docs/ui/evidence/phase-4/sample_light_d_04_results.jpg`, or `git checkout <phase commit> -- docs/ui/evidence/phase-N`. Phase commits: 1 `c978cf1`, 2 `36a3f6c`/`15469b8`, 3 `0995c16`, 4 `8f30c42`, 5 `35759be`, 6 `d3ad507`, 8 `ec48399`. Kept: `before/`, `after/`, `final-pairs/`, `hardening/`, `phase-7/`, the images `REPORT.md` links, the mock and the harness scripts.

## Final gate run (Phase 8)

`sh docs/ui/evidence/gates.sh dist`:
- PASS ruff: All checks passed!
- PASS mypy: Success: no issues found in 63 source files
- PASS pytest: 2100 passed in 43.92s
- PASS compileall
- PASS pip-check: No broken requirements found.
- PASS contracts: 19 contract fixtures unchanged since 822e522 (19 tracked)
- PASS build, twine, distribution
- PASS installation --without-excel --without-pdf (wheel and sdist), pip check for each
- PASS installation --without-excel (rules file)

Also: `phone_tables.py` PASS; `hardening.py` 23 passed, 0 failed. Phase 8 fixes after the final fresh-eyes review: on a phone, tables lead with the line item and variance and status columns (`phoneColumnOrder`, tested); wrapped Help bullets hang; retired chips are muted in forced colours.

## Phase 7 record

- `--help` is grouped (Input, Analysis, Outputs, Surprise history and panels, Chat), each with a one-line description, a two-line usage (a report run and `--chat`) and an example in the epilog. Every flag, destination, type, default, choice, help string and the mutually exclusive pair is unchanged: a dump of all 36 parser actions is identical before and after. Exit codes and error strings are untouched. Before and after: `docs/ui/evidence/phase-7/help_before.txt`, `help_after.txt`.
- The `--assisted` notes on stderr were already one plain line per adjustment, and tests read their `[assisted intake]` prefix; left as they are.
- New test: `test_cli_help_is_grouped_and_starts_with_short_usage`.
- **Gates** (`gates.sh dist`): ruff, mypy (63 files), **2099 passed in 42.53s**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, both installation checks: all PASS.

## STOP 2 decisions (2026-10-24)

The owner answered "do what you recommend and continue". Read as: (1) replace only the workbook hash line of `test_legacy_sample_workbook_and_report_are_byte_identical` with the value-and-address comparison, keep its report hash and schema lines, and commit Phase 6; (2) keep the print stylesheet and do Phase 7; (3) no results panel beside the conversation.

## Phase 6 record

- **Styles** (`xlsx.py`, strings only, no openpyxl): the ink and status colours of the chat page; the header band is a light grey (`F2F1EE`) with a medium rule, the only fill in the workbook; status and outcome cells are the word in its status colour with no fill; totals are set apart by a thin rule above and a double rule below, no fill; the title and section heads lose violet; left-aligned cells get a one-step indent so a word never touches the figure before it.
- **Meaning by colour alone, fixed:** an earnings outcome now takes its colour from the word shown (`_outcome_cell`), so an immaterial miss that reads "In line" is no longer red-filled.
- **Alignment and widths:** numeric heads are right-aligned over right-aligned numbers (Summary, Material Variances, All Rows, Measures, Comparisons, Earnings); the Earnings sheet detects figure columns from their formatted values and sizes each column to its content (12 to 30).
- **Print:** every sheet prints "Variance report: <period>" and the sheet name at the top and "Variance Analysis Agent" and "Page n of N" at the bottom; sheets with a frozen header repeat it on every page (`_xlnm.Print_Titles`). Titles stay out of the sheets' cells; row 1 is still the header and data still starts in row 2.
- **Values:** `tests/xlsx_values.py` writes and reads `{sheet: {address: value}}` with openpyxl; the snapshots in `tests/fixtures/xlsx_values/` were written from the untouched code (diff against `822e522` empty for every workbook module) for the sample, a consensus earnings and a comparison-set workbook; `test_every_value_and_address_is_unchanged_by_the_redesign` passes for all three.
- **Left as cell values (constraint 3):** the comparison-set Status cells hold "F" (the engine's value), and the Root Causes sheet's Mitigation, Optimization and Data Request text (it mirrors the contract report).
- **Rendered and looked at:** LibreOffice to PDF, before and after, `docs/ui/evidence/phase-6/` (13 page images, all opened).
- **Assertion edited (approved at STOP 2):** `test_multi_audience_measures.py`, the workbook SHA-256 line of `test_legacy_sample_workbook_and_report_are_byte_identical` → every value and address equals the `822e522` snapshot. The report SHA-256 and the audit schema lines are unchanged.
- **Gates** (`gates.sh dist`): ruff, mypy (63 files), **2098 passed in 37.55s**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, both installation checks: all PASS.

## Phase 5 record

- **Earnings review.** `chat/earnings.py` `summary` returns a figures view ("Earnings review", compared with, period, currency, the no-estimates sentence) and `column_groups` from `comparison_groups`: each comparison's columns sit under one spanning head with short labels (Supplied, Variance, % / bps, Outcome); the keys stay `display_rows`' keys. Outcomes Beat, Miss and In line show as words with the favorable, unfavorable and neutral shapes (the words are the ones `display_outcome` returns, tested). A column empty in every row (Segment, here) is left out of the display only.
- **Comparison sets.** `_audience_summary` replaces the bare report reply: the text is still `render_markdown` (so the raw pipes stay in the text), and a view plus one table are built with the report's own formatters (`format_measure`, `_pct`, `display_outcome`), so currency, per-share, basis points and counts keep their engine formatting. The file-reading notes become label/value rows by line name.
- **Units.** Tested: per-share values keep "/sh", rates keep "bps", counts keep "units" (`test_earnings_tables_group_each_comparisons_columns`, `test_a_comparison_set_is_a_table_not_markdown_pipes`).
- **Screenshots.** `docs/ui/evidence/phase-5/`: earnings (consensus), comparison set, guidance and loss fixtures × light and dark × 1280 and 375 px, 46 JPEGs, every one opened; before images for consensus and the comparison set are in `before/` (guidance and loss were added to the harness in this phase, so they have no before image).
- **Gates** (`gates.sh dist`): ruff, mypy (63 files), **2092 passed in 36.29s**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, both installation checks: all PASS. `phone_tables.py` still PASS.

## Phase 4 record

- **Figures view.** `view` kind "figures" (shape in `chat/views.py`): title, context pairs, headline figures (label, value, compare, change, status word, tone), sections of label/value rows, notes, and the title of the table that follows. Built from the same engine objects and formatters as the text, in `_build_analysis_summary` (results and summary), `_handle_explain` (drill-down), `_handle_driver_summary`, `_handle_biggest_risks` (which now also returns its three rows as a table) and `_handle_what_if`. The text is unchanged apart from glyphs and the advice wording below; every figure in a view is also in the text (tested).
- **Layout.** One column; a result is not a card: title and a context line, the headline strip between hairlines (three or four figures, 28 px values, comparison and change in 12 px, status as a word with a shape), then the material variances in a framed table. On a phone the strip stacks one figure per row.
- **Tables (every reply with a table).** Status cells are words from `STATUS_WORDS` (mirrors `status_label`, tested) with a dot (favorable), square (unfavorable) or ring (neutral); numeric columns are detected from their values and right-aligned; heads are sentence case (`columnLabel`; keys unchanged); bars sit under the currency variance column only, scaled to it; the filter shows only above 8 rows; sort icons show on hover, focus or when sorted. On a narrow screen the first column is sticky and a "More columns" cue shows until the right edge.
- **T8 check.** `docs/ui/evidence/phone_tables.py`: at 375 px every table on the results, drivers, risks, what-if and waterfall replies either fits or shows its cue (output: 5 tables, all "cue visible", PASS); both scroll extremes shot in `phase-4/phone/`.
- **T12.** `phase-4/phone/print_results.pdf`, rendered and read: five pages, controls and chips dropped, headline strip and tables in black on white, markers still differ by shape.
- **T1 done for `chat/`.** Every glyph left `handlers.py` and `knowledge.py`; drivers cells read "Reconciled", "Not reconciled", "No driver data". `NOT_YET_CONVERTED` is empty.
- **Advice (STOP 1 answer 3).** Reworded as description: the risks "Recommended Action" line, the "Action playbook" chip (now "Drivers"; the phrase still routes), the playbook text, and the wins, concentration, unbudgeted-spend, savings and misses notes. Kept: the `recommendations` reply, because it mirrors the "Strategic Recommendations" section of the Markdown report, which is contract (constraint 3); rewording one without the other would make chat and report disagree. Listed for the owner in `REPORT.md`.
- **Not changed (constraint 2).** Whole-dollar amounts keep ".00" and large values are not scaled to K/M: figures render as the engine formats them. The what-if table marks a $0.00 change "Favorable" because the handler's rule says so; presentation shows it as given.
- **Counting rules.** The radius count treats `50%` (a circle, the status marker) as a shape, not a corner radius. Type sizes in use: 12, 13, 14, 16, 20, 28 px (six, the ceiling).
- **Screenshots.** `docs/ui/evidence/phase-4/`: 86 JPEGs (sample, PDF and unclassified flows × light and dark × 1280 and 375 px) plus 10 phone table extremes, every one opened. Fixed before the commit: the drill-down's figures wrapped mid-number (a width rule lost on specificity), variance values sat above the row baseline, and on a phone the driver rows stacked value over label.
- **Gates** (`gates.sh dist`): ruff, mypy (63 files), **2090 passed in 35.92s**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, both installation checks: all PASS.

## Phase 3 record

- **The `view` field.** `Response.view: dict | None`, passed through `/message`, `/upload` and `/status` (`initial_response.view`). The page draws a view it recognises (`isIntakeView`) and otherwise the text, which still carries every fact. Builders live in the new `chat/views.py`, so `handlers.py` only calls them. `with_lead` puts a sentence (the first-upload welcome, "Switched to worksheet", "Now comparing Actual against") before both the text and the view.
- **Intake panel.** `intake_summary_rows` in `intake.py` is the sibling of `format_intake_summary` (unchanged, still used by the text); it returns the same facts as label/value rows plus the adjustment and attention sentences. `chat/views.py` turns them into a panel: "How I read your file", one row per inference (worksheet or statement, header row, each column mapping, rows read, subtotals left out), "Adjustments I made", "Needs your attention", and the question. Earnings files get the same panel from `chat/earnings.py` (compared against, columns read, one row per measure, headline rows). The page builds it with `createElement`/`textContent` only; on a phone each row stacks label over value.
- **Chat-only wrapper.** `_intake_summary_text` drops the shared formatter's warning sign from chat text; `intake.py` line 2124 is untouched, so the CLI's provenance output is unchanged.
- **Step copy.** "Next Step" reminders and the "Hello!" greetings lose their emoji and greeting; the sentences tests pin ("Upload your financial file", "What reporting period", "Classify 'Unknown Item'", "ready to explore your **Q3 2026** financial results", "Switched to worksheet") are kept word for word. The confirmations and the order of the flow are unchanged.
- **Exit check.** `test_every_intake_reply_is_plain_language` runs the first reply (and the blank-budget follow-up) for all 21 real-world fixtures through the intake file's jargon checker and the T1 glyph check, text and panel. All pass.
- **Screenshots.** `docs/ui/evidence/phase-3/`: 144 JPEGs (intake, period choice, comparison, unclassified, error, earnings, comparison set, PDF, sample × light and dark × 1280 and 375 px), every one opened. Intake states covered at both sizes: blank-budget question, intake summary (workbook, PDF, earnings, comparison set), period, period choice, thresholds, currency, comparison choice, unclassified review, measure thresholds, unreadable file. Sheet and header-row choice are reached only by files the fixtures do not hold in that state; their replies use the same chip and text components.
- **Gates** (`gates.sh dist`): ruff, mypy (63 files), **2080 passed in 41.15s**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, both installation checks: all PASS.

## STOP 1 decisions (2026-10-24)

The owner answered "do what you recommend". Read as:

1. Direction approved: ink blue on warm grey, light and dark.
2. Type: the system stack; no bundled font.
3. Advice wording: reword in Phase 4. "Recommended Action: Focus operational reviews…", the "Action playbook" chip and the `recommendations` reply describe what the numbers show rather than what to do. This is the owner's approval of that STOP-ASK; each pinned assertion it touches is listed in the edits table with this reason.
4. "Start over" stays as the label of the reset button; it still sends `reset`.

Design hook: two file-scoped ignores recorded in `.impeccable/config.json` (excluded from git through `info/exclude`): `pulsing-dot` on `chat.html` (no status dot exists; the working indicator pulses only during a request) and `cramped-padding` on the Phase 1 mock (review evidence, never served).

## Fresh-eyes review (end of Phase 2)

A subagent given only the Phase 2 screenshots and the tell table judged the result "a generated chat app with a decent table component dropped in", held back most by results shown as messages rather than a results view. Its findings and where they go:

- Fixed now: retired chips still read as links (now prefixed "Offered:" in muted meta text); Help offered result chips before any file was loaded (now offers the three that work without a file; new test `test_help_offers_result_chips_only_once_there_is_a_result`).
- Phase 4: the result as prose with ✅ (T5); emoji headings and ✅/❌ marks in drivers, risks and what-if (T1); single-letter F/U and bars by colour (T9); left-aligned number columns in drivers and what-if; phone tables losing Actual, Variance and Status (T8); the variance-percent bars that do not scale; the sort carets on short tables; "Recommended Action" and "mathematically verified causal drivers" copy.
- Phase 5: the earnings table's clipped last column and left-aligned values; comparison-set Markdown tables.
- Disagreed: monospace on command names in Help and prompts (these are code spans, which T3 allows); the amber rule on errors (it is the one attention marker, not a box); Help as a long list (the spec moves the capability list there); intake as a form (Phase 3 owns intake and builds a panel for the summary, the questions stay one at a time because each answer changes the next).
- Not visible in stills: print (T12; the block exists and Phase 4 shoots it), motion (T10, under test).

## Assertions likely to need edits

Each edit is listed again in `REPORT.md` with the reason.

The `⚠️` to `level` migration (constraint 2, the one pre-approved edit to assertions that pin meaning); each keeps checking the same refusal:

- `tests/test_chat_comparison.py` lines 172, 308, 349 (a `not startswith` check, becomes "level is not error"), 359, 373
- `tests/test_chat_upload_state.py` lines 37, 159, 169
- `tests/test_chat.py` lines 319, 325, 542
- `tests/test_pdf_intake.py` line 203 (`startswith(f"⚠️ '{BALANCE}' lists assets")`, becomes the level plus the sentence without the prefix)

Presentation assertions (pass the "same text, different markup" test):

- `tests/test_chat.py:1074` `"🏁 Actual Operating Profit"` in a waterfall table cell (T1, Phase 4).
- `tests/test_chat.py:332–333` intro wording "What it's for" and "What you can do" (T6, Phase 2). The intro's facts stay; the wording is the presentation.

Kept unchanged: `tests/test_chat_upload_state.py` lines 76 and 127 (`intro_shown`), every escaping, `textContent`, `role="log"`, label, `tabIndex` and `aria-sort` string in `test_frontend_contract.py`, and the `@media (max-width: 420px)` / `autoGrow();` checks.

Extended, not loosened (Phase 1, done): `_tokens()`, `_luminance()` and `_contrast()` in `test_frontend_contract.py` moved to `tests/frontend_helpers.py`, which reads both theme blocks, resolves `var()` and fails on a token that is not `#rrggbb`. `test_text_colours_reach_wcag_aa_on_every_surface` and `test_white_text_on_filled_controls_reaches_wcag_aa` keep every pair and threshold and now run once per theme (48 + 8 cases, was 24 + 4).

Edited in Phase 2:

| Test | Was | Now | Kind |
|---|---|---|---|
| `test_chat_comparison.py:172` | `response.text.startswith("⚠️")` | `response.level == "error"` | `level` migration (pre-approved) |
| `test_chat_comparison.py:308` | `text.startswith("⚠️")` | `reply.level == "error"` (text still checked for plan words) | `level` migration |
| `test_chat_comparison.py:349` | `not response.text.startswith("⚠️")` | `response.level is None` | `level` migration (success case) |
| `test_chat_comparison.py:359` | `response.text.startswith("⚠️")` | `response.level == "error"` | `level` migration |
| `test_chat_comparison.py:373` | `response.text.startswith("⚠️")` | `response.level == "error"` | `level` migration |
| `test_chat_upload_state.py:37, 159, 169` | `response.text.startswith("⚠️")` | `response.level == "error"` | `level` migration |
| `test_chat.py:319, 325, 542` | `"⚠️" in resp.text` | `resp.level == "error"` (the sentence checks beside them stay) | `level` migration |
| `test_pdf_intake.py:203` | `startswith(f"⚠️ '{BALANCE}' lists assets")` | `level == "error"` and `startswith(f"'{BALANCE}' lists assets")` | `level` migration |
| `test_chat.py:332-333` | intro contains "What it's for", "What you can do" | intro is short and points to `help`; Help contains "What you can ask", the audience sentence and the commands | presentation (T6 wording) |
| `test_chat.py:1454` | Help contains "Available Commands & Intelligence" | Help contains "What you can ask" | presentation (heading wording) |
| `test_frontend_contract.py:303-304` | fallback labels "New Step", "Exploring"; placeholder "Type a message..." | "New step", "Results"; "Type a message" | presentation (sentence case) |

Edited in Phase 4: `test_chat.py:1078` waterfall cell `"🏁 Actual Operating Profit"` → `"Actual Operating Profit"` (presentation, T1); `test_interface_design.py` size pin now includes 20 and 28 px (own test, the sizes came into use).

Edited in Phase 6 (STOP-ASK approved): the workbook hash line above.

Totals so far: 12 `level` migrations, 4 presentation edits, 1 approved STOP-ASK edit (workbook hash), 2 assertions extended to both themes, 0 assertions that pin meaning edited otherwise. New tests: `tests/test_chat_reply_shape.py` (5, the JSON shape across `/message`, `/upload`, `/status`) and 7 Phase 2 cases in `tests/test_interface_design.py`.

## Decisions

| Decision | Why |
|---|---|
| Work in worktree `.claude/worktrees/ui-professional-design`, not the main checkout | Another agent (Antigravity) commits in the main checkout. |
| Fresh Python 3.11 `.venv` in the worktree | The main checkout's `.venv` is 3.14; the spec's environment is 3.11. |
| Playwright and Chromium in `~/.venvs/vaa-shots`, outside the repository | Spec Part A step 3; nothing added to the project's dependencies. |
| `CLAUDE.md` excluded through `$(git rev-parse --git-path info/exclude)` | A worktree's `.git` is a file; the exclude file is the shared one. |
| sdist `exclude = ["/docs/ui/evidence"]` in `pyproject.toml` | Screenshots and the harness are review evidence; the sdist includes `/docs`. Verified: the sdist holds only `docs/ui/DESIGN.md` under `docs/ui`. `check_distribution.py` gains the matching assertion in the first phase that touches an asset (constraint 11). |
| The harness waits on `body.is-busy` and polls with `page.evaluate` | `chat.js`'s `setBusy` toggles that class; Playwright's `wait_for_function` compiles its predicate with eval, which the page's CSP refuses, so it is not used. The class stays in the redesign. |
| The harness turns off smooth scrolling on `#messages` before positioning a shot | Without it the page's own scroll-to-bottom landed after the harness's scroll and shots showed the middle of a reply. |
| Earnings and comparison-set scenarios answer the period with `3Q26` | The fixtures' Period column is `3Q26`; "Q3 2026" is refused as a conflict. Measure thresholds are answered with `25`. |
| The unclassified scenario uses `docs/ui/evidence/untyped_fictional.csv` | Files with obvious names auto-classify; the review needs ambiguous, fictional names. |

## Risks

- **Advice in existing copy.** "Recommended Action: Focus operational reviews…", "mitigation advice", "Actionable mitigation & optimization steps" and an "Action playbook" chip are advice (constraint 8). New copy adds none; changing existing sentences that tests pin is a STOP-ASK, so Phase 2/4 list them for the owner rather than editing pinned text.
- **Comparison-set replies are raw Markdown.** Fixing it is a `view` for that reply (Phase 5), not a Markdown table renderer, so the text stays the report.
- **What-if status "F" on a $0.00 change** comes from the engine; presentation renders it as given (constraint 2) and does not hide it.
- **`handlers.py` is 4,621 lines** and the shared target of other work; `view` builders go in a new module the handlers call, to keep the diff there small.
- **Help and Reset ids, `#input`, `#phase-label`, the file input** are the harness's interface and keep their ids (constraint 5).
- **The emoji test's allowlist** starts with `handlers.py`, `earnings.py`, `responses.py`, `knowledge.py`; `intake.py` line 2124 is a chat-visible string from a shared module, so it is converted through a chat-only wrapper, not edited in place.
- **Shared session.** The server holds one session; the harness starts a fresh server per scenario, and a stray server from a killed run must be stopped (`pkill -f '<worktree>/.venv/bin/python3.11 .venv/bin/variance-agent --chat'`).
