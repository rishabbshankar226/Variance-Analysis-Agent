# Diagnostic follow-up

Reviewed main: `3401cf92fd7c497ae327f4e21fdcc14dcd2c5660`.
Follow-up patch base: `cb5744307da4cfbe67fb5e3dd6774b1fbd5f1ea5` (PR #1).

## Confirmed defects and changes

| Defect | Reproduction | Change |
|---|---|---|
| Worksheet dimensions hide financial rows | Physical Sales, Rent and Utilities rows with declared range `A1:C3` omit Utilities. Expenses actual becomes 60 instead of 85, yet audit totals are complete. | Reset read-only worksheet dimensions before iteration. Pad short physical rows and reject populated cells beyond the header. |
| Ordinary accounts are mistaken for totals | Separate `Total Quality Management` and `Rent` accounts, each actual 120, produce expenses of 120 instead of 240. | Recognize conservative exact summary labels. Add optional `Row Kind=Detail|Total|Subtotal`; ambiguous labels require explicit metadata. Existing reconciliation remains mandatory. |
| Invalid API type maps claim full coverage | `type_map={"Other": "Bogus"}` excludes the row from both category totals while reporting 100% classification coverage. | Validate values through `LineType`, require nonblank string keys, and copy the map at the exported analysis boundary. |
| Malformed XLSX content escapes CLI error handling | Missing archive parts raise KeyError; malformed workbook XML raises ParseError. | Own the input handle and translate observed workbook structure/XML errors to actionable Excel input errors. |
| Extreme zero scales amplify audit serialization | `0e-1000000` formats as 1,000,002 fixed-point characters despite being numerically zero. | Canonicalize extreme-scale zeros, including API thresholds, while preserving ordinary scales such as 0.00. |

## Validation

- Existing main suite: 26 tests pass.
- Existing PR-head suite: 111 tests pass.
- Initial PR bug-hunt module against main: 23 failures and 2 passing controls.
- New 23-case follow-up module against unmodified PR head: 14 failures and 9 passes.
- Complete suite with the follow-up: **134 tests pass** on Python 3.12.14.
- Ruff, compileall, pip check and git diff whitespace checks pass.
- Real sample CLI report/audit: revenue actual 162,500, expense actual 116,000,
  and net operating variance -8,500.

Run the merge checks:

```bash
python -m pip install -e '.[dev,excel]'
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests
python -m pip check
```

## Performance evidence

Synthetic timings are three-run medians on a shared local host; traced allocations
are not process RSS and timings are not production service-level guarantees.

- A worksheet with 1,003 physical rows and three columns, but declared width
  16,384 columns, loads in approximately 0.898 seconds before the follow-up and
  0.017 seconds after it, about 52.7 times faster on that fixture.
- The one-row extreme-zero fixture peaks at approximately 3.26 MB of traced
  allocations before the follow-up and 8.7 KB after it, about 99.7% less.
- Ordinary 10,000-row CSV parsing, analysis, report rendering, audit construction
  and JSON serialization total approximately 0.416 seconds after the follow-up,
  similar to the PR baseline. Peak traced allocations are approximately 49.1 MB.
  These measurements exclude process startup, file I/O and fsync.
- A declared-height-only test did not reproduce a slowdown. The demonstrated
  oversized-dimension cost is padded column width.

## Compatibility and remaining boundaries

Custom labels containing total/subtotal now require Row Kind unless they match a
recognized category-summary label. Set Row Kind to Detail for ordinary accounts
with those words; use Total or Subtotal for custom rollups. Blank optional Row Kind
values retain conservative inference. Explicit metadata never bypasses summary
reconciliation.

Invalid Python API map values now fail early. Extreme zero-scale canonicalization
changes affected audit fingerprints. No runtime dependency was added.

Per-file atomic replacement still is not a report/audit transaction. Concurrent
writers are not locked. Source pre/post hashing is not an immutable snapshot.
Excel cached formulas are not recalculated. No live LLM, agent loop, database or
external API exists in this repository, and this review does not claim their
failure modes were tested. These limitations are unchanged by the follow-up.
