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

Published versions are immutable. Future shape changes receive separate schemas;
archived records remain valid against their original version.

The existing `analysis_fingerprint` hashes canonical JSON containing both the
public record before its fingerprint is added and derived facts for every analyzed
row. Nonmaterial derived rows are not included in the public payload. Consequently,
the fingerprint cannot be recomputed from that payload alone. Neither this
fingerprint nor a source SHA-256 authenticates authorship or proves correctness.

Completeness describes the supplied dataset: every row classified and both
Revenue and Expense present. It does not establish completeness of a company's
entire P&L. Nested/multiple category summaries remain unsupported.

## Reviewed fixtures

`tests/fixtures/contracts` contains small synthetic inputs, complete Markdown
reports, and audit records for supported drivers, hypotheses, incomplete
classification, zero budgets, summaries, threshold equality, and escaped labels.
Review full financial and presentation diffs when changing a golden; do not
regenerate them merely to make a failure disappear.

The baseline documents current USD presentation. Mixing currency symbols is a
known defect, not an accepted financial rule; no mixed-currency golden is added.
Run `pytest tests/test_contract_fixtures.py` after installing `.[dev,excel]`.
