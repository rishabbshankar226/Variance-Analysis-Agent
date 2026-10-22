# Changelog

## 0.3.0 — Unreleased

### Bug hunt (2026-10-21) — behavior changes first

Details, evidence and remaining boundaries: [docs/BUG_HUNT_2026-10-21.md](docs/BUG_HUNT_2026-10-21.md).

- **Behavior change (assisted intake, chat, `--mapping`).** An amount that cannot be read (`TBD`,
  `1.234,56`) or a blank Actual now stops the run (CLI exit 2, chat "I could not read every amount…")
  with up to ten rows and columns to fix. It was read as 0, which showed a revenue line as a 100%
  shortfall. A trailing minus (`500.00-`), U+2212 and full-width digits are read as the number
  they stand for and reported in the intake notes. Blank Budgets still ask to be read as 0.
- **Behavior change (classification).** Label inference no longer files `Sales Commissions`, `Income Taxes`,
  `Salaries & Wages`, `Provision for Income Taxes` or `Sales Returns and Allowances` under Revenue: cost
  nouns (tax, commission, salary/wages, compensation, provision, returns, bonus, discount, allowance,
  rebate, refund) make a line an Expense, and profit subtotals (`Income Before Taxes`, `Pre-Tax Income`,
  `Income from Operations`, `Comprehensive Income`, EBIT/EBITDA) stay Unclassified. Reports and audit
  fingerprints change for files with such labels. A Type column or type map still wins.
- **Behavior change (chat).** A new successful upload resets period, thresholds, currency, type choices and
  layout mapping; a failed upload changes nothing (it used to leave the bad file's name and hash as the
  audit source). "Keep blank budgets" is removed (it read blanks as 0 anyway). The unused
  `Phase.AWAITING_SHEET_CHOICE` and `Phase.AWAITING_HEADER_CHOICE` are removed. Chat messages over 500
  characters get a friendly reply; pasted tables are unaffected.
- **Behavior change (server).** The chat server refuses cross-origin and DNS-rebound requests (a POST's
  `Origin` must equal `Host`; local mode answers only loopback hosts), requires `application/json` for
  `/message`, no longer sends `Access-Control-Allow-Origin: *`, and sends a strict Content-Security-Policy.
  The page is served from the package (root `static/` is gone) as `chat.html`, `chat.js` and `chat.css`.
- **Behavior change (CLI).** `--chat` binds all interfaces only with `--hosted` or `RENDER` set, no longer
  for a stray `PORT`. Data errors print one line instead of the usage banner. `--type-map` accepts the Type
  column's words (opex, cogs, rev) and `Unclassified`. Mapping files are validated (exit 2, "Mapping file …").
  Output paths that differ only by case are refused. `--assisted` stops when two Actual columns
  (`Actual`, `Actual YTD`) or two identical Budget headers are present instead of taking the first.
- **Behavior change (audit).** `transformations` now records what intake applied on `--mapping` runs too
  (header row found, unit scale applied, items flipped, exclusions), and `zero_reads.accounting_dashes`
  is the real count (it was always 0). Mapping-only fields (period selection, rules, digest) are unchanged.
- **Behavior change (commentary).** The executive commentary no longer says "Balanced performance… no
  unresolved variances" when net is behind budget, or "Operating profit turned negative" when a budgeted
  loss widened; the executive TL;DR no longer calls a zero variance a beat, saving or outperformance.
- Fix: one chat message of whitespace or digits froze the single-threaded server (`what if` plus 200 spaces took
  3.6 s, and the time grew with about the fourth power of the length), which also failed Render's health check;
  `top`/`why` plus 4,301 digits no longer crash.
- Fix: uploads whose names contain non-ASCII characters (`Café.csv`, `預算.csv`) no longer fail.
- Fix: a handler error returns a JSON 500 instead of dropping the connection; replies are ASCII-escaped.
- Fix: a small hostile `.xlsx` or a multipart upload of empty parts can no longer allocate hundreds of MiB;
  staged downloads are capped, cleared on reset or re-upload, and their URLs encoded.
