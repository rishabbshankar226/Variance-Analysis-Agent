# Test-strength sample: 25 seeded mutants

**Method.** A branch is each `ast.If` test (`if` and `elif`), each `ast.While` test, and each `ast.ExceptHandler`, in five modules: `intake.py`, `analysis.py`, `excel.py`, `xlsx.py` and `statement_shape.py`. That gives 659 branches. The 25 drawn are `random.Random(20261102).sample(sorted(pairs), 25)` over the sorted (path, line) pairs.

**How each mutant ran.**

- An `if` or `while` test became `not (<test>)` over its exact source span.
- An `except` handler got a bare `raise` as its first statement.
- Each mutant ran with the full suite, `-x -q`, in an isolated worktree, with `PYTHONPATH=<worktree>/src`.
- Import check: `variance_agent.__file__` lay inside the worktree. Baseline: 2505 passed in 47.44s.
- The worktree was cut at `15100c8`. Its `src/` matches `improve/depth-pass` at `63162aa`, since T1 changed only a test.
- Total run time was 705 s.

The scripts are in `.scratch/mutants/` (`sample.py`, `runner.py`, `draws.json`, `results.jsonl`, `probe_*.py`), which is git-ignored. Draws are quoted by function and source text, so T2 can find them after Phase 4 moves the code.

**Result: 22 killed, 3 survived, 0 not run.**

| # | File | Function | Source (trimmed) | Kind | Result |
|---|---|---|---|---|---|
| 0 | intake.py | plain_analysis_error | `if any(term in text.lower() for term in ("archive", "ooxml", "xml", "dtd", "badzipfile", "corrupt"))` | negate | killed (test_chat.py::test_handle_invalid_file_upload) |
| 1 | analysis.py | analyze_rows | `if not isinstance(config, AnalysisConfig):` | negate | killed |
| 2 | intake.py | _read_excel_bytes | `except Exception as exc:` (after `inspect_workbook`) | raise | **survived** |
| 3 | xlsx.py | _package | `if len(name) > 31 or any(char in name for char in "[]:*?/\\"):` | negate | killed |
| 4 | xlsx.py | render_comparison_xlsx | `if effective_layout(table.config) == "earnings":` | negate | **survived** |
| 5 | intake.py | WorkbookExamination.lines | `if self.external_links:` | negate | killed |
| 6 | excel.py | _worksheet_scan | `elif event == "end" and element.tag == f"{_SHEET_NAMESPACE}v":` | negate | killed |
| 7 | intake.py | _read_ixbrl_bytes | `except IxbrlError as exc:` | raise | killed |
| 8 | analysis.py | _resolve_summary_rows | `if verification is None:` | negate | killed |
| 9 | intake.py | parse_assisted_decimal | `if not isinstance(value, str):` | negate | killed |
| 10 | intake.py | _read_edgar_statement | `if chosen is None:` | negate | killed |
| 11 | intake.py | _process_raw_table | `if any(str(value).strip().endswith("%") for value in (raw_budget, raw_actual)):` | negate | **survived** |
| 12 | xlsx.py | _pct_cell | `if label:` | negate | killed |
| 13 | intake.py | _process_raw_table | `if stop is not None:` | negate | killed |
| 14 | intake.py | match_column_synonym | `if norm in _PERIOD_SYNONYMS:` | negate | killed |
| 15 | statement_shape.py | shape_income_statement | `if kind:` | negate | killed |
| 16 | intake.py | IntakeResult.has_transformations | `if role == CanonicalRole.ACTUAL and orig_lower not in std_actuals:` | negate | killed |
| 17 | intake.py | intake_summary_rows | `if CanonicalRole.ACTUAL in result.column_mapping:` | negate | killed |
| 18 | intake.py | _read_edgar_statement | `if hidden and excel.hidden_rows == "exclude":` | negate | killed |
| 19 | intake.py | plain_analysis_error | `if "normalize" in text.lower() or "same key" in text.lower():` | negate | killed |
| 20 | intake.py | _filing_headline | `if _EXPENSE_TOTAL.match(line.concept):` | negate | killed |
| 21 | statement_shape.py | shape_income_statement | `if all(e >= 0 for e in effects) and any(e > 0 for e in effects):` | negate | killed |
| 22 | intake.py | detect_comparison_columns | `if repeated and not detect_period_pairs([s for _, s in headers]):` | negate | killed |
| 23 | intake.py | parse_assisted_decimal | `if not value.is_finite():` | negate | killed |
| 24 | intake.py | format_intake_summary | `if result.rows_skipped_count > 0:` | negate | killed |

## The three survivors

The main session re-ran each probe on unmutated code at `63162aa`. None of the three is an equivalent mutant.

- **#2.** A loader raising `KeyError` returns `has_fatal_errors=True` with "Could not read Excel file 'book.xlsx': 'broken part'". Under the mutant it would escape `handle_upload`, which catches only `ValueError`. No test refers to the message.
- **#4.** A CONSENSUS + ESTIMATE table gives `['Comparisons']` with preset `fpa` and `['Earnings', 'Comparisons']` with preset `earnings`. The mutant swaps them. The existing `"Earnings" in wb.sheetnames` check goes through `_audience_sheets` instead.
- **#11.** A `41.2%` row gets "read % values as percentage points." and a `0.412` row does not. The mutant inverts this. No test contains "percentage points".
