"""T2: tests that kill the three mutants Phase 1's test-strength sample found surviving (fictional inputs).

docs/improve/evidence/stop-1/mutation-sample.md lists them: draw #2 (`_read_excel_bytes`' except clause re-raising),
#4 (the earnings sheet's layout test negated) and #11 (the percentage-points note's test negated).
"""

from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook

import variance_agent.intake as intake
from variance_agent.audience import AudienceConfig
from variance_agent.chat.handlers import handle_upload
from variance_agent.chat.session import Session
from variance_agent.comparisons import analyze_comparisons
from variance_agent.models import ComparisonBasis
from variance_agent.xlsx import render_comparison_xlsx

WORKBOOK = Path(__file__).resolve().parent / "fixtures" / "realworld" / "fixture_a_erp_title_block.xlsx"
BROKEN = ("Could not read Excel file 'book.xlsx': 'broken part'. Open it in Excel, save the sheet with the statement "
          "as a new workbook, and upload that.")


def _failing_loader():  # type: ignore[no-untyped-def]
    def load(*args: object, **kwargs: object) -> object:
        raise KeyError("broken part")
    return load


def test_a_workbook_the_loader_cannot_open_is_refused_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    """Draw #2: past the workbook check, a loader failure is a refusal naming the file, never an exception."""
    monkeypatch.setattr(intake, "_excel_loader", _failing_loader)
    result = intake.read_input_assisted(WORKBOOK.read_bytes(), ".xlsx", filename="book.xlsx")
    assert (result.has_fatal_errors, result.fatal_error_message) == (True, BROKEN)
    reply = handle_upload(Session(), WORKBOOK.read_bytes(), "book.xlsx")  # the chat catches only ValueError
    monkeypatch.undo()
    assert reply.level == "error"


@pytest.mark.parametrize(("preset", "sheets"), [("fpa", ["Comparisons"]), ("earnings", ["Earnings", "Comparisons"])])
def test_only_the_earnings_layout_adds_an_earnings_sheet(preset: str, sheets: list[str]) -> None:
    """Draw #4: a consensus and estimate table gets the Earnings sheet under the earnings layout only."""
    rows: list[dict[str, object]] = [
        {"Line Item": "Revenue", "Type": "Revenue", "Consensus": "100", "Model": "105", "Actual": "110"}]
    config = AudienceConfig(period="3Q26", dollar_threshold=Decimal("10"), percent_threshold=Decimal(".02"),
                            comparison_basis=ComparisonBasis.CONSENSUS, preset=preset)
    table = analyze_comparisons(rows, config, (ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE))
    assert load_workbook(io.BytesIO(render_comparison_xlsx(table))).sheetnames == sheets


@pytest.mark.parametrize(("budget", "actual", "said"), [("41.2%", "40.6%", True), ("0.412", "0.406", False)])
def test_the_percentage_points_note_appears_only_for_values_with_a_percent_sign(budget: str, actual: str,
                                                                                said: bool) -> None:
    """Draw #11: a rate written with % is read as percentage points and says so; a bare rate does not."""
    data = f"Line Item,Measure,Better,Budget,Actual\nGross Margin,Percent,Higher,{budget},{actual}\n".encode()
    result = intake.read_input_assisted(data, ".csv", filename="f.csv")
    assert ("Gross Margin: read % values as percentage points." in result.visible_transformations) is said
