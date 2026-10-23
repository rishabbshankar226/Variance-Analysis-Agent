# Audit and report contracts

The audit is deterministic analysis output. Source-derived names, labels, periods,
and warnings are untrusted data, including when carried inside valid JSON.
The trust flags declare intended use; they do not enforce model behavior.

`schemas/audit-1.0.schema.json` defines the existing wire format using JSON Schema
Draft 2020-12. Consumers must select a schema using `schema_version` and reject
unknown versions. Financial values are finite fixed-point decimal strings, not
JSON floats. A zero budget with nonzero actual has a null percentage and an
explicit unbudgeted label (Forecast and Prior Period runs use "not in forecast" and "new this period"). Schema validation checks structure; deterministic
Python remains responsible for reconciliation and arithmetic.
Report and audit builders reverify financial row, aggregate, materiality, and
supported-component identities, including manually constructed Python results.
The generic JSON writer is a serializer, not an external-record schema validator;
consumers must validate received records against the exact published schema.

Version 1.1 adds the explicit reporting `currency` (USD, EUR, or GBP).
Version 1.2 adds policy/configuration provenance and a recomputable `payload_sha256`.
Version 1.3 adds classification/materiality decision sources,
summary verification, driver reconciliation diagnostics, and completeness basis.
Version 1.4 records the selected worksheet in `source.worksheet`
(null for CSV/JSON or Python callers without that metadata).
Version 1.5 adds `transformations` (assisted-intake header row, column mapping, ignored columns, sign flips, unit scale, zero reads, excluded totals, period selection, classification rules, mapping-file digest).
`transformations` records what intake applied to the file, on `--assisted` and `--mapping` runs alike: the header row and column mapping it found, the ignored columns, the unit scale applied (from the title, or from a mapping when the file is silent), the revenue line items whose sign it flipped, every exclusion made (detected subtotals plus any a mapping names), and `zero_reads.accounting_dashes` (dashes read as 0). A mapping adds only its period selection, classification rules and digest. Trailing or typographic minus signs read as negative and text-encoding conversions appear in the intake summary (chat) and on stderr (CLI) but have no audit field; schema 1.7 has none, and adding one needs a new schema version. `materiality.percent_threshold` holds a ratio (0.05 for 5%), while the CLI takes a percent number (5).
Version 1.6 adds `comparison: {basis, label}` (`basis` is `budget`, `forecast`, or `prior_period`; `label` is the display text or null), included in the configuration identity and therefore the analysis fingerprint. The `budget` keys keep their names and hold the comparison amount.
Schemas 1.0-1.5 record that amount as a budget, so they are refused for Forecast and Prior Period runs: "Audit schema {version} records the comparison amount as a budget; use --audit-schema-version 1.6 for forecast or prior-period comparisons." Budget runs may still select any version.
Version 1.7 is the default and adds `source.document`: null for every input except a PDF, where it is `{kind: "pdf", statement, pages, reader_notes}`. `statement` is the statement read (also in `source.worksheet`), `pages` its page numbers, and `reader_notes` every adjustment the reader made: which header became which period, rows left out (per-share and share counts), repeated lines renamed, subtotals left out, each line's revenue or expense label and every sign flip. It is part of the record and therefore the analysis fingerprint. Statement subtotals also appear in `transformations.excluded_totals`.
Schemas 1.0-1.6 cannot hold that record, so PDF input refuses them: "Audit schema {version} cannot record how a PDF statement was read; use --audit-schema-version 1.7 for PDF input."
See [financial rules](financial-rules.md). Use `--audit-schema-version 1.0` or the Python `schema_version="1.0"`
keyword for a legacy USD consumer. Version 1.0 cannot represent another currency
and rejects non-USD runs. Its archived records and fingerprint recipe are retained.

Published versions are immutable. Future shape changes receive separate schemas;
archived records remain valid against their original version.

The existing `analysis_fingerprint` hashes canonical JSON containing both the
public record before its fingerprint is added and derived facts for every analyzed
row. Nonmaterial derived rows are not included in the public payload. Consequently,
the fingerprint cannot be recomputed from that payload alone. Neither this
fingerprint nor a source SHA-256 authenticates authorship or proves correctness.

## Provenance and public integrity (1.2)

The CLI captures each input and optional type map once, then hashes and parses
those exact bytes. Captures are currently in memory; memory use scales with
source size and the analyzed rows. Capture during an in-place producer write is
not a filesystem snapshot. Producers should atomically publish completed files.
The Python `load_file(path)` API remains a wrapper around captured-byte parsing.

`provenance` contains the tool version, numeric/classification/driver policy IDs,
a hash of effective configuration, optional exact type-map byte digest, and
identity recipe names. Policy IDs describe semantics and must change when those
semantics change; tool version identifies the release, not a unique source commit.
Pure Python callers supplying rows cannot claim file identity unless they supply
the digest of the exact bytes they parsed. Missing file digests remain null.
The current numeric policy is decimal-50-half-even-e999-v2; the driver policy is
quantity-rate-reconcile-residual-v2. The latter exposes accepted model residuals
as Unexplained residual components instead of claiming an incomplete bridge is
fully explained. Existing schema shapes remain unchanged.

`configuration_sha256` hashes the effective period, decimal threshold strings,
currency, and validated type map using the canonicalization below. Maps with
different key order but identical content have identical configuration identity.
Version 1.4 also includes the selected worksheet, so identical rows on different
worksheets have distinct input-selection identity.

