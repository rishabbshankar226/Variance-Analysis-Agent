# Variance Analysis Agent

A Python application for descriptive variance analysis against supplied budgets, forecasts, prior periods, consensus, estimates and guidance. It reads CSV, JSON, XLSX, or XLSM, or the income statement in a 10-K or 10-Q PDF (with `--assisted`), validates financial inputs, and produces a Markdown report and optional versioned audit JSON.

All financial arithmetic runs in deterministic code. The application makes no model or network calls, requires no credentials, and has no third-party runtime dependencies for CSV or JSON. Excel and PDF support are optional. Python 3.11 or later is required; CI covers Python 3.11–3.14 and Windows output contracts.

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

Install PDF support (10-K and 10-Q filings) with `python -m pip install -e '.[pdf]'`. See [PDF filings](docs/input-contract.md#pdf-filings---assisted).

Direct dependencies and the build backend are pinned in `pyproject.toml`; `requirements-typecheck.txt` pins the development checker and its supporting packages. Other transitive dependencies are resolved by pip for the selected Python version and platform; these pins are not a complete cross-platform environment lock.

## Operation

```sh
variance-agent examples/sample_variance.csv \
  --period 'Q3 2026' \
  --dollar-threshold 10000 \
  --percent-threshold 5 \
  --output reports/q3-2026.md \
  --audit-json reports/q3-2026.audit.json \
  --xlsx reports/q3-2026.xlsx
```

Omit `--output` to print the report. `--xlsx` writes a formatted Excel workbook (Summary, Material Variances, Root Causes & Actions, All Rows) using only the standard library; Excel stores doubles, so use the CSV or audit JSON when exact decimals matter. In the chat UI, `export excel` downloads the same workbook. `--percent-threshold 5` means 5%; the Python API accepts the ratio `Decimal("0.05")`. Threshold equality is not material. To validate without writing outputs:

```sh
variance-agent examples/sample_variance.csv \
  --period 'Q3 2026' --dollar-threshold 10000 --percent-threshold 5 --check-only
```

Use `--currency EUR` or `--currency GBP` for those reporting units. The default is USD. Conflicting symbols or row currencies are rejected; there is no FX conversion. `--sheet 'Reviewed'` selects an exact Excel worksheet name. Without it, the active worksheet is read. Excel formulas use stored cached values and are never recalculated; missing caches fail required-field validation.

Successful commands exit 0. Expected input or filesystem failures exit 2 with an explanation. Report, audit, workbook, source, and type-map paths must be distinct, including symlink and hardlink aliases. All outputs are staged before publication. Each replacement is atomic; multiple replacements are not one transaction. If a later one fails, rerun the command to regenerate the set.

## Input contract

| Field | Requirement |
|---|---|
| Line Item | Required nonblank scalar label; aliases include Line, Item, Account, Account Name, Category |
| Budget | Required finite number; aliases include Budget Amount, Plan, Planned. It is the comparison amount: with `--compare-to forecast` or `prior-period` the column named Forecast or Prior Year supplies it |
| Actual | Required finite number; aliases include Actual Amount, Actuals |
| Type | Recommended Revenue/Expense classification; ambiguous or unknown values remain Unclassified |
| Row Kind | Optional Detail, Total, or Subtotal; resolves ambiguous summary labels |
| Currency | Optional matching USD/EUR/GBP code; blank inherits the reporting unit |
| Period | Optional; if supplied anywhere, every row must provide the configured reporting period |

CSV headers are normalized consistently; collisions, alias ambiguity, misaligned rows, and populated unnamed columns are rejected. JSON accepts a row-object list or an object containing `rows` or `data`, with unique keys and finite numeric constants. Other metadata columns remain data and are not interpreted as instructions.

Numeric strings may contain correctly grouped thousands, scientific notation, currency symbols matching the reporting unit, or accounting parentheses. Missing Budget/Actual, booleans, structured financial values, and nonfinite amounts are rejected. Source JSON numbers and stored numeric Excel XML are converted directly to `Decimal`. Python callers should provide strings or string-initialized `Decimal`; a float already rounded by its producer cannot recover lost digits. The tool likewise cannot recover precision that Excel discarded before saving.

The default path compares Actual against one amount: Budget (default), Forecast, or Prior Period. With `--assisted` (and in chat), intake detects the comparison from headers: Forecast, Fcst, Outlook, Projection, or Projected give a Forecast comparison; Prior Year, PY, Last Year, or Prior Period give a Prior Period comparison; and amount columns labeled only by period (`FY2025`/`FY2024`, `2025`/`2024`, optionally suffixed "Actual") compare the newest as Actual against the next newest as Prior Period. With three or more periods the newest two are compared and intake says so. More than one distinct comparison (including a named comparison beside period-only columns), periods that cannot be ordered, or period columns that also name a comparison stop and ask; rerun with `--compare-to` to choose. Wide Budget/Actual period-pair layouts remain Budget. Strict mode (no `--assisted` or `--mapping`) detects nothing: use `--compare-to {budget,forecast,prior-period}` to name the basis; a basis with no matching column exits 2 naming the columns found. Reports, chat, and audit name the comparison (for example "Prior Period (FY2024)"); files with only Budget and Actual columns produce the same output as before.

Classification precedence is type map, explicit Type, then conservative label inference. Use `--type-map examples/type_map.json` to supply reviewed classifications. Expense amounts follow the positive-cost convention; signed-ledger transformations require explicit preprocessing. Unclassified rows are excluded from category aggregates and make completeness and net operating impact unavailable. Duplicate names produce a warning because dimensional duplicates may be intentional.

## Financial methodology

| Measure | Definition |
|---|---|
| Amount variance | Actual − Budget |
| Percentage variance | Amount variance / absolute nonzero comparison amount |
| Zero Budget | Zero/zero has zero variance; nonzero Actual is unbudgeted with no defined percentage (Forecast: "not in forecast"; Prior Period: "new this period") |
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

## Hosting the chatbot

`variance-agent --chat` opens the chatbot locally; add `--no-browser` to print the local URL without opening a browser. `variance-agent --chat --hosted` serves it on `0.0.0.0:$PORT` (default 10000) without opening a browser. In hosted mode, "export ... to <path>" is refused and files are offered as downloads instead. `render.yaml` deploys this to a free Render web service: in the Render dashboard choose **New → Blueprint** and select this repository. Every visitor shares one chat session, so treat the hosted chatbot as a single-user demo. Free instances sleep after 15 idle minutes and take about a minute to wake.

## Architecture and trust boundary

`parsing.py` captures and validates source data; `excel.py` bounds OOXML expansion and preserves stored decimals. `analysis.py` computes and verifies rows, aggregates, classification, and driver evidence. `numeric.py` isolates arithmetic policy. `report.py` formats verified facts; `audit.py` records versioned facts and provenance. `output.py` stages filesystem writes. `cli.py` coordinates these modules without performing independent financial analysis.

The source capture is limited to 32 MiB. Excel permits at most 2,048 archive members, 64 MiB total expanded content, 100,000 physical row positions including the header, 256 columns, and 1,000,000 cells per worksheet. CSV/JSON permit up to 100,000 data rows subject to the column/value limits. Text fields are limited to 128 KiB, numeric text to 4,096 characters, and JSON/XML nesting to 128 containers. Duplicate archive members, XML DTD/entities, invalid or unordered physical coordinates, and malformed structures are rejected before worksheet expansion. Inflated producer dimensions do not override physical content checks.

Legacy runs default to audit 1.7; new semantics use unreleased 1.8. `--audit-schema-version` retains versions 1.0–1.8; 1.0 is USD-only. Schema 1.6 records the comparison (`basis`, `label`) in the record and configuration identity; 1.0–1.5 are refused for Forecast and Prior Period runs. Schema 1.7 adds `source.document`, which records how a PDF statement was read; 1.0–1.6 are refused for PDF input. Schema 1.8 adds measure, direction, comparison-set, flat-segment, presentation and optional descriptive-statistic facts; older schemas refuse these new semantics. Published JSON schemas forbid additional properties. Source SHA-256 identifies captured bytes; the analysis fingerprint includes all derived rows; the public payload digest is recomputable. Hashes detect changes and do not authenticate authorship or establish source completeness. Report and audit creation reverify financial identities, including results supplied through the Python API.

Source labels and periods are untrusted data. Reports escape Markdown/HTML and render terminal/bidirectional controls visibly. Audit JSON retains source text as data and excludes raw row dictionaries. The [commentary prompt](prompt/variance_report_prompt.md) consumes verified audit facts only; it is not a runtime agent or an enforcement boundary. Any separate LLM integration needs strict runtime argument/output schemas, bounded calls and tokens, timeouts, retry limits, and environment-loaded credentials. Those integrations are outside this CLI and are not implicitly supplied by a prompt.

## Verification

```sh
python -m pip install -c requirements-typecheck.txt -e '.[dev,excel,pdf,release]'
python -m pytest -q
python -m ruff check .
python -m mypy --strict src/variance_agent scripts deterministic_conditioning
python -m compileall -q src tests scripts deterministic_conditioning
python -m pip check
python -m build --outdir dist
python -m twine check dist/*
python scripts/check_distribution.py dist
```

Tests include exact Fraction-oracle accounting/materiality properties, financial/reporting regressions, immutable audit schemas and reviewed reports, hostile workbook preflight, CLI output preservation, and distribution installation checks. Also run a separate non-editable installation without either optional input extra:

```sh
python -m venv ../variance-minimal
../variance-minimal/bin/python -m pip install .
../variance-minimal/bin/python scripts/check_installation.py --without-excel --without-pdf
../variance-minimal/bin/python -m pip check
```

On Windows, use `../variance-minimal/Scripts/python.exe` for that environment.

Strict typing covers `src/variance_agent`, `scripts` and the auxiliary `deterministic_conditioning` package. It is configured in `pyproject.toml` (`[tool.mypy] files`), including bans on explicit and unimported `Any`, and CI runs the command above on each supported Python version. List the package explicitly: when the checkout is also the editable-install target, mypy treats an unlisted package as installed and hides its errors, so a run from a different directory reports errors that CI never showed. Without the `pdf` extra the PDF tests are skipped.

See the [audit ledger](docs/INSTITUTIONAL_AUDIT_2026-10-16.md) for executed results, the [financial rules](docs/financial-rules.md) for exact semantics, and the [audit contract](docs/audit-contract.md) for integrity recipes. Forecasting, valuation, budget creation, and automatic model commentary are outside this application.

## Reader examples

Every company and value in these fixtures is fictional; all tickers end in
`.FAKE`. Currency amounts in the small scenarios are supplied in millions;
EPS, rates and counts keep their own units. Thresholds use those supplied units.

### Maya: budget versus actual

The existing FP&A path and outputs remain the default. In chat, upload the file
and confirm its interpretation, period, thresholds and currency as before.

```sh
variance-agent tests/fixtures/multi_audience/fpa.csv \
  --period 3Q26 --dollar-threshold 10 --percent-threshold 2
```

### Priya: supplied consensus and mixed measures

Compare revenue, EPS, margin and units against supplied Street figures. Percent
rows show bps, and only Consensus receives Beat/Miss/In line labels.

```sh
variance-agent tests/fixtures/multi_audience/consensus.csv --preset earnings \
  --compare-to consensus --period 3Q26 --dollar-threshold 10 --percent-threshold 2 \
  --bps-threshold 25 --per-share-threshold 0.01 --count-threshold 1000
```

For supplied ranges, use `guidance.csv` and `--compare-to guidance`. For a PDF,
use `--assisted --preset earnings`, supply the occurring measure cutoffs and
explicit share-count direction choices through a mapping. See the
[filing policy](docs/input-contract.md#opted-in-eps-and-share-counts-from-filings).
In chat, choose the earnings review or request “review earnings” for a filing.

### Dan: model, consensus and prior year together

The explicit comma list chooses the comparison order. Each basis reuses the
single-basis engine. The report also shows supplied Estimate minus Consensus.

```sh
variance-agent tests/fixtures/multi_audience/comparison_set.csv --preset earnings \
  --compare-to consensus,estimate,prior-period --period 3Q26 \
  --dollar-threshold 10 --percent-threshold 2 --per-share-threshold 0.01
```

### Wei: isolated panels and exact long output

The typed `analyze_table`, `analyze_file` and `analyze_panel` functions are available
from `variance_agent`. See [the API contract](docs/api.md) for exact units,
ordering, provenance, formula protection and compatibility policy.

```sh
variance-agent tests/fixtures/multi_audience/panel.csv \
  --preset quant --group-by Ticker,Period --compare-to consensus \
  --dollar-threshold 10 --percent-threshold 2 \
  --bps-threshold 25 --per-share-threshold 0.01 --count-threshold 1000 \
  --long-output panel.csv --long-output-jsonl panel.jsonl --errors-output errors.csv
```

This fictional fixture deliberately fails one group: five groups succeed and the
command exits **3** with exactly one error row. Exit 0 means success; exit 2 still
means a command/data/global failure. Panel runs never prompt. Declare all needed
measure cutoffs and ambiguous choices. With Period as a group key, omit
`--period`; otherwise it is required. Inputs retain the 32 MiB, 100,000-row,
256-column and 1,000,000-cell caps across the whole panel. Split larger universes
into several files.

## Earnings and quant presets

Presets supply presentation/intake defaults; every explicit option wins and no
preset supplies materiality thresholds.

| Preset | Extended headers | Report | Filing EPS/count lines | Other defaults |
|---|---|---|---|---|
| `fpa` | Off | Existing report | Off | Identical to no preset |
| `earnings` | On | Earnings headline table and Earnings workbook sheet | On | Revenue, EPS and margin headline rows |
| `quant` | On | Markdown only with `-o` | Off | Requires `--long-output` or `--long-output-jsonl` |

Override layout with `--layout standard` or `--layout earnings`. Use
`--per-share-lines` or `--no-per-share-lines` for filing intake. Repeat
`--headline 'Line Item'` to replace the default earnings headline selection.
Earnings presentation shows supplied guidance position, prior-year change
(`YoY %`), flat segments and remaining KPIs. Only Consensus uses Beat/Miss/In
line; other comparisons retain F/U. New chat questions include “did we beat
consensus”, “vs the street”, “margin in bps” and “where are we vs guide”. The
review confirms how the supplied file is read; it makes no estimates.

```sh
variance-agent tests/fixtures/multi_audience/consensus.csv --preset earnings \
  --period 3Q26 --dollar-threshold 10 --percent-threshold 2 \
  --bps-threshold 25 --per-share-threshold 0.01 --count-threshold 1000 \
  -o earnings.md --xlsx earnings.xlsx --audit-json earnings.audit.json
```

Export or layout flags alone keep existing FP&A metadata inert. Extended headers
require an earnings/quant preset, a new comparison basis, an explicit mapping or
confirmed earnings review. The new Python API itself is an explicit opt-in;
`AudienceOptions.extended_headers=False` can preserve legacy header meanings.

Add `--history tests/fixtures/multi_audience/history.csv --surprise-window 8`
to the consensus example to compute descriptive standardized surprise from
supplied prior values. The fixture's diluted EPS result is 2.8577 to four
decimals. A supplied `Std Dev` column also enables dispersion surprise. These
statistics create no estimates or predictions. Their units, null reasons,
minimum history and rounding rules are in the [financial rules](docs/financial-rules.md).

Vendor headers, GAAP versus adjusted metrics, count units and fiscal/calendar
alignment require the user's review. There is no cross-file metric matching,
nested segment hierarchy, FX conversion, valuation or forecasting. Executed
checks and remaining boundaries are in the [implementation report](docs/MULTI_AUDIENCE_2026-10.md).
