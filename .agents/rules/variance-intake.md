# Variance Analysis Agent intake overhaul: standing rules

<project>
The Variance Analysis Agent is an MIT-licensed Python tool for deterministic budget-versus-actual analysis. It reads CSV, JSON, XLSX or XLSM and writes a Markdown report plus an optional versioned audit JSON.

Layout:
- `src/variance_agent/parsing.py`: capture, headers, aliases, numbers
- `src/variance_agent/excel.py`: workbook preflight and stored decimals
- `src/variance_agent/analysis.py`: variances, classification, summaries, drivers
- `src/variance_agent/report.py`, `audit.py`, `output.py`: report, audit and file writing
- `src/variance_agent/cli.py`: the command line
- `src/variance_agent/chat/`: the deterministic chatbot (`handlers.py`, `session.py`, `intent.py`, `server.py`). The UI is `static/chat.html`, with an identical copy at `src/variance_agent/static/chat.html`.
- Documentation: `docs/input-contract.md`, `docs/financial-rules.md`, `docs/audit-contract.md`. Schemas: `schemas/audit-1.x.schema.json`.

The goal is to make getting budget-vs-actual data into the tool easy for a non-technical analyst. The task prompt names the phase. The `deterministic_conditioning/` folder is out of scope.
</project>

<target_user>
The work is for "Maya," an FP&A analyst. Maya is the end user, not a role for you to play.
- She is expert in Excel and accounting but not technical: no command line, no JSON, no Python error text.
- She uses the chatbot (`variance-agent --chat`) and drags in whatever her ERP, planning tool or controller sent.
- Her files have a title block above the header row and columns such as "GL Account," "Account Description," "Budget YTD," "Actual YTD," "Var $," "Var %," "Sep-26 Actual" and "Q3 Budget."
- They contain nested subtotals ("Total Revenue," "Gross Profit," "Total Opex," "Net Income"), and they are often signed ledgers where revenue is negative.
- Amounts are often in thousands. A dash means zero. Unbudgeted lines have a blank budget.
- Budget and actuals sometimes arrive as two separate files.
- She gives up after one confusing error.

Judge every choice by whether it cuts her steps, reformatting or confusion between "I have a file" and "here are my material variances."
</target_user>

<hard_constraints>
These apply in every phase and outrank the task prompts.
1. Use synthetic data only, and label every new fixture and example as fictional.
2. Everything stays deterministic: synonym tables, normalization and explicit rules. There are no model calls and no network calls at runtime. CSV and JSON paths use the standard library only. Excel stays the optional `[excel]` extra.
3. Financial values are `Decimal`, created from strings or stored XML decimal text, inside `numeric.py`'s financial context. Unit scaling and sign flips are exact Decimal operations. Float is never used for an amount.
4. **Every transformation is proposed, visible and confirmed.** That covers a detected header row, a column mapping, a sign flip, a unit scale, a dash or blank read as zero, an excluded subtotal, a joined file and a bulk classification. The chat shows each one and Maya confirms before analysis. Each one is recorded in the audit JSON.
5. **CLI defaults stay the same.** For existing inputs and flags, the reports and audits must match the files in `tests/fixtures/contracts/` byte for byte. New CLI behavior is opt-in through new flags or a mapping file. The chat may use the assisted path by default.
6. **Audit versions:** published schemas `audit-1.0` through `audit-1.4` stay unchanged. Record new provenance in a new schema version (1.5) that keeps `additionalProperties: false`, and keep older versions selectable.
7. **Financial rules stay unchanged:** variance, percentage, materiality, favorability, aggregation, summary reconciliation tolerance and driver models, as documented in `docs/financial-rules.md`. Intake work changes how rows reach those rules, never the rules themselves.
8. **Safety stays in place:** keep the 32 MiB capture, row, column and cell limits, the archive and XML preflight, and the escaping of untrusted labels. New inputs (pasted text, second files, mapping files) get equivalent limits. Hosted mode keeps refusing path exports.
9. Keep both `chat.html` copies identical. Add a test that fails if they differ.
10. **Test first, then change.** Use pytest and the existing fixtures. Use exact Fraction-oracle properties for any new arithmetic. Keep existing tests and assertions as they are. CI must stay green on Python 3.11–3.14 and Windows.
</hard_constraints>

<definitions>
- **Dead end**: Maya ends up with no analysis and no fix action on screen. Only a file that truly can't be read counts as an acceptable dead end.
- **Manual step**: one action Maya takes outside the chat (editing the file, adding a column, re-saving, re-uploading) or one chat reply typed beyond confirming. Clicking a suggested chip counts as half a step.
- **Jargon**: any of the following in a message Maya sees:
  - a snake_case key or `repr()` quoting such as `'budget_ytd'`
  - an exception name
  - CLI flag syntax, unless she is told it is optional
  - any of the words "normalize," "alias," "schema," "OOXML," "archive," "XML," "DTD," "payload," "Row Kind," "Unclassified" (use "not yet labeled revenue or expense")
  - an exit code
- **Plain-language message**: states the problem in accounting terms, points to the location the way a person would ("row 14, Marketing — Digital, Budget column"), gives the exact fix and, where possible, a chip that applies it. It never blames Maya. Error detail can sit behind a "Show technical details" chip.
- **Visible transformation**: anything the tool inferred or changed. It is listed in the "Here's how I read your file" summary before analysis.
</definitions>

<source_of_truth>
The repository code is the source of truth. Task prompts describe commit `a3ce6bb`. Before relying on a described behavior, open the file and confirm it. When the code differs, follow the code and record the difference in the Implementation Plan.
</source_of_truth>

<tool_policy>
- **Do freely:** read and search files, and run tests, linters, type checks and builds.
- **Edit only the files listed in the approved Implementation Plan.** To touch another file, add it to the plan with a reason first.
- **Before reporting a phase complete, run:**
  - `python -m pytest -q`
  - `python -m ruff check .`
  - `python -m mypy --strict src/variance_agent scripts`
  - `python -m compileall -q src tests scripts`
  - `python -m pip check`
  - `python -m build --outdir dist`, then `python -m twine check dist/*` and `python scripts/check_distribution.py dist`
  - `scripts/check_installation.py --without-excel`, in a separate non-editable installation without the Excel extra
  - Use `.github/workflows/ci.yml` as the reference if a command has changed.
- **Report test results only from commands you actually ran, with their summary lines pasted in.** If a command fails or can't run, report that and include its output.
- **Check the chatbot in the browser** (`variance-agent --chat`) at 1280 px and 375 px for every changed screen. Include screenshots or a recording in the Walkthrough.
- **Git:** pushing, merging and rewriting history need my approval. Use branches named `intake/phase-N-<short-name>`.
</tool_policy>

<stop_and_ask>
Before doing any of the following, stop and write one paragraph with your recommendation:
- changing a financial rule, a tolerance, or an existing audit schema or report contract fixture;
- changing a CLI default;
- adding a dependency;
- changing anything in `deterministic_conditioning/`;
- concluding that some layout needs matching that isn't deterministic.

For everything else, decide, write down which interpretation you took in the Implementation Plan, and continue.
</stop_and_ask>

<output_standards>
- **Implementation Plan:** the files to touch, the failing tests to write first, the risks and open questions.
- **Walkthrough:**
  - what changed for Maya, in plain English
  - the friction scorecard before and after, per fixture (dead end yes/no, manual steps, first message shown)
  - pasted command output
  - screenshots or a recording
  - every stop-and-ask decision
- **PR description:** the same content, with jargon removed from the "what changed" section. Add a CHANGELOG entry under the unreleased version.
</output_standards>
