# Variance Analysis Agent

A Python command-line application for descriptive budget-versus-actual analysis. It reads CSV, JSON, XLSX, or XLSM, validates financial inputs, and produces a Markdown report and optional versioned audit JSON.

All financial arithmetic runs in deterministic code. The application makes no model or network calls, requires no credentials, and has no third-party runtime dependencies for CSV or JSON. Excel support is optional. Python 3.11 or later is required; CI covers Python 3.11–3.14 and Windows output contracts.

## Installation

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

On Windows, activate with `.venv\Scripts\activate`. Install Excel support with:

```sh
python -m pip install -e '.[excel]'
```

Direct dependencies and the build backend are pinned in `pyproject.toml`. Transitive dependencies are resolved by pip for the selected Python version and platform; these pins are not a complete cross-platform environment lock.

## Operation

```sh
variance-agent examples/sample_variance.csv \
  --period 'Q3 2026' \
  --dollar-threshold 10000 \
  --percent-threshold 5 \
  --output reports/q3-2026.md \
  --audit-json reports/q3-2026.audit.json
```

Omit `--output` to print the report. `--percent-threshold 5` means 5%; the Python API accepts the ratio `Decimal("0.05")`. Threshold equality is not material. To validate without writing outputs:

```sh
variance-agent examples/sample_variance.csv \
  --period 'Q3 2026' --dollar-threshold 10000 --percent-threshold 5 --check-only
```

Use `--currency EUR` or `--currency GBP` for those reporting units. The default is USD. Conflicting symbols or row currencies are rejected; there is no FX conversion. `--sheet 'Reviewed'` selects an exact Excel worksheet name. Without it, the active worksheet is read. Excel formulas use stored cached values and are never recalculated; missing caches fail required-field validation.

Successful commands exit 0. Expected input or filesystem failures exit 2 with an explanation. Report, audit, source, and type-map paths must be distinct, including symlink and hardlink aliases. Both outputs are staged before publication. Each replacement is atomic; two replacements are not one transaction. If the second fails, rerun the command to regenerate the pair.

## Input contract

| Field | Requirement |
|---|---|
| Line Item | Required nonblank scalar label; aliases include Line, Item, Account, Account Name, Category |
| Budget | Required finite number; aliases include Budget Amount, Plan, Planned |
| Actual | Required finite number; aliases include Actual Amount, Actuals |
| Type | Recommended Revenue/Expense classification; ambiguous or unknown values remain Unclassified |
| Row Kind | Optional Detail, Total, or Subtotal; resolves ambiguous summary labels |
| Currency | Optional matching USD/EUR/GBP code; blank inherits the reporting unit |
| Period | Optional; if supplied anywhere, every row must provide the configured reporting period |

CSV headers are normalized consistently; collisions, alias ambiguity, misaligned rows, and populated unnamed columns are rejected. JSON accepts a row-object list or an object containing `rows` or `data`, with unique keys and finite numeric constants. Other metadata columns remain data and are not interpreted as instructions.

Numeric strings may contain correctly grouped thousands, scientific notation, currency symbols matching the reporting unit, or accounting parentheses. Missing Budget/Actual, booleans, structured financial values, and nonfinite amounts are rejected. Source JSON numbers and stored numeric Excel XML are converted directly to `Decimal`. Python callers should provide strings or string-initialized `Decimal`; a float already rounded by its producer cannot recover lost digits. The tool likewise cannot recover precision that Excel discarded before saving.

Classification precedence is type map, explicit Type, then conservative label inference. Use `--type-map examples/type_map.json` to supply reviewed classifications. Expense amounts follow the positive-cost convention; signed-ledger transformations require explicit preprocessing. Unclassified rows are excluded from category aggregates and make completeness and net operating impact unavailable. Duplicate names produce a warning because dimensional duplicates may be intentional.

## Financial methodology

| Measure | Definition |
|---|---|
| Amount variance | Actual − Budget |
| Percentage variance | Amount variance / signed nonzero Budget |
| Zero Budget | Zero/zero has zero variance; nonzero Actual is unbudgeted with no defined percentage |
| Materiality | Absolute amount or absolute percentage strictly exceeds its threshold; zero Budget uses amount only |
| Favorability | Positive revenue variance is favorable; positive expense variance is unfavorable; zero is neutral |
| Ordering | Descending absolute variance, preserving input order for ties |
| Aggregation | Classified included detail rows; one reconciled category summary is excluded to avoid double counting |

