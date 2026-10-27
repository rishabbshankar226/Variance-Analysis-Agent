"""Derived metrics declared in a mapping file, never assumed (PLAN.md R17).

A metric is a name and signed lists of numerator and (for a ratio) denominator terms. Each term
names one printed line of a filing's statement, by XBRL concept or by exact label, and a period:
the balance sheet's latest instant, the fiscal year, the year to date, or LTM (R11). Each statement
is read and checked (footing, identities) before any of its figures is used, and the figure used
is the one printed. A missing term leaves that metric out by name; a zero or negative denominator
is NM with its reason. No expression is ever evaluated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from .intake import IntakeResult, read_input_assisted
from .ixbrl import IxbrlError, Statement, read_statements
from .ltm import _months
from .models import ComparisonBasis
from .numeric import financial_context, ratio

_STATEMENTS = {"income": "income", "balance_sheet": "balance sheet", "cash_flow": "cash flow"}
_PERIODS = ("instant", "fy", "ytd", "ltm")
_METRIC_KEYS = {"name", "measure", "better", "numerator", "denominator"}
_TERM_KEYS = {"concept", "label", "statement", "period", "sign"}


@dataclass(frozen=True)
class Term:
    concept: str | None
    label: str | None
    statement: str
    period: str
    sign: int


@dataclass(frozen=True)
class Metric:
    name: str
    measure: str
    better: str | None
    numerator: tuple[Term, ...]
    denominator: tuple[Term, ...]


def _bad(message: str) -> ValueError:
    return ValueError(f"Metrics file: {message}")


def load_metrics(data: bytes) -> list[Metric]:
    """The closed structure of PLAN.md R17; anything else refuses."""
    try:
        parsed = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _bad(f"not valid JSON ({exc}).") from None
    if not isinstance(parsed, dict) or set(parsed) != {"metrics"} or not isinstance(parsed["metrics"], list) \
            or not parsed["metrics"]:
        raise _bad('expected {"metrics": [ ... ]} with at least one metric.')
    metrics, names = [], set()
    for item in parsed["metrics"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise _bad("each metric needs a name.")
        name = item["name"].strip()
        unknown = sorted(set(item) - _METRIC_KEYS)
        if unknown:
            raise _bad(f"unknown key '{unknown[0]}' in metric '{name}'.")
        if name in names:
            raise _bad(f"metric '{name}' appears twice.")
        names.add(name)
        measure = item.get("measure", "Currency")
        if measure not in {"Currency", "Multiple"}:
            raise _bad(f"measure must be Currency or Multiple (metric '{name}').")
        better = item.get("better")
        if better is not None and better not in {"Higher", "Lower"}:
            raise _bad(f"better must be Higher or Lower (metric '{name}').")

        def terms(key: str, required: bool, metric: str = name) -> tuple[Term, ...]:
            raw = item.get(key)
            if raw is None and not required:
                return ()
            if not isinstance(raw, list) or not raw:
                raise _bad(f"{key} must be a non-empty list of terms (metric '{metric}').")
            out = []
            for term in raw:
                if not isinstance(term, dict) or set(term) - _TERM_KEYS:
                    extra = sorted(set(term) - _TERM_KEYS) if isinstance(term, dict) else ["(not an object)"]
                    raise _bad(f"unknown key '{extra[0]}' in a term of metric '{metric}'.")
                concept, label = term.get("concept"), term.get("label")
                if (concept is None) == (label is None) or not isinstance(concept or label, str):
                    raise _bad(f"each term names a concept or a label, not both (metric '{metric}').")
                if term.get("statement") not in _STATEMENTS:
                    raise _bad(f"statement must be income, balance_sheet or cash_flow (metric '{metric}').")
                if term.get("period") not in _PERIODS:
                    raise _bad(f"period must be instant, fy, ytd or ltm (metric '{metric}').")
                if term.get("sign") not in (1, -1) or isinstance(term.get("sign"), bool):
                    raise _bad(f"sign must be 1 or -1 (metric '{metric}').")
                out.append(Term(concept, label, str(term["statement"]), str(term["period"]), int(term["sign"])))
            return tuple(out)

        metrics.append(Metric(name, str(measure), better, terms("numerator", True), terms("denominator", False)))
    return metrics


class _Unavailable(Exception):
    """A term that can't be read; the metric is left out with this reason."""


