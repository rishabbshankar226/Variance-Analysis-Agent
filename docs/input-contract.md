# Reporting currency and input amounts

Each run has one reporting currency: USD (default), EUR, or GBP. The CLI accepts
`--currency EUR` or `--currency GBP`; the Python API accepts `AnalysisConfig(...,
currency="EUR")`. Unmarked amounts inherit that explicitly selected reporting
unit. This declaration does not convert amounts or perform FX arithmetic.

A populated optional `Currency` column must contain the selected code. Blank
cells inherit the run's currency. Budget, Actual, and complete driver-model
numeric fields reject currency symbols conflicting with the run. `$` is accepted
only under the USD convention; a dollar symbol alone does not prove that a source
ledger is USD rather than CAD or another dollar currency. Unsupported currencies
must be normalized explicitly outside this tool and labeled accurately.

Materiality amounts use the selected reporting unit. Keep the existing
`--dollar-threshold` option, but provide an undecorated number such as `1000`;
currency symbols on either CLI threshold are rejected. Percent thresholds remain
percent numbers, for example `5` for 5%. Calculations remain Decimal-based.

## Migration

Earlier releases discarded dollar/euro/pound prefixes and displayed every result
as dollars. EUR/GBP-prefixed input now requires the matching `--currency`; mixed
currencies fail with exit code 2 before outputs change. No silent aggregation or
currency inference is performed. Reports include a Reporting Currency line and
use that symbol throughout totals, materiality, drivers, and recommendations.

```sh
variance-agent examples/sample_eur.csv --period 'Q3 2026' \
  --currency EUR --dollar-threshold 100 --percent-threshold 5 \
  --output report.md --audit-json audit.json
```

## Validation without artifacts

`--check-only` runs the same parser, classification, summary/driver verification,
and deterministic analysis, then prints a bounded row/materiality/quality summary.
It creates no report or audit files and cannot be combined with output flags.
Required period and threshold arguments remain required. Expected errors exit 2;
valid input exits 0. Unclassified rows and unsupported drivers retain their normal
warning/hypothesis behavior rather than becoming invented validation errors.

```sh
variance-agent examples/sample_variance.csv --period 'Q3 2026' \
  --dollar-threshold 100 --percent-threshold 5 --check-only
```

## Excel worksheet selection

Use `--sheet 'Reviewed'` to select that exact name from XLSX/XLSM input. Name matching
is case-sensitive; explicit selection can include a hidden worksheet. Without the
flag, the current active worksheet remains the default. Missing/empty sheets fail
actionably; `--sheet` with CSV/JSON is rejected. Headers/dimensions receive the same
validation on every selected sheet.

Audit 1.4 records the actual selected worksheet name, including the active-sheet
default; CSV/JSON use null. Older explicitly selected audit versions omit this
metadata. Excel values come from cached formula results (`data_only=True`);
formulas are never recalculated. Missing caches remain missing input values.
