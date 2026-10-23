# Multi-audience implementation report — October 2026

Phases 0–8 are implemented on local branch `feat/multi-audience`, based on
`f5cd79c24b22197932c657edf3fd9a6a7dcefd4d`. Both optional phases, history statistics
and filing EPS/share counts, were retained at STOP 3. No phase was dropped.
Version remains **0.3.0, unreleased**. No push, merge, tag, release or hosted
publication was performed. This report is the review material for **STOP 4**.

All test counts, command outputs, byte counts and durations below are **measured**
in this environment. Fixture amounts are fictional supplied examples. Count
increases are arithmetic differences between measured collections. No estimated
performance or total-session-duration claim is made.

## What shipped, by phase

| Phase | Readers and behavior | Local commits | Tests added or expanded; measured full-suite count |
|---|---|---|---|
| 0 | Baseline, read-only probes, design and STOP 1 | `c3309dd` | Baseline: 1,772 |
| 1 | Priya: Per Share, Percent/bps, Count, Better and required cutoffs; Maya compatibility | `188d26a` | Measures, strict threshold straddles, Fraction bps, unit-aware report/Excel/audit/chat/mapping; 1,815 |
| 2 | Priya/Dan: supplied Consensus, Estimate, Guidance, periods and explicit comparison sets | `8b309b6` (STOP 2), `87e6a52` | Scenario A/B, loss EPS, exact midpoint/range ends, ambiguous Est., raw # Est., sets/missing bases, period forms, mapping and closed audit children; 1,862 |
| 3 | Priya/Dan: flat segments and scoped reconciliation | `7da87b6` | Cross/same-segment duplicates, summaries, no fabricated consolidation, nested refusal, report/Excel/audit joins; 1,876 |
| 4 | Wei: typed table/file/panel APIs and exact long CSV/JSONL | `fe61da2` | Signature pins, global limits, failure isolation, Scenario C, byte determinism, nulls, ordering, formula text and path protection; 1,908 |
| 5 | Wei: descriptive history and dispersion surprise | `4a1a884` | Scenario D, Fraction variance/sqrt brackets, 3/4-prior minimum, zero deviation, ordering/exclusions, units, source and tamper checks; 1,921 |
| 6 | Maya/Priya/Dan: presets, earnings layouts, structured chat and knowledge routes | `78565b9`, `884561c` | Explicit defaults/overrides, metadata gates, quant output, six topics, routing, Scenario B chat and exports; 1,950 |
| 7 | Priya: opted-in exact filing EPS and weighted average share counts | `87a239c` | Eight cases: extraction/cache off/on, independent units, money-only shaping, direction/mapping, API/CLI/chat provenance and legacy off bytes; 1,958 |
| 8 | All readers: documentation, reader commands, final evidence; adapter fixes for Priya/Wei | `803b1b3` plus the final documentation commit containing this report | Six CSV/JSON single/set mapping and dispersion-option regressions; 1,964 |

The final documentation commit can identify itself without a circular embedded
hash: `git log -1 --format='%h %s' -- docs/MULTI_AUDIENCE_2026-10.md`.
The [implementation plan](superpowers/plans/2026-10-21-multi-audience.md) retains
phase-by-phase commands, red tests, decisions, stops and corrections.

The full suite increased by **192** cases: **178** cases are collected from new
`tests/test_multi_audience*.py` files; the remaining **14** come from existing
parameterized tests naturally expanding over selectable schemas/knowledge.
Original assertions remain unchanged except the owner-approved one-line
schema-1.6 parameter scope. The explicitly requested fixture producer extension
adds the new fictional PDF without regenerating existing PDFs.

Two checkpoint issues are preserved in the plan. Phase 6 was committed before a
new fixture string's lint failure was fixed; `884561c` corrected formatting and
reran the full union gate without rewriting history. In Phase 8, six new adapter
cases first failed, then passed; the first full run also found the final report
link before this file existed (1 failed, 1,963 passed). Creating the report
resolved that link; the successful full rerun is pasted below.

## Reader commands, actually executed

Commands ran from the repository with `.venv/bin` on PATH. Maya, Priya and Dan
exit 0. Wei deliberately exits 3 for the fictional bad quarter. The exact Wei
execution below uses temporary destinations to avoid leaving generated data in
the checkout; the README uses the equivalent relative output filenames.
Currency figures in these small scenario files are supplied in millions. They
are displayed in supplied units; EPS, percentage points and counts retain their
own units. Nothing in a vendor export is assumed to establish GAAP/adjusted or
fiscal/calendar comparability.

