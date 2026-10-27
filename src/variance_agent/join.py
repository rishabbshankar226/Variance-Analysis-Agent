"""Budget and actuals in two files, joined on a key both carry (PLAN.md R12, F4).

Each file is read on its own, by the same reader as any file, so its captions, hidden rows, display
scaling, formulas and blanks are checked as usual and its unit caption scales only its own figures.
The rows are then joined on an account-ID column both files carry, or else on the exact line-item
label. A key in one file only, or repeated in one file, refuses: a join that dropped or doubled a
line would change the totals without a trace.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import replace

from .intake import CanonicalRole, IntakeResult, read_input_assisted
from .models import ComparisonBasis

_FIX = "Add each line to the other file, or remove it, and run again."


def _key(value: object) -> str:
    text = str(value).strip()
    return text[:-2] if re.fullmatch(r"-?\d+\.0", text) else text  # 4010.0 stored as a decimal is 4010


def _fail(message: str) -> IntakeResult:
    return IntakeResult(has_fatal_errors=True, fatal_error_message=message)


def half_role(data: bytes, filename: str) -> tuple[CanonicalRole, str] | None:
    """Which value column a file lacks (Budget or Actual) when it is one half of a pair, and its join key name."""
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for missing in (CanonicalRole.ACTUAL, CanonicalRole.BUDGET):
        result = read_input_assisted(data, suffix, filename=filename, missing_column=missing,
                                     treat_blank_budgets_as_zero=True)
        if result.half_filled and not result.has_fatal_errors and result.rows:
            key = result.column_mapping.get(CanonicalRole.ACCOUNT_ID)
            return missing, f"'{key}'" if key else "line item"
    return None


def join_files(actual: bytes, actual_name: str, comparison: bytes, comparison_name: str, *,
               sheet: str | None = None, compare_to: ComparisonBasis | None = None,
               hidden_rows: str | None = None, treat_blank_budgets_as_zero: bool = True) -> IntakeResult:
    """The actuals file's rows, each with its comparison figure from the other file (PLAN.md R12)."""
    def suffix(name: str) -> str:
        return "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""

    a = read_input_assisted(actual, suffix(actual_name), filename=actual_name, sheet=sheet, compare_to=compare_to,
                            hidden_rows=hidden_rows, treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
                            missing_column=CanonicalRole.BUDGET)
    if a.has_fatal_errors:
        return a
    b = read_input_assisted(comparison, suffix(comparison_name), filename=comparison_name, compare_to=compare_to,
                            hidden_rows=hidden_rows, treat_blank_budgets_as_zero=treat_blank_budgets_as_zero,
                            missing_column=CanonicalRole.ACTUAL)
    if b.has_fatal_errors:
        return b
    if not b.half_filled:
        return _fail(f"'{comparison_name}' already has an Actual column, so it isn't the comparison half of a pair. "
                     "Run it on its own, without --compare-file.")
    if not a.half_filled:
        return _fail(f"'{actual_name}' already has a comparison column, so it isn't the actuals half of a pair. "
                     "Run it on its own, without --compare-file.")
    return join_results(a, actual_name, [{"name": actual_name, "sha256": hashlib.sha256(actual).hexdigest(),
                                          "role": "actual"}], b, comparison_name, comparison)


_DECLARATIONS = ("line_item", "actual", "budget", "account_id")


