# Theo: active return against the benchmark

Theo is an asset management analyst. He brings fund returns against benchmark returns, fees against budget, and AUM and flows against plan, and asks for active return and cost and asset variance. He gets active return in basis points, higher or lower than the benchmark, and the fee and AUM variances. He never gets attribution the file does not supply, or forecasts.

Every file here is fictional (tests/fixtures/analysts/), and every command below was run to produce the output shown (docs/analysts/evidence/build_guides.py).

Each return and fee rate against its benchmark; In line within a declared tolerance.

```sh
variance-agent tests/fixtures/analysts/theo_benchmark.csv --assisted --compare-to benchmark --period 'Oct 2026' --dollar-threshold 1 --percent-threshold 1 --percent-values points --bps-threshold 1
```

Output:

````markdown
# Benchmark Comparison: Oct 2026

- Active difference is actual minus benchmark (basis points for rates). A row is In line when the difference is within its declared tolerance, edge included, or exactly zero without one; In line is Neutral. Otherwise F or U follows the row's declared Better direction. Higher and Lower than benchmark describe the figures, never whether that is good.

## Lines

| Line Item | Benchmark | Actual | Difference | Tolerance | Outcome | Status |
|---|---:|---:|---:|---:|---|---|
| Fund return | 6.8% | 7.25% | 45 bps | 10 bps | Higher than benchmark | Favorable |
| Tracking fund return | 5.05% | 5% | -5 bps | 5 bps | In line | Neutral |
| Management fee rate | 0.8% | 0.82% | 2 bps | none (exact) | Higher than benchmark | Unfavorable |

## How the file was read
- Read bare Percent values as points.
````

## In the chat

In the chat, upload the returns file (its Benchmark column is read as each row's benchmark), confirm, answer the period, thresholds and basis-point cutoff, then ask **active return**. Fees and AUM against budget or plan use the ordinary budget comparison, as in Maya's example in the README.
