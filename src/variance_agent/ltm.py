"""LTM from a 10-K and a later 10-Q, line by line by XBRL key (PLAN.md R11).

Each filing's statement is read exactly as a single-filing read would read it (labels, credits,
sign flips and footing included), so the three components of a line share one convention. LTM is
then the fiscal year plus this year to date less last year to date, in exact Decimal, with every
component cited by document, column and XBRL context. Continuity is checked from the periods'
dates, not assumed from the filing dates.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from .intake import IntakeResult, _read_ixbrl_bytes, read_input_assisted
from .ixbrl import IxbrlError, Statement, fact_values, read_statements
from .models import ComparisonBasis
from .numeric import financial_context

_FIX = "LTM needs the 10-Q that follows that 10-K; upload the 10-K the 10-Q's year continues."
_RECAST = re.compile(r"\b(?:recast|restated|as\s+adjusted)\b", re.IGNORECASE)
_PER_SHARE = re.compile(r"^'(?P<name>.*)' \(per-share and share counts are not money totals\)$")


def _months(period: tuple[str, ...]) -> int:
    start, end = date.fromisoformat(period[1]), date.fromisoformat(period[2])
    return round((end - start).days / 30.44)


def _fail(message: str) -> IntakeResult:
    return IntakeResult(has_fatal_errors=True, fatal_error_message=message, source_kind="ixbrl")


def _flow_statement(statements: list[Statement], kind: str) -> Statement | None:
    """The longest-duration statement of `kind`: the year to date in a 10-Q, the year in a 10-K."""
    found = [s for s in statements if s.kind == kind and s.periods and s.periods[0][0] == "duration"]
    return max(found, key=lambda s: _months(s.periods[0]), default=None)


def _keys(result: IntakeResult) -> dict[str, tuple[str, tuple[tuple[str, str], ...], list[dict[str, object] | None]]]:
    """Each analysed line's XBRL key (concept, dimensions) and its column records, by line name."""
    keys = {}
    for line in result.xbrl_lines:
        if line.get("subtotal") or line.get("left_out"):
            continue
        columns = [c if isinstance(c, dict) else None for c in line.get("columns", [])]  # type: ignore[attr-defined]
        first = next((c for c in columns if c is not None), None)
        if first is None:
            continue
        dims = tuple((str(d["axis"]), str(d["member"])) for d in first.get("dims", []))
        keys[str(line["line_item"])] = (str(first["concept"]), dims, columns)
    return keys


