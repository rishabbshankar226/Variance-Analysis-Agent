# STOP-ASK: F4, budget and actuals in two files (written 2026-10-27)

**Recommendation: join the two files on a key both files carry, and turn the budget-only dead end into a request for the other file.**

Today a budget-only upload stops at "Could not find a header row with Line Item, Budget, and Actual columns", and nothing can combine it with the actuals file. In the repository's own pair (`tests/fixtures/realworld/fixture_f_*.csv`) the line labels differ between the files ("SaaS Subscription Revenue" against "SaaS Subscriptions"), while the GL Account numbers match. So I recommend this rule:

- The join uses an account-ID column both files share (the intake's existing Account ID role). Without one, it uses the exact line-item label. It never matches by similarity.
- The actuals file's labels are shown. Each row records the comparison file's label and account in audit 1.9, beside both files' names and sha256 (multi-document provenance).
- A line in one file only refuses the join, naming the lines on each side, because a partial join would change the totals without a trace. The fix offered is to add the line to the other file or remove it.
- **CLI:** `variance-agent actuals.csv --assisted --compare-file budget.csv` (opt-in; strict mode unchanged).
- **Chat:** a file with a comparison column and no Actual column, or the reverse, asks for the other file instead of stopping. The next upload is joined.

**The one existing assertion this edits:** `tests/test_realworld_intake_baseline.py:154`.
- Old: `"Could not find a header row with Line Item, Budget, and Actual columns" in resp_upload.text`.
- New: `"'fixture_f_budget_separate.csv' has Budget figures but no Actual column. Upload the file with the actuals, and I'll join the two by 'GL Account'." in resp_upload.text`.

Line 153's phase stays `AWAITING_FILE`, since the chat is waiting for the second file, and a new test pins the joined result of the pair. A grep of `tests/` finds one other assertion of this message, `tests/test_intake_comparison.py:269`. It covers a `Name, Amount` file, which has neither a comparison nor an Actual column, so it keeps the header-row refusal unchanged.

F4's second half, "a 10-K plus a 10-Q cannot be combined either", is already closed by `--ltm-from` (R11) and the chat's "Build LTM". No other existing output changes: single-file reads, strict mode and the 19 contract fixtures are untouched.

The alternative is to leave F4 open and record it as a known limit. I don't recommend it, because the spec names closing this dead end as an intended change.
