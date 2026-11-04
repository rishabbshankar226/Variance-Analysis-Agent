# Split proposal for Phase 4 (from the code-health audit)

This proposal comes from the Phase 1 code-health auditor, which mapped the code with `ast` scripts kept in the git-ignored `.scratch/audit-health/`. Line numbers are as of `63162aa`. Phase 4 re-checks every seam before moving code (constraint 8).

## S1. `chat/handlers.py` becomes the package `chat/handlers/`

The call graph covers 167 top-level names. Under the assignment below the module graph has no cycle. Each module imports only from modules listed above it.

| Module | Takes | ~lines |
|---|---|---|
| `__init__.py` | re-exports only, with `__all__` | 30 |
| `_common.py` | `_is_budget`, `_noun`, `_heading`, `_plain_heading`, `_tone`, `_planned`, `_pct_text`, `_variance_percent`, `_pct_change`, `_detail_rows`, `_unclassified_note`, `_with_unclassified_note`, `_file_is_gone`, `_period_slug`, `_MULTI_TABLE_SUFFIXES`, `_is_pdf`, `_sheet_word`, `_choosable`, `_sheet_chip` | 130 |
| `_items.py` | `_ORDINAL_MAP`, `_POSITIONAL_RE`, `_resolve_item_query`, `_GENERIC_ITEM_WORDS`, `_SENTENCE_STOPWORDS`, `_WORD_RE`, `_items_named_in`, `_item_in_sentence`, `_SUGGEST_MAX_QUERY`, `_SUGGEST_MAX_ITEMS`, `_suggest_items`, `_not_found`, `_rows_named` | 200 |
| `_thresholds.py` | `_THRESHOLD_RE`, `_parse_threshold_amount`, `_parse_threshold_text`, `_SINGLE_DOLLAR_RE`, `_SINGLE_PCT_RE`, `_parse_partial_threshold_text` | 120 |
| `summary.py` (after `_common`) | `_basis_summary`, `_audience_summary`, `_STATEMENT_CHIPS`, `_STATEMENT_WORKBOOK`, `_statement_checks`, `_report_text`, `_build_analysis_summary`, `_FILING_TOTALS_NOTE`, `_COMPUTED_TOTALS`, `_filing_summary` | 300 |
| `upload.py` (after `_common`) | `handle_upload`, `_looks_like_pasted_table`, `_COVENANT_ASK`, `_handle_covenant_headroom`, `_load_covenant_file`, `_half_request`, `_load_other_half`, `_LTM_ASK`, `_offers_ltm`, `_handle_build_ltm`, `_load_ltm_annual`, `_load_file`, `_fatal_upload_response`, `HIDDEN_ROWS_CHIPS`, `_comparison_chips`, `_intake_summary_text`, `_intake_confirmation`, `_first_upload_intro`, `_with_first_upload_intro`, `_intake_response`, `_blank_wording` | 390 |
| `run.py` (after `summary`) | `_run_analysis`, `_next_measure_question`, `_handle_classify`, `_rerun_after_classification` | 310 |
| `workbook.py` (after `run`, `upload`) | `_handle_list_sheets`, `_handle_switch_sheet`, `_handle_hidden_rows`, `_handle_set_comparison`, `_CHAT_BASES` | 300 |
| `setup.py` (after `_thresholds`, `run`, `upload`, `workbook`) | `_PERIOD_HINT`, `_QUESTION_OPENERS`, `_looks_like_typed_period`, `_handle_intake_confirmation`, `_handle_blank_budget_confirmation`, `_handle_period_choice`, `_clean_period_input`, `_MAX_PERIOD_CHARS`, `_handle_period`, `_handle_thresholds`, `_clean_currency_input`, `_handle_currency`, `_handle_measure_option` | 355 |
| `export.py` (after `summary`) | `_export_response`, `_PATH_CHARACTERS`, `_export_path`, `_path_export_disabled`, `_handle_export_report`, `_handle_export_audit`, `_FORMULA_STARTS`, `_csv_text`, `_handle_export_csv`, `_handle_export_xlsx`, `_saved_comparison_basis`, `_layout_mapping_for`, `_handle_save_mapping` | 300 |
| `lookup.py` (after `_items`) | `_explain_lines`, `_explain_view`, `_handle_explain`, `_handle_detail` | 210 |
| `explore.py` (after `_thresholds`, `run`, `summary`) | `_handle_help`, `_handle_reset`, `_handle_summary`, `_handle_material`, `_handle_filter_status`, `_handle_filter_type`, `_handle_top_n`, `_handle_set_threshold`, `_handle_warnings`, `_action_plan`, `_handle_recommendations`, `_handle_totals`, `_handle_full_report` | 485 |
| `status.py` (after `_common`) | `_handle_revenue_status`, `_handle_expense_status`, `_handle_budget_utilization`, `_handle_revenue_misses`, `_handle_cost_savings`, `_UnbudgetedWording`, `_UNBUDGETED_WORDING`, `_handle_unbudgeted` | 405 |
| `rankings.py` (after `_common`, `_items`) | `_handle_biggest_risks`, `_handle_biggest_wins`, `_handle_top_percent`, `_handle_metrics_count`, `_handle_concentration`, `_handle_compare` | 430 |
| `scenarios.py` (after `_common`, `_items`) | `_handle_waterfall`, `_handle_what_if`, `_handle_sensitivity`, `_UNRECOGNISED_PERIOD`, `_MONTH_NUMBERS`, `_MONTH_NAME`, `_QUARTER`, `_HALF`, `_detect_period_elapsed_months`, `_handle_run_rate` | 600 |
| `narrative.py` (after `_common`) | `_handle_executive_memo`, `_handle_driver_summary`, `_handle_tldr`, `_handle_profitability` | 365 |
| `conversation.py` (after `_items`, `narrative`) | `_handle_greeting`, `_handle_gratitude`, `_handle_identity`, `_describe_item_reply`, `_handle_unknown`, `_handle_knowledge`, `_KNOWLEDGE_TEXTS` | 270 |
| `router.py` (last) | `handle_message`, `_UPLOAD_ANOTHER_FILE`, `_reader_question`, `_handle_exploring`, `_EXPLORING_HANDLERS` | 260 |

