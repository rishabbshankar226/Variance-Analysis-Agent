# Clara: statement changes and covenant headroom

Clara is a credit analyst. She brings filings and a covenant schedule, and asks for leverage and coverage against covenant levels and for balance sheet and cash flow changes. She gets ratios from formulas she declares, headroom against each supplied limit, and statement changes with their identity checks. She never gets a default EBITDA definition, a rating or a default probability.

Every file here is fictional (tests/fixtures/analysts/), and every command below was run to produce the output shown (docs/analysts/evidence/build_guides.py).

Compare the balance sheet year on year. Every subtotal and the balance sheet identity are checked first.

```sh
variance-agent tests/fixtures/analysts/hal-20250927.htm --assisted --sheet 'Consolidated Balance Sheets' --compare-to prior-period --period 'Sep 2025' --dollar-threshold 1 --percent-threshold 1
```

Output:

````markdown
# Statement Comparison: Sep 2025

Reporting currency: USD

- Checked every subtotal and the balance sheet identity: Total assets equals Total liabilities and stockholders' equity in Sep 2025 and Sep 2024, within the rounding each figure's decimals state
- Compared each line as an Increase or Decrease of its printed figure: a figure printed in parentheses is negative, so a larger outflow or deduction shows as a Decrease
- Lines marked (Total) are the statement's own subtotals.

## Lines

| Line Item | Prior Period (Sep 2024) | Actual | Change | Change (%) | Direction | Material |
|---|---:|---:|---:|---:|---|---|
| Cash and cash equivalents | $2,000,000,000.00 | $2,600,000,000.00 | $600,000,000.00 | 30.0% | Increase | Yes |
| Accounts receivable, net | $770,000,000.00 | $800,000,000.00 | $30,000,000.00 | 3.9% | Increase | Yes |
| Total current assets (Total) | $2,770,000,000.00 | $3,400,000,000.00 | $630,000,000.00 | 22.7% | Increase | Yes |
| Property and equipment, net | $2,700,000,000.00 | $3,100,000,000.00 | $400,000,000.00 | 14.8% | Increase | Yes |
| Total assets (Total) | $5,470,000,000.00 | $6,500,000,000.00 | $1,030,000,000.00 | 18.8% | Increase | Yes |
| Accounts payable | $820,000,000.00 | $900,000,000.00 | $80,000,000.00 | 9.8% | Increase | Yes |
| Total current liabilities (Total) | $820,000,000.00 | $900,000,000.00 | $80,000,000.00 | 9.8% | Increase | Yes |
| Long-term debt | $1,500,000,000.00 | $1,500,000,000.00 | $0.00 | 0.0% | No change | No |
| Total liabilities (Total) | $2,320,000,000.00 | $2,400,000,000.00 | $80,000,000.00 | 3.4% | Increase | Yes |
| Common stock, $0.01 par value; 500 shares authorized; 120 and 118 shares issued | $1,000,000.00 | $1,000,000.00 | $0.00 | 0.0% | No change | No |
| Additional paid-in capital | $1,100,000,000.00 | $1,200,000,000.00 | $100,000,000.00 | 9.1% | Increase | Yes |
| Retained earnings | $2,149,000,000.00 | $2,999,000,000.00 | $850,000,000.00 | 39.6% | Increase | Yes |
| Treasury stock, at cost | -$100,000,000.00 | -$100,000,000.00 | $0.00 | 0.0% | No change | No |
| Total stockholders' equity (Total) | $3,150,000,000.00 | $4,100,000,000.00 | $950,000,000.00 | 30.2% | Increase | Yes |
| Total liabilities and stockholders' equity (Total) | $5,470,000,000.00 | $6,500,000,000.00 | $1,030,000,000.00 | 18.8% | Increase | Yes |
````

Compare the cash flow statement; cash must roll forward from beginning to ending balance.

```sh
variance-agent tests/fixtures/analysts/hal-20250927.htm --assisted --sheet 'Consolidated Statements of Cash Flows' --compare-to prior-period --period FY2025 --dollar-threshold 1 --percent-threshold 1
```

Output:

````markdown
# Statement Comparison: FY2025

Reporting currency: USD

- Checked every subtotal and the cash roll-forward: Ending cash equals beginning cash plus the flows printed between them in FY2025 and FY2024, within the rounding each figure's decimals state
- Left out 1 line after 'Cash, cash equivalents and restricted cash, end of year' (supplemental disclosures): 'Cash paid for interest'
- Compared each line as an Increase or Decrease of its printed figure: a figure printed in parentheses is negative, so a larger outflow or deduction shows as a Decrease
- Lines marked (Total) are the statement's own subtotals.

## Lines

