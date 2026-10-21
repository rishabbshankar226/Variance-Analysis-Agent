"""Read financial-statement tables out of 10-K / 10-Q style PDFs.

The optional ``[pdf]`` extra (pdfplumber) supplies each word and its position on
the page. Everything else is plain rules: statement titles, column alignment and
period headers. Amounts stay as the text printed in the filing, so intake parses
them into Decimal exactly as it does for CSV cells.
"""

from __future__ import annotations

import copy
import hashlib
import io
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import BinaryIO, Protocol, cast

from .limits import MAX_PDF_PAGES, MAX_PDF_SECONDS


class PdfReadError(ValueError):
    """A PDF that cannot be read, described in plain language."""


@dataclass
class StatementTable:
    """One statement read from a PDF, shaped like worksheet rows for intake."""

    name: str
    page_numbers: tuple[int, ...]
    raw_rows: list[list[object]]
    notes: list[str] = field(default_factory=list)


class _Page(Protocol):
    page_number: int

    def extract_words(self) -> list[dict[str, object]]: ...

    def close(self) -> None: ...


class _Pdf(Protocol):
    @property
    def pages(self) -> Sequence[_Page]: ...

    def close(self) -> None: ...


class _Opener(Protocol):
    def __call__(self, stream: BinaryIO, *, pages: list[int]) -> _Pdf: ...


class _TextPage(Protocol):
    def get_text_range(self) -> str: ...

    def close(self) -> None: ...


class _ScanPage(Protocol):
    def get_textpage(self) -> _TextPage: ...

    def close(self) -> None: ...


class _ScanDocument(Protocol):
    def __len__(self) -> int: ...

    def __getitem__(self, index: int) -> _ScanPage: ...

    def close(self) -> None: ...


_ScanOpener = Callable[[bytes], _ScanDocument]

_TITLE_RE = re.compile(
    r"\b(?:condensed\s+)?(?:consolidated\s+)?(?:"
    r"statements?\s+of\s+(?:operations|income|earnings|comprehensive\s+(?:income|loss)"
    r"|cash\s+flows|financial\s+position)"
    r"|balance\s+sheets?)\b",
    re.IGNORECASE,
)
_TITLE_SLACK = 25  # a title line may carry "(Continued)" or "(Unaudited)", not a sentence
_TITLE_SEARCH_LINES = 10
_SMALL_WORDS = {"of", "and", "in", "to"}

_NUMBER_RE = re.compile(r"^\(?-?\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?%?$")
_DASHES = {"-", "–", "—"}
_YEAR_ONLY_RE = re.compile(r"^(?:19|20)\d{2}$")
_PARENTHETICAL_RE = re.compile(r"^\(.*\)$")

_DURATION_RE = re.compile(
    r"\b(?P<count>three|six|nine|twelve|3|6|9|12)\s+months?\s+ended\b"
    r"|\b(?P<year>(?:fiscal\s+)?years?)\s+ended\b"
    r"|\bquarters?\s+ended\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2},?\s+)?"
    r"((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_PER_SHARE_RE = re.compile(
    r"per\s+(?:common\s+|basic\s+|diluted\s+)?share|shares\s+outstanding|shares\s+used"
    r"|weighted[-\s]average\s+(?:number\s+of\s+)?(?:common\s+)?shares|number\s+of\s+shares",
    re.IGNORECASE,
)
_SHARE_SUBROW_RE = re.compile(r"^(?:basic|diluted)\b", re.IGNORECASE)
_PER_SHARE_NOTE = "(per-share and share counts are not money totals)"

_LINE_TOLERANCE = 3.0  # points between word tops on one printed line
_PHRASE_GAP = 8.0  # wider gaps than this split header text into separate phrases
_COLUMN_TOLERANCE = 8.0  # right edges within this distance share a column

_CACHE: dict[tuple[str, int, float], list[StatementTable]] = {}


@dataclass(frozen=True)
class _Word:
    text: str
    x0: float
    x1: float
    top: float


