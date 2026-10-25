"""The look of the chat page, as invariants: the tells of docs/ui/DESIGN.md that a test can check.

Screens are judged by screenshots (docs/ui/evidence); these tests hold what a stylesheet, a page or
the exported JavaScript helpers can prove. Counts are ceilings: each is pinned at its current value
and checked against the ceiling, and the counter itself is checked one step either side of it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.frontend_helpers import THEMES, colour, contrast, css, packaged, theme_block, theme_tokens
from tests.test_frontend_contract import run_js  # noqa: F401  (a fixture)
from variance_agent.chat.server import _STATIC_TYPES

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "variance_agent" / "static"
CHAT = ROOT / "src" / "variance_agent" / "chat"

# Every colour a theme must define for itself; the dark block may not lean on the light values.
COLOUR_TOKENS = (
    [f"grey-{i}" for i in range(9)]
    + ["bg-primary", "bg-secondary", "bg-surface", "bg-card", "border", "border-strong",
       "text-primary", "text-secondary", "text-muted", "accent", "accent-hover", "accent-text",
       "green", "green-strong", "green-strong-hover", "red-text", "amber", "on-accent"]
)
SURFACES = ("bg-primary", "bg-secondary", "bg-surface", "bg-card")

# T1: emoji, arrows, dingbats and geometric shapes. Emoji_Presentation is covered by the
# supplementary pictograph planes plus the BMP blocks that hold emoji (watch, hourglass, play).
_BANNED = (
    (0x2190, 0x21FF), (0x2300, 0x23FF), (0x25A0, 0x25FF), (0x2600, 0x27BF), (0x2B00, 0x2BFF),
    (0x3030, 0x3030), (0x303D, 0x303D), (0xFE0F, 0xFE0F), (0x1F000, 0x1FAFF),
)
# chat/ modules whose reply text still carries glyphs; each phase removes the files it converts.
NOT_YET_CONVERTED = {"handlers.py", "knowledge.py"}


def banned_glyphs(text: str) -> list[str]:
    return sorted({ch for ch in text if any(lo <= ord(ch) <= hi for lo, hi in _BANNED)})


def _rules(stylesheet: str) -> list[tuple[str, str]]:
    """(selector, declarations) for every innermost rule, at-rule wrappers flattened."""
    bare = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.DOTALL)
    return [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", bare)]


def _resolved(value: str) -> str:
    tokens = theme_tokens("light")
    return re.sub(r"var\(--([\w-]+)\)", lambda m: tokens[m[1]], value).strip()


def declared(prop: str, stylesheet: str | None = None) -> set[str]:
    """Distinct resolved values of a property across the stylesheet (custom properties excluded)."""
    sheet = css() if stylesheet is None else stylesheet
    values = re.findall(rf"(?<![\w-]){re.escape(prop)}\s*:\s*([^;}}]+)", sheet)
    found = {_resolved(v) for v in values} - {"inherit", "initial", "unset"}
    if prop == "font-weight":
        found = {{"bold": "700", "normal": "400"}.get(v, v) for v in found}
    return found


# ---------------------------------------------------------------------------
# Themes and colour (T2)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("theme", THEMES)
def test_every_theme_defines_every_colour_token_itself(theme: str) -> None:
    block = theme_block(theme)
    for name in COLOUR_TOKENS:
        assert re.search(rf"--{name}\s*:", block), f"--{name} missing from the {theme} block"
        colour(theme, name)


def test_the_dark_theme_follows_the_system_setting_and_differs_from_light() -> None:
    assert "@media (prefers-color-scheme: dark)" in css()
    assert colour("dark", "bg-primary") != colour("light", "bg-primary")
    assert contrast(colour("dark", "bg-primary"), "#000000") < contrast(colour("light", "bg-primary"), "#000000")


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("text", ["amber"])
def test_attention_text_reaches_wcag_aa_on_every_surface(text: str, surface: str, theme: str) -> None:
    assert contrast(colour(theme, text), colour(theme, surface)) >= 4.5, f"{text} on {surface} ({theme})"


@pytest.mark.parametrize("theme", THEMES)
def test_text_on_the_accent_and_the_focus_ring_are_readable(theme: str) -> None:
    assert contrast(colour(theme, "on-accent"), colour(theme, "accent")) >= 4.5
    assert contrast(colour(theme, "on-accent"), colour(theme, "accent-hover")) >= 4.5
    # A focus ring is a non-text mark: WCAG asks 3:1 against what is next to it.
    for surface in SURFACES:
        assert contrast(colour(theme, "accent-text"), colour(theme, surface)) >= 3


@pytest.mark.parametrize("theme", THEMES)
def test_favorable_and_unfavorable_differ_in_lightness_not_only_hue(theme: str) -> None:
    assert contrast(colour(theme, "green"), colour(theme, "red-text")) >= 1.25, theme


@pytest.mark.parametrize("theme", THEMES)
def test_the_accent_is_not_violet_or_teal(theme: str) -> None:
    r, g, b = (int(colour(theme, "accent")[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hi, lo = max(r, g, b), min(r, g, b)
    hue = 0.0 if hi == lo else (60 * ((g - b) / (hi - lo)) % 360 if hi == r
                                 else 60 * ((b - r) / (hi - lo)) + 120 if hi == g
                                 else 60 * ((r - g) / (hi - lo)) + 240)
    assert not 255 <= hue <= 300, f"violet accent ({hue:.0f} degrees)"
    assert not 160 <= hue <= 200, f"teal accent ({hue:.0f} degrees)"


def test_no_gradient_glow_or_text_shadow() -> None:
    sheet = css()
    assert "gradient(" not in sheet
    assert "glow" not in sheet
    assert "text-shadow" not in sheet and "drop-shadow" not in sheet


# ---------------------------------------------------------------------------
# Type (T3)
# ---------------------------------------------------------------------------

def test_the_counter_resolves_tokens_and_reads_bold_as_700() -> None:
    sample = "a { font-size: var(--text-body); } b { font-size: 14px; font-weight: bold; } i { font-weight: 700; }"
    assert declared("font-size", sample) == {"14px"}
    assert declared("font-weight", sample) == {"700"}


@pytest.mark.parametrize(("sizes", "within"), [(6, True), (7, False)])
def test_the_size_ceiling_is_six(sizes: int, within: bool) -> None:
    sample = " ".join(f".s{i} {{ font-size: {10 + i}px; }}" for i in range(sizes))
    assert (len(declared("font-size", sample)) <= 6) is within


def test_at_most_six_font_sizes_and_three_weights() -> None:
    sizes, weights = declared("font-size"), declared("font-weight")
    assert sizes == {"12px", "13px", "14px", "16px"} and len(sizes) <= 6, sizes
    assert weights == {"400", "500", "600"} and len(weights) <= 3, weights


def test_figures_are_tabular_and_monospace_is_for_code_only() -> None:
    body = next(declarations for selector, declarations in _rules(css()) if selector == "body")
    assert "font-variant-numeric: tabular-nums" in body
    for selector, declarations in _rules(css()):
        if "var(--font-mono)" in declarations and "--font-mono" not in declarations:
            assert "code" in selector, f"monospace on {selector}"


# ---------------------------------------------------------------------------
# Space, shape, depth (T4)
# ---------------------------------------------------------------------------

def test_at_most_two_radii_and_one_overlay_shadow() -> None:
    radii = declared("border-radius")
    assert radii == {"4px", "8px"} and len(radii) <= 2, radii
    shadows = declared("box-shadow")
    assert len(shadows) <= 1 and all(re.fullmatch(r"0 4px 16px #[0-9a-f]{8}", s) for s in shadows), shadows


def test_every_gap_comes_from_the_4px_scale() -> None:
    off_scale = []
    for selector, declarations in _rules(css()):
        if selector == ".sr-only":
            continue  # the standard visually-hidden pattern
        for prop, value in re.findall(r"(?<![\w-])(padding[\w-]*|margin[\w-]*|gap|row-gap|column-gap)\s*:\s*([^;]+)", declarations):
            for px in re.findall(r"(-?\d+(?:\.\d+)?)px", _resolved(value)):
                if float(px) % 4:
                    off_scale.append(f"{selector} {prop}: {px}px")
    assert not off_scale, off_scale


# ---------------------------------------------------------------------------
# Motion (T10), forced colours, print (T12)
# ---------------------------------------------------------------------------

def test_motion_is_short_on_opacity_and_transform_and_stops_when_asked() -> None:
    sheet = css()
    assert not re.search(r"(?<![\w-])transition\s*:(?!\s*none)", sheet), "transitions animate more than opacity"
    for name, frames in re.findall(r"@keyframes\s+([\w-]+)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", sheet):
        props = set(re.findall(r"([\w-]+)\s*:", frames))
        assert props <= {"opacity", "transform"}, f"@keyframes {name} animates {props}"
    for duration in re.findall(r"animation\s*:\s*[\w-]+\s+(\d+(?:\.\d+)?)(ms|s)", _resolved(sheet)):
        seconds = float(duration[0]) / (1000 if duration[1] == "ms" else 1)
        assert seconds <= 1.2, duration
    assert re.search(r"\.typing-dots[^{]*\{[^}]*animation:\s*working 1\.2s", sheet)
    reduced = sheet[sheet.index("@media (prefers-reduced-motion: reduce)"):]
    assert "animation: none !important" in reduced and "transition: none !important" in reduced


def test_forced_colours_keep_controls_and_marks_visible() -> None:
    sheet = css()
    block = sheet[sheet.index("@media (forced-colors: active)"):]
    block = block[:block.index("\n}\n")]
    for needle in (".chip", ".send-btn", "ButtonText", "CanvasText", ".message-body.is-error"):
        assert needle in block, needle


def test_print_releases_the_log_and_drops_the_controls() -> None:
    sheet = css()
    block = sheet[sheet.index("@media print"):]
    block = block[:block.index("\n}\n")]
    assert re.search(r"body \{[^}]*height: auto; overflow: visible", block)
    assert re.search(r"\.messages \{[^}]*overflow: visible; height: auto", block)
    assert re.search(r"\.input-bar, \.chips", block)


# ---------------------------------------------------------------------------
# Assets: no emoji (T1), nothing remote, every file allowlisted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("asset", sorted(_STATIC_TYPES))
def test_no_emoji_arrows_or_dingbats_in_the_page(asset: str) -> None:
    assert banned_glyphs(packaged(asset).decode("utf-8")) == [], asset


def test_the_glyph_check_catches_each_kind() -> None:
    assert banned_glyphs("\U0001F4CA ↓ ▲ ✅ ⭐ ⚠️ plain • …") == sorted(
        ["\U0001F4CA", "↓", "▲", "✅", "⭐", "⚠", "️"]
    )


@pytest.mark.parametrize("module", sorted(p.name for p in CHAT.glob("*.py")))
def test_reply_text_built_by_chat_has_no_glyphs(module: str) -> None:
    found = banned_glyphs((CHAT / module).read_text(encoding="utf-8"))
    if module in NOT_YET_CONVERTED:
        assert found, f"{module} is clean: take it off NOT_YET_CONVERTED"
    else:
        assert found == [], f"{module}: {found}"


def test_nothing_is_loaded_from_another_origin() -> None:
    page, script, sheet, icon = (packaged(name).decode("utf-8")
                                 for name in ("chat.html", "chat.js", "chat.css", "favicon.svg"))
    assert not re.search(r"(?:src|href)\s*=\s*\"(?!/static/)", page)
    assert re.findall(r"https?://[^'\"\s]+", script) == ["http://www.w3.org/2000/svg"]
    assert "url(" not in sheet and "http" not in sheet and "@font-face" not in sheet
    assert re.findall(r"https?://[^'\"\s]+", icon) == ["http://www.w3.org/2000/svg"]
    assert "<style" not in icon and "<script" not in icon and "href" not in icon


def test_every_static_file_is_allowlisted_and_nothing_else_ships() -> None:
    files = {p.name for p in STATIC.iterdir() if p.is_file()}
    assert files == set(_STATIC_TYPES)
    distribution = (ROOT / "scripts" / "check_distribution.py").read_text(encoding="utf-8")
    for name in files:
        assert name in distribution, name


# ---------------------------------------------------------------------------
# The icon helper, run under Node (T1, T11)
# ---------------------------------------------------------------------------

def test_icons_are_one_set_at_two_sizes(run_js: Callable[[str], object]) -> None:  # noqa: F811
    assert run_js("return m.ICON_SIZES;") == [16, 20]
    names = run_js("return Object.keys(m.ICONS).sort();")
    assert names == ["download", "help", "mark", "restart", "search", "sort", "sort-asc", "sort-desc", "upload"]
    assert run_js("return m.iconParts('sort', 16).length;") == 2
    assert run_js("return m.ICONS.mark.filter((p) => p.fill).length;") == 1
    for bad in ("m.iconParts('emoji', 16)", "m.iconParts('sort', 24)"):
        message = run_js(f"try {{ {bad}; return null; }} catch (e) {{ return e.message; }}")
        assert isinstance(message, str) and message.startswith(("Unknown icon", "Icons are drawn at 16 or 20 px")), message


def test_every_icon_path_stays_on_the_20_unit_grid(run_js: Callable[[str], object]) -> None:  # noqa: F811
    paths = run_js("return Object.values(m.ICONS).flat().map((p) => p.d);")
    assert isinstance(paths, list) and paths
    for d in paths:
        assert re.fullmatch(r"[MmLlHhVvAaCcSsZz0-9.\s,-]+", d), d
        numbers = [abs(float(n)) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
        assert max(numbers) <= 20, d


# ---------------------------------------------------------------------------
# The shell and the first minute (Phase 2: T6, T7, T10, T11, the error level)
# ---------------------------------------------------------------------------

def _script() -> str:
    return packaged("chat.js").decode("utf-8")


def test_only_the_latest_turns_chips_respond(run_js: Callable[[str], object]) -> None:  # noqa: F811
    result = run_js(
        "const log = [];"
        "const group = (id, n) => { const chips = Array.from({ length: n }, () => ({ disabled: false }));"
        "  return { chips, classList: { add: (c) => log.push(`${id}:${c}`) },"
        "    setAttribute: (k, v) => log.push(`${id}:${k}=${v}`), querySelectorAll: () => chips }; };"
        "const groups = [group('a', 2), group('b', 3)];"
        "return [m.retireChips(groups), groups.map((g) => g.chips.every((c) => c.disabled)), log, m.retireChips([])];"
    )
    assert result == [5, [True, True],
                      ["a:is-retired", "a:aria-label=Earlier suggestions, no longer available",
                       "b:is-retired", "b:aria-label=Earlier suggestions, no longer available"], 0]
    script = _script()
    body = script[script.index("function addUserMessage(text) {"):]
    body = body[:body.index("\n  }\n")]
    # Retired at the turn boundary, before the new message is drawn, and only `.chips` groups:
    # earlier table drill-downs and download links stay live.
    call = "retireChips(Array.from(messagesEl.querySelectorAll('.chips:not(.is-retired)')))"
    assert body.index(call) < body.index("createElement")
    assert script.count("retireChips(") == 2  # the definition and that one call
    retired = "\n".join(decl for sel, decl in _rules(css()) if ".is-retired" in sel)
    assert "border-color: transparent" in retired and "cursor: default" in retired


def test_markdown_blocks_are_not_followed_by_an_empty_line(run_js: Callable[[str], object]) -> None:  # noqa: F811
    html = run_js("return m.renderMarkdown('**Analysis**\\n\u2022 one\\n\u2022 two\\n\\nDone');")
    assert html == ('<strong>Analysis</strong><br><div class="md-bullet">\u2022 one</div>'
                    '<div class="md-bullet">\u2022 two</div><br>Done')


def test_the_header_has_a_drawn_mark_a_wordmark_and_a_matching_favicon() -> None:
    page = packaged("chat.html").decode("utf-8")
    assert '<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">' in page
    assert "<h1>Variance Analysis Agent</h1>" in page
    assert '<div class="header-icon" aria-hidden="true"></div>' in page
    assert "createIcon('mark', 20)" in _script()
    icon = packaged("favicon.svg").decode("utf-8")
    assert icon.startswith('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">')
    # The favicon draws the same mark: an outlined budget bar beside a taller filled actual bar.
    assert 'fill="none" stroke="#ffffff"' in icon and 'fill="#ffffff"' in icon
    assert colour("light", "accent") in icon


def test_help_and_start_over_keep_their_words_on_a_phone() -> None:
    page = packaged("chat.html").decode("utf-8")
    assert '<span class="btn-label">Help</span>' in page and '<span class="btn-label">Start over</span>' in page
    narrow = css()[css().index("@media (max-width: 420px)"):]
    assert ".header-action-btn .btn-label {" in narrow and "display: none" not in narrow.split(".btn-label {")[1][:200]


def test_the_working_indicator_waits_then_shows_a_flat_skeleton() -> None:
    script = _script()
    show = script[script.index("function showTypingIndicator("):script.index("function removeTypingIndicator()")]
    assert show.rstrip().endswith("    }, 100);\n  }"), "the indicator does not wait 100 ms"
    assert "msg.classList.add('is-long'), 900" in show
    remove = script[script.index("function removeTypingIndicator()"):]
    remove = remove[:remove.index("\n  }\n")]
    assert "clearTimeout(indicatorTimer)" in remove and "clearTimeout(skeletonTimer)" in remove
    skeleton = "\n".join(decl for sel, decl in _rules(css()) if sel.startswith(".skeleton"))
    assert "gradient" not in skeleton
    assert set(re.findall(r"opacity:\s*([\d.]+)", skeleton)) == {"0.6"}  # 1 by default, 0.6 on two bars


def test_errors_are_styled_from_the_level_field_only() -> None:
    script = _script()
    assert "if (level === 'error') body.classList.add('is-error');" in script
    assert "startsWith(" not in script[script.index("function addAgentMessage("):script.index("function addUserMessage(")]
    assert "data.level" in script and "view.reply.level" in script


def test_copy_on_the_page_is_sentence_case_without_exclamations() -> None:
    script = _script()
    labels = re.findall(r"^\s+\w+:\s+'([^']+)',$", script[script.index("PHASE_LABELS = {"):script.index("PHASE_PLACEHOLDERS")], re.M)
    assert len(labels) == 14
    for label in labels:
        words = label.split()
        assert all(w == w.lower() for w in words[1:]), label
    for text in re.findall(r"'([A-Z][a-z][^'\n]{10,})'", script):  # prose, not code
        assert "!" not in text, text
    assert "..." not in script[script.index("PHASE_PLACEHOLDERS = {"):script.index("export function phaseLabel")]


# ---------------------------------------------------------------------------
# The intake panel (Phase 3)
# ---------------------------------------------------------------------------

def test_the_page_draws_only_intake_views_it_understands(run_js: Callable[[str], object]) -> None:  # noqa: F811
    good = ('{kind: "intake", title: "How I read your file", lead: null, question: "Does this look right?",'
            ' rows: [{label: "Header row", value: "Row 2"}], notes: [{title: "Adjustments I made", items: ["x"], more: 0}]}')
    cases = run_js(
        f"const good = {good};"
        "return [m.isIntakeView(good), m.isIntakeView({...good, lead: 'Welcome.'}), m.isIntakeView(null),"
        " m.isIntakeView({...good, kind: 'results'}), m.isIntakeView({...good, rows: []}),"
        " m.isIntakeView({...good, rows: [{label: 'a', value: 3}]}),"
        " m.isIntakeView({...good, notes: [{title: 't', items: ['x'], more: -1}]})];"
    )
    assert cases == [True, True, False, False, False, False, False]


def test_the_intake_panel_sets_file_labels_as_text() -> None:
    script = _script()
    panel = script[script.index("function renderIntakePanel(view) {"):]
    panel = panel[:panel.index("\n  }\n")]
    assert "innerHTML" not in panel
    for field in ("row.label", "row.value", "item", "view.title", "view.question", "note.title"):
        assert f"textContent = {field}" in panel, field
    # The lead is the server's own Markdown and goes through the escaping renderer.
    assert "lead.innerHTML = renderMarkdown(view.lead)" in script
