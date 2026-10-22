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
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
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


def test_hosted_server_accepts_the_proxys_forwarded_host(hosted_httpd: HTTPServer) -> None:
    # If the platform's proxy rewrote Host to an internal name, the public name still arrives in
    # X-Forwarded-Host; a web page cannot add that header (it would need a CORS preflight).
    headers = {"Host": "10.1.2.3:10000", "X-Forwarded-Host": "chat.onrender.com"}
    status, _ = _post_message(hosted_httpd, {**headers, "Origin": "https://chat.onrender.com"})
    assert status == 200
    status, _ = _post_message(hosted_httpd, {**headers, "Origin": "https://evil.example"})
    assert status == 403
    status, _ = _post_message(
        hosted_httpd, {"Host": "10.1.2.3:10000", "Origin": "https://chat.onrender.com"}
    )
    assert status == 403


def test_hosted_server_accepts_the_platforms_external_hostname(
    hosted_httpd: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Render documents RENDER_EXTERNAL_HOSTNAME (e.g. myapp.onrender.com) for web services.
    monkeypatch.setattr(_ChatHandler, "public_hosts", frozenset({"chat.onrender.com"}))
    internal = {"Host": "10.1.2.3:10000"}
    status, _ = _post_message(hosted_httpd, {**internal, "Origin": "https://chat.onrender.com"})
    assert status == 200
    status, _ = _post_message(hosted_httpd, {**internal, "Origin": "https://evil.example"})
    assert status == 403


def test_run_chat_server_reads_the_external_hostname_only_when_hosted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(HTTPServer, "serve_forever", lambda self: None)
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "Chat.OnRender.com")
    try:
        server_module.run_chat_server(host="0.0.0.0", port=0, open_browser=False, hosted=True)
        assert _ChatHandler.public_hosts == frozenset({"chat.onrender.com"})
        server_module.run_chat_server(host="127.0.0.1", port=0, open_browser=False)
        assert _ChatHandler.public_hosts == frozenset()
    finally:
        _ChatHandler.hosted = False
        _ChatHandler.public_hosts = frozenset()
        _ChatHandler.local_hosts = server_module._LOOPBACK_HOSTS


