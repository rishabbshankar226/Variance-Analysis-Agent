# STOP 2: after Phase 6 (the workbook), with one STOP-ASK

Committed on `ui/professional-design`: Phases 0 to 5 (`9bcf130` to `35759be`). Phase 6 is written and
reviewed but **not committed**: it changes the workbook's bytes, and one test pins those bytes (below).

## Look at

| File | What it shows |
|---|---|
| `before_results_d.jpg`, `sample_light_d_04_results.jpg`, `sample_dark_m_04_results.jpg` | Results before; results now (headline strip, status words, framed table; phone) |
| `earnings_light_d_04_review.jpg` | Earnings review: comparison columns under one head, Beat / Miss / In line |
| `print_results.pdf` | The conversation printed (results, drill-down, drivers, risks, what-if) |
| `workbook_before_sample-1.jpg`, `workbook_after_sample-1.jpg` | Workbook Summary sheet rendered with LibreOffice, before and after |
| `workbook_before_consensus-1.jpg`, `workbook_after_consensus-1.jpg` | Earnings sheet before and after |

## The STOP-ASK

`tests/test_multi_audience_measures.py::test_legacy_sample_workbook_and_report_are_byte_identical`
asserts the SHA-256 of the sample workbook (`11db3182…`). Phase 6 restyles the workbook (styles.xml,
alignment, print header and footer, print titles), so the bytes change; every cell value, address and
sheet name is unchanged, proved by `test_every_value_and_address_is_unchanged_by_the_redesign`
(openpyxl, against snapshots written from the code at `822e522`, for the sample, a consensus and a
comparison-set workbook). The same test's Markdown report hash and audit schema check still pass.

Recommendation: replace only the workbook hash line with the value-and-address comparison (which the
spec's Phase 6 asks for), keep the report hash and schema lines as they are, and commit Phase 6.