@dataclass
class _Line:
    words: list[_Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class _Column:
    center: float
    x0: float
    x1: float
    header: str = ""


@dataclass
class _PageTable:
    title: str
    page_number: int
    caption: str
    columns: list[_Column]
    body: list[tuple[str, dict[int, str]]]  # label, values by column index


def extract_statement_tables(
    data: bytes,
    filename: str,
    *,
    max_pages: int = MAX_PDF_PAGES,
    max_seconds: float = MAX_PDF_SECONDS,
) -> list[StatementTable]:
    """Return every income statement, balance sheet and cash flow statement in the PDF."""
    key = (hashlib.sha256(data).hexdigest(), max_pages, max_seconds)
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = _extract(data, filename, max_pages, max_seconds)
    return copy.deepcopy(_CACHE[key])


def _pdf_tools() -> tuple[_ScanOpener, _Opener]:
    """pypdfium2 quickly finds statement pages; pdfplumber reads their word positions."""
    try:
        plumber: object = __import__("pdfplumber")
        pdfium: object = __import__("pypdfium2")
    except ImportError as exc:
        raise PdfReadError(
            "PDF files require the optional PDF tools. "
            "Please install with: pip install 'variance-analysis-agent[pdf]'"
        ) from exc
    return (cast(_ScanOpener, getattr(pdfium, "PdfDocument")),
            cast(_Opener, getattr(plumber, "open")))


def _cannot_open(filename: str) -> PdfReadError:
    return PdfReadError(
        f"We couldn't open '{filename}' as a PDF. It may be damaged or password-protected. "
        "Try saving it again without a password, or export the statement to Excel or CSV."
    )


def _check_time(deadline: float, filename: str) -> None:
    if time.monotonic() >= deadline:
        raise PdfReadError(
            f"Reading '{filename}' took too long. Save just the financial statement "
            "pages as a new PDF and upload that."
        )


def _statement_pages(
    scan: _ScanOpener, data: bytes, filename: str, max_pages: int, deadline: float
) -> list[int]:
    """Return the 1-based numbers of pages whose top lines carry a statement title."""
    try:
        document = scan(data)
        page_count = len(document)
    except Exception as exc:
        raise _cannot_open(filename) from exc
    candidates: list[int] = []
    saw_text = False
    try:
        if page_count > max_pages:
            raise PdfReadError(
                f"'{filename}' has {page_count} pages, more than the {max_pages} we can read at "
                "once. Save just the financial statement pages as a new PDF and upload that."
            )
        for index in range(page_count):
            _check_time(deadline, filename)
            page = document[index]
            text_page = page.get_textpage()
            try:
                text = text_page.get_text_range()
            finally:
                text_page.close()
                page.close()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            saw_text = saw_text or bool(lines)
            if _title(lines) is not None:
                candidates.append(index + 1)
    finally:
        document.close()
    if not saw_text:
        raise PdfReadError(
            f"'{filename}' looks like a scanned image, so there is no text to read. Export the "
            "statement to Excel or CSV, or use a PDF saved from the filing itself, not a scan."
        )
    return candidates


def _extract(data: bytes, filename: str, max_pages: int, max_seconds: float) -> list[StatementTable]:
    scan, opener = _pdf_tools()
    deadline = time.monotonic() + max_seconds
    candidates = _statement_pages(scan, data, filename, max_pages, deadline)
    found: list[_PageTable] = []
    if candidates:
        try:
            pdf = opener(io.BytesIO(data), pages=candidates)
            pages = pdf.pages
        except Exception as exc:
            raise _cannot_open(filename) from exc
        try:
            for page in pages:
                _check_time(deadline, filename)
                try:
                    words = [_word(w) for w in page.extract_words()]
                    page_number = page.page_number
                except PdfReadError:
                    raise
                except Exception as exc:
                    raise _cannot_open(filename) from exc
                finally:
                    page.close()
                table = _page_table(_lines(words), page_number)
                if table is not None:
                    found.append(table)
        finally:
            pdf.close()

    tables = [t for group in _merge_continued(found) for t in _statement_tables(group)]
    if not tables:
        raise PdfReadError(
            f"We couldn't find an income statement, balance sheet or cash flow statement in "
            f"'{filename}'. Export the statement to Excel or CSV and upload that instead."
        )
    return tables


def _coord(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raise PdfReadError("The PDF reader returned a word without a position.")


def _word(raw: dict[str, object]) -> _Word:
    return _Word(str(raw["text"]), _coord(raw["x0"]), _coord(raw["x1"]), _coord(raw["top"]))


def _lines(words: list[_Word]) -> list[_Line]:
    lines: list[_Line] = []
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and abs(word.top - lines[-1].words[0].top) <= _LINE_TOLERANCE:
            lines[-1].words.append(word)
        else:
            lines.append(_Line([word]))
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
        line.words = _join_split_parentheses(line.words)
    return lines


def _join_split_parentheses(words: list[_Word]) -> list[_Word]:
    """Rejoin "(18.7" and ")" when a filing spaces the closing parenthesis apart."""
    joined: list[_Word] = []
    for word in words:
        prev = joined[-1] if joined else None
        if word.text == ")" and prev is not None and prev.text.startswith("(") \
                and prev.text[-1:].isdigit():
            joined[-1] = _Word(prev.text + ")", prev.x0, word.x1, prev.top)
        else:
            joined.append(word)
    return joined


def _is_amount(text: str) -> bool:
    return text in _DASHES or bool(_NUMBER_RE.match(text))


def _title(lines: list[str]) -> tuple[int, str] | None:
    for index, line in enumerate(lines[:_TITLE_SEARCH_LINES]):
        match = _TITLE_RE.search(line)
        if match and len(line) <= len(match.group(0)) + _TITLE_SLACK:
            return index, _pretty_title(match.group(0))
    return None


def _pretty_title(text: str) -> str:
    words = text.split()
    return " ".join(
        w.lower() if i and w.lower() in _SMALL_WORDS else w.capitalize() for i, w in enumerate(words)
    )


def _find_columns(lines: list[_Line]) -> list[_Column]:
    edges: list[float] = []
    for line in lines:
        amounts = [w for w in line.words if _is_amount(w.text)]
        if len(amounts) >= 2:
            edges.extend(w.x1 for w in amounts)
    clusters: list[list[float]] = []
    for edge in sorted(edges):
        if clusters and edge - clusters[-1][-1] <= _COLUMN_TOLERANCE:
            clusters[-1].append(edge)
        else:
            clusters.append([edge])
    columns = []
    for cluster in clusters:
        if len(cluster) >= 2:
            center = sorted(cluster)[len(cluster) // 2]
            columns.append(_Column(center=center, x0=center, x1=center))
    return columns


def _assign(line: _Line, columns: list[_Column]) -> tuple[str, dict[int, str]]:
    """Split a line into its label and its amounts by column index."""
    label: list[str] = []
    values: dict[int, str] = {}
    for word in line.words:
        if word.text == "$":
            continue
        col = None
        if _is_amount(word.text):
            nearest = min(range(len(columns)), key=lambda i: abs(columns[i].center - word.x1))
            if abs(columns[nearest].center - word.x1) <= _COLUMN_TOLERANCE and nearest not in values:
                col = nearest
        if col is None:
            label.append(word.text)
        else:
            values[col] = word.text.replace("$", "")
            columns[col].x0 = min(columns[col].x0, word.x0)
    return " ".join(label), values


def _page_table(lines: list[_Line], page_number: int) -> _PageTable | None:
    found = _title([line.text for line in lines])
    if found is None:
        return None
    title_index, title = found
    body_lines = lines[title_index + 1:]
    columns = _find_columns(body_lines)
    if len(columns) < 2:
        return None

    assigned = [_assign(line, columns) for line in body_lines]
    data_start = next(
        (i for i, (label, values) in enumerate(assigned) if label and values), None)
    if data_start is None:
        return None

    caption_parts: list[str] = []
    header_lines: list[_Line] = []
    for line in body_lines[:data_start]:
        if _PARENTHETICAL_RE.match(line.text):
            caption_parts.append(line.text)
        else:
            header_lines.append(line)
    for line in header_lines:
        _attach_header(line, columns)

    return _PageTable(title, page_number, " ".join(caption_parts), columns, assigned[data_start:])


def _phrases(line: _Line) -> list[_Word]:
    phrases: list[_Word] = []
    for word in line.words:
        if phrases and word.x0 - phrases[-1].x1 <= _PHRASE_GAP:
            last = phrases[-1]
            phrases[-1] = _Word(f"{last.text} {word.text}", last.x0, word.x1, last.top)
        else:
            phrases.append(word)
    return phrases


def _attach_header(line: _Line, columns: list[_Column]) -> None:
    """Add one printed header line to the columns it sits over."""
    left_edge = min(c.x0 for c in columns) - 30
    phrases = [p for p in _phrases(line) if p.x1 >= left_edge]
    if not phrases:
        return

    def distance(phrase: _Word, column: _Column) -> float:
        middle = (column.x0 + column.x1) / 2
        return max(phrase.x0 - middle, middle - phrase.x1, 0.0)

    parts: dict[int, list[str]] = {}
    if len(phrases) == len(columns):
        for i, phrase in enumerate(phrases):
            parts[i] = [phrase.text]
    elif len(phrases) < len(columns):  # spanning text such as "Year Ended December 31,"
        for i, column in enumerate(columns):
            nearest = min(phrases, key=lambda p: distance(p, column))
            parts[i] = [nearest.text]
    else:
        for phrase in phrases:
            i = min(range(len(columns)), key=lambda c: distance(phrase, columns[c]))
            parts.setdefault(i, []).append(phrase.text)
    for i, texts in parts.items():
        columns[i].header = " ".join([columns[i].header, *texts]).strip()


def _merge_continued(found: list[_PageTable]) -> list[list[_PageTable]]:
    """Group a statement with the next page when that page continues it."""
    groups: list[list[_PageTable]] = []
    for table in found:
        prev = groups[-1][-1] if groups else None
        if prev is not None and prev.title == table.title \
                and prev.page_number + 1 == table.page_number \
                and [c.header for c in prev.columns] == [c.header for c in table.columns]:
            groups[-1].append(table)
        else:
            groups.append([table])
    return groups


def _period(header: str) -> tuple[str | None, str]:
    """Return a period label intake can order (FY2025, Sep 2026) and the duration group."""
    duration = _DURATION_RE.search(header)
    group = ""
    if duration:
        group = "Year Ended" if duration.group("year") else _pretty_title(duration.group(0))
    dates = _DATE_RE.findall(header)
    years = _YEAR_RE.findall(header)
    if duration and duration.group("year") and years:
        return f"FY{years[-1]}", group
    if dates:
        month, year = dates[-1]
        return f"{month.capitalize()} {year}", group
    if years:
        return f"FY{years[-1]}", group
    return None, group


def _statement_tables(group: list[_PageTable]) -> list[StatementTable]:
    first = group[0]
    periods = [_period(c.header) for c in first.columns]

    durations = [d for _, d in periods]
    named = sorted({d for d in durations if d}, key=durations.index)
    if len(named) > 1:
        current = named[0]
        for i, duration in enumerate(durations):
            current = duration or current
            durations[i] = current
        splits = [(d, [i for i, x in enumerate(durations) if x == d]) for d in named]
    else:
        splits = [("", list(range(len(first.columns))))]

    pages = tuple(t.page_number for t in group)
    where = f"(p. {pages[0]})" if len(pages) == 1 else f"(pp. {pages[0]}-{pages[-1]})"
    tables = []
    for duration, indexes in splits:
        if len(indexes) < 2:
            continue
        name = f"{first.title}, {duration} {where}" if duration else f"{first.title} {where}"
        tables.append(_statement_table(group, name, pages, indexes, periods))
    return tables


def _statement_table(
    group: list[_PageTable],
    name: str,
    pages: tuple[int, ...],
    indexes: list[int],
    periods: list[tuple[str | None, str]],
) -> StatementTable:
    first = group[0]
    notes: list[str] = []
    labels = [periods[i][0] for i in indexes]
    originals = [first.columns[i].header or f"Column {n}" for n, i in enumerate(indexes, 1)]
    if None in labels or len(set(labels)) != len(labels):
        headers = originals
        notes.extend(f"Couldn't tell which period column '{h}' covers" for h in originals
                     if _period(h)[0] is None)
    else:
        headers = [label for label in labels if label is not None]
        notes.extend(f"Read column '{o}' as {h}" for o, h in zip(originals, headers))

    rows: list[list[object]] = []
    if first.caption:
        rows.append([first.caption])
    rows.append(["Line Item", *headers])

    for table in group:
        section = ""
        pending = ""
        for label, values in table.body:
            if not values:
                if not label or _is_amount(label) or _PARENTHETICAL_RE.match(label):
                    continue
                if pending:
                    section = pending
                pending = "" if label.endswith(":") else label
                if label.endswith(":"):
                    section = label[:-1]
                continue
            if pending and label[:1].islower():
                label = f"{pending} {label}"
            elif pending:
                section = pending
            pending = ""
            if not label:
                continue
            if _PER_SHARE_RE.search(label) or (
                    _SHARE_SUBROW_RE.match(label) and _PER_SHARE_RE.search(section)):
                shown = f"{section}: {label}" if not _PER_SHARE_RE.search(label) else label
                notes.append(f"Left out '{shown}' {_PER_SHARE_NOTE}")
                continue
            cells = [values.get(i, "") for i in indexes]
            if any(cells):
                rows.append([label, *cells])
    return StatementTable(name=name, page_numbers=pages, raw_rows=rows, notes=notes)
