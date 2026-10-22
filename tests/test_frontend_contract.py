"""The page the chat server serves: where it lives, how it is served and what it may do.

Static checks pin the packaging and security contract; the Node-driven checks at the bottom run
the real `chat.js` helpers (skipped when Node is not installed).
"""

from __future__ import annotations

import importlib.resources
import threading
from collections.abc import Iterator
from http.client import HTTPConnection, HTTPResponse
from http.server import HTTPServer
from pathlib import Path

import pytest

from variance_agent.chat import server as server_module
from variance_agent.chat.server import _ChatHandler
from variance_agent.chat.session import Session

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_STATIC = ROOT / "src" / "variance_agent" / "static"


@pytest.fixture
def httpd() -> Iterator[HTTPServer]:
    _ChatHandler.session = Session()
    _ChatHandler.initial_response = None
    server = HTTPServer(("127.0.0.1", 0), _ChatHandler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _get(server: HTTPServer, path: str) -> tuple[HTTPResponse, bytes]:
    conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        conn.request("GET", path)
        response = conn.getresponse()
        return response, response.read()
    finally:
        conn.close()


def _packaged(name: str) -> bytes:
    return importlib.resources.files("variance_agent").joinpath("static", name).read_bytes()


# ---------------------------------------------------------------------------
# One copy of the page, served from inside the package
# ---------------------------------------------------------------------------

def test_there_is_a_single_copy_of_the_page() -> None:
    # A second copy at the repository root resolved outside the package in an installed wheel.
    assert not (ROOT / "static").exists()


def test_the_server_serves_the_packaged_page(httpd: HTTPServer) -> None:
    for path in ("/", "/index.html", "/chat.html"):
        response, body = _get(httpd, path)
        assert response.status == 200
        assert response.getheader("Content-Type") == "text/html; charset=utf-8"
        assert body == _packaged("chat.html")


def test_the_server_module_does_not_look_outside_the_package() -> None:
    assert not hasattr(server_module, "_STATIC_DIR")