`payload_sha256` uses recipe `public-record-without-payload-sha256-v1`: remove only
the top-level `payload_sha256` field; JSON-serialize the remaining record with
sorted object keys, separators `(',', ':')`, `ensure_ascii=False`,
`allow_nan=False`, and UTF-8 encoding; SHA-256 the bytes. No trailing newline is
included. `analysis_fingerprint` is retained inside this public digest.
Use Python `variance_agent.audit.payload_sha256(record)` after schema validation.
This provides change detection, not origin authentication.

`analysis_fingerprint` uses `record-and-derived-rows-v1`: the same canonicalization
over `{record: record-before-both-digests, analyzed_rows: all-derived-row-records}`.
Versions 1.0/1.1/1.2/1.3 retain their original record shape and fingerprint behavior.
For 1.3, derived-row records also include the new decision diagnostics. The recipe
is unchanged; the versioned record shape makes the changed identity explicit.

Completeness describes the supplied dataset: every row classified and both
Revenue and Expense present. It does not establish completeness of a company's
entire P&L. Nested/multiple category summaries remain unsupported.

## Reviewed fixtures

`tests/fixtures/contracts` contains small synthetic inputs, complete Markdown
reports, and audit records for supported drivers, hypotheses, incomplete
classification, zero budgets, summaries, threshold equality, and escaped labels.
Review full financial and presentation diffs when changing a golden; do not
regenerate them merely to make a failure disappear.

Every report now names its reporting currency. Only that metadata line changes in
the reviewed USD goldens; financial values are unchanged. EUR and GBP goldens
exercise every report section. Mixing currency symbols is rejected; it is not an
accepted financial rule.
Run `pytest tests/test_contract_fixtures.py` after installing `.[dev,excel]`.

## Unreleased 1.8: explicit measures and direction

Schema 1.8 is selectable. The legacy default constant remains 1.7 and every
legacy record keeps its bytes. Declared measures/Better or new measure settings
select 1.8 automatically; explicitly choosing 1.0–1.7 for those facts is refused
before output publication. Published schemas 1.0–1.7 are unchanged.

1.8 adds three closed sibling groups:

- `audience`: exact nullable `per_share_threshold`, `count_threshold`,
  `bps_threshold`, and `percent_values` (points/fractions/null).
- `inferences`: visible measure, direction/default, and percent-scale notes.
- `measure_rows`: all analyzed rows, including nonmaterial ones, with line item,
  measure, type, Better/direction source, comparison/actual/variance, nullable
  variance percent/bps and percent label, status, materiality/reason, and
  exclusion from currency aggregation. All financial values are decimal strings.

The existing money-oriented `material_variances` contains Currency rows only;
`measure_rows` is the complete heterogeneous table. Classification quality and
Currency completeness consider Currency rows, while material variance counts
cover all kinds. The effective audience settings enter configuration identity;
all new row facts and notes enter analysis and public payload identities. Every
1.8 object rejects unknown properties. This schema is unreleased and will gain
the remaining approved comparison/panel facts before publication.

### Unreleased 1.8 comparison additions

`comparison.basis` includes consensus/estimate/guidance only in 1.8. Single records
add `comparison_details` (high/low, estimator count, dispersion, guidance bounds,
midpoint and positions) and `unavailable_comparisons`, and an empty `comparisons`.
`measure_rows.display_label` is a status/materiality projection. `audience` also
records full currency/materiality/type-map settings and extended period/header
choices. Unavailable-only records preserve actuals, absence reasons, supplied
metadata, and effective configuration without invented analyzed amounts.

A set record has kind `comparison_set`, ordered `comparisons` of complete single
or unavailable-only 1.8 child records, `comparison_order`, supplied
`estimate_vs_consensus` facts and inference notes. It claims no financial total
across bases. Every child validates against 1.8 independently, has its own source
and digests, and cannot itself contain a set. Closed conditional shapes refuse
unknown or cross-kind fields. Wrapper metadata is included before both digests
are recomputed; changing unavailable rows or supplied-estimate gaps changes them.

### Segment records in 1.8

`measure_rows[].segment` preserves the supplied flat label. `segments[]` carries scoped revenue/expense aggregates and summary verifications in first-seen segment order. These records do not imply a consolidated total; global completeness is false when named segments are present. Segment source columns appear in inferences. Prior schemas remain unchanged.

### API file provenance

The new file API captures a bounded source once and attaches its exact SHA-256,
name and worksheet to `TableAnalysis`. Comparison audits use that provenance by
default. In-memory API results leave source identity null. Long panel outputs
carry the CLI capture hash or null for in-memory calls; the batch itself is not a
new audit schema kind. Every comparison audit remains independently verifiable.

### Statistics in audit 1.8

Comparison-wrapper records optionally add `statistics_configuration` (window,
entity choice and history source name/SHA-256) and `statistics[]`. Each statistic
contains entity, line item, flat segment, measure, amount/bps surprise, history
SHA-256, ordered prior periods and their exact surprise values, count, window,
sample variance, sample deviation, standardized surprise/reason and dispersion
surprise/reason. The prior values permit independent recomputation. In-memory
history has no claimed file hash. Only Consensus children carry statistics; each
child and the complete set validate independently. These fields enter both
public payload and analysis fingerprints; the effective statistic options also
enter the child configuration identity. Published schemas 1.0–1.7 are unchanged.

### Presentation choices in 1.8

`audience` includes the effective preset, layout, per-share filing-line policy
and explicit headline names. Defaulted choices and headline inference are
visible. These values enter the configuration and public payload identities.
Existing Status values are unchanged; an Earnings sheet or Beat label does not
create a second financial calculation.
