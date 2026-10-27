"""Read the face statements of an Inline XBRL 10-K or 10-Q, the primary .htm a filer sends EDGAR.

The document is read with the standard library's HTML parser and fixed rules: no network, no
model, no XML parser. Each `ix:nonFraction` fact is read with its context, unit, `scale`,
`sign`, `decimals` and `format`, and stored two ways (PLAN.md, R1): its value as the XBRL
instance holds it (`sign="-"` applied) and its printed value (negated when the cell prints it in
parentheses or after a minus). Statements are rebuilt from the HTML table that prints their facts,
in printed order with printed labels; only dimensionless facts make the statement (R6), and
every subtotal must foot within the facts' own rounding (R5) or the statement is refused.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from .limits import MAX_CELLS, MAX_ROWS
from .numeric import financial_context

# html.parser never reads a DTD, so a plain <!DOCTYPE html> is harmless; an ENTITY declaration or a
# DOCTYPE with an internal subset is what an XML parser would expand, and is refused (constraint 3).
_DECLARATION = re.compile(rb"<!\s*entity|<!\s*doctype[^>\[]*\[", re.IGNORECASE)
_MAX_SECONDS = 20.0
_MAX_TABLES = 20_000
_MAX_CONTEXTS = 200_000
_TITLE_CHARACTERS = 2000  # text before a table searched for its statement title
_STATEMENT_TITLE = re.compile(
    r"\b(?:condensed\s+)?(?:consolidated\s+)?(?:combined\s+)?(?:"
    r"statements?\s+of\s+(?:condensed\s+)?(?:consolidated\s+)?(?:net\s+)?"
    r"(?:operations|income|earnings|loss|comprehensive\s+(?:income|loss)|cash\s+flows|financial\s+(?:position|condition)"
    r"|condition|assets\s+and\s+liabilities)(?:\s+and\s+comprehensive\s+(?:income|loss))?"
    r"|income\s+statements?|balance\s+sheets?)\b",
    re.IGNORECASE,
)
_SMALL_WORDS = {"of", "and", "in", "to"}
# Elements that start a new line of printed text; inline elements (span, font, b) do not.
_BLOCKS = frozenset({"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "table"})
# Subtotal labels filings print that the shared statement shaper does not name (it serves PDFs too).
FILING_SUBTOTALS = re.compile(
    r"^(?:\((?:loss|income|earnings)\)\s+)?(?:net\s+)?(?:income|earnings|loss|profit)"
    r"(?:\s*\((?:loss|income|earnings)\))?\s+(?:from\s+(?:continuing\s+)?operations\s+)?before\b"
    r"|^net\s+\((?:loss|income|earnings)\)\s+(?:income|earnings|loss|profit)\b",
    re.IGNORECASE,
)
# The bottom line: lines after the first of these only attribute net income (to noncontrolling
# interests, preferred holders) or restate it, and are listed rather than analysed.
BOTTOM_LINE = re.compile(r"^us-gaap:(?:NetIncomeLoss|ProfitLoss)$")
BOTTOM_LINE_LABEL = re.compile(
    r"^net\s+(?:\((?:loss|income|earnings)\)\s+)?(?:income|earnings|loss|profit)(?:\s*\((?:loss|income|earnings)\))?$",
    re.IGNORECASE,
)
# us-gaap concepts that are always a statement's own totals (never a detail line), as hints for the
# shaper; noncontrolling-interest and per-share variants are details or not money, and excluded.
_TOTAL_CONCEPT = re.compile(
    r"^us-gaap:(?:GrossProfit|OperatingIncomeLoss|CostsAndExpenses|OperatingExpenses|OperatingCostsAndExpenses"
    r"|NonoperatingIncomeExpense|IncomeLossFromContinuingOperations(?:BeforeIncomeTaxes\w*)?"
    r"|NetIncomeLoss|NetIncomeLossAvailableToCommonStockholders(?:Basic|Diluted)|ProfitLoss"
    r"|NoninterestIncome|NoninterestExpense|InterestIncomeExpenseNet|InterestAndDividendIncomeOperating"
    r"|InterestIncomeExpenseAfterProvisionForLoanLoss|BenefitsLossesAndExpenses"
    r"|ComprehensiveIncomeNetOfTax|OtherComprehensiveIncomeLossNetOfTax|OtherComprehensiveIncomeLossBeforeTax)$"
)
_SECTION_TOTAL = re.compile(
    r"^us-gaap:(?:CostsAndExpenses|OperatingExpenses|OperatingCostsAndExpenses|NonoperatingIncomeExpense"
    r"|NoninterestIncome|NoninterestExpense|InterestAndDividendIncomeOperating|BenefitsLossesAndExpenses"
    r"|OtherComprehensiveIncomeLossNetOfTax|OtherComprehensiveIncomeLossBeforeTax)$"
)
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")
_DASH_CELL = re.compile(r"[\s\u00a0$€£¥()]*[—–\-]+[\s\u00a0$€£¥()]*")
_CURRENCY = re.compile(r"[\s $€£¥]+")
_NUMBER_WORDS = {"no": 0, "none": 0, "nil": 0, "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class IxbrlError(ValueError):
    """A filing that cannot be read, described in plain language."""


@dataclass(frozen=True)
class Context:
    period: tuple[str, ...]  # ("instant", "2025-09-27") or ("duration", start, end)
    dims: tuple[tuple[str, str], ...]  # sorted (axis, member)


@dataclass
class Fact:
    name: str
    context: str
    unit: str
    decimals: str
    fact_id: str
    text: str = ""
    hidden: bool = False
    nil: bool = False
    magnitude: Decimal | None = None  # the printed figure at full scale, sign-free
    stored: Decimal | None = None  # v: what the XBRL instance holds
    problem: str = ""  # why the figure cannot be read, if it cannot
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class _Cell:
    tokens: list[tuple[str, str | int]] = field(default_factory=list)  # ("text", s) | ("fact", i) | ("ref", id)


@dataclass
class _Table:
    title: str
    rows: list[list[_Cell]] = field(default_factory=list)


@dataclass(frozen=True)
class LineKey:
    """What one printed amount is in the filing, for the audit and the sweep."""

    concept: str
    context: str
    period: tuple[str, ...]
    dims: tuple[tuple[str, str], ...]
    stored: Decimal  # v
    displayed: Decimal  # d
    decimals: str


@dataclass
class Line:
    label: str
    section: str
    concept: str
    measure: str  # "Currency", "Per Share", "Count"
    keys: list[LineKey | None]  # by column
    dash: bool = False  # prints an untagged dash: a column without a fact reads as 0

    @property
    def total(self) -> bool:
        """Whether the line's concept is always a total of the lines above it."""
        return bool(_TOTAL_CONCEPT.match(self.concept))

    @property
    def section_total(self) -> bool:
        """Whether that total may sum just the lines of its own section (as a "Total" row does)."""
        return bool(_SECTION_TOTAL.match(self.concept))


