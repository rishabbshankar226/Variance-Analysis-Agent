# STOP-ASK: a 10-Q's column label is also the audit's key (M4)

**Found** in Phase 3 on 2026-11-02. M4 asks that display labels carry the statement's duration ("6 months ended Mar 2026") wherever the filing states one, while the long CSV, JSONL and audit keys stay as they are. The prompt says that if a label is the key, the item is a STOP-ASK.

**The label is the key.** A 10-Q's column label comes from `ixbrl._period_labels`, which names a duration by its end month ("Mar 2026"). That one string becomes the comparison label, `AnalysisConfig.comparison_label`, and the audit records it as the key: `comparison.label`. Run on the fictional `tests/fixtures/analysts/hal-20260328.htm`, the audit holds `"comparison": {"basis": "prior_period", "label": "Mar 2025"}`. The report heading reads "Prior Period (Mar 2025)", and the chat note says "Comparing Mar 2026 against Mar 2025". Putting the duration into the label would change the audit's `comparison.label`, and with it the long outputs' label fields, on every filing run.

**Recommendation.** Keep every key as it is: the column label, `comparison.label` and the long CSV and JSONL fields. Carry the duration in display text only, through a separate display name for each column; `AnalysisConfig` already has `comparison_title` and `actual_label` for headings. The report headings and the chat summary would then read "Prior Period (6 months ended Mar 2025)", and the statement's own note "Read the column for ... as ..." would name the duration. A test asserts that the audit's `comparison.label`, the long CSV and the JSONL are byte-identical before and after. Wherever the label is shown, the duration is shown with it, so the three-month income statement and the nine-month cash flow statement no longer read alike.

The alternative is to change the label, and so the audit's `comparison.label`, to carry the duration. No schema changes, because the field is free text, but every filing audit's value would change.

**Question.** May the run add the duration as a display name only, keeping every key (recommended), or change the label itself? It is marked `asked` in PLAN.md as M4, and the run continues with M5 and C4.
