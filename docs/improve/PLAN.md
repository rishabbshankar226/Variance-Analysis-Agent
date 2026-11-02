# Improvement pass: plan

Branch `improve/depth-pass`, cut from `main` at `15100c8` on 2026-11-02. The control prompt is `VARIANCE_IMPROVEMENT_PASS_PROMPT.md` (Revision 2), kept outside the repository. This plan plays the rules file's Implementation Plan. It changes only through the Decisions list below. Before an item is edited, it lists the files it touches.

## Status

States: `todo`, `done`, `asked`, `open`, `closed`, `struck`. The ranked backlog, with each item's severity, cost and contract impact, is in [evidence/stop-1/BACKLOG.md](evidence/stop-1/BACKLOG.md). Each item's reproduction is in [evidence/stop-1/audit-findings.md](evidence/stop-1/audit-findings.md). Until STOP 1 answers, every proposed item is `todo`.

| ID | Phase | State | Commit | Files to touch (filled before editing) |
|---|---|---|---|---|
| T1 | 0 (Phase 6 item) | done | `63162aa` | `tests/test_chat_hardening.py` |
| X1 | 2 | done | see `fix(X1)` | `src/variance_agent/intake.py`, `tests/test_amount_forms.py` |
| X2 | 2 | todo | | |
| X3 | 2 | todo | | |
| C2 | 2 | todo | | |
| C5 | 2 | todo | | |
| X4 | 2 | todo | | |
| X5 | 2 | todo | | |
| X6 | 2 | todo | | |
| X7 | 2 | todo | | |
| X8 | 2 | todo | | |
| C1 | 2 | todo | | |
| C3 | 2 | todo | | |
| X30 | 2 | todo | | |
| X9 | — | open | | owned by `claude/per-visitor-sessions-d54fc9` (Decision 12) |
| X10 | 3 | todo | | |
| X11 | — | open | | owned by the per-visitor-sessions work (Decision 12) |
| X12 | 3 | todo | | |
| X13 | 3 | todo | | |
| X14 | 3 | todo | | |
| X15 | 3 | todo | | |
| X16 | 3 | todo | | |
| X17 | 3 | todo | | |
| X18 | 3 | todo | | |
| X19 | 3 | todo | | |
| X20 | 3 | todo | | |
| X21 | 3 | todo | | |
| X22 | 3 | todo | | |
| X23 | 3 | todo | | |
| X24 | 3 | todo | | |
| M1 | 3 | todo | | name the second document only (Decision 12) |
| M2 | 3 | todo | | |
| M3 | 3 | todo | | |
| X25 | 3 | todo | | |
| X26 | 3 | todo | | |
| X27 | 3 | todo | | |
| X28 | 3 | todo | | |
| X29 | 3 | todo | | |
| X31 | 3 | todo | | |
| M4 | 3 | todo | | |
| M5 | 3 | todo | | |
| C4 | 3 | todo | | |
| M6 | 3 | todo | | |
| X35 | 3 | todo | | |
| X36 | 3 | todo | | |
| X32 | 5 | todo | | state the rounding on the sheet (Decision 12) |
| X37 | 4 | todo | | |
| X33 | 7 | todo | | |
| X34 | 7 | todo | | |
| X38 | — | open | | cost; not this run except where X17 or X18 touch it |
| X39 | — | open | | memory on the hosted free plan; not this run |
| X40 | — | open | | left to the owner: the deploy pins (Decision 12) |
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

8. **Ranking.** The backlog is ordered by severity: wrong number, exposure, dead end, misleading, unpinned, cost. Within a severity it is ordered by cost (S, M, L). Exposure ranks second because it is a security gap. A finding that is both a wrong number and an exposure (X9) ranks with the wrong numbers.
9. **The shared hosted session (X9, and with it X11).** Open branches already target this: `claude/per-visitor-sessions-d54fc9` and `feat/chat-intro-per-visitor`. Two writers on one design is the collision the comparison-basis run hit, so both items are `asked` at STOP 1 and not started here.
10. **The mutation sample.** One (path, line) pair per branch node. The list is sorted and drawn with `random.Random(20261102).sample(pairs, 25)` (659 branches). The probe worktree was cut at `15100c8`, and its `src/` matches `63162aa`. That worktree and its branch were removed after its files were copied to `.scratch/mutants/`.
11. **Every Phase 1 finding was re-run by the main session**, and every one reproduced. The minor findings listed under the table in BACKLOG.md do not enter the backlog.
12. **STOP 1 (2026-11-02): the owner approved the backlog as recommended.**
    - Phase 2 takes ranks 1-12 plus X30. Phase 3 takes ranks 14-43, except X32 and the doc items.
    - M1 names the second document in its refusal and does not read it.
    - X9 and X11 are left to the open per-visitor-sessions work: `open`, owned elsewhere.
    - C5 covers all 8 chat handlers. At zero, the table says "Neutral" and the text says "in line with budget" (memo, run-rate, compare, utilization, profitability, greeting) or "no change" (what-if, sensitivity).
    - X32 states the rounding on the sheet and changes no cell value.
    - X40 is left to the owner (`open`). X38 and X39 are `open` as proposed.
    - Draw G waits on the owner setting `EDGAR_USER_AGENT`.

