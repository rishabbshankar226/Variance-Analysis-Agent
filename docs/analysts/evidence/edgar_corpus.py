"""Draw and fetch a seeded random sample of 10-K and 10-Q filings from SEC EDGAR.

A development tool for the analyst-coverage sweep (docs/analysts/PLAN.md); nothing under src/
imports it. It needs EDGAR_USER_AGENT ("Name email", as the SEC asks of automated clients),
sends it on every request, and stays under 5 requests per second. Everything it downloads or
writes lives in the corpus folder ($VAA_EDGAR_CORPUS, default ~/vaa-edgar-corpus), never in
the repository: the repository gets only aggregates and checksums.

    python -I docs/analysts/evidence/edgar_corpus.py index 2025Q4 2026Q1 2026Q2 2026Q3 2018Q1
    python -I docs/analysts/evidence/edgar_corpus.py draw A --seed 20261026
    python -I docs/analysts/evidence/edgar_corpus.py fetch A
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CORPUS = Path(os.environ.get("VAA_EDGAR_CORPUS", str(Path.home() / "vaa-edgar-corpus")))
_HOSTS = ("https://www.sec.gov/", "https://data.sec.gov/")
_MIN_INTERVAL = 0.25  # seconds between requests: 4 per second, under half the SEC's 10
_RECENT = ("2025Q4", "2026Q1", "2026Q2", "2026Q3")
_OLD = "2018Q1"
_FILE_NAME = re.compile(r"^edgar/data/(\d+)/(\d{10}-\d{2}-\d{6})\.txt$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_PRIMARY = 32 * 1024 * 1024  # the tool's capture limit


class Refused(RuntimeError):
    """The SEC refused a request; the run records it and stops for the owner (STOP-ASK)."""


@dataclass(frozen=True)
class Filing:
    form: str
    company: str
    cik: str
    date_filed: str
    accession: str
    quarter: str


_last_request = 0.0


def _get(url: str) -> bytes:
    """One rate-limited GET to an SEC host, with the contact header; refusals raise Refused."""
    global _last_request
    if not url.startswith(_HOSTS):
        raise ValueError(f"not an SEC URL: {url}")
    agent = os.environ.get("EDGAR_USER_AGENT", "").strip()
    if not agent:
        raise SystemExit("Set EDGAR_USER_AGENT to 'Name email' before fetching from EDGAR.")
    for attempt in range(3):
        wait = _MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        request = urllib.request.Request(url, headers={"User-Agent": agent, "Accept-Encoding": "identity"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                raise Refused(f"HTTP {exc.code} for {url}") from exc
            if exc.code == 404:
                raise
            if attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(2.0 * (attempt + 1))
    raise AssertionError("unreachable")


def _cached(path: Path, url: str) -> bytes:
    if path.exists():
        return path.read_bytes()
    body = _get(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def _index_path(quarter: str) -> Path:
    return CORPUS / "index" / f"{quarter[:4]}QTR{quarter[-1]}.form.idx"


def fetch_index(quarter: str) -> bytes:
    url = f"https://www.sec.gov/Archives/edgar/full-index/{quarter[:4]}/QTR{quarter[-1]}/form.idx"
    return _cached(_index_path(quarter), url)


def parse_index(text: str, quarter: str) -> list[Filing]:
    """Rows of form.idx, after confirming its column layout from the header line."""
    lines = text.splitlines()
    header_at = next((i for i, line in enumerate(lines) if line.startswith("Form Type")), None)
    if header_at is None or not set(lines[header_at + 1].strip()) <= {"-"}:
        raise ValueError(f"{quarter}: form.idx has no 'Form Type' header followed by a rule")
    header = lines[header_at]
    starts = [header.find(name) for name in ("Form Type", "Company Name", "CIK", "Date Filed", "File Name")]
    if starts != sorted(starts) or -1 in starts:
        raise ValueError(f"{quarter}: unexpected form.idx columns: {header!r}")
    filings: list[Filing] = []
    bad = 0
    for line in lines[header_at + 2:]:
        if not line.strip():
            continue
        form = line[:starts[1]].strip()
        rest = line[starts[1]:].rstrip().rsplit(None, 3)
        if len(rest) != 4:
            bad += 1
            continue
        company, cik, filed, name = rest
        match = _FILE_NAME.match(name)
        if not (cik.isdigit() and _DATE.match(filed) and match and match[1] == cik):
            bad += 1
            continue
        filings.append(Filing(form, company.strip(), cik, filed, match[2], quarter))
    if bad > len(filings) // 1000:
        raise ValueError(f"{quarter}: {bad} unparseable form.idx rows")
    return filings


def submissions(cik: str) -> dict[str, object]:
    padded = cik.zfill(10)
    body = _cached(CORPUS / "submissions" / f"CIK{padded}.json", f"https://data.sec.gov/submissions/CIK{padded}.json")
    data: dict[str, object] = json.loads(body)
    return data


def _sic(cik: str) -> int | None:
    value = str(submissions(cik).get("sic") or "")
    return int(value) if value.isdigit() else None


def _category(cik: str) -> str:
    return str(submissions(cik).get("category") or "").lower()


STRATA: tuple[tuple[str, str, Callable[[str], bool]], ...] = (
    ("bank", "10-K|10-Q", lambda cik: _sic(cik) in {6021, 6022, 6035, 6036}),
    ("insurer", "10-K|10-Q", lambda cik: (_sic(cik) or 0) in range(6311, 6400)),
    ("reit", "10-K|10-Q", lambda cik: _sic(cik) == 6798),
    ("large_accelerated", "10-K|10-Q", lambda cik: "large accelerated filer" in _category(cik)),
    ("smaller_reporting", "10-K|10-Q", lambda cik: "smaller reporting company" in _category(cik)),
    ("amendment", "10-K/A", lambda cik: True),
)


def _pool(filings: list[Filing], forms: str) -> list[Filing]:
    wanted = set(forms.split("|"))
    return sorted((f for f in filings if f.form in wanted), key=lambda f: f.accession)


def draw_a(seed: int) -> tuple[list[tuple[str, Filing]], dict[str, int]]:
    """Draw A (PLAN.md, Phase 2 corpus settings): 40 filings, one per filer."""
    recent = [f for quarter in _RECENT for f in parse_index(fetch_index(quarter).decode("latin-1"), quarter)]
    old = parse_index(fetch_index(_OLD).decode("latin-1"), _OLD)
    rng = random.Random(seed)
    used: set[str] = set()
    picks: list[tuple[str, Filing]] = []
    sizes: dict[str, int] = {}

    def take(label: str, pool: list[Filing], count: int, keep: Callable[[str], bool] = lambda cik: True) -> None:
        order = list(pool)
        rng.shuffle(order)
        sizes[label] = len(pool)
        taken = 0
        for filing in order:
            if taken == count:
                break
            if filing.cik in used or not keep(filing.cik):
                continue
            used.add(filing.cik)
            picks.append((label, filing))
            taken += 1
        if taken < count:
            raise ValueError(f"{label}: only {taken} of {count} filings found")

    take("10-K", _pool(recent, "10-K"), 14)
    take("10-Q", _pool(recent, "10-Q"), 14)
    for label, forms, keep in STRATA:
        take(label, _pool(recent, forms), 1, keep)
    take("2018 10-K", _pool(old, "10-K"), 3)
    take("2018 10-Q", _pool(old, "10-Q"), 3)
    return picks, sizes


def draw_b(seed: int, earlier: tuple[str, ...] = ("A",)) -> tuple[list[tuple[str, Filing]], dict[str, int]]:
    """A held-out draw (section 5): 30 filings, 15 of each form, uniform over the same four quarters, one per
    filer, excluding every accession and filer of the earlier draws (Draw B: A; Draw C: A and B, Decision 39)."""
    recent = [f for quarter in _RECENT for f in parse_index(fetch_index(quarter).decode("latin-1"), quarter)]
    drawn = [row for name in earlier for row in csv.DictReader((CORPUS / f"draw_{name}.csv").open(encoding="utf-8"))]
    excluded = {row["cik"] for row in drawn} | {row["accession"] for row in drawn}
    rng = random.Random(seed)
    used: set[str] = set()
    picks: list[tuple[str, Filing]] = []
    sizes: dict[str, int] = {}
    for label in ("10-K", "10-Q"):
        pool = [f for f in _pool(recent, label) if f.cik not in excluded and f.accession not in excluded]
        order = list(pool)
        rng.shuffle(order)
        sizes[label] = len(pool)
        taken = 0
        for filing in order:
            if taken == 15:
                break
            if filing.cik in used:
                continue
            used.add(filing.cik)
            picks.append((label, filing))
            taken += 1
        if taken < 15:
            raise ValueError(f"{label}: only {taken} of 15 filings found")
    return picks, sizes


def _filing_record(cik: str, accession: str) -> dict[str, str]:
    """The submissions entry for one accession, searching the paged history when needed."""
    data = submissions(cik)
    pages: list[dict[str, object]] = []
    filings = data.get("filings")
    if isinstance(filings, dict):
        recent = filings.get("recent")
        if isinstance(recent, dict):
            pages.append(recent)
        for extra in filings.get("files", []) if isinstance(filings.get("files"), list) else []:
            name = str(extra.get("name", "")) if isinstance(extra, dict) else ""
            if re.fullmatch(r"CIK\d{10}-submissions-\d{3}\.json", name):
                pages.append(json.loads(_cached(CORPUS / "submissions" / name, f"https://data.sec.gov/submissions/{name}")))
    for page in pages:
        numbers = page.get("accessionNumber")
        if isinstance(numbers, list) and accession in numbers:
            at = numbers.index(accession)
            return {key: str(values[at]) for key, values in page.items() if isinstance(values, list) and at < len(values)}
    raise ValueError(f"{accession} is not in the submissions record of CIK {cik}")


def _wanted(names: list[str], primary: str) -> list[str]:
    """The files the sweep and oracle use from one filing folder."""
    lowered = {name.lower(): name for name in names}
    keep = [primary] if primary in names else []
    inline = [name for name in names if name.lower().endswith("_htm.xml")]
    instance = inline or [name for name in names if re.fullmatch(r"[a-z0-9.\-]+-\d{8}\.xml", name.lower())
                          and not re.search(r"_(cal|def|lab|pre|ref)\.xml$", name.lower())]
    keep += instance[:1]
    keep += [name for name in names if re.search(r"_(pre|lab)\.xml$", name.lower())]
    keep += [lowered[name] for name in ("financial_report.xlsx", "filingsummary.xml") if name in lowered]
    keep += [name for name in names if name.lower().endswith(".pdf")]
    return list(dict.fromkeys(keep))


def _statement_pages(summary: bytes) -> list[str]:
    """R pages the FilingSummary files under its statements category, for filings without a linkbase."""
    pages = re.findall(rb"<Report[^>]*>(.*?)</Report>", summary, re.DOTALL)
    found = []
    for report in pages:
        category = re.search(rb"<MenuCategory>(.*?)</MenuCategory>", report)
        page = re.search(rb"<HtmlFileName>(R\d+\.htm)</HtmlFileName>", report)
        if category and page and category.group(1).strip().lower() == b"statements":
            found.append(page.group(1).decode("ascii"))
    return found


def fetch(draw: str, seed: int) -> None:
    picks = list(csv.DictReader((CORPUS / f"draw_{draw}.csv").open(encoding="utf-8")))
    manifest_path = CORPUS / "manifest.csv"
    rows = [row for row in csv.DictReader(manifest_path.open(encoding="utf-8"))] if manifest_path.exists() else []
    done = {row["accession"] for row in rows if row["draw"] == draw}
    largest = 0
    for pick in picks:
        accession, cik = pick["accession"], pick["cik"]
        if accession in done:
            continue
        record = _filing_record(cik, accession)
        primary = record.get("primaryDocument", "")
        folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
        listing = json.loads(_cached(CORPUS / accession / "index.json", folder + "index.json"))
        names = [str(item["name"]) for item in listing["directory"]["item"]]
        target = CORPUS / accession
        files = _wanted(names, primary)
        if not any(re.search(r"_pre\.xml$", name.lower()) for name in files) and "FilingSummary.xml" in files:
            summary = _cached(target / "FilingSummary.xml", folder + "FilingSummary.xml")
            files += [page for page in _statement_pages(summary) if page in names]
        entries = []
        for name in files:
            body = _cached(target / name, folder + name)
            entries.append(f"{name}={len(body)}:{hashlib.sha256(body).hexdigest()}")
            if name == primary:
                largest = max(largest, len(body))
        submission = submissions(cik)
        rows.append({
            "draw": draw, "label": pick["label"], "accession": accession, "form": record.get("form", pick["form"]),
            "cik": cik, "company": pick["company"], "sic": str(submission.get("sic") or ""),
            "category": str(submission.get("category") or "").replace("<br>", "; "),
            "period": record.get("reportDate", ""), "date_filed": pick["date_filed"],
            "inline_xbrl": record.get("isInlineXBRL", ""), "primary": primary, "files": ";".join(entries),
            "seed": str(seed),
        })
        _write_manifest(manifest_path, rows)
        print(f"{pick['label']:>18} {accession} {len(files)} files", flush=True)
    print(f"largest primary document this run: {largest:,} bytes (cap {_MAX_PRIMARY:,})")


def _write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["draw", "label", "accession", "form", "cik", "company", "sic", "category", "period", "date_filed",
              "inline_xbrl", "primary", "files", "seed"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index")
    index.add_argument("quarters", nargs="+")
    draw = sub.add_parser("draw")
    draw.add_argument("name", choices=("A", "B", "C"))
    draw.add_argument("--seed", type=int, required=True)
    get = sub.add_parser("fetch")
    get.add_argument("name", choices=("A", "B", "C"))
    args = parser.parse_args(argv)
    try:
        if args.command == "index":
            for quarter in args.quarters:
                rows = parse_index(fetch_index(quarter).decode("latin-1"), quarter)
                print(f"{quarter}: {len(rows):,} rows; 10-K {sum(r.form == '10-K' for r in rows):,}, "
                      f"10-Q {sum(r.form == '10-Q' for r in rows):,}, 10-K/A {sum(r.form == '10-K/A' for r in rows):,}")
        elif args.command == "draw":
            picks, sizes = (draw_a(args.seed) if args.name == "A" else draw_b(args.seed) if args.name == "B"
                            else draw_b(args.seed, ("A", "B")))
            with (CORPUS / f"draw_{args.name}.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["label", "accession", "form", "cik", "company", "date_filed", "quarter", "seed"])
                for label, filing in picks:
                    writer.writerow([label, filing.accession, filing.form, filing.cik, filing.company,
                                     filing.date_filed, filing.quarter, args.seed])
            (CORPUS / f"draw_{args.name}_pools.json").write_text(json.dumps(sizes, indent=2), encoding="utf-8")
            print(f"drew {len(picks)} filings from pools {sizes}")
        else:
            seed = int(next(csv.DictReader((CORPUS / f"draw_{args.name}.csv").open(encoding="utf-8")))["seed"])
            fetch(args.name, seed)
    except Refused as exc:
        (CORPUS / "refusals.log").open("a", encoding="utf-8").write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {exc}\n")
        print(f"EDGAR refused a request: {exc}. Recorded in refusals.log; stopping for the owner.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
