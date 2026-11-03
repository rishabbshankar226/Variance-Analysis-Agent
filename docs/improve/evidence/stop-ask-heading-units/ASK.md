# STOP-ASK: amount headings that name different units are scaled by one multiplier (X45, from X23)

**Found** in Phase 8 on 2026-11-03 by the fresh-eyes reviewer for unsupported numbers, and reproduced here. A wrong number found after STOP 1 is a STOP-ASK. It is not on a 0.2.0 path: `intake.py` did not exist at `5e288bb`, and `main` refuses all three files below ("Could not find a header row with Line Item, Budget, and Actual columns").

**The cause.** X23 lets "Budget ($000)" and "Actual ($M)" map as Budget and Actual (`intake.py` `match_column_synonym`, the qualifier retry), but no column keeps its own unit. `_unit_scale` runs `detect_unit_scale` over the title text and every heading joined together, and millions is checked first, so one multiplier scales the whole table. The `--long-output` and batch path refuses qualified headings, so it is unaffected.

**Reproduced** with `--assisted --period "Oct 2026" --dollar-threshold 1 --percent-threshold 1` (inputs and outputs here; `*.branch.md` is the report, `*.main.err.txt` is `main`'s refusal):

| File | Shown (report, audit `material_variances`, All Rows sheet) | What the source supports |
|---|---|---|
| `a1.csv`: Budget ($000) 250, Actual ($M) 0.275 | Budget $250,000,000.00, Actual $275,000.00, variance -$249,725,000.00 U | $250,000 against $275,000, +$25,000 F |
| `a2.csv`: Budget ($000) 250, Actual ($) 275000 | Budget $250,000.00, Actual $275,000,000.00, variance +$274,750,000.00 F | $250,000 against $275,000, +$25,000 F |
| `a3.csv`: Budget ($000) 250, Actual 275 (no unit) | Budget $250,000.00, Actual $275,000.00 | Actual's unit is not stated |

**Recommendation.** Give each amount column the run reads a unit: its own heading's qualifier, else the title's caption, else none. Scale only when Budget (or the comparison column) and Actual have the same unit. When they differ, refuse and name both headings and their units, for example: "'Budget ($000)' is in thousands and 'Actual ($M)' in millions. Restate one column so both use the same unit, then upload again." `a3.csv` refuses the same way, because one column names a unit and the other names none. Headings with the same qualifier still scale (`f24_header_000.xlsx` and the 11 tests in `tests/test_header_units.py`), and so does a title caption over bare headings (`f03`). A title "in thousands" over "Actual ($M)" refuses. Tests straddle each case and assert the message. This changes no contract file and edits no existing assertion, since no test reads mixed units. The alternative is to scale each column by its own unit. That reads `a1` and `a2` right, but it adds per-column arithmetic for a layout no reader has shown us, and a refusal names the cause and the fix.

**Question.** May the run refuse amount headings whose units differ, `a3`'s half-stated unit included (recommended)? Or should it scale each column by its own unit? It is marked `asked` in PLAN.md as X45.
