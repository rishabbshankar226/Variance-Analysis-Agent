# Owen: LTM against the management case

Owen is an investment banking analyst. He brings a target's last 10-K, its latest 10-Q and a management case, and asks for LTM revenue and EBITDA against the case and each statement year on year. He gets an LTM build with every component cited to its document and column, then the variance against the case. He never gets a valuation, multiples or enterprise value.

Every file here is fictional (tests/fixtures/analysts/), and every command below was run to produce the output shown (docs/analysts/evidence/build_guides.py).

Build LTM from the 10-Q and the 10-K: the income statement's fiscal year plus this year to date less last year to date, line by line by XBRL concept, compared with the fiscal year.

```sh
variance-agent tests/fixtures/analysts/hal-20260328.htm --assisted --ltm-from tests/fixtures/analysts/hal-20250927.htm --period 'LTM Mar 2026' --dollar-threshold 1 --percent-threshold 1
```

Output:

````markdown
# FP&A Variance Report: LTM Mar 2026

## Executive Summary
- Reporting Currency: USD
- Compared Against: Prior Period (FY2025)
- Total Revenue: $4,300,000,000.00 vs. $4,100,000,000.00 ($200,000,000.00, 4.9%, F)
- Total Expenses: $2,765,000,000.00 vs. $2,650,000,000.00 ($115,000,000.00, 4.3%, U)
- Bottom Line Impact: Revenue and expense variances imply a net operating variance of $85,000,000.00, above prior period on this simplified revenue-less-expense basis. The largest material variance is Net sales at $200,000,000.00 (F).

## Material Variances
Thresholds: $1.00 or 1.0%

| Line Item | Type | Prior Period (FY2025) | Actual | Var ($) | Var (%) | Status |
|---|---|---:|---:|---:|---:|---|
| Net sales | Revenue | $4,100,000,000.00 | $4,300,000,000.00 | $200,000,000.00 | 4.9% | F |
| Cost of sales | Expense | $2,300,000,000.00 | $2,400,000,000.00 | $100,000,000.00 | 4.3% | U |
| Research and development | Expense | $300,000,000.00 | $310,000,000.00 | $10,000,000.00 | 3.3% | U |
| Interest expense | Expense | $50,000,000.00 | $55,000,000.00 | $5,000,000.00 | 10.0% | U |

## Root Cause Analysis
- **Net sales (Hypothesis):** No causal driver is asserted from the supplied data. To validate a cause, provide volume/units, price/rate, customer count, and mix.
- **Cost of sales (Hypothesis):** No causal driver is asserted from the supplied data. To validate a cause, provide units/headcount, rate, vendor pricing, and timing.
- **Research and development (Hypothesis):** No causal driver is asserted from the supplied data. To validate a cause, provide units/headcount, rate, vendor pricing, and timing.
- **Interest expense (Hypothesis):** No causal driver is asserted from the supplied data. To validate a cause, provide units/headcount, rate, vendor pricing, and timing.

## Strategic Recommendations
- Mitigation: Cost of sales is the largest material U variance, but the dataset does not support a causal corrective action; obtain the missing operating driver data before assigning a cause-specific intervention.
- Optimization: Net sales is the largest material F variance, but the dataset does not support a causal corrective action; obtain the missing operating driver data before assigning a cause-specific intervention.
- Data Request: Provide reconciled operating driver metrics for: Net sales, Cost of sales, Research and development, Interest expense.

## LTM build

- Built LTM as FY2025 from 'hal-20250927.htm' plus 6 months to Mar 2026 less 6 months to Mar 2025 from 'hal-20260328.htm', line by line by XBRL concept
- Checked continuity: the prior year to date starts where FY2025 starts (2024-09-29), and the year to date starts the day after it ends (2025-09-28)
- Left out 'Basic (in dollars per share)': per-share amounts and share counts are not computable as LTM

| Line Item | FY2025 | + 6 months to Mar 2026 | - 6 months to Mar 2025 | = LTM |
|---|---:|---:|---:|---:|
| Net sales | $4,100,000,000.00 | $2,200,000,000.00 | $2,000,000,000.00 | $4,300,000,000.00 |
| Cost of sales | $2,300,000,000.00 | $1,200,000,000.00 | $1,100,000,000.00 | $2,400,000,000.00 |
| Research and development | $300,000,000.00 | $160,000,000.00 | $150,000,000.00 | $310,000,000.00 |
| Interest expense | $50,000,000.00 | $25,000,000.00 | $20,000,000.00 | $55,000,000.00 |
````

Compare declared LTM revenue and EBITDA with the case. The metrics file names each term by XBRL concept and period; EBITDA here is net income plus interest plus D&A from the cash flow statement, as declared.

```sh
variance-agent tests/fixtures/analysts/hal-20260328.htm --assisted --ltm-from tests/fixtures/analysts/hal-20250927.htm --metrics tests/fixtures/analysts/owen_case_metrics.json --compare-file tests/fixtures/analysts/owen_case.csv --period 'LTM Mar 2026' --dollar-threshold 1 --percent-threshold 1
```

Output:

````markdown
# Variance Report: LTM Mar 2026

Reporting currency: USD

## Currency totals

Currency totals are incomplete; net operating impact is unavailable.

## Currency variances

| Line Item | Measure | Budget | Actual | Variance | Var (%) | Status | Material |
|---|---|---:|---:|---:|---:|---|---|
| LTM revenue | Currency | $4,250,000,000.00 | $4,300,000,000.00 | $50,000,000.00 | 1.2% | F | Yes |
| LTM EBITDA | Currency | $1,750,000,000.00 | $1,800,000,000.00 | $50,000,000.00 | 2.9% | F | Yes |

## How the file was read
- LTM revenue: read Better to Higher.
- LTM EBITDA: read Better to Higher.

## Metrics

- LTM revenue = $4,300,000,000.00 = Net sales \[income, ltm\]
  - Net sales \[income, ltm\]: $4,100,000,000.00 (FY2025, hal-20250927.htm) + $2,200,000,000.00 (6 months to Mar 2026, hal-20260328.htm) - $2,000,000,000.00 (6 months to Mar 2025, hal-20260328.htm) = $4,300,000,000.00
- LTM EBITDA = $1,800,000,000.00 = Net income \[income, ltm\] + Interest expense \[income, ltm\] + Depreciation and amortization \[cash flow, ltm\]
  - Net income \[income, ltm\]: $1,450,000,000.00 (FY2025, hal-20250927.htm) + $815,000,000.00 (6 months to Mar 2026, hal-20260328.htm) - $730,000,000.00 (6 months to Mar 2025, hal-20260328.htm) = $1,535,000,000.00
  - Interest expense \[income, ltm\]: $50,000,000.00 (FY2025, hal-20250927.htm) + $25,000,000.00 (6 months to Mar 2026, hal-20260328.htm) - $20,000,000.00 (6 months to Mar 2025, hal-20260328.htm) = $55,000,000.00
  - Depreciation and amortization \[cash flow, ltm\]: $200,000,000.00 (FY2025, hal-20250927.htm) + $110,000,000.00 (6 months to Mar 2026, hal-20260328.htm) - $100,000,000.00 (6 months to Mar 2025, hal-20260328.htm) = $210,000,000.00
````

## In the chat

In the chat, upload the 10-Q, choose **Build LTM**, upload the 10-K when asked, and confirm the summary.
