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

## Layout mapping files (--mapping)

`--mapping` replays a mapping saved from the chat. It is read as a small JSON file (at most 1 MiB) and checked before use: `header_row_number` a whole number of 1 or more, `column_mapping` an object of column names, `unit_scale` a positive number, `flip_signs` and `treat_blank_budgets_as_zero` true or false, `exclude_totals` a list of names, and `classification_rules` limited to `gl_ranges` (`min`, `max`, `type` Revenue or Expense), `keywords` and `bulk_default`, with types spelled Revenue, Expense or Unclassified in any letter case. A malformed mapping exits 2 with a message that starts "Mapping file", never a traceback. When `--type-map` is also given it is used and the mapping's `classification_rules` are not applied, which is announced on stderr.

## Period labels

Column headers that name periods are ordered newest first when the labels can be trusted. Two-digit years use the usual pivot (`FY69`-`FY99` are 1969-1999, `FY00`-`FY68` are 2000-2068), so `FY99` comes before `FY00`. `FY2025`, `FY 2025`, `Q3 2026`, `Q3-26`, `Sep 2026`, `Sept 2026`, `September 2026` and `2026-09` are recognized.

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
- **Number normalization**: Reads accounting dashes (`"-"`, `"–"`, `"—"`) as zero and treats blank budgets as 0 (unbudgeted). A trailing minus (`500.00-`, as ERP exports write it), the typographic minus U+2212, full-width digits and non-breaking spaces are read as the number they stand for; each trailing or typographic minus is counted in the notes. `5-5`, `5--` and `(5)-` are not guessed.
- **Amounts that cannot be read stop the run.** Text such as `TBD` or `1.234,56`, and a blank Actual, are never read as 0. Intake stops (CLI exit 2) and lists up to ten rows and columns to fix ("...and N more"), so a revenue line can no longer show a false 100% shortfall. Only a blank Budget keeps its confirmation (read as 0, unbudgeted).
- **Text encoding.** CSV/TSV files are read as UTF-8 (a byte-order mark is fine) or UTF-16 with a byte-order mark. A file that is not valid UTF-8 is read as Windows-1252, the usual Excel "CSV" encoding on Windows, with a note to check accents and currency symbols; bytes that fit no encoding stop with advice to save as CSV UTF-8. Replacement characters are never substituted. JSON may start with a byte-order mark.
- **CSV layout.** The delimiter (`,`, `;`, tab or `|`) is detected from the first lines (European Excel uses `;`). Quoted cells may contain line breaks. Blank lines are kept, so row numbers in messages are the file's own. The row, column and cell limits above apply here too.
- **Columns that repeat.** More than one Actual column (`Actual`, `Actual YTD`) or an exact repeat of a Budget/Forecast/Prior Period header stops intake and names the columns with their positions (`Actual (column D)`); it never takes the first silently. Different names for one basis (`Budget` and `Plan`) are still not ambiguous: the first is used. A `Category` column does not beat a column that names the accounts (`Account Description`). Header words are matched whole, so `Contract Value` is not an Actual column.
- **Worksheets.** Hidden worksheets rank after visible ones, so a hidden draft is not chosen automatically; `--sheet` can still name one. A sheet named only like a cover or notes page (`Index`, `Cover Page`, `Notes`) is ranked lower; `Price Index` is not.
- **Subtotal detection** finds block subtotals and formula totals in near-linear time (8,000 rows take well under a second).
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
- **Same basis twice.** Two columns of the same basis under different names (for example `Budget` and `Plan`) are not ambiguous: the first column is used, as before this feature. An exact repeat of one header (two `Budget` columns), or naming that basis with `--compare-to` while it appears twice, stops with "keep one and try again" / "keep one and rerun" and the columns involved.
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
- **Shaping the statement.** Subtotals (Total …, Gross profit, Operating income, Income/Earnings before …, Net income, Comprehensive income) are checked against the lines above them, allowing for each printed figure's rounding, and left out of the analysis. That arithmetic shows whether each line adds to income (labeled revenue) or reduces it (labeled expense). A line printed with the opposite sign, such as interest expense printed (343) in a block the statement adds, is flipped and listed. Lines the arithmetic cannot settle are left for the user to label, including every line of a block of more than 16 lines that has no "Total" row before the next subtotal. Signed-ledger flipping and sum-based subtotal detection are not applied to these rows.
- **Left out and renamed.** Per-share and share-count rows are left out. A label that repeats is named by its section or by the subtotal it rolls into, for example `Other (current liabilities)`. A unit caption such as `(In millions)` or `(millions, except per share data)` scales amounts exactly.
- **Shown and recorded.** Every adjustment is listed in the "Here's how I read your file" summary (chat) or on stderr (CLI), and recorded in audit schema 1.7 under `source.document`.
- **Limits and errors.** At most 400 pages and 20 seconds per file, beside the 32 MiB file limit. Scanned (image-only), damaged or password-protected PDFs, files without statements, and missing PDF tools each stop with a plain message. Strict mode (no `--assisted`) refuses PDFs and points to `--assisted`.