@dataclass
class Statement:
    """One face statement as printed, before intake labels and compares it."""

    kind: str  # "income", "comprehensive_income", "balance_sheet", "cash_flow"
    name: str
    periods: list[tuple[str, ...]]
    labels: list[str]
    lines: list[Line]
    notes: list[str] = field(default_factory=list)
    left_out: list[str] = field(default_factory=list)
    problem: str = ""  # why this statement cannot be read; other statements of the filing still can


def _transform(fmt: str, text: str) -> Decimal:
    """The figure an ixt transform reads from printed text; ValueError for anything else."""
    local = fmt.rpartition(":")[2].lower()
    raw = " ".join(text.split())
    if local in {"fixed-zero", "zerodash", "numdash", "fixedzero"}:
        return Decimal(0)
    if local in {"numwordsen", "num-words-en"}:
        words = raw.lower().strip(" .")
        if words in _NUMBER_WORDS:
            return Decimal(_NUMBER_WORDS[words])
        raise ValueError(f"number words '{raw}'")
    if not local:
        # No format: the content must already be a plain decimal (Inline XBRL 1.1, 4.5.1).
        if not re.fullmatch(r"\d+(?:\.\d+)?|\.\d+", raw):
            raise ValueError(f"'{raw}' is not a plain decimal")
        return Decimal(raw)
    if local in {"num-dot-decimal", "numdotdecimal", "numcommadot", "num-dot-decimal-apos"}:
        if not re.fullmatch(r"\d{1,3}(?:[,  ']?\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+", raw):
            raise ValueError(f"'{raw}' is not a figure in the {fmt or 'plain'} format")
        return Decimal(re.sub(r"[,  ']", "", raw))
    if local in {"num-comma-decimal", "numcommadecimal", "numdotcomma", "numspacecomma"}:
        if not re.fullmatch(r"\d{1,3}(?:[.  ]?\d{3})*(?:,\d+)?|\d+(?:,\d+)?", raw):
            raise ValueError(f"'{raw}' is not a figure in the {fmt} format")
        return Decimal(re.sub(r"[.  ]", "", raw).replace(",", "."))
    raise ValueError(f"the {fmt} format")


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.contexts: dict[str, Context] = {}
        self.units: dict[str, str] = {}
        self.facts: list[Fact] = []
        self.tables: list[_Table] = []
        self.started = time.monotonic()
        self._skip = 0
        self._hidden = 0
        self._context: tuple[str, list[str], list[tuple[str, str]], str | None] | None = None
        self._capture: list[str] | None = None
        self._unit: tuple[str, list[str], bool] | None = None
        self._facts_open: list[Fact] = []
        self._table_stack: list[_Table] = []
        self._cell: _Cell | None = None
        self._outside = ""  # the text since the last table, as printed (spans join without spaces)
        self._ref_depth: list[tuple[str, int]] = []
        self._tags = 0

    def _check(self) -> None:
        self._tags += 1
        if self._tags % 5000 == 0 and time.monotonic() - self.started > _MAX_SECONDS:
            raise IxbrlError("reading the filing took longer than 20 seconds")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check()
        if tag in _BLOCKS and self._cell is None:
            self._outside += " "
        values = {name: value or "" for name, value in attrs}
        if tag in {"script", "style"}:
            self._skip += 1
            return
        hidden_ref = re.search(r"-sec-ix-hidden\s*:\s*([^;\s]+)", values.get("style", ""))
        if self._ref_depth and self._ref_depth[-1][0] == tag and not hidden_ref:
            self._ref_depth[-1] = (tag, self._ref_depth[-1][1] + 1)
        if tag == "ix:hidden":
            self._hidden += 1
        elif tag == "xbrli:context":
            if len(self.contexts) >= _MAX_CONTEXTS:
                raise IxbrlError("the filing has more contexts than can be read")
            self._context = (values.get("id", ""), [], [], None)
        elif tag in {"xbrli:instant", "xbrli:startdate", "xbrli:enddate", "xbrli:measure"}:
            self._capture = []
        elif tag in {"xbrldi:explicitmember", "xbrldi:typedmember"} and self._context is not None:
            self._capture = []
            self._context = (*self._context[:3], values.get("dimension", ""))
        elif tag == "xbrli:unit":
            self._unit = (values.get("id", ""), [], False)
        elif tag == "xbrli:divide" and self._unit is not None:
            self._unit = (self._unit[0], self._unit[1], True)
        elif tag == "ix:nonfraction":
            if len(self.facts) >= MAX_CELLS:
                raise IxbrlError("the filing has more figures than can be read")
            fact = Fact(values.get("name", ""), values.get("contextref", ""), values.get("unitref", ""),
                        values.get("decimals", ""), values.get("id", ""), hidden=self._hidden > 0,
                        # The XMLSchema-instance prefix is the filer's choice (xsi:nil, xs:nil, ...).
                        nil=any(name.rpartition(":")[2] == "nil" and value.strip().lower() in {"true", "1"}
                                for name, value in values.items()), attributes=values)
            self.facts.append(fact)
            if self._cell is not None and not fact.hidden and not self._facts_open:
                self._cell.tokens.append(("fact", len(self.facts) - 1))
            self._facts_open.append(fact)
        elif tag == "table":
            if len(self.tables) >= _MAX_TABLES:
                raise IxbrlError("the filing has more tables than can be read")
            table = _Table(title=" ".join(self._outside.split()))
            self.tables.append(table)
            self._table_stack.append(table)
            self._outside = ""
        elif tag == "tr" and self._table_stack:
            if len(self._table_stack[-1].rows) >= MAX_ROWS:
                raise IxbrlError("a table in the filing has more rows than can be read")
            self._table_stack[-1].rows.append([])
            self._cell = None
        elif tag in {"td", "th"} and self._table_stack:
            if not self._table_stack[-1].rows:
                self._table_stack[-1].rows.append([])
            self._cell = _Cell()
            self._table_stack[-1].rows[-1].append(self._cell)
        if hidden_ref and self._cell is not None:
            # The cell prints a fact kept in ix:hidden; that fact is the cell's figure.
            self._cell.tokens.append(("ref", hidden_ref.group(1)))
            self._ref_depth.append((tag, 1))

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCKS and self._cell is None:
            self._outside += " "
        if tag in {"script", "style"}:
            self._skip = max(0, self._skip - 1)
            return
        if self._ref_depth and self._ref_depth[-1][0] == tag:
            depth = self._ref_depth[-1][1] - 1
            self._ref_depth[-1] = (tag, depth)
            if depth == 0:
                self._ref_depth.pop()
        if tag == "ix:hidden":
            self._hidden = max(0, self._hidden - 1)
        elif tag in {"xbrli:instant", "xbrli:startdate", "xbrli:enddate"} and self._context and self._capture is not None:
            self._context[1].append("".join(self._capture).strip())
            self._capture = None
        elif tag in {"xbrldi:explicitmember", "xbrldi:typedmember"} and self._context and self._capture is not None:
            prefix = "" if tag == "xbrldi:explicitmember" else "typed:"
            self._context[2].append((self._context[3] or "", prefix + " ".join("".join(self._capture).split())))
            self._capture = None
        elif tag == "xbrli:context" and self._context is not None:
            context_id, dates, dims, _ = self._context
            period = ("instant", dates[0]) if len(dates) == 1 else ("duration", *dates[:2])
            self.contexts[context_id] = Context(period, tuple(sorted(dims)))
            self._context = None
        elif tag == "xbrli:measure" and self._unit is not None and self._capture is not None:
            self._unit[1].append("".join(self._capture).strip())
            self._capture = None
        elif tag == "xbrli:unit" and self._unit is not None:
            unit_id, measures, divide = self._unit
            self.units[unit_id] = ("/" if divide else "*").join(measures)
            self._unit = None
        elif tag == "ix:nonfraction" and self._facts_open:
            self._facts_open.pop()
        elif tag in {"td", "th"}:
            self._cell = None
            self._ref_depth = []  # a hidden fact's printed text never runs past its cell
        elif tag == "table" and self._table_stack:
            table = self._table_stack.pop()
            self._cell = None
            if not any(kind in {"fact", "ref"} for row in table.rows for cell in row for kind, _ in cell.tokens):
                # A table without figures (a page or title header) is printed text before the next table.
                text = " ".join("".join(str(t) for kind, t in cell.tokens if kind == "text") for row in table.rows for cell in row)
                self._outside = f"{table.title} {text} "[-_TITLE_CHARACTERS:]

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._capture is not None:
            self._capture.append(data)
            return
        if self._facts_open:
            for fact in self._facts_open:
                fact.text += data
            return
        if self._ref_depth:
            return  # the printed text of a hidden fact; the fact itself stands for it
        if self._hidden:
            return
        if self._cell is not None:
            self._cell.tokens.append(("text", data))
        else:
            self._outside = (self._outside + data)[-_TITLE_CHARACTERS:]


