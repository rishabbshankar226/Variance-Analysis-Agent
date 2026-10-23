# Multi-audience expansion: implementation plan and STOP 1

Prepared 2026-10-22 (America/Chicago), against `main` at
`f5cd79c24b22197932c657edf3fd9a6a7dcefd4d` (`f5cd79c`).
Branch: `feat/multi-audience`. Status: **Phase 0 complete;
STOP 1 approved; implementation in progress**.

## Execution brief

Preserve Maya's current FP&A workflow and all existing outputs. Add explicit
opt-in support for Priya's earnings review, Dan's comparison sets, and Wei's
typed panel analysis. Work through phases 1–8, test first, commit after each green
phase, and preserve deterministic Decimal arithmetic and existing input limits.
No new runtime dependency, external service, model call, investment advice,
hierarchy, FX, valuation, forecasting, or scenario modeling is authorized.
No push, merge, tag, or release is authorized. STOP 2 applies before changing any
existing test or contract fixture. STOP 3 follows phase 4; phases 5 and 7 can be
dropped only at that decision. STOP 4 precedes any push or merge.

Phase 0 changes only this plan. No production code, existing tests, schemas,
fixtures, or `deterministic_conditioning/` files change. Temporary probes and
verification logs are outside the checkout. The phase-0 commit must name the
readers it serves. Future file additions must first be listed here with a reason.

## Baseline: source inspection

Read in full: `README.md`, `.agents/rules/variance-intake.md`,
`docs/financial-rules.md`, `docs/input-contract.md`, `docs/audit-contract.md`,
`docs/roadmap.md`, `src/variance_agent/models.py`, `comparison.py`, `numeric.py`,
`report.py`, `audit.py`, `cli.py`, and `__init__.py`.

Read targeted windows, after searching definitions and call sites, in
`analysis.py`, `intake.py`, `pdf_tables.py`, `statement_shape.py`, `xlsx.py`,
`parsing.py`, `mapping.py`, and `chat/{handlers,intent,knowledge,session,
responses,server}.py`. Read the standing rules, limits, project configuration,
type-check pins, CI workflow, contract tests, and chat setup helpers. Large source
files were not loaded whole.

| Brief assertion | Verified baseline |
|---|---|
| Starting version / tree | `0.3.0`, described as development metadata; 266 tracked files; clean `main` at `f5cd79c` before branching |
| Test baseline | **Measured:** 1,772 passed in 37.72 seconds on Python 3.12.14, Linux x86_64; optional Excel/PDF extras installed |
| CI | Linux Python 3.11–3.14; strict mypy, ruff, compilation, pytest, pip check; separate minimal/package jobs and Windows output smoke job |
| Comparison bases | Budget, Forecast, Prior Period only; one basis per result; strict CLI defaults to Budget; CSV assisted intake asks on multiple recognized bases |
| Forecast synonyms | Forecast, Fcst, Outlook, Projection, Projected; Outlook must stay Forecast |
| Period parser | `Q3 2026` and `Q3-26` recognized; none of the five requested new quarter spellings recognized |
| Favorability | Revenue/Expense classification controls F/U; no measure kind or Better direction; zero variance is Neutral even for an unlabeled legacy row |
| Values | A single reporting currency; USD/EUR/GBP; no per-share, rate, or count semantics |
| Percentage | `_percent_variance` divides by `abs(budget)`; README methodology's “signed nonzero Budget” is stale |
| PDF | `_statement_table` excludes per-share/share-count rows with the exact existing note; statement shaping assumes every remaining numeric column is additive money |
| Python API | Four names in `__all__`; constructors/signatures recorded below; `__version__` is also an attribute, outside `__all__`; no panel/long-format surface |
| CLI and chat | CLI description is FP&A-specific; knowledge intent set has no earnings concepts; route matching is ordered and first-match wins |
| Audit | Default 1.7; 1.0–1.7 selectable; all eight published schema files exist and prohibit additional properties |
| Contracts | 19 tracked files: five inputs, five audits, nine reports; all compared to Git object bytes at `f5cd79c` |
| Large files | handlers 4,471; intake 2,173; analysis 606; intent 575 lines, as the brief states |

### Executed behavior matrix

All probes used fictional data and period `3Q26`, amount threshold `10`, and
percentage threshold `2` (CLI percentage units). Chat was driven through actual
`handle_upload` / `handle_message` calls, including period, thresholds, and
currency; it was not a static inspection. Full CLI stdout/stderr, intake data,
and chat replies were captured outside the checkout.

| Input | Strict CLI | Assisted CLI | Chat |
|---|---|---|---|
| Diluted EPS: Budget 0.84, Actual 0.91, no Type | Exit 0; money `$0.07`, 8.3%, Unclassified; excluded from totals | Same | Upload succeeds; after setup asks whether EPS is Revenue or Expense, with skip choices |
| Gross Margin: Budget `41.2%`, Actual `40.6%` | Exit 2, invalid numeric format in Budget | Exit 2, names both unreadable percentage cells | Refuses upload, names both cells and offers another upload / technical detail |
| Extra Consensus beside Budget/Actual: 100/110/105 | Exit 0, uses Budget 100 | Same; Consensus passes through as metadata | Existing Budget path; no earnings choice |
| Consensus/Actual only: 105/110 | Exit 2, required Budget absent | Exit 2, cannot find header with comparison | Upload error, no earnings recognition |
| Two Revenue rows, Segment North/South, 100/110 and 200/210 | Exit 0; duplicate-name warning; totals combine to 300/320 | Same; Segment passes through | Existing path; same duplicate warning in result |
| Extra `3Q26` column beside Budget/Actual | Exit 0, ignores it for analysis | Same; metadata passthrough | Existing Budget path |
| `3Q26` / `3Q25` amount columns only | Exit 2, Budget absent | Exit 2, no recognizable comparison header | Upload error |

Representative exact outputs:

```text
| Diluted EPS | Unclassified | $0.84 | $0.91 | $0.07 | 8.3% | Unclassified |
variance-agent: error: Gross Margin: field 'Budget' has an invalid numeric format: '41.2%'.
Duplicate line-item names detected; confirm these are intentional dimensional rows: Revenue
```

The EPS chat stops with:

```text
Analysis complete, but **1** line item is not yet labeled revenue or expense.

**'Diluted EPS'** is not yet labeled revenue or expense. Should it be:
```

### Differences and resolved interpretations

