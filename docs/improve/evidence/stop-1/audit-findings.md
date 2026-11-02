# Phase 1 findings: reproductions

Each item lists its cause, the reproduction, and what the main session's re-run showed at `63162aa`. Every script and input is fictional and lives in the git-ignored `.scratch/` folder:

- `audit-numbers/`: wrong numbers
- `audit-maya/`: dead ends for Maya (`build_files.py`, `drive.py FILE`, `probes.py NAME`)
- `audit-contract/` and `rerun-contract/`: contract drift
- `audit-health/`: code health
- `mutants/`: test strength
- `audit-exposure/`: exposure (`launch_hosted.py PORT` and the `t_*.py` scripts, run with `AUDIT_PORT`)

A fix's test rebuilds its shape as a committed fictional fixture made by a script. These scratch files are not committed.

## Wrong numbers

- **X1** `intake.py:623`: NFKC runs before the number regex, so `950¹` becomes `9501` and `①` becomes `1`. Run `variance-agent .scratch/audit-numbers/superscript.csv --assisted --period "Q3 2026" --dollar-threshold 100 --percent-threshold 5`. Re-run: "Total Revenue: $9,501.00 vs. $900.00 ($8,601.00, 955.7%, F)". Strict mode refuses the cell.
- **X2** `scorecard.py:31-32`: `load_workbook(data_only=True)` plus `str(v)`. Run `.scratch/audit-numbers/scorecard_xlsx.py`. Re-run: the CSV gives "Beat | 12.4%" and "BRAVIK.FAKE (3%)"; the `.xlsx` with `0.00%` cells gives "(0.03%)".
- **X3** `pdf_tables.py:399` (the body starts after the title line) and `:413-421` (only `^\(.*\)$` counts as a caption). Run `.scratch/audit-numbers/pdf_caption.py`. Re-run: caption on its own line gives $1,250,400,000.00 with a note; on the title line, $1,250.40; unparenthesised, $1,250.40.
- **C2**: run `.scratch/c2/make.py .scratch/c2`, then the FP&A and earnings commands in `.scratch/c2/REPRO.txt`. Caption alone gives $1,234,000.00 on FP&A against $1,234.00 on earnings consensus, with no note there. Format alone and both are right on both paths.
- **C5** `handlers.py`, the `>= 0` / `<= 0` / `> 0 else 'Favorable'` ternaries at 3122, 3242, 3250, 3258, 3261 (`_handle_compare`), 4173 (`_handle_what_if`), 4235 (`_handle_sensitivity`), 4355, 4356, 4385, 4394, 4403 (`_handle_run_rate`), 4463, 4464, 4486, 4497, 4543, 4557 (`_handle_executive_memo`), 4637 (`_handle_greeting`) and 4809 (`_handle_profitability`); also 3122 (`_handle_budget_utilization`). `.scratch/audit-numbers/chat_zero_status.py` shows "Total Revenue ... $0.00 ... Status F" where the engine says Neutral.
- **X4** `intake.py:693-694` (`_THOUSANDS_RE`, `_MILLIONS_RE`). `.scratch/audit-numbers/captions.py` prints 32 variants. Re-run: `(000)`, `(£000)`, `(€000)`, `(in billions)` and `($ in billions)` all scale by 1. "Costs incurred in M&A" scales by 1,000,000. With `gbp_000.csv`, `--currency GBP` gives £1,350.00.
- **X5** `intake.py:653-659` has the symbol check, but its callers at 3113 and 3138 pass no `currency`. `.scratch/audit-health/eur_chat.py` (chat) shows "Currency: USD", "Total Revenue: $120.00 vs. $100.00" for `€` cells. Strict mode refuses ("currency EUR conflicts with reporting currency USD").
- **X6** `intake.py:1076-1082`: `detect_header_row` returns on the first synonym match, so the `selected_period` branch (1084-1110) never runs when the headers are direct synonyms ("Budget YTD", "Actual YTD"). Run `drive.py f23_month_and_ytd.xlsx`. Re-run: "Analyzed period: Sep-26" next to "Budget from 'Budget YTD', Actual from 'Actual YTD'".
- **X7** `intake.py:3265-3273` flips only revenue-named rows. Gross Profit and Net Income then fail `detect_subtotals_and_totals` (885-975) and land in `unreconciled_totals`, which is never shown. Run `drive.py f19_signed_subtotals.xlsx`. Re-run: "Total Revenue: $457,000.00 vs. $430,000.00", "Total Expenses: -$32,000.00 vs. -$50,000.00". Skip path: `probes.py combo_skip_more`.
- **X8** `cli.py:408-411` routes these runs to `_run_comparisons` (714-823), which never reads `ltm_from`, `compare_file`, `metrics`, `panel` or `multiple_threshold` and skips the filing guards in `_run` (497-524, 629-640). Two reproductions:
  - LTM: `variance-agent tests/fixtures/analysts/hal-20260328.htm --assisted --ltm-from tests/fixtures/analysts/hal-20250927.htm --period 'LTM Mar 2026' --dollar-threshold 1 --percent-threshold 1 --layout standard -o X.md`. Re-run: "Net sales ... $1,020,000,000.00 | $1,150,000,000.00" and no LTM build. Without `--layout`: $4,300,000,000.00 vs $4,100,000,000.00 and an LTM build.
  - Filing workbook: the 10-K plus `--layout standard --xlsx` writes a workbook and "Total Revenue / Total Expenses" lines; the plain run refuses `--xlsx`.
  - Same cause: `ines_limits.csv --assisted --compare-to limit --long-output` gives "No Limit column found. Columns found: ..., limit, ...". `multiple_b.csv --multiple-threshold 0.1 --long-output` gives "supply --multiple-threshold".
