# Variance Analysis Agent

A deterministic FP&A variance-analysis engine built around an audited prompt specification. It calculates and validates all financial outputs in Python, applies explicit favorable/unfavorable accounting logic, prevents silent imputation, separates supported drivers from hypotheses, and generates an executive-ready Markdown report.

## What it enforces

- `Variance $ = Actual - Budget`
- `Variance % = (Actual - Budget) / Budget` when Budget is nonzero
- Explicit zero-budget handling, including unbudgeted rows
- Expense F/U logic: positive = Unfavorable, negative = Favorable
- Revenue/Income F/U logic: positive = Favorable, negative = Unfavorable
- Strict materiality: `ABS(Variance $) > threshold OR ABS(Variance %) > threshold`
- Material rows sorted by absolute dollar variance descending
- Conservative classification: ambiguous rows remain `Unclassified`
- Subtotal/total detection to reduce double-counting risk
- Supported-driver labels only when supplied operating metrics reconcile to Budget/Actual
- Final deterministic checks before report generation
- Rounding only at display time

## Quick start

```bash
python -m pip install -e .
variance-agent examples/sample_variance.csv \
  --period "Q3 2026" \
  --dollar-threshold 10000 \
  --percent-threshold 5
```

Write the report to a file:

```bash
variance-agent examples/sample_variance.csv \
  --period "Q3 2026" \
  --dollar-threshold 10000 \
  --percent-threshold 5 \
  --output reports/q3-2026.md
```

For Excel files:

```bash
python -m pip install -e ".[excel]"
```

## Input fields

Minimum usable fields:

| Field | Required | Notes |
|---|---|---|
| Line Item | Yes | `Line Item`, `Line`, `Item`, `Account`, `Account Name`, or `Category` |
| Budget | Yes | Currency symbols, commas, and accounting parentheses are accepted |
| Actual | Yes | Same cleaning rules as Budget |
| Type | Recommended | Revenue/Income/Sales or Expense/Cost. Ambiguous rows remain Unclassified |

Optional reconciled driver models:

- `Budget Volume`, `Actual Volume`, `Budget Price`, `Actual Price`
- `Budget Units`, `Actual Units`, `Budget Price`, `Actual Price`
- `Budget Headcount`, `Actual Headcount`, `Budget Rate`, `Actual Rate`
- `Budget Customers`, `Actual Customers`, `Budget Rate`, `Actual Rate`

A driver decomposition is labeled **Supported driver** only if the supplied driver model reconciles to the row's Budget and Actual values. Otherwise the report does not assert a cause.

## Data classification

The engine prefers, in order:

1. An explicit JSON type map
2. An explicit Type/classification column
3. A conservative, unambiguous line-item label
4. `Unclassified`

No ambiguous row is silently forced into Revenue or Expense totals.

## Tests

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

## Prompt reference

The audited prompt that defines the behavioral contract is stored in [`prompt/FP&A_Optimized_Prompt_v4.md`](prompt/FP&A_Optimized_Prompt_v4.md). The executable engine intentionally implements the numerical and evidence controls in code so correctness does not depend on an LLM following prose instructions.

## Scope

This project performs descriptive variance analysis and supported driver decomposition. It does not automatically expand into forecasting, valuation, budgeting, or scenario modeling.