def _read_facts(reader: _Reader) -> None:
    for fact in reader.facts:
        if fact.nil:
            continue
        fmt = fact.attributes.get("format", "")
        text = fact.text.strip()
        if "-" in text and fmt.rpartition(":")[2].lower() not in {"fixed-zero", "zerodash", "numdash", "fixedzero"}:
            fact.problem = "a minus sign inside the tagged figure"
            continue
        try:
            scale = int(fact.attributes.get("scale", "0") or "0")
            with financial_context():
                magnitude = _transform(fmt, text).scaleb(scale)
                fact.magnitude = magnitude
                fact.stored = -magnitude if fact.attributes.get("sign") == "-" else magnitude
        except (ValueError, InvalidOperation) as exc:
            fact.problem = f"cannot read {exc}"


def _pretty(title: str) -> str:
    words = title.split()
    return " ".join(w.lower() if i and w.lower() in _SMALL_WORDS else w.capitalize() for i, w in enumerate(words))


def _kind(title: str) -> str:
    lowered = title.lower()
    if "cash flow" in lowered:
        return "cash_flow"
    if re.search(r"balance sheet|financial (?:position|condition)|statements? of condition|assets and liabilities", lowered):
        return "balance_sheet"
    if "comprehensive" in lowered and not re.search(r"operations|earnings|income and", lowered):
        return "comprehensive_income"
    return "income"


