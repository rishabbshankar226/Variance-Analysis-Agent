"""Interactive Web UI Server for Deterministic Conditioning Visualizer."""

from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import sys
from pathlib import Path

from deterministic_conditioning.router import DynamicPromptRouter


class VisualizerRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the visualizer HTML dashboard and lightweight JSON API routes."""

    UI_DIR = Path(__file__).parent

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, directory=str(self.UI_DIR), **kwargs)

    def do_POST(self) -> None:
        if self.path == "/api/route":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body) if body else {}

            prompt = data.get("prompt", "")
            history = data.get("history", [])

            router = DynamicPromptRouter()
            decision = router.route(prompt, history)

            response = {
                "rule_id": decision.rule_id,
                "rule_name": decision.rule_name,
                "required_pos": decision.required_first_token_pos,
                "pos_examples": decision.pos_examples,
                "inversions": decision.inversion_constraints,
                "structure": decision.structural_archetype,
                "compiled_prompt": decision.compiled_system_instruction,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
        else:
            self.send_error(404, "Endpoint not found")

    def log_message(self, format: str, *args: object) -> None:
        # Keep terminal output clean
        sys.stderr.write(f"[UI Server] {self.address_string()} - {format % args}\n")


def run_server(port: int = 8050) -> None:
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), VisualizerRequestHandler) as httpd:
        print("\n=================================================================")
        print("    DETERMINISTIC CONDITIONING VISUALIZER DASHBOARD RUNNING      ")
        print("=================================================================")
        print(f"  URL: http://localhost:{port}")
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
