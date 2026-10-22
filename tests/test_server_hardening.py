"""Transport-level hardening of the chat server: uploads, cross-origin requests, failures.

Every test talks to a real loopback `HTTPServer`, the same way a browser would, so the
behaviour asserted here is what a visitor (or a hostile web page) actually gets.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection, HTTPResponse
from http.server import HTTPServer
from typing import Any

import pytest

from variance_agent.chat import server as server_module
from variance_agent.chat.server import _ChatHandler
from variance_agent.chat.session import Phase, Session

CSV = b"Line Item,Budget,Actual\nSales,100,120\nRent,50,70\n"
BOUNDARY = "XBOUNDARY"


@pytest.fixture
def httpd() -> Iterator[HTTPServer]:
    _ChatHandler.session = Session()
    _ChatHandler.initial_response = None
    server_module._downloads.clear()
    server = HTTPServer(("127.0.0.1", 0), _ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    server_module._downloads.clear()


def _request(
    server: HTTPServer,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[HTTPResponse, bytes]:
    conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response, response.read()
    finally:
        conn.close()


def _multipart(
    filename_header: bytes,
    content: bytes = CSV,
    extra_parts: bytes = b"",
) -> tuple[bytes, dict[str, str]]:
    """A multipart/form-data body shaped like the one a browser's FormData produces."""
    body = (
        f"--{BOUNDARY}\r\n".encode()
        + b'Content-Disposition: form-data; name="file"; '
        + filename_header
        + b"\r\nContent-Type: text/csv\r\n\r\n"
        + content
        + b"\r\n"
        + extra_parts
        + f"--{BOUNDARY}--\r\n".encode()
    )
    return body, {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}


def _upload(server: HTTPServer, filename_header: bytes) -> tuple[int, dict[str, Any]]:
    body, headers = _multipart(filename_header)
    response, data = _request(server, "POST", "/upload", body, headers)
    return response.status, json.loads(data)


# ---------------------------------------------------------------------------
# Upload filename handling
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "filename_header",
    [
        'filename="Café.csv"'.encode(),  # raw UTF-8, what browsers send
        'filename="預算.csv"'.encode(),
        b"filename*=UTF-8''Caf%C3%A9.csv",  # RFC 2231 form
        b'filename="plain.csv"',
    ],
)
def test_upload_accepts_non_ascii_and_encoded_filenames(
    httpd: HTTPServer, filename_header: bytes
) -> None:
    status, data = _upload(httpd, filename_header)
    assert status == 200, data
    assert "error" not in data
    assert _ChatHandler.session.phase is not Phase.AWAITING_FILE


def test_upload_reports_the_decoded_filename(httpd: HTTPServer) -> None:
    status, _ = _upload(httpd, 'filename="預算.csv"'.encode())
    assert status == 200
    assert _ChatHandler.session.source_name == "預算.csv"


def test_upload_keeps_only_the_last_path_component(httpd: HTTPServer) -> None:
    status, _ = _upload(httpd, b'filename="C:\\Users\\me\\..\\evil/budget.csv"')
    assert status == 200
    assert _ChatHandler.session.source_name == "budget.csv"


def test_upload_keeps_backslashes_a_browser_sends_unescaped(httpd: HTTPServer) -> None:
    # Browsers escape only the quote, CR and LF in a multipart filename, never the backslash.
    status, _ = _upload(httpd, b'filename="C:\\Users\\Finance\\custom_variance.csv"')
    assert status == 200
    assert _ChatHandler.session.source_name == "custom_variance.csv"


def test_upload_filename_may_contain_a_semicolon(httpd: HTTPServer) -> None:
    status, _ = _upload(httpd, b'filename="q3;final.csv"')
    assert status == 200
    assert _ChatHandler.session.source_name == "q3;final.csv"


def test_upload_accepts_bare_lf_line_endings(httpd: HTTPServer) -> None:
    body = (
        f'--{BOUNDARY}\nContent-Disposition: form-data; name="file"; filename="lf.csv"\n'
        f"Content-Type: text/csv\n\n".encode() + CSV + f"\n--{BOUNDARY}--\n".encode()
    )
    response, data = _request(
        httpd, "POST", "/upload", body,
        {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
    )
    assert response.status == 200, data
    assert _ChatHandler.session.source_name == "lf.csv"


def test_upload_without_a_boundary_is_a_400(httpd: HTTPServer) -> None:
    response, data = _request(
        httpd, "POST", "/upload", b"whatever", {"Content-Type": "multipart/form-data"}
    )
    assert response.status == 400
    assert "error" in json.loads(data)


def test_upload_rejects_a_flood_of_multipart_parts(httpd: HTTPServer) -> None:
    flood = b"".join(
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="p{i}"\r\n\r\n\r\n'.encode()
        for i in range(50)
    )
    body, headers = _multipart(b'filename="a.csv"', extra_parts=flood)
    response, data = _request(httpd, "POST", "/upload", body, headers)
    assert response.status == 400
    assert "too many" in json.loads(data)["error"].lower()
    assert _ChatHandler.session.phase is Phase.AWAITING_FILE
