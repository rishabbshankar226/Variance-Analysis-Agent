# Limit Comparison: FY2025

Reporting currency: USD

- Breach is strictly beyond a limit; a row equal to its limit is Within. Near appears only where a row declares a buffer. Headroom is limit minus actual for a Max and actual minus limit for a Min, so a negative headroom is a Breach for either kind. Utilization is actual over limit: above 100% is beyond a Max, and below 100% is short of a Min.
- No revenue, expense or net totals apply to this comparison.

**0 Breach, 1 Near, 1 Within.**

## Lines, by severity

| Line Item | Kind | Limit | Actual | Headroom | Utilization | Buffer | Status |
|---|---|---:|---:|---:|---:|---:|---|
| Gross leverage | Max | 1.25x | 0.88x | 0.37x | 70.6% | 0.5x | Near |
| Interest cover | Min | 4x | 34x | 30x | 850.0% | 1x | Within |

## How the file was read
- Gross leverage: read Measure as Multiple.
- Interest cover: read Measure as Multiple.

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
