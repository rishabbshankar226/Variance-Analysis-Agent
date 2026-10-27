# STOP 2 (after Phase 5), 2026-10-27

Branch `analysts/filings-and-excel`. Only aggregates are kept here. Per-filing rows, the fresh-eyes sample and report, and the sweep outputs live in `~/vaa-edgar-corpus/stop-2/` and `~/vaa-edgar-corpus/sweep_A_p5b-*` (constraint 7). Everything under `readers/` is fictional (HALVORSEN.FAKE and `.FAKE` tickers).

## Done since STOP 1

- **Phase 4.**
  - Balance sheets and cash flow statements from Inline XBRL are compared as Increase or Decrease, after every subtotal foots and the identity holds (R7-R9).
  - LTM is built from a 10-K and a 10-Q (`--ltm-from`, and "Build LTM" in the chat), with every component cited (R10-R11).
  - Budget and actuals in two files join on a shared key (`--compare-file`, two uploads in the chat), which closes F4 (R12).
- **Phase 5.**
  - `limit`, `benchmark` and `target` bases (R13-R15).
  - The `Multiple` measure (R16).
  - Derived metrics declared in a mapping file and compared with a case or covenant schedule (R17).
  - All are opt-in, recorded in audit 1.9 and documented in `docs/financial-rules.md`. Each has a Fraction oracle and straddling tests at Breach/Near, Near/Within and In line/Above.
- **Contracts.** The 19 contract fixtures and schemas 1.0-1.8 are unchanged.

## Draw A at STOP 2

The final sweep ran at `1d903a6` (`p5e`, after the fresh-eyes fixes); the results file sha256 is `13badea7ffaa02efe6ff99c1e1e91a59f460f5eb3a834e8edc12228406474332`.

| Measure | Inline XBRL primaries (33 filings) |
|---|---|
| Wrong values | **0** |
| Values verified / unverified | 5,560 / 78; every unverified one is a printed dash or a confirmed blank, with no fact behind it (Decision 35) |
| All three statements read, by section 5's definition | **15 of 33 (45%, Wilson 95% 30-62%)** |
| All three read without a refusal | 26 of 33 (79%, 62-89%) |
| Read without a refusal, by statement | income 27/33, balance sheet 32/33, cash flow 32/33 |
| Refusals | 25, every one plain |
| Of the 26 read without a refusal but not 15 fully | 6 short only by printed dashes or confirmed blanks (no fact behind them, Decision 35); 5 missing an oracle line the reader doesn't cover |

The `Financial_Report.xlsx` reader on the six 2018 filings: 169 verified, 7 unverified, 0 wrong.

Earlier sweeps at this stop (`p5-f3e0a5f`, `p5b-8e7131e`) also showed zero wrong. The fresh-eyes sample came from `p5-f3e0a5f`. Between `p5b` and `p5e`:
- Income went from 28 to 27, because the SPAC's balance sheet is no longer counted as its income statement.
- One sweep (`p5d`) misparsed the statement listing after its refusal gained a fix sentence; the sweep was fixed (`1d903a6`) and rerun.

## Per-reader reviews

One subagent per new seat got that seat's row of section 3 and its outputs (`readers/<seat>/`), and none of the plan's reasoning. **None found a wrong number.**

What their findings changed, before this stop:
- **Owen.** A metric term now uses its stored XBRL value, so one metrics file gives the same EBITDA however a filing prints interest; R17 was amended. The report cites every term and LTM component.
- **Clara.**
  - The identity record states its rule and every subtotal's terms (R9).
  - The statement report lists supplemental lines left out.
  - The covenant formulas show natural signs.
- **Marcus and Theo.**
  - A rate's tolerance is shown in bps.
  - A missing tolerance says "none (exact)".
  - The benchmark note says In line is Neutral and the edge counts.
  - The target table drops its empty Status column.
- **Ines.** The limit report opens with its Breach/Near/Within count and says how to read a Min limit's utilization.
- **Chat.** The screenshot run found that a request for a second file (LTM's 10-K, the other half of a pair) showed no drop zone. That reply now carries one.

The outputs as reviewed are in `reviewed-before-fixes/`, which the reviewers' line numbers refer to. The outputs under `readers/` were regenerated after the fixes.

Raised for the owner, since they are rules or Phase 6 work, not defects:
- the Increase/Decrease wording on printed negatives (R7)
- a row at its limit with a buffer reading Within (section 3's own words)
- the breach ranking and the reading of a Min limit's utilization
- no default early-warning band
- Above and Below on a fee row
- FP&A wording and fields left over in the new seats' reports and audits
- display precision
- a percentage shown on a sign flip

## Fresh eyes

The sweep verifies values by XBRL key, and Total Revenue only where a filing prints one dimensionless revenue fact. It cannot see a wrong label on a right value, or wrong typing behind a bank's headline totals; fresh eyes on 5 filings caught both. After the fixes, the bank's balance sheet (sweep `p5e`) names its unlabeled subtotal by concept, beside one 'Total shareholders' equity', and its income read credits no line among costs.


Five Draw A Inline XBRL filings were drawn with `random.Random(20261028).sample`, the seed committed before the draw. A subagent with none of the plan's reasoning checked the tool's balance sheet, cash flow and income outputs (sweep `p5-f3e0a5f`) against each printed filing and its instance, defaulting to "wrong" under doubt. It reported **4 wrong figures in 2 filings**:
- **W1.** A SPAC's "income" output was its balance sheet.
- **W2.** A bank's unlabeled equity-before-treasury subtotal was named "Total Shareholders' equity".
- **W3, W4.** The same bank's headline Total Revenue and Total Expenses: interest income was credited among costs, because a revenue-from-contracts breakdown was taken for the filing's revenue.

Every line value it checked matched its fact and its printed cell, and every variance and identity recomputed.

What was done:
- **W1** is a sweep artifact. The tool lists no income statement for that filing, whose two periods differ in length, so the sweep ran without naming one and the tool read its default statement. The sweep now asks for the statement by the filing's title and scores the tool's plain refusal (`abbb52e`).
- **W2-W4** were real and are fixed, each pinned by a fictional test (`141c236`, Decision 37).

Report: `~/vaa-edgar-corpus/stop-2/fresh_eyes_report.md`.

## Browser check

`shots/` holds 43 images, at 1280 and 375 px, of every chat screen this run changed:
- the HTML filing summary and statement list
- the hidden-rows question and its answer
- the formula refusal
- choosing and comparing a balance sheet, through to its report
- Build LTM with the 10-K as a second upload
- a budget file asking for its actuals, then the joined summary

Every file uploaded is fictional (`../shots_analysts.py`). The first run stopped at the second upload because no drop zone was shown; that was fixed (`52ae8ab`) and the run repeated.

## Gates

`sh docs/ui/evidence/gates.sh dist` at `95a13f7` (`src/` unchanged since): ruff, mypy (70 files), pytest **2449 passed**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, and both artifacts installed without the Excel and PDF extras: **all PASS**. The log is at `~/vaa-edgar-corpus/stop-2/gates_dist.log`.