- **C1, C3**: reproduced in Phase 2 per the prompt.

## Exposure

- **X9** `server.py:181` (`session: ClassVar[Session]`), `483-484`; `session.py:4-5`. Run `.scratch/audit-exposure/t_hosted_shared.py` against `launch_hosted.py 18733`. Re-run: visitor B's "summary" returns A's analysis (Fictional Revenue A, $115,500.00). B's `reset` sends A back to "Please upload a file".
- **X10** `cli.py:332`. `RENDER=1 PORT=abc variance-agent --chat --no-browser` gives "PORT must be a port number between 1 and 65535, not 'abc'.", a message only the hosted branch prints.
- **X11** `server.py:50, 276-295`; the names are built at `handlers.py:2671, 2703, 2772, 2788`. Re-run: B's `GET /download/variance_report_q3_2026.md` gives 200 and A's report.
- **X12** `server.py:189-191, 410`. `t_size.py short`: dropped after 15.0 s; another client's GET waited 14.0 s. `t_size.py drip`: answered after 60.2 s; the other GET took 60.2 s.

## Dead ends

- **X13** `cli.py:301-318`. `variance-agent act.csv --assisted --compare-file bud.csv ... -o bud.csv` exits 0, and `bud.csv` now starts "# FP&A Variance Report: Q3".
- **X14** the earnings preset on `hal-20250927.htm` with `--audit-json`: the default gives "Audit schema 1.8 cannot record what the workbook examination found; use --audit-schema-version 1.9."; 1.9 gives "Comparison sets and new comparisons require audit schema 1.8."
- **X15** `parsing.py:271-272`. `pasted.tsv --assisted` gives "Unsupported input format '.tsv'. Use CSV, JSON, XLSX, or XLSM."
- **X16** `intake.py:2816, 2843-2846`. `drive.py f21_section_headers.xlsx` gives "Row 2, REVENUE, Actual column: the amount is blank."
- **X17** `handlers.py:516` and `parsing.py:392` leave out `.xls`. `.scratch/audit-health/xls_sheets.py`: for `book.xls`, "list sheets" gives "a XLS file, which contains a single dataset". The same bytes named `.xlsx` switch fine.
- **X18** `comparisons.py:391, 502` against `intake.py:157-173`. `Description,Budget,Forecast,Actual` passes with `--compare-to budget` and fails with `--compare-to budget,forecast`: "Could not find a Line Item and Actual header".
- **X19** `server.py:357` clears `_downloads` before `handle_upload`. `t_failed_upload.py`: the download gives 200, a broken upload is refused, the analysis is still there, and the same download gives 404.
- **X20** `number_formats.py:77-82`: the zero section `"-"` has divisor 1. `intake.py:3364` then requires every cell to agree. `.scratch/audit-numbers/zero_section.py`: with no zero the book reads, and with one zero Travel Actual it exits 2 with "number formats don't agree", listing the agreeing cells.
- **X21** `handlers.py:548-549, 643-646`; the message comes from `join.py:62-67`. `probes.py half_then_full` gives "'f13_var_columns.xlsx' already has a comparison column, so it isn't the actuals half of a pair. Run it on its own, without --compare-file." and no chips. Repeating it gives the same.
- **X22** `intake.py:3434-3490` (the summary leaves out `unreconciled_totals`) and `:3578-3588` (the rule 6 wording). `drive.py f20_rounded_thousands.xlsx` gives "Summary total for 'Total Opex' does not match the sum of its Expense detail rows detail rows."
- **X23** `intake.py:554-590`. `probes.py header_units`: "Budget ($000)", "Budget $000", "Budget ($K)", "Budget (in thousands)", "Budget $" and "Budget (USD)" fail; "FY26 Budget" reads.
- **X24** `intake.py:1047-1110, 1339-1343`. `probes.py merged_variants`: two-row headers fail with or without merges. `drive.py f17_date_headers.xlsx` gives "Could not determine period order for Sep 2026, Sep 2026."

