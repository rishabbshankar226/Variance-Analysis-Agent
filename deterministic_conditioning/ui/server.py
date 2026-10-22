"""Local web server for the deterministic conditioning visualizer.

The page and its one JSON route run on the loopback interface only, serve nothing but
``index.html`` and make no requests to other hosts.
"""

from __future__ import annotations

import argparse
import http.server
import json
import sys
from pathlib import Path

from deterministic_conditioning.router import DynamicPromptRouter

MAX_BODY_BYTES = 64 * 1024
MAX_TEXT_CHARS = 8_000
MAX_HISTORY_TURNS = 50
INDEX_PATHS = frozenset({"/", "/index.html"})
# The page keeps its script and styles inline; everything else must come from this origin.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class RequestError(Exception):
    """A request the visualizer refuses, with the HTTP status to answer it with."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _text_field(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise RequestError(400, f"{name} must be a string")
    if len(value) > MAX_TEXT_CHARS:
        raise RequestError(400, f"{name} is longer than {MAX_TEXT_CHARS} characters")
    return value


def _history(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise RequestError(400, "history must be a list")
    if len(value) > MAX_HISTORY_TURNS:
        raise RequestError(400, f"history has more than {MAX_HISTORY_TURNS} turns")
    turns: list[dict[str, str]] = []
    for turn in value:
        if not isinstance(turn, dict):
            raise RequestError(400, "each history turn must be an object")
        turns.append({"role": _text_field(turn.get("role"), "history role"),
                      "content": _text_field(turn.get("content"), "history content")})
    return turns


class VisualizerRequestHandler(http.server.BaseHTTPRequestHandler):
    """Serves the visualizer page and the ``/api/route`` JSON route."""

    UI_DIR = Path(__file__).parent
    server_version = "ConditioningVisualizer"
    timeout = 10  # a client that stalls mid-request must not hold its thread forever

    def _send(self, status: int, content_type: str, body: bytes, head_only: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        self._send(status, "application/json", json.dumps(payload).encode("utf-8"))

    def _serve_page(self, head_only: bool) -> None:
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        if path not in INDEX_PATHS:
            self._send_json(404, {"error": "Not found"})
            return
        page = (self.UI_DIR / "index.html").read_bytes()
        self._send(200, "text/html; charset=utf-8", page, head_only=head_only)

    def do_GET(self) -> None:
        self._serve_page(head_only=False)

    def do_HEAD(self) -> None:
        self._serve_page(head_only=True)

    def _read_json_object(self) -> dict[str, object]:
        declared = self.headers.get("Content-Length", "")
        if not (declared.isascii() and declared.isdigit()):
            raise RequestError(400, "Content-Length must be a non-negative integer")
        length = int(declared)
        if length > MAX_BODY_BYTES:
            raise RequestError(413, f"Request body is larger than {MAX_BODY_BYTES} bytes")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise RequestError(400, "Request body must be UTF-8 JSON") from None
        if not isinstance(data, dict):
            raise RequestError(400, "Request body must be a JSON object")
        return data

    def do_POST(self) -> None:
        if self.path != "/api/route":
            self._send_json(404, {"error": "Endpoint not found"})
            return
        try:
            data = self._read_json_object()
            prompt = _text_field(data.get("prompt", ""), "prompt")
            history = _history(data.get("history", []))
        except RequestError as error:
            self._send_json(error.status, {"error": str(error)})
            return

        router = DynamicPromptRouter()
        decision = router.route(prompt, history)
        signals = router.extract_signals(prompt)
        self._send_json(200, {
            "rule_id": decision.rule_id,
            "rule_name": decision.rule_name,
            "required_pos": decision.required_first_token_pos,
            "pos_examples": decision.pos_examples,
            "inversions": decision.inversion_constraints,
            "structure": decision.structural_archetype,
            "compiled_prompt": decision.compiled_system_instruction,
            "signals": {
                "word_count": signals.word_count,
                "has_question": signals.has_question,
                "has_frustration": signals.has_frustration,
                "has_technical_terms": signals.has_technical_terms,
            },
        })

    def log_message(self, format: str, *args: object) -> None:
        # Keep terminal output clean
        sys.stderr.write(f"[UI Server] {self.address_string()} - {format % args}\n")


def make_server(port: int = 8050, host: str = "127.0.0.1") -> http.server.ThreadingHTTPServer:
    """Bind the visualizer without serving; port 0 picks a free port."""
    return http.server.ThreadingHTTPServer((host, port), VisualizerRequestHandler)


def run_server(port: int = 8050, host: str = "127.0.0.1") -> None:
    with make_server(port, host) as httpd:
        print("\n=================================================================")
        print("    DETERMINISTIC CONDITIONING VISUALIZER DASHBOARD RUNNING      ")
        print("=================================================================")
        print(f"  URL: http://{host}:{httpd.server_address[1]}")
        print("  Press Ctrl+C to terminate.")
        print("=================================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down visualizer server.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic LLM Visualizer Server.")
    parser.add_argument("--port", type=int, default=8050, help="HTTP server port.")
    args = parser.parse_args()
    run_server(port=args.port)


if __name__ == "__main__":
    main()
