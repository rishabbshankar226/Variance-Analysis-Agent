# Interface redesign: report

Branch `ui/professional-design`, cut from `822e522`. Spec: `VARIANCE_UI_DESIGN_PROMPT.md`, Revision 1. Plan and per-phase records: [PLAN.md](PLAN.md). Design system and decisions: [DESIGN.md](DESIGN.md). This file replaces the intake rules file's Walkthrough and friction scorecard.

Presentation only. Unchanged:
- every figure, rounding, status and financial rule;
- the 19 contract fixtures;
- every default CLI report and audit;
- every workbook cell value, address and sheet name.

## Before and after, per screen

All images are in `docs/ui/evidence/`. Before shots are dark only, because the old page had one theme.

| Screen | Before | After | What changed |
|---|---|---|---|
| First screen | [before](evidence/before/first_dark_d_01_first.jpg) | [light](evidence/after/first_light_d_01_first.jpg), [dark](evidence/after/first_dark_d_01_first.jpg), [phone](evidence/after/first_dark_m_01_first.jpg) | Drawn mark and wordmark; a sentence on what the file needs; a quiet drop zone; no emoji or gradient |
| First reply after upload | [before](evidence/before/sample_dark_d_01_upload.jpg) | [after](evidence/after/sample_dark_d_01_upload.jpg) | One-sentence welcome, then the file line and the question (T6) |
| Intake summary | [before](evidence/before/intake_dark_d_03_intake-summary.jpg) | [after](evidence/after/intake_dark_d_02_intake-summary.jpg) | A panel with one row per inference |
| Unreadable file | [before](evidence/before/error_dark_d_01_unreadable.jpg) | [after](evidence/after/error_light_d_01_unreadable.jpg) | `level: "error"` and an attention rule, with no ⚠️ |
| Results | [before](evidence/before/sample_dark_d_05_results.jpg) | [light](evidence/after/sample_light_d_04_results.jpg), [dark](evidence/after/sample_dark_d_04_results.jpg) | Headline figures first, then the material variances; status words with shapes (T5, T9) |
| Results, phone | [before](evidence/before/sample_dark_m_05_results.jpg) | [after](evidence/after/sample_dark_m_04_results.jpg), [table right edge](evidence/phase-4/phone/results_table0_right.jpg) | Stacked figures; the line item stays in view; variance leads; a cue for the other columns (T8) |
| Drill-down | [before](evidence/before/sample_dark_d_07_drilldown.jpg) | [after](evidence/after/sample_dark_d_05_drilldown.jpg) | Budget, actual and variance figures, plus the decomposition as rows |
| Drivers, risks, what-if | [drivers](evidence/before/sample_dark_d_08_drivers.jpg), [risks](evidence/before/sample_dark_d_09_risks.jpg), [what-if](evidence/before/sample_dark_d_11_whatif.jpg) | [drivers](evidence/after/sample_dark_d_06_drivers.jpg), [risks](evidence/after/sample_dark_d_07_risks.jpg), [what-if](evidence/after/sample_dark_d_08_whatif.jpg) | Views and tables in place of emoji headings and prose; advice reworded as description |
| Earnings review | [before](evidence/before/earnings_dark_d_04_review.jpg) | [after](evidence/after/earnings_light_d_04_review.jpg) | Comparison columns under one head; Beat, Miss and In line shown |
| Comparison set | [before](evidence/before/comparison-set_dark_d_03_result.jpg) | [after](evidence/after/comparison-set_dark_d_02_result.jpg) | A table in place of raw Markdown pipes |
| Workbook | [before](evidence/phase-6/workbook_before_sample-1.jpg) | [after](evidence/phase-6/workbook_after_sample-1.jpg), [earnings](evidence/phase-6/workbook_after_consensus-1.jpg) | Quiet header band; status as a word with no fill; print header and footer |
| Print | — | [PDF](evidence/hardening/print_results.pdf) | Controls dropped, black on white, shapes kept |
| `--help` | [before](evidence/phase-7/help_before.txt) | [after](evidence/phase-7/help_after.txt) | Five groups and a short usage line |

**Blind comparison.** A reviewer saw nine pairs labelled A and B, with the sides alternated. It picked the redesign in all nine. The pairs and the key are in `evidence/final-pairs/`.

## Tell table, final status

