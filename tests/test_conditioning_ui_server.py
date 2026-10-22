"""The conditioning visualizer is a local, offline, read-only tool: keep it that way."""

from __future__ import annotations

import http.client
import json
import re
import socket
import threading
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path

import pytest

from deterministic_conditioning.ui import server as ui

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "deterministic_conditioning" / "ui" / "index.html"


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[HTTPServer]:
    monkeypatch.setattr(ui.VisualizerRequestHandler, "log_message", lambda *args, **kwargs: None)
    httpd = ui.make_server(port=0)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def connect(httpd: HTTPServer) -> http.client.HTTPConnection:
    return http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=5)


def get(httpd: HTTPServer, path: str, method: str = "GET") -> http.client.HTTPResponse:
    conn = connect(httpd)
    conn.request(method, path)
    return conn.getresponse()


def post(httpd: HTTPServer, body: bytes | str, path: str = "/api/route",
         content_length: str | None = None) -> tuple[int, dict[str, object]]:
    payload = body.encode() if isinstance(body, str) else body
    conn = connect(httpd)
    conn.putrequest("POST", path)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", content_length if content_length is not None else str(len(payload)))
    conn.endheaders(payload if content_length is None else b"")
    response = conn.getresponse()
    raw = response.read()
    data: dict[str, object] = json.loads(raw) if raw.startswith(b"{") else {}
    return response.status, data


def test_server_binds_loopback_only_by_default(server: HTTPServer) -> None:
    assert server.server_address[0] == "127.0.0.1"
    assert ui.run_server.__defaults__ is not None and "127.0.0.1" in ui.run_server.__defaults__


def test_index_is_served_at_root_and_index_html(server: HTTPServer) -> None:
    for path in ("/", "/index.html", "/index.html?cache=bust"):
        response = get(server, path)
        body = response.read().decode()
        assert response.status == 200, path
        assert response.getheader("Content-Type", "").startswith("text/html"), path
        assert "Deterministic LLM Conditioning" in body, path
        assert response.getheader("X-Content-Type-Options") == "nosniff"
    head = get(server, "/", method="HEAD")
    assert head.status == 200 and head.read() == b""


@pytest.mark.parametrize("path", [
    "/__main__.py",
    "/__init__.py",
    "/__pycache__/",
    "/__pycache__",
    "/__pycache__/__main__.cpython-311.pyc",
    "/../router.py",
    "/%2e%2e/router.py",
    "/index.html/../__main__.py",
    "/missing.html",
    "/api/route",
])
def test_nothing_but_the_page_is_served(server: HTTPServer, path: str) -> None:
    for method in ("GET", "HEAD"):
        response = get(server, path, method=method)
        body = response.read()
        assert response.status == 404, (method, path, response.status)
        assert b"import " not in body and b"DynamicPromptRouter" not in body


def test_route_endpoint_returns_the_routing_decision(server: HTTPServer) -> None:
    status, data = post(server, json.dumps({"prompt": "THE SERVER KEEPS CRASHING NOW", "history": []}))
    assert status == 200
    assert data["rule_id"] == "R1"
    signals = data["signals"]
    assert isinstance(signals, dict) and signals["has_frustration"] is True


def test_route_endpoint_accepts_a_prompt_only_body(server: HTTPServer) -> None:
    status, data = post(server, json.dumps({"prompt": "hey what's up"}))
    assert status == 200 and data["rule_id"] == "R2"


def test_route_endpoint_uses_history_for_state_inversion(server: HTTPServer) -> None:
    history = [{"role": "user", "content": "How do cookies work?"},
               {"role": "assistant", "content": "Check your browser headers first. They are cheap."}]
    status, data = post(server, json.dumps({"prompt": "Can we read them with JS?", "history": history}))
    assert status == 200
    assert any("FORBID opener" in str(item) for item in data["inversions"])  # type: ignore[attr-defined]


@pytest.mark.parametrize("length", ["abc", "-5", "1e3", "", " 12 x", "0x10", "²"])  # "²".isdigit() is True
def test_unparseable_content_length_is_a_400(server: HTTPServer, length: str) -> None:
    status, data = post(server, b"", content_length=length)
    assert status == 400 and "Content-Length" in str(data["error"])


def test_oversized_declared_body_is_a_413_without_reading_it(server: HTTPServer) -> None:
    status, data = post(server, b"", content_length=str(200 * 1024 * 1024))
    assert status == 413 and "error" in data


@pytest.mark.parametrize("body", [
    b"",
    b"{not json",
    b"\xff\xfe\x00",
    b"[1, 2]",
    b'"text"',
    b"null",
    b"[" * 60000,  # raises RecursionError, not JSONDecodeError
])
def test_malformed_json_is_a_400(server: HTTPServer, body: bytes) -> None:
    status, data = post(server, body)
    assert status == 400 and "error" in data


@pytest.mark.parametrize("payload", [
    {"prompt": 5},
    {"prompt": None},
    {"prompt": "x" * 20000},
    {"prompt": "ok", "history": "not a list"},
    {"prompt": "ok", "history": [1, 2]},
    {"prompt": "ok", "history": [{"role": "assistant", "content": 7}]},
    {"prompt": "ok", "history": [{"role": 3, "content": "text"}]},
    {"prompt": "ok", "history": [{"role": "assistant"}]},
    {"prompt": "ok", "history": [{"role": "assistant", "content": "y" * 20000}]},
    {"prompt": "ok", "history": [{"role": "user", "content": "hi"}] * 500},
])
def test_invalid_fields_are_a_400_not_a_dropped_connection(server: HTTPServer, payload: dict[str, object]) -> None:
    status, data = post(server, json.dumps(payload))
    assert status == 400 and "error" in data, payload


def test_the_server_keeps_answering_after_bad_requests(server: HTTPServer) -> None:
    for body in (b"{bad", b'{"prompt": 5}', b"[" * 60000):
        post(server, body)
    status, data = post(server, json.dumps({"prompt": "What is Raft consensus?"}))
    assert status == 200 and data["rule_id"] == "R3"


def test_unknown_post_path_is_a_404(server: HTTPServer) -> None:
    status, _ = post(server, "{}", path="/api/other")
    assert status == 404


def test_a_stalled_client_does_not_block_other_requests(server: HTTPServer) -> None:
    stalled = socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=5)
    try:
        stalled.sendall(b"POST /api/route HTTP/1.1\r\nContent-Length: 100\r\n\r\n{")
        response = get(server, "/")
        assert response.status == 200
    finally:
        stalled.close()


def test_page_makes_no_requests_to_other_hosts() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in html and "fonts.gstatic.com" not in html
    assert not re.findall(r"(?:src|href)\s*=\s*[\"']https?://", html)
    assert not re.findall(r"url\(\s*[\"']?https?://", html)
    assert "@import" not in html
    assert "fetch('/api/route'" in html


def test_page_restricts_itself_to_its_own_origin(server: HTTPServer) -> None:
    csp = get(server, "/").getheader("Content-Security-Policy", "")
    assert "default-src 'self'" in csp and "connect-src 'self'" in csp
    assert "http:" not in csp and "https:" not in csp
