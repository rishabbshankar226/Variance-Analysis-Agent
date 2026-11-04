"""S2 characterization: assisted intake's rows and notes for every fixture under tests/fixtures/.

Phase 4 splits `intake._process_raw_table` into named stages without changing behaviour (docs/improve/PLAN.md,
S2). Each fixture is read twice, with blank comparison amounts left blank and read as 0, and everything intake
returns about it is compared with the snapshot taken before the split.

Regenerate the snapshot only for an approved behaviour change:
    .venv/bin/python -c "from tests.test_characterization_s2 import write; write()"
"""

from __future__ import annotations

import json
from pathlib import Path

from variance_agent.intake import read_input_assisted

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SNAPSHOT = FIXTURES / "characterization" / "s2_intake.json"
SUFFIXES = {".csv", ".tsv", ".txt", ".json", ".xlsx", ".xlsm", ".xls", ".htm", ".html", ".pdf"}


def fixtures() -> list[Path]:
    return sorted(path for path in FIXTURES.rglob("*") if path.suffix.lower() in SUFFIXES
                  and "characterization" not in path.parts)


def _read(path: Path, blanks_as_zero: bool) -> dict[str, object]:
    try:
        result = read_input_assisted(path.read_bytes(), path.suffix.lower(), filename=path.name,
                                     treat_blank_budgets_as_zero=blanks_as_zero)
    except Exception as exc:  # recorded, so a change in what raises is seen too
        return {"raised": f"{type(exc).__name__}: {exc}"}
    return {
        "fatal": result.has_fatal_errors, "message": result.fatal_error_message, "rows": result.rows,
        "notes": result.visible_transformations, "reader_notes": result.reader_notes,
        "mapping": {role.value: header for role, header in result.column_mapping.items()},
        "basis": result.comparison_basis, "label": result.comparison_label, "sheet": result.sheet_name,
        "header_row": result.header_row_number, "unit": result.detected_unit_multiplier,
        "totals": result.detected_totals, "blanks": result.blank_budget_items, "blanks_as_zero": result.blank_budgets_as_zero,
        "signed": result.detected_signed_ledger, "flipped": result.negative_revenue_items,
        "pairs": [pair.period for pair in result.detected_period_pairs or []],
        "problems": [str(problem) for problem in result.problems], "period_names": result.period_names,
    }


def snapshot() -> dict[str, object]:
    found = {f"{path.relative_to(FIXTURES).as_posix()} blanks={flag}": _read(path, flag)
             for path in fixtures() for flag in (False, True)}
    return json.loads(json.dumps(found, default=str))  # type: ignore[no-any-return]


def write() -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot(), indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def test_intake_reads_every_fixture_as_before_the_split() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = snapshot()
    assert sorted(actual) == sorted(expected)
    for key in sorted(expected):
        assert actual[key] == expected[key], key