def build_ltm(quarter: bytes, quarter_name: str, annual: bytes, annual_name: str, *, sheet: str | None = None,
              treat_blank_budgets_as_zero: bool = True) -> IntakeResult:
    """Read the 10-Q's statement as LTM against the 10-K's fiscal year (PLAN.md R11)."""
    try:
        quarter_statements = read_statements(quarter, quarter_name)
        annual_statements = read_statements(annual, annual_name)
    except IxbrlError as exc:
        return _fail(str(exc))
    named = next((s for s in quarter_statements if s.name == sheet), None) if sheet else None
    if sheet and named is None:
        return _fail(f"No statement called '{sheet}' was found in '{quarter_name}'. "
                     f"Statements found: {', '.join(s.name for s in quarter_statements)}.")
    kind = named.kind if named is not None else "income"
    if kind == "cash_flow":
        return _fail("LTM is built for income statements: a cash flow statement's beginning and ending cash are "
                     "balances, which don't add across periods. Choose the income statement, or compare the cash flow "
                     "statement on its own.")
    if kind == "balance_sheet":
        result = read_input_assisted(quarter, ".htm", filename=quarter_name, sheet=sheet,
                                     treat_blank_budgets_as_zero=treat_blank_budgets_as_zero)
        result.visible_transformations.insert(0, "A balance sheet is point in time, so it is read as of its latest "
                                                  "period; LTM applies to income and cash flow statements")
        return result
    ytd, year = _flow_statement(quarter_statements, kind), _flow_statement(annual_statements, kind)
    if ytd is None:
        return _fail(f"'{quarter_name}' has no {kind.replace('_', ' ')} statement to build LTM from.")
    if year is None or _months(year.periods[0]) != 12:
        return _fail(f"'{annual_name}' has no fiscal-year {kind.replace('_', ' ')} statement. --ltm-from takes the 10-K "
                     "whose year the 10-Q continues.")
    if len(ytd.periods) < 2:
        return _fail(f"'{quarter_name}' prints no prior year to date beside its current one, so LTM can't be built.")
    fiscal, current, prior = year.periods[0], ytd.periods[0], ytd.periods[1]
    fy_label = year.labels[0]
    if _months(current) == 12:
        result = _read_ixbrl_bytes(quarter, quarter_name, ytd.name, treat_blank_budgets_as_zero, None,
                                   ComparisonBasis.PRIOR_PERIOD)
        result.visible_transformations.insert(0, f"There is no later 10-Q, so LTM equals {ytd.labels[0]} as printed")
        return result
    day_after = (date.fromisoformat(fiscal[2]) + timedelta(days=1)).isoformat()
    if current[1] != day_after:
        return _fail(f"The 10-Q's year to date starts {current[1]}, but {fy_label} in '{annual_name}' ends {fiscal[2]}, so "
                     f"the year to date should start {day_after}. {_FIX}")
    if prior[1] != fiscal[1]:
        return _fail(f"The 10-Q's prior year to date starts {prior[1]}, but {fy_label} in '{annual_name}' starts "
                     f"{fiscal[1]}, so the two years don't line up. {_FIX}")
    q_read = _read_ixbrl_bytes(quarter, quarter_name, ytd.name, treat_blank_budgets_as_zero, None,
                               ComparisonBasis.PRIOR_PERIOD)
    if q_read.has_fatal_errors:
        return q_read
    k_read = _read_ixbrl_bytes(annual, annual_name, year.name, treat_blank_budgets_as_zero, None,
                               ComparisonBasis.PRIOR_PERIOD)
    if k_read.has_fatal_errors:
        return k_read
    q_keys, k_keys = _keys(q_read), _keys(k_read)
    k_by_key = {(concept, dims): name for name, (concept, dims, _) in k_keys.items()}
    q_by_key = {(concept, dims): name for name, (concept, dims, _) in q_keys.items()}
    for name, (concept, dims, _) in q_keys.items():
        if (concept, dims) not in k_by_key:
            return _fail(f"'{name}' ({concept}) is in '{quarter_name}' but not in '{annual_name}', so LTM can't be built "
                         "line by line without changing a total. Compare the 10-Q on its own instead.")
    for name, (concept, dims, _) in k_keys.items():
        if (concept, dims) not in q_by_key:
            return _fail(f"'{name}' ({concept}) is in '{annual_name}' but not in '{quarter_name}', so LTM can't be built "
                         "line by line without changing a total. Compare the 10-Q on its own instead.")
    k_rows = {str(row["line_item"]): row for row in k_read.rows}
    q_months = _months(current)
    columns = [f"{q_months} months to {ytd.labels[0]}", f"{q_months} months to {ytd.labels[1]}"]
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in ((annual_name, annual), (quarter_name, quarter))}
    rows, lines, build = [], [], []
    with financial_context():
        for row in q_read.rows:
            name = str(row["line_item"])
            concept, dims, q_columns = q_keys[name]
            k_name = k_by_key[(concept, dims)]
            k_row = k_rows[k_name]
            if row.get("type") != k_row.get("type"):
                return _fail(f"'{name}' reads as {str(row.get('type')).lower()} in '{quarter_name}' but as "
                             f"{str(k_row.get('type')).lower()} in '{annual_name}', so LTM can't add them. Compare the "
                             "10-Q on its own instead.")
            fy, now, before = (Decimal(str(v)) for v in (k_row["actual"], row["actual"], row["budget"]))
            ltm = fy + now - before
            rows.append({**row, "actual": ltm, "budget": fy})
            k_columns = k_keys[k_name][2]
            cited = [(annual_name, fy_label, k_columns[0], 1, fy), (quarter_name, columns[0], q_columns[0], 1, now),
                     (quarter_name, columns[1], q_columns[1] if len(q_columns) > 1 else None, -1, before)]
            lines.append({"line_item": name, "concept": concept, "components": [
                {"document": document, "column": column, "context": str(key["context"]) if key else None,
                 "displayed": str(key["displayed"]) if key else None, "weight": weight, "used": format(value, "f")}
                for document, column, key, weight, value in cited], "ltm": format(ltm, "f"), "comparison": format(fy, "f")})
            build.append((name, fy, now, before, ltm))
    left_out = [f"Left out '{m.group('name')}': per-share amounts and share counts are not computable as LTM"
                for m in (_PER_SHARE.match(item) for item in ytd.left_out) if m]
    built = (f"Built LTM as {fy_label} from '{annual_name}' plus {columns[0]} less {columns[1]} from '{quarter_name}', "
             "line by line by XBRL concept")
    continuity = (f"Checked continuity: the prior year to date starts where {fy_label} starts ({fiscal[1]}), and the year "
                  f"to date starts the day after it ends ({day_after})")
    recast = ([f"'{quarter_name}' marks its statement as recast or restated; the prior year to date is used as the 10-Q "
               "prints it"] if _RECAST.search(ytd.heading) else [])
    # Where the 10-K itself tags the 10-Q's prior year to date (a quarterly note), a different figure is flagged.
    annual_facts = fact_values(annual, annual_name)
    for line in lines:
        components = line["components"]
        assert isinstance(components, list)
        q_name = str(line["line_item"])
        concept, dims, q_columns = q_keys[q_name]
        prior_key = q_columns[1] if len(q_columns) > 1 else None
        reported = annual_facts.get((concept, prior, dims))
        if prior_key is not None and reported is not None and reported != Decimal(str(prior_key["stored"])):
            recast.append(f"'{q_name}': '{annual_name}' reports {_money(reported)} for {columns[1]}, but '{quarter_name}' "
                          f"prints {_money(Decimal(str(prior_key['stored'])))}; the 10-Q's figure is used")
    notes = [built, continuity, *recast, *left_out]
    record: dict[str, object] = {"kind": "ltm", "statement": ytd.name,
              "documents": [{"name": name, "sha256": hashes[name], "statement": statement}
                            for name, statement in ((annual_name, year.name), (quarter_name, ytd.name))],
              "reader_notes": [*notes, *q_read.reader_notes], "lines": lines}
    comparing = f"Comparing LTM against {fy_label}, the fiscal year of '{annual_name}'."
    result = replace(q_read, rows=rows, comparison_basis=ComparisonBasis.PRIOR_PERIOD, comparison_label=fy_label,
                     visible_transformations=[*notes, *[t for t in q_read.visible_transformations
                                                        if not t.startswith("Comparing ")], comparing])
    result.ltm = record
    result.report_appendix = [
        "## LTM build", "", *("- " + _safe_inline(note) for note in notes), "",
        f"| Line Item | {_safe_inline(fy_label)} | + {columns[0]} | - {columns[1]} | = LTM |", "|---|---:|---:|---:|---:|",
        *(f"| {_safe_inline(name)} | {_money(fy)} | {_money(now)} | {_money(before)} | {_money(ltm)} |"
          for name, fy, now, before, ltm in build)]
    return result


def _safe_inline(text: str) -> str:
    from .report import _safe_inline as safe
    return safe(text)


def _money(value: Decimal) -> str:
    from .report import _money as money
    return money(value)
