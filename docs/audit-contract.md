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
Version 1.6 is the default and adds `comparison: {basis, label}` (`basis` is `budget`, `forecast`, or `prior_period`; `label` is the display text or null), included in the configuration identity and therefore the analysis fingerprint. The `budget` keys keep their names and hold the comparison amount.
Schemas 1.0-1.5 record that amount as a budget, so they are refused for Forecast and Prior Period runs: "Audit schema {version} records the comparison amount as a budget; use --audit-schema-version 1.6 for forecast or prior-period comparisons." Budget runs may still select any version.
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