### Maya — existing budget review

```sh
variance-agent tests/fixtures/multi_audience/fpa.csv --period 3Q26 --dollar-threshold 10 --percent-threshold 2
```

Measured exit: **0**. Captured stdout:

```text
# FP&A Variance Report: 3Q26

## Executive Summary
- Reporting Currency: USD
- Total Revenue: $1,287.50 vs. $1,250.00 ($37.50, 3.0%, F)
- Total Expenses: $383.00 vs. $380.00 ($3.00, 0.8%, U)
- Bottom Line Impact: Revenue and expense variances imply a net operating variance of $34.50, above budget on this simplified revenue-less-expense basis. The largest material variance is Revenue at $37.50 (F).

## Material Variances
Thresholds: $10.00 or 2.0%

| Line Item | Type | Budget | Actual | Var ($) | Var (%) | Status |
|---|---|---:|---:|---:|---:|---|
| Revenue | Revenue | $1,250.00 | $1,287.50 | $37.50 | 3.0% | F |

## Root Cause Analysis
- **Revenue (Hypothesis):** No causal driver is asserted from the supplied data. To validate a cause, provide volume/units, price/rate, customer count, and mix.

## Strategic Recommendations
- Mitigation: No material U variance is available for a data-backed action.
- Optimization: Revenue is the largest material F variance, but the dataset does not support a causal corrective action; obtain the missing operating driver data before assigning a cause-specific intervention.
- Data Request: Provide reconciled operating driver metrics for: Revenue.
```

### Priya — supplied consensus

```sh
variance-agent tests/fixtures/multi_audience/consensus.csv --preset earnings --compare-to consensus --period 3Q26 --dollar-threshold 10 --percent-threshold 2 --bps-threshold 25 --per-share-threshold 0.01 --count-threshold 1000
```

Measured exit: **0**. Captured stdout:

```text
# Earnings Review: 3Q26

## Headline comparisons

| Line Item | Segment | Measure | Actual | Consensus comparison | Consensus variance | Consensus % / bps | Consensus outcome |
|---|---|---|---|---|---|---|---|
| Revenue |  | Currency | $1,287.50 | $1,250.00 | $37.50 | 3.0% | Beat |
| Gross Margin |  | Percent | 40.6% | 41.2% | -60 bps | -60 bps | Miss |
| Diluted EPS |  | Per Share | $0.91/sh | $0.84/sh | $0.07/sh | 8.3% | Beat |

## Other KPIs

| Line Item | Segment | Measure | Actual | Consensus comparison | Consensus variance | Consensus % / bps | Consensus outcome |
|---|---|---|---|---|---|---|---|
| Operating Expenses |  | Currency | $383.00 | $380.00 | $3.00 | 0.8% | In line |
| Units Shipped |  | Count | 46,500 units | 48,000 units | -1,500 units | -3.1% | Miss |

## How the file was read

- Comparing Actual against Consensus.
- Using earnings layout; read headline rows: revenue, gross margin, diluted eps. Per-share filing lines on.
- Revenue: read Measure as Currency.
- Operating Expenses: read Measure as Currency.
- Gross Margin: read Measure as Percent.
- Gross Margin: read % values as percentage points.
- Gross Margin: read Better to Higher.
- Diluted EPS: read Measure as Per Share.
- Diluted EPS: read Better to Higher.
- Units Shipped: read Measure as Count.
- Units Shipped: read Better to Higher.
```

Captured stderr:

```text
[comparison intake] Comparing Actual against Consensus.
[comparison intake] Using earnings layout; read headline rows: revenue, gross margin, diluted eps. Per-share filing lines on.
[measure intake] Revenue: read Measure as Currency.
[measure intake] Operating Expenses: read Measure as Currency.
[measure intake] Gross Margin: read Measure as Percent.
[measure intake] Gross Margin: read % values as percentage points.
[measure intake] Gross Margin: read Better to Higher.
[measure intake] Diluted EPS: read Measure as Per Share.
[measure intake] Diluted EPS: read Better to Higher.
[measure intake] Units Shipped: read Measure as Count.
[measure intake] Units Shipped: read Better to Higher.
```

### Dan — three supplied comparisons

```sh
variance-agent tests/fixtures/multi_audience/comparison_set.csv --preset earnings --compare-to consensus,estimate,prior-period --period 3Q26 --dollar-threshold 10 --percent-threshold 2 --per-share-threshold 0.01
```

Measured exit: **0**. Captured stdout:

