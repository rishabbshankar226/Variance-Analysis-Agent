"""Run the tool over a drawn corpus and score every amount it read against the oracle.

A development tool (docs/analysts/PLAN.md; section 5 of the spec). For each filing and face
statement it runs one fixed command per reader:

    variance-agent <document> --assisted --compare-to prior-period --period <report date>
        --dollar-threshold 1 --percent-threshold 1 --audit-json <out> --audit-schema-version 1.9
        [--sheet <statement>]

and scores the audit: a source read is verified when the oracle's fact for its concept,
period and dimensions holds the value; wrong when that fact holds another value; unverified
when no key reaches a fact. Derived variances are recomputed with Fraction. Per-filing rows go
to <corpus>/sweep_<draw>.csv; the aggregate (no company, no accession) is printed as JSON for
the repository.

    python -I docs/analysts/evidence/sweep.py A [--readers primary,financial_report,pdf]
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402  (a sibling development module, not variance_agent)

CORPUS = oracle.CORPUS
TOOL = Path(sys.executable).with_name("variance-agent")
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_COLUMN_NOTE = re.compile(r"^Read column '(?P<header>.*)' as (?P<label>.+)$")
_FLIP_NOTE = re.compile(r"^Read '(?P<label>.*)' as (?:income|an expense): the statement prints it as")
_FIX_WORDS = re.compile(r"\b(upload|rerun|save|choose|open|give|mark|remove|export|download|unhide|count|leave|pick)\b",
                        re.IGNORECASE)
_JARGON = re.compile(r"Traceback|Error:|Exception|\bschema\b|\bpayload\b|\bXML\b|\bOOXML\b", re.IGNORECASE)


@dataclass
class Score:
    verified: int = 0
    unverified: int = 0
    wrong: int = 0
    covered: int = 0
    monetary: int = 0
    details: str = ""


def _normal(text: str) -> str:
    text = re.sub(r"\[\d+\]", "", text)
    return " ".join(re.sub(r"[^a-z0-9%&]+", " ", text.lower()).split())


def _date(text: str) -> date | None:
    match = re.search(r"\b([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+((?:19|20)\d{2})\b", text)
    if not match or match.group(1).lower() not in _MONTHS:
        return None
    return date(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))


def _months(text: str) -> int | None:
    match = re.search(r"\b(\d{1,2}|three|six|nine|twelve)\s+months?\s+ended", text, re.IGNORECASE)
    words = {"three": 3, "six": 6, "nine": 9, "twelve": 12}
    if match:
        return int(match.group(1)) if match.group(1).isdigit() else words[match.group(1).lower()]
    if re.search(r"years?\s+ended", text, re.IGNORECASE):
        return 12
    return None


def _periods(header: str) -> list[oracle.Period]:
    """The instance periods a printed column header can mean: instants, or durations of its length."""
    end = _date(header)
    if end is None:
        return []
    months = _months(header)
    if months is None:
        return [("instant", end.isoformat())]
    return [("duration", start, end.isoformat()) for start in _starts(end, months)]


def _starts(end: date, months: int) -> list[str]:
    """Start dates a duration ending on `end` may have: calendar months back, give or take a week (52/53 weeks)."""
    year, month = end.year, end.month - months
    while month <= 0:
        month, year = month + 12, year - 1
    anchor = date(year, month, min(end.day, 28)).toordinal()
    return [date.fromordinal(anchor + offset).isoformat() for offset in range(-10, 12)]


def _fact(instance: oracle.Instance, concept: str, candidates: list[oracle.Period]) -> oracle.Fact | None:
    for period in candidates:
        for fact in instance.lookup(concept, period):
            if fact.value is not None and fact.unit.startswith("iso4217:") and "/" not in fact.unit:
                return fact
    return None


def _group(record: object, key: str) -> dict[str, object]:
    value = record.get(key) if isinstance(record, dict) else None
    return value if isinstance(value, dict) else {}


def _items(record: object, key: str) -> list[object]:
    value = record.get(key) if isinstance(record, dict) else None
    return value if isinstance(value, list) else []


def score_audit(audit: dict[str, object], statement: oracle.Statement, instance: oracle.Instance) -> Score:
    """Verify each read line of an audit against the oracle (keyless reads match by printed label)."""
    score = Score()
    notes = [str(note) for note in _items(_group(audit, "source").get("document"), "reader_notes")]
    columns = [m for m in (_COLUMN_NOTE.match(n) for n in notes) if m]
    flipped = {m.group("label") for m in (_FLIP_NOTE.match(n) for n in notes) if m}
    by_label = {_normal(line.label): line for line in statement.lines}
    money = {line.concept for line in statement.monetary(instance)}
    score.monetary = len(money)
    labels = {m.group("label"): _periods(m.group("header")) for m in columns}
    current_label = _group(audit, "audience").get("actual_label")
    comparison_label = _group(audit, "comparison").get("label")
    current = labels.get(str(current_label)) or (list(labels.values())[0] if labels else [])
    prior = labels.get(str(comparison_label)) or (list(labels.values())[1] if len(labels) > 1 else [])
    covered: set[str] = set()
    for name in _items(_group(audit, "transformations"), "excluded_totals"):
        line = by_label.get(_normal(str(name)))
        if line is not None:
            covered.add(line.concept)
    problems = []
    for row in _items(audit, "measure_rows"):
        if not isinstance(row, dict) or row.get("measure") != "Currency":
            continue
        name = str(row.get("line_item", ""))
        line = by_label.get(_normal(name))
        if line is None:
            score.unverified += 2
            continue
        covered.add(line.concept)
        negated = "negated" in line.preferred_label.lower()
        sign = -1 if name in flipped else 1
        for field, periods in (("actual", current), ("comparison", prior)):
            fact = _fact(instance, line.concept, periods)
            value = row.get(field)
            if fact is None or fact.value is None or value is None:
                score.unverified += 1
                continue
            displayed = -fact.value if negated else fact.value
            if Fraction(str(value)) == Fraction(sign) * Fraction(displayed):
                score.verified += 1
            else:
                score.wrong += 1
                problems.append(f"{name} {field}: tool {value}, filing {displayed}")
        variance = row.get("variance")
        if variance is not None and row.get("actual") is not None and row.get("comparison") is not None:
            if Fraction(str(variance)) != Fraction(str(row["actual"])) - Fraction(str(row["comparison"])):
                score.wrong += 1
                problems.append(f"{name} variance does not recompute")
    score.covered = len(covered & money)
    score.details = "; ".join(problems)[:500]
    return score


def _plain(message: str) -> bool:
    return bool(message) and bool(_FIX_WORDS.search(message)) and not _JARGON.search(message)


def _run(document: Path, period: str, sheet: str | None, out: Path) -> tuple[int, str, float]:
    command = [str(TOOL), str(document), "--assisted", "--compare-to", "prior-period", "--period", period,
               "--dollar-threshold", "1", "--percent-threshold", "1", "--audit-json", str(out),
               "--audit-schema-version", "1.9", "-o", str(out.with_suffix(".md"))]
    if sheet is not None:
        command += ["--sheet", sheet]
    started = time.monotonic()
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        return -1, "timed out after 120 seconds", time.monotonic() - started
    message = done.stderr.strip().splitlines()[-1] if done.returncode and done.stderr.strip() else ""
    return done.returncode, message.removeprefix("variance-agent: error: "), time.monotonic() - started


def _xlsx_sheets(path: Path) -> list[str]:
    import zipfile
    with zipfile.ZipFile(path) as archive:
        data = archive.read("xl/workbook.xml")
    if oracle._DECLARATION.search(data):
        return []
    root = ElementTree.fromstring(data)
    return [sheet.get("name", "") for sheet in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")]


def _targets(reader: str, folder: Path, row: dict[str, str], statement: oracle.Statement, page: str) -> tuple[Path, str | None] | None:
    if reader == "primary":
        return folder / row["primary"], None
    if reader == "financial_report":
        path = folder / "Financial_Report.xlsx"
        number = re.fullmatch(r"R(\d+)\.htm", page)
        if not path.exists() or number is None:
            return None
        sheets = _xlsx_sheets(path)
        index = int(number.group(1)) - 1
        return (path, sheets[index]) if index < len(sheets) else None
    pdfs = sorted(folder.glob("*.pdf"))
    return (pdfs[0], None) if pdfs else None


def wilson(hits: int, total: int) -> tuple[float, float] | None:
    if total == 0:
        return None
    z = 1.959964
    p = hits / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)


def sweep(draw: str, readers: list[str]) -> dict[str, object]:
    manifest = [row for row in csv.DictReader((CORPUS / "manifest.csv").open(encoding="utf-8")) if row["draw"] == draw]
    out_dir = CORPUS / f"sweep_{draw}"
    out_dir.mkdir(exist_ok=True)
    results = []
    for row in manifest:
        folder = CORPUS / row["accession"]
        path = oracle.instance_path(folder)
        instance = oracle.load_instance(path) if path is not None else oracle.Instance()
        reports = {kind: page for kind, _, _, page in oracle.statement_reports(folder)}
        statements = oracle.load_statements(folder)
        for reader in readers:
            for statement in statements:
                target = _targets(reader, folder, row, statement, reports.get(statement.kind, ""))
                if target is None:
                    continue
                document, sheet = target
                audit_path = out_dir / f"{row['accession']}.{reader}.{statement.kind}.json"
                code, message, seconds = _run(document, row["period"] or "latest", sheet, audit_path)
                score = Score(monetary=len(statement.monetary(instance)))
                if code == 0 and audit_path.exists():
                    score = score_audit(json.loads(audit_path.read_text(encoding="utf-8")), statement, instance)
                read = code == 0 and score.wrong == 0 and score.unverified == 0 and score.covered == score.monetary > 0
                results.append({
                    "accession": row["accession"], "label": row["label"], "form": row["form"],
                    "inline_xbrl": row["inline_xbrl"], "reader": reader, "statement": statement.kind,
                    "exit": code, "statement_read": read, "verified": score.verified, "unverified": score.unverified,
                    "wrong": score.wrong, "covered": score.covered, "monetary_lines": score.monetary,
                    "refusal": message, "plain_refusal": code == 2 and _plain(message), "seconds": round(seconds, 2),
                    "details": score.details,
                })
                print(f"{row['label']:>18} {reader:>16} {statement.kind:>13} exit {code} "
                      f"v{score.verified} u{score.unverified} w{score.wrong}", flush=True)
    results_path = CORPUS / f"sweep_{draw}.csv"
    with results_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]) if results else ["accession"])
        writer.writeheader()
        writer.writerows(results)
    return aggregate(results, results_path)


def aggregate(results: list[dict[str, object]], results_path: Path) -> dict[str, object]:
    summary: dict[str, object] = {"results_sha256": hashlib.sha256(results_path.read_bytes()).hexdigest()}
    for reader in sorted({str(r["reader"]) for r in results}):
        rows = [r for r in results if r["reader"] == reader]
        filings = {str(r["accession"]) for r in rows}
        all_three = sum(1 for a in filings if sum(1 for r in rows if r["accession"] == a and r["statement_read"]) == 3)
        refused = [r for r in rows if r["exit"] == 2]
        summary[reader] = {
            "filings": len(filings), "statement_runs": len(rows),
            "statements_read": sum(1 for r in rows if r["statement_read"]),
            "filings_with_all_three_read": all_three, "all_three_rate_95ci": wilson(all_three, len(filings)),
            "refused": len(refused), "refused_plainly": sum(1 for r in refused if r["plain_refusal"]),
            "other_failures": sum(1 for r in rows if r["exit"] not in (0, 2)),
            "lines_verified": sum(int(str(r["verified"])) for r in rows),
            "lines_unverified": sum(int(str(r["unverified"])) for r in rows),
            "lines_wrong": sum(int(str(r["wrong"])) for r in rows),
        }
    return summary


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit("usage: sweep.py <draw> [--readers primary,financial_report,pdf]")
    chosen = ["primary", "financial_report", "pdf"]
    if "--readers" in args:
        chosen = args[args.index("--readers") + 1].split(",")
    print(json.dumps(sweep(args[0], chosen), indent=2))