1. The checkout matches the brief's `f5cd79c`; no rebase of its assumptions was
   necessary. The observed test count matches, but measured time and interpreter
   differ: 37.72 seconds / Python 3.12.14 here versus the brief's 54 seconds /
   Python 3.13.16. Python 3.11 is not installed here. Neither Windows nor the
   other supported Python versions has been executed in this environment.
2. The environment was not prebuilt. A local virtual environment was created
   and the repository's existing pinned development/Excel/PDF/release extras
   installed. This added no project dependency or runtime network behavior.
   Package installation and Git transport are environment setup, not financial
   engine operations. Runner model/reasoning settings cannot be changed or
   independently attested from this checkout; no claim about them is made.
3. The standing rules still reference schema 1.5, two HTML copies, and commit
   `a3ce6bb`. The tree has audit 1.7 and one packaged HTML file. Use the brief's
   explicit overrides, 1.8 for new provenance, and this branch name.
4. Assisted JSON does **not** auto-detect comparison bases: `_read_json_bytes`
   uses Budget unless a basis is explicit, then calls strict selection. CSV and
   Excel take comparison detection. Preserve legacy JSON behavior; the new
   opted-in path will apply consistent new recognition across supported formats.
5. Strict parsing already accepts some header aliases; it is not limited to the
   three exact spellings the input-contract prose suggests. No alias removal.
6. README's signed denominator is wrong; code and financial-rules agree on the
   absolute denominator. Correct the prose in phase 8, not existing arithmetic.
7. `# Est.` and `Est.` both become `est` in intake normalization (and in strict
   key normalization). Preserve raw header identity before new interpretation;
   reject unresolved collisions. Do not infer that `est` means estimator count.
8. The phase-1 prose calls a count absolute cutoff optional, but its later
   materiality rule explicitly requires each kind's threshold. Use the stronger
   rule: require `--count-threshold` when Count occurs, including zero-comparison
   rows; no preset supplies thresholds. Record this in help and docs.
9. New headers are not all globally reserved. Measure/Better are explicit new
   semantic columns; Consensus/Model/Region/Division/Segment and new quarter
   forms require earnings/quant, a new explicit basis, a new mapping, or a
   confirmed chat earnings review. Budget uploads with incidental earnings
   metadata continue through the old path without a new prompt.
10. The brief's 1.8 addition cannot unconditionally change legacy audit defaults
    without breaking its byte promise. Legacy runs still emit exactly 1.7 when
    no schema is selected. Explicit 1.8 is available; new semantics auto-select
    1.8. An explicit older version with new semantics fails before publication.
11. A missing consensus is not zero. Current parsing cannot analyze missing
    amounts. Represent an unavailable basis separately; never substitute zero
    or run fabricated values through the engine. Explicit zero consensus is real;
    new Consensus percentage is null at zero, while the legacy zero/zero rule is
    untouched. The display label for blank and zero is “N/A (No consensus)”;
    `comparison_present` and the amount distinguish them in 1.8.
12. Existing currency renderers use ASCII `-` and no leading `+`. Follow those
    sign conventions for new formats (`-$0.07/sh`, `-60 bps`, `-1,500 units`),
    despite typographic minus/plus signs in the acceptance table. Arithmetic and
    the requested unit suffixes remain exact.
13. Existing source parsing accepts Python floats for legacy compatibility.
    Do not tighten existing callers. The new API rejects float amounts,
    thresholds, and statistics; file numeric text/stored XML is kept exact.
    Existing PDF coordinate floats and workbook layout floats are geometry,
    never financial values.
14. `shape_income_statement` and unit scaling assume additive money. Retained
    EPS/counts must bypass subtotal sign solving; Per Share never receives the
    filing's monetary millions multiplier. Share counts require their own explicit
    scale; ambiguous captions stop for a mapping. Count direction is still a
    user choice; never assume that more or fewer shares is better.
15. The four existing public signatures include both dataclass constructors.
    Preserve them, not only the two functions. New configuration/result wrappers
    hold extensions; no required fields are added to those constructors.
16. The standing rules' all-checks phase gate includes packaging and minimal
    installation, beyond section 2's shorter five-command list. Run the union at
    every phase. Visual QA is not applicable to this documentation-only phase.
    Later changed screens use a browser if available; otherwise run chat/frontend
    tests and disclose the brief's permitted fallback.
17. A same-label/same-segment duplicate can make a comparison-set join ambiguous.
    Keep the legacy duplicate warning in single runs; a set/panel group requiring
    an ambiguous join fails with its key and requests a unique metric identity.
    Do not invent occurrence-based pairings.
18. `test_audit_schema_17.py` explicitly pins `CURRENT_SCHEMA_VERSION == "1.7"`.
    Keep that constant as the legacy default. Make 1.8 selectable and choose it
    explicitly in the extended path; do not update this existing test. The
    existing tests which iterate selectable versions will naturally collect
    more cases after 1.8 is added, without editing their source.
