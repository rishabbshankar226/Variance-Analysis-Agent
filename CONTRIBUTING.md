# Contributing

Use Python 3.11-3.14 and a virtual environment:

```sh
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev,excel,release]'
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/python -m compileall -q src tests scripts
.venv/bin/python -m pip check
```

On Windows, use `.venv\Scripts\python.exe` and the corresponding Ruff executable.
The runtime needs no third-party packages for CSV/JSON. Excel is an optional extra.
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
Type checking can be introduced incrementally at module boundaries; do not hide
errors behind blanket ignores.

See [release preparation](docs/releasing.md) and [security reporting](SECURITY.md).
