# Precision and driver audit

Baseline: `a220f3de3f9a767860bf771c385cfee8b9c2f5a6`.

This pass concentrates on the remaining numerical-policy limitation recorded in
the earlier audits and on selection among multiple supplied driver models.

## Confirmed failures

| Problem | Reproduction | Resolution |
|---|---|---|
| Caller Decimal settings affect financial output | Precision 4 renders 123457.79 as 123500.00 and changes computed ratios. | Fresh 50-digit contexts isolate analysis, report/audit output, and CLI threshold conversion. Caller precision, rounding, traps, and flags are preserved. |
| Rounded percentages suppress material rows | A 1/3 variance ratio compared with a threshold of 50 repeating 3s is treated as equal/nonmaterial. | Compare absolute variance to the exact product of threshold and absolute budget. Percentage display precision cannot decide materiality. |
| High-precision arithmetic silently loses values | Budget 1e100 and actual 0.01 lose the cent component under the old context. | Trap inexact financial arithmetic and out-of-range calculations with an actionable ValueError. Recurring ratios alone allow rounding. |
| First failed driver prevents later supported evidence | Volume/price fails, but units/price exactly reconciles 1000 to 1200. | Prefer the first reconciled complete model; retain the first nonreconciling model only if none reconcile. |
| Optional missing-value markers abort valid analysis | Budget Volume=N/A prevents use of a valid units/price model. | Treat documented missing markers as unavailable driver inputs. |
| Structured labels become inferred financial categories | A list containing Sales is converted to a string and inferred as Revenue. | Reject boolean and structured line-item labels. |

## Evidence and review

- Initial focused run: 12 failures and 1 passing control before changes.
- Expanded precision/driver module: 20 cases, including positive/negative budgets,
  exact threshold boundaries, caller and process-default rounding/trap isolation, CLI conversion,
  supported large values, and retention of hypothesis evidence.
- Full suite: 104 tests pass locally, including the existing 250-case independent
  Fraction oracle and CSV/JSON/Excel equivalence checks.
- Ruff, compilation, dependency consistency, and real CLI sample output checked.
- Changes are confined to numerical policy, driver selection, label validation,
  regression tests, and documentation. No runtime dependencies were added.

## Limits and compatibility

This is an explicit bounded-precision policy, not arbitrary-precision arithmetic.
Some previously accepted extreme inputs now fail safely. Percentage strings can
contain more digits than before, and affected audit fingerprints will change.
Financial inputs should use Decimal/string values when supplied through the Python
API; already-rounded binary floats cannot be repaired after the caller creates them.
Per-file atomic output still does not provide a transaction across report and audit.
The test results establish the specified behaviors, not the absence of all bugs.
