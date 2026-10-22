# Contributing

Use Python 3.11-3.14 and a virtual environment:

```sh
python -m venv .venv
.venv/bin/python -m pip install -c requirements-typecheck.txt -e '.[dev,excel,pdf,release]'
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/python -m mypy --strict src/variance_agent scripts deterministic_conditioning
.venv/bin/python -m compileall -q src tests scripts deterministic_conditioning
.venv/bin/python -m pip check
```

On Windows, use `.venv\Scripts\python.exe` and the corresponding Ruff executable.
Ruff enforces bugbear and a 140-column line limit; the few template-heavy files exempt from the limit are listed in
`pyproject.toml`.
The runtime needs no third-party packages for CSV/JSON. Excel and PDF are optional extras;
without `pdf` the PDF tests are skipped, so install it before changing intake.
Schema validators and build tools are development/release dependencies only.

For behavior changes, add a regression demonstrating the failure first. Run the
full suite after the fix. Review complete golden diffs instead of blindly replacing
fixtures. Preserve deterministic arithmetic, expense/revenue sign conventions,
strict materiality, Unclassified exclusions, hierarchy limits, and driver support
rules. Do not introduce LLM arithmetic or silently reinterpret source amounts.

Published audit schemas are immutable. Add a separate version and document
migration when changing the contract; keep legacy fixtures. Decision/provenance
metadata should contain derived facts, never raw input dictionaries.

Use synthetic reproductions. State Python/tool versions, file format, reporting
currency, expected behavior, and actual error/output. Remove confidential ledger
contents. Keep PRs focused and include test evidence and compatibility effects.

CI tests every declared Python version, schemas/goldens, an installation without
Excel, wheel/sdist installations, and portable output behavior on Windows.
Repository owners can require the stable `Required checks` job on main. Action
SHAs must be verified against their upstream repository when updating pins.
The source, verification scripts and the auxiliary `deterministic_conditioning`
package have a strict mypy configuration, including explicit/unimported Any bans.
The development extra includes the pinned checker; CI runs
`python -m mypy --strict src/variance_agent scripts deterministic_conditioning`
on every supported Python version. Executed results are recorded in the institutional audit ledger. Do not hide
errors behind blanket ignores or introduce new third-party dependencies without
the repository owner's approval.

See [release preparation](docs/releasing.md) and [security reporting](SECURITY.md).
