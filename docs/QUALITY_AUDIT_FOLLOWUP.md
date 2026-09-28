# Follow-up quality audit

Baseline: `85a2333ef7121285c9583a1c72bf6655659e930e` (the first bug-hunt branch).

## Findings and changes

| Area | Reproduced issue | Change |
|---|---|---|
| Numeric input | `1,00` becomes 100, `12$34` becomes 1234, `(-100)` becomes positive 100. Booleans raise an internal Decimal exception. | Validate the entire numeric representation, preserve valid financial formats, and reject ambiguous signs, separators, and symbols. CLI thresholds use the same parser. |
| Source precision | Applying accounting parentheses rounds digits under a low-precision Decimal context. | Use context-independent `copy_negate()` when parsing source values. This does not change the arithmetic precision policy. |
| Dataset selection | JSON with both `rows` and `data` silently selects one. | Require one dataset wrapper key. |
| Classification | Duplicate type-map keys or multiple Type/classification columns silently select one classification. | Reject ambiguity; retain explicit type-map precedence. |
| Final verification | Incorrect percentages, percentage labels, F/U statuses, aggregate metrics, and missing/duplicate material rows pass the verification step. | Verify those invariants and reconstruct expected material membership from all analyzed rows. |
| Output failure | An invalid audit destination overwrites a previous report before failing. Direct writes can truncate existing files on I/O failure. | Stage and flush all files first, then atomically replace each file. Reject destinations that contain one another, retain existing file permissions, and clean temporary files on handled failures. |
| Optional dependency | Missing openpyxl produces an uncaught RuntimeError. | Return the existing actionable installation message as a normal CLI input error. |

## Validation

- 21 initial failure cases reproduced before fixes. The complete follow-up test
  module produces **24 failures and 9 passes** against the isolated baseline.
- Full current suite: **84 passed** on local Python 3.12.
- 250 deterministic generated cases checked against an independent Fraction-based
  oracle for variance, materiality, zero budgets, negative budgets, and F/U status.
- Equivalent CSV, JSON, and Excel inputs produce the same analysis fingerprint
  when source-specific metadata is omitted.
- Injected staging and replacement failures preserve existing files as specified
  and leave no temporary output files.
- Mutation tests prove the final verification rejects corrupted result fields
  and omitted/duplicated material rows.
- Lint, compilation, dependency checks, and the sample CLI report/audit flow pass.

## Review scope and remaining boundaries

Reviewed the changed parser, analysis verification, CLI, audit serializer, new
output helper, and their call sites. No new runtime dependencies or LLM calls.
Valid currency/scientific formats are regression-tested alongside rejected forms.

Each output replacement is atomic, but the pair is not transactional. A failure
during the second replacement can leave a new report with an old audit; the CLI
reports the failure, and rerunning regenerates both. A process killed before
cleanup can leave a temporary file. Concurrent writers are not locked.
Decimal calculations retain the existing context/precision policy; this change
fixes source-sign conversion, not arbitrary-precision arithmetic. The tests do
not prove that every possible bug has been eliminated.
