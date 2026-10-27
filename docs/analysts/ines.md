# Ines: which limits are breached or close

Ines is a risk analyst. She brings exposures against limits by desk and metric, each limit marked Max or Min, and asks which limits are breached or close. She gets utilization and headroom labeled Breach, At limit, Near or Within, ordered by severity. She never gets VaR, stress results or predictions.

Every file here is fictional (tests/fixtures/analysts/), and every command below was run to produce the output shown (docs/analysts/evidence/build_guides.py).

Each exposure against its limit; Near only where a row declares a buffer.

```sh
variance-agent tests/fixtures/analysts/ines_limits.csv --assisted --compare-to limit --period 'Oct 2026' --dollar-threshold 1 --percent-threshold 1
```

Output:

````markdown
# Limit Comparison: Oct 2026

Reporting currency: USD

- Breach is strictly beyond a limit; a row exactly at its limit is At limit. Near appears only where a row declares a buffer. Headroom is limit minus actual for a Max and actual minus limit for a Min, so a negative headroom is a Breach for either kind. Utilization is actual over limit: above 100% is beyond a Max, and below 100% is short of a Min.

**2 Breach, 1 At limit, 1 Near, 1 Within.**

## Lines, by severity

| Line Item | Kind | Limit | Actual | Headroom | Headroom (% of limit) | Utilization | Buffer | Status |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Desk B gross exposure | Max | $500.00 | $510.00 | -$10.00 | -2.0% | 102.0% | $25.00 | Breach |
| Desk C liquidity reserve | Min | $100.00 | $95.00 | -$5.00 | -5.0% | 95.0% |  | Breach |
| Desk D liquidity reserve | Min | $100.00 | $100.00 | $0.00 | 0.0% | 100.0% | $10.00 | At limit |
| Desk A gross exposure | Max | $500.00 | $480.00 | $20.00 | 4.0% | 96.0% | $25.00 | Near |
| Desk E net exposure | Max | $500.00 | $300.00 | $200.00 | 40.0% | 60.0% |  | Within |
````

## In the chat

In the chat, upload the limits file (its Limit column is read as each row's limit), confirm, answer the period and thresholds, then ask **which limits are breached**.
