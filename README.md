# Variance Analysis Agent

A command-line tool that compares budget to actual, flags material variances and writes a Markdown variance report. It started as an LLM prompt for FP&A variance analysis. This version does every calculation in Python, so the numbers don't depend on a model following instructions.

## What it checks

- `Variance $ = Actual - Budget`
- `Variance % = (Actual - Budget) / Budget` when Budget is nonzero
- Zero budgets are handled explicitly, including unbudgeted rows
- Expenses: a positive variance is Unfavorable and a negative one Favorable
- Revenue and income: a positive variance is Favorable and a negative one Unfavorable
- A row is material when `ABS(Variance $) > threshold OR ABS(Variance %) > threshold`
- Material rows are sorted by absolute dollar variance, largest first
- A row whose type is unclear stays `Unclassified`
- Subtotal and total rows are detected so nothing is counted twice
- A driver is labeled a supported driver only when the operating metrics supplied reconcile to Budget and Actual
- A final set of checks runs before the report is written
- Numbers are rounded only for display

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

Optional driver models:

- `Budget Volume`, `Actual Volume`, `Budget Price`, `Actual Price`
- `Budget Units`, `Actual Units`, `Budget Price`, `Actual Price`
- `Budget Headcount`, `Actual Headcount`, `Budget Rate`, `Actual Rate`
- `Budget Customers`, `Actual Customers`, `Budget Rate`, `Actual Rate`

A driver decomposition is labeled **Supported driver** only if the driver model reconciles to the row's Budget and Actual values. Otherwise the report doesn't assert a cause.

## Classifying rows

Each row's type comes from the first of these that applies:

1. A JSON type map passed with `--type-map`
2. A Type or classification column
3. A line-item label that is unambiguous
4. Otherwise, `Unclassified`

Unclassified rows are left out of the Revenue and Expense totals, and the report lists them in a warning.

## Tests

```bash
python -m pip install -e ".[dev]"
pytest
ruff check .
```

## The prompt

The prompt this tool grew out of is in [`prompt/variance_report_prompt.md`](prompt/variance_report_prompt.md). Its rules are implemented in code, so the arithmetic doesn't rely on a model following written instructions.

## Audit JSON

Use `--audit-json` to write a machine-readable record next to the Markdown report:

```bash
variance-agent examples/sample_variance.csv \
  --period "Q3 2026" \
  --dollar-threshold 10000 \
  --percent-threshold 5 \
  --output reports/q3-2026.md \
  --audit-json reports/q3-2026.audit.json
```

The audit JSON is meant to be the input for an LLM, if one is added later to write the commentary. It holds the source file's SHA-256, a fingerprint of the analysis, classification coverage, completeness flags, the verified totals, the material variances, whether each driver is supported or a hypothesis, and any warnings. Its `trust_contract` block marks text taken from the source file as data for a model to read and never follow. Raw rows are left out.

That way a model can describe the verified results without redoing the math.

## Scope

The tool explains variances and breaks down the drivers the data supports. It doesn't forecast, value, budget or model scenarios.