- Fix: assisted intake took 9.6 s for 8,000 rows (hours near the 100,000-row cap); it now takes under a second.
- Fix: assisted CSV reading keeps quoted line breaks, detects `;`, tab and `|` delimiters, keeps the file's own
  row numbers, enforces the row/column/cell limits, and decodes UTF-8, UTF-16 or Windows-1252 (with a note)
  instead of substituting replacement characters.
- Fix: a PDF with one unreadable figure no longer skips sign resolution and subtotal removal; it stops with a
  PDF-specific message. `$(1,234)`, `−1,234` and `$—` are read as printed.
- Fix: a caller's Decimal precision or rounding no longer changes audit values or the fingerprint; parsing an
  unreadable figure no longer leaves `InvalidOperation` set in the caller's context.
- Fix: hidden worksheets rank after visible ones; an oversized worksheet is named in the error; `FY99` orders
  before `FY00`; invisible characters (zero-width space, soft hyphen, tag characters) show as escapes.
- Fix (chat): "show me / give me" phrasings, "unfavourable", "top 3 expenses", "why is X over budget?", curly
  quotes and non-breaking spaces route correctly; `top 0` is refused; "download report now" no longer writes a
  file named `now`; "Upload a different file" works in every step; period answers must be a period found in
  the file; repeated line names are all shown; `expense status` lists the largest overspends first; `metrics`
  ignores reconciled subtotals; `sheet N` picks the Nth sheet; run-rate parsing handles ranges and half-years.
- Fix (chat): profitability, run rate, sensitivity, what-if, compare and utilization say when unclassified rows
  are left out; what-if refuses unclassified targets and drops over 100%; percentages use the absolute budget;
  thresholds show every digit; CSV exports guard text cells against spreadsheet formulas.
- Fix (UI): all 11 steps are labelled; a reload mid-intake keeps the server's step; error and 413 replies show a
  message; the input is a multi-line box (Enter sends, Shift+Enter adds a line, pasted tables keep their line
  breaks); one request at a time with a deadline; keyboard-reachable upload, sorting and drill-down; WCAG AA
  contrast; `aria-live` log; no external font request.
- Fix (`deterministic_conditioning`): curation Gate 2 and Gate 4 can fail; `verify_pipeline` can fail and audits
  the dataset the trainers use; the visualiser binds `127.0.0.1` and serves only its page; `DeterministicChatClient`
  stays offline unless a backend is configured; the package is type-checked in CI.
- Docs: the current audit schema is 1.7 (the PDF-statement record in `source.document`); `--chat`, `--hosted`,
  `--no-browser`, `--commentary`, `--assisted`, `--mapping` and the `pdf` extra are documented in the README;
  `render.yaml` builds `.[excel,pdf]`.

### Earlier in 0.3.0

- Record the file adjustments confirmed in the chat (header row below a title block,
  amounts in thousands, excluded subtotals, blank budgets read as 0) in audits
  downloaded from the chat, plus the digest of a layout mapping saved for that analysis.
  The chat and CLI `--assisted`/`--mapping` audits now share one builder; CLI audits are
  unchanged byte for byte.
- Measure baseline intake friction for FP&A analysts: add 9 synthetic real-world
  fixtures, baseline chat tests, and a message inventory documenting intake errors,
  jargon rates, and dead ends.
- Add intelligent assisted data intake (`src/variance_agent/intake.py`) with header-row
  detection, multi-sheet budget-vs-actual scoring, column synonym mapping, accounting
  dash parsing, and single-pass issue collection.
- Introduce plain-language conversational summaries ("Here's how I read your file")
  and blank budget confirmations ("Treat blank budgets as 0?"), eliminating intake dead
  ends for ERP title blocks, multi-sheet workbooks, accounting dashes, and pasted TSV data.
