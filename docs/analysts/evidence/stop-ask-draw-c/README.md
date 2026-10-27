# STOP-ASK: Draw C's final fresh eyes found wrong figures (2026-10-27)

Branch `analysts/filings-and-excel`. Draw C was the measure for Decision 39's fixes, and informs no code change. Nothing has been changed since its sweep. Per-filing detail is in `~/vaa-edgar-corpus/final-c/`: the sample, my check of the reviewer's findings, and the label counts. This file names no company or accession.

## Draw C, as swept once at `cabf9a8`

**0 wrong values**, with every line and every headline figure scored. 3,644 values were verified and 28 unverified, all printed dashes or confirmed blanks with no fact behind them.

All three statements were read on **12 of 27** Inline XBRL filings (44%, 28-63%), and 15 of 27 without a refusal (56%, 37-72%). The 90% target is not reached.

There were 15 refusals:
- 9 plain.
- 6 that name no fix: the three statements of each of two filings.
  - A bank 10-K whose statements are in a second Inline XBRL document of the filing (its annual report).
  - A 10-Q whose statement tables the reader's assembly misses.

## Fresh eyes (seed `20261101`)

Five Draw C filings were drawn with the seed committed before the draw, and checked by a subagent with none of this plan's reasoning. It checked 492 Actual and Prior cells in 9 reports, every change, percent and label, 7 headline figures, and every subtotal and identity claim. **Every line value, change, subtotal and headline figure matched.** It counted 8 wrong figures.

| Count | What | My verdict |
|---:|---|---|
| 1 | A percent: 52/64 = 81.25% shown as 81.2% | **Not wrong, by rule.** The README states one half-even rounding to a tenth of a point |
| 7 | One insurer's balance sheet: labels quote amounts as the filing prints them, in thousands ("amortized cost: $1,431,586 and $1,432,454"), beside columns the report restates in whole dollars ($1,271,111,000.00). The report doesn't carry the filing's "in thousands" caption | **Wrong figures in the report.** The tool neither read nor computed them (they are the filing's own label text), but it shows them at a scale it doesn't state, and no rule covers that. A reader of the row gets a relationship the filing doesn't support |
| (10 more, if counted) | Gains and other income shown as negative expenses | **Not wrong, by rule** (Decision 28; the report explains each) |

**How far it reaches.** It isn't one filing. On statements printed in thousands or millions, labels quoting aggregate dollar amounts (allowances, amortized cost, accumulated depreciation, fair value; par values excluded) appear in every draw:

| Draw | Labels | Filings |
|---|---:|---:|
| A | 40 | 18 |
| B | 23 | 8 |
| C | 21 | 10 |

Nearly all are balance sheet labels such as "net of allowance of $402 and $212". The earlier fresh-eyes reviews passed every balance sheet they saw, so this class went uncaught since Phase 4. The PDF and `Financial_Report.xlsx` readers keep labels verbatim too.

**Also found** (known limits, not wrong figures):
- 10-Q column labels name the end month only, so a three-month income statement and a nine-month cash flow statement both read "Jul 2026".
- A balance sheet continued in an untitled table on the next page was not joined. Its refusal ("couldn't find both … totals") misstates the cause and offers no CSV route.
- An income statement refused on a pre-tax subtotal the reviewer finds off by $1M, which should sit inside R5's rounding interval. Not investigated, since Draw C informs no change.
- An insurer's "Total benefits and expenses" refused, although it adds; it has a nested subtotal and a contra line.
- Repeated labels are named by their place ("Deferred income taxes (1)/(2)"), as documented.

## Recommendation

Fix in the report, then measure on a fresh Draw D. A filing report states the filing's own unit caption and says how labels are quoted. For example: "The filing states its figures in thousands; amounts inside line labels are quoted as printed." Restating the amounts inside labels would rewrite the filing's text, so I don't recommend that.

The fix changes no value the tool reads or computes. A Draw A re-sweep will show it moves nothing the sweep scores, and a fictional fixture pins it.

Under section 5, a fix after a held-out draw is measured on a fresh one:
- **Seed:** Draw D seed `20261102`, and fresh-eyes seed `20261103`, committed to PLAN.md as a Decision before the draw.
- **The draw:** 30 filings drawn as B and C were, excluding Draws A, B and C.
- **The measure:** swept once, then fresh eyes on five filings, with balance sheet labels named in the brief.
- **The report:** Draw B and Draw C stay in REPORT.md as measured.

The alternative is to report Draw C as measured, list this as a known defect, and finish. I recommend the fix.

**Question.** Fix the report's unit caption and measure on Draw D (seed `20261102`)? Or finish with Draw C as measured and this listed as a known defect?
