"""Drive the chat as Maya would, for each FICTIONAL file, and record the transcript.

Run: .venv/bin/python .scratch/audit-maya/drive.py [file ...]
Policy (what Maya does):
  intake summary        -> click "Looks right"            (confirm: 0 steps)
  blank budgets         -> click the "Treat ... as 0" chip (confirm: 0 steps)
  period choice         -> click the first period chip    (0.5)
  period question       -> chip if any (0.5) else type "Q3 2026" (1)
  thresholds            -> click "$10,000 or 5%"           (0.5)
  currency              -> click "USD"                     (0.5)
  GL range rules        -> click "Looks right"             (confirm: 0)
  each unlabeled line   -> click Revenue / Expense by name (0.5 each)
  second file asked for -> upload the other half           (1: an upload outside the chat flow)
Stops at EXPLORING (analysis) or when no chip moves forward (dead end).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

HERE = Path(__file__).resolve().parent
FILES = HERE / "files"
OUT = HERE / "transcripts"
OUT.mkdir(exist_ok=True)

PAIRS = {"f06a_budget_only.xlsx": "f06b_actual_only.xlsx"}

JARGON = [
    (r"\b[a-z]+_[a-z_]+\b", "snake_case"),
    (r"\b\w*(Error|Exception)\b", "exception"),
    (r"(?<![\w-])--[a-z][a-z0-9-]+", "cli flag"),
    (r"\bnormaliz\w*", "normalize"),
    (r"\balias\w*", "alias"),
    (r"\bschema\w*", "schema"),
    (r"\bOOXML\b", "OOXML"),
    (r"\barchive\b", "archive"),
    (r"\bXML\b", "XML"),
    (r"\bDTD\b", "DTD"),
    (r"\bpayload\b", "payload"),
    (r"\bRow Kind\b", "Row Kind"),
    (r"\bUnclassified\b", "Unclassified"),
    (r"\bexit code\b", "exit code"),
    (r"`[^`]*<[^`]*>[^`]*`", "command syntax"),
]


def view_strings(view: object) -> list[str]:
    out: list[str] = []
    if isinstance(view, dict):
        for v in view.values():
            out += view_strings(v)
    elif isinstance(view, list):
        for v in view:
            out += view_strings(v)
    elif isinstance(view, str):
        out.append(view)
    return out


def jargon_in(text: str) -> list[str]:
    hits = []
    for pat, label in JARGON:
        for m in re.finditer(pat, text):
            hits.append(f"{label}: {m.group(0)!s}")
    return hits


def pick(resp, session: Session) -> tuple[str | None, float, str]:
    chips = resp.chips or []
    ph = session.phase
    if ph == Phase.AWAITING_INTAKE_CONFIRMATION and "Looks right" in chips:
        return "Looks right", 0, "confirm"
    cmp = next((c for c in chips if c.startswith("Compare to")), None)
    if cmp is not None:
        return cmp, 0.5, "chip"
    if "Leave the hidden rows out" in chips:
        return "Leave the hidden rows out", 0.5, "chip"
    if ph == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION:
        c = next((c for c in chips if c.startswith("Treat")), None)
        return c, 0, "confirm"
    if ph == Phase.AWAITING_PERIOD_CHOICE and chips:
        return chips[0], 0.5, "chip"
    if ph == Phase.AWAITING_PERIOD:
        if chips:
            return chips[0], 0.5, "chip"
        return "Q3 2026", 1, "typed"
    if ph == Phase.AWAITING_THRESHOLDS:
        return "$10,000 or 5%", 0.5, "chip"
    if ph == Phase.AWAITING_CURRENCY:
        return "USD", 0.5, "chip"
    if ph == Phase.RESOLVE_UNCLASSIFIED:
        if "Looks right" in chips:
            return "Looks right", 0, "confirm"
        item = session.unclassified_queue[0] if session.unclassified_queue else ""
        rev = re.search(r"revenue|sales|income|grant", item, re.I)
        return ("Revenue" if rev else "Expense"), 0.5, "chip"
    if ph in (Phase.AWAITING_MEASURE_OPTIONS, Phase.AWAITING_COMPARISON_CHOICE, Phase.AWAITING_EARNINGS_REVIEW) and chips:
        return chips[0], 0.5, "chip"
    return None, 0, "stuck"


def run(name: str) -> dict[str, object]:
    session = Session()
    lines: list[str] = []
    steps = 0.0
    jargon: list[str] = []
    data = (FILES / name).read_bytes()
    resp = handle_upload(session, data, name)
    first = resp.text
    turns = 0
    outcome = "stuck"

    def record(who: str, msg: str, r=None) -> None:
        lines.append(f"--- {who}: {msg}")
        if r is not None:
            body = r.text
            lines.append(body)
            lines.append(f"[chips={r.chips} phase={session.phase} level={r.level} ask_upload={r.ask_upload}]")
            if r.view:
                lines.append(f"[view={json.dumps(r.view, ensure_ascii=False)[:1500]}]")
            cells = [str(v) for row in (r.table or []) for v in row.values()]
            for s in [body, *(r.chips or []), *view_strings(r.view), *cells]:
                jargon.extend(jargon_in(s))

    record("UPLOAD", name, resp)
    while turns < 40:
        turns += 1
        if session.phase == Phase.EXPLORING and session.result is not None:
            outcome = "analysis"
            for q in ("show material variances", "Warnings"):  # what Maya reads next (not counted as steps)
                record("MAYA (reads, +0)", q, handle_message(session, q))
            break
        if resp.ask_upload and name in PAIRS:
            other = PAIRS[name]
            steps += 1
            resp = handle_upload(session, (FILES / other).read_bytes(), other)
            record("UPLOAD (second file, +1)", other, resp)
            continue
        msg, cost, kind = pick(resp, session)
        if msg is None:
            outcome = "dead end" if session.result is None else "stuck after analysis"
            break
        steps += cost
        resp = handle_message(session, msg)
        record(f"MAYA ({kind}, +{cost})", msg, resp)
    res = session.result
    summary = {
        "file": name,
        "outcome": outcome,
        "steps": steps,
        "turns": turns,
        "jargon": sorted(set(jargon)),
        "first": first.replace("\n", " ")[:300],
        "rows": None
        if res is None
        else [(r.line_item, str(r.line_type), str(r.budget), str(r.actual), str(r.variance_dollars), str(r.status)) for r in res.rows],
    }
    lines.append("=== SUMMARY ===")
    lines.append(json.dumps(summary, indent=1, ensure_ascii=False))
    (OUT / f"{name}.txt").write_text("\n".join(lines), encoding="utf-8")
    return summary


if __name__ == "__main__":
    names = sys.argv[1:] or sorted(p.name for p in FILES.iterdir() if p.name != "f06b_actual_only.xlsx")
    for n in names:
        s = run(n)
        print(f"{s['file']:28} {s['outcome']:12} steps={s['steps']:<4} jargon={s['jargon']}")