```text
# Earnings Review: 3Q26

## Headline comparisons

| Line Item | Segment | Measure | Actual | Consensus comparison | Consensus variance | Consensus % / bps | Consensus outcome | Estimate comparison | Estimate variance | Estimate % / bps | Estimate outcome | Prior Period comparison | Prior Period variance | Prior Period % / bps | Prior Period outcome | Estimate - Consensus | Estimate - Consensus % / bps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Revenue |  | Currency | $1,287.50 | $1,250.00 | $37.50 | 3.0% | Beat | $1,260.00 | $27.50 | 2.2% | F | $1,190.00 | $97.50 | 8.2% | F | $10.00 | 0.8% |
| Diluted EPS |  | Per Share | $0.91/sh | $0.84/sh | $0.07/sh | 8.3% | Beat | $0.88/sh | $0.03/sh | 3.4% | F | $0.80/sh | $0.11/sh | 13.8% | F | $0.04/sh | 4.8% |

## Prior year / prior period

| Line Item | Segment | Measure | Actual | Consensus comparison | Consensus variance | Consensus % / bps | Consensus outcome | Estimate comparison | Estimate variance | Estimate % / bps | Estimate outcome | Prior Period comparison | Prior Period variance | Prior Period % / bps | Prior Period outcome | Estimate - Consensus | Estimate - Consensus % / bps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Revenue |  | Currency | $1,287.50 | $1,250.00 | $37.50 | 3.0% | Beat | $1,260.00 | $27.50 | 2.2% | F | $1,190.00 | $97.50 | 8.2% | F | $10.00 | 0.8% |
| Diluted EPS |  | Per Share | $0.91/sh | $0.84/sh | $0.07/sh | 8.3% | Beat | $0.88/sh | $0.03/sh | 3.4% | F | $0.80/sh | $0.11/sh | 13.8% | F | $0.04/sh | 4.8% |

## Other KPIs

No supplied rows in this section.

## How the file was read

- Comparing Actual against Consensus.
- Comparing Actual against Estimate.
- Comparing Actual against Prior Period.
- Using earnings layout; read headline rows: revenue, diluted eps. Per-share filing lines on.
- Revenue: read Measure as Currency.
- Diluted EPS: read Measure as Per Share.
- Diluted EPS: read Better to Higher.
```

Captured stderr:

```text
[comparison intake] Comparing Actual against Consensus.
[comparison intake] Comparing Actual against Estimate.
[comparison intake] Comparing Actual against Prior Period.
[comparison intake] Using earnings layout; read headline rows: revenue, diluted eps. Per-share filing lines on.
[measure intake] Revenue: read Measure as Currency.
[measure intake] Diluted EPS: read Measure as Per Share.
[measure intake] Diluted EPS: read Better to Higher.
[measure intake] Revenue: read Measure as Currency.
[measure intake] Diluted EPS: read Measure as Per Share.
[measure intake] Diluted EPS: read Better to Higher.
[measure intake] Revenue: read Measure as Currency.
[measure intake] Diluted EPS: read Measure as Per Share.
[measure intake] Diluted EPS: read Better to Higher.
```

### Wei — isolated panel

```sh
variance-agent tests/fixtures/multi_audience/panel.csv --preset quant --group-by Ticker,Period --compare-to consensus --dollar-threshold 10 --percent-threshold 2 --bps-threshold 25 --per-share-threshold 0.01 --count-threshold 1000 --long-output /workspace/scratch/61f04cd678fb/phase0-evidence/reader-panel.csv --long-output-jsonl /workspace/scratch/61f04cd678fb/phase0-evidence/reader-panel.jsonl --errors-output /workspace/scratch/61f04cd678fb/phase0-evidence/reader-errors.csv
```

Measured exit: **3**. Captured stdout:

```text
(empty)
```

Captured stderr:

```text
[panel intake] Comparing Actual against Consensus.
Panel: 5 successful groups; 1 failed groups.
```

Written long CSV:

