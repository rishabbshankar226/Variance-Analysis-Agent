"""A tiny standard-library PDF writer for synthetic filing fixtures.

It places Helvetica text at exact positions so tests control the layout a PDF
reader sees. Text is WinAnsi encoded; use "—" for an em dash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PAGE_WIDTH = 612
PAGE_HEIGHT = 792

# Helvetica advance widths (per 1000 em) for the characters right-aligned in fixtures.
_WIDTHS = {**{str(d): 556 for d in range(10)}, ",": 278, ".": 278, "(": 333, ")": 333,
           "$": 556, "—": 1000, "-": 333, " ": 278, "%": 889}
_AVERAGE_WIDTH = 520


def text_width(text: str, size: float) -> float:
    return sum(_WIDTHS.get(ch, _AVERAGE_WIDTH) for ch in text) * size / 1000


def _escape(text: str) -> bytes:
    raw = text.encode("cp1252")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


@dataclass
class Page:
    """One page; y is measured from the top so fixtures read top to bottom."""

    ops: list[bytes] = field(default_factory=list)

    def text(self, x: float, y: float, text: str, size: float = 9) -> None:
        self.ops.append(
            b"BT /F1 %.2f Tf %.2f %.2f Td (%s) Tj ET"
            % (size, x, PAGE_HEIGHT - y, _escape(text))
        )

    def right(self, x_right: float, y: float, text: str, size: float = 9) -> None:
        self.text(x_right - text_width(text, size), y, text, size)

    def center(self, x_center: float, y: float, text: str, size: float = 9) -> None:
        self.text(x_center - text_width(text, size) / 2, y, text, size)

    def box(self, x: float, y: float, w: float, h: float) -> None:
        """Draw a filled rectangle (no text), like a scanned page image."""
        self.ops.append(b"%.2f %.2f %.2f %.2f re f" % (x, PAGE_HEIGHT - y - h, w, h))


def write_pdf(path: Path, pages: list[Page]) -> None:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # page tree, filled in below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    kids = []
    for page in pages:
        stream = b"\n".join(page.ops)
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        content_ref = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
            % (PAGE_WIDTH, PAGE_HEIGHT, content_ref)
        )
        kids.append(b"%d 0 R" % len(objects))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(pages))

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref)
    path.write_bytes(bytes(out))
