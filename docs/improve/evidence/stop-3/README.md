# Final STOP evidence

- `gates.txt`: the full gate list at `c70c5ac`, as printed (`.scratch/gates/final.sh` in the run), after X45 to X48. An earlier run at `7049fac` gave 2814 passed.
- `d3-exits.txt`: the exit code of each of the README's 25 commands, run in order from a clean clone at `5e8a0fc` (D3).
- `scorecard/`: the friction scorecard in REPORT.md. `before.jsonl` is `main` at `15100c8`, `after.jsonl` is `7049fac`. Re-run at `ebd1912` and at `c70c5ac`, every row is the same as `after.jsonl`.

To reproduce the scorecard on any tree (every file is fictional and built by a script):

```sh
cd docs/improve/evidence/stop-3/scorecard
../../../../../.venv/bin/python build_files.py
../../../../../.venv/bin/python ../../phase-3/shots_phase3.py --build /tmp/mfiles
PYTHONPATH=<tree>/src ../../../../../.venv/bin/python scorecard.py files /tmp/mfiles ../../../../../tests/fixtures/analysts
```

`build_files.py` writes Maya's 25 files into `files/`; `drive.py` is Phase 1's policy (a chip where one is offered, "Q3 2026" typed for a period question), and `scorecard.py` adds one rule for X22's "Leave ... out" offer. `drive.py` makes a `transcripts/` folder beside itself when imported.
