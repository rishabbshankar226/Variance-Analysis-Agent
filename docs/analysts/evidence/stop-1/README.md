# STOP 1 (after Phase 3), 2026-10-26

Branch `analysts/filings-and-excel`. The final sweep and the dist gates ran at tool commit `69d8366`, after the fixes the fresh-eyes review prompted. Aggregates only: per-filing rows, renders and the fresh-eyes report live in `~/vaa-edgar-corpus/stop-1/` (constraint 7).

## Draw A, before and after (40 filings, seed 20261026)

| Reader | Measure | Before (Phase 1 tool, `a4791bb`) | After (`69d8366`) |
|---|---|---|---|
| Inline XBRL primary `.htm` | statement runs | 116, all refused plainly | 116: 26 read, 90 refused plainly (balance sheets and cash flows until Phase 4; 6 documents without Inline XBRL) |
| | lines verified / unverified / wrong (incl. subtotals, listed lines, the Total Revenue check) | 0 / 0 / 0 | **1,041 / 13 / 0** |
| | income statements read (33 Inline XBRL filings) | 0 | **25 (76%, Wilson 95% 59–87%)**; 21 fully verified and covered (64%, 47–78%); 8 refused plainly: 5 subtotals whose lines could not be traced, 2 blank amounts, 1 with no income statement found |
| `Financial_Report.xlsx` (6 filings from 2018) | lines verified / unverified / wrong | 186 / 63 / **15** | **169 / 7 / 0** |

Results file sha256 (after, `69d8366`): `6805a39a8cb1aa01db8365d0a7874a1947d0d15fc71d878977b266c2a601253a`. The figures equal those at `d72d710`; only the notes changed. The sweep before the fresh-eyes fixes (`3439e0e`, sha256 `c520ca97…`) also showed zero wrong *line* values. It did not then check Total Revenue. Before: see `../draw_A_baseline.json`.

## Fresh eyes

Five Draw A Inline XBRL filings drawn with `random.Random(20261027).sample`. A subagent given none of the plan's reasoning checked the tool's income-statement outputs against each filing's printed statement and XBRL instance, defaulting to "wrong" under doubt. It ran on the outputs at `3439e0e` and found **4 wrong figures in two filings**, all the headline Total Revenue (actual and comparison). Every line value it checked (79 detail lines, 31 subtotals) matched its fact and its printed cell, and every variance recomputed.

Cause: the shared statement shaper labels every line that adds to income as revenue. Other income, equity earnings and gains, printed below the revenue total or as credits inside costs, joined Total Revenue. Fixes, for filing reads only (PDF reading unchanged), each pinned by a test:
1. Where the statement prints its revenue, only that block is revenue, and other income-increasing lines are cost-side credits, leaving net income and the net variance unchanged (`13a79e1`, `8d1ee72`).
2. The sweep re-run then caught one more filing the same way (a net loss and its attribution lines read as revenue). An income statement now ends at its first net-income line; the lines below it are listed as left out and recorded as read, and "Net (loss) income" label forms are subtotals (`9b137d9`, `d72d710`).
3. The sweep now checks Total Revenue against the filing's revenue fact, and the keys of subtotals and listed lines.
4. The shaper's "Labeled 'X' as revenue" note and its revenue/expense line count were written before the credit, so the summary overstated revenue lines on those filings. Both now follow the final labels (`69d8366`).

After the fixes, both flagged filings show the filing's printed revenue exactly, and the full Draw A re-sweep has zero wrong figures. The reviewer's notes that were not counted: one untagged all-dash zero line is not listed (no figure changes), and a $1k securities loss moves to expenses on a bank with no printed revenue total. Report: `~/vaa-edgar-corpus/stop-1/fresh_eyes_report.md`.

## Renders

Three Draw A income statements rendered by the tool beside EDGAR's own R page: `~/vaa-edgar-corpus/stop-1/render_<accession>.html`.

## Browser check

`shots/`: the screens Phases 1 and 3 changed, at 1280 and 375 px: an HTML filing's read summary and statement list, the hidden-rows question and its answer, and the formula refusal. Every file uploaded is fictional (`docs/analysts/evidence/shots_analysts.py`).

## Gates

`sh docs/ui/evidence/gates.sh dist` at `69d8366`: ruff, mypy (65 files), pytest **2317 passed**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, and both artifacts installed without the Excel and PDF extras: all PASS (log `~/vaa-edgar-corpus/stop-1/gates_dist_69d8366.log`). `mypy --strict docs/analysts/evidence/` is clean.