def _period_label(period: tuple[str, ...]) -> str:
    end = date.fromisoformat(period[-1])
    if period[0] == "duration":
        days = (end - date.fromisoformat(period[1])).days
        if 340 <= days <= 380:
            return f"FY{end.year}"
    return f"{_MONTHS[end.month - 1]} {end.year}"


def _months(period: tuple[str, ...]) -> int:
    if period[0] != "duration":
        return 0
    days = (date.fromisoformat(period[2]) - date.fromisoformat(period[1])).days
    return max(1, round(days / 30.44))


def _negation(before: str, after: str) -> bool | None:
    """Printed negation from the text around a figure (R1): True, False, or None when unbalanced."""
    before, after = _CURRENCY.sub("", before), _CURRENCY.sub("", after)
    opened, closed = before.endswith("("), after.startswith(")")
    if opened != closed:
        return None
    return opened or before.endswith(("-", "−"))


def _monetary(unit: str) -> bool:
    return unit.lower().startswith("iso4217:") and "/" not in unit and "*" not in unit


def _measure(unit: str) -> str:
    lowered = unit.lower()
    if lowered.startswith("iso4217:") and lowered.endswith("/xbrli:shares"):
        return "Per Share"
    if lowered == "xbrli:shares":
        return "Count"
    return "Currency" if _monetary(unit) else ""


