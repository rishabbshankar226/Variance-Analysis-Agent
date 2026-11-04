"""S1 characterization: the chat's replies over a fixed script of 20 fictional uploads and messages.

Phase 4 moves `chat/handlers.py` into a package without changing behaviour (docs/improve/PLAN.md, S1). Every
reply's text, table, chips, view, phase, level and upload request is compared with the snapshot taken before
the move. A download is compared by its name and, for text, by its digest.

Regenerate the snapshot only for an approved behaviour change:
    .venv/bin/python -c "from tests.test_characterization_s1 import write; write()"
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Session

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "tests" / "fixtures" / "characterization" / "s1_chat.json"
RW = ROOT / "tests" / "fixtures" / "realworld"

# ("upload", path) or ("say", text): twenty steps across the handler families.
SCRIPT: list[tuple[str, str]] = [
    ("upload", str(ROOT / "examples" / "sample_variance.csv")),
    ("say", "Q3 2026"),
    ("say", "$10,000 or 5%"),
    ("say", "USD"),
    ("say", "Why Subscription Revenue?"),
    ("say", "drivers"),
    ("say", "biggest risks"),
    ("say", "what if marketing is 10% lower"),
    ("say", "waterfall"),
    ("say", "what is the full year run rate?"),
    ("say", "executive memo"),
    ("say", "revenue status"),
    ("say", "top 3 variances"),
    ("say", "warnings"),
    ("say", "export report"),
    ("say", "thanks"),
    ("upload", str(RW / "fixture_e_wide_monthly.xlsx")),
    ("upload", str(RW / "fixture_f_budget_separate.csv")),
    ("upload", str(RW / "fixture_f_actuals_separate.csv")),
    ("say", "Looks right"),
]


def _download(download: dict[str, str | bytes] | None) -> dict[str, str] | None:
    if download is None:
        return None
    seen: dict[str, str] = {}
    for key, value in sorted(download.items()):
        if isinstance(value, bytes):
            text_like = str(download.get("filename", download.get("name", ""))).endswith((".md", ".csv", ".json", ".txt"))
            seen[key] = hashlib.sha256(value).hexdigest() if text_like else f"<{len(value) > 0} bytes>"
        else:
            seen[key] = str(value)
    return seen


def snapshot() -> list[dict[str, object]]:
    session = Session()
    replies: list[dict[str, object]] = []
    for kind, arg in SCRIPT:
        if kind == "upload":
            reply = handle_upload(session, Path(arg).read_bytes(), Path(arg).name)
        else:
            reply = handle_message(session, arg)
        replies.append({"step": f"{kind} {Path(arg).name if kind == 'upload' else arg}", "text": reply.text,
                        "table": reply.table, "chips": reply.chips, "view": reply.view, "phase": reply.phase,
                        "level": reply.level, "ask_upload": reply.ask_upload, "download": _download(reply.download)})
    return json.loads(json.dumps(replies, default=str))  # type: ignore[no-any-return]


def write() -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def test_the_chat_replies_match_the_snapshot_taken_before_the_move() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = snapshot()
    assert len(actual) == len(SCRIPT) == len(expected) == 20
    for step, (want, got) in enumerate(zip(expected, actual, strict=True), start=1):
        assert got == want, f"step {step}: {want['step']}"
