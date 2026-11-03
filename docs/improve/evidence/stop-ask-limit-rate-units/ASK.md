# STOP-ASK: a Percent limit row prints its headroom and buffer in percentage points with a "bps" label (X47, from main; N1 exports it)

**Found** in Phase 8 on 2026-11-03 by the fresh-eyes reviewer for unsupported numbers, and reproduced here. A wrong number found after STOP 1 is a STOP-ASK. It is on `main` but not on a 0.2.0 path: `--compare-to` did not exist at `5e288bb`. On this branch N1's Limits sheet also carries it.

**The cause.** The limit table in `report.py` formats a Percent row's headroom and buffer with `amount(d.headroom, row, variance=True)` and `amount(d.buffer, row, variance=True)`. Both values are in percentage points, the row's unit, and the formatter labels the number "bps". The target and benchmark tolerance a few lines below multiplies by 100 first ("A rate's tolerance is in percentage points; it is shown in basis points"). `xlsx.py` `_basis_figures` copies the report's text into the Limits sheet.

**Reproduced** with `c1.csv --assisted --compare-to limit --period "Q3 2026" --bps-threshold 1 --dollar-threshold 1 --percent-threshold 1 --xlsx c1.xlsx`:

| File | Shown (report and the Limits sheet's Headroom and Buffer cells) | What the source supports |
|---|---|---|
| `c1.csv`: Limit 40%, Actual 41%, Min, Buffer 0.5 | Headroom **1 bps**, Buffer **0.5 bps**, Within | 100 bps and 50 bps. The audit holds headroom "1" and buffer "0.5" (points) and difference_bps "100"; Within is right |

`main` prints the same Markdown (`c1.main.txt`). The audit, the status and the order are right; only the two displayed figures are off by a factor of 100.

**Recommendation.** Show a Percent row's headroom and buffer in basis points, multiplied by 100 as the tolerance is: "100 bps" and "50 bps". The Limits sheet copies the corrected text, and the audit is unchanged. Tests: `c1`'s report row and its Limits cells, a negative headroom (a Breach) and a zero buffer on a Percent row, and a Currency row unchanged. This changes no contract file (no contract has a limit basis) and edits no existing assertion (no test pins a Percent limit row). The alternative is to keep points and label them "pts", which matches the audit's unit but not the difference column the other bases show in bps.

**Question.** May the run show a rate's headroom and buffer in basis points (recommended), or in points labelled "pts"? It is marked `asked` in PLAN.md as X47.