| # | Tell | Status | Proof |
|---|---|---|---|
| T1 | Emoji, arrows and dingbats as icons | done: none in `static/` or `chat/`; one drawn icon set | P (`test_no_emoji_arrows_or_dingbats_in_the_page`, `test_reply_text_built_by_chat_has_no_glyphs`, allowlist empty) |
| T2 | Violet, gradients, glow | done: ink-blue accent; light and dark from the system setting | P (`test_no_gradient_glow_or_text_shadow`, theme and contrast tests) + S |
| T3 | Type without a scale | done: 6 sizes, 3 weights, tabular figures, monospace on code only | P |
| T4 | Spacing and shape by feel | done: 4 px scale, 2 radii, 1 overlay shadow | P + S |
| T5 | Result as a chat bubble | done: results, drill-down, drivers, risks, what-if, earnings and comparison set render from `view` | P (`test_chat_reply_shape.py`) + S |
| T6 | Capability essay | done | P + S |
| T7 | Old chips left live | done: disabled, announced, shown as "Offered:" | P + S |
| T8 | Phone table | done: sticky first column, variance and status lead, a cue | S (`phone_tables.py`: PASS) |
| T9 | Status by colour alone | done: a word and a shape | P |
| T10 | Decorative motion | done: a 150 ms fade, a 1.2 s opacity loader; reduced motion stops both | P + hardening |
| T11 | Emoji brand | done: drawn mark and favicon | P + S |
| T12 | Screen-only design | done: print stylesheet; workbook print setup | P + S |

## Decisions

Every decision is recorded with the alternative it rejected:
- [DESIGN.md](DESIGN.md), section Decisions;
- [PLAN.md](PLAN.md), sections Decisions, STOP 1 decisions and STOP 2 decisions.

The owner answered both stops with "do what you recommend". That approved:
- the direction;
- the system font;
- the advice rewording;
- the "Start over" label;
- the workbook hash edit;
- Phase 7 and the print stylesheet;
- no results panel.

## Edited assertions

| Count | Kind | Where |
|---|---|---|
| 12 | `⚠️` → `level` migration (pre-approved by constraint 2) | `test_chat_comparison.py` ×5, `test_chat_upload_state.py` ×3, `test_chat.py` ×3, `test_pdf_intake.py` ×1 |
| 5 | Presentation: wording or markup, the meaning still holds | intro wording (`test_chat.py:332-333`), the Help heading (`:1454`), the waterfall cell emoji (`:1078`), phase-label sentence case (`test_frontend_contract.py:303-304`) |
| 1 | STOP-ASK, approved at STOP 2 | `test_legacy_sample_workbook_and_report_are_byte_identical`: the workbook SHA-256 → a value-and-address comparison against the `822e522` snapshot; the report hash and schema lines are unchanged |
| 2 | Extended, not loosened | both contrast tests now run per theme |

Each row, with its old and new text, is in [PLAN.md](PLAN.md) under "Assertions likely to need edits".

## Gates (final run)

The final run is listed under "Final gate run" in [PLAN.md](PLAN.md). The per-phase runs are in each phase record.

## Hardening (Phase 8)

`docs/ui/evidence/hardening.py`; output in `evidence/hardening/results.txt`: 23 passed, 0 failed.
- **axe-core 4.10.3**, WCAG 2.1 A and AA: no violations. Run on the first screen, the intake panel, the results and the earnings review, light and dark, at 1280 and 375 px. axe was read from the owner's copy outside the repository; it was not copied in.
- **Keyboard:** 9 tab stops, each with a visible focus outline. The drop zone opens the file chooser with Enter. The setup can be typed. A table line item drills down with Enter.
- **Reflow:** no sideways page scroll at 320 px (400% zoom) or 640 px (200% zoom).
- **Reduced motion:** no element animates.
- **Forced colours:** controls and tables keep solid borders. After this run, retired chips were made quieter there.
- **Print:** checked by rendering a PDF.
- **Widths:** 768 and 1920 px shots opened (first, sample, intake and earnings scenarios). The column stays centred at 960 px.

## Not verified

- Real Excel on Windows or macOS. The workbook was rendered with LibreOffice only.
- Screen readers: no VoiceOver or NVDA pass. ARIA roles and labels are under test, and axe passed.
- Windows high contrast mode on Windows itself. Forced colours was emulated in Chromium.
- Safari and Firefox. Every screenshot is Chromium (Playwright headless shell).
- Real 200% browser zoom. Reflow was checked by viewport width, which is equivalent for CSS pixels.
- Sheet-choice and header-row-choice intake states: no fixture reaches them interactively. They use the same components.
- Hosted mode (`--hosted`) on Render.

## Left for the owner

The final blind reviewer raised these and they were not changed:
- **Results inside the transcript.** A results surface beside the conversation was declined at STOP 2.
- **Setup questions asked one at a time.** The order and confirmations of the flow are fixed by the spec.
- **"Offered:" history.** Decided at STOP 1.
- **Figures as the engine formats them** (constraint 2). Amounts keep their cents and aren't scaled to K/M. The what-if table marks a $0.00 change "Favorable". Net operating impact has no status word.
- **The `recommendations` reply and the workbook's Mitigation and Optimization text.** They mirror the contract report's "Strategic Recommendations" section.
- **The product name and mark.**
- **Evidence size.** Done: the per-phase folders were pruned, taking `docs/ui/evidence/` from 49 MB to 19 MB. They remain in the branch history; [PLAN.md](PLAN.md) under "Evidence kept" says where. A squash merge carries only what is kept. The folder is excluded from the sdist, and `check_distribution.py` checks that.
