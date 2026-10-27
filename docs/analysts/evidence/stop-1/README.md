# STOP 1 (after Phase 3), 2026-10-26

Branch `analysts/filings-and-excel`, sweep at tool commit `3439e0e` (the code is identical at `13de5e8` apart from the chat panel's "Statement" wording). Aggregates only: per-filing rows, renders and the fresh-eyes report live in `~/vaa-edgar-corpus/stop-1/` (constraint 7).

## Draw A, before and after (40 filings, seed 20261026)

| Reader | Measure | Before (Phase 1 tool, `a4791bb`) | After (`3439e0e`) |
|---|---|---|---|
| Inline XBRL primary `.htm` | statement runs | 116, all refused plainly | 116: 25 read, 91 refused plainly (balance sheets and cash flows until Phase 4; 6 documents without Inline XBRL) |
| | lines verified / unverified / wrong | 0 / 0 / 0 | **677 / 13 / 0** |
| | income statements read (33 Inline XBRL filings) | 0 | **24 (73%, Wilson 95% 56–85%)**; 20 fully verified and covered (61%, 44–75%) |
| `Financial_Report.xlsx` (6 filings from 2018) | lines verified / unverified / wrong | 186 / 63 / **15** | **169 / 7 / 0** |

Results file sha256 (after): `c520ca971990cbf36bec7ef833d6b663369bfc1b766dbe532622c8fc52508b99`. Before: see `../draw_A_baseline.json`.

## Fresh eyes

Five Draw A Inline XBRL filings drawn with `random.Random(20261027).sample`. A subagent given none of the plan's reasoning checked the tool's income-statement outputs against each filing's printed statement and XBRL instance, defaulting to "wrong" under doubt. Result: FRESH_EYES_RESULT

## Renders

Three Draw A income statements rendered by the tool beside EDGAR's own R page: `~/vaa-edgar-corpus/stop-1/render_<accession>.html`.

## Browser check

`shots/`: the screens Phases 1 and 3 changed, at 1280 and 375 px: an HTML filing's read summary and statement list, the hidden-rows question and its answer, and the formula refusal. Every file uploaded is fictional (`docs/analysts/evidence/shots_analysts.py`).

## Gates

`sh docs/ui/evidence/gates.sh dist`: ruff, mypy (65 files), pytest **2311 passed**, compileall, pip check, contracts (19 unchanged), build, twine, distribution, and both artifacts installed without the Excel and PDF extras: all PASS. `mypy --strict docs/analysts/evidence/` is clean.
