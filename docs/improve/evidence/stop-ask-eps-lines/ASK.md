# STOP-ASK: a statement's "EPS" lines are read as money and scaled by its caption (X50, on `main`)

**Found** after the final STOP, on 2026-11-03, while reproducing what the Phase 8 reviewer had suspected but not reproduced: a PDF title's caption scaling "except per share" rows. A wrong number found after STOP 1 is a STOP-ASK. It is not on a 0.2.0 path: `pdf_tables.py` and `intake.py` did not exist at `5e288bb`.

**The cause.** A statement read by `pdf_tables.py` leaves a per-share line out, or with `--per-share-lines` keeps it as Per Share, unscaled. This covers a PDF and a sheet laid out like EDGAR's Financial_Report.xlsx, which share `_statement_table`. But it recognises a per-share line only by `_PER_SHARE_RE` ("per share", "shares outstanding", and similar), or by a Basic or Diluted line under such a heading. `\bEPS\b` is checked only when `--per-share-lines` is given. So "Basic EPS" and "Diluted EPS" stay money rows, and the statement's "$ in Millions" scales them by 1,000,000. The Inline XBRL reader is not affected: it scales each fact by its own `scale` attribute (`ixbrl.py`).

**Reproduced** with `--assisted --period FY2025 --dollar-threshold 1 --percent-threshold 1`. `build_inputs.py e1.xlsx` rebuilds the workbook. The branch and `main` (a detached worktree of `main`, with `PYTHONPATH` on its `src`) give the same report.

| File | Shown, on the branch and on `main` | What the source supports |
|---|---|---|
| `e1.xlsx`: "$ in Millions"; Basic EPS 6.1 and 5.5, Diluted EPS 6.0 and 5.4 | `\| Basic EPS \| Unclassified \| $5,500,000.00 \| $6,100,000.00 \| $600,000.00 \| 10.9% \|`, and the same for Diluted. They are left out of the totals as Unclassified, but shown, and the reader is asked to label them | $5.50 and $6.10 a share; the caption says "except per share" in the PDF form, and in the EDGAR form EPS is per share by definition |

**Recommendation.** Recognise `\bEPS\b` as a per-share line whatever `--per-share-lines` says, moving the check out of the flag's condition where it already lives. By default the line is then left out with the existing note ("Left out 'Basic EPS' (per-share and share counts are not money totals)"). With `--per-share-lines` it is kept as Per Share, unscaled, as today.
- **Boundary cases:** "Basic EPS", "Diluted EPS" and "Adjusted EPS" are left out. "Basic earnings per share" is left out, as before. "STEPS program costs" and "Epsilon fund income" stay money rows. With `--per-share-lines`, "Basic EPS" is Per Share, 6.10 unscaled.
- This changes no contract file. By grep, no PDF or EDGAR-sheet test has an EPS line, so no existing assertion changes.
- **The alternative** is to refuse a statement that holds an EPS line under a scaling caption. That is safe, but it stops statements that read right once the line is left out.

**Question.** May the run treat an "EPS" line as per-share, left out by default and kept as Per Share with `--per-share-lines` (recommended)? Or should it refuse such statements? It is marked `asked` in PLAN.md as X50.
