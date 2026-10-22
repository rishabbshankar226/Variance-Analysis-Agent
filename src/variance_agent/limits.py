"""Explicit limits for untrusted local financial inputs."""

from typing import Final

MAX_INPUT_BYTES: Final = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES: Final = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS: Final = 2048
MAX_ROWS: Final = 100_000
MAX_COLUMNS: Final = 256
MAX_CELLS: Final = 1_000_000
MAX_TEXT_LENGTH: Final = 128 * 1024
MAX_NUMBER_LENGTH: Final = 4096
MAX_JSON_DEPTH: Final = 128
MAX_XML_DEPTH: Final = 128
MAX_PDF_PAGES: Final = 400
MAX_PDF_SECONDS: Final = 20.0


# Bidirectional controls plus characters that print as nothing (soft hyphen, zero-width space,
# word joiner, byte-order mark). Zero-width joiners (U+200C/U+200D) are left alone: real scripts need them.
_INVISIBLE_CODES = frozenset({
    0x00AD, 0x061C, 0x200B, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2060, 0x2066, 0x2067, 0x2068, 0x2069, 0xFEFF,
})


def validate_text(value: object, *, field: str, nonblank: bool = False) -> str:
    if not isinstance(value, str) or (nonblank and not value.strip()):
        raise ValueError(f"{field} must be {'nonblank ' if nonblank else ''}text.")
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"{field} exceeds the supported text length ({MAX_TEXT_LENGTH}).")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{field} must contain valid Unicode text.") from exc
    return value


def display_text(value: str) -> str:
    """Keep source controls visible without allowing terminal or bidi commands."""
    parts = []
    for char in value:
        code = ord(char)
        if char.isspace():
            parts.append(" ")
        elif code < 32 or 127 <= code <= 159 or code in _INVISIBLE_CODES or 0xE0000 <= code <= 0xE007F:
            parts.append(f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}")
        else:
            parts.append(char)
    return " ".join("".join(parts).split())