def test_local_server_ignores_a_forwarded_host(httpd: HTTPServer) -> None:
    status, _ = _post_message(
        httpd, {"X-Forwarded-Host": "evil.example", "Origin": "http://evil.example"}
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


# ---------------------------------------------------------------------------
# A handler failure is an answer, not a dropped connection
# ---------------------------------------------------------------------------

def test_a_failing_message_handler_gets_a_json_500_and_a_stderr_traceback(
    httpd: HTTPServer, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("kaboom-secret")

    monkeypatch.setattr(server_module, "handle_message", explode)
    response, data = _request(httpd, "POST", "/message", b'{"text": "help"}',
                              {"Content-Type": "application/json"})
    assert response.status == 500
    payload = json.loads(data)
    assert payload["error"]
    assert "kaboom-secret" not in payload["error"]  # details go to the log, not the visitor
    assert "kaboom-secret" in capsys.readouterr().err


def test_a_failing_upload_handler_gets_a_json_500(
    httpd: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: object, **kwargs: object) -> object:
        raise ValueError("bad internals")

    monkeypatch.setattr(server_module, "handle_upload", explode)
    body, headers = _multipart(b'filename="a.csv"')
    response, data = _request(httpd, "POST", "/upload", body, headers)
    assert response.status == 500
    assert "error" in json.loads(data)


def test_a_failing_get_gets_a_json_500(httpd: HTTPServer) -> None:
    class BrokenSession:
        @property
        def phase(self) -> Phase:
            raise RuntimeError("no phase")

    _ChatHandler.session = BrokenSession()  # type: ignore[assignment]
    response, data = _request(httpd, "GET", "/status")
    assert response.status == 500
    assert "error" in json.loads(data)


def test_the_server_keeps_serving_after_a_handler_failure(
    httpd: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = server_module.handle_message
    calls = {"n": 0}

    def flaky(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first call fails")
        return real(*args, **kwargs)

    monkeypatch.setattr(server_module, "handle_message", flaky)
    assert _post_message(httpd, {})[0] == 500
    assert _post_message(httpd, {})[0] == 200


def test_a_lone_surrogate_in_a_reply_does_not_crash_serialisation(
    httpd: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    from variance_agent.chat.responses import Response

    monkeypatch.setattr(
        server_module, "handle_message", lambda *a, **k: Response(text="odd \ud800 text")
    )
    response, data = _request(httpd, "POST", "/message", b'{"text": "help"}',
                              {"Content-Type": "application/json"})
    assert response.status == 200
    assert json.loads(data)["text"] == "odd \ud800 text"
    data.decode("ascii")  # escaped on the wire, so the reply is plain ASCII


# ---------------------------------------------------------------------------
# Staged downloads
# ---------------------------------------------------------------------------

def _stub_download(monkeypatch: pytest.MonkeyPatch, files: dict[str, str | bytes]) -> None:
    from variance_agent.chat.responses import Response

    monkeypatch.setattr(
        server_module, "handle_message", lambda *a, **k: Response(text="ok", download=files)
    )


@pytest.mark.parametrize("filename", ["memo q3 #2 ?.md", "a%20b.md", "q3/2026.md", "r&d=1;x.md"])
def test_download_url_round_trips_awkward_filenames(
    httpd: HTTPServer, monkeypatch: pytest.MonkeyPatch, filename: str
) -> None:
    _stub_download(monkeypatch, {filename: "body text"})
    status, data = _post_message(httpd, {})
    assert status == 200
    assert data["download_filename"] == filename
    assert "#" not in data["download_url"] and "?" not in data["download_url"]
    response, content = _request(httpd, "GET", data["download_url"])
    assert response.status == 200
    assert content == b"body text"


def test_reset_discards_staged_downloads(httpd: HTTPServer) -> None:
    _ChatHandler.session.phase = Phase.EXPLORING
    server_module._downloads["executive_memo_q3_2026.md"] = "confidential memo"
    status, data = _post_message(httpd, {}, b'{"text": "reset"}')
    assert status == 200 and data["phase"] == Phase.AWAITING_FILE
    response, _ = _request(httpd, "GET", "/download/executive_memo_q3_2026.md")
    assert response.status == 404
    assert not server_module._downloads


def test_a_new_upload_discards_downloads_of_the_previous_file(httpd: HTTPServer) -> None:
    server_module._downloads["variance_report_old.md"] = "old report"
    status, _ = _upload(httpd, b'filename="new.csv"')
    assert status == 200
    assert "variance_report_old.md" not in server_module._downloads


def test_other_messages_keep_staged_downloads(httpd: HTTPServer) -> None:
    _ChatHandler.session.phase = Phase.EXPLORING
    server_module._downloads["report.md"] = "report"
    _post_message(httpd, {}, b'{"text": "help"}')
    assert "report.md" in server_module._downloads


def test_staged_downloads_are_bounded_in_count_and_oldest_go_first(
    httpd: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = {"n": 0}
    from variance_agent.chat.responses import Response

    def stage(*args: object, **kwargs: object) -> Response:
        counter["n"] += 1
        return Response(text="ok", download={f"export_{counter['n']}.md": "x"})

    monkeypatch.setattr(server_module, "handle_message", stage)
    for _ in range(server_module._MAX_STAGED_DOWNLOADS + 5):
        _post_message(httpd, {})
    names = list(server_module._downloads)
    assert len(names) == server_module._MAX_STAGED_DOWNLOADS
    assert names[-1] == f"export_{server_module._MAX_STAGED_DOWNLOADS + 5}.md"
    assert "export_1.md" not in names


def test_staged_downloads_are_bounded_in_bytes_but_keep_the_newest(
    httpd: HTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server_module, "_MAX_STAGED_BYTES", 1000)
    for name in ("a.md", "b.md", "c.md"):
        _stub_download(monkeypatch, {name: "x" * 600})
        _post_message(httpd, {})
    assert list(server_module._downloads) == ["c.md"]
    _stub_download(monkeypatch, {"huge.md": "x" * 5000})
    _post_message(httpd, {})
    assert list(server_module._downloads) == ["huge.md"]


# ---------------------------------------------------------------------------
# Content-Length strictness and response headers
# ---------------------------------------------------------------------------

def _raw_post(server: HTTPServer, content_length: str, body: bytes = b"") -> bytes:
    import socket

    request = (
        b"POST /message HTTP/1.1\r\nHost: " + _host(server).encode() + b"\r\n"
        b"Content-Type: application/json\r\nContent-Length: " + content_length.encode()
        + b"\r\n\r\n" + body
    )
    with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=10) as sock:
        sock.sendall(request)
        return sock.recv(400)


@pytest.mark.parametrize("value", ["+16", "1_6", "0x10", "16.0", "١٦", "-16", "1e1", ""])
def test_content_length_must_be_plain_ascii_digits(httpd: HTTPServer, value: str) -> None:
    # int() would accept several of these as 16, the real length of this body.
    body = b'{"text": "help"}'
    assert len(body) == 16
    reply = _raw_post(httpd, value, body)
    assert b" 400 " in reply.split(b"\r\n", 1)[0], reply


def test_a_plain_content_length_is_still_accepted(httpd: HTTPServer) -> None:
    body = b'{"text": "help"}'
    assert b" 200 " in _raw_post(httpd, str(len(body)), body).split(b"\r\n", 1)[0]


@pytest.mark.parametrize("path", ["/status", "/favicon.ico", "/download/none.md", "/nope"])
def test_every_reply_forbids_content_sniffing_and_referrers(httpd: HTTPServer, path: str) -> None:
    response, _ = _request(httpd, "GET", path)
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Referrer-Policy") == "no-referrer"


def test_api_replies_are_not_cacheable(httpd: HTTPServer) -> None:
    response, _ = _request(httpd, "GET", "/status")
    assert response.getheader("Cache-Control") == "no-store"
    response, _ = _request(httpd, "POST", "/message", b'{"text": "help"}',
                           {"Content-Type": "application/json"})
    assert response.getheader("Cache-Control") == "no-store"


def test_downloads_are_not_cacheable_and_not_sniffed(httpd: HTTPServer) -> None:
    server_module._downloads["report.md"] = "# private"
    response, body = _request(httpd, "GET", "/download/report.md")
    assert response.status == 200 and body == b"# private"
    assert response.getheader("Cache-Control") == "no-store"
    assert response.getheader("X-Content-Type-Options") == "nosniff"
