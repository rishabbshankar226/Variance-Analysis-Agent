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

## Next focused work

- **I09 / Optional consumers:** an offline, bounded, schema-validated LLM commentary
  contract using fact references and support status. Python renders all numbers;
  source text remains data. No live-model integration or forecasting is required.
- **I10 / Optional consumers:** generation directories with an atomic manifest
  pointer if downstream readers require a coherent report/audit pair. Preserve
  current output flags and their documented per-file atomicity.

Do not expand nested hierarchy or add FX conversion, valuation, budgeting, or
scenario modeling without a separately justified scope decision.
