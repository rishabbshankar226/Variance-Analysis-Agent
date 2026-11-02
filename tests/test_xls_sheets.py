"""X17: an .xls workbook (Excel 2007+ bytes under the old name) lists and switches sheets in the chat (fictional)."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Session


def _book() -> bytes:
    book = Workbook()
    summary = book.active
    summary.title = "Summary"
    summary.append(["Line Item", "Budget", "Actual"])
    summary.append(["Fictional Sales", 100, 120])
    data = book.create_sheet("Data")
    data.append(["Line Item", "Budget", "Actual"])
    data.append(["Fictional Rent", 50, 55])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize("name", ["book.xls", "book.xlsx"])
def test_sheets_list_and_switch(name: str) -> None:
    session = Session()
    handle_upload(session, _book(), name)
    listed = handle_message(session, "list sheets").text
    assert "1. **Summary**" in listed and "2. **Data**" in listed
    assert "Switched to worksheet **'Data'**" in handle_message(session, "sheet Data").text


def test_a_csv_still_holds_a_single_dataset() -> None:
    session = Session()
    handle_upload(session, b"Line Item,Budget,Actual\nFictional Sales,100,120\n", "plain.csv")
    assert "contains a single dataset" in handle_message(session, "list sheets").text
