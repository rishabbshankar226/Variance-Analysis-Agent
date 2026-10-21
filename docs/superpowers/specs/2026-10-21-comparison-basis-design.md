# Comparison basis: compare Actual against Budget, Forecast, or Prior Period

Date: 2026-10-21
Status: Design approved in conversation; awaiting written-spec review

## Purpose

Today the agent only compares Actual against Budget. Many people who want a
variance analysis have no budget: a public filing (10-K) or an annual report
shows this year next to last year, and finance teams often track actuals
against a forecast rather than the original budget. This feature lets one run
compare Actual against exactly one of Budget, Forecast, or Prior Period, with
the report, audit, and chat always naming the comparison truthfully.

## Where this sits

The wider request ("accept multi-year files, statements without a budget,
forecasts, PDFs, and raw transactions") decomposes into three sub-projects,
each with its own spec → plan → implementation cycle:

1. **Comparison basis (this spec).** Covers multi-year files, budgetless
   statements, and supplied forecasts.
2. **Document intake.** SEC XBRL import for 10-Ks; PDF table extraction with
   user confirmation for documents only available as PDF (e.g. ACFRs). Depends
   on (1), because a 10-K has no budget.
3. **Transaction aggregation.** Roll invoice/bank lines up into an Actual column
   by account.

Implementation starts after the uncommitted Phase 2 intake work on
`intake/phase-2-real-ledgers` lands, to avoid conflicts in `intake.py`.

## Goals

- One comparison per run: Budget (default), Forecast, or Prior Period.
- Detect the comparison from headers, state the choice in one line, and ask
  when it is ambiguous. Allow an explicit override.
- Every user-visible label (report, chat, commentary prompt) names the real
  comparison. Nothing calls a forecast or prior year a "budget".
- Budget runs are byte-identical to today's output.

## Non-goals

- Generating forecasts. The roadmap keeps forecasting out of scope; this
  feature only compares against a forecast the user supplies.
- Several comparisons in one report (e.g. side-by-side Budget and Forecast
  variance columns).
- Renaming the internal `budget` field or audit JSON keys.
- New driver-column aliases (e.g. "Prior Volume"). Existing `Budget Volume` /
  `Budget Price` names keep working for every basis.
- PDF, XBRL, or transaction input (sub-projects 2 and 3).

## Design

### Model (`models.py`)

- New `ComparisonBasis(StrEnum)`: `BUDGET`, `FORECAST`, `PRIOR_PERIOD`.
- `AnalysisConfig` gains:
  - `comparison_basis: ComparisonBasis = ComparisonBasis.BUDGET`
  - `comparison_label: str | None = None` (display text such as `FY2024` or
    `Q3 Outlook`; validated with `limits.validate_text`).
- Internally, `budget` continues to mean "the amount Actual is compared
  against". `analysis.py` arithmetic is unchanged.

### Detection (`intake.py`)

Extends Phase 2 header matching (`match_column_synonym`, `detect_period_pairs`).

| Headers | Role | Basis |
|---|---|---|
| Budget, Plan, Planned (existing) | comparison | Budget |
| Forecast, Fcst, Outlook, Projection, Projected | comparison | Forecast |
| Prior Year, PY, Last Year, Prior Period | comparison | Prior Period |
| Two or more amount columns labeled only by period (`FY2025`, `2025`, `Q3 2025`) with no Actual/Budget/Forecast words | newest = Actual, next newest = comparison | Prior Period |

- `comparison_label` comes from the comparison column's header period when
  present (e.g. `FY2024`), else from the basis name.
- Intake reports its choice in one line, e.g.
  "Comparing FY2025 against FY2024 (prior period)."
- More than one comparison candidate (e.g. Budget and Forecast both present)
  is an `IntakeProblem` listing the candidates; intake does not choose.

### Override

- CLI: `--compare-to {budget,forecast,prior-period}`. Default is detection;
  with no comparison-specific headers this resolves to Budget as today.
- Chat: a reply such as "compare to forecast" sets the same option in the
  session.
- An override naming a basis with no matching column is an expected input
  error (exit 2) naming the columns found.

### Financial semantics

- Variance, percentage, materiality, and favorability rules are unchanged:
  revenue above the comparison amount is favorable; expense above it is
  unfavorable.
- Zero comparison amount with nonzero Actual: the label "unbudgeted" becomes
  "not in forecast" (Forecast) or "new this period" (Prior Period). The
  undefined-percentage rule is unchanged.

### Report (`report.py`)

- The table column header and every "Budget"/"vs budget" phrase use the basis
  wording plus label, e.g. "Prior Period (FY2024)", "vs forecast".
- Driver-section labels follow the same wording.
- Budget runs render exactly as today; existing goldens are unchanged.

### Audit (`audit.py`, `schemas/audit-1.6.schema.json`)

- New schema version 1.6 = 1.5 plus `comparison: {basis, label}` inside the
  config identity, so the basis is covered by the analysis fingerprint.
- The `budget` keys keep their names; schema descriptions document them as
  "the comparison amount".
- `CURRENT_SCHEMA_VERSION` becomes 1.6. Requesting 1.0–1.5 for a non-Budget
  run is refused with a message suggesting `--audit-schema-version 1.6`, since
  those versions would record the comparison as a budget.
- 1.6 is separate from the unreleased 1.5 so Phase 2 and this feature can be
  reviewed and landed independently.

### Chat (`chat/handlers.py`, `chat/knowledge.py`, `chat/responses.py`)

- One helper returns the basis noun ("budget", "forecast", "prior period")
  and all user-visible wording goes through it.
- `knowledge.py` explains the three comparison types and how to choose one.

### Commentary prompt (`prompt/variance_report_prompt.md`)

- Instructs the consumer to read `comparison.basis` and `comparison.label`
  and never describe a forecast or prior period as a budget.

### Documentation

- README "Input contract" and `docs/input-contract.md`: comparison columns and
  `--compare-to`.
- `docs/financial-rules.md`: basis-specific zero-comparison wording.
- `docs/audit-contract.md` and CHANGELOG: schema 1.6.

## Errors and edge cases

All surface through the existing plain-language `IntakeProblem` path.

| Case | Behavior |
|---|---|
| Multiple comparison candidates | Stop; list candidates; ask which one |
| Three or more period-only amount columns | Compare newest against the next newest; say so ("Found FY2025, FY2024, FY2023 — comparing FY2025 against FY2024.") |
| Period labels that cannot be ordered (e.g. `FY2025` with `Q3 2024`) | Stop and ask; never guess |
| `--compare-to` basis not present | Exit 2 naming the columns found |
| Pre-1.6 audit schema requested for non-Budget run | Refuse; suggest 1.6 |

## Testing (test-driven)

- **Fixtures** (`tests/fixtures/realworld/build_fixtures.py`): 10-K-style
  FY2025/FY2024/FY2023 file; Forecast file; Budget + Forecast ambiguous file;
  year columns in reverse order.
- **Unit:** header detection per basis, period ordering, label extraction,
  every error message above, `--compare-to` override.
- **Audit:** 1.6 schema contract tests, fingerprint changes when basis
  changes, refusal for 1.0–1.5 on non-Budget runs.
- **Report goldens:** one Forecast run and one Prior Period run.
- **Chat:** no reply contains "budget" during a non-Budget session.
- **Regression:** all existing goldens unchanged; Fraction-oracle property
  tests pass unchanged and are parameterized over all three bases (numbers
  must be identical).
- Full verification suite from the README (pytest, ruff, mypy --strict,
  build/twine/distribution checks).
