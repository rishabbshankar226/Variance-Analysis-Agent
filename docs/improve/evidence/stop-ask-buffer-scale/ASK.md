# STOP-ASK: a unit caption scales Limit, Benchmark and Target but not Buffer or Tolerance (X41)

**Found** in Phase 2 on 2026-11-02, while reading the FP&A caption path as the reference for C2. This is a wrong number found after STOP 1, so it is asked here. It is not on a 0.2.0 path: the limit, benchmark and target bases are 0.3.0 additions, and `intake.py` did not exist at `5e288bb`. So the run continues with independent work.

**The cause.** `intake.scale_rows_by_unit` (and `reconcile_declared_unit`, which calls it for a mapping's declared unit) multiplies only the `budget` and `actual` keys of a Currency row. Under a "($ in thousands)" caption, the Limit, Benchmark or Target (the row's comparison) and the Actual are scaled ×1,000. The declared `Buffer` and `Tolerance` are not, though `docs/financial-rules.md` states both "in the row's unit".

**Reproduced** with fictional CSVs in the git-ignored `.scratch/c2/` (`lim.csv`, `bench.csv`, `tgt.csv`), each run with `--assisted --compare-to limit|benchmark|target`:

| File | Shown | What the source supports |
|---|---|---|
| Limit 100, Actual 95, Max, Buffer 10, in thousands | headroom $5,000.00, buffer **$10.00**, **Within** | buffer $10,000.00, so 0 < headroom <= buffer: **Near** |
| Benchmark 100, Actual 105, Higher, Tolerance 10, in thousands | active $5,000.00, tolerance **$10.00**, **Higher than benchmark** | tolerance $10,000.00: **In line** |
| Target 100, Actual 105, Tolerance 10, in thousands | difference $5,000.00, tolerance **$10.00**, **Over** | tolerance $10,000.00: **On target** |

**Recommendation.** Scale a Currency row's `Buffer` and `Tolerance` by the same caption or declared unit, in the same place and by the same exact multiplication, and say so in the existing scaling note. Percent, Per Share, Count and Multiple rows stay unscaled, as now. Tests straddle the boundary at the scaled values: headroom equal to the scaled buffer is Near, one step more is Within, and the benchmark and target tolerances are pinned the same way. The fix changes no contract file, because the contracts cover the strict JSON path, and no financial rule, because the rules already say both values are in the row's unit. The alternative is to refuse a captioned file that declares a Buffer or Tolerance. That is safe, but it strands Ines and Theo on an ordinary ERP export.

**Question.** May the run scale Buffer and Tolerance with the caption (recommended), or should it refuse such files? It is marked `asked` in PLAN.md as X41, and the run continues with C2.
