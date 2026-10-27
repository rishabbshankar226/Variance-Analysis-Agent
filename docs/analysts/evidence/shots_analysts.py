"""Screenshots of the chat screens this run changed, at each STOP (docs/analysts/PLAN.md, Decision 8).

Reuses the interface redesign's harness (docs/ui/evidence/shots.py) with this run's scenarios.
Every file uploaded is fictional and built here: an Inline XBRL filing for HALVORSEN.FAKE, a
workbook with a hidden row, and one with a formula Excel never calculated.

    .venv/bin/python docs/analysts/evidence/shots_analysts.py --build <scratch dir>
    ~/.venvs/vaa-shots/bin/python docs/analysts/evidence/shots_analysts.py <out dir> <scratch dir>

The project venv builds the files (it has openpyxl); the harness's venv takes the screenshots.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "docs" / "ui" / "evidence"))
sys.path.insert(0, str(ROOT))



FILES = {"filing": "hal-20250927.htm", "hidden": "plan_hidden_rows.xlsx", "formula": "plan_uncalculated.xlsx",
         "statements": "hal-statements-20250927.htm", "quarter": "hal-20260328.htm",
         "budget": "fixture_f_budget_separate.csv", "actuals": "fixture_f_actuals_separate.csv",
         # Phase 6: the new readers' own files (tests/fixtures/analysts/).
         "limits": "ines_limits.csv", "benchmark": "theo_benchmark.csv", "targets": "marcus_targets.csv",
         "metrics": "clara_metrics.json", "covenants": "clara_covenants.csv"}


def build(scratch: Path) -> None:
    from openpyxl import Workbook  # type: ignore[import-untyped]

    from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing, income_filing, quarter_all_filing

    def save(name: str, rows: list[list[object]], hide: int | None = None) -> Path:
        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        for row in rows:
            sheet.append(row)
        if hide is not None:
            sheet.row_dimensions[hide].hidden = True
        capture = io.BytesIO()
        workbook.save(capture)
        path = scratch / name
        path.write_bytes(capture.getvalue())
        return path

    scratch.mkdir(parents=True, exist_ok=True)
    (scratch / FILES["filing"]).write_bytes(income_filing())
    (scratch / FILES["statements"]).write_bytes(all_statements_filing())
    (scratch / FILES["quarter"]).write_bytes(quarter_all_filing())
    realworld = ROOT / "tests" / "fixtures" / "realworld"
    for key in ("budget", "actuals"):
        (scratch / FILES[key]).write_bytes((realworld / FILES[key]).read_bytes())
    for key in ("limits", "benchmark", "targets", "metrics", "covenants"):
        (scratch / FILES[key]).write_bytes((ROOT / "tests" / "fixtures" / "analysts" / FILES[key]).read_bytes())
    save(FILES["hidden"], [["Line Item", "Budget", "Actual", "Type"], ["Revenue", 100, 110, "Revenue"],
                           ["Draft line", 5, 5, "Expense"], ["COGS", 40, 45, "Expense"]], hide=3)
    save(FILES["formula"], [["Line Item", "Budget", "Actual", "Type"], ["Revenue", 100, 110, "Revenue"],
                            ["COGS", 40, 45, "Expense"], ["Other income", "=B2-B3", 70, "Revenue"]])


def main(out: Path, scratch: Path) -> None:
    import shots  # type: ignore[import-not-found]  # the redesign harness; needs Playwright

    files = {key: scratch / name for key, name in FILES.items()}
    shots.SCENARIOS = {
        "filing": [("upload", str(files["filing"]), "htm-summary"), ("say", "statements", "htm-statements")],
        "hidden-rows": [("upload", str(files["hidden"]), "hidden-question"),
                        ("say", "Leave the hidden rows out", "hidden-answer")],
        "formula": [("upload", str(files["formula"]), "formula-refusal")],
        # Phase 4: a balance sheet compared, LTM from a second upload, budget and actuals joined.
        "balance-sheet": [("upload", str(files["statements"]), "bs-upload"),
                          ("say", "statement Consolidated Balance Sheets", "bs-summary"),
                          ("say", "Looks right", "bs-period"), ("say", "Sep 2025", "bs-thresholds"),
                          ("say", "$1 or 1%", "bs-currency"), ("say", "USD", "bs-report")],
        "ltm": [("upload", str(files["quarter"]), "ltm-offer"), ("say", "Build LTM", "ltm-ask"),
                ("upload", str(files["filing"]), "ltm-summary")],
        "join": [("upload", str(files["budget"]), "join-ask"), ("upload", str(files["actuals"]), "join-summary")],
        # Phase 6: each new reader from upload to a first answer.
        "limits": [("upload", str(files["limits"]), "limits-summary"), ("say", "Looks right", "limits-period"),
                   ("say", "Oct 2026", "limits-thresholds"), ("say", "$1 or 1%", "limits-currency"),
                   ("say", "USD", "limits-report"), ("say", "which limits are breached", "limits-ask")],
        "benchmark": [("upload", str(files["benchmark"]), "benchmark-summary"), ("say", "Looks right", "benchmark-period"),
                      ("say", "Oct 2026", "benchmark-thresholds"), ("say", "$1 or 1%", "benchmark-currency"),
                      ("say", "USD", "benchmark-bps"), ("say", "1", "benchmark-report"),
                      ("say", "active return", "benchmark-ask")],
        "target": [("upload", str(files["targets"]), "target-summary"), ("say", "Looks right", "target-period"),
                   ("say", "Oct 2026", "target-thresholds"), ("say", "$1 or 1%", "target-currency"),
                   ("say", "USD", "target-bps"), ("say", "1", "target-report"), ("say", "drift from target", "target-ask")],
        "covenant": [("upload", str(files["statements"]), "covenant-upload"),
                     ("say", "compare balance sheets", "covenant-bs-summary"), ("say", "Looks right", "covenant-period"),
                     ("say", "Sep 2025", "covenant-thresholds"), ("say", "$1 or 1%", "covenant-currency"),
                     ("say", "USD", "covenant-bs-report"), ("say", "covenant headroom", "covenant-ask"),
                     ("upload", str(files["metrics"]), "covenant-schedule-ask"),
                     ("upload", str(files["covenants"]), "covenant-summary"),
                     ("say", "Looks right", "covenant-turns"), ("say", "0.1", "covenant-report")],
    }
    for path in shots.run(out, ["light"], ["d", "m"], list(shots.SCENARIOS)):
        print(path)


if __name__ == "__main__":
    if sys.argv[1] == "--build":
        build(Path(sys.argv[2]))
    else:
        main(Path(sys.argv[1]), Path(sys.argv[2]))
