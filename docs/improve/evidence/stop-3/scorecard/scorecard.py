"""Friction scorecard (rules file, Walkthrough): each fixture driven as Maya would, on the tree PYTHONPATH names.

Run with PYTHONPATH=<tree>/src: prints JSON rows {file, outcome, steps, first}. The policy is Phase 1's
(drive.py beside this script): chips where offered, "Q3 2026" typed for a period question, etc.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import variance_agent
import drive  # noqa: E402  (its pick() is the policy)
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session


def run(path: Path, pair: Path | None) -> dict[str, object]:
    session = Session()
    resp = handle_upload(session, path.read_bytes(), path.name)
    first = next((line for line in resp.text.replace("Welcome to the Variance Analysis Agent.", "").splitlines() if line.strip()), "")
    steps, outcome = 0.0, "dead end"
    for _ in range(40):
        if session.phase == Phase.EXPLORING and session.result is not None:
            outcome = "analysis"
            break
        if resp.ask_upload and pair is not None:
            steps += 1
            resp = handle_upload(session, pair.read_bytes(), pair.name)
            pair = None
            continue
        leave = next((c for c in resp.chips or [] if c.startswith("Leave ") and c.endswith(" out")), None)
        # X22's offer, which Phase 1's policy predates: Maya leaves the unreconciled total out (a chip, 0.5)
        msg, cost, _ = (leave, 0.5, "chip") if leave else drive.pick(resp, session)
        if msg is None:
            break
        steps += cost
        resp = handle_message(session, msg)
    return {"file": path.name, "outcome": outcome, "steps": steps, "first": first[:160]}


maya = Path(sys.argv[1])
mfiles = Path(sys.argv[2])
analysts = Path(sys.argv[3])
print(json.dumps({"tree": variance_agent.__file__}))
for f in sorted(p for p in maya.iterdir() if p.name != "f06b_actual_only.xlsx"):
    print(json.dumps(run(f, maya / "f06b_actual_only.xlsx" if f.name == "f06a_budget_only.xlsx" else None)))
for name in [
    "hal-elsewhere-20250927.htm",
    "hal-runs-on-20250927.htm",
    "years.xlsx",
    "hal-copies-20250927.htm",
    "empty.csv",
    "no_header.csv",
]:
    print(json.dumps({"m": True, **run(mfiles / name, None)}))
print(json.dumps({"m": True, **run(analysts / "hal-20260328.htm", None)}))
