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
Numeric cells use the stored XML decimal text directly rather than openpyxl's
binary float conversion. This preserves stored fractional cents but cannot
recover precision discarded by the workbook's producer.

## Period and resource limits

The reporting period must be nonblank text. An optional Period column declares
the row period; if it appears, every row must supply the configured period. Filter
or aggregate multi-period ledgers deliberately before analysis.

Source and type-map captures are each limited to 32 MiB. CSV/JSON allow at most
100,000 data rows, 256 columns, and 1,000,000 cells/JSON values. Text is limited to
128 KiB and numeric literals to 4,096 characters. JSON/XML nesting remains limited to
128 containers. Excel allows 2,048 archive members and 64 MiB total expanded
content; worksheet physical indices are bounded to 100,000 rows including the
header and 256 columns, with 1,000,000 cells per worksheet. Inflated dimension
metadata does not expand these limits. Duplicate archive paths, DTD/entities,
duplicate or unordered coordinates, and invalid physical positions are rejected
before the workbook library expands a worksheet.

## Assisted intake (--assisted)

By default, the CLI enforces strict canonical column headers (`Line Item`, `Budget`, `Actual`),
expects headers on row 1 of the active worksheet, and rejects accounting dashes or blank budgets.
This guarantees 100% byte-identical backwards compatibility with existing automated pipelines.

Passing `--assisted` enables intelligent intake for real-world files:
- **Header detection**: Skips title blocks, blank rows, and metadata lines above the header row, picking the first candidate row containing line-item, budget, and actual columns.
- **Synonym matching**: Maps common ERP and planning column names:
  - Line item: `Account Description`, `Description`, `GL Account Name`, `Account Title`, `Line Item Name`, `GL Description`.
  - Account ID: `GL Account`, `GL Account Number`, `Account Number`, `Acct #` (stored as line metadata).
  - Budget: `Budget YTD`, `YTD Budget`, `Plan YTD`, `Bgt`, `Budget Amt`.
  - Forecast comparison: `Forecast`, `Fcst`, `Outlook`, `Projection`, `Projected`.
  - Prior Period comparison: `Prior Year`, `PY`, `Last Year`, `Prior Period`.
  - Actual: `Actual YTD`, `YTD Actual`, `Act`, `Actual Amt`.
  - Ignored computed columns: `Var $`, `Var %`, `Variance`, `% of Budget` (ignored with visible provenance).
- **Number normalization**: Reads accounting dashes (`"-"`, `"–"`, `"—"`) as zero and treats blank budgets as 0 (unbudgeted).
- **Provenance**: In `--assisted` mode, all inferred adjustments are printed to stderr so report and audit stdout streams remain clean.

```sh
variance-agent exports/raw_erp_dump.xlsx --assisted --period 'Q3 2026' \
  --dollar-threshold 10000 --percent-threshold 5
```

## Comparison basis

Each run compares Actual against exactly one amount: Budget (default), Forecast, or Prior Period. Internally and in audit JSON the comparison amount keeps the `budget` field name.

- **Detection (assisted intake and chat).** Forecast and Prior Period headers are listed above. Amount columns labeled only by period (`FY2025`/`FY2024`, `2025`/`2024`, optionally suffixed "Actual") make the newest period Actual and the next newest the Prior Period comparison. With three or more periods the newest two are compared and intake says so.
- **Stops and asks.** More than one distinct comparison (for example Budget and Forecast both present) or periods that cannot be ordered (for example `FY2025` with `Q3 2024`). Intake never chooses between candidates of different bases.
- **Unchanged.** Wide Budget/Actual period-pair layouts remain Budget.
- **Strict mode.** Without `--assisted` or `--mapping`, nothing is detected. Pass `--compare-to {budget,forecast,prior-period}` to use a forecast or prior-period column; a basis with no matching column is an input error (exit 2) naming the columns found.
- **Chat.** "compare to forecast", "compare to prior year", or "compare to budget" switches the basis and re-reads the file; "what can I compare against?" explains the options.
- **Naming.** The comparison label comes from the comparison column's period (for example `FY2024`) or the basis name. Reports and chat show it as "Prior Period (FY2024)" or "Compared Against: …" and never call a forecast or prior period a budget.

```sh
variance-agent exports/10k_extract.csv --assisted --period 'FY2025' \
  --dollar-threshold 10000 --percent-threshold 5
variance-agent plan.csv --period 'Q3 2026' --compare-to forecast \
  --dollar-threshold 10000 --percent-threshold 5
```
