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
- **Stops and asks.** Intake never chooses between candidates of different bases. It stops, lists the candidates, and asks when:
  - more than one distinct named comparison is present (for example `Budget` and `Forecast`);
  - a named comparison sits beside period-only columns (for example `Budget, FY2025, FY2024`, or `Forecast, FY2025 Actual, FY2024 Actual`);
  - a period column also names a comparison (for example `FY2025 Forecast, FY2025 Actual, FY2024 Actual`, or monthly `Jan 2026 Forecast` / `Jan 2026 Actual` columns);
  - an undated `Actual` column sits beside period columns (for example `FY25, FY24, Actual`);
  - periods cannot be ordered (for example `FY2025` with `Q3 2024`).

  The CLI exits 2 and ends the message with "Rerun with --compare-to budget|forecast|prior-period." where `--compare-to` can settle the choice; chat offers one "Compare to …" reply per such basis. `--compare-to budget` or `forecast` picks the named column (with no `Actual` column, the newest period column is Actual); `--compare-to prior-period` reads the period columns.
- **Same basis twice.** Two columns of the same basis (for example `Budget` and `Plan`) are not ambiguous: the first column is used, as before this feature. Naming that basis with `--compare-to` while it appears twice stops with "keep one and rerun".
- **Unchanged.** Wide Budget/Actual period-pair layouts remain Budget, including headers that use a budget synonym as a word (`Jan 2026 Bgt` / `Jan 2026 Actual`).
- **Saved mappings.** A layout mapping saved from chat records `comparison_basis` when a basis was chosen or a non-Budget basis was detected; `--mapping` replays it, and an explicit `--compare-to` wins. Mappings without the field (all earlier files and Budget mappings) load and run as before.
- **Strict mode.** Without `--assisted` or `--mapping`, nothing is detected. Pass `--compare-to {budget,forecast,prior-period}` to use a forecast or prior-period column; a basis with no matching column is an input error (exit 2) naming the columns found. A file with Forecast or Prior Year columns but no Budget column, run without `--compare-to`, fails with the missing-Budget error plus the same "Rerun with --compare-to …" hint.
- **Chat.** "compare to forecast", "compare to prior year", or "compare to budget" switches the basis and re-reads the file; "what can I compare against?" explains the options.
- **Naming.** The comparison label comes from the comparison column's period (for example `FY2024`) or the basis name. Reports and chat show it as "Prior Period (FY2024)" or "Compared Against: …" and never call a forecast or prior period a budget.

```sh
variance-agent exports/10k_extract.csv --assisted --period 'FY2025' \
  --dollar-threshold 10000 --percent-threshold 5
variance-agent plan.csv --period 'Q3 2026' --compare-to forecast \
  --dollar-threshold 10000 --percent-threshold 5
```

## PDF filings (--assisted)

With the optional `[pdf]` extra (`pip install 'variance-analysis-agent[pdf]'`), assisted intake and the chat read the financial statements in a 10-K or 10-Q PDF. Nothing is sent anywhere: the PDF is read on this machine with fixed rules.

- **Finding statements.** Pages whose top lines carry a statement title (income statement, comprehensive income, balance sheet, cash flows, including "Statements of Consolidated …" and "Condensed …" forms) are read for tables. Index pages, MD&A tables, equity statements, footers and page numbers are skipped. A statement continued on the next page is joined.
- **Columns and periods.** Columns are rebuilt from where the amounts sit on the page. Headers become period labels: `Year Ended December 31, 2025` reads as `FY2025`; `Three Months Ended September 30, 2026` and a date such as `September 30, 2026` read as `Sep 2026`. A 10-Q's three- and six/nine-month columns become separate statements. The newest period is Actual and the next newest the Prior Period comparison (see [Comparison basis](#comparison-basis)).
- **Choosing a statement.** Each statement acts like a worksheet: the income statement is chosen first; chat lists the others with `statements` and switches with `statement <name>`; the CLI takes `--sheet "<statement name>"`. When a filing covers a parent and a subsidiary, each name starts with the company.
- **Income statements only.** Balance sheets and cash flow statements are listed but not compared, because their lines are not revenue and expense: "'{statement}' lists assets, liabilities and equity, which can't be compared as revenue and expense yet. Choose an income statement instead: …".
- **Shaping the statement.** Subtotals (Total …, Gross profit, Operating income, Income/Earnings before …, Net income, Comprehensive income) are checked against the lines above them, allowing for each printed figure's rounding, and left out of the analysis. That arithmetic shows whether each line adds to income (labeled revenue) or reduces it (labeled expense). A line printed with the opposite sign, such as interest expense printed (343) in a block the statement adds, is flipped and listed. Lines the arithmetic cannot settle are left for the user to label. Signed-ledger flipping is not applied to these rows.
- **Left out and renamed.** Per-share and share-count rows are left out. A label that repeats is named by its section or by the subtotal it rolls into, for example `Other (current liabilities)`. A unit caption such as `(In millions)` or `(millions, except per share data)` scales amounts exactly.
- **Shown and recorded.** Every adjustment is listed in the "Here's how I read your file" summary (chat) or on stderr (CLI), and recorded in audit schema 1.7 under `source.document`.
- **Limits and errors.** At most 400 pages and 20 seconds per file, beside the 32 MiB file limit. Scanned (image-only), damaged or password-protected PDFs, files without statements, and missing PDF tools each stop with a plain message. Strict mode (no `--assisted`) refuses PDFs and points to `--assisted`.

```sh
variance-agent filings/10-K-2025.pdf --assisted --period 'FY2025' \
  --dollar-threshold 100000 --percent-threshold 5 --audit-json audit.json
```
