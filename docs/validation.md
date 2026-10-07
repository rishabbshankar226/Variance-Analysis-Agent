# Validation and troubleshooting


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
  plus one total that reconciles within 0.01 in the reporting currency. Multiple nested subtotals have no
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

## Verification and output safety

Numeric inputs accept decimal/scientific notation, correctly grouped thousands,
leading currency symbols, and accounting parentheses. Ambiguous forms such as
`1,00`, `12$34`, and `(-100)` are rejected instead of silently reinterpreted.
Accounting parentheses already mean negative; do not put another sign inside.
Duplicate type-map keys and multiple classification columns are rejected. JSON
wrappers must supply either `rows` or `data`, not both.

Before output, the CLI verifies row percentages and F/U statuses, aggregate
metrics, and the exact membership and order of the material-variance list.
Both output files are serialized and staged before replacement. A staging failure
preserves existing files; each replacement is atomic. Replacing two files is not
a single transaction: if the second replacement fails, rerun the command to
regenerate the pair. Temporary files are cleaned up on handled failures.

## Numerical precision and driver selection

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

See the [input contract](input-contract.md) for currency, worksheet selection, and `--check-only`; see the [financial rules](financial-rules.md) for reconciliation tolerances and driver formulas.
