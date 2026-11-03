# Local verification after the second final STOP (Decision 22)

The owner answered "do what you recommend". This folder holds the checks of the "Not verified" items that this Mac (macOS, Apple silicon) could run without a push. Nothing in `src/` or `tests/` changed for them.

## CI's test job on Python 3.12, 3.13 and 3.14

`ci_test_job.sh` runs the steps of `.github/workflows/ci.yml`'s `test` job in a scratch venv per Python: ruff, `mypy --strict src/variance_agent scripts deterministic_conditioning`, compileall, pytest and `pip check`. Each venv was installed with `-c requirements-typecheck.txt -e ".[dev,excel,pdf]"`. 3.13 and 3.14 came from uv's cache. 3.12 needed one wheel the cache lacked (cffi 2.1.1, from PyPI). The tree was `2682603` plus two uncommitted docs edits (PLAN.md's Decision 22 and the screenshot harness), so `src/` and `tests/` were `2682603`'s. Output, verbatim, in `ci-test-job.txt`:

| Python | ruff | mypy --strict | compileall | pytest | pip check |
|---|---|---|---|---|---|
| 3.12.14 | All checks passed! | no issues found in 90 source files | exit 0 | 2906 passed in 66.14s | No broken requirements found. |
| 3.13.15 | All checks passed! | no issues found in 90 source files | exit 0 | 2906 passed in 133.25s | No broken requirements found. |
| 3.14.0 | All checks passed! | no issues found in 90 source files | exit 0 | 2906 passed in 102.87s | No broken requirements found. |

The suite ran while the browser shots below were taken, at load averages of 10 to 61, so the durations are not comparable with the gates' 47 seconds. This is macOS, not CI's Ubuntu. CI's own run on draft PR #28 later passed every job at `be28fe4`, the Windows output-contract job included (REPORT.md, "CI on draft PR #28").

## The chat screens in WebKit and Firefox

`docs/ui/evidence/shots.py` takes `VAA_SHOTS_ENGINE` (chromium by default) and, after every shot, records how many pixels the page, a reply, a results section or a facts grid runs wider than its own box. A table inside its scrolling wrapper does not count. Phase 8's six scenarios and Phase 5's three export scenarios, desktop (1280 by 800) and phone (375 by 760), were shot in each engine:

    VAA_SHOTS_ENGINE=webkit ~/.venvs/vaa-shots/bin/python docs/improve/evidence/phase-8/shots_phase8.py docs/improve/evidence/verify-local/webkit
    VAA_SHOTS_ENGINE=webkit ~/.venvs/vaa-shots/bin/python docs/improve/evidence/phase-5/shots_phase5.py docs/improve/evidence/verify-local/webkit <files>

| Engine (Playwright 1.60 build) | Scenario runs | Screenshots | Widest overflow |
|---|---|---|---|
| Chromium 148.0.7778.96 (baseline, not kept) | 18 | 31 | 0 px |
| WebKit 26.4 (`webkit-2287`) | 18 | 31, in `webkit/` | 0 px |
| Firefox 150.0.2 (`firefox-1522`) | 18 | 31, in `firefox/` | 0 px |

**The measure can see an overflow.** With X52's CSS fix reversed (`git apply -R` of `c70c5ac`'s `chat.css` diff) and restored after, the target and limit results panels measured:

| Scenario | Chromium | WebKit | Firefox |
|---|---|---|---|
| x46-percent-tolerance, desktop / phone | 242 / 322 px | 249 / 322 px | 242 / 322 px |
| x47-limit-bps, desktop / phone | 210 / 290 px | 217 / 290 px | 210 / 290 px |

These are Playwright's engines, not Safari or Firefox as shipped, and not an iPhone.

## Microsoft Excel

The workbooks (X32's tie, the FP&A sample, N1's three exports, and the X46 and X47 exports, all from fictional files) were written to the session scratchpad and the read-back was to go through Excel 16.114.3's own `string value` (the text a cell shows). The first scripted open timed out, and the owner declined computer-use access to Excel. Real Excel stays not verified.
