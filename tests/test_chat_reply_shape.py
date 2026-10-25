"""The JSON shape of a chat reply: the fields the page reads, and the error level that styles a refusal.

A refusal used to be marked by a warning sign at the start of its text. It now carries `level`
("error") through /message, /upload and /status, and the text starts with the sentence itself.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.client import HTTPConnection
from typing import Any

from tests.chat_helpers import SAMPLE_CSV
from tests.test_chat import _post_upload, chat_server_url  # noqa: F401  (chat_server_url is a fixture)
from variance_agent.chat.responses import Response
from variance_agent.chat.server import _ChatHandler

REPLY_KEYS = {"text", "phase", "table", "chips", "level", "download_url", "download_filename"}
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
                                          "table": None, "level": "error"}


def test_sample_upload_still_reads_as_before(chat_server_url: str) -> None:  # noqa: F811
    reply = _upload(chat_server_url, "sample.csv", SAMPLE_CSV)
    assert "level" not in reply and reply["phase"] == "awaiting_period"
