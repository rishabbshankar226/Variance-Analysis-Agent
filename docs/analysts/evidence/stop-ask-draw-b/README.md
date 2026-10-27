# STOP-ASK: Draw B found a wrong number (2026-10-27)

Branch `analysts/filings-and-excel`. Section 5: "When Draw B finds a wrong number, take STOP-ASK with the evidence. A fix after Draw B is measured on a fresh Draw C … and Draw B's result stays in the report unchanged." Nothing has been fixed since the sweep. Per-filing detail is in `~/vaa-edgar-corpus/stop-ask-draw-b/findings.md` (constraint 7); this file names no company or accession.

## Draw B, as measured

Seed `20261029` (committed at `19e6840` before the draw): 15 10-K and 15 10-Q from 2025Q4-2026Q3, one per filer, excluding every Draw A accession and filer. Swept once at `3f731a7` (sweep `B-3f731a7`, results sha256 `e6b69e91a01ea85eb979dde7f94b3b86c396f0b3314c72cbb1aa1958761d8b7b`).

| Measure | Draw B (28 Inline XBRL filings) |
|---|---|
| Wrong values, as the sweep scores them | **1** (a derived revenue subtotal; every line value matched its fact). Fresh eyes found 3 more headline figures the sweep doesn't score; see below |
| Values verified / unverified | 4,193 / 42; every unverified one is a printed dash or confirmed blank with no fact behind it (Decision 35) |
| All three statements read, by section 5's definition | **12 of 28 (43%, Wilson 95% 27-61%)**, against the 90% target: not reached |
| All three read without a refusal | 18 of 28 (64%, 46-79%) |
| Read without a refusal, by statement | income 24/27, balance sheet 26/28, cash flow 23/28 |
| Fully read, by statement | income 19/27, balance sheet 23/28, cash flow 17/28 |
| Refusals | 10: cash flow 5, income 3, balance sheet 2; **9 plain, 1 not** |
| Of the 6 read without a refusal but not fully | 2 short only by dashes or confirmed blanks; 2 by dashes and an oracle line the reader doesn't cover; 1 by coverage; 1 by the wrong value |

- **Two 10-Ks without XBRL** (only the primary document in the folder) are outside the denominator. The oracle finds no statements, so the sweep has no rows; run by hand, each refuses plainly ("a web page without Inline XBRL figures … Upload the filing's 10-K or 10-Q document from its EDGAR folder, its PDF, or a CSV or Excel table").
- **One income statement was never swept.** Its title is "… Statements of Income (Loss) and Comprehensive Income (Loss)", and the oracle drops a statement titled as comprehensive income. That filing counts as not all-three-read above. Run by hand outside the aggregate, it reads, and its Total Revenue equals the filing's revenue facts.

## What was found

**W-B1, the wrong value.** A 10-Q prints a combined statement of operations and comprehensive loss, with 'Net loss' twice and a revenue line that is 0 this quarter. The tool typed 'Interest income' as revenue, so its revenue subtotal is the interest income (the report's headline reads "Total Revenue: N/A (classification incomplete; classified subtotal: …)", and the audit's `totals.revenue` holds the figure). The filing's revenue for the quarter is 0. Mechanism, read from the code with nothing changed:
1. Repeated labels are told apart by section, so the bottom line became "Operating expenses: Net loss".
2. Under that name the shaper doesn't treat it as net income, so it can't place 'Interest income' and leaves both untyped.
3. Decision 28's revenue-block step only moves lines already typed Revenue, so it skips the untyped one.
4. The engine then types 'Interest income' as Revenue by its label.

This is the same class as STOP 1's W3/W4: a headline derived figure that adds other income to revenue.

**A refusal that isn't plain.** One income statement refuses with "Total revenue, net: ambiguous summary label; specify Row Kind as Detail, Total, or Subtotal." A filing reader can't specify a Row Kind. This is the same family as the Phase 3 blank-amount message that Phase 4 fixed for filings.

**A misleading period label** (on the hand run above, not a swept figure). A 52/53-week filer's years ending 2026-01-03 and 2024-12-28 read as "comparing FY2026 against FY2024", which suggests a two-year gap between consecutive years.

