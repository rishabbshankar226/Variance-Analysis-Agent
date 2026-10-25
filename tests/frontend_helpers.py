"""Readers for the packaged chat page and its stylesheet, shared by the frontend test modules.

The stylesheet keeps every colour as a hex token inside a theme block: the light `:root` first and
the dark `:root` inside `@media (prefers-color-scheme: dark)`. A token may name another token with
`var(--name)`. A theme block these helpers cannot read fails the test that asks for it.
"""

from __future__ import annotations

import importlib.resources
import re

THEMES = ("light", "dark")
_HEX = re.compile(r"#[0-9a-fA-F]{6}")
_DARK_MEDIA = re.compile(r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{")


def packaged(name: str) -> bytes:
    return importlib.resources.files("variance_agent").joinpath("static", name).read_bytes()


def css() -> str:
    return packaged("chat.css").decode("utf-8")


def _block_after(text: str, start: int) -> str:
    """The body of the `{ ... }` block whose opening brace is the first one at or after `start`."""
    opened = text.index("{", start)
    depth = 0
    for i in range(opened, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[opened + 1:i]
    raise AssertionError("unbalanced braces in chat.css")


def theme_block(theme: str, stylesheet: str | None = None) -> str:
    """The declarations of one theme's `:root` block."""
    sheet = css() if stylesheet is None else stylesheet
    if theme == "light":
        first = re.search(r"(?m)^:root\s*\{", sheet)
        assert first, "chat.css has no top-level :root block"
        return _block_after(sheet, first.start())
    if theme == "dark":
        media = _DARK_MEDIA.search(sheet)
        assert media, "chat.css has no @media (prefers-color-scheme: dark) block"
        body = _block_after(sheet, media.start())
        inner = re.search(r":root\s*\{", body)
        assert inner, "the dark media block has no :root"
        return _block_after(body, inner.start())
    raise AssertionError(f"unknown theme {theme!r}")


def theme_tokens(theme: str, stylesheet: str | None = None) -> dict[str, str]:
    """Every custom property of a theme, with `var(--x)` references resolved.

    The dark block overrides the light one, so a dark token it leaves out keeps its light value.
    """
    def declarations(block: str) -> dict[str, str]:
        return {name: value.strip() for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", block)}

    values = declarations(theme_block("light", stylesheet))
    if theme == "dark":
        values.update(declarations(theme_block("dark", stylesheet)))

    def resolve(name: str, seen: tuple[str, ...] = ()) -> str:
        assert name not in seen, f"--{name} refers to itself"
        assert name in values, f"--{name} is not defined in the {theme} theme"
        ref = re.fullmatch(r"var\(--([\w-]+)\)", values[name])
        return resolve(ref[1], (*seen, name)) if ref else values[name]

    return {name: resolve(name) for name in values}


def colour(theme: str, name: str, stylesheet: str | None = None) -> str:
    """A colour token of a theme as `#rrggbb`; anything else fails the test."""
    value = theme_tokens(theme, stylesheet)[name]
    assert _HEX.fullmatch(value), f"--{name} in the {theme} theme is {value!r}, not a #rrggbb colour"
    return value.lower()


def luminance(hex_colour: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(foreground: str, background: str) -> float:
    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)