Why the placements avoid cycles:

- `_reader_question` calls `handle_message`, so both live in `router`.
- `_next_measure_question` goes in `run`, since `_run_analysis` calls it.
- `_handle_switch_sheet` sits in `workbook`, between `upload`/`run` and `setup`.
- `_handle_unknown` calls `_handle_profitability`, so `conversation` imports `narrative`.

**Names that must stay importable from `variance_agent.chat.handlers`:**

- `handle_message`, `handle_upload` (server.py:28, about 78 test sites)
- `_export_response`, `_period_slug` (`chat/earnings.py:153`, lazy)
- `_intake_summary_text` (tests/test_chat_reply_shape.py:22)
- `_layout_mapping_for` (tests/test_excel_hidden_rows.py:191)
- `_detect_period_elapsed_months` (tests/test_chat_correctness.py:11)
- `_KNOWLEDGE_TEXTS` (tests/test_chat_wording.py:103)

Nothing patches handlers by attribute or by string target.

**Musts for the split:**

- Change the E501 exemption in `pyproject.toml:59` to the new paths, or remove it once lines are wrapped.
- `__init__.py` declares `__all__` with all 8 names: mypy strict turns off implicit re-export, and ruff's F401 needs it too.
- Every relative import gains one dot. The 19 lazy ones inside function bodies fail only when their path runs: `.earnings` at 221, 224, 236, 239, 267, 712, 715, 738, 1334, 1630, 1865, 3893; `..metrics` at 571, 579; `..join` at 618, 635; `..ltm` at 683; `..report` at 1531, 1984. Add a check that resolves every relative import in the package (`importlib.util.resolve_name` plus `find_spec`).
- Keep each in-body `from ..earnings import X` inside its function, and leave `earnings.py:153` as `from .handlers import ...`.
- T1's test patches `normalize_for_routing` on every loaded `variance_agent*` module. So each submodule that folds text must import it under that exact name, `__init__` must import `router`, and `_items.py` must call `difflib.SequenceMatcher` as an attribute. A `from difflib import SequenceMatcher` would silently weaken the test.
- `tests/test_server_hardening.py` patches `server_module.handle_message` / `handle_upload`, so `server.py:28` must keep binding both from `.handlers`.

## S2. `intake.py::_process_raw_table` (2853-3329, 477 lines)

