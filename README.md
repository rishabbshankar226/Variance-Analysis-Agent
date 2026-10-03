# Variance Analysis Agent

Each run uses one reporting currency: USD by default, or explicit `--currency EUR`
or `--currency GBP`. Conflicting row codes/symbols are rejected; no FX conversion
is performed. See [the input contract](docs/input-contract.md) and
[the versioned audit contract](docs/audit-contract.md), including the legacy USD
audit-format option.

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
| Row Kind | Optional | `Detail`, `Total`, or `Subtotal`; use it when a label could be mistaken for a summary |

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

## Input validation and troubleshooting

- Use one accepted column name per field; do not supply both `Budget` and `Plan`.
- Quote comma-containing CSV values, for example `"1,000"`. Every record must match
  the header's column count. Data under unnamed columns is rejected.
- JSON decimals are loaded directly as `Decimal`; duplicate JSON keys are rejected.
- Blank Excel rows are ignored; populated cells under blank headers are rejected.
- Excel rows are read from worksheet contents rather than trusting declared dimensions.
  Malformed workbook structures produce an actionable Excel input error.
- Blank types allow label inference. Nonblank, unrecognized types stay Unclassified.
  Net income, operating income, and gross profit labels are not inferred as revenue.
- For each category, supply detail rows alone, one summary alone, or detail rows
  plus one total that reconciles within $0.01. Multiple nested subtotals have no
  hierarchy metadata and are rejected; remove them before analysis.
- Common category labels such as `Total Revenue` and `Grand Total Expenses` are
  recognized as summaries. Other labels containing `total` or `subtotal` require
  `Row Kind` to resolve their meaning. For example, mark `Total Quality Management`
  as `Detail` when it represents a separate expense account. A custom rollup can
  use `Row Kind=Total`; the existing reconciliation rules still apply.
- Report and audit destinations must differ from each other, the input, and the
  type map. This also applies to symlinks and hardlinks.
- Expected input/file errors exit with code 2 and an explanation. Fix the named
  input or path before retrying.

The audit fingerprint includes every analyzed row, even nonmaterial rows, while
raw input dictionaries remain excluded from the audit output. Fingerprints from
versions before this change use a different recipe and will not match.

### Verification and output safety

Numeric inputs accept decimal/scientific notation, correctly grouped thousands,
leading currency symbols, and accounting parentheses. Ambiguous forms such as
`1,00`, `12$34`, and `(-100)` are rejected instead of silently reinterpreted.
Accounting parentheses already mean negative; do not put another sign inside.
Duplicate type-map keys and multiple classification columns are rejected. JSON
wrappers must supply either `rows` or `data`, not both.

Before output, the agent verifies row percentages and F/U statuses, aggregate
metrics, and the exact membership and order of the material-variance list.
Both output files are serialized and staged before replacement. A staging failure
preserves existing files; each replacement is atomic. Replacing two files is not
a single transaction: if the second replacement fails, rerun the command to
regenerate the pair. Temporary files are cleaned up on handled failures.

### Numerical precision and driver selection

Analysis, report rendering, audit creation, and CLI threshold conversion use an
isolated Decimal context: 50 significant digits, round-half-even, exponent limits
-999 to 999. Caller Decimal settings cannot change the results. Financial
arithmetic that loses information or exceeds the supported range raises an error
instead of silently rounding amounts. Recurring percentage ratios may round to
50 digits, but materiality compares `abs(variance)` directly with
`percent_threshold * abs(budget)` at sufficient product precision. This avoids
false negatives near a repeating-ratio boundary. Zero-budget rules are unchanged.
This policy supersedes the historical precision limitations in earlier audit notes.
Extreme exponents on zero values are canonicalized to signed zero so audit
serialization cannot allocate an arbitrarily large fixed-point string.

The exported Python API validates type-map values as `Revenue`, `Expense`, or
`Unclassified`, and copies the mapping before analysis. Invalid values fail
before the tool can claim complete classification.

Driver models are checked in their documented order until one reconciles.
Optional driver values marked blank, N/A, NA, null, or a dash are unavailable;
they do not block a later usable model. If all complete models fail reconciliation,
the first model remains hypothesis evidence. Malformed numeric driver values
still fail validation. Boolean or structured line-item labels are rejected.
