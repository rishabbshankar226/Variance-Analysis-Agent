# Variance Analysis Agent

A command-line tool for reviewing budget-versus-actual results. It reads CSV, JSON, or Excel data, checks classifications and totals, and writes a Markdown report of material variances. An optional audit JSON records the calculations and supporting evidence for downstream reporting.

Calculations use Python `Decimal` arithmetic. The CLI makes no model calls and requires no API key.

Requires Python 3.11 or later. Current development version: **0.3.0**. See the [changelog](CHANGELOG.md).

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
variance-agent examples/sample_variance.csv \
  --period "Q3 2026" \
  --dollar-threshold 10000 \
  --percent-threshold 5
```

The report prints to the terminal. To save both outputs:

```bash
variance-agent examples/sample_variance.csv \
  --period "Q3 2026" \
  --dollar-threshold 10000 \
  --percent-threshold 5 \
  --output reports/q3-2026.md \
  --audit-json reports/q3-2026.audit.json
```

### What the sample shows

With the thresholds above, four rows are material, in this order:

| Line item | Variance (USD) | Variance % | Status |
|---|---:|---:|---|
| Subscription Revenue | $15,500 | 15.5% | Favorable |
| Marketing Expense | $13,000 | 65.0% | Unfavorable |
| Payroll Expense | $8,000 | 13.3% | Unfavorable |
| Services Revenue | -$3,000 | -6.0% | Unfavorable |

Services Revenue is flagged by its percentage even though its dollar variance is below $10,000. Rent Expense is unchanged and is not flagged.

Subscription Revenue also supplies volume and price inputs. The model reconciles its $15,500 variance to a $5,000 volume effect and a $10,500 price effect. Rows without reconciled operating metrics are not given a supported driver.

## Financial rules

| Rule | Behavior |
|---|---|
| Variance amount | `Actual - Budget` |
| Variance percentage | `(Actual - Budget) / Budget` for nonzero Budget |
| Zero Budget | Nonzero Actual is unbudgeted with no percentage; zero/zero has zero variance |
| Favorable or unfavorable | Positive revenue variance is favorable; positive expense variance is unfavorable |
| Materiality | Absolute amount **or** percentage strictly exceeds the chosen threshold; equality is not material |
| Sorting | Material rows appear by descending absolute amount |
| Classification | Ambiguous rows stay `Unclassified` and are excluded from category totals |
| Summaries | Reconciled totals are excluded when their detail rows are supplied |
| Drivers | A model is supported only when its inputs reconcile to Budget and Actual |
| Rounding | Display values are rounded; calculations and threshold comparisons retain precision |

Expense inputs use positive-cost amounts. A zero-budget row uses only the amount threshold. See the [financial rules](docs/financial-rules.md) for exact tolerances, formulas, and numeric limits.

## Input fields

| Field | Required | Accepted values or notes |
|---|---|---|
| Line Item | Yes | Aliases: `Line`, `Item`, `Account`, `Account Name`, or `Category` |
| Budget | Yes | Currency symbols, grouped thousands, and accounting parentheses are accepted |
| Actual | Yes | Same numeric rules as Budget |
| Type | Recommended | Revenue/Income/Sales or Expense/Cost; ambiguous types stay Unclassified |
| Row Kind | Optional | `Detail`, `Total`, or `Subtotal` resolves ambiguous summary labels |

Classification uses a JSON map supplied with `--type-map` first, then an explicit Type, then conservative label inference. The report warns about unclassified rows.

Optional driver fields are checked in this order:

1. `Budget Volume`, `Actual Volume`, `Budget Price`, `Actual Price`
2. `Budget Units`, `Actual Units`, `Budget Price`, `Actual Price`
3. `Budget Headcount`, `Actual Headcount`, `Budget Rate`, `Actual Rate`
4. `Budget Customers`, `Actual Customers`, `Budget Rate`, `Actual Rate`

Each run uses one reporting currency: USD by default, or `--currency EUR` or `--currency GBP`. Mixed currencies are rejected; the tool does not convert currencies.

Install Excel support with `python -m pip install -e ".[excel]"`. Excel input reads cached formula values and does not recalculate the workbook. Use `--sheet 'Reviewed'` to select a worksheet.

Use `--check-only` with the period and threshold arguments to validate input without writing files. See the [input contract](docs/input-contract.md) and [validation guide](docs/validation.md) for formats, numeric cleaning, summary rules, and error handling.

## Audit JSON and optional commentary

The versioned audit record includes the source SHA-256, analysis fingerprint, classification coverage, completeness flags, verified totals, material rows, driver evidence, and warnings. Raw source rows are excluded. Integrity hashes detect changes; they do not authenticate the source or its author. See the [audit contract](docs/audit-contract.md).

The project began with the [reporting prompt](prompt/variance_report_prompt.md), which is retained as a reference and an optional interface for LLM commentary. A commentary consumer should describe the verified audit results without redoing arithmetic or inventing causes. The `trust_contract` marks source strings as untrusted data rather than instructions.

## Development

```bash
python -m pip install -e ".[dev,excel]"
pytest
ruff check .
```

See [implementation notes](docs/IMPLEMENTATION_NOTES.md), [contributing](CONTRIBUTING.md), and the [roadmap](docs/roadmap.md).

The project covers descriptive variance analysis and supported driver decomposition. Forecasting, valuation, budget creation, and scenario modeling are outside its current scope.