Keep the orchestrator and its signature. The `reread` re-entry starts at the top, so the half-fill (2876-2879, which mutates the `_HALF` context variable) and the dated-header rewrite (2881-2890) run again exactly as today. State lives in a private mutable `_TableRead` dataclass, and each stage returns `IntakeResult | None` for a stop.

| Stage | Lines | Note |
|---|---|---|
| S1 `_find_header` | 2870-2911 | returns at 2871, 2896, 2910 |
| `_reread` (a module function replacing the closure at 2913-2921) | | captures 7 parameters; calls `_process_raw_table(..., replace(excel, block=None), layout_retry=False)` |
| S2 `_named_block_retry` | 2923-2930 | |
| S3 `_detect_basis` | 2932-2963 | returns at 2950, 2954 (reread), 2957 |
| S4 `_map_columns` | 2965-3028 | **mutates `roles` in place** (2968, 2970); creates `visible_transformations` |
| S5 `_check_layout` | 3030-3082 | returns at 3052, 3054 |
| S6 row loop, plus `_row_kind` (3090-3108), `_row_amounts` (3109-3151), `_row_record` (3153-3206) | 3084-3207 | loop-carried lists, plus dash and minus counts kept in an accumulator. **3109 returns inside the loop**: use a private exception caught in `_process_raw_table`, or `_read_excel_bytes`' `except Exception` (1995) would rewrite it. That `IntakeResult` carries no `sheet_name` or `header_row_number`; keep it that way. |
| S7 `_post_row_notes` | 3209-3240 | |
| S8 `_unit_scale` | 3243-3263 | |
| S9 `_signs_and_totals` | 3266-3294 | |
| S10 `_table_result` | 3296-3329 | |

## S3. `cli.py::_run` (323-670, 348 lines)

Tests patch these `cli` globals: `load_input`, `analyze_rows`, `render_markdown` (test_cli_audit.py:18-20, test_provenance.py:55) and `_run` (test_institutional_financial.py:187). Other tests patch `server.run_chat_server`, so the lazy import at cli.py:329 stays. Every stage stays in cli.py and calls these names as globals.

The stages:

- `_run_chat`: 324-342.
- Orchestrator: the quant and group-by exit, 344-350.
- **parse**, `_check_single_file_args`: 351-384.
- **read**:
  - `_capture`: 386-411. The comparison-path branch at 406 comes before the opt-in raise at 409-411.
  - `_read_mapped`: 414-494, with `_mapping_type_map` taken from 465-489. It mutates `intake_res.detected_totals` (443) and the signed-ledger fields (462-463).
  - `_read_assisted`: 495-544.
  - `_read_strict`: 545-560.
- **analyse**: `_build_config` 562-604 (re-binds `parsed_rows` at 577-585), then `_analyse` 605-618.
- Orchestrator: check-only, 619-624.
- **write**, `_write_outputs`: 625-670. Keep the three `--xlsx` guards (629-638) after analysis, so the same error wins.

## S4. `_handle_what_if` (handlers.py:3959-4201) and `build_audit_record` (audit.py:283-514)

**What-if:**

- W1 amount, 3968-4023.
- W2 target, 4026-4054.
- W3 `_simulate`, 4056-4117. It owns the whole `with financial_context()` block with `traps[Inexact] = False`; no seam goes inside it.
- W4 text, 4119-4137.
- W5 table, 4139-4175.
- W6 view, 4177-4200.

**Audit record:**

- B1 verify and schema, 299-334. Keep the 10 raise checks in order.
- B2 identity checks, 335-346. These are a copy of `validate_source_identity`, 581-585.
- B3 counts, 349-372.
- B4 base record, 374-429. `source` and `data_quality` are mutated later, so pass the same dicts.
- B5 versioned sections, 430-465.
- B6 diagnostics, 466-491.
- B7 audience, 492-505.
- B8 the fingerprint, then the payload hash, 506-513; these stay last.

Key order does not matter, because both serialisers sort keys.

**Other functions over 150 lines:**

- `analysis.py:504 analyze_rows`: config validation, per-row `_analyze_row`, dataset warnings, aggregate.
- `handlers.py:3209 _handle_compare`: a macro helper and a revenue-against-expense helper.
- `intake.py:1833 _read_excel_bytes`: keep the try/except/finally in place, and move the body out in three parts.
- `comparisons.py:394 read_comparison_input`: six stages.
- `statement_shape.py:132 shape_income_statement`: four stages.
