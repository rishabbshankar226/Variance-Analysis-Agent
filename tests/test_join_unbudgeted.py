"""X36: a line the comparison file of a pair lacks can be read as 0, as a blank budget can (fictional files).

The chat offers it as a chip; nothing is read as 0 until it is chosen.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from tests.chat_helpers import finish_setup
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session
from variance_agent.join import join_files

REALWORLD = Path(__file__).resolve().parent / "fixtures" / "realworld"
BUDGET = (REALWORLD / "fixture_f_budget_separate.csv").read_bytes()
ACTUALS = (REALWORLD / "fixture_f_actuals_separate.csv").read_bytes()
EXTRA_ACTUAL = ACTUALS + b"5040,Travel,6000,Fictional\n"
EXTRA_BUDGET = BUDGET + b"5050,Office Supplies,2000,Fictional\n"
CHIP = "Treat them as 0 (unbudgeted)"
LISTED = "In 'act.csv' but not in 'bud.csv': 5040 (Travel). Joining without them would change the totals without a trace."


def _offered() -> tuple[Session, str]:
    session = Session()
    handle_upload(session, BUDGET, "bud.csv")
    response = handle_upload(session, EXTRA_ACTUAL, "act.csv")
    return session, response.text.replace("\\", "")


def test_the_join_still_refuses_unless_asked() -> None:
    result = join_files(EXTRA_ACTUAL, "act.csv", BUDGET, "bud.csv")
    assert result.has_fatal_errors
    assert result.fatal_error_message == f"{LISTED} Add each line to the other file, or remove it, and run again."


def test_asked_the_join_reads_the_missing_comparison_as_zero() -> None:
    result = join_files(EXTRA_ACTUAL, "act.csv", BUDGET, "bud.csv", unbudgeted_as_zero=True)
    assert not result.has_fatal_errors, result.fatal_error_message
    travel = next(row for row in result.rows if row["line_item"] == "Travel")
    assert travel["budget"] == Decimal(0) and travel["actual"] == Decimal(6000)
    assert "Read 1 line in 'act.csv' but not in 'bud.csv' as 0 (unbudgeted): 5040 (Travel)" in result.visible_transformations
    assert result.join is not None
    line = next(line for line in result.join["lines"] if line["key"] == "5040")  # type: ignore[union-attr]
    assert line == {"line_item": "Travel", "key": "5040", "comparison_line_item": ""}
    assert len(result.rows) == 6


def test_a_line_only_in_the_comparison_file_still_refuses() -> None:
    result = join_files(ACTUALS, "act.csv", EXTRA_BUDGET, "bud.csv", unbudgeted_as_zero=True)
    assert result.has_fatal_errors
    assert result.fatal_error_message is not None
    assert result.fatal_error_message.startswith("In 'bud.csv' but not in 'act.csv': 5050 (Office Supplies).")


def test_the_chat_offers_the_zero_reading_as_a_chip() -> None:
    session = Session()
    handle_upload(session, BUDGET, "bud.csv")
    response = handle_upload(session, EXTRA_ACTUAL, "act.csv")
    assert response.level == "error" and response.chips == [CHIP, "Upload a different file"]
    assert response.text.replace("\\", "") == (
        f"{LISTED} Choose **{CHIP}** to read them with a budget of 0, or upload a corrected file.")
    assert session.pending_half is not None


def test_choosing_the_chip_joins_and_the_line_is_unbudgeted() -> None:
    session, _ = _offered()
    response = handle_message(session, CHIP)
    assert response.level != "error", response.text
    assert session.pending_half is None and session.phase is not Phase.AWAITING_FILE
    assert "Read 1 line in 'act.csv' but not in 'bud.csv' as 0 (unbudgeted): 5040 (Travel)" in response.text.replace("\\", "")
    finish_setup(session)
    assert session.result is not None
    travel = next(row for row in session.result.rows if row.line_item == "Travel")
    assert (travel.budget, travel.actual) == (Decimal(0), Decimal(6000))


def test_lines_missing_both_ways_refuse_with_no_chip() -> None:
    session = Session()
    handle_upload(session, EXTRA_BUDGET, "bud.csv")
    response = handle_upload(session, EXTRA_ACTUAL, "act.csv")
    assert response.level == "error" and not response.chips
    assert response.text.replace("\\", "").endswith("Add each line to the other file, or remove it, and run again.")


def test_a_corrected_upload_clears_the_offer_and_joins() -> None:
    session, _ = _offered()
    response = handle_upload(session, ACTUALS, "act.csv")
    assert response.level != "error" and session.pending_half is None
    assert session.pending_unbudgeted is None
    assert len(session.parsed_rows or []) == 5


def test_a_basis_where_zero_would_invent_a_figure_still_refuses() -> None:
    from dataclasses import replace

    from variance_agent.intake import CanonicalRole, read_input_assisted
    from variance_agent.join import join_results
    from variance_agent.models import ComparisonBasis
    a = read_input_assisted(EXTRA_ACTUAL, ".csv", filename="act.csv", missing_column=CanonicalRole.BUDGET,
                            treat_blank_budgets_as_zero=True)
    b = read_input_assisted(BUDGET, ".csv", filename="lim.csv", missing_column=CanonicalRole.ACTUAL,
                            treat_blank_budgets_as_zero=True)
    for basis in (ComparisonBasis.LIMIT, ComparisonBasis.TARGET, ComparisonBasis.CONSENSUS):
        result = join_results(a, "act.csv", [], replace(b, comparison_basis=basis), "lim.csv", BUDGET,
                              unbudgeted_as_zero=True)
        assert result.has_fatal_errors and (result.fatal_error_message or "").startswith(
            "In 'act.csv' but not in 'lim.csv': 5040 (Travel)."), basis
