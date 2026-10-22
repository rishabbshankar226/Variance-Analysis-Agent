"""Chat exports: spreadsheet formula injection through text cells (WS2 P1)."""

from __future__ import annotations

import csv
import io
import re

from tests.chat_helpers import SAMPLE_CSV, analysed, ask
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

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


# ---- download names -----------------------------------------------------------------------

ODD_PERIOD = 'Q3 #1/2026; x="y" ../etc'


def _session_for_period(period: str) -> Session:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "a.csv")
    handle_message(session, period)
    handle_message(session, "$1,000 or 5%")
    handle_message(session, "USD")
    assert session.phase == Phase.EXPLORING
    return session


def test_download_names_contain_only_safe_characters() -> None:
    session = _session_for_period(ODD_PERIOD)
    for prompt in ("export report", "export audit", "export csv", "export excel", "memo"):
        download = ask(session, prompt).download
        assert download is not None, prompt
        for filename in download:
            assert re.fullmatch(r"[a-z_]+_[a-z0-9_-]+\.(?:md|json|csv|xlsx)", filename), filename


def test_ordinary_periods_keep_their_download_names() -> None:
    session = _session_for_period("Jul-26")
    assert "variance_report_jul-26.md" in (ask(session, "export report").download or {})
    session = _session_for_period("FY 2026")
    assert "variance_audit_fy_2026.json" in (ask(session, "export audit").download or {})


def test_an_overlong_period_is_refused() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "a.csv")
    response = handle_message(session, "Q3 " + "x" * 200)
    assert session.phase == Phase.AWAITING_PERIOD
    assert session.period is None
    assert "short" in response.text.lower()
