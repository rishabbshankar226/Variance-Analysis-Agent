"""How much an Excel number format scales what a cell displays.

A unit caption such as "($ in thousands)" describes what Excel shows. A format can show a
cell's stored value scaled: each comma after the last digit placeholder of a section divides
the display by 1,000 (`#,##0,` shows 110000 as 110), and each `%` multiplies it by 100. Commas
between digit placeholders are grouping. Intake reconciles the caption with these divisors so
an amount stored at full scale is never scaled a second time (PLAN.md, R2).
"""

from __future__ import annotations

from decimal import Decimal

_DIGITS = frozenset("0#?")


def _sections(code: str) -> list[str]:
    """Split a format code on `;`, outside quotes, escapes and brackets."""
    sections, current, index = [], [], 0
    quoted = False
    while index < len(code):
        char = code[index]
        if quoted:
            quoted = char != '"'
        elif char == '"':
            quoted = True
        elif char == "\\" or char in "_*":
            current.append(code[index:index + 2])
            index += 2
            continue
        elif char == "[":
            end = code.find("]", index)
            end = len(code) - 1 if end == -1 else end
            current.append(code[index:end + 1])
            index = end + 1
            continue
        elif char == ";":
            sections.append("".join(current))
            current, index = [], index + 1
            continue
        current.append(char)
        index += 1
    sections.append("".join(current))
    return sections[:4]


def _tokens(section: str) -> list[str] | None:
    """Digit placeholders, commas, the decimal point and percent signs; None when unreadable."""
    tokens: list[str] = []
    index = 0
    while index < len(section):
        char = section[index]
        if char == '"':
            end = section.find('"', index + 1)
            index = len(section) if end == -1 else end + 1
            continue
        if char == "\\" or char in "_*":
            index += 2
            continue
        if char == "[":
            end = section.find("]", index)
            if section[index + 1:index + 2] in {"<", ">", "="}:
                return None  # a condition picks the section by value, not by sign
            index = len(section) if end == -1 else end + 1
            continue
        if char in "Ee" and section[index + 1:index + 2] in {"+", "-"}:
            return None  # scientific display
        if char in _DIGITS or char in ",.%":
            tokens.append("0" if char in _DIGITS else char)
        index += 1
    return tokens


def _section_for(sections: list[str], value: Decimal) -> str:
    if value < 0 and len(sections) >= 2:
        return sections[1]
    if value == 0 and len(sections) >= 3:
        return sections[2]
    return sections[0]


def _scaling(tokens: list[str]) -> int | None:
    """Count scaling commas; None when a comma's role cannot be read."""
    scaling = 0
    seen_point = False
    for position, token in enumerate(tokens):
        if token == ".":
            seen_point = True
        if token != ",":
            continue
        before = next((t for t in reversed(tokens[:position]) if t != ","), None)
        after = next((t for t in tokens[position + 1:] if t != ","), None)
        if before is None:
            continue  # a comma before any digit is printed as a literal
        if after == "0" and not seen_point:
            continue  # grouping between integer digits
        if after is None and before in {"0", "%"}:
            scaling += 1
            continue
        return None  # between fractional digits, or just before the decimal point
    return scaling


def display_divisor(code: str, value: Decimal) -> Decimal | None:
    """What the stored `value` is divided by when Excel displays it under `code`.

    1 for General and plain formats, 1000 per scaling comma, 1/100 per percent sign. None
    when this reader cannot tell (a conditional section, scientific display, a comma it
    cannot place); the caller treats that as a format it cannot interpret.
    """
    sections = _sections(code)
    if any(_tokens(section) is None for section in sections):
        return None
    tokens = _tokens(_section_for(sections, value))
    assert tokens is not None
    commas = _scaling(tokens)
    if commas is None:
        return None
    return Decimal(1).scaleb(3 * commas - 2 * tokens.count("%"))


def shows_percent(code: str, value: Decimal) -> bool:
    """Whether the section that displays `value` shows it as a percentage."""
    tokens = _tokens(_section_for(_sections(code), value))
    return tokens is not None and "%" in tokens
