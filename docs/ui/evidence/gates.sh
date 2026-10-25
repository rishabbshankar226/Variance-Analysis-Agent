#!/bin/sh
# The redesign's gate list (docs/ui/PLAN.md, "Gates"). Run from the repository root.
#   sh docs/ui/evidence/gates.sh          core gates (every phase)
#   sh docs/ui/evidence/gates.sh dist     core gates plus the distribution gates (phases that touch an asset)
# Prints one summary line per gate and exits non-zero on the first failure.
set -eu
PY=.venv/bin/python
SCRATCH="${TMPDIR:-/tmp}/vaa-gates"
gate() { name="$1"; shift; if out=$("$@" 2>&1); then echo "PASS $name: $(printf '%s\n' "$out" | tail -1 | cut -c1-140)"; else printf '%s\n' "$out" | tail -20; echo "FAIL $name"; exit 1; fi; }

gate ruff "$PY" -m ruff check .
gate mypy "$PY" -m mypy --strict src/variance_agent scripts deterministic_conditioning
gate pytest "$PY" -m pytest -q --tb=line -p no:cacheprovider
gate compileall "$PY" -m compileall -q src tests scripts deterministic_conditioning
gate pip-check "$PY" -m pip check
gate contracts sh -c 'test -z "$(git diff --name-only 822e522 -- tests/fixtures/contracts)" && echo "19 contract fixtures unchanged since 822e522 ($(git ls-files tests/fixtures/contracts | wc -l | tr -d " ") tracked)"'

if [ "${1:-}" = dist ]; then
  rm -rf "$SCRATCH" && mkdir -p "$SCRATCH"
  gate build "$PY" -m build --outdir "$SCRATCH/dist"
  gate twine sh -c "$PY -m twine check $SCRATCH/dist/*"
  gate distribution "$PY" scripts/check_distribution.py "$SCRATCH/dist"
  for artifact in "$SCRATCH"/dist/*; do
    env="$SCRATCH/env-$(basename "$artifact")"
    "$PY" -m venv "$env"
    gate "install $(basename "$artifact")" "$env/bin/python" -m pip install -q "$artifact"
    gate "installation --without-excel --without-pdf ($(basename "$artifact"))" "$env/bin/python" scripts/check_installation.py --without-excel --without-pdf
    gate "pip-check ($(basename "$artifact"))" "$env/bin/python" -m pip check
  done
  wheel=$(ls "$SCRATCH"/dist/*.whl)
  "$PY" -m venv "$SCRATCH/env-pdf"
  gate "install wheel[pdf]" "$SCRATCH/env-pdf/bin/python" -m pip install -q "$wheel[pdf]"
  gate "installation --without-excel (rules file)" "$SCRATCH/env-pdf/bin/python" scripts/check_installation.py --without-excel
fi
