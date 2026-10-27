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

    python -I docs/analysts/evidence/sweep.py A --tag <commit> [--readers primary,financial_report,pdf]
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
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
# The tool under test: this venv's entry point, or the CLI's main() on another checkout's
# src/ (VAA_TOOL_SRC), so an earlier commit can be swept without its own installation.
TOOL_SRC = os.environ.get("VAA_TOOL_SRC")
TOOL = ([sys.executable, "-c", "import sys; from variance_agent.cli import main; sys.exit(main())"] if TOOL_SRC
        else [str(Path(sys.executable).with_name("variance-agent"))])
_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
_COLUMN_NOTE = re.compile(r"^Read column '(?P<header>.*)' as (?P<label>.+)$")
_FLIP_NOTE = re.compile(r"^Read '(?P<label>.*)' as (?:income|an expense): the statement prints it as")
_CREDIT_NOTE = re.compile(r"^Read '(?P<label>.*)' as a credit among costs")
_REVENUE = re.compile(r"^us-gaap:(?:Revenues|RevenueFromContractWithCustomer\w*|SalesRevenue\w*|RevenuesNetOfInterestExpense)$")
_FIX_WORDS = re.compile(r"\b(upload|rerun|save|choose|open|give|mark|remove|export|download|unhide|count|leave|pick)\b",
                        re.IGNORECASE)
_JARGON = re.compile(r"Traceback|Error:|Exception|\bschema\b|\bpayload\b|\bXML\b|\bOOXML\b", re.IGNORECASE)


@dataclass
class Score:
    verified: int = 0
    unverified: int = 0
    unverified_no_fact: int = 0  # of those, a printed dash or confirmed blank: no XBRL fact exists (Decision 35)
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


