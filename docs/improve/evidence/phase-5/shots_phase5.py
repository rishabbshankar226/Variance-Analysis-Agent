"""Screenshots of the chat screens Phase 5 of the improvement pass changed (docs/improve/PLAN.md, N1).

N1 lets Export Excel write a workbook for a limit run, a balance sheet comparison and a filing's income
statement, where the chat refused before. Each scenario ends on that export reply. Every file is
fictional: the analysts' Ines file and a filing built by tests/fixtures/ixbrl/build_ixbrl.py.

    .venv/bin/python docs/improve/evidence/phase-5/shots_phase5.py --build <scratch dir>
    .venv/bin/python docs/improve/evidence/phase-5/shots_phase5.py --check <scratch dir>
    ~/.venvs/vaa-shots/bin/python docs/improve/evidence/phase-5/shots_phase5.py <out dir> <scratch dir> [names]

The harness is the interface redesign's (docs/ui/evidence/shots.py), as Phase 3's script uses it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs" / "ui" / "evidence"))
sys.path.insert(0, str(ROOT))

INES = str(ROOT / "tests" / "fixtures" / "analysts" / "ines_limits.csv")


def scenarios(files: Path) -> dict[str, list[tuple[str, str, str]]]:
    """name -> steps, as shots.py takes them: ("upload", path, label), ("say", text, label)."""
    filing = str(files / "hal-20250927.htm")
    return {
        "n1-limit-export": [("upload", INES, ""), ("say", "Looks right", ""), ("say", "Oct 2026", ""),
                            ("say", "$1 or 1%", ""), ("say", "USD", "results"), ("say", "export excel", "export")],
        "n1-balance-sheet-export": [("upload", filing, ""), ("say", "statement Consolidated Balance Sheets", ""),
                                    ("say", "Looks right", ""), ("say", "Sep 2025", ""), ("say", "$10,000 or 5%", ""),
                                    ("say", "USD", "results"), ("say", "export excel", "export")],
        "n1-filing-income-export": [("upload", filing, ""), ("say", "Looks right", ""), ("say", "FY2025", ""),
                                    ("say", "$1 or 1%", ""), ("say", "USD", "results"),
                                    ("say", "export excel", "export")],
    }


def build(scratch: Path) -> None:
    from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing

    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / "hal-20250927.htm").write_bytes(all_statements_filing())


def check(scratch: Path) -> None:
    """Drive each scenario through the chat handlers, printing the phase and the reply's first line."""
    from variance_agent.chat.handlers import handle_message, handle_upload
    from variance_agent.chat.session import Session

    for name, steps in scenarios(scratch).items():
        session = Session()
        print(f"== {name}")
        for kind, arg, label in steps:
            if kind == "upload":
                reply = handle_upload(session, Path(arg).read_bytes(), Path(arg).name)
            else:
                reply = handle_message(session, arg)
            text = reply.text.replace("Welcome to the Variance Analysis Agent.", "").strip()
            lines = [line for line in text.splitlines() if line.strip() and not line.startswith(("I compare", "Type"))]
            print(f"  {kind} {Path(arg).name if kind == 'upload' else arg!r} [{label}] -> {session.phase.value} "
                  f"{reply.level or ''} download={sorted(reply.download or {})} | {(lines[0] if lines else '')[:140]}")


def main(out: Path, scratch: Path, only: list[str]) -> None:
    import shots  # type: ignore[import-not-found]  # the redesign harness; needs Playwright

    out.mkdir(parents=True, exist_ok=True)
    shots.SCENARIOS = scenarios(scratch)
    for path in shots.run(out, ["light"], ["d", "m"], only or list(shots.SCENARIOS)):
        print(path)


if __name__ == "__main__":
    if sys.argv[1] == "--build":
        build(Path(sys.argv[2]))
    elif sys.argv[1] == "--check":
        check(Path(sys.argv[2]))
    else:
        main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].split(",") if len(sys.argv) > 3 else [])
