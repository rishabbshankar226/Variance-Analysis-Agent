"""Screenshots of the chat screens Phase 8's fixes changed (docs/improve/PLAN.md, X45 to X47).

X45 refuses a file whose Budget and Actual headings name different units, X46 reads a percent-formatted
Tolerance as the percentage Excel shows, and X47 shows a Percent limit row's headroom and buffer in basis
points. Each scenario ends on the screen that changed. Every file is fictional, from the STOP-ASK evidence.

    .venv/bin/python docs/improve/evidence/phase-8/shots_phase8.py --check
    ~/.venvs/vaa-shots/bin/python docs/improve/evidence/phase-8/shots_phase8.py <out dir> [names]

The harness is the interface redesign's (docs/ui/evidence/shots.py), as Phases 3 and 5 use it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs" / "ui" / "evidence"))
sys.path.insert(0, str(ROOT))

EVIDENCE = ROOT / "docs" / "improve" / "evidence"


def scenarios() -> dict[str, list[tuple[str, str, str]]]:
    """name -> steps, as shots.py takes them: ("upload", path, label), ("say", text, label)."""
    return {
        "x45-heading-units": [("upload", str(EVIDENCE / "stop-ask-heading-units" / "a1.csv"), "refusal")],
        "x46-percent-tolerance": [("upload", str(EVIDENCE / "stop-ask-percent-declarations" / "b1.xlsx"), ""),
                                  ("say", "Looks right", ""), ("say", "Q3 2026", ""), ("say", "$1 or 1%", ""),
                                  ("say", "USD", ""), ("say", "1", "results")],
        "x47-limit-bps": [("upload", str(EVIDENCE / "stop-ask-limit-rate-units" / "c1.csv"), ""),
                          ("say", "Looks right", ""), ("say", "Q3 2026", ""), ("say", "$1 or 1%", ""),
                          ("say", "USD", ""), ("say", "1", "results")],
    }


def check() -> None:
    """Drive each scenario through the chat handlers, printing the phase and the reply's first line."""
    from variance_agent.chat.handlers import handle_message, handle_upload
    from variance_agent.chat.session import Session

    for name, steps in scenarios().items():
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
                  f"{reply.level or ''} chips={reply.chips} | {(lines[0] if lines else '')[:160]}")
            for line in lines:
                if line.startswith("| Fictional"):
                    print(f"    {line}")


def main(out: Path, only: list[str]) -> None:
    import shots  # type: ignore[import-not-found]  # the redesign harness; needs Playwright

    out.mkdir(parents=True, exist_ok=True)
    shots.SCENARIOS = scenarios()
    for path in shots.run(out, ["light"], ["d", "m"], only or list(shots.SCENARIOS)):
        print(path)


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        check()
    else:
        main(Path(sys.argv[1]), sys.argv[2].split(",") if len(sys.argv) > 2 else [])
