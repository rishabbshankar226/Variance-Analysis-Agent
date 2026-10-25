# Interface redesign: plan and state

Spec: `VARIANCE_UI_DESIGN_PROMPT.md`, Revision 1 (the owner's prompt library). Branch `ui/professional-design`, cut from `822e522`.
This file is the rules file's "approved Implementation Plan" for this run (spec section 2, constraint 1).

## Status

| Phase | Task | State | Commit |
|---|---|---|---|
| 0 | Read, baseline, harness, before screenshots, renders, this plan, `DESIGN.md` skeleton, `CLAUDE.md` | done | `9bcf130` |
| 1 | Design system: `DESIGN.md` in full, results mock + blur check, tokens light and dark, icon helper, `tests/test_interface_design.py`, contrast helpers per theme | done | (this commit) |
| 2 | Shell, mark, favicon, first screen, chips (T7), first reply after upload (T6), `level` field and the `⚠️` migration | todo | |
| — | **STOP 1** (evidence in `docs/ui/evidence/stop-1/`) | todo | |
| 3 | Intake panel (sibling of `format_intake_summary` returning rows) | todo | |
| 4 | Results `view` (T5, T8, T9, print), drill-down, driver breakdown | todo | |
| 5 | Earnings and equity views; emoji allowlist empty | todo | |
| 6 | Workbook styles (raw SpreadsheetML), openpyxl value-equality test | todo | |
| — | **STOP 2** | todo | |
| 7 | Command line help (droppable at STOP 2) | todo | |
| 8 | Hardening, `REPORT.md`, CHANGELOG, README screenshots | todo | |

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

Edited so far: 2 assertions extended (above), 0 pinning meaning.

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