19. Phase 5 describes the square root as the only inexact step, but a general
    sample variance (including Scenario D's `91/120000`) and the final SUE ratio
    need not have finite decimal expansions. Proposed interpretation: compute
    exact Decimal variance numerator/denominator, use the existing explicitly
    rounded ratio policy for their division, then a locally rounded sqrt and
    final ratio; document all three boundaries. Keep Fraction only in test
    oracles. This interpretation needs acceptance in the STOP 1 plan decision
    before phase 5; the phase remains optional at STOP 3.
20. Strict CSV counts data rows/cells; assisted delimited intake includes its
    header in physical row/cell accounting. Thus 100,000 data rows x 10 columns
    fit strict CSV's two caps, while assisted intake permits 99,999 data rows
    at that width. Keep each existing accounting rule; report which path the
    throughput run uses rather than relaxing a cap.

## Design and compatibility boundary

### Routing

Keep the current CLI `_run` legacy branch intact for no new options/columns.
The new branch uses shared capture, validation, analysis, verification, escaping,
and staged outputs. Preset defaults are resolved after parsing with explicit
flags taking precedence. `fpa` is identical to no preset. Header recognition is
controlled by an explicit immutable recognition policy, passed through intake;
do not add global synonyms that change Maya's files.

An explicit Measure/Better column enables only its declared row semantics. It
does not enable unrelated consensus/segment inference. A new basis, earnings or
quant preset, or versioned audience mapping enables the extended header table.
An old mapping remains byte-identical when saved; new mapping fields are omitted
unless chosen. A budget-bearing upload always keeps the existing chat path.
Without Budget, earnings headers can offer an earnings review; actual conversion
waits for confirmation. No inferred direction, rate scale, period interpretation,
or other transformation bypasses confirmation.

### Types and fields (proposed, not implemented)

Use frozen dataclasses and enums; no dependency or dynamic plugin registry.

| Type | Fields and responsibility |
|---|---|
| `MeasureKind` | Currency, Per Share, Percent, Count; Currency is the legacy default |
| `BetterDirection` | Higher, Lower; absent remains a distinct state |
| `AudienceConfig` | New subclass of `AnalysisConfig`, new fields keyword-only: per-share/count/bps Decimal thresholds, percent-values points/fractions, recognition policy. The base constructor stays identical. `dataclasses.replace` must preserve new settings |
| `MetricMetadata` | Stable source row identity, line item, measure, Better and its source, segment, scale decision, source column/row locations; original labels remain data |
| `AnalyzedRow` extension | Defaulted measure, direction, segment, variance-bps and relevant decision fields; legacy construction still works. `variance_dollars` retains its legacy meaning in old audits; new wire records use neutral `variance` |
| `ComparisonMetadata` | Basis, comparison/actual period labels, fiscal/calendar qualifier, guidance low/high/midpoint/position, consensus high/low/estimator count/dispersion and range position; all validated, nullable when absent |
| `ComparisonAnalysis` | One verified `AnalysisResult`, basis metadata, metric metadata, and unavailable comparison rows; no missing amount masquerades as an `AnalyzedRow` |
| `TableAnalysis` | Ordered tuple of `ComparisonAnalysis`, requested preset/layout, recorded inferences, optional Estimate-minus-Consensus facts. No change to `AnalysisResult`'s constructor |
| `LongRow` | Ordered group keys, line item, segment, measure, basis, comparison-present, exact comparison/actual/variance/ratio/bps or null, status, material flag, display label, source SHA-256 |
| `GroupFailure` / `BatchResult` | Ordered group keys and plain reason / successes and failures; no prompts, no clocks, no tracebacks in data output |
| `SurpriseStatistics` (phase 5) | Prior count and periods, window, sample variance/deviation, standardized value or reason, dispersion value or reason, history digest |

`ComparisonBasis` gains Consensus, Estimate, Guidance. `Status` gains nothing.
Beat/Miss/In line are display projections of existing status plus materiality,
only for Consensus. Missing comparisons have no status/display outcome.

`analyze_rows(rows, config)` keeps its signature and is the one single-basis
engine. It accepts the new config subtype when new semantics are requested.
Extract small private measure-aware helpers where needed and use them for both
analysis and boundary verification. Do not create a second variance engine.
Each requested basis passes separately through this engine; combining results
only joins verified facts. Legacy execution must avoid new metadata output and
preserve its classification, warning order, sort order, formatting, and digests.

Currency totals and completeness inspect Currency rows only. Scored noncurrency
rows and Currency rows scored solely by Better stay outside additive totals;
their absence of Revenue/Expense classification must not pollute Currency
completeness. An unclassified Currency row still affects completeness exactly as
before. Revenue/Expense Type wins on Currency; contradicting Better is an error.
Better controls new measures, with Higher visibly defaulted for Per Share only.
Unknown/ambiguous Better is never converted to a revenue label.

### Arithmetic, units, and materiality

All finite values and cutoffs are validated in `financial_context`.
Actual minus comparison and strict amount/percentage materiality remain shared.
Use exact cross-products for percentage cutoff decisions, never a rounded ratio.
Per Share and Count use the current absolute-comparison ratio. Percent is stored
in percentage points; its variance is exactly 100 times the point difference,
with no variance-percent ratio. A percent sign declares points; every bare value
requires the points/fractions setting (even a bare `41.2`, not only `0.412`).

Require per-share, count, or bps threshold for each occurring corresponding kind.
Percent uses bps only. Per Share/Count use absolute OR percent, with the absolute
test only at zero comparison. A typed new measure with missing Better is a
plain-language resolution request in chat and a named row/setting error in CLI.
Required direction/scale confirmations fail a panel group unless a flag/mapping
settles them. Use deterministic formatting that does not round the arithmetic.

Guidance ranges require both finite ends, low <= high, exact midpoint; equality
with either end is Within range. Consensus High/Low must be ordered if both
exist; estimator count is a nonnegative whole number, dispersion nonnegative.
Missing optional values remain missing. Percent consensus dispersion is converted
to the same bps units as its surprise before division. No GAAP/adjusted matching
is inferred.

Recognize new quarter spellings only under the extended policy. Retain original
period text and a parsed calendar/fiscal qualifier. Refuse mixed granularities,
duplicate period identities, and mixed fiscal/calendar columns. Legacy accepted
labels keep “Prior Period (FY2024)” and all other current wording. New quarter
recognition can yield Prior Year / Prior Quarter; it cannot rename old paths.

### Flat segments and combination

Only one scalar segment dimension is supported; competing aliases require an
explicit column choice. Blank segments form a distinct unsegmented bucket.
Scope summary verification by `(segment, LineType)` with the same tolerance and
standalone-summary behavior. Do not automatically sum across segments or combine
an unsegmented consolidated total with segment details. Refuse explicit nested
objects, parent/child dimensions, or requests to infer hierarchy. Slashes in a
label alone are not evidence of hierarchy.

Join comparison sets by validated metric identity `(line_item, segment, measure)`;
normalization for duplicate detection follows current casefold rules. Missing
basis rows are blank groups, not zeros. Estimate-minus-Consensus uses the supplied
amounts, absolute-consensus ratio, or bps for rates; it is not an estimate the
application creates. Comparison order follows the explicit comma-list order.

## Audit 1.8: field-by-field delta

Published schemas 1.0–1.7 are immutable. New groups are siblings rather than
reinterpreted old fields. All nested objects, not only the root, forbid extra
properties. Amounts are fixed-point decimal strings; null is explicit absence.
Below is the proposed 1.8 shape; tests must pin keys, types, and hash coverage.

| Path | Type / semantics |
|---|---|
| `schema_version` | Literal `1.8` |
| Existing 1.7 fields | Same structure/meaning for representable Currency results; extensions cannot silently occupy `variance_dollars` |
| `audience.preset` / `layout` | `fpa`, `earnings`, `quant` / selected report layout |
| `audience.thresholds` | `per_share`, `count`, `bps`: decimal string or null; `percent_values`: points/fractions/null |
| `audience.recognition` | Explicit activation source: preset/new basis/mapping/confirmed chat/Measure or Better column |
| `inferences[]` | `kind`, `row`, `column`, `line_item`, `source_text`, `interpreted_value`, `decision_source`, `confirmed`; bounded strings and exact decimal text; covers basis, kind, Better default, scale, segment, period and retained PDF lines |
| `measure_rows[]` | Every extended non-additive/new-measure row: `row_id`, `line_item`, `segment`, `measure`, `better`, `better_source`, `type`, `comparison_present`, `comparison`, `actual`, `variance`, `variance_percent`, `variance_bps`, `percent_label`, `status`, `material`, `materiality_reason`, `display_label`, `excluded_from_aggregation` |
| `comparison_details[]` | Keyed by `row_id`; `guidance_low`, `guidance_high`, `guidance_midpoint`, `guidance_position`, `consensus_low`, `consensus_high`, `estimator_count`, `dispersion`, `consensus_range_position`; exact values or null |
| `period_interpretation` | `actual_label`, `comparison_label`, `calendar_kind`, `granularity`, `relationship`; no reinterpretation of existing `comparison.label` |
| `segments[]` | Segment key, Currency completeness and revenue/expense totals, scoped summary verifications; do not synthesize consolidated totals |
| `comparisons[]` | Empty for a single basis; for a set, ordered complete standalone 1.8 single-basis records with their own source/configuration identities, payload digest, and empty inner comparisons; schema references a nonrecursive single-record definition |
| `estimate_vs_consensus[]` | Metric key, both supplied amounts, exact difference/ratio/bps, or null with an unavailable reason |
| `statistics[]` (phase 5) | Metric key, history SHA-256, ordered prior periods, prior count, window, sample variance/deviation, standardized surprise/reason, dispersion surprise/reason |
| `provenance.configuration_sha256` | Includes effective new thresholds, scale, recognition, mapping choices, basis order, group keys and optional statistic configuration |
| `analysis_fingerprint` | Includes all new derived rows/metadata, not only material rows, with a documented version-specific canonical identity object |
| `payload_sha256` | Existing public-record-without-self recipe; every new field is covered |

New features selecting 1.8 must not be omitted to satisfy an older schema.
Each child comparison can be validated and recomputed alone. Unavailable rows
carry null amount-derived facts and no Beat/Miss label. Raw source dictionaries
are still excluded. Schema enums include new bases only in 1.8. The final delta
table in `docs/audit-contract.md` will document every implemented key; dropped
phase-5 fields remain absent from the shipped schema rather than speculative.

The wrapper audit builder handles sets, while `build_audit_record` keeps its
signature and dispatches extended single results to 1.8. Legacy results default
to 1.7 even after 1.8 is selectable. Validate refusal before staging any output.

## API, panel, and output contracts

Proposed public functions in `variance_agent.api`, exported beside the existing
four names:

```python
analyze_table(rows: list[dict[str, object]], config: AnalysisConfig, *,
              options: AudienceOptions | None = None) -> TableAnalysis
analyze_file(path: str | Path, config: AnalysisConfig, *,
             options: AudienceOptions | None = None) -> TableAnalysis
analyze_panel(rows: list[dict[str, object]], *, group_by: tuple[str, ...],
              options: PanelOptions) -> BatchResult
```

`AudienceOptions` supplies comparison tuple, thresholds, percent scale, preset,
sheet, mapping and optional history. It is distinct from the internal engine's
validated config subtype; only the validated effective choices reach analysis.
`PanelOptions` supplies those options plus common thresholds/currency and an
optional non-group period. It cannot inject a file digest into in-memory rows.
`analyze_file` owns bounded capture and truthful SHA-256. `analyze_table` and
`analyze_panel` record source digest null for pure in-memory input. The CLI captures
one bounded panel and attaches that captured-file digest to its output rows.
Public signatures are pinned exactly before implementation, including all four
existing signatures. Minor versions may add optional capabilities/new exports;
not change an existing signature, existing default semantics, old schema, column
meaning, or deterministic ordering without an explicit versioned migration.

`--group-by` enables panel mode. If Period is a key, each group's Period supplies
its config and `--period` is refused. Otherwise `--period` is required. Missing
keys/unsupported structure/capture limits are whole-input exit-2 errors. An
unreadable amount or unresolved inference within a well-keyed group produces one
failure record and does not stop other groups. Any group failure produces exit 3;
all-success produces exit 0. No prompt or waiting for stdin is allowed.
Require `--errors-output` in panel mode so failures always have a destination;
the CLI names that flag before work if absent. Global path/preflight failures
leave outputs unchanged. Successful groups and errors are staged together with
existing per-file atomicity, not a new multi-file transaction guarantee.

Long output column order is group keys in declared order, then line item,
segment, measure, basis, comparison-present, comparison, actual, variance,
variance-percent, variance-bps, status, material, display-label, source-SHA256;
optional statistic columns are appended only under their explicit option.
Group order is lexicographic over original key text (no numeric ticker guessing),
within group input metric order, then explicit basis order. JSONL uses fixed
key order, UTF-8, one record and LF per line, no timestamps; CSV uses the same
stable row order and LF. Every financial number is an exact decimal string.
CSV null is empty; JSONL null is null; booleans have documented representations.

CSV formula policy: prefix untrusted text beginning `=`, `+`, `-` or `@` with an
apostrophe (also after leading whitespace/control characters); neutralize display
controls. Numeric columns are exempt so negative amounts remain exact numbers.
JSONL retains original text as data and documents the CSV safety transformation.
The transformation is deterministic and tested; source SHA stays that of input.

Keep 100,000-row/1,000,000-cell and 32-MiB limits for the full panel before
grouping, and equivalent limits for history/other auxiliary data. Do not evade
limits by splitting an oversized captured table into valid-looking groups.
For the planned throughput measurement generate a fictional 10-column,
100,000-data-row CSV panel (Ticker, Period, Line Item, Type, Consensus, Actual,
Measure, Better, Segment, Currency): exactly 1,000,000 data cells, with compact
values under 32 MiB. An 11-column panel is limited to 90,909 data rows. Verify
the parser's actual header-cell accounting before generation; if headers count,
reduce data rows accordingly and report the real admitted maximum. Time the
complete CLI read/analyze/write operation with a monotonic timer, record hardware,
Python and bytes, then optimize only if measured time exceeds 60 seconds.

## Phase-by-phase edit and test plan

In this section source paths are relative to `src/variance_agent/`. Every new
fixture goes under `tests/fixtures/multi_audience/` with a README identifying
fictional companies and `.FAKE` tickers. Existing tests remain unedited; new tests
live in new files. Every phase ends with the union verification gate below and a
local commit naming its reader(s). New phase-specific docs are written alongside
behavior, not deferred if needed to understand new arithmetic.

### Phase 0 — Maya, Priya, Dan, Wei: baseline and plan

- Edit only this plan. Record source inspection, probes, test baseline, proposed
  interfaces, schema delta, phase files, risks, and stop conditions.
- Exit: all baseline verification commands pass, contract bytes unchanged, local
  documentation commit; **STOP 1**. No feature code shipped.

### Phase 1 — Priya: kinds, direction, exact unit-aware analysis

- Modify `models.py`, `analysis.py`, `numeric.py` only if a shared arithmetic
  helper is needed, `parsing.py`, `intake.py`, `mapping.py`, `cli.py`, `report.py`,
  `audit.py`, `xlsx.py`, and the minimum chat direction/scale state in
  `chat/{session,handlers,responses}.py`. Add `measures.py` for the new vocabulary,
  validation and formatting; `audience.py` for opt-in options/metadata shared by
  later phases. Add `schemas/audit-1.8.schema.json` now for new provenance.
- Update `docs/{input-contract,financial-rules,audit-contract}.md`; do not publish
  a 1.8 schema shape and then mutate it as though already released. Until phase 8
  it is one unreleased working schema.
- Test first: `test_multi_audience_measures.py`,
  `test_multi_audience_materiality.py`, `test_multi_audience_audit.py`,
  `test_multi_audience_compatibility.py`, `test_multi_audience_chat.py`.
  Pin all legacy signatures, default audit bytes and sample XLSX bytes. Pin exact
  equality / immediately below / immediately above all three new thresholds;
  Fraction-oracle bps; noncurrency exclusions; Currency Type conflicts; Higher
  default inference; Percent/Count missing Better; points/fractions refusals and
  confirmation; hostile labels and float rejection for the new path.
- Proposed aliases: Currency = currency/money; Per Share = per share/per-share/
  per_share/eps; Percent = percent/percentage/rate; Count = count/units.
  No kind is inferred from a label except explicitly documented earnings intake
  proposals confirmed by the user. Unknown Measure errors with the row name.
- Exit: old contracts/tests unchanged, new kind arithmetic and CLI/chat asks
  verified, all checks green; commit for Priya.

### Phase 2 — Priya and Dan: bases, quarters, comparison sets

- Modify `models.py`, `comparison.py`, `audience.py`, `analysis.py`, `intake.py`,
  `parsing.py`, `mapping.py`, `cli.py`, `report.py`, `audit.py`, `xlsx.py`,
  `chat/{handlers,intent,session,responses}.py`, and unreleased 1.8 schema.
  Add `comparisons.py` only for set orchestration/join and range metadata; use
  the single-basis engine for every actual comparison.
- Update the three contracts/rules documents. Extend only new test files:
  `test_multi_audience_comparisons.py`, `test_multi_audience_periods.py`,
  `test_multi_audience_sets.py`, plus phase-1 compatibility/audit/chat tests.
- Test first Scenario A in full, Scenario B midpoint/loss, low/end/high range
  straddles with Fraction midpoint/position oracle, explicit zero vs missing
  consensus, nonmaterial unfavorable In line, only-Consensus vocabulary,
  estimator-count raw-header distinction, ambiguous Est., negative consensus,
  fiscal/calendar mixing, legacy period wording, missing-basis joins,
  duplicate-join refusal and standalone revalidation of each child audit.
- Add Comparisons sheet only for a set. In Markdown emit one combined table;
  no repeated executive narratives. Estimate-minus-Consensus stays descriptive.
- Exit: A and B values all verified, every old assertion untouched; green commit
  naming Priya and Dan.

### Phase 3 — Priya and Dan: flat segments

- Modify `audience.py`, `models.py`, `analysis.py`, `intake.py`, `mapping.py`,
  `comparisons.py`, `report.py`, `xlsx.py`, `audit.py`, `chat/handlers.py`, 1.8
  schema, and `docs/{input-contract,financial-rules,audit-contract}.md`.
- New `test_multi_audience_segments.py`: same name/different segment has no
  duplicate warning; same name/same segment still warns; two segments each with
  one reconciled summary; tolerance straddles; no cross-segment reconciliation;
  nested dimension refusal; empty segment; escaped segment labels; legacy
  Region/Division columns still inert without opt-in.
- Exit: scoped reconciliation/duplicate tests and byte contracts, green commit.

### Phase 4 — Wei: API, isolated batches, stable long output

- Add `api.py`, `panel.py`, `long_output.py`, `docs/api.md`. Modify
  `__init__.py`, `audience.py`, `cli.py`, `parsing.py` only for bounded metadata
  capture, `output.py` only to extend path checks/staging reuse if needed,
  `audit.py`, 1.8 schema, `README.md`, and input/audit docs.
- New `test_multi_audience_api.py`, `test_multi_audience_panel.py`,
  `test_multi_audience_long_output.py`. Test Scenario C with six groups, exactly
  one malformed group, exactly one error row containing its keys and `TBD`,
  exit 3, five successful groups, two byte-identical complete reruns. Also pin
  exact signatures, Period-key rules, flags/mapping-only resolution, malformed
  keys, all-failed/empty batch behavior, caps on whole input, source-byte hash,
  same-path/symlink/hardlink collisions, staged failure preservation, and CSV
  formula text with negative-number exemption. Add numeric-length/text/nesting
  limit cases for new auxiliary captures.
- Generate/time the maximum admissible fictional panel outside tracked fixtures;
  keep the generator instructions and measured output in the final report.
- Exit: API/Scenario C/throughput measured and all checks green; commit for Wei.
  **STOP 3:** report actual elapsed work, remaining phases, and whether optional
  history/PDF work is feasible. No precommitment to a time estimate.

### Phase 5 — Wei: descriptive surprise statistics (optional at STOP 3)

- Add `surprise.py`; modify `audience.py`, `api.py`, `panel.py`, `cli.py`,
  `audit.py`, `report.py`, `long_output.py`, 1.8 schema and financial/input/API
  docs. No statistical runtime library.
- New `test_multi_audience_surprise.py`: Scenario D windows 8/4; file-order
  permutation; exclude current/future quarters; keyed entity+metric histories;
  duplicate period refusal; fiscal/granularity ambiguity; minimum 3/4; window 3
  exit 2; zero variance; missing/zero dispersion; correct rate units.
- Compute demeaned sample variance with exact Decimal sums/cross-products, then
  round its Decimal representation under an explicitly documented ratio policy
  only when nonterminating. Square root uses `Decimal.sqrt` with Inexact disabled
  locally and 50-digit half-even context. Final ratios use the existing permitted
  ratio rounding. Do not disable Inexact around amount arithmetic.
- Oracle brackets the exact Fraction variance using one last-significant-digit
  unit of the deviation; include terminating-square cases where equality is
  expected instead of a strict inequality. No predictive wording.
- Exit: D and precision boundaries green; commit for Wei, or record dropped.

### Phase 6 — Maya and Priya: complete presets, earnings display, chat

- Modify `cli.py`, `audience.py`, `report.py`, `xlsx.py`,
  `chat/{handlers,intent,knowledge,session,responses}.py`; change
  `static/{chat.html,chat.js,chat.css}` only if generic tables/chips cannot express
  the new review. Add `earnings.py` for the earnings layout if needed rather than
  enlarging the 4,471-line handler with report-building code.
- Update README/help and docs to list preset defaults. fpa = old path;
  earnings = new headers/layout/Earnings sheet/per-share on; quant = new headers,
  long output required, no Markdown unless `-o`. Provide explicit layout and
  per-share on/off overrides so explicit options win. No threshold default.
- New `test_multi_audience_presets.py`, extend new chat tests and add
  `test_multi_audience_routing.py`. Full Scenario B chat from upload through
  guidance confirmation, thresholds, report and download. All six knowledge
  topics and new phrases get route tests; explicitly pin “beat the plan” and
  budget-bearing metadata uploads to their old routes.
- Lead with user-declared/confirmed headline metrics, then guidance, prior year,
  segments, remaining KPIs. Unsupported requests remain descriptive refusals;
  never generate investment calls or estimates.
- Exit: existing chat tests unedited, browser 1280/375 or disclosed permitted
  chat/frontend fallback, green commit naming Maya and Priya.

### Phase 7 — Priya: per-share filing intake (optional at STOP 3)

- Modify `pdf_tables.py`, `statement_shape.py`, `intake.py`, `audience.py`,
  `cli.py`, `chat/handlers.py`, 1.8 schema, input/audit docs. Add the opt-in flag
  through the full call chain, preserving the exact old omission note when off.
- Modify only the existing fixture builder
  `tests/fixtures/realworld/build_pdf_fixtures.py` to append a fictional filing
  (no edits to existing outputs), and add its new PDF with a fictional README
  entry. Add `test_multi_audience_pdf.py` for exact basic/diluted EPS, Count
  retention, independent scale, exposed transformations, off-mode bytes,
  missing direction/threshold requests, and summary-shaping isolation.
- All existing PDF tests remain unedited. If the builder rerenders old binary
  fixtures, restore those generated changes; never commit them.
- Exit: exact fictional filing EPS/count behavior and existing PDF tests green;
  commit for Priya, or record dropped.

### Phase 8 — all readers: documentation and full evidence

- Modify `README.md`, `CHANGELOG.md`, `docs/{financial-rules,input-contract,
  audit-contract,api,roadmap}.md`, finalize the unreleased 1.8 schema; write
  `docs/MULTI_AUDIENCE_2026-10.md`. Update this plan's decisions/phase status.
- Record the narrow scope decision in roadmap. Fix only the stale denominator
  prose. Document vendor mapping/GAAP-adjusted/fiscal-period ambiguities, batch
  exit 3, scale, formula text, statistical rounding and deterministic ordering.
- Execute each reader's fixture command/chat flow and paste its actual output,
  before/after test counts, contract byte comparison, phase commit IDs, full
  check outputs, throughput machine/time and measured-vs-estimated labels.
- Rebuild/check wheel and sdist and separately install/check both artifacts and
  a minimal non-editable package with neither optional input dependency.
- Disclose untested real vendor exports, real filings, hosted deployment,
  Windows, and interpreter variants unless actually executed.
- Exit: all required evidence, green commit, then **STOP 4** before push/merge.

## Risks and decision gates

The main risk is accidental activation on Maya's metadata, followed by unit
scaling, incomplete totals, and record hashing. Tests must prove that new policy
defaults are inert, that Percent never receives money formatting/relative percent,
that noncurrency rows never enter money totals, and that every extended fact is
reverified and covered by an identity hash.

The new Python type layout and 1.8 schema are design choices for review at STOP 1.
They are not shipped APIs. Tighten a field name in this plan before its first
implementation, and preserve all four existing signatures. The schema must make
single vs set constraints explicit; a comparison-set root cannot claim a single
consolidated financial total across bases. Error files are required in panel mode
as proposed above; if the owner prefers an automatic sidecar path, decide before
pinning the phase-4 public CLI contract.

No feature currently appears to require a forbidden dependency or remote call.
If that changes, stop immediately and name the feature/constraint. If any old test
needs editing or any contract byte would change, **STOP 2**, show the diff and
reason, and do not update the expected value. Never silently drop optional phases
or exceed input caps to improve throughput. No subagents are needed for these
sequential phase gates.

## Phase-0 verification evidence

All figures in this section are **measured**. Full command output is appended
below by the phase-0 verification capture. Dependency install used the existing
`requirements-typecheck.txt` pins and `.[dev,excel,pdf,release]`. No code/tests
changed. Initial verification included the complete README block and the CI
minimal non-editable installation check. Only local Linux/Python 3.12 was run.

Legacy sample regression hashes (sample CSV, Q3 2026, 10000 / 0.05 API ratio,
no file-provenance arguments to the audit builder):

```text
report 63f5d2d61de895f715d8270d948fb1b6d54208fa582f461c95a4e49b637d8587
audit  3420b6d4e77dab921dfb683feb7241f8cece1c298d86c2c9f01f951d2c829c7c
xlsx   11db3182fb2f5b377e7973016e9b51fc0780e96fd80d6b3471e1c6633025ee43
```

STOP 1: present this plan and Differences to the owner and wait. The attachment
explicitly says: “After Phase 0. Present the plan and its ‘Differences’ list.”

### Captured commands and outputs
All following commands completed with exit 0. Empty successful output is explicitly identified.

**environment**

```text
$ .venv/bin/python (platform.platform(), platform.python_version(), platform.machine() captured in the baseline probe)
Linux-6.18.55-x86_64-with-glibc2.39
Python 3.12.14
x86_64
```

**pytest**

```text
$ .venv/bin/python -m pytest -q
........................................................................ [  4%]
........................................................................ [  8%]
........................................................................ [ 12%]
........................................................................ [ 16%]
........................................................................ [ 20%]
........................................................................ [ 24%]
........................................................................ [ 28%]
........................................................................ [ 32%]
........................................................................ [ 36%]
........................................................................ [ 40%]
........................................................................ [ 44%]
........................................................................ [ 48%]
........................................................................ [ 52%]
........................................................................ [ 56%]
........................................................................ [ 60%]
........................................................................ [ 65%]
........................................................................ [ 69%]
........................................................................ [ 73%]
........................................................................ [ 77%]
........................................................................ [ 81%]
........................................................................ [ 85%]
........................................................................ [ 89%]
........................................................................ [ 93%]
........................................................................ [ 97%]
............................................                             [100%]
1772 passed in 37.72s
```

**ruff**

```text
$ .venv/bin/python -m ruff check .
All checks passed!
```

**mypy**

```text
$ .venv/bin/python -m mypy --strict src/variance_agent scripts deterministic_conditioning
Success: no issues found in 51 source files
```

**compileall**

```text
$ .venv/bin/python -m compileall -q src tests scripts deterministic_conditioning
(no output; exit 0)
```

**dependency consistency**

```text
$ .venv/bin/python -m pip check
No broken requirements found.
```

**build**

```text
$ .venv/bin/python -m build --outdir dist
* Creating isolated environment: venv+pip...
* Installing packages in isolated environment:
  - hatchling==1.32.4
* Getting build dependencies for sdist...
* Installed build dependency versions:
  - hatchling==1.32.4
* Building sdist...
* Building wheel from sdist
* Creating isolated environment: venv+pip...
* Installing packages in isolated environment:
  - hatchling==1.32.4
* Getting build dependencies for wheel...
* Installed build dependency versions:
  - hatchling==1.32.4
* Building wheel...
Successfully built variance_analysis_agent-0.3.0.tar.gz and variance_analysis_agent-0.3.0-py3-none-any.whl
```

**twine**

```text
$ .venv/bin/python -m twine check dist/*
Checking dist/variance_analysis_agent-0.3.0-py3-none-any.whl: PASSED
Checking dist/variance_analysis_agent-0.3.0.tar.gz: PASSED
```

**distribution**

```text
$ .venv/bin/python scripts/check_distribution.py dist
Wheel/sdist contents, license, Python support, and entry point verified
```

**minimal installation**

```text
$ python -m venv ../phase0-minimal
../phase0-minimal/bin/python -m pip install .
Processing /workspace/scratch/61f04cd678fb/Variance-Analysis-Agent
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Getting requirements to build wheel: started
  Getting requirements to build wheel: finished with status 'done'
  Preparing metadata (pyproject.toml): started
  Preparing metadata (pyproject.toml): finished with status 'done'
Building wheels for collected packages: variance-analysis-agent
  Building wheel for variance-analysis-agent (pyproject.toml): started
  Building wheel for variance-analysis-agent (pyproject.toml): finished with status 'done'
  Created wheel for variance-analysis-agent: filename=variance_analysis_agent-0.3.0-py3-none-any.whl size=245932 sha256=6aee4f5043791168967659d6f79bf9fdcf5ba1ae549b3c9ca47712a40411070c
  Stored in directory: /root/.cache/pip/wheels/7f/8e/b5/ec311c6462b75150cf81647260a56e29faa29938cffbd3f92d
Successfully built variance-analysis-agent
Installing collected packages: variance-analysis-agent
Successfully installed variance-analysis-agent-0.3.0

[notice] A new release of pip is available: 25.0.1 -> 26.2.2
[notice] To update, run: python -m pip install --upgrade pip
```

**minimal smoke**

```text
$ ../phase0-minimal/bin/python scripts/check_installation.py --without-excel --without-pdf
Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified
```

**minimal consistency**

```text
$ ../phase0-minimal/bin/python -m pip check
No broken requirements found.
```

**contracts**

```text
$ .venv/bin/python (for each path: assert Path(path).read_bytes() == subprocess.check_output(["git", "show", "f5cd79c:" + path]))
19 contract files match f5cd79c byte for byte
```

### Existing public signatures to preserve

```text
AnalysisConfig (period: 'str', dollar_threshold: 'Decimal', percent_threshold: 'Decimal', type_map: 'dict[str, LineType]' = <factory>, currency: 'str' = 'USD', comparison_basis: 'ComparisonBasis' = <ComparisonBasis.BUDGET: 'budget'>, comparison_label: 'str | None' = None) -> None
AnalysisResult (config: 'AnalysisConfig', rows: 'tuple[AnalyzedRow, ...]', material_rows: 'tuple[AnalyzedRow, ...]', revenue: 'Aggregate', expenses: 'Aggregate', warnings: 'tuple[str, ...]') -> None
analyze_rows (rows: 'list[dict[str, object]]', config: 'AnalysisConfig') -> 'AnalysisResult'
build_audit_record (result: 'AnalysisResult', *, source_name: 'str | None' = None, source_sha256: 'str | None' = None, schema_version: 'str | None' = None, type_map_sha256: 'str | None' = None, source_worksheet: 'str | None' = None, transformations: 'Mapping[str, object] | None' = None, source_document: 'Mapping[str, object] | None' = None) -> 'JSONObject'
```

### Baseline probe reproduction

Each CLI probe was run twice through `variance_agent.cli.main`, once without
extra options and once with `--assisted`, capturing stdout, stderr and SystemExit.
The input variants and exact values are in the behavior matrix above. The common
arguments were `--period 3Q26 --dollar-threshold 10 --percent-threshold 2`.
Chat uploads used the same bytes and replies `Looks right` when requested,
`3Q26`, `$10 or 2%`, `USD`; the EPS flow was intentionally left at its
classification question. New quarter spellings were also called directly through
`parse_period_label`, all returning None. `Q3 2026` and `Q3-26` both returned
`(2026, "quarter", 3)`. These are baseline observations, not new fixtures or tests.

### Verification boundary

The baseline commands above ran before the documentation-only plan was added.
No production code, tests, schemas or fixtures changed afterward. This plan was
reviewed with `git diff --check` before its local commit. A one-off signature probe
initially used the host interpreter and failed to import the package; rerunning
it with the installed `.venv/bin/python` succeeded. This was an interpreter
selection error, not a failed repository check. No other interpreter/OS/browser
result is claimed. The scratch evidence is reproducible from this document;
future implementation evidence belongs in the required final report.

## Implementation record — Phase 1

STOP 1 approved by the owner with “continue”. Add `tests/test_multi_audience_cli.py`
to phase 1 for real CLI/intake/workbook boundary regressions. Phase-1 schema uses
closed `audience`, `inferences`, `measure_rows` groups first; later unreleased
phases extend it before final publication. No published schema changes.

Phase 1 also adds `tests/test_multi_audience_mapping.py` for confirmed scale,
direction and threshold replay, and malformed mapping rejection.

Phase 1 adds `src/variance_agent/static/chat.js` to its files: the existing frontend
contract requires a phase label and placeholder for the new measure-options state.
The failing existing test is preserved; add only the two state-map entries.

### Phase 1 completed — Priya, with Maya compatibility

Implemented explicit kinds/Better, required cutoffs, exact bps, percentage scale,
noncurrency isolation, typed opt-in config, new unit-aware report/workbook,
closed unreleased audit 1.8, visible inferences, chat questions, and saved mapping
replay. Original public signatures and legacy sample report/workbook hashes are
pinned. Existing audit default constant remains 1.7. No dependency added.

New tests were observed failing before implementation: missing audience module;
unit-aware CLI/schema/workbook boundaries; direction/scale chat questions;
mapping replay; forged direction; follow-up table units; malformed mapping
threshold error. All were subsequently observed passing. A full regression caught
the new session phase missing from frontend maps; two JS entries fixed the cause
without editing the existing test.

Local Chromium could not launch: Playwright's browser executable is absent.
Used the brief's permitted chat/frontend-test fallback; 1280/375 screenshots were
not taken. No hosted, Windows, or other-interpreter result is claimed.

Measured final test result: **1,815 passed in 37.28s**, versus 1,772 baseline.
Every pre-existing test/fixture and schema 1.0–1.7 was byte-compared to the base Git
objects and is unchanged. No STOP 2 condition arose. Final verification outputs:

**pytest**

```text
........................................................................ [  3%]
........................................................................ [  7%]
........................................................................ [ 11%]
........................................................................ [ 15%]
........................................................................ [ 19%]
........................................................................ [ 23%]
........................................................................ [ 27%]
........................................................................ [ 31%]
........................................................................ [ 35%]
........................................................................ [ 39%]
........................................................................ [ 43%]
...........................................................----------------------------------------
Exception occurred during processing of request from ('127.0.0.1', 45806)
............. [ 47%]
........................................................................ [ 51%]
........................................................................ [ 55%]
........................................................................ [ 59%]
........................................................................ [ 63%]
........................................................................ [ 67%]
........................................................................ [ 71%]
........................................................................ [ 75%]
........................................................................ [ 79%]
........................................................................ [ 83%]
........................................................................ [ 87%]
........................................................................ [ 91%]
........................................................................ [ 95%]
........................................................................ [ 99%]
...............                                                          [100%]
1815 passed in 37.28s
```

**ruff**

```text
All checks passed!
```

**strict mypy**

```text
Success: no issues found in 53 source files
```

**compileall**

```text
(no output; exit 0)
```

**pip check**

```text
No broken requirements found.
```

**build**

```text
* Creating isolated environment: venv+pip...
* Installing packages in isolated environment:
  - hatchling==1.32.4
* Getting build dependencies for sdist...
* Installed build dependency versions:
  - hatchling==1.32.4
* Building sdist...
* Building wheel from sdist
* Creating isolated environment: venv+pip...
* Installing packages in isolated environment:
  - hatchling==1.32.4
* Getting build dependencies for wheel...
* Installed build dependency versions:
  - hatchling==1.32.4
* Building wheel...
Successfully built variance_analysis_agent-0.3.0.tar.gz and variance_analysis_agent-0.3.0-py3-none-any.whl
```

**twine**

```text
Checking dist/variance_analysis_agent-0.3.0-py3-none-any.whl: PASSED
Checking dist/variance_analysis_agent-0.3.0.tar.gz: PASSED
```

**distribution**

```text
Wheel/sdist contents, license, Python support, and entry point verified
```

**minimal install smoke**

```text
Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified
```

**minimal pip check**

```text
No broken requirements found.
```

The compile/type/lint/pip commands were also rerun successfully after the final
JS phase-map fix, as shown in the execution transcript. This commit is local;
no push/merge is authorized. Next: phase 2 (Priya and Dan).

## STOP 2 — legacy schema test enumerates future bases

Phase 1 committed locally as `188d26a`, with 1,815 passing tests. Before phase 2
implementation, source inspection found `tests/test_audit_schema_16.py`:

```python
@pytest.mark.parametrize("basis", list(ComparisonBasis))
def test_16_records_comparison_and_validates(basis: ComparisonBasis) -> None:
    record = build_audit_record(analyze_rows(ROWS, cfg(basis, label="FY2024")), schema_version="1.6")
    assert record["comparison"] == {"basis": basis.value, "label": "FY2024"}
    _validator("1.6").validate(record)
```

Adding the required enum members automatically expands this test to demand that
schema 1.6 accepts Consensus/Estimate/Guidance. The unchanged published schema
permits only budget/forecast/prior_period. The new bases require 1.8 under the
approved design; accepting or downgrading them to 1.6 would violate the contract.
Thus this existing test needs its parameter scope pinned to the original bases.
This is a prospective compatibility gate, not a claim that phase-2 code or an
existing test has already failed. No phase-2 implementation has been written.

Recommended exact exception (not applied):

```diff
-@pytest.mark.parametrize("basis", list(ComparisonBasis))
+@pytest.mark.parametrize("basis", (B, F, P))
 def test_16_records_comparison_and_validates(basis: ComparisonBasis) -> None:
```

All three constants are already imported by that test. Every existing assertion
and legacy schema stays unchanged; all three existing cases are retained. Add
new tests that require 1.8 for the three added bases and reject older versions.
Do not change enum iteration behavior to conceal the new bases.

Measured schema-only reproduction using an actual valid 1.6 record, changing only
`comparison.basis` and validating against the unchanged published schema:

```text
consensus: schema 1.6 rejects comparison.basis; allowed: budget, forecast, prior_period
estimate: schema 1.6 rejects comparison.basis; allowed: budget, forecast, prior_period
guidance: schema 1.6 rejects comparison.basis; allowed: budget, forecast, prior_period
```

The instruction requiring this pause is the owner's attachment, section 5:
“Whenever a change would alter a byte of a contract fixture or require editing
an existing test. Show the diff and the reason.”

Awaiting owner approval for only the one-line parameter-scope exception above.
All existing tests/fixtures/schemas remain byte-identical to the baseline; the
working tree has no feature changes after phase 1. Nothing has been pushed.