```csv
Ticker,Period,line_item,segment,measure,basis,comparison_present,comparison,actual,variance,variance_percent,variance_bps,status,material,display_label,source_sha256
BRWB.FAKE,2Q26,Revenue,,Currency,consensus,true,100,120,20,0.2,,F,true,Beat,aa11301e22e04c5a09d23a96702d74b59b7cbc279b8bc93385ee51dcbf6842ab
BRWB.FAKE,3Q26,Revenue,,Currency,consensus,true,100,105,5,0.05,,F,true,Beat,aa11301e22e04c5a09d23a96702d74b59b7cbc279b8bc93385ee51dcbf6842ab
CORD.FAKE,2Q26,Revenue,,Currency,consensus,true,500,520,20,0.04,,F,true,Beat,aa11301e22e04c5a09d23a96702d74b59b7cbc279b8bc93385ee51dcbf6842ab
HALV.FAKE,2Q26,Revenue,,Currency,consensus,true,1250.0,1287.5,37.5,0.03,,F,true,Beat,aa11301e22e04c5a09d23a96702d74b59b7cbc279b8bc93385ee51dcbf6842ab
HALV.FAKE,3Q26,Revenue,,Currency,consensus,true,1250.0,1287.5,37.5,0.03,,F,true,Beat,aa11301e22e04c5a09d23a96702d74b59b7cbc279b8bc93385ee51dcbf6842ab
```

Written error CSV:

```csv
Ticker,Period,error,source_sha256
CORD.FAKE,3Q26,Revenue: field 'Actual' has an invalid numeric format: 'TBD'.,aa11301e22e04c5a09d23a96702d74b59b7cbc279b8bc93385ee51dcbf6842ab
```

Two runs: CSV, JSONL and errors bytes identical; five successful groups, one error, exit 3.

### Supplied-history example, actually executed

The API also ran Scenario D with both windows. This is descriptive scaling of
supplied EPS surprises, independent of status/materiality. The minimum/history,
zero-deviation and Decimal/Fraction tests cover the null/rounding boundaries.

```python
from decimal import Decimal
from variance_agent import analyze_file
from variance_agent.api import AudienceOptions
from variance_agent.audience import AudienceConfig
from variance_agent.surprise import SurpriseOptions, load_history
cfg = AudienceConfig('3Q26', Decimal('10'), Decimal('.02'),
                     per_share_threshold=Decimal('.01'), bps_threshold=Decimal('25'),
                     count_threshold=Decimal('1000'))
for window in (8, 4):
    table = analyze_file('tests/fixtures/multi_audience/consensus.csv', cfg,
        options=AudienceOptions(surprise=SurpriseOptions(
            history=load_history('tests/fixtures/multi_audience/history.csv'), window=window)))
    eps = next(s for s in table.statistics if s.line_item == 'Diluted EPS')
    print(f'Window {window}: prior_count={eps.prior_count}, '
          f'sample_variance={eps.sample_variance}, standardized={eps.standardized_surprise:.4f}')
```

```text
Window 8: prior_count=8, sample_variance=0.0006, standardized=2.8577
Window 4: prior_count=4, sample_variance=0.00075833333333333333333333333333333333333333333333333, standardized=2.5420
```

## Compatibility proof

This exact command compares every contract fixture against its baseline Git
object; it checks bytes, independently of pytest's expected-output logic.

```sh
.venv/bin/python - <<'PY'
from pathlib import Path
import subprocess
base = 'f5cd79c24b22197932c657edf3fd9a6a7dcefd4d'
paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', base,
                                 'tests/fixtures/contracts'], text=True).splitlines()
assert len(paths) == 19
for name in paths:
    assert Path(name).read_bytes() == subprocess.check_output(['git', 'show', base + ':' + name]), name
print('19 contract files match f5cd79c byte for byte')
PY
```

```text
19 contract files match f5cd79c byte for byte
```

An extended byte check used the same Git-object comparison for all original
non-producer fixtures, schemas, tests, dependency manifests and the out-of-scope
package. It permits exactly `(B, F, P)` in the approved schema test; for the PDF
producer it verifies the old prefix and main function after removing only
`build_fixture_t()`, the new function and its printed label. A separate sample
analysis uses `AnalysisConfig('Q3 2026', Decimal('10000'), Decimal('.05'))` and
compares rendered Markdown, serialized audit and XLSX SHA-256 against the
Phase-0 captures. Executed output:

```text
19 contract files match f5cd79c byte for byte
58 existing non-producer fixture files match byte for byte
8 published schemas, 26 deterministic_conditioning files and dependency manifests unchanged
All original test source unchanged except the owner-approved one-line schema-1.6 scope
Fixture producer changes are limited to new build_fixture_t and its invocation/label
Legacy sample report SHA-256: 63f5d2d61de895f715d8270d948fb1b6d54208fa582f461c95a4e49b637d8587 (matches baseline)
Legacy sample audit SHA-256: 3420b6d4e77dab921dfb683feb7241f8cece1c298d86c2c9f01f951d2c829c7c (matches baseline)
Legacy sample xlsx SHA-256: 11db3182fb2f5b377e7973016e9b51fc0780e96fd80d6b3471e1c6633025ee43 (matches baseline)
```

