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
formulas are never recalculated. A formula with no saved result (one Excel never
calculated) is never read as blank or 0: intake stops, names each cell the read uses
(`Row 4, Other income, Budget column (cell B4)`), and asks for the file to be opened,
calculated and saved in Excel. A workbook that asks Excel to recalculate on open
(`fullCalcOnLoad`, which XlsxWriter sets while saving 0 as every result) gets the same
stop for every formula it reads, since its saved results may be stale. Formulas in
ignored computed columns such as `Var $` do not stop intake.
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
- **Unit captions and number formats.** A caption such as `($ in thousands)` describes what Excel shows. When an amount's number format already shows it scaled (`#,##0,` shows 110000 as 110; each trailing comma is a factor of 1,000), the cell stores the full amount, so it is read as stored and not scaled again, with a note. A caption over unscaled formats scales exactly as before. Without a caption, stored amounts are read and the scaled display is noted. When caption and formats disagree (thousands over `#,##0,,`, mixed formats, a percent format on a money row, or a conditional or scientific format), intake stops and lists up to ten cells with their formats. A mapping's `unit_scale` is checked against the formats the same way.
- **Amounts that cannot be read stop the run.** Text such as `TBD` or `1.234,56`, and a blank Actual, are never read as 0. Intake stops (CLI exit 2) and lists up to ten rows and columns to fix ("...and N more"), so a revenue line can no longer show a false 100% shortfall. Only a blank Budget keeps its confirmation (read as 0, unbudgeted).
- **Text encoding.** CSV/TSV files are read as UTF-8 (a byte-order mark is fine) or UTF-16 with a byte-order mark. A file that is not valid UTF-8 is read as Windows-1252, the usual Excel "CSV" encoding on Windows, with a note to check accents and currency symbols; bytes that fit no encoding stop with advice to save as CSV UTF-8. Replacement characters are never substituted. JSON may start with a byte-order mark.
- **CSV layout.** The delimiter (`,`, `;`, tab or `|`) is detected from the first lines (European Excel uses `;`). Quoted cells may contain line breaks. Blank lines are kept, so row numbers in messages are the file's own. The row, column and cell limits above apply here too.
- **Period bands and side-by-side tables.** When a header repeats Budget and Actual under period headings in the row above (`Q3 2026` merged over one pair, `Q2 2026` over the next, or written once and left blank to the right), the headings are joined onto the columns below them and read as a period choice. `--period` names a heading, and otherwise the newest is read. When a sheet holds two tables side by side, separated by a column that is blank from the header down, the first table that reads is used, and the summary names the other (`--sheet "<sheet> (columns E-G)"` reads it instead). Both are tried only where the plain read stops on a repeated column, so a sheet that reads today reads the same.
- **Columns that repeat.** More than one Actual column (`Actual`, `Actual YTD`) or an exact repeat of a Budget/Forecast/Prior Period header stops intake and names the columns with their positions (`Actual (column D)`); it never takes the first silently. Different names for one basis (`Budget` and `Plan`) are still not ambiguous: the first is used. A `Category` column does not beat a column that names the accounts (`Account Description`). Header words are matched whole, so `Contract Value` is not an Actual column.
- **EDGAR statement sheets.** A sheet laid out like a statement in EDGAR's `Financial_Report.xlsx` (one cell holding the title and its unit caption, such as `CONSOLIDATED STATEMENTS OF OPERATIONS - USD ($) $ in Millions`, a duration band such as `12 Months Ended` over the period dates, then the lines) is read the way the PDF reader reads a statement. Its periods are labeled (`Sep. 27, 2025` reads as Sep 2025), per-share and share-count lines are left out, subtotals are checked and left out, each line is labeled revenue or expense from the arithmetic, and the caption scales money. Only a sheet that has no Line Item/Budget/Actual header is read this way, so sheets that read today read the same. A sheet with several durations reads the first and names the others (`--sheet "<sheet> (9 Months Ended)"`). Balance sheets and cash flow statements are listed, not compared, as in PDFs.
- **Files named .xls.** A file named `.xls` is read by its contents, on strict and assisted runs alike. An `.xlsx` workbook renamed `.xls` is read as one, with a note. An Excel 97-2003 (BIFF) workbook, a web page saved as `.xls`, or other text stops with the Save As (.xlsx) fix.
- **Rows hidden in Excel.** A row below the header that Excel hides (one by one, at zero height, or collapsed in an outline group) and that holds anything is never counted silently. Intake stops, lists up to ten such rows with how each is hidden, and asks whether to count them: `--hidden-rows include` or `--hidden-rows exclude` on the CLI, "Count the hidden rows" or "Leave the hidden rows out" in chat, `hidden_rows` in a saved mapping, or `AudienceOptions(hidden_rows=...)` in the file API, which never prompts. The read summary then says which rows were counted or left out. Hidden rows above the header ask nothing. A hidden column that intake reads is named in the summary. Strict mode (no `--assisted` or `--mapping`) reads every row as given and refuses `--hidden-rows`.
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

