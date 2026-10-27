# STOP-ASK: Draw D's final fresh eyes found wrong figures in labels (2026-10-27)

Branch `analysts/filings-and-excel`. Draw D was the measure for Decision 40's fix, and informs no code change. Nothing has been changed since its sweep. Per-filing detail is in `~/vaa-edgar-corpus/final-d/`. This file names no company or accession.

## Draw D, as swept once at `0f1d284`

**0 wrong values**, with every line and every headline figure scored. 3,888 values were verified and 51 unverified, all printed dashes or confirmed blanks with no fact behind them.

All three statements were read on **11 of 28** Inline XBRL filings (39%, 24-58%), and 19 of 28 without a refusal (68%, 49-82%). The 90% target is not reached.

There were 12 refusals, **all plain**. Draw A re-swept on the same code is unchanged in every scored row.

## Fresh eyes (seed `20261103`)

Five Draw D filings were drawn with the seed committed before the draw, and checked by a subagent with none of this plan's reasoning. Amounts inside labels were named in its brief. It traced 280 table rows and 18 headline lines to their facts and printed cells. **Every line value, subtotal, change, percent, headline figure and identity matched.** What it found is in label text:

| Found | Verdict |
|---|---|
| **3 wrong amounts** in one balance sheet's labels: "$0.010.01 par value", "75,000,00075,000,000 shares authorized" and "403,351403,351" (treasury shares), where the filing prints "$0.01", "75,000,000" and "403,351" | **Wrong figures**, confirmed against the filing |
| 2 cash flow rows named "Cash Flows from Financing Activities: Cash and cash equivalents … at beginning/end of period". The prefix is a section they aren't in | **Wrong labels**, no figure changed |
| A note reading "Read 'Restructuring' as a credit among costs" on a line printed as dashes in both compared years | **Wrong note**, no figure changed |
| A headline "Total expenses: -$408,747,000.00 vs. -$378,446,000.00 (-$30,301,000.00, -8.0%)": the filing prints the total in parentheses | Follows the stated rule (printed figures), but reads as a fall when expenses rose. Doubtful |

**The cause of the wrong amounts.** One filing agent's documents wrap each figure in a label inside two nested `-sec-ix-hidden` spans, each pointing at a hidden fact. The reader prints the figure once for each span.

**How far it reaches.** Labels holding a doubled figure (three or more characters repeated back to back):

| Draw | Labels | Filings |
|---|---:|---:|
| A | 7 | 5 |
| B | 3 | 2 |
| C | 3 | 3 |
| D | 6 | 3 |

All are equity labels: par value, shares authorized, issued, outstanding or held in treasury. The class has been there since Phase 3, and no earlier review or sweep caught it, because the sweep scores no label text.

**Also found** (known limits):
- 10-Q column labels don't state the period's length (three months against nine).
- A balance sheet refused on a line under a printed Total that the reviewer finds plain arithmetic.
- A refusal that blames the reader where the filing's own figures don't add up by 10,000.
- Footnote-like "(1)/(2)" suffixes on repeated labels, which is the documented naming.

## Recommendation

Fix, then measure on a fresh Draw E. Add a label check to the sweep, so the measure itself catches this class instead of fresh eyes alone.

1. **Nested hidden spans.** A figure is printed once, however many hidden-fact spans wrap it.
2. **Section names.** A repeated label is never named by a section whose own subtotal comes before it. Today only a line starting "Total" closes a section; a cash flow section closed by "Net cash … activities" should count too.
3. **Decision 28.** No credit among costs is noted for a line whose compared figures are both dashes or zero.
4. **Headline cue.** A headline figure printed negative in both columns gets R7's "larger negative" or "smaller negative" cue, as statement lines do.
5. **Sweep.** A line label holding a doubled figure scores as wrong. A label's section prefix must be a heading printed above it, after the previous subtotal, or it scores as wrong.

Each fix gets a fictional fixture that fails first. Draw A is re-swept with the new label checks, then measured on Draw E:
- **Seeds:** Draw E seed `20261104`, and fresh-eyes seed `20261105`, committed as a Decision before the draw.
- **The draw:** 30 filings, excluding Draws A-D, swept once.
- **The report:** Draws B, C and D stay in REPORT.md as measured.

The alternative is to finish with Draw D as measured and these listed as known defects. Every round of fresh eyes has found a new class in what the sweep doesn't score: headline figures at B, label units at C, label text now. So I recommend the fix with the sweep's label checks, so Draw E is measured on labels too.

**Question.** Fix items 1-5 and measure on Draw E (seed `20261104`)? Or finish with Draw D as measured and these listed as known defects?
