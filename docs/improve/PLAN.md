# Improvement pass: plan

Branch `improve/depth-pass`, cut from `main` at `15100c8` on 2026-11-02. The control prompt is `VARIANCE_IMPROVEMENT_PASS_PROMPT.md` (Revision 2), kept outside the repository. This plan plays the rules file's Implementation Plan. It changes only through the Decisions list below. Before an item is edited, it lists the files it touches.

## Status

States: `todo`, `done`, `asked`, `open`, `closed`, `struck`. The X items join at STOP 1.

| ID | Phase | State | Commit | Files to touch (filled before editing) |
|---|---|---|---|---|
| T1 | 0 (Phase 6 item) | done | see `fix(T1)` | `tests/test_chat_hardening.py` |
| C1 | 2 | todo | | |
| C2 | 2 | todo | | |
| C3 | 2 | todo | | |
| C5 | 2 | todo | | |
| M1 | 3 | todo | | |
| M2 | 3 | todo | | |
| M3 | 3 | todo | | |
| M4 | 3 | todo | | |
| M5 | 3 | todo | | |
| M6 | 3 | todo | | |
| C4 | 3 | todo | | |
| S1 | 4 | todo | | |
| S2 | 4 | todo | | |
| S3 | 4 | todo | | |
| S4 | 4 | todo | | |
| N1 | 5 | todo | | |
| N2 | 5 | todo | | |
| T2 | 6 | todo | | |
| T3 | 6 | todo | | |
| D1 | 7 | todo | | |
| D2 | 7 | todo | | |
| D3 | 7 | todo | | |

## Decisions

1. **Worktree cleanup is scoped to this run.** The prompt's "remove finished worktrees before each gates run" covers only worktrees this session creates. The ten worktrees already under `.claude/worktrees/` belong to other branches and sessions and are left alone. `ruff check .` lints 205 files and none of theirs, because `.git/info/exclude` lists `.claude/worktrees/`. If a gate ever reached them, the fix would be an exclude, not a removal.
2. **No side sessions.** Every phase edits this branch in the main clone and depends on the phase before. Subagents run only where the prompt calls for them.
3. **`.scratch/` ignores itself.** A plugin hook in this session blocks shell writes to `.git/info/exclude`. So `.scratch/.gitignore` holds `*`, which makes git, and ruff through git's rules, skip the folder. `/CLAUDE.md` and `.claude/worktrees/` were already in `.git/info/exclude`. `.claude/` holds nothing else, so the only place agent worktrees land is already excluded.
4. **Environment.** The owner chose to rebuild `.venv` on Python 3.11, the floor CI covers. The old Python 3.14 env, which had no pip and no `pdf` or `release` extras, is kept at `.scratch/venv-3.14-old`.
5. **Draw G.** `EDGAR_USER_AGENT` was unset at Phase 0, though `~/vaa-edgar-corpus` exists. The owner sets it; it is raised again at STOP 1 and STOP 2. If it is still unset at Phase 8, Draw G is recorded as not measured. The owner's email goes into no SEC request without their explicit yes.
6. **T1's scope.** Only the test named in section 1 flakes. The subprocess-timed hostile-message tests in the same file (`_assert_quick`, 0.5 s inside a child process) were run under the same load (64 CPU-bound processes on 10 cores): 31 passed. They are left as they are.
7. **T1's method: count the work, not the clock.** Commit `1fc32b8` fixed a 1 to 3 s answer on 20,000 lines. Its cost came from two things: a difflib comparison for every name, and several passes over the names. The test now counts both, at 5,000 and at 20,000 lines. Difflib comparisons must be equal at the two sizes, because the suggestion cap holds whatever the file size. Routing folds may grow by at most three per added name. Three is the current shape, measured by caller: one fold per name in each of `intent._match_key`, `handlers._items_named_in` and the sentence match's word scan. Counting only `handlers` would have shown two. A sanity check confirms the counter is live: at least one fold per name. The counter patches every loaded `variance_agent` module that holds `normalize_for_routing`, so S1's move of the handlers into a package keeps it counting. A wide wall-clock bound was rejected because it would not catch the original regression. That regression took 1 to 3 s, inside any bound wide enough to survive load.

