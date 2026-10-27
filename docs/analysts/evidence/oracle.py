"""The sweep's oracle for one EDGAR filing folder: XBRL fact values and statement structure.

A development tool (docs/analysts/PLAN.md, section 5 of the spec); it never imports
variance_agent. Values come from the XBRL instance the SEC publishes beside a filing, indexed by
concept, context period, dimension set and unit. Structure comes from the presentation linkbase
role that FilingSummary.xml files under its statements category (or that statement's R page
when there is no linkbase), filtered to the income statement, balance sheet and cash flow
statement. Every XML file is refused when it declares a DOCTYPE or ENTITY, before parsing.

    python -I docs/analysts/evidence/oracle.py index A    # one row per Draw A filing
"""

from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree

CORPUS = Path(os.environ.get("VAA_EDGAR_CORPUS", str(Path.home() / "vaa-edgar-corpus")))
XBRLI = "{http://www.xbrl.org/2003/instance}"
LINK = "{http://www.xbrl.org/2003/linkbase}"
XLINK = "{http://www.w3.org/1999/xlink}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"
_DECLARATION = re.compile(rb"<!\s*(?:doctype|entity)", re.IGNORECASE)
_STANDARD_LABEL = "http://www.xbrl.org/2003/role/label"

Period = tuple[str, ...]  # ("instant", date) or ("duration", start, end)
Dims = tuple[tuple[str, str], ...]  # sorted (axis, member)


def _parse(path: Path) -> ElementTree.Element:
    data = path.read_bytes()
    if _DECLARATION.search(data):
        raise ValueError(f"{path.name}: DOCTYPE or ENTITY declarations are refused")
    return ElementTree.fromstring(data)


def _namespaces(path: Path) -> dict[str, str]:
    """Namespace URI -> the prefix the document declares for it."""
    found: dict[str, str] = {}
    data = path.read_bytes()
    if _DECLARATION.search(data):
        raise ValueError(f"{path.name}: DOCTYPE or ENTITY declarations are refused")
    from io import BytesIO
    for _, (prefix, uri) in ElementTree.iterparse(BytesIO(data), events=("start-ns",)):
        found.setdefault(uri, prefix)
    return found


@dataclass(frozen=True)
class Fact:
    concept: str  # "us-gaap:Revenues"
    period: Period
    dims: Dims
    unit: str  # "iso4217:USD", "iso4217:USD/xbrli:shares", "" for non-numeric
    value: Decimal | None  # None for nil or non-numeric
    decimals: str
    text: str


@dataclass
class Instance:
    facts: list[Fact] = field(default_factory=list)
    by_key: dict[tuple[str, Period, Dims, str], list[Fact]] = field(default_factory=lambda: defaultdict(list))

    def lookup(self, concept: str, period: Period, dims: Dims = (), unit: str | None = None) -> list[Fact]:
        if unit is not None:
            return list(self.by_key.get((concept, period, dims, unit), ()))
        return [fact for (c, p, d, _), facts in self.by_key.items() if c == concept and p == period and d == dims
                for fact in facts]

    def concepts_with_money(self) -> set[str]:
        # A nil fact states that the line has no amount (PLAN.md Decision 33), so it is not a line to read.
        return {f.concept for f in self.facts if f.unit.startswith("iso4217:") and "/" not in f.unit and f.value is not None}


def load_instance(path: Path) -> Instance:
    prefixes = _namespaces(path)
    root = _parse(path)

    def qname(tag: str) -> str:
        uri, _, local = tag[1:].partition("}")
        return f"{prefixes.get(uri, uri)}:{local}"

    contexts: dict[str, tuple[Period, Dims]] = {}
    for context in root.iter(f"{XBRLI}context"):
        instant = context.findtext(f"{XBRLI}period/{XBRLI}instant")
        start = context.findtext(f"{XBRLI}period/{XBRLI}startDate")
        end = context.findtext(f"{XBRLI}period/{XBRLI}endDate")
        period: Period = ("instant", instant.strip()) if instant else ("duration", (start or "").strip(), (end or "").strip())
        members: list[tuple[str, str]] = []
        for member in context.iter(f"{XBRLDI}explicitMember"):
            members.append((member.get("dimension", ""), (member.text or "").strip()))
        for member in context.iter(f"{XBRLDI}typedMember"):
            members.append((member.get("dimension", ""), "typed:" + "".join(member.itertext()).strip()))
        contexts[context.get("id", "")] = (period, tuple(sorted(members)))
    units: dict[str, str] = {}
    for unit in root.iter(f"{XBRLI}unit"):
        measures = [m.text.strip() for m in unit.iter(f"{XBRLI}measure") if m.text]
        divide = unit.find(f"{XBRLI}divide")
        units[unit.get("id", "")] = "/".join(measures) if divide is not None else "*".join(measures)
    instance = Instance()
    for element in root:
        reference = element.get("contextRef")
        if reference is None or reference not in contexts:
            continue
        period, dims = contexts[reference]
        text = (element.text or "").strip()
        value: Decimal | None = None
        if element.get("unitRef") is not None and element.get(XSI_NIL) != "true":
            try:
                value = Decimal(text)
            except InvalidOperation:
                value = None
        fact = Fact(qname(element.tag), period, dims, units.get(element.get("unitRef") or "", ""), value,
                    element.get("decimals", ""), text[:200])
        instance.facts.append(fact)
        instance.by_key[(fact.concept, period, dims, fact.unit)].append(fact)
    return instance