```sh
variance-agent filings/10-K-2025.pdf --assisted --period 'FY2025' \
  --dollar-threshold 100000 --percent-threshold 5 --audit-json audit.json
```

## Explicit measure columns (opt-in)

`Measure` enables unit-aware rows: Currency (default; aliases `currency`, `money`),
Per Share (`per share`, `per-share`, `per_share`, `eps`), Percent (`percent`,
`percentage`, `rate`), or Count (`count`, `units`). `Better` accepts Higher or
Lower. Revenue/Expense classification controls Currency direction; a conflicting
Better is rejected. Better can score an otherwise unclassified Currency profit
metric without making it additive. Per Share defaults visibly to Higher;
Percent and Count require Better. Noncurrency rows never enter currency totals.

Provide `--per-share-threshold`, `--count-threshold`, or `--bps-threshold` for
any corresponding kind present. All cutoffs are nonnegative, exact numbers, with
strict greater-than materiality. No cutoff is inferred. Percent strings such as
`41.2%` mean 41.2 percentage points. Bare Percent numbers require
`--percent-values points` or `--percent-values fractions`; the latter reads
`0.412` as 41.2 points. The chat proposes this choice and asks before analysis.
New typed metric callers supply exact text, integers, or Decimal; floats and
booleans are refused. Legacy undeclared Currency callers keep their contract.

New mapping files can record `measure_options` with text-valued keys
`percent_values`, `per_share_threshold`, `count_threshold`, and `bps_threshold`,
and `better_directions` mapping line-item names to Higher/Lower. Explicit CLI
scale/cutoff flags override the mapping. Old mapping serialization is unchanged.

## Earnings comparison columns (explicit opt-in)

`--compare-to consensus`, `estimate`, or `guidance`, a comma-list comparison set,
or `--preset earnings` / `quant` enables new headers. Without these choices,
Consensus, Model, Region, Division and the new quarter forms stay ordinary
metadata; assisted legacy files still ask on multiple existing comparison bases.
In chat, files with earnings comparisons and no Budget offer a confirmed earnings
review. Budget uploads follow the existing path. An earnings review can choose
one basis or “Compare against all of them.”

Consensus synonyms: Consensus, Cons, Street, Consensus Mean, Mean Estimate.
Estimate synonyms: Our Est., House, Model, Internal Estimate. `Est.` / `Estimate`
alone is ambiguous and needs an explicit column mapping or a renamed header.
The raw `# Est.` header means number of estimates; normalization alone cannot
identify it. High, Low, Std Dev, Std. Dev., Standard Deviation are optional
consensus metadata. Low must not exceed High; dispersion is nonnegative and the
estimator count a nonnegative whole number. GAAP-versus-adjusted matching is the
user's responsibility. Blank consensus is unavailable and never converted to 0.
Supplied zero is a real comparison, with no defined surprise percentage.

Guidance/Guide supplies a point, or Guidance Low/High and Guide Low/High supply
an inclusive range. A point and range together need an explicit mapping.
The range compares against its exact midpoint and records its position.
Outlook continues to mean Forecast. `--compare-to consensus,estimate,prior-period`
selects all three supplied bases in that order; every basis is independently
analyzed. Missing cells in a set leave unavailable comparison groups. Ambiguous
same-name/same-segment/same-measure joins are refused.

Extended period recognition adds 3Q26, Q3 FY26, F3Q26, Q3'26 and 3QFY26. Mixed
fiscal/calendar quarters, mixed granularities, and duplicate period identities
need a user choice. New quarter comparisons name consecutive quarters/years;
existing forms retain their old wording, including Prior Period (FY2024).

New saved mappings may carry an ordered `comparison_bases` list; an explicit
`--compare-to` wins. A column mapping can select one of competing comparison
columns (for example `estimate: Model`) or choose a guidance point instead of a
range. Ignored competing columns are named in intake notes. Raw header identity
is retained before mapping, so `consensus: Est.` and `estimator_count: # Est.`
can be resolved separately. Existing single-basis mapping bytes stay unchanged.
