# Limit Comparison: Q3 2026

- Breach is strictly beyond a limit; a row exactly at its limit is At limit. Near appears only where a row declares a buffer. Headroom is limit minus actual for a Max and actual minus limit for a Min, so a negative headroom is a Breach for either kind. Utilization is actual over limit: above 100% is beyond a Max, and below 100% is short of a Min.

**0 Breach, 0 At limit, 0 Near, 1 Within.**

## Lines, by severity

| Line Item | Kind | Limit | Actual | Headroom | Headroom (% of limit) | Utilization | Buffer | Status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Fictional margin | Min | 40% | 40.3% | 0.3 bps | 0.8% | 100.8% | 0.005 bps | Within |

## How the file was read
- Comparing Actual against the limit.
- Fictional margin: read Limit and Actual as the percentages Excel shows (number format '0.0%').