**Browser check** (77 images in `shots/`, 1280 and 375 px; each new reader from upload to first answer). The numbers shown are right, and each reader reaches a first answer. Three presentation defects:
- **Raw Markdown tables in chat replies.** The statement reports (since Phase 4; also in STOP 2's `bs-report` shots, which I missed then) and the answers to "which limits are breached", "drift from target" and "active return" print their tables as raw `|` text.
- **The results panel for limit, benchmark and target runs keeps the budget layout.**
  - It shows "Currency totals are incomplete; net operating impact is unavailable".
  - It shows Variance % and Material columns where headroom and utilization belong.
  - It lists rows in file order, not by severity.
  - It offers Export Excel, which then refuses.
- **The drop zone's new subtitle shows correctly** ("… or a 10-K or 10-Q as .htm or PDF").

## Fresh eyes on five Draw B filings

Five Draw B Inline XBRL filings were drawn with `random.Random(20261030).sample`, the seed committed before the draw. By chance, the sample includes the W-B1 filing and the filing with the non-plain refusal. A subagent with none of this plan's reasoning checked every figure in the 13 reports against each filing's printed tables and instance, defaulting to "wrong" under doubt. It reported:
- **All 10 balance sheet and cash flow reports clean.** Every line, variance, subtotal, identity and period is right.
- **35 wrong cells under a strict sign rule** (25 under a looser one), all in the three income reports.

My check of those 35:

| Cells | What | Verdict |
|---:|---|---|
| 4 | W-B1's revenue subtotal, change and percent | **wrong**, as above |
| 8 | The Total Expenses headline in two filings (an amount, a comparison, a change and a percent each) | **wrong.** It is the tool's revenue-less-expense basis: every cost line down to net income, net of credited other income. The filing prints a narrower "Total expenses" or "Total operating expenses", and the two differ by the non-operating items |
| 1 | "Net operating variance" in one filing | **wrong name.** The figure is the change in net loss, not in operating loss |
| 12 | Gains and other income shown as negative expenses in two filings | **by the approved rule** (Decision 28: a credit among costs, sign turned). The values are each fact negated. But the Markdown report omits the note that says so: it is only on stderr and in the audit, so a reader of the report can't tell why |
| 10 | Expense-named lines whose facts are negative (for example, "Other expense, net") | **not wrong:** shown as printed, per R1, and the stored values match the facts |

**Surviving: 4 wrong headline figures in 3 of the 5 filings. No line value is wrong.** The expense headline and the "net operating" name come from the revenue-less-expense summary, which every filing income read uses, so Draw A carries them too. No sweep scored them: the sweep checks Total Revenue only. The STOP 1 lesson, "score the totals against a filing fact too", was applied to revenue and not to the other headlines.

Also found:
- a stray "$" in two labels taken from the printed cell
- the R7 cue reading "smaller negative" or "larger negative" where one side is 0 (from Phase 6)
- a second income refusal over a subtotal that sums the two printed just above it, whose suggested fix ("Upload the filing's PDF") rarely applies to a recent EDGAR filing (F2)

The reviewer's report, checker and output are in `~/vaa-edgar-corpus/stop-ask-draw-b/`.

## Gates at `3f731a7`

`sh docs/ui/evidence/gates.sh dist`: ruff, mypy (71 files), pytest **2,467 passed**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, and both artifacts installed without the Excel and PDF extras. **All PASS.** The log is at `~/vaa-edgar-corpus/stop-ask-draw-b/gates_dist.log`.

## Recommendation

Fix, then measure on a fresh Draw C, and keep Draw B's numbers in REPORT.md exactly as above. A wrong number is the one outcome this run may not ship, and W-B1 is a reachable shape: a combined operations-and-comprehensive-loss statement is common among small filers.

Tool fixes. Each one gets a fictional fixture built by `build_ixbrl.py` first, failing before the fix:
1. **Net income found by concept, not by name.** The bottom line (`NetIncomeLoss`, `ProfitLoss`) is net income whatever name repeated-label handling gives it. A repeated label is named by its place ("Net loss (2)") when one occurrence is the bottom line, never by a section it doesn't belong to.
2. **Decision 28 applies to the final types.** On a filing read where the statement prints its revenue, a line outside that revenue block is never counted as revenue, however it is typed later (by the shaper, by its label, or by an answer). It becomes a credit among costs, with the same note.
3. **Filing refusals name a filing fix.** The "ambiguous summary label" stop on a filing says which line it couldn't place and offers the PDF, or a CSV or Excel copy with a Row Kind column, as the Phase 4 blank-amount message does.
4. **52/53-week years are named by their end month** ("Jan 2026 against Dec 2024"), so consecutive years never read as a gap.
5. **A filing's income headline shows only the filing's own totals.** That means revenue, plus whichever of total expenses, operating income and net income the statement prints, each from its fact. The revenue-less-expense Total Expenses and the "net operating variance" are not shown for a filing. The sweep then checks every headline figure against its fact, not only revenue.
6. **The report carries the reading notes.** A Decision 28 credit says in the report itself that the line is read as a credit among costs, and why.
7. **Small fixes:**
   - no stray "$" in labels
   - the R7 cue only where both figures are negative
   - a filing refusal suggests a CSV or Excel copy before a PDF

Chat fixes (from the browser check, not from Draw B):
- render Markdown tables in replies
- give limit, benchmark and target runs their own results panel: outcome, headroom and utilization, ordered by severity, with no budget totals line and no Export Excel

Sweep fix: the oracle takes an "income … and comprehensive income" title as the income statement.

Then Draw C:
- seed `20261031`, committed to PLAN.md as a Decision before the draw
- 30 filings drawn exactly as Draw B was, excluding every Draw A and Draw B accession and filer
- swept once on the fixed code
- a final fresh-eyes check on five Draw C filings
- full gates
- REPORT.md with Draw B and Draw C side by side

The alternative is to report Draw B as measured and finish without fixes. I don't recommend it, because the tool would ship with a known way to put interest income into revenue.

**Questions**
1. Fix items 1-7 and the chat and sweep items, then measure on Draw C (seed `20261031`)? Or report Draw B as measured and finish? Item 5 changes what a filing's income report shows: the revenue-less-expense Total Expenses and net operating variance give way to the filing's own printed totals.
2. The 90% target is not reached on Draw B under Decision 35's strict definition (43%, 27-61%; 64% without a refusal). Report it so, as Decision 38 already provides?
