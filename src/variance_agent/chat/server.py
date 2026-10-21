"""Local HTTP server for the deterministic chatbot.

Uses only the Python standard library (http.server, json, email.parser).
Binds to 127.0.0.1 by default; hosted mode binds the address the platform
provides and disables exports to server paths.
"""

import json
import urllib.parse
import webbrowser
from email.message import Message
from email.parser import BytesParser
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import ClassVar

from .handlers import handle_message, handle_upload
from .responses import Response
from .session import Session


_STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"
_PKG_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Staged downloads keyed by filename
_downloads: dict[str, str] = {}


class _ChatHandler(BaseHTTPRequestHandler):
    """Request handler for the chatbot API."""

    session: ClassVar[Session]
    initial_response: ClassVar[Response | None] = None

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default request logging to keep the terminal clean."""
        pass

    # ------------------------------------------------------------------
    # GET routes
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._serve_static("chat.html", "text/html; charset=utf-8")
        elif self.path == "/status":
            payload: dict[str, object] = {"phase": self.session.phase.value}
            if self.initial_response is not None:
                payload["initial_response"] = {
                    "text": self.initial_response.text,
                    "chips": self.initial_response.chips,
                    "table": self.initial_response.table,
                }
            self._json_response(payload)
        elif self.path.startswith("/download/"):
            raw_filename = self.path[len("/download/"):].split("?")[0]
            filename = urllib.parse.unquote(raw_filename)
            if filename in _downloads:
                content = _downloads[filename].encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self._json_error("File not found.", HTTPStatus.NOT_FOUND)
        else:
            self._json_error("Not found.", HTTPStatus.NOT_FOUND)

    # ------------------------------------------------------------------
    # POST routes
    # ------------------------------------------------------------------

    def do_POST(self) -> None:
        if self.path == "/upload":
            self._handle_upload()
        elif self.path == "/message":
            self._handle_message()
        else:
            self._json_error("Not found.", HTTPStatus.NOT_FOUND)

    def _handle_upload(self) -> None:
        """Parse a multipart/form-data upload and process the file."""
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._json_error("Expected multipart/form-data.", HTTPStatus.BAD_REQUEST)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Parse multipart using email.parser
        header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
        msg = BytesParser().parsebytes(header_bytes + body)

        file_bytes: bytes | None = None
        filename: str | None = None
        sheet: str | None = None

        if msg.is_multipart():
            parts = msg.get_payload()
            if isinstance(parts, list):
                for part in parts:
                    if not isinstance(part, Message):
                        continue
                    disposition = part.get("Content-Disposition", "")
                    if 'name="file"' in disposition:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            file_bytes = payload
                        # Extract filename from Content-Disposition
                        for token in disposition.split(";"):
                            token = token.strip()
                            if token.startswith("filename="):
                                raw_fn = token.split("=", 1)[1].strip('"').strip("'")
                                filename = raw_fn.replace("\\", "/").split("/")[-1]
                    elif 'name="sheet"' in disposition:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            sheet_text = payload.decode("utf-8").strip()
                            if sheet_text:
                                sheet = sheet_text

        if file_bytes is None or filename is None:
            self._json_error(
                "No file found in the upload. Please select a CSV, JSON, XLSX, or XLSM file.",
                HTTPStatus.BAD_REQUEST,
            )
            return

        response = handle_upload(self.session, file_bytes, filename, sheet)
        self._send_response(response)

    def _handle_message(self) -> None:
        """Process a text message through the intent router."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._json_error("Invalid JSON.", HTTPStatus.BAD_REQUEST)
            return

        text = data.get("text", "").strip()
        if not text:
            self._json_error("Empty message.", HTTPStatus.BAD_REQUEST)
            return

        response = handle_message(self.session, text)
        self._send_response(response)

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _send_response(self, response: object) -> None:
        """Serialize a Response dataclass to JSON and send it."""
        from .responses import Response

        assert isinstance(response, Response)

        payload: dict[str, object] = {
            "text": response.text,
            "phase": response.phase or self.session.phase,
        }
        if response.table is not None:
            payload["table"] = response.table
        if response.chips is not None:
            payload["chips"] = response.chips
        if response.download is not None:
            # Stage the download and return a URL
            for filename, content in response.download.items():
                _downloads[filename] = content
                payload["download_url"] = f"/download/{filename}"
                payload["download_filename"] = filename

        self._json_response(payload)

    def _json_response(self, data: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, message: str, status: HTTPStatus) -> None:
        self._json_response({"error": message}, status)

    def _serve_static(self, filename: str, content_type: str) -> None:
        filepath = _STATIC_DIR / filename
        if not filepath.is_file():
            filepath = _PKG_STATIC_DIR / filename
        if not filepath.is_file():
            self._json_error(f"Static file not found: {filename}", HTTPStatus.NOT_FOUND)
            return
        content = filepath.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run_chat_server(
    host: str = "127.0.0.1",
    port: int = 0,
    initial_input: str | None = None,
    initial_sheet: str | None = None,
    open_browser: bool = True,
    hosted: bool = False,
) -> int:
    """Start the chatbot server and open the browser.

    Port 0 lets the OS assign an available port automatically.
    Hosted mode refuses chat commands that write to server-side paths.
    Returns 0 on clean shutdown.
    """
    session = Session(path_exports_enabled=not hosted)
    _ChatHandler.session = session
    _ChatHandler.initial_response = None

    if initial_input is not None:
        input_path = Path(initial_input)
        if input_path.is_file():
            file_bytes = input_path.read_bytes()
            _ChatHandler.initial_response = handle_upload(
                session, file_bytes, input_path.name, initial_sheet
            )

    server = HTTPServer((host, port), _ChatHandler)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}"

    if hosted:
        print(f"Variance Analysis Chatbot listening on port {actual_port} (hosted mode)", flush=True)
    else:
        print(f"Variance Analysis Chatbot running at {url}")
    print("Press Ctrl+C to stop.\n")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()

    return 0