## Existing assertions to edit

| Test | Assertion | Reason |
|---|---|---|
| `tests/test_chat_hardening.py::test_unmatched_questions_on_a_big_file_stay_fast` (7 cases) | `assert time.perf_counter() - start < 0.5` is replaced by the work counts of Decision 7. `assert response.text` stays. | T1. The bound failed under load. Measured here: 5 of 7 cases failed on each of two runs beside 64 CPU-bound processes. The work counts pin the same fix without a clock. |

## Phase 0 figures (Python 3.11.16, macOS, 10 cores)

Gates, summary lines as printed:

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed! |
| `mypy --strict src/variance_agent scripts deterministic_conditioning` | Success: no issues found in 71 source files |
| `compileall -q src tests scripts deterministic_conditioning` | exit 0 |
| `pytest -q` | 2505 passed in 48.53s |
| `pip check` | No broken requirements found. |
| `build` / `twine check` / `check_distribution.py` | built `variance_analysis_agent-0.3.0.tar.gz` and `-py3-none-any.whl`; both PASSED; "Wheel/sdist contents, license, Python support, and entry point verified" |
| minimal install: `check_installation.py --without-excel --without-pdf`, `pip check` | "Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified"; No broken requirements found. |
| Windows output-contract job | not runnable here; covered by CI only |

Size table, measured by `.scratch/size_table.py` (an `ast` walk, counting from the `def` line). It matches the prompt's section 1: 732 functions in `src/`, 36 over 80 lines, 9 over 150. `chat/handlers.py` has 5,082 lines and `intake.py` 3,627.

| Function | File | Lines |
|---|---|---|
| `_process_raw_table` | `intake.py` | 477 |
| `_run` | `cli.py` | 348 |
| `_handle_what_if` | `chat/handlers.py` | 243 |
| `build_audit_record` | `audit.py` | 232 |
| `analyze_rows` | `analysis.py` | 223 |
| `_handle_compare` | `chat/handlers.py` | 171 |
| `_read_excel_bytes` | `intake.py` | 170 |
| `read_comparison_input` | `comparisons.py` | 161 |
| `shape_income_statement` | `statement_shape.py` | 155 |

Contracts: 19 files in `tests/fixtures/contracts/`. Schemas: `audit-1.0` to `audit-1.9`. Docs root: 17 Markdown files.

T1 under load: `pytest tests/test_chat_hardening.py::test_unmatched_questions_on_a_big_file_stay_fast` beside 64 runs of `.scratch/burn.py`, a 150 s busy loop. Both runs printed "5 failed, 2 passed" with, for example, `assert (1110104.490578166 - 1110103.815566125) < 0.5`. Beside 16 such processes, three runs passed. Unloaded, each question takes 0.04 to 0.09 s.

## Revert proofs

| ID | Fix reverted | Test run | Result with the fix reverted |
|---|---|---|---|
| T1 | The test checks `1fc32b8`'s fix, so the proof re-introduces that fix's two costs one at a time. (a) `_SUGGEST_MAX_ITEMS = 10**9`: the suggestion cap removed. | `pytest tests/test_chat_hardening.py -k stay_fast` | 3 failed, 4 passed: `assert 120000 == 30000`, difflib comparisons growing with the file |
| T1 | (b) `_item_in_sentence` ignores the caller's `named` and recomputes the scan: an extra pass over the names. | same | 1 failed, 6 passed: `assert (80009 - 20009) <= (3 * (20000 - 5000))` |
| T1 | Load, the reason for the change: the old test beside 64 CPU-bound processes, then the new one. | `pytest ...::test_unmatched_questions_on_a_big_file_stay_fast` | old test: "5 failed, 2 passed" on each of 2 runs; new test: "7 passed" on each of 2 runs |

## Path existed in 0.2.0

Recorded for C2 and C3 in Phase 2.

## Looking at the outputs

One sentence each per phase, on one report, one workbook and one chat reply the phase changed.