## Final verification

Baseline command `.venv/bin/python -m pytest -q` at `f5cd79c` produced:

```text
1772 passed in 37.72s
```

Final environment: Linux x86_64, Python 3.12.14. The existing pinned extras were
installed with the README command below; no dependency manifest changed. The
installer completed with `Successfully installed variance-analysis-agent-0.3.0`.
Every verification command below exited 0. Output is pasted from the commands;
empty successful commands are identified explicitly.

```sh
.venv/bin/python -m pip install -c requirements-typecheck.txt -e '.[dev,excel,pdf,release]'
```

### Full tests

```sh
.venv/bin/python -m pytest -q
```

```text
........................................................................ [  3%]
........................................................................ [  7%]
........................................................................ [ 10%]
........................................................................ [ 14%]
........................................................................ [ 18%]
........................................................................ [ 21%]
........................................................................ [ 25%]
........................................................................ [ 29%]
........................................................................ [ 32%]
........................................................................ [ 36%]
........................................................................ [ 40%]
.................................................................----------------------------------------
....... [ 43%]
........................................................................ [ 47%]
........................................................................ [ 51%]
........................................................................ [ 54%]
........................................................................ [ 58%]
........................................................................ [ 62%]
........................................................................ [ 65%]
........................................................................ [ 69%]
........................................................................ [ 73%]
........................................................................ [ 76%]
........................................................................ [ 80%]
........................................................................ [ 84%]
........................................................................ [ 87%]
........................................................................ [ 91%]
........................................................................ [ 95%]
........................................................................ [ 98%]
....................                                                     [100%]
1964 passed in 40.32s
```

### Lint

```sh
.venv/bin/python -m ruff check .
```

```text
All checks passed!
```

### Strict types

```sh
.venv/bin/python -m mypy --strict src/variance_agent scripts deterministic_conditioning
```

```text
Success: no issues found in 62 source files
```

### Compilation

```sh
.venv/bin/python -m compileall -q src tests scripts deterministic_conditioning
```

```text
(no output; exit 0)
```

### Dependency consistency

```sh
.venv/bin/python -m pip check
```

```text
No broken requirements found.
```

### Build

```sh
.venv/bin/python -m build --outdir dist
```

```text
* Creating isolated environment: venv+pip...
* Installing packages in isolated environment:
  - hatchling==1.32.4
* Getting build dependencies for sdist...
* Installed build dependency versions:
  - hatchling==1.32.4
* Building sdist...
* Building wheel from sdist
* Creating isolated environment: venv+pip...
* Installing packages in isolated environment:
  - hatchling==1.32.4
* Getting build dependencies for wheel...
* Installed build dependency versions:
  - hatchling==1.32.4
* Building wheel...
Successfully built variance_analysis_agent-0.3.0.tar.gz and variance_analysis_agent-0.3.0-py3-none-any.whl
```

### Metadata

```sh
.venv/bin/python -m twine check dist/*
```

```text
Checking dist/variance_analysis_agent-0.3.0-py3-none-any.whl: PASSED
Checking dist/variance_analysis_agent-0.3.0.tar.gz: PASSED
```

### Distribution contents

```sh
.venv/bin/python scripts/check_distribution.py dist
```

```text
Wheel/sdist contents, license, Python support, and entry point verified
```

### Separate non-editable installations

Source install used the separate minimal environment created in Phase 0.
Wheel and sdist each used a fresh separate environment, as CI does. None has
Excel/PDF installed. Each command below succeeded; installer chatter is omitted
and each executed smoke/pip-check result is pasted.

```sh
../phase0-minimal/bin/python -m pip install . --force-reinstall
../phase0-minimal/bin/python scripts/check_installation.py --without-excel --without-pdf
../phase0-minimal/bin/python -m pip check
```

```text
Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified
No broken requirements found.
```

```sh
.venv/bin/python -m venv ../phase8-wheel
../phase8-wheel/bin/python -m pip install dist/variance_analysis_agent-0.3.0-py3-none-any.whl
../phase8-wheel/bin/python scripts/check_installation.py --without-excel --without-pdf
../phase8-wheel/bin/python -m pip check
```

```text
Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified
No broken requirements found.
```

```sh
.venv/bin/python -m venv ../phase8-sdist
../phase8-sdist/bin/python -m pip install dist/variance_analysis_agent-0.3.0.tar.gz
../phase8-sdist/bin/python scripts/check_installation.py --without-excel --without-pdf
../phase8-sdist/bin/python -m pip check
```

