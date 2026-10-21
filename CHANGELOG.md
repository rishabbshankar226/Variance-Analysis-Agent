# Changelog

## 0.3.0 — Unreleased

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
- Publish audit schema 1.6 (current), adding `comparison: {basis, label}` to the record and configuration
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
