"""The JSON shape of a chat reply: the fields the page reads, and the error level that styles a refusal.

A refusal used to be marked by a warning sign at the start of its text. It now carries `level`
("error") through /message, /upload and /status, and the text starts with the sentence itself.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.client import HTTPConnection
from typing import Any

from pathlib import Path

import pytest

from tests.chat_helpers import SAMPLE_CSV
from tests.test_interface_design import banned_glyphs
from tests.test_plain_language import assert_plain_language
from tests.test_chat import _post_upload, chat_server_url  # noqa: F401  (chat_server_url is a fixture)
from variance_agent.chat.handlers import _intake_summary_text, handle_message, handle_upload
from variance_agent.chat.responses import Response
from variance_agent.chat.server import _ChatHandler
from variance_agent.chat.session import Session
from variance_agent.chat.views import with_lead

REPLY_KEYS = {"text", "phase", "table", "chips", "level", "view", "download_url", "download_filename"}
WARNING_SIGN = "⚠"


def _request(url: str, method: str, path: str, body: bytes | None = None,
             headers: dict[str, str] | None = None) -> dict[str, Any]:
    conn = HTTPConnection(url)
    conn.request(method, path, body=body, headers=headers or {})
    res = conn.getresponse()
    assert res.status == HTTPStatus.OK
    data: dict[str, Any] = json.loads(res.read().decode("utf-8"))
    conn.close()
    return data


def _message(url: str, text: str) -> dict[str, Any]:
    body = json.dumps({"text": text}).encode("utf-8")
    return _request(url, "POST", "/message", body, {"Content-Type": "application/json",
                                                     "Content-Length": str(len(body))})


def _upload(url: str, name: str, content: bytes) -> dict[str, Any]:
    boundary = "----ShapeBoundary"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: text/csv\r\n\r\n").encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return _request(url, "POST", "/upload", body, {"Content-Type": f"multipart/form-data; boundary={boundary}",
                                                   "Content-Length": str(len(body))})


def test_a_refused_upload_carries_the_error_level_and_no_warning_sign(chat_server_url: str) -> None:  # noqa: F811
    reply = _upload(chat_server_url, "empty.csv", b"Line Item,Budget,Actual\n")
    assert set(reply) <= REPLY_KEYS
    assert reply["level"] == "error"
    assert "contains no data rows" in reply["text"]
    assert not reply["text"].startswith(WARNING_SIGN)


def test_a_good_upload_has_no_level(chat_server_url: str) -> None:  # noqa: F811
    reply = _post_upload(chat_server_url, "0")
    assert set(reply) <= REPLY_KEYS
    assert "level" not in reply
    assert reply["phase"] != "awaiting_file"


def test_a_refused_message_carries_the_error_level(chat_server_url: str) -> None:  # noqa: F811
    reply = _message(chat_server_url, "alpha\tbeta\nfoo\tbar\n")
    assert set(reply) <= REPLY_KEYS
    assert reply["level"] == "error"
    assert "paste a table" in reply["text"].lower()
    ok = _message(chat_server_url, "help")
    assert "level" not in ok


def test_the_status_payload_passes_the_start_up_replys_level(chat_server_url: str) -> None:  # noqa: F811
    _ChatHandler.initial_response = Response(text="The file could not be read.", level="error")
    try:
        status = _request(chat_server_url, "GET", "/status")
    finally:
        _ChatHandler.initial_response = None
    assert status["initial_response"] == {"text": "The file could not be read.", "chips": None,
                                          "table": None, "level": "error", "view": None}


def test_sample_upload_still_reads_as_before(chat_server_url: str) -> None:  # noqa: F811
    reply = _upload(chat_server_url, "sample.csv", SAMPLE_CSV)
    assert "level" not in reply and reply["phase"] == "awaiting_period"


# ---------------------------------------------------------------------------
# The intake panel (`view` kind "intake")
# ---------------------------------------------------------------------------

INTAKE_KEYS = {"kind", "title", "lead", "rows", "notes", "question"}
REALWORLD = Path(__file__).resolve().parent / "fixtures" / "realworld"


def _assert_intake_shape(view: dict[str, Any]) -> None:
    assert set(view) == INTAKE_KEYS and view["kind"] == "intake"
    assert view["title"] == "How I read your file" and view["question"] == "Does this look right?"
    assert view["lead"] is None or isinstance(view["lead"], str)
    assert view["rows"] and all(set(row) == {"label", "value"} for row in view["rows"])
    assert all(isinstance(row["label"], str) and isinstance(row["value"], str) for row in view["rows"])
    assert all(set(note) == {"title", "items", "more"} and note["items"] for note in view["notes"])


def test_the_intake_summary_comes_as_rows_and_the_text_is_unchanged() -> None:
    session = Session()
    name = "fixture_d_thousands_dashes_blanks.xlsx"
    handle_upload(session, (REALWORLD / name).read_bytes(), name, first_visit=False)
    reply = handle_message(session, "Treat blank budgets as 0 (unbudgeted)")
    assert reply.view is not None
    view = json.loads(json.dumps(reply.view))  # it must survive JSON as it is
    _assert_intake_shape(view)
    assert view["lead"] is None
    labels = [row["label"] for row in view["rows"]]
    assert labels == ["Worksheet", "Header row", "Line items", "Budget", "Actual", "Rows read"]
    assert {"label": "Header row", "value": "Row 2"} in view["rows"]
    assert [note["title"] for note in view["notes"]] == ["Adjustments I made"]
    # The text still carries every fact on its own, from the shared formatter.
    assert reply.text == _intake_summary_text(session.intake_result)  # type: ignore[arg-type]
    for row in view["rows"]:
        assert row["value"].split(" (")[0].replace("from ", "").strip("'") in reply.text
    for item in view["notes"][0]["items"]:
        assert item in reply.text


def test_a_first_upload_puts_the_welcome_above_the_panel() -> None:
    session = Session()
    pdf = REALWORLD / "fixture_t_halvorsen_fake_eps.pdf"
    reply = handle_upload(session, pdf.read_bytes(), pdf.name, first_visit=True)
    assert reply.view is not None
    _assert_intake_shape(reply.view)
    lead = reply.view["lead"]
    assert isinstance(lead, str) and lead.startswith("Welcome to the Variance Analysis Agent.")
    assert reply.text.startswith(lead)
    assert reply.view["rows"][0]["label"] == "Statement"


def test_earnings_files_get_the_same_panel() -> None:
    session = Session()
    data = (Path(__file__).resolve().parent / "fixtures" / "multi_audience" / "consensus.csv").read_bytes()
    handle_upload(session, data, "consensus.csv", first_visit=False)
    reply = handle_message(session, "Review earnings")
    assert reply.view is not None
    _assert_intake_shape(reply.view)
    rows = {row["label"]: row["value"] for row in reply.view["rows"]}
    assert rows["Compared against"] == "Consensus"
    assert rows["Diluted EPS"] == "Per Share"
    assert "Here's how I read your file:" in reply.text


def test_a_lead_goes_above_the_view_and_before_the_text() -> None:
    view: dict[str, object] = {"kind": "intake", "title": "How I read your file", "lead": "Earlier.",
                               "rows": [{"label": "Header row", "value": "Row 1"}], "notes": [],
                               "question": "Does this look right?"}
    led = with_lead(Response(text="Here's how I read your file:", view=view, level=None), "Switched to worksheet **'B'**.\n\n")
    assert led.text == "Switched to worksheet **'B'**.\n\nHere's how I read your file:"
    assert led.view is not None and led.view["lead"] == "Switched to worksheet **'B'**.\n\nEarlier."
    assert view["lead"] == "Earlier."  # the original view is not changed
    plain = with_lead(Response(text="Body", level="error"), "Lead. ")
    assert plain.text == "Lead. Body" and plain.view is None and plain.level == "error"


def test_switching_sheets_says_so_without_a_glyph() -> None:
    from tests.chat_helpers import analysed
    from tests.test_chat_correctness import _workbook
    session = analysed(_workbook({"Alpha": 1100, "Beta": 1200}), "w.xlsx")
    reply = handle_message(session, "sheet Beta")
    assert reply.text.startswith("Switched to worksheet **'Beta'**")


def _view_strings(view: object) -> list[str]:
    if isinstance(view, str):
        return [view]
    if isinstance(view, dict):
        return [s for value in view.values() for s in _view_strings(value)]
    if isinstance(view, list):
        return [s for value in view for s in _view_strings(value)]
    return []


INTAKE_FIXTURES = sorted(p.name for p in REALWORLD.iterdir()
                         if p.suffix in {".csv", ".xlsx", ".pdf", ".txt"} and p.name.startswith("fixture_"))


@pytest.mark.parametrize("name", INTAKE_FIXTURES)
def test_every_intake_reply_is_plain_language(name: str) -> None:
    """Phase 3's exit check: the first reply to each real-world file, text and panel, has no jargon."""
    session = Session()
    reply = handle_upload(session, (REALWORLD / name).read_bytes(), name, first_visit=True)
    replies = [reply]
    if session.phase.value == "awaiting_blank_budget_confirmation":
        replies.append(handle_message(session, "Treat blank budgets as 0 (unbudgeted)"))
    for each in replies:
        assert_plain_language(each.text)
        for text in _view_strings(each.view):
            assert_plain_language(text)
        assert banned_glyphs(each.text) == [], (name, banned_glyphs(each.text))
