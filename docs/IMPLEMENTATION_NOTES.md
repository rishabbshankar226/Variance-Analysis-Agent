# Implementation Notes

The repository converts the audited FP&A prompt into deterministic application behavior.

## Contract mapping

| Prompt requirement | Implementation |
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

## Design choice

The prompt is retained under `prompt/` as the behavioral reference, but the financial logic is implemented in code. This reduces dependence on model compliance for arithmetic, materiality, classification, and reconciliation.

## Intentional scope boundary

The engine does not infer causal explanations such as seasonality, inflation, timing, or mix unless supplied operating data mathematically supports the driver. It also does not expand into forecasting, valuation, budgeting, or scenario modeling.
