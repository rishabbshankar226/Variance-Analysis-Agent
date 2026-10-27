# Marcus: drift from target and the holdings scorecard

Marcus is a portfolio manager. He brings a holdings sheet with target and actual weights and a consensus panel for the holdings, and asks for drift from target and how the book's holdings reported. He gets drift in basis points labeled Over, Under or On target, and the weight share of holdings labeled Beat, Miss or In line. He never gets trades or rebalancing advice.

Every file here is fictional (tests/fixtures/analysts/), and every command below was run to produce the output shown (docs/analysts/evidence/build_guides.py).

Drift of each holding's weight from its target, with a declared tolerance band.

```sh
variance-agent tests/fixtures/analysts/marcus_targets.csv --assisted --compare-to target --period 'Oct 2026' --dollar-threshold 1 --percent-threshold 1 --percent-values points --bps-threshold 1
```

Output:

````markdown
# Target Comparison: Oct 2026

- Difference is actual minus target (basis points for rates). A row is On target when the difference is within its declared tolerance, edge included, or exactly zero without one. A target is neutral: no F or U.

## Lines

| Line Item | Target | Actual | Difference | Tolerance | Outcome |
|---|---:|---:|---:|---:|---|
| NORDVIK.FAKE | 12% | 12.4% | 40 bps | 25 bps | Over |
| HALVORSEN.FAKE | 8% | 7.9% | -10 bps | 25 bps | On target |
| OSTRAVA.FAKE | 6% | 5% | -100 bps | 25 bps | Under |

## How the file was read
- Read bare Percent values as points.
````

Label each holding by its diluted EPS against consensus and share the book's weight out by label.

```sh
variance-agent tests/fixtures/analysts/marcus_holdings.csv --assisted --panel tests/fixtures/analysts/marcus_panel.csv --join-key Ticker --deciding-metric 'Diluted EPS' --period 'Q3 2026' --dollar-threshold 1 --percent-threshold 1 --per-share-threshold 0.01
```

Output:

````markdown
# Variance Report: Q3 2026

Reporting currency: USD

## Currency totals

Currency totals are incomplete; net operating impact is unavailable.

## Other measures

| Line Item | Measure | Consensus | Actual | Variance | Var (%) | Status | Material |
|---|---|---:|---:|---:|---:|---|---|
| NORDVIK.FAKE | Per Share | $1.10/sh | $1.25/sh | $0.15/sh | 13.6% | Beat | Yes |
| HALVORSEN.FAKE | Per Share | $0.80/sh | $0.80/sh | $0.00/sh | 0.0% | In line | No |
| OSTRAVA.FAKE | Per Share | $0.55/sh | $0.40/sh | -$0.15/sh | -27.3% | Miss | Yes |

## How the file was read
- NORDVIK.FAKE: read Measure as Per Share.
- NORDVIK.FAKE: read Better to Higher.
- HALVORSEN.FAKE: read Measure as Per Share.
- HALVORSEN.FAKE: read Better to Higher.
- OSTRAVA.FAKE: read Measure as Per Share.
- OSTRAVA.FAKE: read Better to Higher.

## Holdings scorecard: Diluted EPS

- Joined 'marcus\_panel.csv' to 'marcus\_holdings.csv' by 'Ticker'; each holding is decided by its Diluted EPS row against consensus
- Not covered by the panel for Diluted EPS: BRAVIK.FAKE (3%)
- Left out of the panel: TROLL.FAKE (not a holding in 'marcus\_holdings.csv')

| Label | Weight | Share of book | Share of covered |
|---|---:|---:|---:|
| Beat | 12.4% | 43.8% | 49.0% |
| In line | 7.9% | 27.9% | 31.2% |
| Miss | 5% | 17.7% | 19.8% |
| Not covered | 3% | 10.6% |  |
````

## In the chat

In the chat, upload the weights file (its Target column is read as each holding's target), confirm, and answer the period, thresholds and basis-point cutoff; then ask **drift from target**.