## Inline XBRL filings (.htm, --assisted)

A 10-K or 10-Q's primary document on EDGAR is HTML with Inline XBRL tags. Assisted intake and the chat read its face statements from the tagged figures, on this machine with fixed rules (the standard library's HTML parser; no network, no model). Strict mode points HTML at `--assisted`.

- **Figures.** Each `ix:nonFraction` fact is read with its context, unit, `scale`, `sign`, `decimals` and `format` (`num-dot-decimal`, `num-comma-decimal`, `fixed-zero`, `zerodash`, number words). Facts kept in `ix:hidden` count only where a cell prints them through `-sec-ix-hidden`. A fact is kept twice: as the XBRL instance holds it (`sign="-"` applied), and as printed (negative when the cell shows it in parentheses or after a minus). Amounts are at full scale from `scale`, so the statement's "(in millions)" caption is never applied again.
- **Statements.** A table titled as an income statement, balance sheet or cash flow statement that prints at least three tagged amounts is a statement. The first copy of each kind is read, so a note repeating the title is not, and an untitled table straight after it continues it. Columns are the facts' own periods, newest first; a 10-Q's three- and nine-month columns become separate statements, named like PDF statements. Per-share and share-count lines are left out (or kept with `--per-share-lines`). A line printed only with one-axis figures (revenue by product, cost by segment) is read as a printed line, keyed by its axis and member, and its total must foot over it; it is not written to the Segment column. Figures on two or more axes are left out and listed.
- **Footing.** Every subtotal must add up from the lines above it within the facts' own rounding (XBRL Calculations 1.1: each figure stands for its `decimals` interval). A subtotal that does not, or one no lines above add up to, refuses the statement plainly instead of presenting it.
- **Revenue and the bottom line.** Where the statement prints its revenue (a revenue concept, or a total that sums such lines), only that block is revenue. Other lines that add to income, such as other income, equity earnings or gains printed as credits inside costs, are read as credits among costs with their sign turned and a note, so net income and the net variance are unchanged. An income statement ends at its first net-income line, found by its concept (`NetIncomeLoss`, `ProfitLoss`) or its printed label; it keeps its printed name even where the label is printed twice, and it must add up like any subtotal. The lines below it, which attribute net income to noncontrolling interests or preferred holders, are listed as left out. The report lists each credit among costs, and why, under "How the filing was read"; a line both compared columns print as zero is never called one. A line the statement's arithmetic can't place stays unclassified, shown as printed with no F or U; its label never types it. A line whose effect changes sign between columns (a tax expense one year, a benefit the next) takes the type the arithmetic gives it, added or subtracted, so every figure stays as printed. The report states every sign it turns under "How the filing was read" (Decision 42). Every line kept is a Detail row, so a lone revenue line printed as "Total revenue, net" reads as that line.
- **The headline.** A filing's income report is headed by the filing's own printed totals: its revenue (the printed revenue total, or a lone revenue line; several revenue lines with no total are named, not summed), and whichever of total expenses (`CostsAndExpenses`, `OperatingExpenses`, `BenefitsLossesAndExpenses`, `NoninterestExpense`), operating income (`OperatingIncomeLoss`) and net income it prints. Each is its XBRL fact for the two columns compared, with the change and the percent of the comparison's absolute value; a total printed negative in both columns adds "larger negative" or "smaller negative", as statement lines do. A total without a tagged figure in a compared column is named and left out. The report shows no Total Revenue, Total Expenses or net operating variance added up from the lines, the chat answers questions about such totals with the headline, audit 1.9 records `totals` as null, and `--xlsx` refuses. An investment company's statement of operations, whose net investment income subtracts a subtotal, refuses plainly for now. PDF and `Financial_Report.xlsx` income reads, which carry no facts, keep the summary of totals added up from their lines.
- **Units.** Every report of an Inline XBRL statement states the unit the filing prints its figures in, from the facts' `scale` ("The filing prints these figures in thousands; this report shows them in full, and amounts inside line labels are quoted as the filing prints them"). Label text is never rewritten, so an amount inside a label (an allowance, an amortized cost) stays in the filing's unit. An LTM report states both filings' units. Audit 1.9 records the sentence as the headline's `unit` and among the reader notes (Decision 40).
- **Labels and periods.** A figure printed inside a label is quoted once, however many hidden-fact spans wrap it. A line printed after its section's own subtotal (a "Total …" line, a section-total concept, or a cash flow section's "Net cash … activities") is not named by that section; where a repeated label has one occurrence outside every open section, that one keeps its printed label. Slash forms such as "Income / (loss) before income taxes" are subtotal labels. A "$" printed in its own cell before a figure is never part of the label, blank spacer cells between them included. Where consecutive 52/53-week fiscal years would read as a skipped or repeated year (a year ending early in January), every year column of that table is named by its end month ("Jan 2026 against Dec 2024"). A refusal on a filing suggests a CSV or Excel copy of the statement before the filing's PDF, which EDGAR rarely carries for recent filings.
- **Recorded.** Audit 1.9 records `source.document` as `{kind: "ixbrl", statement, reader_notes, lines, headline}` (`headline` on income statements), where each line carries its concept, whether it is a subtotal or left out, and each column its context, period, dimensions, stored and printed values and `decimals`. A web page with no Inline XBRL figures stops with what to upload instead.
- **Balance sheets and cash flow statements.** Every printed line, subtotals included, is read at its printed value and compared as an Increase, Decrease or No change of that figure. A figure printed in parentheses is negative, so a larger outflow is a Decrease; where both figures are negative, the outcome adds "larger negative" or "smaller negative". Lines are never revenue or expense, and they carry F or U only where a mapping's `better_directions` declares a direction. First, every subtotal must add up from a run of lines above it within the facts' rounding, every line must sit inside a subtotal that does, and the identity must hold in every column: total assets against total liabilities and equity (temporary equity and noncontrolling interests included; no total liabilities line needed), or ending cash against beginning cash plus the flows printed between. Anything else refuses plainly. A blank cell inside a footed subtotal reads as 0 with a note. Lines after the closing total (supplemental disclosures) are listed as left out. The report shows the checks in place of revenue and expense totals, the audit records `totals` as null, and `--xlsx` refuses for these comparisons. PDF and `Financial_Report.xlsx` balance sheets and cash flow statements still refuse.