@dataclass(frozen=True)
class Line:
    concept: str
    label: str
    depth: int
    preferred_label: str  # the label role the statement prints with ("" for the standard label)


@dataclass(frozen=True)
class Statement:
    kind: str  # "income", "balance_sheet" or "cash_flow"
    title: str
    role: str
    lines: tuple[Line, ...]

    def monetary(self, instance: Instance) -> list[Line]:
        money = instance.concepts_with_money()
        return [line for line in self.lines if line.concept in money]


_PARENTHETICAL = re.compile(r"parenthetical", re.IGNORECASE)
_EQUITY = re.compile(r"equity|stockholders|shareholders|partners|members'? capital|changes in capital", re.IGNORECASE)


def statement_kind(title: str) -> str | None:
    """The rule recorded in PLAN.md: the three face statements, by the report's title."""
    if _PARENTHETICAL.search(title):
        return None
    if re.search(r"cash\s+flows?", title, re.IGNORECASE):
        return "cash_flow"
    if re.search(r"balance\s+sheets?|financial\s+(?:position|condition)|statements?\s+of\s+condition"
                 r"|statements?\s+of\s+assets\s+and\s+liabilities", title, re.IGNORECASE):
        return "balance_sheet"
    if _EQUITY.search(title) and not re.search(r"operations|earnings", title, re.IGNORECASE):
        return None
    if re.search(r"comprehensive", title, re.IGNORECASE) and not re.search(r"operations|earnings|income\s+and", title,
                                                                              re.IGNORECASE):
        return None  # a separate statement of comprehensive income
    if re.search(r"operations|income|earnings|loss", title, re.IGNORECASE):
        return "income"
    return None


def statement_reports(folder: Path) -> list[tuple[str, str, str, str]]:
    """(kind, title, role, R page) of the face statements in FilingSummary.xml, first of each kind."""
    summary = folder / "FilingSummary.xml"
    if not summary.exists():
        return []
    root = _parse(summary)
    chosen: dict[str, tuple[str, str, str, str]] = {}
    for report in root.iter("Report"):
        if (report.findtext("MenuCategory") or "").strip().lower() != "statements":
            continue
        title = (report.findtext("LongName") or report.findtext("ShortName") or "").strip()
        title = re.sub(r"^\d+\s*-\s*Statement\s*-\s*", "", title)
        kind = statement_kind(title)
        if kind is not None and kind not in chosen:
            chosen[kind] = (kind, title, (report.findtext("Role") or "").strip(), (report.findtext("HtmlFileName") or "").strip())
    return list(chosen.values())


def _concept_of(href: str) -> str:
    fragment = href.rpartition("#")[2]
    prefix, _, local = fragment.partition("_")
    return f"{prefix}:{local}" if local else fragment


def _labels(folder: Path) -> dict[str, dict[str, str]]:
    """concept -> label role -> text, from the label linkbase."""
    found: dict[str, dict[str, str]] = defaultdict(dict)
    for path in folder.glob("*_lab.xml"):
        root = _parse(path)
        for link in root.iter(f"{LINK}labelLink"):
            locs = {loc.get(f"{XLINK}label", ""): _concept_of(loc.get(f"{XLINK}href", "")) for loc in link.iter(f"{LINK}loc")}
            texts: dict[str, list[tuple[str, str]]] = defaultdict(list)
            for label in link.iter(f"{LINK}label"):
                texts[label.get(f"{XLINK}label", "")].append((label.get(f"{XLINK}role", _STANDARD_LABEL),
                                                               " ".join("".join(label.itertext()).split())))
            for arc in link.iter(f"{LINK}labelArc"):
                concept = locs.get(arc.get(f"{XLINK}from", ""))
                if concept is None:
                    continue
                for role, text in texts.get(arc.get(f"{XLINK}to", ""), []):
                    found[concept].setdefault(role, text)
    return found