def score_keyed(audit: dict[str, object], statement: oracle.Statement, instance: oracle.Instance) -> Score:
    """Verify an Inline XBRL read by the XBRL key each line carries (concept, period, dimensions)."""
    score = Score()
    document = _group(audit, "source").get("document")
    lines = {str(line.get("line_item")): line for line in _items(document, "lines") if isinstance(line, dict)}
    notes = [str(n) for n in _items(document, "reader_notes")]
    flipped = {m.group("label") for m in (_FLIP_NOTE.match(n) for n in notes) if m}
    credited = {m.group("label") for m in (_CREDIT_NOTE.match(n) for n in notes) if m}
    comparison_label = _group(audit, "comparison").get("label")
    money = {line.concept for line in statement.monetary(instance)}
    score.monetary = len(money)
    covered = {str(line.get("concept")) for line in lines.values()} & money
    problems = []
    for row in _items(audit, "measure_rows"):
        if not isinstance(row, dict) or row.get("measure") != "Currency":
            continue
        name = str(row.get("line_item", ""))
        columns = [c for c in _items(lines.get(name), "columns")]
        prior = next((c for c in columns if isinstance(c, dict) and c.get("label") == comparison_label), None)
        # The actual is the statement's first (newest) column; a blank there has no key and is unverified,
        # never matched against an older column's fact.
        current = columns[0] if columns and isinstance(columns[0], dict) and columns[0].get("label") != comparison_label else None
        for field, key in (("actual", current), ("comparison", prior)):
            value = row.get(field)
            if not isinstance(key, dict) or value is None:
                score.unverified += 1
                score.unverified_no_fact += not isinstance(key, dict)
                continue
            period = tuple(str(part) for part in _items(key, "period"))
            dims = tuple(sorted((str(d.get("axis")), str(d.get("member"))) for d in _items(key, "dims") if isinstance(d, dict)))
            facts = [f for f in instance.lookup(str(key.get("concept")), period, dims)
                     if f.value is not None and f.unit.startswith("iso4217:") and "/" not in f.unit]
            sign = (-1 if name in flipped else 1) * (-1 if name in credited else 1)
            shown_ok = Fraction(str(value)) == sign * Fraction(str(key.get("displayed")))
            if not facts:
                score.unverified += 1
            elif any(Fraction(str(f.value)) == Fraction(str(key.get("stored"))) for f in facts) and shown_ok:
                score.verified += 1
            else:
                score.wrong += 1
                problems.append(f"{name} {field}: tool stored {key.get('stored')} shown {value}, filing {facts[0].value}")
        variance = row.get("variance")
        if variance is not None and row.get("actual") is not None and row.get("comparison") is not None:
            if Fraction(str(variance)) != Fraction(str(row["actual"])) - Fraction(str(row["comparison"])):
                score.wrong += 1
                problems.append(f"{name} variance does not recompute")
    # Subtotals and lines listed as left out were read too: their keys must hold the filing's values.
    # A balance sheet's or cash flow's subtotals are rows, already scored above, so they count once.
    scored = {str(row.get("line_item")) for row in _items(audit, "measure_rows") if isinstance(row, dict)}
    for line in lines.values():
        if not (line.get("subtotal") or line.get("left_out")) or str(line.get("line_item")) in scored:
            continue
        for column in _items(line, "columns"):
            if not isinstance(column, dict):
                continue
            period = tuple(str(part) for part in _items(column, "period"))
            dims = tuple(sorted((str(d.get("axis")), str(d.get("member"))) for d in _items(column, "dims") if isinstance(d, dict)))
            facts = [f for f in instance.lookup(str(column.get("concept")), period, dims) if f.value is not None]
            if not facts:
                score.unverified += 1
            elif any(Fraction(str(f.value)) == Fraction(str(column.get("stored"))) for f in facts):
                score.verified += 1
            else:
                score.wrong += 1
                problems.append(f"{line.get('line_item')}: stored {column.get('stored')}, filing {facts[0].value}")
    # A derived figure: where the statement prints its revenue as one fact, Total Revenue must equal it.
    revenue_lines = [line for line in lines.values() if _REVENUE.match(str(line.get("concept")))
                     and not any(isinstance(c, dict) and _items(c, "dims") for c in _items(line, "columns"))]
    total = _group(_group(audit, "totals"), "revenue")
    if len(revenue_lines) == 1 and total.get("actual") is not None:
        latest = next((c for c in _items(revenue_lines[0], "columns")
                       if isinstance(c, dict) and c.get("label") != comparison_label), None)
        if isinstance(latest, dict) and Fraction(str(total["actual"])) != Fraction(str(latest.get("displayed"))):
            score.wrong += 1
            problems.append(f"Total Revenue {total['actual']} is not the filing's revenue {latest.get('displayed')}")
    # Every headline figure (Decision 39) must be its own fact, and its change must recompute; where the statement
    # prints one dimensionless revenue line, the headline must carry it.
    headline = _group(_group(_group(audit, "source"), "document"), "headline")
    for item in _items(headline, "items"):
        if not isinstance(item, dict):
            continue
        keys = [item.get("actual"), item.get("comparison")]
        for key in keys:
            if not isinstance(key, dict):
                score.wrong += 1
                problems.append(f"headline {item.get('line_item')} has no fact key")
                continue
            period = tuple(str(part) for part in _items(key, "period"))
            facts = [f for f in instance.lookup(str(key.get("concept")), period, ()) if f.value is not None]
            if not any(Fraction(str(f.value)) == Fraction(str(key.get("stored"))) for f in facts):
                score.wrong += 1
                problems.append(f"headline {item.get('line_item')}: stored {key.get('stored')} is not a filing fact")
        if all(isinstance(key, dict) for key in keys) and Fraction(str(item.get("change"))) != (
                Fraction(str(keys[0]["displayed"])) - Fraction(str(keys[1]["displayed"]))):  # type: ignore[index]
            score.wrong += 1
            problems.append(f"headline {item.get('line_item')} change does not recompute")
    if headline and len(revenue_lines) == 1 and not any(
            isinstance(item, dict) and item.get("concept") == revenue_lines[0].get("concept")
            and item.get("role") == "revenue" for item in _items(headline, "items")):
        score.wrong += 1
        problems.append("headline lacks the filing's one revenue line")
    score.covered = len(covered)
    score.details = "; ".join(problems)[:500]
    return score


