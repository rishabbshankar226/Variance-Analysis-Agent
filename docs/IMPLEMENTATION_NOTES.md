# Implementation Notes

Where the financial rules are implemented and how report consumers receive their results.

## Rule mapping

| Financial rule | Implementation |
|---|---|
| Python for every calculation | `src/variance_agent/analysis.py` uses `Decimal` arithmetic for every variance, threshold, aggregate, and driver calculation |
| Actual - Budget | `_percent_variance` and row analysis preserve the signed dollar variance |
| Zero-budget edge cases | `_percent_variance` returns `N/A (Unbudgeted)` for nonzero actuals and `0.0%` for zero/zero |
| Revenue vs. Expense F/U | `_status` is centralized and covered by tests |
| Dollar OR percentage materiality | `material` uses strict `>` logic and absolute magnitude |
| Sort by dollar-magnitude variance | `material_rows` sorts by `abs(variance_dollars)` descending |
| Avoid invented classification | explicit map/field first; conservative label cues second; otherwise `Unclassified` |
| Avoid double counting | subtotal/total rows are excluded from aggregate totals |
| Validate duplicate risk | repeated normalized line-item names generate a data-quality warning |
| Separate facts from hypotheses | driver claims are `Supported driver` only when supplied driver inputs reconcile; otherwise the report labels the section `Hypothesis` |
| Reconcile before output | final assertions recheck row math, materiality, sorting, and aggregate totals |
| Round only for display | arithmetic retains `Decimal` precision; formatting occurs in `report.py` |

## Calculation boundary

`analysis.py` owns arithmetic, materiality, classification, and reconciliation. `report.py` formats the accepted results. The original [reporting prompt](../prompt/variance_report_prompt.md) remains a reference for the reporting rules; it is not executed by the CLI.

## Scope

The tool doesn't attribute a variance to seasonality, inflation, timing or mix unless the operating data supplied supports that driver mathematically. It doesn't forecast, value, budget or model scenarios.

## Audit JSON

`src/variance_agent/audit.py` writes the analysis results and data-quality metadata to a versioned JSON record. It leaves out the raw rows, records the source file's SHA-256 and a fingerprint of the analysis, reports completeness, and marks each material driver as `supported` or `hypothesis`.

An optional LLM commentary consumer should read this record and describe its verified results. Source strings remain untrusted data under `trust_contract`; they cannot override the reporting instructions. The consumer must not redo calculations or invent drivers.
