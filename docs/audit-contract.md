# Audit and report contracts

The audit is deterministic analysis output. Source-derived names, labels, periods,
and warnings are untrusted data, including when carried inside valid JSON.
The trust flags declare intended use; they do not enforce model behavior.

`schemas/audit-1.0.schema.json` defines the existing wire format using JSON Schema
Draft 2020-12. Consumers must select a schema using `schema_version` and reject
unknown versions. Financial values are finite fixed-point decimal strings, not
JSON floats. A zero budget with nonzero actual has a null percentage and an
explicit unbudgeted label. Schema validation checks structure; deterministic
Python remains responsible for reconciliation and arithmetic.

Version 1.1 adds the explicit reporting `currency` (USD, EUR, or GBP).
Version 1.2 is the default and adds policy/configuration provenance and a
recomputable `payload_sha256`. Use `--audit-schema-version 1.0` or the Python `schema_version="1.0"`
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

`configuration_sha256` hashes the effective period, decimal threshold strings,
currency, and validated type map using the canonicalization below. Maps with
different key order but identical content have identical configuration identity.

`payload_sha256` uses recipe `public-record-without-payload-sha256-v1`: remove only
the top-level `payload_sha256` field; JSON-serialize the remaining record with
sorted object keys, separators `(',', ':')`, `ensure_ascii=False`,
`allow_nan=False`, and UTF-8 encoding; SHA-256 the bytes. No trailing newline is
included. `analysis_fingerprint` is retained inside this public digest.
Use Python `variance_agent.audit.payload_sha256(record)` after schema validation.
This provides change detection, not origin authentication.

`analysis_fingerprint` uses `record-and-derived-rows-v1`: the same canonicalization
over `{record: record-before-both-digests, analyzed_rows: all-derived-row-records}`.
Versions 1.0/1.1 retain their original record shape and fingerprint behavior.

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
