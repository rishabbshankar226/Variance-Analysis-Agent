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



FILES = {"filing": "hal-20250927.htm", "hidden": "plan_hidden_rows.xlsx", "formula": "plan_uncalculated.xlsx"}


def build(scratch: Path) -> None:
    from openpyxl import Workbook

    from tests.fixtures.ixbrl.build_ixbrl import income_filing

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
    save(FILES["hidden"], [["Line Item", "Budget", "Actual", "Type"], ["Revenue", 100, 110, "Revenue"],
                           ["Draft line", 5, 5, "Expense"], ["COGS", 40, 45, "Expense"]], hide=3)
    save(FILES["formula"], [["Line Item", "Budget", "Actual", "Type"], ["Revenue", 100, 110, "Revenue"],
                            ["COGS", 40, 45, "Expense"], ["Other income", "=B2-B3", 70, "Revenue"]])


def main(out: Path, scratch: Path) -> None:
    import shots  # the redesign's harness; needs Playwright

    files = {key: scratch / name for key, name in FILES.items()}
    shots.SCENARIOS = {
        "filing": [("upload", str(files["filing"]), "htm-summary"), ("say", "statements", "htm-statements")],
        "hidden-rows": [("upload", str(files["hidden"]), "hidden-question"),
                        ("say", "Leave the hidden rows out", "hidden-answer")],
        "formula": [("upload", str(files["formula"]), "formula-refusal")],
    }
    for path in shots.run(out, ["light"], ["d", "m"], list(shots.SCENARIOS)):
        print(path)


if __name__ == "__main__":
    if sys.argv[1] == "--build":
        build(Path(sys.argv[2]))
    else:
        main(Path(sys.argv[1]), Path(sys.argv[2]))
