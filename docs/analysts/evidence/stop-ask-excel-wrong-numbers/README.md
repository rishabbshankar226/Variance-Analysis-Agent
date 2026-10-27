# STOP-ASK: E1, E2, E7 (excel wrong numbers)

Written at the end of Phase 0, 2026-10-26, on `analysts/filings-and-excel` cut from `8a609c4`.
The three recommendation paragraphs are in `docs/analysts/PLAN.md` under "STOP-ASK: E1, E2, E7", and the rules behind them under R2, R3 and R4.

Evidence: the Appendix A probes (fictional values), rebuilt outside the tree in `~/vaa-edgar-corpus/probes/` and run with
`variance-agent FILE --assisted --period X --dollar-threshold 1 --percent-threshold 1` on Python 3.11.16:

| Probe | Outcome at `8a609c4` | True figure |
|---|---|---|
| E1 `e1_display_scaled.xlsx` | Total Revenue $110,000,000.00 vs $100,000,000.00; "Amounts scaled from thousands (x1,000)" | $110,000 vs $100,000 |
| E2 `e2_hidden_rows.xlsx` | Total Expenses $50.00 vs $45.00, no mention of hidden row 3 or hidden column E | the analyst's choice: $50/$45 with row 3, $45/$40 without |
| E7 `e7_no_cached_results.xlsx` | "Row 4, Total, Actual column: the amount is blank." | no saved result; open and save in Excel |
| E7b `e7b_budget_formula.xlsx` | "Treated blank budgets as 0 on 1 unbudgeted line"; Total Revenue $180.00 vs $100.00 | budget $160.00 |

No existing test assertion changes for any of the three (see PLAN, "Existing assertions expected to change").
