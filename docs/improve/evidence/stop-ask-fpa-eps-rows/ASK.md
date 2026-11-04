# STOP-ASK: a budget file's "EPS" row with no Measure column is scaled by its caption (X53, on `main`; C2 widens it)

**Found** on 2026-11-03, while checking how far X50's cause reaches before fixing X50. A wrong number found after STOP 1 is a STOP-ASK, and X50's approval covered statements read by `pdf_tables.py` only. It is not on a 0.2.0 path: `intake.py` and `comparisons.py` did not exist at `5e288bb`, and the strict reader applies no caption.

**The cause.** In a CSV or workbook that FP&A intake reads, a row with no Measure column is a Currency row, whatever its label says. `measure_kind(None, "Basic EPS")` is Currency. So a caption such as "(in millions, except per share data)" scales a "Basic EPS" row with the money rows. With `--per-share-lines`, the run goes through the comparison path. On `main` that path applied no caption at all, so EPS read right by accident while Net sales read 1,000,000 times too small. C2 made the comparison path apply the caption, which fixed Net sales and scaled EPS with it. A Measure column that says Per Share reads the row right on every path.

**Reproduced** with `--assisted --period FY2025 --dollar-threshold 1 --percent-threshold 1`, with and without `--per-share-lines`, on the branch and on `main` (a detached worktree of `main`, with `PYTHONPATH` on its `src`). The input and the outputs are in this folder.

| `k1.csv` (caption "(in millions, except per share data)"; Net sales 4,000 against 4,100; Basic EPS 5.50 against 6.10) | Net sales | Basic EPS |
|---|---|---|
| branch and `main`, no flag | $4,000,000,000.00 against $4,100,000,000.00 | **$5,500,000.00 against $6,100,000.00** (Unclassified, out of the totals, but shown) |
| `main`, `--per-share-lines` | **$4,000.00 against $4,100.00** (C2's cause, fixed on the branch) | $5.50 against $6.10 |
| branch, `--per-share-lines` | $4,000,000,000.00 against $4,100,000,000.00 | **$5,500,000.00 against $6,100,000.00** |
| What the source supports | $4.0bn against $4.1bn | $5.50 against $6.10 a share |

**Recommendation.** When a unit caption or heading unit would scale the amounts, a row with no declared Measure whose label names a per-share figure refuses before anything is scaled. "Names a per-share figure" uses the statement readers' own patterns (X50's `\bEPS\b`, and "per share", "shares outstanding", "weighted-average shares"). This applies on both readers, intake's `_unit_scale` and the comparison path's `_apply_unit_caption`. The refusal names the line and both ways forward: "'Basic EPS' looks like a per-share figure, which the caption's millions would scale as money. Add a Measure column that says Per Share for it, or leave the line out, then upload the file again."
- A file with a Measure column is unchanged, and so is one with no scaling caption: there is nothing to scale wrongly.
- **Boundary cases:** `k1` refuses with and without the flag. The same file with Measure "Per Share" on that row reads 5.50 and 6.10. "Basic EPS" with no caption reads unscaled, as today. "STEPS program costs" under a caption scales as money.
- This changes no contract file. By grep, no test has a per-share label without a Measure under a caption.
- **The alternative** is to read such a row as Per Share automatically, unscaled. That guesses a Measure, and it needs a per-share threshold the reader has not given. A refusal names the cause and the fix.

**Question.** May the run refuse a per-share row that has no Measure when a caption would scale it, on both readers (recommended)? Or should it read the row as Per Share automatically? It is marked `asked` in PLAN.md as X53.