def join_results(a: IntakeResult, actual_name: str, actual_documents: list[dict[str, object]], b: IntakeResult,
                 comparison_name: str, comparison: bytes, excused: dict[str, str] | None = None) -> IntakeResult:
    """Join two read halves: the actuals' rows, each with the matching comparison row's figure and declarations."""
    excused = excused or {}
    by_account = CanonicalRole.ACCOUNT_ID in a.column_mapping and CanonicalRole.ACCOUNT_ID in b.column_mapping
    field = "account_id" if by_account else "line_item"
    key_name = str(a.column_mapping[CanonicalRole.ACCOUNT_ID]) if by_account else "line item"
    keyed: list[dict[str, dict[str, object]]] = []
    for result, name in ((a, actual_name), (b, comparison_name)):
        rows: dict[str, dict[str, object]] = {}
        for row in result.rows:
            key = _key(row.get(field, ""))
            if key in rows:
                return _fail(f"'{key}' appears more than once in '{name}', so I can't tell which row to join. "
                             f"Combine those rows, or give each its own {key_name}, and run again.")
            rows[key] = row
        keyed.append(rows)
    a_rows, b_rows = keyed
    for (one, one_name), (other, other_name) in (((a_rows, actual_name), (b_rows, comparison_name)),
                                                 ((b_rows, comparison_name), (a_rows, actual_name))):
        only = [key for key in one if key not in other and not (one is b_rows and key in excused)]
        if only:
            shown = ", ".join(key + (f" ({one[key]['line_item']})" if by_account else "") for key in only[:5])
            more = f" and {len(only) - 5} more" if len(only) > 5 else ""
            return _fail(f"In '{one_name}' but not in '{other_name}': {shown}{more}. Joining without them would change "
                         f"the totals without a trace. {_FIX}")
    # The comparison file's own declarations (Limit Kind, Buffer, Better, Tolerance, Measure) come with its figure,
    # where the actuals row doesn't declare them itself.
    joined_rows: list[dict[str, object]] = [
        {**{k: v for k, v in b_rows[key].items() if k not in _DECLARATIONS}, **row, "budget": b_rows[key]["budget"]}
        for key, row in a_rows.items()]
    renamed = [(str(row["line_item"]), str(b_rows[key]["line_item"])) for key, row in a_rows.items()
               if str(row["line_item"]) != str(b_rows[key]["line_item"])]
    joined = (f"Joined '{comparison_name}' to '{actual_name}' by '{key_name}': {len(joined_rows)} line"
              f"{'s' if len(joined_rows) != 1 else ''}, each in both files")
    notes = [joined, f"Took Actual from '{actual_name}' and the comparison from '{comparison_name}'"]
    notes += [f"Left out '{key}' of '{comparison_name}': {reason}" for key, reason in excused.items() if key in b_rows]
    if renamed:
        notes.append("Kept the actuals file's labels where the files differ: "
                     + "; ".join(f"'{mine}' is '{theirs}' in '{comparison_name}'" for mine, theirs in renamed[:5])
                     + (f"; and {len(renamed) - 5} more" if len(renamed) > 5 else ""))
    drop = ("Comparing ", "Used '")  # each half's own comparison note and account note are restated above
    halves = [f"{actual_name}: {t}" for t in a.visible_transformations if not t.startswith(drop)]
    halves += [f"{comparison_name}: {t}" for t in b.visible_transformations if not t.startswith(drop)]
    basis, label = b.comparison_basis, b.comparison_label
    comparing = [t for t in b.visible_transformations if t.startswith("Comparing ")]
    record: dict[str, object] = {
        "kind": "join", "key": key_name,
        "documents": [*actual_documents, {"name": comparison_name, "sha256": hashlib.sha256(comparison).hexdigest(),
                                          "role": "comparison"}],
        "reader_notes": [*notes, *halves],
        "lines": [{"line_item": str(row["line_item"]), "key": key, "comparison_line_item": str(b_rows[key]["line_item"])}
                  for key, row in a_rows.items()],
    }
    result = replace(a, rows=joined_rows, comparison_basis=basis, comparison_label=label,
                     column_mapping={**a.column_mapping, CanonicalRole.BUDGET:
                                     f"{b.column_mapping.get(CanonicalRole.BUDGET, 'Budget')} in {comparison_name}"},
                     visible_transformations=[*notes, *halves, *comparing],
                     blank_budget_items=list(b.blank_budget_items), detected_totals=[*a.detected_totals])
    result.join = record
    return result
