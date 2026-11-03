"""X50: a statement's "EPS" line is per-share, left out of the money lines or kept as Per Share, never scaled.

Every statement here is built in the test and every value is fictional.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.test_excel_edgar_statement import LINES, _read, _statement
from variance_agent.intake import read_input_assisted
from variance_agent.pdf_tables import statement_tables_from_grid

BODY = [("Total net sales", ["1,000", "900"]), ("STEPS program costs", ["40", "35"]),
        ("Epsilon fund income", ["12", "10"]), ("Net income", ["100", "90"]), ("Basic EPS", ["1.23", "1.10"]),
        ("Diluted EPS", ["1.20", "1.08"]), ("Adjusted EPS", ["1.30", "1.15"]), ("Basic earnings per share", ["1.23", "1.10"])]
HEADERS = ["12 Months Ended Sep. 27, 2025", "12 Months Ended Sep. 28, 2024"]
EDGAR_LINES = [line for line in LINES if not str(line[0]).startswith("Basic")] + [
    ("Basic EPS", Decimal("6.1"), Decimal("5.5")), ("Diluted EPS", Decimal("6.0"), Decimal("5.4"))]


def _grid(*, per_share_lines: bool = False):  # type: ignore[no-untyped-def]
    [table] = statement_tables_from_grid("CONSOLIDATED STATEMENTS OF OPERATIONS", "(In millions, except per share data)",
                                         HEADERS, BODY, per_share_lines=per_share_lines)
    return table


def test_eps_lines_are_left_out_of_a_statements_money_lines() -> None:
    table = _grid()
    assert [row[0] for row in table.raw_rows[2:]] == [
        "Total net sales", "STEPS program costs", "Epsilon fund income", "Net income"]
    for label in ("Basic EPS", "Diluted EPS", "Adjusted EPS", "Basic earnings per share"):
        assert f"Left out '{label}' (per-share and share counts are not money totals)" in table.notes


def test_with_per_share_lines_an_eps_line_is_kept_as_per_share() -> None:
    table = _grid(per_share_lines=True)
    row = next(row for row in table.raw_rows if row[0] == "Basic EPS")
    assert row[1:3] == ["1.23", "1.10"] and row[3] == "Per Share"


def test_an_edgar_statement_reads_without_its_eps_lines() -> None:
    result = _read(_statement(lines=EDGAR_LINES))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert not [row for row in result.rows if "EPS" in str(row["line_item"])]
    million = Decimal(1_000_000)
    assert next(row for row in result.rows if row["line_item"] == "Net sales")["actual"] == 4100 * million
    assert "Left out 'Basic EPS' (per-share and share counts are not money totals)" in result.visible_transformations


@pytest.mark.parametrize("label", ["Basic EPS", "Diluted EPS"])
def test_an_edgar_statements_eps_line_kept_as_per_share_is_not_scaled(label: str) -> None:
    result = read_input_assisted(_statement(lines=EDGAR_LINES), ".xlsx", filename="Financial_Report.xlsx",
                                 per_share_lines=True)
    assert not result.has_fatal_errors, result.fatal_error_message
    row = next(row for row in result.rows if row["line_item"] == label)
    assert (Decimal(str(row["budget"])), Decimal(str(row["actual"]))) == dict(
        (name, (Decimal(str(b)), Decimal(str(a)))) for name, a, b in EDGAR_LINES)[label]