class _Sources:
    """The filings' statements, each read and checked once, and the lines a term can name."""

    def __init__(self, primary: bytes, primary_name: str, annual: bytes | None, annual_name: str | None) -> None:
        self.documents = [(primary_name, primary)] + ([(annual_name, annual)] if annual is not None and annual_name else [])
        self.statements: dict[str, list[Statement]] = {}
        for name, data in self.documents:
            try:
                self.statements[name] = read_statements(data, name)
            except IxbrlError as exc:
                raise ValueError(str(exc)) from None
        self._reads: dict[tuple[str, str], IntakeResult] = {}

    def _read(self, document: str, statement: Statement) -> IntakeResult:
        key = (document, statement.name)
        if key not in self._reads:
            data = dict(self.documents)[document]
            self._reads[key] = read_input_assisted(data, ".htm", filename=document, sheet=statement.name,
                                                   compare_to=ComparisonBasis.PRIOR_PERIOD, treat_blank_budgets_as_zero=True)
        return self._reads[key]

    def _statement(self, document: str, kind: str, *, year: bool | None) -> Statement | None:
        found = [s for s in self.statements.get(document, []) if s.kind == kind]
        if kind == "balance_sheet":
            return found[0] if found else None
        flows = [s for s in found if s.periods and s.periods[0][0] == "duration"]
        if year is True:
            return next((s for s in flows if _months(s.periods[0]) == 12), None)
        shorter = [s for s in flows if _months(s.periods[0]) < 12]
        return max(shorter, key=lambda s: _months(s.periods[0]), default=None)

    def _line(self, term: Term, document: str, statement: Statement) -> tuple[dict[str, object], IntakeResult]:
        read = self._read(document, statement)
        if read.has_fatal_errors:
            raise _Unavailable(f"the {_STATEMENTS[term.statement]} statement of '{document}' couldn't be read: "
                               f"{read.fatal_error_message}")
        lines = [line for line in read.xbrl_lines
                 if (line.get("concept") == term.concept if term.concept else line.get("line_item") == term.label)
                 and not any(isinstance(c, dict) and c.get("dims") for c in line.get("columns", []))]  # type: ignore[attr-defined]
        named = f"with {term.concept}" if term.concept else f"labeled '{term.label}'"
        if not lines:
            raise _Unavailable(f"no line {named} on the {_STATEMENTS[term.statement]} statement for {term.period}, so it "
                               "can't be computed")
        if len(lines) > 1:
            raise _Unavailable(f"more than one line {named} on the {_STATEMENTS[term.statement]} statement, so the term "
                               "is ambiguous")
        return lines[0], read

    def value(self, term: Term) -> tuple[Decimal, list[dict[str, object]], str]:
        """The term's printed value, its citations, and the line's printed name."""
        primary = self.documents[0][0]
        annual = self.documents[1][0] if len(self.documents) > 1 else None
        if (term.statement == "balance_sheet") != (term.period == "instant"):
            raise _Unavailable("a balance sheet line takes period instant, and only a balance sheet line does")

        def cite(document: str, statement: Statement, line: dict[str, object], column: int) -> tuple[Decimal, dict[str, object]]:
            columns = line.get("columns", [])
            key = columns[column] if isinstance(columns, list) and column < len(columns) else None
            if not isinstance(key, dict):
                raise _Unavailable(f"'{line['line_item']}' prints no figure in that column of '{document}'")
            return Decimal(str(key["displayed"])), {
                "document": document, "statement": statement.name, "column": str(key["label"]),
                "context": str(key["context"]), "concept": str(key["concept"]), "value": str(key["displayed"])}

        if term.period == "instant":
            sheet = self._statement(primary, "balance_sheet", year=None)
            if sheet is None:
                raise _Unavailable(f"'{primary}' has no balance sheet")
            line, _ = self._line(term, primary, sheet)
            value, citation = cite(primary, sheet, line, 0)
            return value, [citation], str(line["line_item"])
        if term.period in {"fy", "ytd"}:
            document = (annual or primary) if term.period == "fy" else primary
            statement = self._statement(document, term.statement, year=term.period == "fy")
            if statement is None:
                which = "fiscal-year" if term.period == "fy" else "year-to-date"
                raise _Unavailable(f"'{document}' has no {which} {_STATEMENTS[term.statement]} statement")
            line, _ = self._line(term, document, statement)
            value, citation = cite(document, statement, line, 0)
            return value, [citation], str(line["line_item"])
        if annual is None:
            raise _Unavailable("an ltm term needs --ltm-from with the 10-K")
        year = self._statement(annual, term.statement, year=True)
        ytd = self._statement(primary, term.statement, year=False)
        if year is None or ytd is None or len(ytd.periods) < 2:
            raise _Unavailable(f"LTM needs the {_STATEMENTS[term.statement]} statement for the fiscal year and both years "
                               "to date")
        from .ltm import continuity_problem
        problem = continuity_problem(year.periods[0], ytd.periods[0], ytd.periods[1], year.labels[0], annual)
        if problem:
            raise _Unavailable(problem)
        lines = []
        for document, statement in ((primary, ytd), (annual, year)):  # the 10-Q's line first: a balance refuses as such
            line, _ = self._line(term, document, statement)
            if any(isinstance(c, dict) and c.get("period", [""])[0] == "instant" for c in line.get("columns", [])):  # type: ignore[attr-defined]
                raise _Unavailable(f"'{line['line_item']}' is a cash balance, which doesn't add across periods, so it "
                                   "can't be an LTM term")
            lines.append(line)
        q_line, k_line = lines
        fy, fy_cite = cite(annual, year, k_line, 0)
        now, now_cite = cite(primary, ytd, q_line, 0)
        before, before_cite = cite(primary, ytd, q_line, 1)
        with financial_context():
            return fy + now - before, [fy_cite, now_cite, {**before_cite, "weight": -1}], str(q_line["line_item"])


