"""X51: a results screen whose result can be written as a workbook offers Export excel as a chip (fictional data)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Session

ROOT = Path(__file__).resolve().parent.parent
LIMITS = ROOT / "tests" / "fixtures" / "analysts" / "ines_limits.csv"
EXPORTS = ["Export report", "Export excel", "Export audit"]


def _results(upload: tuple[bytes, str], steps: list[str]) -> tuple[Session, list[str]]:
    session = Session()
    reply = handle_upload(session, *upload)
    for step in steps:
        reply = handle_message(session, step)
    return session, list(reply.chips or [])


@pytest.mark.parametrize(("name", "upload", "steps", "sheets"), [
    ("limit", (LIMITS.read_bytes(), LIMITS.name), ["Looks right", "Oct 2026", "$1 or 1%", "USD"], "Limits sheet"),
    ("balance sheet", (all_statements_filing(), "hal-20250927.htm"),
     ["statement Consolidated Balance Sheets", "Looks right", "Sep 2025", "$10,000 or 5%", "USD"], "Lines sheet"),
])
def test_a_results_screen_offers_its_workbook(name: str, upload: tuple[bytes, str], steps: list[str],
                                              sheets: str) -> None:
    session, chips = _results(upload, steps)
    assert chips == EXPORTS, name
    assert handle_message(session, "Export excel").text == f"Excel workbook ready for download: {sheets}."


def test_a_filings_income_statement_offers_its_workbook() -> None:
    session, chips = _results((all_statements_filing(), "hal-20250927.htm"), ["Looks right", "FY2025", "$1 or 1%", "USD"])
    assert chips[-3:] == EXPORTS and chips[:-3] == [chip for chip in chips if chip not in EXPORTS]
    assert handle_message(session, "Export excel").text == (
        "Excel workbook ready for download: Summary, Material Variances, Root Causes & Actions, and All Rows sheets.")
