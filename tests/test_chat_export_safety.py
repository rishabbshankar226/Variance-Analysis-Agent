"""Chat exports: spreadsheet formula injection through text cells (WS2 P1)."""

from __future__ import annotations

import csv
import io

from tests.chat_helpers import analysed, ask

HOSTILE_LABELS = [
    '=HYPERLINK("http://evil.example","click")',
    "+cmd|' /C calc'!A0",
    "@SUM(1+1)",
    "-2+3",
    "\tTabbed",
    "\rReturned",
    "Plain Label",
]


def _hostile_file() -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Line Item", "Type", "Budget", "Actual"])
    for index, label in enumerate(HOSTILE_LABELS):
        writer.writerow([label, "Expense", "-100" if index == 0 else "100", "250"])
    return out.getvalue().encode()


def _exported_rows() -> list[list[str]]:
    response = ask(analysed(_hostile_file()), "export csv")
    assert response.download is not None
    text = next(iter(response.download.values()))
    assert isinstance(text, str)
    return list(csv.reader(io.StringIO(text, newline="")))


def test_text_label_cells_cannot_start_a_formula() -> None:
    rows = _exported_rows()[1:]
    labels = [row[0] for row in rows]
    assert len(labels) == len(HOSTILE_LABELS)
    for label in labels:
        assert label[:1] not in "=+-@\t\r", label
    by_stripped = {label.lstrip("'"): label for label in labels}
    assert by_stripped['=HYPERLINK("http://evil.example","click")'].startswith("'=HYPERLINK")
    assert by_stripped["@SUM(1+1)"].startswith("'@SUM")
    assert "Plain Label" in labels  # ordinary labels are untouched


def test_numeric_columns_are_never_prefixed() -> None:
    rows = _exported_rows()
    header, body = rows[0], rows[1:]
    budget = header.index(next(h for h in header if h.startswith("Budget")))
    variance = header.index(next(h for h in header if h.startswith("Variance (")))
    values = [row[budget] for row in body]
    assert "-100" in values
    assert not any(v.startswith("'") for row in body for v in row[budget:variance + 1])
    assert not any(row[header.index("Variance (%)")].startswith("'") for row in body)
