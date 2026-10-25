"""Local HTTP server for the deterministic chatbot.

Uses only the Python standard library (http.server, json, importlib.resources).
Binds to 127.0.0.1 by default; hosted mode binds the address the platform
provides and disables exports to server paths.
"""

import importlib.resources
import json
import os
import re
import sys
import traceback
import urllib.parse
import webbrowser
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import ClassVar

from variance_agent.limits import MAX_INPUT_BYTES, MAX_TEXT_LENGTH
from variance_agent.xlsx import XLSX_MEDIA_TYPE

from .handlers import handle_message, handle_upload
from .responses import Response
from .session import Phase, Session


# The only files served from the package's static/ directory, by exact name.
_STATIC_TYPES = {
    "chat.html": "text/html; charset=utf-8",
    "chat.js": "text/javascript; charset=utf-8",
    "chat.css": "text/css; charset=utf-8",
    "favicon.svg": "image/svg+xml",
}

# The page loads only its own script and stylesheet: no inline code, no third-party origins, no
# framing, no <base> or plugin tricks. chat.js builds the DOM with createElement/textContent.
_PAGE_CSP = (
    "default-src 'self'; base-uri 'none'; object-src 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)

# Staged downloads keyed by filename, oldest first. They are sensitive (reports, memos) and the
# service is small, so they are bounded and dropped when the analysis they belong to ends.
_downloads: OrderedDict[str, str | bytes] = OrderedDict()
_MAX_STAGED_DOWNLOADS = 16
_MAX_STAGED_BYTES = 48 * 1024 * 1024

_DOWNLOAD_TYPES = {".xlsx": XLSX_MEDIA_TYPE}

# Request bodies beyond these sizes are refused before they are read.
_MAX_UPLOAD_BODY = MAX_INPUT_BYTES + 1024 * 1024  # file plus multipart framing
_MAX_MESSAGE_BODY = 2 * MAX_TEXT_LENGTH
# A real upload has a file plus two small fields; anything near this many parts is hostile.
_MAX_FORM_PARTS = 8

# Names a non-hosted server answers to. A page on another host that rebinds its DNS name to
# 127.0.0.1 reaches the server with its own name in Host, so anything else is refused.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})

_DISPOSITION_PARAM = re.compile(r';\s*([A-Za-z][A-Za-z0-9*-]*)\s*=\s*(?:"([^"]*)"|([^;\s]*))')


@dataclass(frozen=True)
class _FormPart:
    name: str
    filename: str | None
    content: bytes


def _stage_download(filename: str, content: str | bytes) -> None:
    """Keep an export for download, evicting the oldest ones beyond the count and byte caps."""
    _downloads.pop(filename, None)
    _downloads[filename] = content
    while len(_downloads) > 1 and (
        len(_downloads) > _MAX_STAGED_DOWNLOADS
        or sum(len(staged) for staged in _downloads.values()) > _MAX_STAGED_BYTES
    ):
        _downloads.popitem(last=False)


def _hostname(host_header: str) -> str:
    """The lower-cased host of a Host header, without its port (IPv6 literals keep brackets)."""
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[: host.find("]") + 1] if "]" in host else host
    return host.partition(":")[0]


def _boundary_of(content_type: str) -> bytes | None:
    header = Message()
    header["Content-Type"] = content_type
    boundary = header.get_param("boundary")
    if not isinstance(boundary, str) or not boundary or len(boundary) > 200:
        return None
    return boundary.encode("utf-8")


def _disposition_params(header_block: bytes) -> dict[str, str]:
    """The Content-Disposition parameters of one part, read the way browsers write them.

    A browser escapes only '"', CR and LF in a multipart filename (as %22, %0D, %0A) and leaves
    backslashes alone, so quoted values are taken literally rather than with e-mail unescaping.
    """
    text = header_block.decode("utf-8", errors="replace")
    params: dict[str, str] = {}
    for line in text.split("\n"):  # not splitlines(): U+2028 and friends may sit in a filename
        field, _, value = line.partition(":")
        if field.strip().lower() != "content-disposition":
            continue
        for match in _DISPOSITION_PARAM.finditer(";" + value.partition(";")[2]):
            quoted = match[2] if match[2] is not None else match[3]
            params[match[1].lower()] = quoted.replace("%22", '"')
    return params


def _filename_of(params: dict[str, str]) -> str | None:
    """The file name a part declares, reduced to its last path component."""
    raw: str | None
    extended = params.get("filename*")
    if extended is not None:
        charset, _, rest = extended.partition("'")
        encoded = rest.partition("'")[2]
        try:
            raw = urllib.parse.unquote(encoded, encoding=charset or "utf-8", errors="replace")
        except LookupError:
            raw = urllib.parse.unquote(encoded, errors="replace")
    else:
        raw = params.get("filename")
    if raw is None:
        return None
    return raw.replace("\\", "/").split("/")[-1] or None


def _split_form_data(body: bytes, boundary: bytes) -> list[_FormPart] | str:
    """Split a multipart/form-data body into its parts, or return the reason it was refused."""
    delimiter = b"--" + boundary
    # Splitting stops after the cap, so a body of hundreds of thousands of empty parts costs one
    # pass and no per-part objects; the unsplit remainder shows up as one extra chunk.
    chunks = body.split(delimiter, _MAX_FORM_PARTS + 1)
    parts: list[_FormPart] = []
    for index in range(1, len(chunks)):
        chunk = chunks[index]
        if chunk.startswith(b"--"):  # the closing delimiter
            return parts
        if len(parts) == _MAX_FORM_PARTS:
            return "The upload has too many form fields."
        # A delimiter only counts at the start of a line (RFC 7578).
        if index > 1 and not chunks[index - 1].endswith(b"\n"):
            return "Malformed multipart body."
        part = _parse_part(chunk)
        if part is None:
            return "Malformed multipart body."
        parts.append(part)
    return parts


def _parse_part(chunk: bytes) -> _FormPart | None:
    chunk = chunk.lstrip(b" \t")
    crlf = chunk.startswith(b"\r\n")
    if not crlf and not chunk.startswith(b"\n"):
        return None
    newline = b"\r\n" if crlf else b"\n"
    headers, found, content = chunk[len(newline):].partition(newline * 2)
    if not found:
        return None
    if content.endswith(newline):
        content = content[: -len(newline)]
    params = _disposition_params(headers)
    return _FormPart(params.get("name", ""), _filename_of(params), content)


class _ChatHandler(BaseHTTPRequestHandler):
    """Request handler for the chatbot API."""

    session: ClassVar[Session]
    initial_response: ClassVar[Response | None] = None
    # Hosted servers answer to their platform's public name, so only Origin is checked there.
    hosted: ClassVar[bool] = False
    local_hosts: ClassVar[frozenset[str]] = _LOOPBACK_HOSTS
    # The platform's public name (Render sets RENDER_EXTERNAL_HOSTNAME), valid for Origin even if
    # its proxy rewrites Host.
    public_hosts: ClassVar[frozenset[str]] = frozenset()
    # The server is single-threaded and its session is shared, so a client that stalls
    # mid-request is dropped after this many seconds instead of blocking everyone.
    timeout = 15

    def log_message(self, format: str, *args: object) -> None:
        """Suppress default request logging to keep the terminal clean."""
        pass

    # ------------------------------------------------------------------
    # GET routes
    # ------------------------------------------------------------------

    def _request_is_allowed(self) -> bool:
        """Refuse DNS-rebound hosts (local mode) and cross-origin POSTs; reply 403 if refused."""
        host = self.headers.get("Host", "")
        if not self.hosted and _hostname(host) not in self.local_hosts:
            self._json_error("Unexpected Host header.", HTTPStatus.FORBIDDEN)
            return False
        origin = self.headers.get("Origin")
        if self.command == "POST" and origin is not None:
            # A page's own requests carry an Origin equal to the Host it was loaded from; another
            # site (or an opaque "null" origin) cannot forge that match.
            origin_host = urllib.parse.urlsplit(origin).netloc.lower()
            own_hosts = {host.strip().lower()}
            if self.hosted:
                # Behind a proxy that rewrites Host, the public name is the platform's own
                # hostname or X-Forwarded-Host. A web page cannot send that header: it is not
                # CORS-safelisted and this server never answers a preflight. The site is identified
                # by its hostname: the proxy may append its internal port to Host while the browser's
                # Origin has none. (Local mode keeps the port: another dev server on localhost is a
                # different origin.)
                forwarded = self.headers.get("X-Forwarded-Host", "").split(",")[0]
                own_hosts = {_hostname(name) for name in (host, forwarded) if name.strip()}
                own_hosts |= self.public_hosts
                origin_host = _hostname(origin_host)
            if not origin_host or origin_host not in own_hosts:
                self._json_error("Cross-origin requests are not allowed.", HTTPStatus.FORBIDDEN)
                return False
        return True

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def _guarded(self, route: Callable[[], None]) -> None:
        """Run a route so that a failure becomes a logged JSON 500, never a dropped connection."""
        try:
            if self._request_is_allowed():
                route()
        except (ConnectionError, TimeoutError):
            # The client went away or stalled mid-request; there is nobody to answer.
            self.close_connection = True
        except Exception:
            print(f"Unhandled error serving {self.command} {self.path}:", file=sys.stderr)
            traceback.print_exc()
            try:
                self._json_error(
                    "Something went wrong while handling that request. "
                    "Please try again, or type reset to start over.",
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )
            except OSError:
                self.close_connection = True

    def do_GET(self) -> None:
        self._guarded(self._route_get)

    def _route_get(self) -> None:
        if self.path in {"/", "/index.html", "/chat.html"}:
            self._serve_static("chat.html")
        elif self.path.startswith("/static/") and self.path[len("/static/"):] in _STATIC_TYPES:
            self._serve_static(self.path[len("/static/"):])
        elif self.path in {"/status", "/health", "/healthz"}:
            payload: dict[str, object] = {"phase": self.session.phase.value, "status": "ok"}
            if self.initial_response is not None:
                payload["initial_response"] = {
                    "text": self.initial_response.text,
                    "chips": self.initial_response.chips,
                    "table": self.initial_response.table,
                    "level": self.initial_response.level,
                    "view": self.initial_response.view,
                }
            self._json_response(payload)
        elif self.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        elif self.path.startswith("/download/"):
            raw_filename = self.path[len("/download/"):].split("?")[0]
            filename = urllib.parse.unquote(raw_filename)
            if filename in _downloads:
                staged = _downloads[filename]
                content = staged if isinstance(staged, bytes) else staged.encode("utf-8")
                content_type = _DOWNLOAD_TYPES.get(
                    Path(filename).suffix.lower(), "application/octet-stream"
                )
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                # The filename embeds the user's period text; never reflect quotes or ';' into the header.
                header_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
                self.send_header("Content-Disposition", f'attachment; filename="{header_name}"')
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store")
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
        self._guarded(self._route_post)

    def _route_post(self) -> None:
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

        body = self._read_body(_MAX_UPLOAD_BODY)
        if body is None:
            return

        boundary = _boundary_of(content_type)
        if boundary is None:
            self._json_error("The upload has no multipart boundary.", HTTPStatus.BAD_REQUEST)
            return
        form = _split_form_data(body, boundary)
        if isinstance(form, str):
            self._json_error(form, HTTPStatus.BAD_REQUEST)
            return

        file_bytes: bytes | None = None
        filename: str | None = None
        sheet: str | None = None
        first_visit: bool | None = None

        for part in form:
            if part.name == "file":
                file_bytes = part.content
                filename = part.filename
            elif part.name == "sheet":
                sheet_text = part.content.decode("utf-8", errors="replace").strip()
                if sheet_text:
                    sheet = sheet_text
            elif part.name == "first_visit":
                first_visit = part.content.strip() == b"1"

        if file_bytes is None or filename is None:
            self._json_error(
                "No file found in the upload. Please select a CSV, JSON, XLSX, XLSM, or PDF file.",
                HTTPStatus.BAD_REQUEST,
            )
            return

        _downloads.clear()  # exports of the previous file must not outlive it
        response = handle_upload(self.session, file_bytes, filename, sheet, first_visit=first_visit)
        self._send_response(response)

    def _handle_message(self) -> None:
        """Process a text message through the intent router."""
        # A cross-site form can send text/plain without a preflight; only the page's own
        # fetch() sends JSON.
        if self.headers.get_content_type() != "application/json":
            self._json_error("Expected application/json.", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return
        body = self._read_body(_MAX_MESSAGE_BODY)
        if body is None:
            return

        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self._json_error("Invalid JSON.", HTTPStatus.BAD_REQUEST)
            return

        raw_text = data.get("text", "") if isinstance(data, dict) else None
        if not isinstance(raw_text, str):
            self._json_error("Expected a JSON object with a text string.", HTTPStatus.BAD_REQUEST)
            return
        text = raw_text.strip()
        if not text:
            self._json_error("Empty message.", HTTPStatus.BAD_REQUEST)
            return

        raw_first_visit = data.get("first_visit")
        first_visit = raw_first_visit if isinstance(raw_first_visit, bool) else None
        phase_before = self.session.phase
        response = handle_message(self.session, text, first_visit=first_visit)
        if phase_before is not Phase.AWAITING_FILE and self.session.phase is Phase.AWAITING_FILE:
            _downloads.clear()  # the session was reset; its exports go with it
        self._send_response(response)

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _read_body(self, limit: int) -> bytes | None:
        """Read a request body of a declared, bounded length; reply 4xx and return None otherwise."""
        # int() also accepts '+5', '5_0' and non-ASCII digits; a length is plain ASCII digits.
        raw_length = self.headers.get("Content-Length", "0").strip()
        if not re.fullmatch(r"[0-9]{1,12}", raw_length):
            self._json_error("Invalid Content-Length.", HTTPStatus.BAD_REQUEST)
            return None
        length = int(raw_length)
        if length > limit:
            self._json_error("Request body is too large.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return None
        return self.rfile.read(length)

    def _send_response(self, response: Response) -> None:
        """Serialize a Response dataclass to JSON and send it."""
        payload: dict[str, object] = {
            "text": response.text,
            "phase": response.phase or self.session.phase,
        }
        if response.table is not None:
            payload["table"] = response.table
        if response.chips is not None:
            payload["chips"] = response.chips
        if response.level is not None:
            payload["level"] = response.level
        if response.view is not None:
            payload["view"] = response.view
        if response.download is not None:
            # Stage the download and return a URL
            for filename, content in response.download.items():
                _stage_download(filename, content)
                payload["download_url"] = "/download/" + urllib.parse.quote(filename, safe="")
                payload["download_filename"] = filename

        self._json_response(payload)

    def _json_response(self, data: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        # ASCII-only on the wire: a lone surrogate in user text would not encode as UTF-8.
        body = json.dumps(data, ensure_ascii=True).encode("ascii")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, message: str, status: HTTPStatus) -> None:
        self._json_response({"error": message}, status)

    def _serve_static(self, filename: str) -> None:
        content_type = _STATIC_TYPES[filename]
        try:
            content = (
                importlib.resources.files("variance_agent").joinpath("static", filename).read_bytes()
            )
        except OSError:
            self._json_error(f"Static file not found: {filename}", HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")  # revalidate, so a new release is picked up
        if filename.endswith(".html"):
            self.send_header("Content-Security-Policy", _PAGE_CSP)
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
    _ChatHandler.hosted = hosted
    _ChatHandler.local_hosts = _LOOPBACK_HOSTS | ({_hostname(host)} - {"", "0.0.0.0", "::"})
    external = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
    _ChatHandler.public_hosts = frozenset({external}) if hosted and external else frozenset()

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
        print(f"Variance Analysis Chatbot running at {url}", flush=True)
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
