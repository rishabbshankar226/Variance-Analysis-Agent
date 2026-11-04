"""X16: a label with no amounts in any column is a section heading, left out visibly (fictional data)."""

from __future__ import annotations

from variance_agent.intake import read_input_assisted

HEADED = b"""GL Account,Line Item,Budget,Actual
,REVENUE,,
4000,Fictional Product Sales,100,120
,OPERATING EXPENSES,,
6000,Fictional Rent,50,55
"""


def test_section_headings_are_left_out_with_a_note() -> None:
    result = read_input_assisted(HEADED, ".csv", filename="headed.csv")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert [row["line_item"] for row in result.rows] == ["Fictional Product Sales", "Fictional Rent"]
    assert ("Left out 2 section heading rows with no amounts in any column: Row 2 (REVENUE), "
            "Row 4 (OPERATING EXPENSES).") in result.visible_transformations


def test_a_labelled_row_with_one_amount_still_names_the_blank_cell() -> None:
    data = HEADED.replace(b"6000,Fictional Rent,50,55", b"6000,Fictional Rent,50,")
    result = read_input_assisted(data, ".csv", filename="headed.csv")
    assert result.has_fatal_errors
    assert "Row 5, Fictional Rent, Actual column: the amount is blank." in (result.fatal_error_message or "")