def score_audit(audit: dict[str, object], statement: oracle.Statement, instance: oracle.Instance) -> Score:
    """Verify each read line of an audit against the oracle (keyless reads match by printed label)."""
    if _group(_group(audit, "source"), "document").get("kind") == "ixbrl":
        return score_keyed(audit, statement, instance)
    score = Score()
    notes = [str(note) for note in _items(_group(audit, "source").get("document"), "reader_notes")]
    columns = [m for m in (_COLUMN_NOTE.match(n) for n in notes) if m]
    flipped = {m.group("label") for m in (_FLIP_NOTE.match(n) for n in notes) if m}
    by_label: dict[str, list[oracle.Line]] = {}
    for line in statement.lines:
        by_label.setdefault(_normal(line.label), []).append(line)
    money = {line.concept for line in statement.monetary(instance)}
    score.monetary = len(money)
    labels = {m.group("label"): _periods(m.group("header")) for m in columns}
    current_label = _group(audit, "audience").get("actual_label")
    comparison_label = _group(audit, "comparison").get("label")
    current = labels.get(str(current_label)) or (list(labels.values())[0] if labels else [])
    prior = labels.get(str(comparison_label)) or (list(labels.values())[1] if len(labels) > 1 else [])
    covered: set[str] = set()
    for name in _items(_group(audit, "transformations"), "excluded_totals"):
        for line in _candidates(by_label, str(name)):
            covered.add(line.concept)
    problems = []
    rows = [row for row in _items(audit, "measure_rows") if isinstance(row, dict) and row.get("measure") == "Currency"]
    totals: dict[str, int] = {}
    for row in rows:
        totals[_key(by_label, str(row.get("line_item", "")))] = totals.get(_key(by_label, str(row.get("line_item", ""))), 0) + 1
    seen: dict[str, int] = {}
    for row in rows:
        name = str(row.get("line_item", ""))
        key = _key(by_label, name)
        candidates = by_label.get(key, [])
        occurrence = seen.get(key, 0)
        seen[key] = occurrence + 1
        # A repeated label is keyed by its place among the repeats, and only when both sides repeat it
        # equally often; otherwise the key is ambiguous and the read is unverified.
        if not candidates or (len(candidates) > 1 and totals[key] != len(candidates)):
            score.unverified += 2
            continue
        line = candidates[occurrence if len(candidates) > 1 else 0]
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


def _key(by_label: dict[str, list[oracle.Line]], name: str) -> str:
    """The oracle label a tool line name stands for, undoing the tool's renaming of repeated lines."""
    for candidate in (name, name.rpartition(": ")[2], re.sub(r"\s*\([^()]*\)$", "", name)):
        if _normal(candidate) in by_label:
            return _normal(candidate)
    return _normal(name)


def _candidates(by_label: dict[str, list[oracle.Line]], name: str) -> list[oracle.Line]:
    return by_label.get(_key(by_label, name), [])


def _plain(message: str) -> bool:
    return bool(message) and bool(_FIX_WORDS.search(message)) and not _JARGON.search(message)


def _run(document: Path, period: str, sheet: str | None, out: Path) -> tuple[int, str, float]:
    command = [*TOOL, str(document), "--assisted", "--compare-to", "prior-period", "--period", period,
               "--dollar-threshold", "1", "--percent-threshold", "1", "--audit-json", str(out),
               "--audit-schema-version", "1.9", "-o", str(out.with_suffix(".md"))]
    if sheet is not None:
        command += ["--sheet", sheet]
    started = time.monotonic()
    try:
        env = {**os.environ, "PYTHONPATH": TOOL_SRC} if TOOL_SRC else None
        done = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False, env=env)
    except subprocess.TimeoutExpired:
        return -1, "timed out after 120 seconds", time.monotonic() - started
    message = done.stderr.strip().splitlines()[-1] if done.returncode and done.stderr.strip() else ""
    return done.returncode, message.removeprefix("variance-agent: error: "), time.monotonic() - started


_LISTED = re.compile(r"Statements found: (.*?)\.(?: Choose one of those statements\.)?$")


_LISTINGS: dict[Path, list[str]] = {}