## Limits, benchmarks, targets and derived metrics (--assisted, opt-in)

`--compare-to limit|benchmark|target` reads a `Limit`, `Benchmark` or `Target` column (with synonyms such as `Covenant`, `Index`, `Target Weight`) as the comparison, and each row's declarations beside it: `Limit Kind` (Max or Min) and optional `Buffer`; `Better` and optional `Tolerance`; optional `Tolerance`. The headers count only when `--compare-to` names the basis. Without it, a file holding one refuses, and the message names the flag; such a file is never one half of a two-file pair. Strict mode, `--mapping` and `--xlsx` refuse these bases. `Measure: Multiple` reads `3.25x` with `--multiple-threshold`. `--metrics PATH --compare-file FILE` reads declared metrics from an Inline XBRL filing (with `--ltm-from` for LTM terms) and joins them by exact name with a case or covenant schedule. See docs/financial-rules.md for every label and boundary.

## Budget and actuals in two files (--assisted --compare-file)

`variance-agent actuals.csv --assisted --compare-file budget.csv` joins a file of actuals with a file holding the comparison column (budget, forecast or prior period). Each file is read on its own by the reader its format takes, so captions, hidden rows, display scaling, formulas and blanks are checked as usual, and each file's unit caption scales only its own figures. The rows join on an account-ID column both files carry, or else on the exact line-item label; never on a similar label. A key repeated within a file, or found in one file only, refuses the join, naming the lines, because leaving them out would change the totals. The actuals file's labels and types are kept, and labels that differ are listed. In the chat, a file with only a comparison column, or only actuals, asks for the other file, and the next upload is joined. Audit 1.9 records `source.document` as `{kind: "join", key, documents, reader_notes, lines}`, with both files' names and sha256 and each line's label in each file.