- Add `--assisted` opt-in CLI flag for non-standard file intake while guaranteeing
  100% byte-identical contract fixture compatibility for default CLI runs.
- Eliminate developer jargon (`!r` quoting, `Unclassified`, exception names, CLI flags)
  from all analyst-facing responses and resolve the Skip All classification loop bug.
- Reject mixed reporting currencies; support explicit USD/EUR/GBP without FX
  conversion. Reports name the reporting currency throughout all sections.
- Reject currency-decorated CLI thresholds instead of discarding their symbols.
- Display exact configured materiality thresholds in reports, preserving fractional
  cents and percentage digits while retaining ordinary amount/percentage rounding.
- Preserve literal HTML-entity and tilde text in source labels and reporting
  periods, including GitHub Markdown strikethrough markers.
- Reject JSON nesting beyond 128 object/array levels with a CLI validation error
  for both inputs and type maps across supported Python versions, preserving
  existing report/audit outputs.
- Fix an argparse formatting error that made `--help` crash.
- Publish audit schemas 1.0 through 1.4 and reviewed report/audit fixtures.
- Capture and parse the exact hashed source/type-map bytes; add versioned policy
  provenance and a recomputable public-payload digest.
- Expose classification/materiality decisions, summary verification, and driver
  reconciliation diagnostics. Preserve financial policy and hypothesis fallback.
- Add check-only validation without output artifacts and exact Excel worksheet
  selection; record the actual worksheet in audit schema 1.4.
- Keep older audit versions selectable; schema 1.0 remains USD-only. See
  [migration details](docs/input-contract.md) and [audit versions](docs/audit-contract.md).
- Add a comparison basis: compare Actual against Budget (default), Forecast, or Prior Period, one per run.
  Assisted intake and chat detect Forecast/Fcst/Outlook/Projection and Prior Year/PY/Last Year columns and
  period-only year columns (newest = Actual, next newest = Prior Period); ambiguous or unorderable
  comparisons stop and ask. Add `--compare-to {budget,forecast,prior-period}` (required in strict mode to use
  such columns), basis-specific zero-comparison labels, comparison naming in reports and chat, and
  "compare to forecast / prior year / budget" in chat. Saved layout mappings record the chosen basis.
- **Behavior change (assisted intake, chat, `--mapping`).** A lone Forecast column now runs as a Forecast
  comparison; it was previously read as the Budget with a note. Files with a Budget column plus Forecast,
  Prior Year, or period-only year columns now stop and ask (CLI exit 2) instead of using the first match.
  Files with only Budget/Actual columns, and strict-mode runs, produce the same reports and audits as before.
  Migration: pass `--compare-to budget` to keep the previous Budget reading.
- Publish audit schema 1.6, adding `comparison: {basis, label}` to the record and configuration
  identity. Schemas 1.0-1.5 are refused for Forecast and Prior Period runs. The commentary prompt now reads
  `comparison.basis` and `comparison.label`.
- Fix `--mapping` with `unit_scale` crashing.
- Fix a layout mapping saved in the chat giving different amounts when replayed with
  `--mapping`: amounts in a file titled "(in thousands)" were scaled twice, and
  `flip_signs` flipped every line (undoing the revenue flip and negating expenses).
  The mapping now adds only the scale or revenue flip the file itself does not show,
  flips only revenue lines stored as credits, and stops with an error when the file's
  title and the mapping disagree on the unit.
- Add Python 3.11-3.14, Windows output, minimal-install, and distribution CI gates;
  use one package-version source and include the declared MIT license.

## 0.2.0

The preceding deterministic CLI includes CSV/JSON/Excel validation, isolated
Decimal arithmetic, strict materiality, summary reconciliation, supported driver
checks, audit fingerprints, and staged output replacement. Historical defect and
regression evidence is retained in `docs/`.
