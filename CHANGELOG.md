# Changelog

## 0.3.0 — Unreleased

- Reject mixed reporting currencies; support explicit USD/EUR/GBP without FX
  conversion. Reports name the reporting currency throughout all sections.
- Reject currency-decorated CLI thresholds instead of discarding their symbols.
- Fix an argparse formatting error that made `--help` crash.
- Publish audit schemas 1.0 through 1.3 and reviewed report/audit fixtures.
- Capture and parse the exact hashed source/type-map bytes; add versioned policy
  provenance and a recomputable public-payload digest.
- Expose classification/materiality decisions, summary verification, and driver
  reconciliation diagnostics. Preserve financial policy and hypothesis fallback.
- Keep older audit versions selectable; schema 1.0 remains USD-only. See
  [migration details](docs/input-contract.md) and [audit versions](docs/audit-contract.md).
- Add Python 3.11-3.14, Windows output, minimal-install, and distribution CI gates;
  use one package-version source and include the declared MIT license.

## 0.2.0

The preceding deterministic CLI includes CSV/JSON/Excel validation, isolated
Decimal arithmetic, strict materiality, summary reconciliation, supported driver
checks, audit fingerprints, and staged output replacement. Historical defect and
regression evidence is retained in `docs/`.