def _presentation(folder: Path, role: str, labels: dict[str, dict[str, str]]) -> list[Line]:
    for path in folder.glob("*_pre.xml"):
        root = _parse(path)
        for link in root.iter(f"{LINK}presentationLink"):
            if link.get(f"{XLINK}role") != role:
                continue
            locs = {loc.get(f"{XLINK}label", ""): _concept_of(loc.get(f"{XLINK}href", "")) for loc in link.iter(f"{LINK}loc")}
            children: dict[str, list[tuple[Decimal, str, str]]] = defaultdict(list)
            targets: set[str] = set()
            for arc in link.iter(f"{LINK}presentationArc"):
                parent, child = arc.get(f"{XLINK}from", ""), arc.get(f"{XLINK}to", "")
                try:
                    order = Decimal(arc.get("order", "1"))
                except InvalidOperation:
                    order = Decimal(1)
                children[parent].append((order, child, arc.get("preferredLabel", "")))
                targets.add(child)
            roots = [label for label in locs if label not in targets and label in children]
            lines: list[Line] = []
            # Depth-first in arc order, iteratively; a cyclic linkbase cannot recurse forever.
            stack = [(node, 0, "") for node in reversed(roots)]
            seen: set[str] = set()
            while stack:
                node, depth, preferred = stack.pop()
                if node in seen:
                    continue
                seen.add(node)
                concept = locs.get(node, node)
                text = labels.get(concept, {})
                lines.append(Line(concept, text.get(preferred) or text.get(_STANDARD_LABEL) or concept, depth, preferred))
                stack.extend((child, depth + 1, child_label)
                             for _, child, child_label in sorted(children.get(node, []), reverse=True))
            return lines
    return []


def _r_page_lines(folder: Path, page: str) -> list[Line]:
    """Fallback structure: the concepts an R page prints, in order (its defref_ anchors)."""
    path = folder / page
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = []
    for match in re.finditer(r"defref_([A-Za-z0-9\-]+)_([A-Za-z0-9]+)'.*?>(.*?)</a>", text, re.DOTALL):
        label = " ".join(re.sub(r"<[^>]+>", "", match.group(3)).split())
        lines.append(Line(f"{match.group(1)}:{match.group(2)}", label, 0, ""))
    return lines


def load_statements(folder: Path) -> list[Statement]:
    labels = _labels(folder)
    statements = []
    for kind, title, role, page in statement_reports(folder):
        lines = _presentation(folder, role, labels) or _r_page_lines(folder, page)
        statements.append(Statement(kind, title, role, tuple(lines)))
    return statements


def instance_path(folder: Path) -> Path | None:
    inline = sorted(folder.glob("*_htm.xml"))
    if inline:
        return inline[0]
    plain = [p for p in sorted(folder.glob("*.xml")) if re.fullmatch(r"[a-z0-9.\-]+-\d{8}\.xml", p.name.lower())]
    return plain[0] if plain else None


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] != "index":
        print("usage: oracle.py index <draw>", file=sys.stderr)
        return 2
    manifest = [row for row in csv.DictReader((CORPUS / "manifest.csv").open(encoding="utf-8")) if row["draw"] == argv[1]]
    out = CORPUS / f"oracle_{argv[1]}.csv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["accession", "instance", "facts", "monetary_concepts", "statements", "lines", "monetary_lines", "error"])
        for row in manifest:
            folder = CORPUS / row["accession"]
            path = instance_path(folder)
            try:
                instance = load_instance(path) if path is not None else Instance()
                statements = load_statements(folder)
                writer.writerow([row["accession"], path.name if path else "", len(instance.facts),
                                 len(instance.concepts_with_money()), "|".join(s.kind for s in statements),
                                 "|".join(str(len(s.lines)) for s in statements),
                                 "|".join(str(len(s.monetary(instance))) for s in statements), ""])
            except (ValueError, ElementTree.ParseError, OSError) as exc:
                writer.writerow([row["accession"], path.name if path else "", 0, 0, "", "", "", str(exc)[:200]])
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