## Phase 2 rules (written before each item's test)

**X1, footnote marks beside an amount.** Assisted reading applies NFKC to an amount only to fold full-width forms and odd spaces. A character that is not itself a decimal digit (Unicode category Nd) but folds under NFKC into ASCII digits is a mark beside the number, never part of it. That covers superscripts `¹²³`, subscripts `₁`, circled `①` and `⑩`, parenthesised `⑴`, and digit-with-stop `⒈`. A cell holding one is refused. The refusal names the row, the line, the column and the mark, so the reader can remove the mark. This keeps strict mode's answer, which already refuses such a cell. Silently reading the figure without the mark would be a transformation nobody approved, so the cell is refused instead.

Boundary cases:
- `９５０` (full-width digits, category Nd) still reads 950.
- `950` reads 950.
- `950¹`, `¹950`, `9²50`, `950₁`, `①`, `⑩` (no digit value, but NFKC gives "10"), `950⑴` and `950⒈` are refused.
- NBSP and other spaces fold as before.

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

## Phase 1 figures

- Six auditors. Findings returned, then kept after the main session's re-run: wrong numbers 8, then 8; Maya 10, then 10; contract drift 10 plus 4 small, then 10 plus 1; code health 10, then 4 kept (6 cost items merged as X37 and X38, and F10 is no defect); exposure 8, then 8. That makes 40 X items.
- Test strength: 3 of 25 mutants survived; the baseline for T2.
- Maya's scorecard over 25 fictional files:
  - 6 dead ends.
  - 3 runs reach an analysis with a wrong figure (f14, f19, f23).
  - One manual step (typing the period) in 16 of the 18 runs that reach an analysis.

## Looking at the outputs, Phase 0 and 1

- Report: no output changed. The re-run LTM report with `--layout` (`.scratch/rerun-contract/ltm_layout.md`) puts quarter figures under an "LTM Mar 2026" title.
- Workbook: unchanged. A filing's `--layout --xlsx` workbook carries totals the filing does not print.
- Chat reply: unchanged. The Sep-26 reply for f23 names Sep-26 and maps the YTD columns in the same summary.

## Revert proofs

| ID | Fix reverted | Test run | Result with the fix reverted |
|---|---|---|---|
| T1 | The test checks `1fc32b8`'s fix, so the proof re-introduces that fix's two costs one at a time. (a) `_SUGGEST_MAX_ITEMS = 10**9`: the suggestion cap removed. | `pytest tests/test_chat_hardening.py -k stay_fast` | 3 failed, 4 passed: `assert 120000 == 30000`, difflib comparisons growing with the file |
| T1 | (b) `_item_in_sentence` ignores the caller's `named` and recomputes the scan: an extra pass over the names. | same | 1 failed, 6 passed: `assert (80009 - 20009) <= (3 * (20000 - 5000))` |
| X1 | `_footnote_marks` and its check in `parse_assisted_decimal` removed (git checkout of `intake.py`), tests kept | `pytest tests/test_amount_forms.py` | 9 failed: `Failed: DID NOT RAISE ValueError` for each mark, and the intake test's message assertion fails |
| T1 | Load, the reason for the change: the old test beside 64 CPU-bound processes, then the new one. | `pytest ...::test_unmatched_questions_on_a_big_file_stay_fast` | old test: "5 failed, 2 passed" on each of 2 runs; new test: "7 passed" on each of 2 runs |

## Path existed in 0.2.0

The repository has no release tag. Released 0.2.0 is taken as `5e288bb` (2026-10-02), the last commit whose `version.py` reads `0.2.0`; the next commit, `ebda726`, sets `0.3.0`. Its `src/variance_agent/` holds only `__init__`, `analysis`, `audit`, `cli`, `currencies`, `models`, `numeric`, `output`, `parsing`, `report` and `version` (`git ls-tree --name-only 5e288bb src/variance_agent/`). There is no `comparisons.py`, `intake.py`, `excel.py`, chat or filing reader.

- **C2**: not in 0.2.0. `comparisons.read_comparison_input`, the earnings preset and `api.analyze_file` came later.
- **C3**: not in 0.2.0. There was no filing reader.
- A finding counts as on a 0.2.0 path only when the cause sits in one of the eleven modules above, on a CLI path that 0.2.0 already offered.

Post-T1 suite: 2505 passed in 47.31s (count unchanged).

## Looking at the outputs

One sentence each per phase, on one report, one workbook and one chat reply the phase changed.