Calculations use a fresh Decimal context with 50 significant digits, `ROUND_HALF_EVEN`, and exponent limits −999 to 999. Division-by-zero, invalid operation, overflow, underflow, and inexact amount arithmetic fail explicitly. Exact subnormal values down to the context's minimum exponent are representable. Recurring API percentage ratios round to 50 significant digits; materiality uses exact cross-products and report percentages use exact integer ratios with a single half-even rounding to one decimal percentage point.

Report currency values share at least two decimal places. Additional fractional places are retained when necessary for exact detail-to-total and driver reconciliation; the report states the resulting precision. No account receives an invented penny allocation. Audit financial values remain unrounded fixed-point decimal strings.

One summary per classified category may reconcile to supplied details within 0.01 for Budget and Actual. A standalone summary is included without a claim of detail verification. Multiple/nested summaries are rejected because the input lacks hierarchy metadata.

## Driver evidence

The engine checks complete volume/price, units/price, headcount/rate, and customers/rate models in that order. Missing optional values skip a model. The first model meeting the reconciliation checks is used; otherwise the first complete model remains a hypothesis.

For quantity Q and rate P, the effects are `(Actual Q − Budget Q) × Budget P` and `(Actual P − Budget P) × Actual Q`. Balance tolerance is `max(0.01, abs(Budget) × 0.000001, abs(Actual) × 0.000001)`; variance tolerance is `max(0.01, abs(Actual − Budget) × 0.000001)`. An accepted nonzero model residual is an explicit **Unexplained residual** component, so components sum exactly to observed variance. It is requested for reconciliation and is not presented as an operating cause. These models do not establish causation or implement a separate mix decomposition.

For the supplied sample and the command above, material variances are Subscription Revenue +15,500, Marketing Expense +13,000, Payroll Expense +8,000, and Services Revenue −3,000. Subscription Revenue's +15,500 decomposes into +5,000 volume and +10,500 price.

## Architecture and trust boundary

`parsing.py` captures and validates source data; `excel.py` bounds OOXML expansion and preserves stored decimals. `analysis.py` computes and verifies rows, aggregates, classification, and driver evidence. `numeric.py` isolates arithmetic policy. `report.py` formats verified facts; `audit.py` records versioned facts and provenance. `output.py` stages filesystem writes. `cli.py` coordinates these modules without performing independent financial analysis.

The source capture is limited to 32 MiB. Excel permits at most 2,048 archive members, 64 MiB total expanded content, 100,000 physical row positions including the header, 256 columns, and 1,000,000 cells per worksheet. CSV/JSON permit up to 100,000 data rows subject to the column/value limits. Text fields are limited to 128 KiB, numeric text to 4,096 characters, and JSON/XML nesting to 128 containers. Duplicate archive members, XML DTD/entities, invalid or unordered physical coordinates, and malformed structures are rejected before worksheet expansion. Inflated producer dimensions do not override physical content checks.

The current audit schema is 1.4. `--audit-schema-version` retains versions 1.0–1.4; 1.0 is USD-only. Published JSON schemas forbid additional properties. Source SHA-256 identifies captured bytes; the analysis fingerprint includes all derived rows; the public payload digest is recomputable. Hashes detect changes and do not authenticate authorship or establish source completeness. Report and audit creation reverify financial identities, including results supplied through the Python API.

Source labels and periods are untrusted data. Reports escape Markdown/HTML and render terminal/bidirectional controls visibly. Audit JSON retains source text as data and excludes raw row dictionaries. The [commentary prompt](prompt/variance_report_prompt.md) consumes verified audit facts only; it is not a runtime agent or an enforcement boundary. Any separate LLM integration needs strict runtime argument/output schemas, bounded calls and tokens, timeouts, retry limits, and environment-loaded credentials. Those integrations are outside this CLI and are not implicitly supplied by a prompt.

## Verification

```sh
python -m pip install -e '.[dev,excel,release]'
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests scripts
python -m pip check
python -m build --outdir dist
python -m twine check dist/*
python scripts/check_distribution.py dist
```

Tests include exact Fraction-oracle accounting/materiality properties, financial/reporting regressions, immutable audit schemas and reviewed reports, hostile workbook preflight, CLI output preservation, and distribution installation checks. `scripts/check_installation.py --without-excel` must run in a separate non-editable installation without the Excel extra.

Strict source and script typing is configured in `pyproject.toml`. The checker is not yet included in the development extra; its proposed pinned version is mypy 2.4.0. Once available, the command is:

```sh
python -m mypy --strict src/variance_agent scripts
```

See the [audit ledger](docs/INSTITUTIONAL_AUDIT_2026-10-16.md) for executed results and remaining approval gates, the [financial rules](docs/financial-rules.md) for exact semantics, and the [audit contract](docs/audit-contract.md) for integrity recipes. Forecasting, valuation, budget creation, and automatic model commentary are outside this application.