def _statement_name(document: Path, kind: str) -> str | None:
    """The tool's own name for the statement of `kind`, from the listing it prints for an unknown name."""
    if not document.name.lower().endswith((".htm", ".html", ".pdf")):
        return None
    if document not in _LISTINGS:
        code, message, _ = _run(document, "listing", "?", CORPUS / "listing.json")
        found = _LISTED.search(message) if code == 2 else None
        names: list[str] = []
        for part in (found.group(1).split(", ") if found else []):
            if names and re.match(r"\d+ Months Ended\b", part):
                names[-1] += ", " + part  # a duration names one statement of several
            else:
                names.append(part)
        _LISTINGS[document] = names
    return next((name for name in _LISTINGS[document] if oracle.statement_kind(name) == kind), None)


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
        document = folder / row["primary"]
        name = _statement_name(document, statement.kind)
        # A statement the tool doesn't list is asked for by the filing's own title, so the run records the tool's
        # plain "No statement called ..." refusal instead of reading its default statement (STOP 2 fresh eyes, W1).
        if name is None and document.name.lower().endswith((".htm", ".html")):
            name = statement.title or statement.kind.replace("_", " ")
        return document, name
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


def sweep(draw: str, readers: list[str], tag: str) -> dict[str, object]:
    manifest = [row for row in csv.DictReader((CORPUS / "manifest.csv").open(encoding="utf-8")) if row["draw"] == draw]
    out_dir = CORPUS / f"sweep_{draw}_{tag}"
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
                    "unverified_no_fact": score.unverified_no_fact, "wrong": score.wrong,
                    "covered": score.covered, "monetary_lines": score.monetary,
                    "refusal": message, "plain_refusal": code == 2 and _plain(message), "seconds": round(seconds, 2),
                    "details": score.details,
                })
                print(f"{row['label']:>18} {reader:>16} {statement.kind:>13} exit {code} "
                      f"v{score.verified} u{score.unverified} w{score.wrong}", flush=True)
    # One file per run, named by the tool commit swept, so no run overwrites another's evidence.
    results_path = CORPUS / f"sweep_{draw}_{tag}.csv"
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
        # Section 5's target: Inline XBRL filings that contain statements (a filing without any has no rows).
        inline = {str(r["accession"]) for r in rows if str(r["inline_xbrl"]) == "1"}
        all_three = sum(1 for a in inline if sum(1 for r in rows if r["accession"] == a and r["statement_read"]) == 3)
        unrefused = sum(1 for a in inline if sum(1 for r in rows if r["accession"] == a and r["exit"] == 0) == 3)
        refused = [r for r in rows if r["exit"] == 2]
        summary[reader] = {
            "filings": len(filings), "inline_xbrl_filings": len(inline), "statement_runs": len(rows),
            "statements_read": sum(1 for r in rows if r["statement_read"]),
            "filings_with_all_three_read": all_three, "all_three_rate_95ci": wilson(all_three, len(inline)),
            "filings_with_all_three_unrefused": unrefused, "all_three_unrefused_95ci": wilson(unrefused, len(inline)),
            "refused": len(refused), "refused_plainly": sum(1 for r in refused if r["plain_refusal"]),
            "other_failures": sum(1 for r in rows if r["exit"] not in (0, 2)),
            "lines_verified": sum(int(str(r["verified"])) for r in rows),
            "lines_unverified": sum(int(str(r["unverified"])) for r in rows),
            "lines_unverified_no_fact": sum(int(str(r.get("unverified_no_fact", 0) or 0)) for r in rows),
            "lines_wrong": sum(int(str(r["wrong"])) for r in rows),
        }
    return summary


def aggregate_csv(path: Path) -> dict[str, object]:
    """Recompute the aggregate from a sweep's per-filing CSV, without re-running the tool."""
    rows: list[dict[str, object]] = []
    for row in csv.DictReader(path.open(encoding="utf-8")):
        rows.append({**row, "exit": int(row["exit"]), "statement_read": row["statement_read"] == "True",
                     "plain_refusal": row["plain_refusal"] == "True"})
    return aggregate(rows, path)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--aggregate"]:
        print(json.dumps(aggregate_csv(Path(args[1])), indent=2))
        raise SystemExit(0)
    if not args:
        raise SystemExit("usage: sweep.py <draw> [--readers primary,financial_report,pdf]")
    chosen = ["primary", "financial_report", "pdf"]
    if "--readers" in args:
        chosen = args[args.index("--readers") + 1].split(",")
    tag = args[args.index("--tag") + 1] if "--tag" in args else "run"
    print(json.dumps(sweep(args[0], chosen, tag), indent=2))