```text
Installed 0.3.0: console, CSV/JSON, audit provenance, chat page verified
No broken requirements found.
```

### Chat and frontend fallback

Chromium's executable was unavailable when browser launch was attempted. The
brief expressly permits chat/frontend tests in that case. No 1280 px / 375 px
screenshots or visual-browser success are claimed. The final full suite includes
those tests; this focused final fallback was also run:

```sh
.venv/bin/python -m pytest -q tests/test_chat*.py tests/test_frontend_contract.py   tests/test_multi_audience_chat.py tests/test_multi_audience_routing.py   tests/test_multi_audience_presets.py tests/test_multi_audience_pdf.py
```

```text
........................................................................ [ 13%]
........................................................................ [ 27%]
........................................................................ [ 41%]
........................................................................ [ 54%]
........................................................................ [ 68%]
........................................................................ [ 82%]
........................................................................ [ 95%]
......................                                                   [100%]
526 passed in 20.78s
```

Installed-package smoke checks above also started the local chat server and
fetched its page, assets and health endpoint. These are local installation
checks, not a hosted-deployment or visual-browser check. The new fictional PDF
was rendered to PNG and visually inspected: its fictional caption, aligned
statement columns and EPS/count rows were legible with no clipping.

## Throughput, measured

Phase 4 measured **21.097414243999992 seconds**. The final-code rerun measured
**19.399163291999912 seconds**, with source generation excluded and the complete
CLI capture/group/analysis/CSV+JSONL write included. Both are single observations
on this host, not estimates or a performance guarantee. The output verifier
counted 100,000 JSONL rows and zero error rows. No throughput optimization was
needed because the measured duration was below the brief's 60-second trigger.

The largest admitted strict CSV has 100,000 data rows, 10 columns and 1,000,000
cells; its header is additional. Assisted scanning also counts its header/title
rows and therefore admits fewer data rows at the same width. Neither cap was
relaxed. Split a larger universe into separate files. Host-reported CPU model
and visible logical CPU count are included below.

```json
{
  "rows": 100000,
  "columns": 10,
  "cells": 1000000,
  "groups": 1000,
  "input_bytes": 8000078,
  "seconds": 19.399163291999912,
  "exit": 0,
  "machine": "Linux-6.18.55-x86_64-with-glibc2.39",
  "python": "3.12.14",
  "cpu_count": 9,
  "cpu_model": "AMD EPYC 9V74 80-Core Processor"
}
```

Reproduction: save the following generator in an empty temporary directory and
run it from the checkout with `PYTHONPATH=src .venv/bin/python /absolute/path/benchmark.py`.
It generates only fictional `.FAKE` entities and writes data beside itself.

```python
"""Generate the maximum 100,000-row / 1,000,000-cell fictional strict CSV."""
import csv
import json
import os
import platform
import time
from pathlib import Path
from variance_agent.cli import main

root = Path(__file__).resolve().parent
source = root / 'maximum-panel.csv'
with source.open('w', newline='') as handle:
    writer = csv.writer(handle, lineterminator='\n')
    writer.writerow(['Ticker', 'Period', 'Line Item', 'Consensus', 'Actual', 'Type', 'Measure', 'Better', 'Currency', 'Segment'])
    for ticker in range(100):
        for quarter in range(10):
            for metric in range(100):
                writer.writerow([f'Fictional{ticker:03d}.FAKE', f'Q{quarter % 4 + 1} {2024 + quarter // 4}',
                                 f'Revenue {metric:03d}', '100', '110', 'Revenue', 'Currency', 'Higher', 'USD', 'North'])
start = time.perf_counter()
code = main([str(source), '--group-by', 'Ticker,Period', '--compare-to', 'consensus', '--dollar-threshold', '10',
             '--percent-threshold', '2', '--long-output', str(root / 'maximum-panel-long.csv'),
             '--long-output-jsonl', str(root / 'maximum-panel-long.jsonl'), '--errors-output', str(root / 'maximum-panel-errors.csv')])
seconds = time.perf_counter() - start
result = {'rows':100000,'columns':10,'cells':1000000,'groups':1000,'input_bytes':source.stat().st_size,
          'seconds':seconds,'exit':code,'machine':platform.platform(),'python':platform.python_version(),'cpu_count':os.cpu_count()}
try:
    result['cpu_model'] = next(line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name'))
except (OSError, StopIteration):
    result['cpu_model'] = 'unavailable'
(root / 'phase8-benchmark.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result,indent=2))
assert code == 0
assert sum(1 for _ in (root / 'maximum-panel-long.jsonl').open()) == 100000
assert len((root / 'maximum-panel-errors.csv').read_text().splitlines()) == 1
```

