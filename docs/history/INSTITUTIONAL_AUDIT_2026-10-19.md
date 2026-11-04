# Audit Ledger (Variance-Analysis-Agent) — Institutional Reconciled Audit 2026-10-19

Audit baseline: `137cb31979f028f96decb36100f8d86902566898` on `main`. Evidence locations refer to that baseline.

This audit executes a full-context root-cause bug audit across pure math domain logic, decimal arithmetic precision, CLI error boundaries, and file output permissions.

## Severity-ranked findings

| ID | Severity | file:line at baseline | Category | Root cause and reproduced evidence | Exact remediation and status |
|---|---|---|---|---|---|
| VA-17 | Critical | `src/variance_agent/analysis.py:147-153`; `src/variance_agent/report.py:46-55` | Variance Math | Negative baseline percentage variance divided by signed Budget: Budget `-100` and Actual `50` (variance `+150`, Favorable) resulted in `-150.0%`, inverting sign polarity. | Divide by $\|Budget\|$ (`abs(budget)`) in `_percent_variance()` and evaluate percentage sign in `_pct()` solely based on variance sign. Reconciled fraction oracle in `test_quality_audit.py:294` and documented in `docs/financial-rules.md`. Fixed. |
| VA-18 | High | `src/variance_agent/numeric.py:35` | Decimal Precision | `financial_context()` omitted `FloatOperation` from trapped exceptions. Operations between Decimals and binary floats executed or coerced silently. | Added `FloatOperation` to `traps` in `financial_context()` conforming strictly to IEEE 754-2019 standards and institutional model risk rules. Prohibits binary float operations. Fixed. |
| VA-19 | High | `src/variance_agent/numeric.py:50`; `src/variance_agent/report.py:33` | Decimal Precision | `ratio()` and `_money()` called `localcontext()` without binding to the policy context, inheriting ambient thread or process-global `decimal.getcontext()` precision/rounding mutations. | Bound `ratio()` and `_money()` directly to isolated `financial_context()`. Pure arithmetic maintains guaranteed 50-digit policy precision regardless of external context state. Fixed. |
| VA-20 | Medium | `src/variance_agent/cli.py:171` | Type Safety / Agentic CLI | `main()` caught `(OSError, ValueError, csv.Error, DecimalException, BadZipFile)` but omitted `RuntimeError`. Verification identity failures crashed with raw Python tracebacks. | Added `RuntimeError` to caught exceptions in `main()`, sanitizing errors through `parser.error()` with clean exit code 2. Fixed. |
| VA-21 | Low | `src/variance_agent/output.py:43-45` | State / I/O | `write_text_outputs()` only adjusted permissions if `path.exists()` was True. Newly created reports and audit files retained restrictive temporary `0600` permissions. | Applied process `umask` (`0o666 & ~umask`) to newly staged files while continuing to preserve exact permissions on pre-existing files. Fixed. |

## Verification suite and executed results

- **pytest**: 359 passed in 1.41s (354 pre-existing baseline tests + 5 deterministic regression tests).
- **ruff**: Zero lint errors found across all modules and scripts.
- **mypy --strict**: Zero type errors across all 16 tracked source and script files under strict configuration.
- **compileall**: Passed cleanly across `src`, `tests`, and `scripts`.