def read_statements(data: bytes, filename: str, *, per_share_lines: bool = False) -> list[Statement]:
    """Every face statement the filing prints, first copy of each kind, in document order."""
    if _DECLARATION.search(data):
        raise IxbrlError(f"'{filename}' declares an XML entity or document type subset, which this reader refuses. "
                         "Upload the filing's PDF, or a CSV or Excel copy of the statement.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    reader = _Reader()
    reader.feed(text)
    reader.close()
    if not reader.facts:
        raise IxbrlError(f"'{filename}' is a web page without Inline XBRL figures, so it has no statements I can find. "
                         "Upload the filing's 10-K or 10-Q document from its EDGAR folder, its PDF, or a CSV or Excel table.")
    _read_facts(reader)
    by_id = {fact.fact_id: index for index, fact in enumerate(reader.facts) if fact.fact_id}
    statements: list[Statement] = []
    seen: set[str] = set()
    pending: tuple[str, str, list[_Table]] | None = None
    for table in reader.tables:
        # A title may also be printed in the table's own leading rows, before any figure.
        lead: list[str] = []
        for cells in table.rows:
            if any(kind in {"fact", "ref"} for cell in cells for kind, _ in cell.tokens):
                break
            lead.append(" ".join("".join(str(t) for kind, t in cell.tokens if kind == "text") for cell in cells))
        if lead:
            table.title = " ".join(f"{table.title} {' '.join(lead)}".split())
        titles = list(_STATEMENT_TITLE.finditer(table.title))
        match = titles[-1] if titles else None  # the title nearest the table
        facts = [reader.facts[i] for row in table.rows for cell in row for kind, i in cell.tokens
                 if kind == "fact" and isinstance(i, int)]
        money = [f for f in facts if _monetary(reader.units.get(f.unit, "")) and f.context in reader.contexts
                 and not reader.contexts[f.context].dims]
        titled = match is not None and "parenthetical" not in table.title[match.start():].lower()
        if titled and len(money) >= 3 and match is not None:
            kind = _kind(match.group(0))
            if pending is not None and pending[0] == kind and "continued" in table.title.lower():
                pending[2].append(table)
                continue
            if pending is not None:
                statements.extend(_build(pending, reader, by_id, per_share_lines))
                pending = None
            if kind not in seen:
                seen.add(kind)
                pending = (kind, _pretty(match.group(0)), [table])
        elif pending is not None and money and not table.title.strip() and _same_periods(pending[2][0], table, reader):
            pending[2].append(table)  # the statement runs on in the next table, untitled, over the same periods
        elif pending is not None and money:
            statements.extend(_build(pending, reader, by_id, per_share_lines))
            pending = None
    if pending is not None:
        statements.extend(_build(pending, reader, by_id, per_share_lines))
    if not statements:
        raise IxbrlError(f"I could not find the financial statements in '{filename}': no table there is titled as an "
                         "income statement, balance sheet or cash flow statement and holds their tagged figures.")
    return statements


def _money_periods(table: _Table, reader: _Reader) -> set[tuple[str, ...]]:
    periods = set()
    for cells in table.rows:
        for cell in cells:
            for kind, index in cell.tokens:
                if kind == "fact" and isinstance(index, int):
                    fact = reader.facts[index]
                    context = reader.contexts.get(fact.context)
                    if context is not None and not context.dims and _monetary(reader.units.get(fact.unit, "")):
                        periods.add(context.period)
    return periods


def _same_periods(first: _Table, table: _Table, reader: _Reader) -> bool:
    """Whether a following untitled table prints figures for the statement's own periods."""
    return bool(_money_periods(table, reader)) and _money_periods(table, reader) <= _money_periods(first, reader)


def _build(found: tuple[str, str, list[_Table]], reader: _Reader, by_id: dict[str, int],
           per_share_lines: bool) -> list[Statement]:
    kind, title, tables = found
    rows: list[tuple[str, str, list[tuple[Fact, bool | None]], bool]] = []  # label, section, figures, prints a dash
    section = ""
    wrapped = ""  # a label row with no figures, which may be the start of the next row's label
    for table in tables:
        for cells in table.rows:
            flat: list[tuple[str, str | int]] = []
            label_parts: list[str] = []
            first_figure = next((n for n, cell in enumerate(cells) if any(k in {"fact", "ref"} for k, _ in cell.tokens)), None)
            # A "$" or "(" printed in its own cell before the first figure belongs to the figure, not the label.
            while first_figure is not None and first_figure > 1 and re.fullmatch(
                    r"[\s\u00a0$€£¥(\-\u2212]*", "".join(str(t) for k, t in cells[first_figure - 1].tokens if k == "text")) \
                    and any(str(t).strip() for k, t in cells[first_figure - 1].tokens if k == "text"):
                first_figure -= 1
            dash = False
            for n, cell in enumerate(cells):
                cell_text = "".join(str(t) for k, t in cell.tokens if k == "text")
                if (first_figure is None or n < first_figure) and not (n and _DASH_CELL.fullmatch(cell_text)):
                    label_parts.append(cell_text)
                else:
                    dash = dash or bool(_DASH_CELL.fullmatch(cell_text))
                    flat.extend(cell.tokens)
            label = " ".join(_INVISIBLE.sub("", " ".join(label_parts)).split())
            if first_figure is None:
                if label and not re.fullmatch(r"[\d\s,.$()%\-—–]*", label):
                    section = label.rstrip(":")
                    wrapped = label
                continue
            if not label and wrapped:
                label = wrapped  # the label ran onto the row above
            elif not label and section and rows and rows[-1][1] == section:
                label = f"Total {section}"  # an unlabeled figures row closing its section is the section's total
            wrapped = ""
            figures: list[tuple[Fact, bool | None]] = []
            for position, (token_kind, value) in enumerate(flat):
                if token_kind not in {"fact", "ref"}:
                    continue
                index = value if token_kind == "fact" else by_id.get(str(value))
                if not isinstance(index, int):
                    continue
                before = _text_since(flat, position, -1)
                after = _text_since(flat, position, 1)
                figures.append((reader.facts[index], _negation(before, after)))
            rows.append((label, section, figures, dash))
    # Columns: the periods of the dimensionless money facts, newest first, split by duration.
    periods: dict[tuple[str, ...], None] = {}
    for _, _, figures, _ in rows:
        for fact, _ in figures:
            context = reader.contexts.get(fact.context)
            if context is not None and not context.dims and _monetary(reader.units.get(fact.unit, "")):
                periods.setdefault(context.period)
    groups: dict[int, list[tuple[str, ...]]] = {}
    for period in periods:
        groups.setdefault(_months(period), []).append(period)
    statements = []
    for months, group in sorted(groups.items(), key=lambda item: -len(item[1])):
        if len(group) < 2:
            continue
        group.sort(key=lambda p: p[-1], reverse=True)
        name = title if len(groups) == 1 or months == 0 else f"{title}, {months} Months Ended"
        statements.append(_statement(kind, name, group, rows, reader, per_share_lines))
    return statements


def _text_since(tokens: list[tuple[str, str | int]], position: int, step: int) -> str:
    """Text between the figure at `position` and the next figure in direction `step` (or the row's end)."""
    parts: list[str] = []
    index = position + step
    while 0 <= index < len(tokens) and tokens[index][0] == "text":
        parts.append(str(tokens[index][1]))
        index += step
    return "".join(reversed(parts) if step < 0 else parts)


def _statement(kind: str, name: str, periods: list[tuple[str, ...]],
               rows: list[tuple[str, str, list[tuple[Fact, bool | None]], bool]], reader: _Reader,
               per_share_lines: bool) -> Statement:
    labels = [_period_label(p) for p in periods]
    statement = Statement(kind, name, periods, labels, [])
    if len(set(labels)) != len(labels):
        statement.notes.append("Two columns share a period label")
    statement.notes.extend(f"Read the column for {p[-1]} as {label}" for p, label in zip(periods, labels, strict=True))
    breakdowns: list[str] = []
    for label, section, figures, dash in rows:
        keys: list[LineKey | None] = [None] * len(periods)
        concept, measure, dims_seen, problem = "", "", set(), ""
        plain = any(not reader.contexts[f.context].dims for f, _ in figures if f.context in reader.contexts)
        for fact, negated in figures:
            context = reader.contexts.get(fact.context)
            unit = reader.units.get(fact.unit, "")
            if context is None:
                continue
            if context.dims:
                dims_seen.add(len(context.dims))
                # A line printing a one-axis breakdown (revenue by product) is a printed line: its total
                # must foot over it (R5, R6). Facts on two or more axes are left out.
                if plain or len(context.dims) > 1:
                    continue
            if context.period not in periods:
                continue
            fact_measure = _measure(unit)
            if not fact_measure:
                continue
            if fact.nil:
                continue  # xsi:nil: the filing states there is no value, so the cell is blank
            if fact.problem or fact.stored is None or fact.magnitude is None:
                problem = problem or (fact.problem or "no value")
                continue
            if negated is None:
                problem = problem or "a parenthesis that opens or closes on one side only"
                continue
            displayed = -fact.magnitude if negated else fact.magnitude
            keys[periods.index(context.period)] = LineKey(fact.name, fact.context, context.period, context.dims,
                                                          fact.stored, displayed, fact.decimals)
            concept, measure = concept or fact.name, measure or fact_measure
        if not any(keys):
            if dims_seen:
                statement.left_out.append(f"'{label}' (a breakdown by several axes)")
            continue
        if not plain:
            breakdowns.append(label)
        if problem and not statement.problem:
            statement.problem = (f"I could not read every figure of '{label or 'an unlabeled line'}' in the {name}: "
                                 f"{problem}. Upload the filing's PDF, or a CSV or Excel copy of the statement.")
        if measure != "Currency" and not per_share_lines:
            statement.left_out.append(f"'{label}' (per-share and share counts are not money totals)")
            continue
        statement.lines.append(Line(label, section, concept, measure, keys, dash))
    if breakdowns:
        statement.notes.append(f"Read {len(breakdowns)} line{'s' if len(breakdowns) != 1 else ''} that break a total down "
                               f"by one axis (such as '{breakdowns[0]}') as printed lines; the audit names each axis and member")
    return statement