## Misleading

- **X25** `handlers.py:2610, 2636`. In local mode, `export report ~/home_report.md` gives "Report written to `~/home_report.md`", and the file is at `<cwd>/~/home_report.md`.
- **X26** `server.py:264-271, 485, 495-497`. `t_initial.py`: after reset and a new upload, `/status` still carries the start-up `initial_response`.
- **X27** `responses.py:83, 87, 94`, `models.py:11, 18`, `analysis.py:680`, `handlers.py:1526, 2975, 3041`. `probes.py combo_skip_more`: Type "Unclassified" and Status "Unclassified" cells.
- **X28** `mapping.py:203`. A mapping holding `{oops` gives "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)".
- **X29** `cli.py:356`. `--check-only --long-output co.csv` gives "Validation passed: 5 rows, 1 comparison(s)." and no file.
- **X30** `ixbrl.py:425`, `ltm.py:199, 255-257`. `ltm_currency.py`: the main table shows €4,300,000,000.00, and the LTM build row shows $4,300,000,000.00.
- **X31** `intake.py:3187-3190`, `measures.py:91-96`. `pct_format.py`: `points` gives "0.4% | 0.425% | 2.5 bps | No"; `fractions` gives "40% | 42.5% | 250 bps | Yes".
- **X32** `report.py:66-79` against `xlsx.py:331, 343`. `pct_tie.py`: the workbook cells hold 0.1225 and 0.0245 (shown 12.3% and 2.5%), and the report shows 12.2% and 2.4%.
- **X33** README.md:167, 295. **X34** input-contract.md:172 against cli.py:409.

## Unpinned (T2): the mutants that survived

See [mutation-sample.md](mutation-sample.md).

## Cost

- **X35** `handlers.py:346-349, 893-896` asks for the period with no chips. `probes.py period_text` shows the captured title text "Q3 2026" for f03.
- **X36** `join.py:19, 93-100`. `probes.py two_files_reverse` gives "In 'f06b_actual_only.xlsx' but not in 'budget_partial.xlsx': 5000 (Cost of Goods Sold), ... run again."
- **X37** `intake.py:191` `_MISSING_MARKERS`, which nothing references. `handlers.py:4107-4109`: `LineType` has 3 members, and UNCLASSIFIED returns at 4047.
- **X39** `t_memory_steps.py PID fixture_100k.csv` on a fresh hosted process: 49 MiB at start, 169 after upload, 269 after analysis, 559 after `export excel`.
- **X40** `render.yaml:6` `pip install ".[excel,pdf]"`; `.gitignore:15` `uv.lock`.