## Differences and resolved interpretations

1. The checkout matches the brief's `f5cd79c`; no rebase of its assumptions was
   necessary. The observed test count matches, but measured time and interpreter
   differ: 37.72 seconds / Python 3.12.14 here versus the brief's 54 seconds /
   Python 3.13.16. Python 3.11 is not installed here. Neither Windows nor the
   other supported Python versions has been executed in this environment.
2. The environment was not prebuilt. A local virtual environment was created
   and the repository's existing pinned development/Excel/PDF/release extras
   installed. This added no project dependency or runtime network behavior.
   Package installation and Git transport are environment setup, not financial
   engine operations. Runner model/reasoning settings cannot be changed or
   independently attested from this checkout; no claim about them is made.
3. The standing rules still reference schema 1.5, two HTML copies, and commit
   `a3ce6bb`. The tree has audit 1.7 and one packaged HTML file. Use the brief's
   explicit overrides, 1.8 for new provenance, and this branch name.
4. Assisted JSON does **not** auto-detect comparison bases: `_read_json_bytes`
   uses Budget unless a basis is explicit, then calls strict selection. CSV and
   Excel take comparison detection. Preserve legacy JSON behavior; the new
   opted-in path will apply consistent new recognition across supported formats.
5. Strict parsing already accepts some header aliases; it is not limited to the
   three exact spellings the input-contract prose suggests. No alias removal.
6. README's signed denominator is wrong; code and financial-rules agree on the
   absolute denominator. Correct the prose in phase 8, not existing arithmetic.
7. `# Est.` and `Est.` both become `est` in intake normalization (and in strict
   key normalization). Preserve raw header identity before new interpretation;
   reject unresolved collisions. Do not infer that `est` means estimator count.
8. The phase-1 prose calls a count absolute cutoff optional, but its later
   materiality rule explicitly requires each kind's threshold. Use the stronger
   rule: require `--count-threshold` when Count occurs, including zero-comparison
   rows; no preset supplies thresholds. Record this in help and docs.
9. New headers are not all globally reserved. Measure/Better are explicit new
   semantic columns; Consensus/Model/Region/Division/Segment and new quarter
   forms require earnings/quant, a new explicit basis, a new mapping, or a
   confirmed chat earnings review. Budget uploads with incidental earnings
   metadata continue through the old path without a new prompt.
10. The brief's 1.8 addition cannot unconditionally change legacy audit defaults
    without breaking its byte promise. Legacy runs still emit exactly 1.7 when
    no schema is selected. Explicit 1.8 is available; new semantics auto-select
    1.8. An explicit older version with new semantics fails before publication.
11. A missing consensus is not zero. Current parsing cannot analyze missing
    amounts. Represent an unavailable basis separately; never substitute zero
    or run fabricated values through the engine. Explicit zero consensus is real;
    new Consensus percentage is null at zero, while the legacy zero/zero rule is
    untouched. The display label for blank and zero is “N/A (No consensus)”;
    `comparison_present` and the amount distinguish them in 1.8.
12. Existing currency renderers use ASCII `-` and no leading `+`. Follow those
    sign conventions for new formats (`-$0.07/sh`, `-60 bps`, `-1,500 units`),
    despite typographic minus/plus signs in the acceptance table. Arithmetic and
    the requested unit suffixes remain exact.
13. Existing source parsing accepts Python floats for legacy compatibility.
    Do not tighten existing callers. The new API rejects float amounts,
    thresholds, and statistics; file numeric text/stored XML is kept exact.
    Existing PDF coordinate floats and workbook layout floats are geometry,
    never financial values.
14. `shape_income_statement` and unit scaling assume additive money. Retained
    EPS/counts must bypass subtotal sign solving; Per Share never receives the
    filing's monetary millions multiplier. Share counts require their own explicit
    scale; ambiguous captions stop for a mapping. Count direction is still a
    user choice; never assume that more or fewer shares is better.
15. The four existing public signatures include both dataclass constructors.
    Preserve them, not only the two functions. New configuration/result wrappers
    hold extensions; no required fields are added to those constructors.
