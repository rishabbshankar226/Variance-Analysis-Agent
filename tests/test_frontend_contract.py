"""The page the chat server serves: where it lives, how it is served and what it may do.

Static checks pin the packaging and security contract; the Node-driven checks at the bottom run
the real `chat.js` helpers (skipped when Node is not installed).
"""

from __future__ import annotations

import importlib.resources
import json
import re
import shutil
import subprocess
import threading
from collections.abc import Callable, Iterator
from http.client import HTTPConnection, HTTPResponse
from http.server import HTTPServer
from pathlib import Path

import pytest

from variance_agent.chat import server as server_module
from variance_agent.chat.server import _ChatHandler
from variance_agent.chat.session import Session

from tests.frontend_helpers import THEMES, colour, contrast

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


# ---------------------------------------------------------------------------
# Strict Content-Security-Policy: no inline script, style or handlers
# ---------------------------------------------------------------------------

def _page() -> str:
    return _packaged("chat.html").decode("utf-8")


def _script() -> str:
    return _packaged("chat.js").decode("utf-8")


def test_the_page_has_no_inline_script_or_style_bodies() -> None:
    page = _page()
    assert not re.search(r"<style\b", page, re.IGNORECASE)
    for match in re.finditer(r"<script\b([^>]*)>(.*?)</script>", page, re.IGNORECASE | re.DOTALL):
        assert "src=" in match[1] and not match[2].strip(), match[0][:80]
    assert 'href="/static/chat.css"' in page
    assert 'src="/static/chat.js"' in page


@pytest.mark.parametrize("source", ["page", "script"])
def test_no_inline_handlers_or_style_attributes(source: str) -> None:
    text = _page() if source == "page" else _script()
    assert not re.search(r"\bon[a-z]+\s*=\s*[\"']", text, re.IGNORECASE), "inline event handler"
    assert not re.search(r"\bstyle\s*=\s*[\"'\\]", text, re.IGNORECASE), "inline style attribute"
    assert "setAttribute('style'" not in text and 'setAttribute("style"' not in text
    assert "cssText" not in text
    assert "javascript:" not in text.lower()


def test_the_page_is_served_with_a_strict_csp(httpd: HTTPServer) -> None:
    response, _ = _get(httpd, "/")
    policy = response.getheader("Content-Security-Policy") or ""
    directives = {d.split()[0]: d.split()[1:] for d in policy.split(";") if d.strip()}
    assert directives["default-src"] == ["'self'"]
    assert directives["frame-ancestors"] == ["'none'"]
    assert directives["base-uri"] == ["'none'"]
    assert directives["object-src"] == ["'none'"]
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy
    assert "http" not in policy.replace("'self'", "")  # nothing is allowed from another origin


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/static/chat.js", "text/javascript; charset=utf-8"),
        ("/static/chat.css", "text/css; charset=utf-8"),
        ("/static/chat.html", "text/html; charset=utf-8"),
        ("/static/favicon.svg", "image/svg+xml"),
    ],
)
def test_assets_are_served_from_the_package_with_their_types(
    httpd: HTTPServer, path: str, content_type: str
) -> None:
    response, body = _get(httpd, path)
    assert response.status == 200
    assert response.getheader("Content-Type") == content_type
    assert body == _packaged(path.rsplit("/", 1)[1])
    assert response.getheader("Cache-Control") == "no-cache"
    assert response.getheader("X-Content-Type-Options") == "nosniff"


@pytest.mark.parametrize(
    "path",
    [
        "/static/",
        "/static/missing.js",
        "/static/../chat/server.py",
        "/static/%2e%2e/chat/server.py",
        "/static/..%2fchat%2fserver.py",
        "/static/chat.js/",
        "/static//chat.js",
        "/static/__init__.py",
    ],
)
def test_only_the_allowlisted_assets_are_served(httpd: HTTPServer, path: str) -> None:
    response, _ = _get(httpd, path)
    assert response.status == 404


