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


# ---------------------------------------------------------------------------
# Cross-origin requests and DNS rebinding
# ---------------------------------------------------------------------------

def _host(server: HTTPServer) -> str:
    return f"127.0.0.1:{server.server_address[1]}"


def _post_message(
    server: HTTPServer, extra_headers: dict[str, str], body: bytes = b'{"text": "help"}'
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json", **extra_headers}
    response, data = _request(server, "POST", "/message", body, headers)
    return response.status, json.loads(data)


@pytest.fixture
def hosted_httpd(httpd: HTTPServer) -> Iterator[HTTPServer]:
    _ChatHandler.hosted = True
    yield httpd
    _ChatHandler.hosted = False


def test_no_cors_header_is_sent(httpd: HTTPServer) -> None:
    response, _ = _request(httpd, "GET", "/status")
    assert response.getheader("Access-Control-Allow-Origin") is None
    response, _ = _request(httpd, "POST", "/message", b'{"text": "help"}',
                           {"Content-Type": "application/json"})
    assert response.getheader("Access-Control-Allow-Origin") is None


def test_cross_origin_json_post_is_refused_and_has_no_effect(httpd: HTTPServer) -> None:
    status, data = _post_message(httpd, {"Origin": "http://evil.example"})
    assert status == 403
    assert "error" in data and "text" not in data


def test_cross_origin_text_plain_csrf_post_is_refused(httpd: HTTPServer) -> None:
    # The classic "simple request": no preflight, so the server itself has to say no.
    response, data = _request(
        httpd, "POST", "/message", b'{"text": "reset"}',
        {"Content-Type": "text/plain", "Origin": "http://evil.example"},
    )
    assert response.status == 403, data


def test_cross_origin_upload_is_refused_and_has_no_effect(httpd: HTTPServer) -> None:
    body, headers = _multipart(b'filename="a.csv"')
    response, _ = _request(httpd, "POST", "/upload", body,
                           {**headers, "Origin": "http://evil.example"})
    assert response.status == 403
    assert _ChatHandler.session.phase is Phase.AWAITING_FILE


def test_other_local_port_is_a_different_origin(httpd: HTTPServer) -> None:
    status, _ = _post_message(httpd, {"Origin": "http://127.0.0.1:1"})
    assert status == 403


def test_opaque_null_origin_is_refused(httpd: HTTPServer) -> None:
    status, _ = _post_message(httpd, {"Origin": "null"})
    assert status == 403


def test_same_origin_post_is_accepted(httpd: HTTPServer) -> None:
    status, data = _post_message(httpd, {"Origin": f"http://{_host(httpd)}"})
    assert status == 200, data
    assert "text" in data


def test_post_without_origin_is_accepted(httpd: HTTPServer) -> None:
    status, data = _post_message(httpd, {})
    assert status == 200, data


@pytest.mark.parametrize("path", ["/status", "/", "/download/anything.md"])
def test_local_server_refuses_a_rebound_hostname(httpd: HTTPServer, path: str) -> None:
    # DNS rebinding: evil.example resolves to 127.0.0.1, so the page is "same origin" with it.
    response, _ = _request(httpd, "GET", path, headers={"Host": "evil.example"})
    assert response.status == 403


def test_local_server_refuses_a_rebound_hostname_on_post(httpd: HTTPServer) -> None:
    status, _ = _post_message(httpd, {"Host": "evil.example", "Origin": "http://evil.example"})
    assert status == 403


@pytest.mark.parametrize(
    "host", ["localhost", "localhost:8123", "127.0.0.1:8123", "[::1]", "[::1]:8123", "LOCALHOST"]
)
def test_local_server_accepts_loopback_hostnames(httpd: HTTPServer, host: str) -> None:
    response, _ = _request(httpd, "GET", "/status", headers={"Host": host})
    assert response.status == 200


def test_hosted_server_serves_its_public_hostname(hosted_httpd: HTTPServer) -> None:
    response, _ = _request(hosted_httpd, "GET", "/status", headers={"Host": "chat.onrender.com"})
    assert response.status == 200
    status, _ = _post_message(
        hosted_httpd, {"Host": "chat.onrender.com", "Origin": "https://chat.onrender.com"}
    )
    assert status == 200


def test_hosted_server_still_refuses_a_foreign_origin(hosted_httpd: HTTPServer) -> None:
    status, _ = _post_message(
        hosted_httpd, {"Host": "chat.onrender.com", "Origin": "https://evil.example"}
    )
    assert status == 403


def test_hosted_health_check_needs_no_origin_or_known_host(hosted_httpd: HTTPServer) -> None:
    response, data = _request(hosted_httpd, "GET", "/healthz", headers={"Host": "10.1.2.3:10000"})
    assert response.status == 200
    assert json.loads(data)["status"] == "ok"


# ---------------------------------------------------------------------------
# /message content type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", ""])
def test_message_requires_a_json_content_type(httpd: HTTPServer, content_type: str) -> None:
    headers = {"Content-Type": content_type} if content_type else {}
    response, _ = _request(httpd, "POST", "/message", b'{"text": "help"}', headers)
    assert response.status == 415


@pytest.mark.parametrize(
    "content_type", ["application/json", "application/json; charset=utf-8", "Application/JSON"]
)
def test_message_accepts_json_content_types(httpd: HTTPServer, content_type: str) -> None:
    response, _ = _request(httpd, "POST", "/message", b'{"text": "help"}',
                           {"Content-Type": content_type})
    assert response.status == 200


def test_run_chat_server_wires_hosted_mode_and_the_bound_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(HTTPServer, "serve_forever", lambda self: None)
    try:
        assert server_module.run_chat_server(host="127.0.0.1", port=0, open_browser=False) == 0
        assert _ChatHandler.hosted is False
        assert "localhost" in _ChatHandler.local_hosts
        assert server_module.run_chat_server(
            host="0.0.0.0", port=0, open_browser=False, hosted=True
        ) == 0
        assert _ChatHandler.hosted is True
        assert "" not in _ChatHandler.local_hosts and "0.0.0.0" not in _ChatHandler.local_hosts
    finally:
        _ChatHandler.hosted = False
        _ChatHandler.local_hosts = server_module._LOOPBACK_HOSTS