16. The standing rules' all-checks phase gate includes packaging and minimal
    installation, beyond section 2's shorter five-command list. Run the union at
    every phase. Visual QA is not applicable to this documentation-only phase.
    Later changed screens use a browser if available; otherwise run chat/frontend
    tests and disclose the brief's permitted fallback.
17. A same-label/same-segment duplicate can make a comparison-set join ambiguous.
    Keep the legacy duplicate warning in single runs; a set/panel group requiring
    an ambiguous join fails with its key and requests a unique metric identity.
    Do not invent occurrence-based pairings.
18. `test_audit_schema_17.py` explicitly pins `CURRENT_SCHEMA_VERSION == "1.7"`.
    Keep that constant as the legacy default. Make 1.8 selectable and choose it
    explicitly in the extended path; do not update this existing test. The
    existing tests which iterate selectable versions will naturally collect
    more cases after 1.8 is added, without editing their source.
19. Phase 5 describes the square root as the only inexact step, but a general
    sample variance (including Scenario D's `91/120000`) and the final SUE ratio
    need not have finite decimal expansions. Proposed interpretation: compute
    exact Decimal variance numerator/denominator, use the existing explicitly
    rounded ratio policy for their division, then a locally rounded sqrt and
    final ratio; document all three boundaries. Keep Fraction only in test
    oracles. This interpretation needs acceptance in the STOP 1 plan decision
    before phase 5; the phase remains optional at STOP 3.
20. Strict CSV counts data rows/cells; assisted delimited intake includes its
    header in physical row/cell accounting. Thus 100,000 data rows x 10 columns
    fit strict CSV's two caps, while assisted intake permits 99,999 data rows
    at that width. Keep each existing accounting rule; report which path the
    throughput run uses rather than relaxing a cap.

The preceding list records the Phase-0 decisions approved at STOP 1. Final
implementation differences and refinements are:

21. The preliminary audit table proposed structured inference objects, row IDs,
    nested threshold groups and a separate period-interpretation object. The
    implementation uses visible strings, metric/segment/measure identity,
    explicit nullable audience fields and existing comparison labels. The
    [final field delta](audit-contract.md#final-18-field-delta) and closed schema
    describe the shipped shape; the plan's proposal is retained as history.
22. Configuration identity covers effective audience/statistic options; explicit
    mapping provenance, basis order and all derived facts are covered by record
    fingerprints and public payload digests. Panels use the documented long
    contract rather than a new audit root. A canonical validated mapping digest
    identifies choices, not the mapping file's whitespace bytes.
23. Retained filing counts remain in printed units with a visible policy; there
    is no new count-scale inference or count-scale mapping. Verify/prepare a
    different printed count scale before analysis. PDF coordinates and wall-clock
    timers use floats for geometry/performance only, never financial values.
24. The existing safe chat table widget already supports structured results, so
    no additional frontend layout component was needed for earnings. The two
    phase-1 phase-label entries were the only required frontend code changes.
25. Final mapping regressions exposed assisted header discovery checking names
    before applying the supplied mapping, plus missing mapped-file notes in child
    audits. Explicit mapped names, header rows and notes are now retained. The
    same final tests cover explicit dispersion-only window/entity forwarding.

## Tested boundary and user choices

Only synthetic fixtures were analyzed. **Real data-vendor exports, real filings,
the hosted deployment, Windows, Python 3.11, 3.13 and 3.14 were not executed in
this environment.** Existing CI still defines those platform/interpreter checks;
no remote CI result is claimed. No live vendor integration or data download was
used to validate mappings. The benchmark is local and was not a stress test of a
multi-user hosted server.

The user must align GAAP versus adjusted EPS, diluted versus basic shares,
metric names and definitions, fiscal/calendar periods, currencies and units.
Bare rates need a scale choice; Count needs a direction and cutoff; missing
consensus stays absent; ambiguous Est. needs a mapping. A share-count caption
or vendor convention does not silently establish a unit multiplier. The tool
compares supplied amounts and produces descriptive statistics only; it does not
create a consensus, forecast, valuation, price target or investment rating.

Flat segments do not model a hierarchy or reconcile a consolidated company from
segment rows. PDF extraction reads a supplied comparable statement; it does not
match a filing to a separate consensus file. Long outputs retain the capture
limits and documented per-file atomic replacement (multiple files are not one
filesystem transaction). Hashes detect change, not source authorship or GAAP
correctness. No runtime dependency, financial network/model call or modification
to `deterministic_conditioning/` was introduced.

## STOP 4

All authorized local implementation and verification work is complete. Review
this report and the local commits before authorizing any push or merge. The
branch is not published by this work.