def test_the_javascript_parses() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    result = subprocess.run(
        [node, "--check", str(PACKAGE_STATIC / "chat.js")], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_the_script_opts_into_type_checking() -> None:
    assert _script().lstrip().startswith("// @ts-check")


# ---------------------------------------------------------------------------
# Phases and limits stay in step with the server
# ---------------------------------------------------------------------------

def _object_keys(source: str, name: str) -> set[str]:
    block = re.search(rf"export const {name} = \{{(.*?)\n\}};", source, re.DOTALL)
    assert block, f"{name} not found"
    return set(re.findall(r"^\s*(\w+):", block[1], re.MULTILINE))


def test_every_session_phase_has_a_label_and_a_placeholder() -> None:
    from variance_agent.chat.session import Phase

    phases = {phase.value for phase in Phase}
    # Extra entries are fine (the chat logic may retire a phase); missing ones show raw ids.
    assert phases <= _object_keys(_script(), "PHASE_LABELS")
    assert phases <= _object_keys(_script(), "PHASE_PLACEHOLDERS")


def test_page_limits_mirror_the_server_limits() -> None:
    from variance_agent.limits import MAX_INPUT_BYTES, MAX_TEXT_LENGTH

    def value(name: str) -> int:
        match = re.search(rf"export const {name} = ([\d* ]+);", _script())
        assert match, name
        product = 1
        for factor in match[1].split("*"):
            product *= int(factor)
        return product

    assert value("MAX_MESSAGE_CHARS") == MAX_TEXT_LENGTH
    assert value("MAX_UPLOAD_BYTES") == MAX_INPUT_BYTES


# ---------------------------------------------------------------------------
# Accessibility and layout contract
# ---------------------------------------------------------------------------

def _css() -> str:
    return _packaged("chat.css").decode("utf-8")


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("surface", ["bg-primary", "bg-secondary", "bg-surface", "bg-card"])
@pytest.mark.parametrize(
    "text", ["text-primary", "text-secondary", "text-muted", "accent-text", "red-text", "green"]
)
def test_text_colours_reach_wcag_aa_on_every_surface(text: str, surface: str, theme: str) -> None:
    assert contrast(colour(theme, text), colour(theme, surface)) >= 4.5, f"{text} on {surface} ({theme})"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("background", ["accent", "accent-hover", "green-strong", "green-strong-hover"])
def test_white_text_on_filled_controls_reaches_wcag_aa(background: str, theme: str) -> None:
    assert contrast("#ffffff", colour(theme, background)) >= 4.5, f"{background} ({theme})"


def test_the_stylesheet_has_no_remote_import_and_uses_dynamic_viewport_height() -> None:
    css = _css()
    assert "@import" not in css and "http" not in css
    assert re.search(r"height:\s*100vh;\s*height:\s*100dvh;", css)
    assert "prefers-reduced-motion" in css
    assert ":focus-visible" in css


def test_the_message_box_is_a_labelled_textarea_and_the_log_is_announced() -> None:
    page = _page()
    assert re.search(r"<textarea\b[^>]*\bid=\"input\"", page)
    assert not re.search(r"<input\b[^>]*\bid=\"input\"", page)
    assert re.search(r'<label for="input"', page)
    log = re.search(r'<div class="messages"[^>]*>', page)
    assert log and 'role="log"' in log[0] and 'aria-live="polite"' in log[0]
    assert 'aria-label="Send message"' in page


def test_enter_sends_shift_enter_breaks_the_line_and_composition_is_respected() -> None:
    script = _script()
    handler = re.search(r"addEventListener\('keydown', \(e\) => \{(.*?)\n    \}\);", script, re.DOTALL)
    assert handler
    assert "e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229" in handler[1]
    # Only the ends are trimmed; interior line breaks of a pasted table reach the server.
    assert "inputEl.value.trim()" in script
    assert not re.search(r"inputEl\.value[^;\n]*\.replace\(", script)


def test_every_interactive_control_is_keyboard_reachable() -> None:
    script = _script()
    assert "zone.tabIndex = 0" in script and "e.key === 'Enter' || e.key === ' '" in script
    assert "link.className = 'item-link'" in script and "document.createElement('button')" in script
    assert "th.setAttribute('aria-sort'" in script
    assert "wrapper.tabIndex = 0" in script
    assert not re.search(r"\.className = 'chip'[^;]*\n[^;]*createElement\('div'\)", script)
    # No click handlers on non-interactive cells or headers any more.
    assert "th.addEventListener('click'" not in script
    assert "td.addEventListener('click'" not in script


# ---------------------------------------------------------------------------
# Behaviour of the real chat.js helpers, run under Node (skipped without it)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def run_js(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    # Node treats a .mjs file as an ES module whatever the nearest package.json says.
    module = tmp_path_factory.mktemp("chatjs") / "chat.mjs"
    module.write_bytes(_packaged("chat.js"))

    def run(body: str) -> object:
        program = (
            f"const m = await import({json.dumps(module.as_uri())});\n"
            f"const result = await (async () => {{ {body} }})();\n"
            "console.log(JSON.stringify(result));"
        )
        done = subprocess.run(
            [node, "--input-type=module", "-e", program], capture_output=True, text=True, timeout=30
        )
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    return run


def test_unknown_and_inherited_phase_names_still_get_a_readable_label(run_js: Callable[[str], object]) -> None:
    labels = run_js("return ['awaiting_new_step', 'constructor', '', 'exploring'].map(m.phaseLabel);")
    assert labels == ["New step", "Constructor", "Ready", "Results"]
    assert run_js("return m.phasePlaceholder('toString');") == "Type a message"


def test_a_reload_mid_intake_keeps_the_servers_phase(run_js: Callable[[str], object]) -> None:
    views = run_js("""
      return [
        m.startupView(null),
        m.startupView({phase: 'awaiting_file'}),
        m.startupView({phase: 'awaiting_blank_budget_confirmation'}),
        m.startupView({phase: 'exploring', initial_response: {text: 'Loaded', chips: ['a']}}),
        m.startupView({phase: 7}),
      ];""")
    assert views == [
        {"kind": "welcome", "phase": "awaiting_file"},
        {"kind": "welcome", "phase": "awaiting_file"},
        {"kind": "resumed", "phase": "awaiting_blank_budget_confirmation"},
        {"kind": "restored", "phase": "exploring", "reply": {"text": "Loaded", "chips": ["a"]}},
        {"kind": "welcome", "phase": "awaiting_file"},
    ]


def test_failed_requests_are_described_never_blank(run_js: Callable[[str], object]) -> None:
    messages = run_js("""
      return [
        m.describeFailure(413, {error: 'Request body is too large.'}),
        m.describeFailure(413, null),
        m.describeFailure(502, null),
        m.describeFailure(500, {}),
        m.describeFailure(400, {error: '   '}),
      ];""")
    assert messages[0] == "Request body is too large."
    assert "larger than the server accepts" in messages[1]
    assert "not responding" in messages[2]
    assert messages[3] == "The server could not handle that request (HTTP 500)."
    assert messages[4] == "The server could not handle that request (HTTP 400)."  # blank error text


def test_request_json_reports_http_errors_and_non_json_bodies(run_js: Callable[[str], object]) -> None:
    results = run_js("""
      const reply = (status, body) => async () => new Response(body, {status});
      return [
        await m.requestJson('/x', {}, 1000, reply(413, JSON.stringify({error: 'too big'}))),
        await m.requestJson('/x', {}, 1000, reply(502, '<html>Bad gateway</html>')),
        await m.requestJson('/x', {}, 1000, reply(200, '[1, 2]')),
        await m.requestJson('/x', {}, 1000, reply(200, JSON.stringify({text: 'hi'}))),
      ];""")
    assert results == [
        {"ok": False, "status": 413, "data": {"error": "too big"}},
        {"ok": False, "status": 502, "data": None},
        {"ok": True, "status": 200, "data": None},
        {"ok": True, "status": 200, "data": {"text": "hi"}},
    ]


def test_request_json_gives_up_after_the_deadline_and_explains_a_dead_network(
    run_js: Callable[[str], object],
) -> None:
    messages = run_js("""
      const hang = (url, init) => new Promise((_, reject) =>
        init.signal.addEventListener('abort', () => reject(new DOMException('x', 'AbortError'))));
      const down = async () => { throw new TypeError('Failed to fetch'); };
      const outcome = async (fetchImpl, ms) => {
        try { await m.requestJson('/x', {}, ms, fetchImpl); return 'resolved'; }
        catch (err) { return err.message; }
      };
      return [await outcome(hang, 30), await outcome(down, 1000)];""")
    assert "did not answer in time" in messages[0]
    assert "Could not reach the server" in messages[1]


@pytest.mark.parametrize(
    "payload",
    [
        "<img src=x onerror=alert(1)>",
        "<script>alert(1)</script>",
        "&lt;script&gt;alert(1)&lt;/script&gt;",  # the server's own escape, decoded once then re-escaped
        "**<b>bold</b>** and `<i>code</i>`",
        "# <svg onload=alert(1)>",
        "- <a href=\"javascript:alert(1)\">x</a>",
    ],
)
def test_markdown_rendering_never_emits_markup_from_the_text(run_js: Callable[[str], object], payload: str) -> None:
    html = run_js(f"return m.renderMarkdown({json.dumps(payload)});")
    assert isinstance(html, str)
    # Whatever the renderer generated carries only a fixed tag name and one of its own classes;
    # every other angle bracket in the text must have been escaped.
    generated = r"</?(strong|em|code|h[234]|div|br|hr|table|thead|tbody|tr|th|td)( class=\"md-[a-z0-9]+\")?>"
    assert "<" not in re.sub(generated, "", html), html


def test_markdown_uses_classes_not_inline_styles(run_js: Callable[[str], object]) -> None:
    html = run_js("return m.renderMarkdown('# One\\n## Two\\n### Three\\n---\\n- item\\n• dot');")
    assert isinstance(html, str)
    assert "style" not in html
    for cls in ("md-h2", "md-h3", "md-h4", "md-hr", "md-bullet"):
        assert cls in html


def test_a_markdown_table_in_a_reply_renders_as_a_table(run_js: Callable[[str], object]) -> None:
    html = run_js(r"""return m.renderMarkdown('Lead\n\n| Line | Limit | Status |\n|---|---:|---|\n'
                                              + '| Desk A \\| B | $500.00 | **Breach** |\n\nAfter');""")
    assert isinstance(html, str)
    assert ('<div class="md-tablewrap"><table class="md-table"><thead><tr><th>Line</th><th class="md-num">Limit</th>'
            '<th>Status</th></tr></thead><tbody><tr><td>Desk A | B</td><td class="md-num">$500.00</td>'
            '<td><strong>Breach</strong></td></tr></tbody></table></div>') in html
    assert html.startswith("Lead<br><br>") and html.endswith("<br>After")
    assert "|---" not in html


def test_pipes_without_a_separator_row_stay_text(run_js: Callable[[str], object]) -> None:
    html = run_js("return m.renderMarkdown('| not | a table |');")
    assert html == "| not | a table |"


def test_server_escapes_are_decoded_once_for_text_and_cells(run_js: Callable[[str], object]) -> None:
    out = run_js(r"""
      return [m.renderMarkdown('R&amp;D\\_Costs and 1 &lt; 2'), m.plainText('R&amp;D\\_Costs &lt;x&gt;')];""")
    assert out == ["R&amp;D_Costs and 1 &lt; 2", "R&D_Costs <x>"]


def test_amounts_parse_like_the_table_sorter_expects(run_js: Callable[[str], object]) -> None:
    values = run_js("""
      return ['$1,234.50', '(1,234)', '($50)', '12.5%', '€-7', '', null, 'n/a'].map(m.parseNumericVal);""")
    assert values == [1234.5, -1234, -50, 12.5, -7, 0, 0, 0]


def test_a_huge_paste_is_echoed_as_a_bounded_preview(run_js: Callable[[str], object]) -> None:
    out = run_js("""
      const short = 'a\\tb\\n1\\t2';
      const long = 'x'.repeat(10000);
      return [m.previewText(short), m.previewText(long).length < 4200, m.previewText(long).includes('6,000 more characters')];""")
    assert out == ["a\tb\n1\t2", True, True]


def test_the_phone_header_keeps_the_phase_label_visible() -> None:
    css = _css()
    narrow = css[css.index("@media (max-width: 420px)"):]
    assert ".header-status { display: none; }" not in narrow
    assert "autoGrow();" in re.search(r"function updatePhase\(phase\) \{(.*?)\n  \}", _script(), re.DOTALL)[1]  # type: ignore[index]
