# STOP-ASK: a unit named only by a heading that isn't Budget or Actual scales the amounts (X49, on `main`)

**Found** after the final STOP, on 2026-11-03, while reproducing what the Phase 8 reviewer had suspected but not reproduced ("Headcount (000s)"). A wrong number found after STOP 1 is a STOP-ASK. It is not on a 0.2.0 path: `intake.py` did not exist at `5e288bb`.

**The cause.** When neither amount heading names a unit, `_unit_scale` runs `detect_unit_scale` over the title and every heading joined. A unit on any other column ("Headcount (000s)") then scales Budget and Actual. X45's fallback, for an amount heading with no unit of its own, also reads "the caption the title and the other headings give", so it inherits the same reach.

**Reproduced** with `--assisted --period "Q3 2026" --dollar-threshold 1 --percent-threshold 1`. The branch and `main` (a detached worktree of `main`, with `PYTHONPATH` on its `src`) give the same output, and the inputs and outputs are in this folder.

| File | Shown, on the branch and on `main` | What the source supports |
|---|---|---|
| `h1.csv`: `Budget`, `Actual`, `Headcount (000s)`; Sales 250,000 against 275,000 | "Amounts scaled from thousands (x1,000)": $250,000,000.00 against $275,000,000.00 | $250,000 against $275,000; the unit names the headcount column only |
| `h2.csv`: `Budget`, `Actual`, `Variance ($000)`; Sales 250 against 275 | scaled by 1,000: $250,000.00 against $275,000.00 | Probably thousands, since the variance column is in thousands; but the amount headings don't say so |

**Recommendation.** Take a unit only from the amount headings themselves or from the title. When neither amount heading names one and the title names none, but another heading does, refuse and name it: "'Headcount (000s)' names thousands, but 'Budget' and 'Actual' name no unit, so I can't tell whether the amounts are in thousands. Give the Budget and Actual headings their unit, such as 'Budget ($000)', or put a caption such as ($ in thousands) above the table, then upload the file again." The same change narrows X45's fallback to the title alone. So `Budget ($000)` beside a bare `Actual` refuses even when `Headcount (000s)` sits elsewhere; today it scales Actual by 1,000. Files whose title gives the caption, and files where no heading names a unit, read exactly as today.
- **Cost, measured:** the rule applied in a throwaway worktree at `e790e09` leaves all 2868 tests passing. No test, contract or Phase 1 fixture relies on another heading's unit.
- **Boundary cases:** `h1` and `h2` refuse with the message. A title caption with `Headcount (000s)` beside it scales by the title. Two bare headings with no unit anywhere read unscaled. A caption in the title over `Variance ($000)` scales by the title.
- This changes no contract file and, by the probe, no existing assertion.
- **The alternative** is to ignore other headings' units. `h1` then reads right and `h2` unscaled, which is wrong if its amounts are in thousands. A refusal names the cause and the fix, so I don't recommend it.

**Question.** May the run refuse when only a heading other than Budget or Actual names a unit, and narrow X45's fallback to the title (recommended)? Or should it ignore other headings' units? It is marked `asked` in PLAN.md as X49.
