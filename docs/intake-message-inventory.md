# Intake Message Inventory

This document catalogs every user-facing message Maya can encounter during the data intake and analysis preparation workflow across the Variance Analysis Agent codebase (commit `a3ce6bb`).

Per the definitions in [`.agents/rules/variance-intake.md`](file:///Users/rishabbshankar/Desktop/projects/Automated%20Variance%20Analysis/Variance%20Analysis%20Agent/.agents/rules/variance-intake.md):
- **Jargon**: Any message containing:
  1. A snake_case key or `repr()` quoting (such as `'budget_ytd'`, `!r`, `seen[key]!r`).
  2. An exception name (`ValueError`, `RuntimeError`, `BadZipFile`, `SyntaxError`, `KeyError`, etc.).
  3. CLI flag syntax (`--sheet`, `--currency`, etc.) unless explicitly stated as optional.
  4. Forbidden technical words: `normalize`, `alias`, `schema`, `OOXML`, `archive`, `XML`, `DTD`, `payload`, `Row Kind`, `Unclassified` (preferred: "not yet labeled revenue or expense").
  5. An exit code (`exit code 2`, etc.).
- **Offers a Fix**: States the exact fix and, where possible, provides an interactive chip that applies it.

---

## 1. Executive Summary & Inventory Metrics

| Metric | Count | Percentage |
|---|---|---|
| **Total Messages Audited** | **113** | 100.0% |
| **Messages Containing Jargon** | **32** | 28.3% |
| **Plain-Language Messages** | **81** | 71.7% |
| **Messages Offering an Actionable Fix** | **43** | 38.1% |
| **Messages With No Fix (Dead Ends / Unassisted Errors)** | **70** | 61.9% |

### Breakdown by Component

| Component Source | Total Messages | Jargon Messages | Offers Fix |
|---|---|---|---|
| [`src/variance_agent/parsing.py`](file:///Users/rishabbshankar/Desktop/projects/Automated%20Variance%20Analysis/Variance%20Analysis%20Agent/src/variance_agent/parsing.py) | 42 | 9 (21.4%) | 12 (28.6%) |
| [`src/variance_agent/excel.py`](file:///Users/rishabbshankar/Desktop/projects/Automated%20Variance%20Analysis/Variance%20Analysis%20Agent/src/variance_agent/excel.py) | 16 | 7 (43.8%) | 0 (0.0%) |
| [`src/variance_agent/analysis.py`](file:///Users/rishabbshankar/Desktop/projects/Automated%20Variance%20Analysis/Variance%20Analysis%20Agent/src/variance_agent/analysis.py) | 25 | 10 (40.0%) | 8 (32.0%) |
| [`src/variance_agent/chat/handlers.py`](file:///Users/rishabbshankar/Desktop/projects/Automated%20Variance%20Analysis/Variance%20Analysis%20Agent/src/variance_agent/chat/handlers.py) | 23 | 5 (21.7%) | 22 (95.7%) |
| [`src/variance_agent/chat/server.py`](file:///Users/rishabbshankar/Desktop/projects/Automated%20Variance%20Analysis/Variance%20Analysis%20Agent/src/variance_agent/chat/server.py) | 7 | 1 (14.3%) | 1 (14.3%) |

---

## 2. Complete Message Inventory

### A. Parsing & File Loading (`parsing.py`)

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `parsing.py:45` | `{line_item}: field '{field}' must be a finite number.` | No | Yes | Tells user to supply finite number |
| `parsing.py:47` | `{line_item}: field '{field}' exceeds the supported numeric length.` | No | No | Technical limit without fix guidance |
| `parsing.py:62` | `{line_item}: required field '{field}' is missing.` | No | No | Identifies missing field, no recovery chip |
| `parsing.py:64` | `{line_item}: field '{field}' must be numeric, not boolean.` | No | Yes | States numeric constraint |
| `parsing.py:70` | `{line_item}: field '{field}' must be a numeric scalar.` | No | Yes | Uses technical term "scalar" |
| `parsing.py:72` | `{line_item}: field '{field}' exceeds the supported numeric length.` | No | No | Technical limit |
| `parsing.py:75` | `{line_item}: required field '{field}' is missing.` | No | No | Fails on blanks / dashes |
| `parsing.py:82` | `{line_item}: field '{field}' must be a finite number.` | No | Yes | Prescribes finite number |
| `parsing.py:85` | `{line_item}: field '{field}' has an invalid numeric format: {value!r}.` | **Yes** | No | Uses Python `repr()` formatting (`!r`) |
| `parsing.py:89` | `{line_item}: field '{field}' currency {code} conflicts with reporting currency {currency}; no FX conversion is performed.` | No | No | Financial conflict explanation |
| `parsing.py:96` | `{line_item}: field '{field}' is not numeric: {value!r}.` | **Yes** | No | Uses Python `repr()` formatting (`!r`) |
| `parsing.py:116` | `Columns {seen[key]!r} and {original!r} normalize to the same key {key!r}.` | **Yes** | No | Uses forbidden word `normalize` and `!r` |
| `parsing.py:123` | `Dataset exceeds the supported column count ({MAX_COLUMNS}).` | No | No | Hard ceiling without resolution advice |
| `parsing.py:129` | `Each row must be an object with named columns.` | No | Yes | States requirement |
| `parsing.py:131` | `Row exceeds the supported column count ({MAX_COLUMNS}).` | No | No | Hard ceiling |
| `parsing.py:140` | `Row data appears under a blank column header.` | No | No | Does not point to column coordinate |
| `parsing.py:144` | `Columns {originals[key]!r} and {original!r} normalize to the same key {key!r}.` | **Yes** | No | Uses forbidden word `normalize` and `!r` |
| `parsing.py:160` | `CSV input has no header row.` | No | No | Identifies problem without template offer |
| `parsing.py:167` | `CSV row {line_num}: column count does not match header.` | No | No | Points to row number |
| `parsing.py:169` | `CSV row {line_num}: data appears under a blank header.` | No | No | Rejects data under unlabelled column |
| `parsing.py:172` | `CSV exceeds the supported row or cell count.` | No | No | Hard limit |
| `parsing.py:180` | `Duplicate JSON key: {key!r}.` | **Yes** | No | Uses Python `repr()` formatting (`!r`) |
| `parsing.py:198` | `JSON exceeds the supported value count.` | No | No | Limit check |
| `parsing.py:208` | `JSON nesting exceeds the supported depth.` | No | No | Limit check |
| `parsing.py:213` | `JSON constant {value!r} is not a finite number.` | **Yes** | No | Uses Python `repr()` formatting (`!r`) |
| `parsing.py:223` | `JSON nesting exceeds the supported depth.` | No | No | Limit check |
| `parsing.py:232` | `JSON input contains both 'rows' and 'data'; supply one dataset.` | No | Yes | Instructs to supply one dataset |
| `parsing.py:235` | `JSON input must be a list of row objects or contain a 'rows'/'data' list.` | No | Yes | Prescribes structure |
| `parsing.py:237` | `Every JSON row must be an object.` | No | Yes | Prescribes structure |
| `parsing.py:239` | `Dataset exceeds the supported row count ({MAX_ROWS}).` | No | No | Hard ceiling |
| `parsing.py:248` | `Excel input requires the optional dependency: pip install 'variance-analysis-agent[excel]'` | **Yes** | Yes | Developer shell instruction (`pip install`) |
| `parsing.py:256` | `Unsupported input format '{suffix}'. Use CSV, JSON, XLSX, or XLSM.` | No | Yes | Lists supported extensions |
| `parsing.py:270` | `Input exceeds the supported size (32 MiB).` | No | No | Size limit |
| `parsing.py:292` | `Worksheet selection requires XLSX or XLSM input.` | No | Yes | Clarifies requirement |
| `parsing.py:294` | `Worksheet name must be text.` | No | Yes | Type requirement |
| `parsing.py:309` | `Worksheet {sheet!r} was not found; supply an exact --sheet name.` | **Yes** | Yes | Mentions CLI flag `--sheet` and `!r` |
| `parsing.py:312` | `Excel input has no active worksheet.` | No | No | Structure failure |
| `parsing.py:321` | `Excel input is empty.` | No | No | No recovery guidance |
| `parsing.py:331` | `Excel row {row_number}: data appears under a blank header beyond the header row.` | No | No | Internal physical coordinate failure |
| `parsing.py:335` | `Excel row {row_number}: data appears under a blank header.` | No | No | Triggered by title blocks above header |
| `parsing.py:341` | `Invalid Excel workbook {source_name!r}: {exc}` | **Yes** | No | Leaks Python exception text `{exc}` and `!r` |
| `parsing.py:345` | `Unsupported input format '{suffix}'. Use CSV, JSON, XLSX, or XLSM.` | No | Yes | Prescribes formats |

---

### B. Excel Preflight & XML Validation (`excel.py`)

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `excel.py:70` | `Excel XML exceeds the supported depth ({MAX_XML_DEPTH}).` | **Yes** | No | Contains forbidden word `XML` |
| `excel.py:75` | `Excel physical rows must increase within 1..{MAX_ROWS}.` | No | No | Internal XML physical ordering |
| `excel.py:81` | `Excel worksheet exceeds the supported cell count ({MAX_CELLS}).` | No | No | Limit error |
| `excel.py:90` | `Excel cell contains an invalid physical coordinate.` | No | No | Low-level cell coordinate parser |
| `excel.py:96` | `Excel cell coordinate conflicts with its physical row.` | No | No | Low-level cell coordinate parser |
| `excel.py:99` | `Excel physical coordinates exceed {MAX_ROWS} rows or {MAX_COLUMNS} columns.` | No | No | Physical index boundary |
| `excel.py:102` | `Excel physical cell columns must be strictly increasing.` | No | No | Low-level OOXML structure check |
| `excel.py:104` | `Excel worksheet contains duplicate cell coordinates.` | No | No | Internal workbook corruption check |
| `excel.py:110` | `Excel numeric literal exceeds the supported length.` | No | No | Length check |
| `excel.py:126` | `Excel archive exceeds {MAX_ARCHIVE_MEMBERS} members.` | **Yes** | No | Contains forbidden word `archive` |
| `excel.py:128` | `Excel archive contains duplicate member paths.` | **Yes** | No | Contains forbidden word `archive` |
| `excel.py:130` | `Excel archive exceeds the 64 MiB expanded size limit.` | **Yes** | No | Contains forbidden word `archive` |
| `excel.py:138` | `Excel archive exceeds the 64 MiB expanded size limit.` | **Yes** | No | Contains forbidden word `archive` |
| `excel.py:143` | `Excel XML DTD and entity declarations are forbidden.` | **Yes** | No | Contains forbidden words `XML` and `DTD` |
| `excel.py:147` | `Invalid Excel archive: {exc}` | **Yes** | No | Contains forbidden word `archive` & exception leak |
| `excel.py:154` | `Excel numeric cell is missing its stored decimal representation.` | No | No | Missing cached formula result |

---

### C. Analysis Engine & Row Validation (`analysis.py`)

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `analysis.py:79` | `Row {row_number}: multiple aliases for '{display_name}': {present}. Supply one column per field.` | **Yes** | Yes | Contains forbidden word `aliases` & snake_case keys |
| `analysis.py:84` | `Row {row_number}: required field '{display_name}' was not found. Accepted names: {candidates}.` | **Yes** | Yes | Dumps snake_case keys (`budget_amount`, `planned`) |
| `analysis.py:108` | `{line_item}: Row Kind must be Detail, Total, or Subtotal.` | **Yes** | Yes | Mandates adding forbidden technical column `Row Kind` |
| `analysis.py:112` | `{line_item}: ambiguous summary label; specify Row Kind as Detail, Total, or Subtotal.` | **Yes** | Yes | Mandates `Row Kind` column to resolve totals |
| `analysis.py:125` | `{line_item}: multiple classification aliases: {type_keys}.` | **Yes** | No | Contains forbidden word `aliases` & snake_case keys |
| `analysis.py:269` | `Multiple {line_type.value} summary rows were supplied without detail rows; aggregation would be ambiguous and could double count.` | No | No | Financial rule error |
| `analysis.py:281` | `Multiple {line_type.value} summary rows have ambiguous scope; supply detail rows only or one reconciled total.` | No | Yes | Rejects nested subtotals |
| `analysis.py:286` | `Summary {summary.line_item!r} does not reconcile to {line_type.value} detail rows; check for missing or overlapping data.` | **Yes** | Yes | Uses Python `repr()` formatting (`!r`) |
| `analysis.py:290` | `Summary {summary.line_item!r} does not reconcile to {line_type.value} detail rows; check for missing or overlapping data.` | **Yes** | Yes | Uses Python `repr()` formatting (`!r`) |
| `analysis.py:408` | `Final verification failed: dataset contains no data rows` | No | No | Internal assertion leak |
| `analysis.py:416` | `Configuration must be an AnalysisConfig instance.` | **Yes** | No | Leaks Python class name `AnalysisConfig` |
| `analysis.py:419` | `Rows must be a list of row objects.` | No | No | Developer type error |
| `analysis.py:422` | `Dataset contains no data rows.` | No | No | Empty input failure |
| `analysis.py:424` | `Dataset exceeds the supported row count ({MAX_ROWS}).` | No | No | Limit check |
| `analysis.py:428` | `Materiality thresholds must be Decimal values initialized from strings.` | **Yes** | No | Leaks Python `Decimal` technical requirement |
| `analysis.py:430` | `Materiality thresholds must be finite numbers.` | No | No | Numeric check |
| `analysis.py:432` | `Materiality thresholds must be non-negative.` | No | No | Threshold rule |
| `analysis.py:435` | `Type map must be a dictionary of line-item strings to classifications.` | No | No | Developer dictionary specification |
| `analysis.py:439` | `Type map keys must be nonblank line-item strings.` | No | No | Developer specification |
| `analysis.py:444` | `Type map value for {item!r} must be Revenue, Expense, or Unclassified.` | **Yes** | Yes | Uses `!r` and forbidden word `Unclassified` |
| `analysis.py:468` | `Row {index}: Period conflicts with the reporting period.` | No | No | Rejects multi-period ledgers |
| `analysis.py:471` | `Row {index}: Line Item must be a scalar text or numeric label.` | No | No | Technical term "scalar" |
| `analysis.py:474` | `Row {index}: Line Item is blank.` | No | No | Blank line item rejection |
| `analysis.py:480` | `{line_item}: Currency must be a reporting currency code.` | No | No | ISO code check |
| `analysis.py:483` | `{line_item}: row currency {row_currency} conflicts with reporting currency {config.currency}.` | No | No | Currency conflict |

---

### D. Guided Chat Intake (`chat/handlers.py`)

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `handlers.py:55` | `Please type a message or upload a file.` | No | Yes | General prompt |
| `handlers.py:77` | `Please upload a file using the drop zone above. Supported formats: CSV, JSON, XLSX, XLSM.` | No | Yes | File intake prompt |
| `handlers.py:108` | `⚠️ {display_text(str(exc))}` | **Yes** | Yes | Catches exceptions and surfaces them directly with `Upload a different file` |
| `handlers.py:115` | `⚠️ The uploaded file '{safe_inline(filename)}' contains no data rows. Please upload a file with at least one row of budget and actual data.` | No | Yes | Actionable prompt |
| `handlers.py:137` | `✅ Loaded '{safe_inline(filename)}' ({row_count} data rows)... switch with 'sheet <name>'. What reporting period does this analysis cover?` | No | Yes | Includes period prompt and sheet hint |
| `handlers.py:165` | `The reporting period cannot be blank. Please enter a period (e.g., Q3 2026).` | No | Yes | Clear prompt |
| `handlers.py:173` | `Period set to: **{safe_inline(period)}**... Now set the materiality thresholds...` | No | Yes | Offers 4 threshold presets as chips |
| `handlers.py:364` | `I couldn't parse those thresholds. Please enter them as: '$10,000 or 5%'` | No | Yes | Format example with chips |
| `handlers.py:375` | `Thresholds set: **${dollar}** or **{pct}%**... What is the reporting currency?` | No | Yes | Offers currency chips |
| `handlers.py:407` | `Please choose a supported currency: USD, EUR, or GBP.` | No | Yes | Currency chips |
| `handlers.py:436` | `⚠️ Analysis failed: {display_text(str(exc))}` | **Yes** | Yes | Surfaces internal validation errors with chips |
| `handlers.py:455` | `Analysis complete, but **{remaining}** line items are unclassified. **'{item}'** is Unclassified. Should it be:` | **Yes** | Yes | Uses forbidden word `Unclassified` and `repr` quoting |
| `handlers.py:490` | `Please choose Revenue, Expense, or Skip for '{safe_inline(current_item)}'.` | No | Yes | Resolution chips |
| `handlers.py:499` | `Got it. {remaining} remaining. **'{next_item}'** is Unclassified. Should it be:` | **Yes** | Yes | Uses forbidden word `Unclassified` |
| `handlers.py:518` | `✅ **Analysis Complete**...` | No | Yes | Summary cards and chips |
| `handlers.py:1380` | `Please specify a sheet name: 'sheet <name>'. Available sheets: ...` | No | Yes | Command syntax guidance |
| `handlers.py:1391` | `Worksheet '{sheet}' not found. Available sheets: ...` | No | Yes | Lists available sheets |
| `handlers.py:1404` | `⚠️ Failed to switch to worksheet '{sheet}': {exc}` | **Yes** | No | Surfacing raw exception text `{exc}` |
| `handlers.py:1410` | `Worksheet '{sheet}' is empty.` | No | No | State notice |
| `handlers.py:1422` | `📑 Switched to worksheet **'{sheet}'** ({row_count} data rows)...` | No | Yes | Confirmation notice |
| `handlers.py:1429` | `⚠️ No active workbook to switch sheets in. Please upload an Excel file first.` | No | Yes | Guidance |
| `handlers.py:1438` | `Available worksheets in '{filename}': ... Switch sheets with 'sheet <name>'.` | No | Yes | Lists sheet names |
| `handlers.py:1445` | `No multi-sheet workbook is currently loaded.` | No | No | State notice |

---

### E. Server Endpoints (`chat/server.py`)

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `server.py:71` | `File not found.` | No | No | Generic 404 |
| `server.py:73` | `Not found.` | No | No | Generic 404 |
| `server.py:85` | `Not found.` | No | No | Generic 404 |
| `server.py:91` | `Expected multipart/form-data.` | **Yes** | No | HTTP protocol jargon (`multipart/form-data`) |
| `server.py:131` | `No file found in the upload. Please select a CSV, JSON, XLSX, or XLSM file.` | No | Yes | Upload advice |
| `server.py:147` | `Invalid JSON.` | No | No | Protocol payload error |
| `server.py:152` | `Empty message.` | No | No | Protocol payload error |

---

### F. PDF Filings (`pdf_tables.py`, `intake.py`, `parsing.py`), added with PDF intake

These messages postdate the audited commit and are not in the counts above.

| Source | Message Text | Jargon? | Offers Fix? | Notes |
|---|---|---|---|---|
| `pdf_tables.py` | `PDF files require the optional PDF tools. Please install with: pip install 'variance-analysis-agent[pdf]'` | No | Yes | Install command (CLI and hosted setup) |
| `pdf_tables.py` | `We couldn't open '{filename}' as a PDF. It may be damaged or password-protected. Try saving it again without a password, or export the statement to Excel or CSV.` | No | Yes | |
| `pdf_tables.py` | `'{filename}' has {n} pages, more than the {max} we can read at once. Save just the financial statement pages as a new PDF and upload that.` | No | Yes | |
| `pdf_tables.py` | `Reading '{filename}' took too long. Save just the financial statement pages as a new PDF and upload that.` | No | Yes | |
| `pdf_tables.py` | `'{filename}' looks like a scanned image, so there is no text to read. Export the statement to Excel or CSV, or use a PDF saved from the filing itself, not a scan.` | No | Yes | |
| `pdf_tables.py` | `We couldn't find an income statement, balance sheet or cash flow statement in '{filename}'. Export the statement to Excel or CSV and upload that instead.` | No | Yes | |
| `intake.py` | `No statement called '{sheet}' was found in '{filename}'. Statements found: {names}.` | No | Yes | Lists the statements; chat offers chips |
| `intake.py` | `'{statement}' lists assets, liabilities and equity, which can't be compared as revenue and expense yet. Choose an income statement instead: {names}.` | No | Yes | Also "cash coming in and going out" for cash flows; chat offers chips |
| `parsing.py` | `PDF files are read with --assisted, which finds the financial statements in the filing and lists every adjustment it makes.` | No | Yes | CLI only; the flag is the fix |

## 3. Key Findings & Friction Patterns

1. **The Exception Pass-Through Leak**:
   In `chat/handlers.py`, line 108 wraps any exception raised during file intake as:
   ```python
   text = f"⚠️ {display_text(str(exc))}"
   chips = ["Upload a different file"]
   ```
   Because `parsing.py`, `excel.py`, and `analysis.py` throw exceptions containing low-level developer text (e.g. `!r`, `normalize`, `OOXML`, `archive`, `DTD`, `Row Kind`, `--sheet`), Maya is directly confronted with technical terminology the moment any real-world file deviates from strict requirements.

2. **The Ambiguous Total / Nested Subtotal Blocker**:
   When a user uploads a P&L containing natural subtotal rows (like "Gross Profit" or "Total Operating Expenses"), the agent crashes with:
   `⚠️ Analysis failed: Total Operating Expenses: ambiguous summary label; specify Row Kind as Detail, Total, or Subtotal.`
   This forces Maya to leave the chat, open Excel, create a new column named `Row Kind`, populate it with `Total` or `Detail`, and re-upload.

3. **Strict Column Alias Failures**:
   Headers such as `Budget YTD`, `Actual YTD`, `Jul-26 Budget`, and `Sep-26 Actual` immediately fail with:
   `Row 2: required field 'Budget' was not found. Accepted names: budget, budget_amount, plan, planned.`
   This dumps a list of snake_case internal aliases rather than offering an interactive column mapper.

4. **Missing vs Zero Conflation**:
   Accounting dashes (`"-"` and `"–"`) are classified as missing values rather than zero spend, raising:
   `Travel Expense: required field 'Actual' is missing.`
   Similarly, unbudgeted lines with empty budget cells abort analysis rather than offering a "Treat blank budgets as 0 (unbudgeted)?" chip.

5. **The Unclassified Loop Trap**:
   In `chat/handlers.py`, if Maya starts resolving unclassified lines and then selects "Skip all", `_handle_classify` triggers `_run_analysis` because `session.type_map` is non-empty. `_run_analysis` re-encounters the remaining unclassified lines and sends Maya right back into the unclassified queue, effectively trapping her in an inescapable loop.
