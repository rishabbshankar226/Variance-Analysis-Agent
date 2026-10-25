"""Every cell value and address of the workbooks the redesign restyles, for a before/after check.

`workbooks()` builds the workbooks; `values()` reads one back with openpyxl as
{sheet name: {address: value}}. The JSON files in fixtures/xlsx_values were written from the
workbook code at 822e522, before Phase 6 changed its styles, by running this module.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOTS = ROOT / "fixtures" / "xlsx_values"


def _sample() -> bytes:
    from variance_agent.parsing import load_file
    from variance_agent.analysis import analyze_rows
    from variance_agent.models import AnalysisConfig
    from variance_agent.xlsx import render_xlsx
    rows = load_file(ROOT.parent / "examples" / "sample_variance.csv")
    return render_xlsx(analyze_rows(rows, AnalysisConfig("Q3 2026", Decimal("10000"), Decimal("0.05"))))


def _chat_export(name: str, answers: tuple[str, ...]) -> bytes:
    from variance_agent.chat.handlers import handle_message, handle_upload
    from variance_agent.chat.session import Session
    session = Session()
    handle_upload(session, (ROOT / "fixtures" / "multi_audience" / name).read_bytes(), name, first_visit=False)
    for answer in answers:
        handle_message(session, answer)
    reply = handle_message(session, "export excel")
    assert reply.download is not None, reply.text
    data = next(iter(reply.download.values()))
    assert isinstance(data, bytes)
    return data


WORKBOOKS: dict[str, Callable[[], bytes]] = {
    "sample": _sample,
    "consensus": lambda: _chat_export("consensus.csv", ("Review earnings", "Looks right", "3Q26", "$10,000 or 5%",
                                                        "USD", "25", "25", "25")),
    "comparison_set": lambda: _chat_export("comparison_set.csv", ("Looks right", "3Q26", "$10,000 or 5%", "USD", "25")),
}


def values(data: bytes) -> dict[str, dict[str, str | None]]:
    import openpyxl
    book = openpyxl.load_workbook(io.BytesIO(data))
    return {sheet.title: {cell.coordinate: None if cell.value is None else repr(cell.value)
                          for row in sheet.iter_rows() for cell in row if cell.value is not None}
            for sheet in book.worksheets}


if __name__ == "__main__":
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    for name, build in WORKBOOKS.items():
        (SNAPSHOTS / f"{name}.json").write_text(json.dumps(values(build()), indent=1, sort_keys=True) + "\n",
                                                encoding="utf-8")
        print("wrote", name)
