# Improvement roadmap

## Completed implementation

| Issue | Result |
|---|---|
| I01 | One explicit reporting currency; conflicting currencies rejected; full currency rendering |
| I02 | Published schemas 1.0-1.4, consumer rejection tests, archived audit fixtures |
| I03 | Tool/policy/config identities, named fingerprint recipe, public-payload digest |
| I04 | Exact captured-byte source/type-map provenance and replacement regression |
| I05 | Classification/materiality sources, summary verification, driver reconciliation diagnostics |
| I06 | Reviewed full report goldens for complete/incomplete, unbudgeted, summary, and currency cases |
| I07 | Python 3.11-3.14, Windows output, minimal-install, and wheel/sdist CI gates |
| I08 | Check-only validation without artifacts; exact worksheet selection and recorded worksheet identity |
| I11 | License, maintainer guides/templates, ownership, changelog, single version source, release checklist |

The financial rules remain deterministic Python/Decimal. Published audit versions
are selectable and their archived fixtures retained. See the changelog for input
and report migrations. Version 0.3.0 is development metadata, not a published release.

## Approved multi-audience scope (October 2026)

The owner-approved brief permits supplied Consensus, Estimate and Guidance
bases, explicit comparison sets, Per Share/Percent/Count measures, one flat
segment dimension, typed panels and descriptive surprise statistics. These
are implemented as opt-in extensions of the deterministic single-basis engine.
The earnings and quant presets serve the new readers; the FP&A default retains
its existing contracts. See [the implementation report](history/MULTI_AUDIENCE_2026-10.md)
for commands, verification and the boundary of this decision.

The decision does not permit nested hierarchy, FX conversion, valuation, price
targets, investment ratings, budget creation, forecasting or scenario modeling.
Metric definitions, vendor mappings and fiscal/calendar alignment remain explicit
user choices. No live vendor integration, model call or runtime dependency was
added. Larger panels must be split to retain existing capture/table limits.

## Improvement pass (November 2026)

Branch `improve/depth-pass`; the plan and evidence are in `docs/improve/`.

| Area | Closed |
|---|---|
| Wrong numbers | X1 to X8, X30, X41, C1, C2, C5: paths that could show a figure the source does not support, each with a failing test first. C3 was investigated and left the rule as it is |
| Refusals and friction | X10, X12 to X29, X31, X35, X36, X42, M1 to M6, C3m, C4: refusals that named no cause or fix, and replies that stranded a reader |
| Structure | S1 to S4, X37: `chat/handlers` is a package of 17 modules, and no function in `src/` runs over 150 lines |
| Not built before | N1: workbook sheets for limit, benchmark, target, statement, metric and filing income comparisons. N2: `--batch` over a folder of filings, with a manifest |
| Tests | T1: a timing test load cannot break. T2: 0 of 25 seeded mutants survive (3 before). T3: the one test over 5 s, from 22 s in the suite to under 3 s alone |
| Docs | D1: earlier records in `docs/history/`. X32, X33, X34: workbook rounding, audit 1.9 and `--mapping` described as they behave |

Left open:

- **X9, X11, the shared hosted session.** Hosted mode gives every visitor one session, and staged downloads sit under guessable names. The per-visitor-sessions branches own this.
- **X24's merged date band.** A date band merged over Budget and Actual still fails with "Could not determine period order"; two-row headers otherwise read.
- **X43.** A limit, benchmark or target table prints a scaled amount with the three decimal places it holds ("$89,999.000"). The value is right; only the display is.
- **X38.** Four copies of the number grammar and workbook helpers, with drifted messages.
- **X39.** `export excel` on a 4.28 MiB CSV takes the hosted server from 49 to 559 MiB on the free plan.
- **X40.** The hosted build installs the newest reader dependencies; pinning them is the owner's call.

## Next focused work

- **I09 / Optional consumers:** an offline, bounded, schema-validated LLM commentary
  contract using fact references and support status. Python renders all numbers;
  source text remains data. No live-model integration or forecasting is required.
- **I10 / Optional consumers:** generation directories with an atomic manifest
  pointer if downstream readers require a coherent report/audit pair. Preserve
  current output flags and their documented per-file atomicity.

Do not expand nested hierarchy or add FX conversion, valuation, budgeting, or
scenario modeling without a separately justified scope decision.