## LTM from a 10-K and a 10-Q (--assisted --ltm-from)

`variance-agent <10-Q .htm> --assisted --ltm-from <10-K .htm> --period <label>` reads the 10-Q's year-to-date income statement as LTM: the 10-K's fiscal year plus the year to date less the prior year to date, line by line by XBRL concept and dimensions, compared with that fiscal year. Each filing is read as it would be on its own. Continuity is checked from the periods' dates: the prior year to date must start where the 10-K's year starts, and the year to date the day after it ends. A line in one filing only, or typed revenue in one and expense in the other, refuses the build. Per-share amounts and share counts are left out as not computable as LTM. Cash flow statements refuse, because their balances don't add across periods; a balance sheet is read as of its latest period. The report is headed by LTM of each printed total in both filings' headlines (matched by concept, built the same way and cited), appends an "LTM build" section citing every component, and audit 1.9 records `source.document` as `{kind: "ltm", statement, documents, reader_notes, lines, headline}`, with each line's three components (document, column, context, printed value, weight, value used).

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

### Flat segments (opt-in)

With extended header recognition, Segment, Division, Region, Geography or Business Unit identifies one flat dimension. Choose competing columns with a mapping. Blank labels form an unsegmented bucket. Nested objects, parent columns and second levels are refused. Legacy uploads keep treating these names as metadata.

### Panel captures

Panel grouping applies only after whole-input row, column, cell, text and nesting
validation. Group keys must be distinct named text columns with nonblank scalar
text values. Missing keys are global errors. Amounts and unresolved analytical
choices fail their own groups without prompts. Period keys supply group periods;
a simultaneous configured period is refused. See `docs/api.md` for the wire
contract and deterministic ordering.

### Supplied surprise history

`--history` accepts bounded CSV/JSON with Entity (or Ticker), Metric (or Line
Item), Period and Surprise. Optional Segment and Measure can disambiguate flat
metrics and assert units. Surprise is an exact amount difference, or bps for a
Percent metric. It is never a percentage surprise ratio. Histories are keyed by
entity, metric and segment; duplicate period identities, mixed granularities,
and fiscal/calendar quarter mixtures are refused. File order is irrelevant.
Current and future periods do not enter the window. Ticker/Entity in actual rows
supplies identity; otherwise use `--entity`. Larger captures must be split under
the same existing input limits. A supplied `Std Dev` column enables dispersion
statistics; explicit history also reports why dispersion is absent.

### Opted-in EPS and share counts from filings

Under assisted PDF intake, `--per-share-lines` retains recognizable basic/diluted
EPS as Per Share with Better Higher, and weighted average share counts as Count.
The earnings preset enables this policy; `--no-per-share-lines` overrides it.
Default FP&A intake and its exact omission note remain unchanged. Other omitted
share-related disclosures are not guessed into these measures.

EPS is never multiplied by a currency-caption scale. Share counts remain as
printed, with a visible note; a dollars-in-millions caption scales only Currency.
Verify a vendor's share-count units and normalize a different printed count scale
before analysis. Count Better and all occurring measure thresholds remain the
user's choices. Statement sign/subtotal reconciliation considers Currency only.
PDF statement, pages, period label and reader transformations remain in audit
1.8. The tool does not match EPS from a filing with a separate consensus file;
users must align metric definitions and combine supplied amounts explicitly.

In chat, request “review earnings” before a filing upload, or after uploading it,
to opt into these retained lines. Confirm the review, reporting period and
thresholds, then choose Higher or Lower for each count measure. Ordinary filing
uploads remain on the existing FP&A path. Hosted path exports remain disabled.