def _formula(parts: list[tuple[Term, str]]) -> str:
    text = ""
    for n, (term, name) in enumerate(parts):
        piece = f"{name} [{_STATEMENTS[term.statement]}, {term.period}]"
        text += (("- " if term.sign < 0 else "") if n == 0 else (" - " if term.sign < 0 else " + ")) + piece
    return text


def _dollars(value: Decimal) -> str:
    whole = value == value.to_integral_value()
    return ("-" if value < 0 else "") + "$" + format(abs(value).quantize(Decimal(1)) if whole else abs(value), ",f")


def build_metrics(metrics: list[Metric], primary: bytes, primary_name: str, annual: bytes | None = None,
                  annual_name: str | None = None) -> tuple[IntakeResult, dict[str, str]]:
    """The metrics as the actuals half of a pair (R12), and the metrics left out, by name, with their reason."""
    sources = _Sources(primary, primary_name, annual, annual_name)
    rows: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    notes: list[str] = []
    left_out: dict[str, str] = {}
    for metric in metrics:
        resolved: dict[str, list[tuple[Term, Decimal, list[dict[str, object]], str]]] = {"numerator": [], "denominator": []}
        try:
            for side, terms in (("numerator", metric.numerator), ("denominator", metric.denominator)):
                for term in terms:
                    value, citations, name = sources.value(term)
                    resolved[side].append((term, value, citations, name))
        except _Unavailable as unavailable:
            left_out[metric.name] = str(unavailable)
            notes.append(f"Left out '{metric.name}': {unavailable}")
            records.append({"name": metric.name, "formula": None, "value": None, "reason": str(unavailable), "terms": []})
            continue
        with financial_context():
            top = sum((t.sign * v for t, v, _, _ in resolved["numerator"]), Decimal(0))
            bottom = sum((t.sign * v for t, v, _, _ in resolved["denominator"]), Decimal(0))
        numerator = _formula([(t, n) for t, _, _, n in resolved["numerator"]])
        formula = (f"({numerator}) / ({_formula([(t, n) for t, _, _, n in resolved['denominator']])})"
                   if metric.denominator else numerator)
        cited = [{**citation, "line_item": n, "sign": t.sign, "period": t.period, "side": side}
                 for side in ("numerator", "denominator") for t, _, citations, n in resolved[side] for citation in citations]
        if metric.denominator and bottom <= 0:
            reason = f"NM, because its denominator is {_dollars(bottom)} (zero or negative)"
            left_out[metric.name] = reason
            notes.append(f"{metric.name}: {reason}")
            records.append({"name": metric.name, "formula": formula, "value": None, "reason": reason, "terms": cited})
            continue
        value = ratio(top, bottom) if metric.denominator else top
        row: dict[str, object] = {"line_item": metric.name, "actual": value, "Metric Formula": formula}
        if metric.measure == "Multiple":
            row["Measure"] = "Multiple"
        if metric.better:
            row["Better"] = metric.better
        rows.append(row)
        records.append({"name": metric.name, "formula": formula, "value": format(value, "f"), "reason": None, "terms": cited})
        from .measures import format_measure
        from .models import MeasureKind
        shown = format_measure(value, MeasureKind.MULTIPLE if metric.measure == "Multiple" else MeasureKind.CURRENCY)
        notes.append(f"{metric.name} = {shown} = {formula}")
    if not rows:
        raise ValueError("No metric could be computed. " + " ".join(f"{n}." for n in notes))
    result = IntakeResult(rows=rows, rows_read=len(rows), half_filled=True, source_kind="ixbrl",
                          visible_transformations=list(notes))
    result.join = {"kind": "metrics", "documents": [
        {"name": name, "sha256": hashlib.sha256(data).hexdigest()} for name, data in sources.documents],
        "metrics": records, "reader_notes": list(notes)}
    return result, left_out


