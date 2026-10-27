# STOP-ASK: Draw E's final fresh eyes found wrong figures in two income statements (2026-10-27)

Branch `analysts/filings-and-excel`. Draw E was the measure for Decision 41's fixes, and informs no code change, scorer included. Nothing has been changed since its sweep. Per-filing detail is in `~/vaa-edgar-corpus/final-e/`. This file names no company or accession.

## Draw E, as swept once at `1b10d97`

**0 wrong values**: every line and every headline figure matched its fact. 3,822 values were verified and 36 unverified, all printed dashes or confirmed blanks with no fact behind them.

The new label check scored 6 labels wrong, all in one bank's cash flow statement. I checked all 6, and each names a heading the filing prints directly above the row ("Loans held for sale: Proceeds from sales"). The check judges headings by the presentation linkbase, which lacks these sub-headings: a limit of the checker, left as measured.

All three statements were read on **10 of 27** filings (37%, 22-56%), and 17 of 27 without a refusal (63%, 44-78%). The 90% target is not reached. All 12 refusals are plain.

Draw A, swept on the same code with label text scored, shows 0 wrong. Final dist gates PASS (2,501).

## Fresh eyes (seed `20261105`)

Five Draw E filings were drawn with the seed committed before the draw, and checked by a subagent with none of this plan's reasoning; label text was named in its brief.
- Every balance sheet and cash flow report is clean: values, signs, labels and their figures, section names, subtotals and identities.
- Every headline figure matches.
- The errors are in **two income statements**. The reviewer counted 12 wrong figures (6 values and their 6 changes) and 7 wrong type or status labels, and I confirmed them against the reports and the audits:

| Where | What the report shows | What the filing prints | Cause |
|---|---|---|---|
| A bank's income statement | "Income tax expense (benefit) \| Revenue \| $2,303,000 \| -$43,480,000 \| -$45,783,000 \| -1988.0%" | 43,480 this quarter, (2,303) a year earlier: an expense | The shaper read the line "as income: the statement prints it as 43480000 and subtracts it". It is typed Revenue with its sign turned, and only the audit says why |
| An income statement | "Income tax (expense) / benefit \| Expense \| -$331,000 \| -$878,000 \| … \| F" and "Interest expense \| Expense \| -$170,000 \| -$116,000 \| … \| U" | (878) and (331); (116) and (170) | The arithmetic couldn't place these lines, so the engine typed them Expense by their labels. Figures printed in parentheses then read as negative costs, so the F/U is the reverse of the truth |
| The same statement | "Income / (loss) before income taxes \| Expense \| … \| U" | A printed subtotal | The "/ (loss)" form isn't a subtotal label the shaper knows, so the subtotal is analysed as a line, typed Expense by its label |
| Two other income statements | Interest income typed Revenue | Printed under "Other income" | No figure changed (low severity) |

**How far it reaches.**
- **Lines typed by their label** on filing income reads: 16 material lines in 2 Draw B filings, and 10 in 3 Draw E filings.
- **Sign-turned lines the report doesn't explain**: 35 in 17 Draw A filings, 27 in 16 Draw B, 29 in 15 Draw C, 56 in 19 Draw D and 23 in 11 Draw E. Most are the conventional reading (an expense printed in parentheses shown as a positive cost). The harmful case is a line given the type opposite to its nature.

**The pattern across rounds.** Since Draw B the sweep has found no wrong value. Each round of fresh eyes has found a new class it doesn't score:
- headline figures at B
- the unit of label amounts at C
- label text at D
- how an income statement types and signs the lines its arithmetic can't place, at E

## Recommendation

Fix, then measure on a fresh Draw F. Add one more sweep check, so the measure catches this class itself.

1. **No label typing on filings.** A line the statement's arithmetic can't place stays Unclassified, shown as printed, with no F/U. This extends Decision 39 item 2 from revenue to every type.
2. **Every sign turn is explained in the report**, not only the audit: each "read as income / as an expense" turn, beside the credits.
3. **A line the shaper must turn keeps the latest year's printed sign where it can.** A line printed positive and subtracted is an expense, not negative income.
4. **"Income / (loss) before …" and similar slash forms** are subtotal labels.
5. **Sweep.** A row's shown figure must equal its printed figure, or the report must state the turn. A row typed by its label on a filing scores as wrong.

Each fix gets a fictional fixture that fails first. Draw A is re-swept, then the fixes are measured on Draw F:
- **Seeds:** `20261106`, and fresh eyes `20261107`, committed as a Decision before the draw.
- **The draw:** 30 filings, excluding Draws A-E.

Item 3 changes how existing filing reads type a turned line, a financial rule (section 7), and is part of this question.

The alternative is to finish now with Draw E as measured and these listed as known defects. A wrong F/U on a tax expense, or an expense shown as a negative cost, is a figure an analyst would trust. So I recommend the fix. If Draw F's fresh eyes then find another class, I'd recommend finishing with it listed rather than another round.

**Question.** Fix items 1-5, including the turned-line rule in item 3, and measure on Draw F (seed `20261106`)? Or finish with Draw E as measured and these listed as known defects?
