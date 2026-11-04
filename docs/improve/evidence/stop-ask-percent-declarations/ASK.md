# STOP-ASK: a Tolerance or Buffer cell Excel shows as a percentage keeps its stored fraction (X46, from X31)

**Found** in Phase 8 on 2026-11-03 by the fresh-eyes reviewer for unsupported numbers, and reproduced here. A wrong number found after STOP 1 is a STOP-ASK. It is not on a 0.2.0 path: the limit and target bases and `comparisons.py` came after `5e288bb`.

**The cause.** X31 reads a Percent row's comparison and Actual cells as the percentage Excel shows when their number format shows one (`intake.py` `_apply_measure`; `comparisons.py` `_percent_as_shown`, over `_amount_columns` only). The row's Tolerance or Buffer under the same kind of format is left as stored. A Tolerance cell that holds 0.0025 and shows "0.25%" is then read as 0.0025 percentage points, since `docs/financial-rules.md` states a rate's Tolerance and Buffer "in the row's unit, percentage points for rates".

**Reproduced** with `--assisted --compare-to target|limit --period "Q3 2026" --bps-threshold 1 --dollar-threshold 1 --percent-threshold 1`. `build_inputs.py b1.xlsx b2.xlsx b2n.xlsx` rebuilds the three workbooks.

| File | Shown (report and the Targets or Limits sheet) | What the source supports |
|---|---|---|
| `b1.xlsx`: Target 40.0%, Actual 40.2%, Tolerance 0.0025 under `0.00%` (shows 0.25%) | Difference 20 bps, Tolerance **0.25 bps**, **Over**; audit tolerance "0.0025" | Tolerance 25 bps, so 20 bps is within it: **On target** |
| `b2.xlsx`: Limit 40.0%, Actual 41.0%, Min, Buffer 0.005 under `0.0%` (shows 0.5%) | Buffer **0.005 bps**, Within | buffer 0.5 points; Within is right here |
| `b2n.xlsx`: the same with Actual 40.3% (headroom 0.3 points) | Buffer 0.005 bps, **Within** | 0 < 0.3 <= 0.5: **Near** |

`main` refuses both workbooks ("bare rate in Target needs --percent-values points or fractions"; `*.main.err.txt`). With `--percent-values fractions`, `main` reads Target and Actual as fractions and the Tolerance as 0.0025 points: 0.25 bps, Over (`b1.main-fractions.txt`). That follows the rule's "percentage points for rates" whatever the flag, so I do not count it as a wrong number, but a reader who sets `fractions` may expect otherwise.

**Recommendation.** On a Percent row, read a Tolerance or Buffer cell that Excel shows as a percentage as that percentage, in points (0.0025 under `0.00%` reads 0.25), by the same exact multiplication X31 uses, with a Fraction oracle. Name it in X31's note ("read Target, Actual and Tolerance as the percentages Excel shows"), in both readers. Tests: `b1` is On target, and a tolerance one step below the difference is Over. The limit's Near and Within are straddled at the converted buffer, and a Currency row's declarations are unchanged. This changes no contract file and no financial rule, and edits no existing assertion (`tests/test_percent_formats.py` has no declaration cells). The flag's reading of bare declarations stays as the rule states it: changing that would be a rule change, which is a STOP-ASK of its own, and I do not recommend it. The alternative is to refuse a percent-formatted Tolerance or Buffer cell, naming the cell and asking for points.

**Question.** May the run read percent-formatted Tolerance and Buffer cells as the percentages they show (recommended), or should it refuse them? It is marked `asked` in PLAN.md as X46.