def compare_metrics(metrics_file: bytes, primary: bytes, primary_name: str, comparison: bytes, comparison_name: str, *,
                    annual: bytes | None = None, annual_name: str | None = None,
                    compare_to: ComparisonBasis | None = None) -> IntakeResult:
    """Declared metrics from the filings, joined by exact metric name with a case or covenant schedule (R12, R17)."""
    from .intake import CanonicalRole
    from .join import join_results
    from .report import _safe_inline
    half, left_out = build_metrics(load_metrics(metrics_file), primary, primary_name, annual, annual_name)
    suffix = "." + comparison_name.rsplit(".", 1)[-1].lower() if "." in comparison_name else ""
    other = read_input_assisted(comparison, suffix, filename=comparison_name, compare_to=compare_to,
                                treat_blank_budgets_as_zero=True, missing_column=CanonicalRole.ACTUAL)
    if other.has_fatal_errors:
        return other
    record = half.join or {}
    documents = [{**d, "role": "filing"} for d in record.get("documents", [])]  # type: ignore[attr-defined]
    half.column_mapping = {CanonicalRole.LINE_ITEM: "metric", CanonicalRole.ACTUAL: "value"}
    result = join_results(half, "the metrics", documents, other, comparison_name, comparison, excused=left_out)
    if result.has_fatal_errors or result.join is None:
        return result
    joined = result.join
    notes = list(record.get("reader_notes", []))  # type: ignore[call-overload]
    join_notes = [n for n in joined["reader_notes"] if not str(n).startswith("the metrics: ")]  # type: ignore[attr-defined]
    result.join = {"kind": "metrics", "key": joined["key"], "documents": joined["documents"],
                   "metrics": record.get("metrics", []), "reader_notes": [*notes, *join_notes], "lines": joined["lines"]}
    result.report_appendix = ["## Metrics", "", *("- " + _safe_inline(str(note)) for note in notes)]
    return result