| Line Item | Prior Period (FY2024) | Actual | Change | Change (%) | Direction | Material |
|---|---:|---:|---:|---:|---|---|
| Net income | $1,330,000,000.00 | $1,450,000,000.00 | $120,000,000.00 | 9.0% | Increase | Yes |
| Depreciation and amortization | $180,000,000.00 | $200,000,000.00 | $20,000,000.00 | 11.1% | Increase | Yes |
| Increase in accounts receivable | -$20,000,000.00 | -$30,000,000.00 | -$10,000,000.00 | -50.0% | Decrease, larger negative | Yes |
| Net cash provided by operating activities (Total) | $1,490,000,000.00 | $1,620,000,000.00 | $130,000,000.00 | 8.7% | Increase | Yes |
| Purchases of property and equipment | -$500,000,000.00 | -$600,000,000.00 | -$100,000,000.00 | -20.0% | Decrease, larger negative | Yes |
| Net cash used in investing activities (Total) | -$500,000,000.00 | -$600,000,000.00 | -$100,000,000.00 | -20.0% | Decrease, larger negative | Yes |
| Dividends paid | -$350,000,000.00 | -$400,000,000.00 | -$50,000,000.00 | -14.3% | Decrease, larger negative | Yes |
| Net cash used in financing activities (Total) | -$350,000,000.00 | -$400,000,000.00 | -$50,000,000.00 | -14.3% | Decrease, larger negative | Yes |
| Effect of exchange rate changes on cash | $10,000,000.00 | -$20,000,000.00 | -$30,000,000.00 | -300.0% | Decrease | Yes |
| Net increase in cash, cash equivalents and restricted cash (Total) | $650,000,000.00 | $600,000,000.00 | -$50,000,000.00 | -7.7% | Decrease | Yes |
| Cash, cash equivalents and restricted cash, beginning of year | $1,350,000,000.00 | $2,000,000,000.00 | $650,000,000.00 | 48.1% | Increase | Yes |
| Cash, cash equivalents and restricted cash, end of year (Total) | $2,000,000,000.00 | $2,600,000,000.00 | $600,000,000.00 | 30.0% | Increase | Yes |
````

Test the declared ratios against the covenant schedule. A metric the filing can't supply is left out by name.

```sh
variance-agent tests/fixtures/analysts/hal-20250927.htm --assisted --metrics tests/fixtures/analysts/clara_metrics.json --compare-file tests/fixtures/analysts/clara_covenants.csv --compare-to limit --period FY2025 --dollar-threshold 1 --percent-threshold 1 --multiple-threshold 0.1
```

Output:

````markdown
# Limit Comparison: FY2025

- Breach is strictly beyond a limit; a row exactly at its limit is At limit. Near appears only where a row declares a buffer. Headroom is limit minus actual for a Max and actual minus limit for a Min, so a negative headroom is a Breach for either kind. Utilization is actual over limit: above 100% is beyond a Max, and below 100% is short of a Min.

**0 Breach, 0 At limit, 1 Near, 1 Within.**

## Lines, by severity

| Line Item | Kind | Limit | Actual | Headroom | Headroom (% of limit) | Utilization | Buffer | Status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Gross leverage | Max | 1.25x | 0.88x | 0.37x | 29.4% | 70.6% | 0.5x | Near |
| Interest cover | Min | 4x | 34x | 30x | 750.0% | 850.0% | 1x | Within |

## Metrics

- Gross leverage = 0.88x = (Long-term debt \[balance sheet, instant\]) / (Net income \[income, fy\] + Interest expense \[income, fy\] + Depreciation and amortization \[cash flow, fy\])
  - Long-term debt \[balance sheet, instant\]: $1,500,000,000.00 (Sep 2025, hal-20250927.htm)
  - Net income \[income, fy\]: $1,450,000,000.00 (FY2025, hal-20250927.htm)
  - Interest expense \[income, fy\]: $50,000,000.00 (FY2025, hal-20250927.htm)
  - Depreciation and amortization \[cash flow, fy\]: $200,000,000.00 (FY2025, hal-20250927.htm)
- Interest cover = 34x = (Net income \[income, fy\] + Interest expense \[income, fy\] + Depreciation and amortization \[cash flow, fy\]) / (Interest expense \[income, fy\])
  - Net income \[income, fy\]: $1,450,000,000.00 (FY2025, hal-20250927.htm)
  - Interest expense \[income, fy\]: $50,000,000.00 (FY2025, hal-20250927.htm)
  - Depreciation and amortization \[cash flow, fy\]: $200,000,000.00 (FY2025, hal-20250927.htm)
  - Interest expense \[income, fy\]: $50,000,000.00 (FY2025, hal-20250927.htm)
- Left out 'Fixed charge cover': no line with us-gaap:OperatingLeasePayments on the cash flow statement for fy, so it can't be computed
````

## In the chat

In the chat, upload the 10-K and type **compare balance sheets**, then **covenant headroom**: upload the metrics file and the covenant schedule when asked, and confirm.
