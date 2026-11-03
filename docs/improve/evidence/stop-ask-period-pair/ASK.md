# STOP-ASK: period-paired columns read the last pair by position, under the report's period heading (X48, from main; M3 widens it)

**Found** in Phase 8 on 2026-11-03 by the fresh-eyes reviewer for unsupported numbers, for bare years. Reproduced here, and the same cause shows on `main` for month and fiscal-year headings. A wrong number found after STOP 1 is a STOP-ASK. It is not on a 0.2.0 path: `intake.py` did not exist at `5e288bb`.

**The cause.** When headings pair Budget and Actual by period, intake reads `pairs[-1]`, the last pair by column position, unless a mapping or the chat names one (`intake.py`, the header scan and the "Analyzed period" note). The report is headed with `--period`, which is never matched against the pairs. When the columns run newest first, the older pair is read under the newer heading. The only trace is the "Analyzed period" line on stderr; the report body does not name it. M3 added bare years ("2026 Budget") to this path. The year-band workbook path already reads the newest pair, as M3's test says.

**Reproduced** with `--assisted --dollar-threshold 1 --percent-threshold 1` (inputs and outputs here):

| File and `--period` | Shown | What the source supports |
|---|---|---|
| `d1.csv`: 2026 Budget, 2026 Actual, 2025 Budget, 2025 Actual; `2026` | "FP&A Variance Report: 2026", Fictional Sales $100.00 against $110.00 (the 2025 figures) | 2026: $200 against $230. `main` asks which column to compare against |
| `d3.csv`: Sep 2026 then Aug 2026 pairs; `"Sep 2026"` | "Sep 2026" with Aug 2026's $100.00 against $110.00, on the branch and on `main` | Sep 2026: $200 against $230 |
| `d4.csv`: FY2026 then FY2025 pairs; `FY2026` | "FY2026" with FY2025's figures, on the branch and on `main` | FY2026: $200 against $230 |

Without `--assisted`, the branch's message for `d1.csv` says "rerun with --assisted to compare the newest year against the one before it", and the run that follows reads the older year. `--compare-to prior-period` refuses it ("No prior period column found"; `d1.prior-period.branch.err.txt`).

**Recommendation.** (1) When `--period` names one of the detected pairs (case-insensitive, as a mapping's period selection is matched today), read that pair. (2) Otherwise read the newest pair by period order (`order_period_labels`, which the prior-period path uses), not the last by position, and refuse with the pairs named when they cannot be ordered. Tests: `d1`, `d3` and `d4` read the 2026, Sep 2026 and FY2026 figures. Ascending columns read the same pair as today (`test_wide_month_layout_stays_budget` reads Feb-26). The band tests keep Q3 2026 and a named Q2 2026. The chat's typed period ("aug-26") still selects its pair, and a `--period` that names no pair reads the newest. This changes no contract file (the contract inputs have plain Budget and Actual keys) and, as far as I have read, edits no existing assertion. The alternative is to refuse a file with more than one pair when neither `--period` nor a mapping names one. That is safe, but it stops month layouts that read right today.

**Question.** May the run select the pair `--period` names, else the newest by period order (recommended)? Or should it refuse when no pair is named? It is marked `asked` in PLAN.md as X48.
