"""List every user-facing message of the intake workflow and check it against the intake rules (M6).

Usage: python scripts/message_inventory.py [--markdown PATH] [--failing]

A message is the text of a ``raise``, a chat ``Response(text=...)``, an intake refusal
(``fatal_error_message=``, ``_fail(...)``, ``_statement_refusal(...)``) or an upload refusal in the
chat server. Each is read from the source with ``ast``, so the listing is the code's own text:
placeholders show the expression they print, as ``{line_item}``.

The checks follow the definitions in ``.agents/rules/variance-intake.md``, which apply to "a message
Maya sees":

- **Jargon**: a snake_case key or ``repr()`` quoting, an exception name, CLI flag syntax (unless the
  message says the flag is optional), one of the rule's forbidden words, or an exit code.
  Placeholders are values, not keys, so only the literal text is checked, except that a ``!r``
  placeholder is repr quoting.
- **Offers a fix**: for an error or refusal, a sentence telling the reader what to do (it opens
  with a verb such as "Upload", "Choose" or "Add") or chips that apply it. A confirmation or a
  question is not scored for a fix.

A message is counted when a chat reader can see it. The rest are listed with the reason they are not:
the command line's own messages, the strict reader the chat never uses, the server's protocol
replies, internal checks, checks of the API's arguments, a raise caught where it is raised, and
clauses another message completes. A message shown inside another (an Excel or JSON read error
after "Could not read ...", a cell under "Fix these cells ...") is checked for jargon; its wrapper
carries the fix. ``analysis.py``'s errors reach the chat through ``plain_analysis_error``, so the
text checked is what that shows.

``--failing`` lists the counted messages that fail either check.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "variance_agent"

# The intake workflow: reading a file and preparing it for analysis, in the chat and its readers. The
# inventory written by hand at a3ce6bb covered parsing, Excel, the engine, the chat and its server; the
# readers added since (assisted intake, two-file joins, PDF and Inline XBRL filings, LTM, covenant metrics)
# join them.
INTAKE = ("parsing.py", "excel.py", "analysis.py", "intake.py", "join.py", "pdf_tables.py", "ixbrl.py",
          "statement_shape.py", "ltm.py", "metrics.py", "chat/")
# Replies only a client that isn't the page can draw: the page always sends a well-formed request from its own
# origin, so these are listed under the server but not counted.
PROTOCOL = {"Not found.", "File not found.", "Expected multipart/form-data.", "The upload has no multipart boundary.",
            "Expected application/json.", "Invalid JSON.", "Empty message.", "Unexpected Host header.",
            "Cross-origin requests are not allowed.", "Expected a JSON object with a text string.",
            "Invalid Content-Length.", "Static file not found: {filename}"}
INTERNAL = {"RuntimeError", "AssertionError", "NotImplementedError", "TypeError"}
REFUSALS = {"_fail", "_statement_refusal", "_refusal", "refuse", "_json_error"}

# (module, function) -> the message its messages are shown inside, which carries the fix.
WRAPPED = {
    ("intake.py", "parse_assisted_decimal"): "shown under \"Fix these cells and upload the file again\"",
    **{("excel.py", name): "shown after \"Could not read Excel file ...\""
       for name in ("inspect_workbook", "_worksheet_scan", "cell_value")},
    **{("parsing.py", name): "shown after \"Could not read JSON data ...\""
       for name in ("load_json_text", "load_json_value", "_json_object", "_validate_json_depth",
                    "_reject_json_constant")},
}
# (module, function) -> why a chat reader never sees its messages.
NOT_SHOWN = {
    # The strict reader: the command line and the API read a file with it unless --assisted is given. The
    # chat reads every file with assisted intake.
    **{("parsing.py", name): "strict reader (command line and API)"
       for name in ("load_input", "load_csv_text", "validate_input_format", "_validate_capture",
                    "_normalized_headers", "normalize_row")},
    # The engine re-checks values intake has already read; a typed threshold's error is caught and replaced.
    **{("parsing.py", name): "re-check of a value already read (API)" for name in ("parse_decimal", "_require_finite")},
    ("analysis.py", "_validate_comparison"): "check of the API's arguments",
    ("analysis.py", "_verify_result"): "internal check",
}
# Engine messages only a caller of the API can trigger: the chat builds the configuration and rows itself.
API_CHECKS = ("Configuration must be", "Rows must be a list", "Materiality thresholds must be",
              "Comparison basis must be", "Type map value for", "Dataset contains no data rows",
              "Dataset exceeds the supported row count")
# Messages the chat can't reach: it reads a file holding both columns on its own before any join.
COMMAND_LINE_TEXT = ("'{comparison_name}' already has an Actual column", "'{actual_name}' already has a comparison")

FORBIDDEN = re.compile(r"\b(normali[sz]e[sd]?|alias(?:es)?|schema|OOXML|archive|XML|DTD|payload|Row Kind|Unclassified)\b")
SNAKE = re.compile(r"(?<![\w./\\-])[a-z][a-z0-9]*_[a-z0-9_]+(?![\w./-])")
EXCEPTION = re.compile(r"\b(?:[A-Z][a-z]+)+(?:Error|Exception)\b|\bBadZipFile\b|\bKeyError\b|\bStopIteration\b")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]+")
EXIT_CODE = re.compile(r"\bexit(?:ed)?(?: with)? (?:code|status) \d", re.IGNORECASE)
FIX_VERBS = (
    "add", "answer", "ask", "change", "check", "choose", "click", "combine", "compare", "confirm", "convert",
    "count", "delete", "drop", "edit", "enter", "export", "fill", "fix", "give", "install", "keep", "label",
    "leave", "list", "make", "map", "mark", "move", "open", "paste", "pick", "please", "provide", "put", "re-save",
    "re-upload", "remove", "rename", "replace", "reply", "resave", "run", "save", "select", "send", "set", "show",
    "shorten", "split", "start", "supply", "switch", "tell", "try", "turn", "type", "unhide", "unmerge", "upload",
    "use", "wait",
)
# A fix opens a sentence, a list item or a bolded chip name, perhaps after a condition ("If the filing puts
# them in another document, upload that document"), or follows "so", "or" or "then" ("..., so give two
# filings in one currency").
FIX = re.compile(r"(?:(?:^|[.:;!?]\s+)(?:if\b[^.]*?,\s+|otherwise,?\s+)?|[,;]\s+(?:so|or|then|and)\s+|\bso\s+"
                 r"|\n[-*\s]*|\*\*)(?:" + "|".join(re.escape(v) for v in FIX_VERBS) + r")\b", re.IGNORECASE)


@dataclass
class Message:
    path: str
    line: int
    kind: str  # raise <Name>, refusal, reply or error reply
    text: str
    chips: bool
    not_shown: str = ""  # why a chat reader never sees it; "" when one can
    wrapped: str = ""  # the message it is shown inside, which carries the fix

    @property
    def module(self) -> str:
        return Path(self.path).name

    @property
    def seen_in_chat(self) -> bool:
        return not self.not_shown

    @property
    def shown(self) -> str:
        """The text a chat reader sees: an engine error is rewritten by plain_analysis_error first."""
        if self.module == "analysis.py":
            from variance_agent.intake import plain_analysis_error
            return plain_analysis_error(self.text)
        return self.text

    @property
    def is_error(self) -> bool:
        return self.kind != "reply"

    def jargon(self) -> list[str]:
        text = self.shown
        literal = re.sub(r"\{[^{}]*\}", "X", text)
        found = []
        if "!r}" in text or re.search(r"\{[^{}]*repr\(", text):
            found.append("repr quoting")
        if (match := SNAKE.search(literal)) is not None:
            found.append(f"snake_case '{match.group()}'")
        if (match := EXCEPTION.search(literal)) is not None:
            found.append(f"exception name {match.group()}")
        if (match := FLAG.search(literal)) is not None and "optional" not in literal.lower():
            found.append(f"flag {match.group()}")
        if (match := FORBIDDEN.search(literal)) is not None:
            found.append(f"word '{match.group()}'")
        if EXIT_CODE.search(literal):
            found.append("exit code")
        return found

    def offers_fix(self) -> bool | None:
        """None where no fix is asked of the message: a confirmation, or one shown inside a wrapper."""
        if not self.is_error or self.wrapped:
            return None
        return self.chips or FIX.search(self.shown.strip()) is not None

    def failing(self) -> list[str]:
        return [*self.jargon(), *(["no fix"] if self.offers_fix() is False else [])]


def _clause(text: str) -> bool:
    """A clause another message completes ("the filing has more tables than can be read")."""
    text = text.strip()
    return text[:1].islower() or text[-1:] not in set(".!?:}`*)")


def _render(node: ast.AST, constants: dict[str, str]) -> str | None:
    """The text a string expression prints, with each placeholder shown as {expression}; None if not text.

    A placeholder naming a module-level text constant shows the constant's text.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue):
                if isinstance(value.value, ast.Name) and value.value.id in constants and value.conversion == -1:
                    parts.append(constants[value.value.id])
                    continue
                conversion = {114: "!r", 115: "!s", 97: "!a"}.get(value.conversion, "")
                parts.append("{" + ast.unparse(value.value) + conversion + "}")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _render(node.left, constants), _render(node.right, constants)
        if left is not None or right is not None:
            return (left if left is not None else "{" + ast.unparse(node.left) + "}") + \
                   (right if right is not None else "{" + ast.unparse(node.right) + "}")
    if isinstance(node, ast.IfExp):
        body, orelse = _render(node.body, constants), _render(node.orelse, constants)
        if body is not None and orelse is not None:
            return body if len(body) >= len(orelse) else orelse
        return body if body is not None else orelse
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        texts = [text for text in (_render(value, constants) for value in node.values) if text is not None]
        return texts[0] if texts else None
    return None


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _handler_names(handler: ast.ExceptHandler) -> set[str]:
    kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type] if handler.type else []
    return {kind.id if isinstance(kind, ast.Name) else kind.attr if isinstance(kind, ast.Attribute) else ""
            for kind in kinds}


def _messages(path: Path) -> list[Message]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = path.relative_to(ROOT).as_posix()
    constants = {target.id: node.value.value for node in tree.body if isinstance(node, ast.Assign)
                 and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
                 for target in node.targets if isinstance(target, ast.Name)}
    found: list[Message] = []

    def add(node: ast.AST, kind: str, text: str | None, function: str, caught: bool, *, chips: bool = False,
            internal: bool = False) -> None:
        if not text or not text.strip():
            return
        text = " ".join(text.split())
        key = (path.name, function)
        if internal:
            not_shown = "internal check"
        elif caught:
            not_shown = "caught where it is raised"
        elif key in NOT_SHOWN:
            not_shown = NOT_SHOWN[key]
        elif path.name == "analysis.py" and text.startswith(API_CHECKS):
            not_shown = "check of the API's arguments"
        elif text.startswith(COMMAND_LINE_TEXT):
            not_shown = "command line only"
        elif text in PROTOCOL:
            not_shown = "protocol reply"
        elif key not in WRAPPED and not kind.endswith("reply") and _clause(text):
            not_shown = "a clause another message completes"
        else:
            not_shown = ""
        found.append(Message(relative, getattr(node, "lineno", 0), kind, text, chips, not_shown,
                             WRAPPED.get(key, "")))

    def visit(node: ast.AST, function: str, catching: frozenset[str]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            function, catching = node.name, frozenset()
        if isinstance(node, ast.Try):
            caught = frozenset(name for handler in node.handlers for name in _handler_names(handler))
            for statement in node.body:
                visit(statement, function, catching | caught)
            for part in [*node.handlers, *node.orelse, *node.finalbody]:
                visit(part, function, catching)
            return
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
            name = _call_name(node.exc)
            add(node, f"raise {name}", _render(node.exc.args[0], constants), function,
                name in catching or "Exception" in catching, internal=name in INTERNAL)
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            keywords = {k.arg: k.value for k in node.keywords if k.arg}
            if name == "Response" and "text" in keywords:
                chips = "chips" in keywords and not (isinstance(keywords["chips"], ast.Constant)
                                                     and keywords["chips"].value is None)
                level = keywords.get("level")
                error = isinstance(level, ast.Constant) and level.value == "error"
                add(node, "error reply" if error else "reply", _render(keywords["text"], constants), function,
                    False, chips=chips)
            elif "fatal_error_message" in keywords:
                add(node, "refusal", _render(keywords["fatal_error_message"], constants), function, False)
            elif name in REFUSALS and node.args:
                message = node.args[-1] if name == "_statement_refusal" else node.args[0]
                add(node, "refusal", _render(message, constants), function, False)
        for child in ast.iter_child_nodes(node):
            visit(child, function, catching)

    visit(tree, "", frozenset())
    return sorted(found, key=lambda m: m.line)


def inventory() -> list[Message]:
    paths = [path for path in sorted(SOURCE.rglob("*.py"))
             if any(path.relative_to(SOURCE).as_posix().startswith(name) for name in INTAKE)]
    return [m for path in paths for m in _messages(path)]


def failing(messages: list[Message] | None = None) -> list[Message]:
    """The messages a chat reader can see that fail a check."""
    return [m for m in (inventory() if messages is None else messages) if m.seen_in_chat and m.failing()]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("`", "'")


def _share(count: int, whole: int) -> str:
    return f"{100 * count / whole:.1f}%" if whole else "0.0%"


def markdown(messages: list[Message], commit: str) -> str:
    counted = [m for m in messages if m.seen_in_chat]
    errors = [m for m in counted if m.offers_fix() is not None]
    jargon = sum(bool(m.jargon()) for m in counted)
    fixes = sum(bool(m.offers_fix()) for m in errors)
    lines = [
        "# Intake Message Inventory", "",
        "This document lists every user-facing message of the intake workflow (reading a file and preparing it "
        f"for analysis) in the source at commit `{commit}`: {', '.join(f'`{name}`' for name in INTAKE)}. "
        "[`scripts/message_inventory.py`](../scripts/message_inventory.py) writes it, so it changes only with "
        "the code. The inventory before it was written by hand at `a3ce6bb`.",
        "",
        "Per the definitions in [`.agents/rules/variance-intake.md`](../.agents/rules/variance-intake.md), which "
        "apply to a message Maya sees:",
        "- **Jargon**: a snake_case key or `repr()` quoting, an exception name, CLI flag syntax (unless the "
        "message says it is optional), one of the words \"normalize,\" \"alias,\" \"schema,\" \"OOXML,\" "
        "\"archive,\" \"XML,\" \"DTD,\" \"payload,\" \"Row Kind,\" \"Unclassified\", or an exit code.",
        "- **Offers a Fix**: an error or refusal that tells the reader what to do, or offers chips that do it. A "
        "confirmation or a question is not scored (`n/a`), nor is a message shown inside another that carries "
        "the fix.",
        "",
        "Placeholders such as `{line_item}` show the expression a message prints; they are values, so only "
        "the message's own words are checked, except that `!r` is repr quoting. The counts cover messages a "
        "chat reader can see; the rest are listed with the reason they are not. Engine messages from "
        "`analysis.py` are checked as `plain_analysis_error` shows them in the chat.",
        "", "---", "", "## 1. Summary", "",
        "| Metric | Count | Percentage |", "|---|---|---|",
        f"| **Messages a chat reader can see** | **{len(counted)}** | 100.0% |",
        f"| **Messages Containing Jargon** | **{jargon}** | {_share(jargon, len(counted))} |",
        f"| **Plain-Language Messages** | **{len(counted) - jargon}** | {_share(len(counted) - jargon, len(counted))} |",
        f"| **Errors and refusals scored for a fix** | **{len(errors)}** | {_share(len(errors), len(counted))} |",
        f"| **Errors Offering an Actionable Fix** | **{fixes}** | {_share(fixes, len(errors))} of errors |",
        f"| **Errors With No Fix** | **{len(errors) - fixes}** | {_share(len(errors) - fixes, len(errors))} of errors |",
        f"| Listed, not seen in the chat | {len(messages) - len(counted)} | |",
        "", "### Breakdown by Component", "",
        "| Component Source | Messages Seen | Jargon Messages | Errors Offering a Fix |", "|---|---|---|---|",
    ]
    for path in sorted({m.path for m in counted}):
        mine = [m for m in counted if m.path == path]
        scored = [m for m in mine if m.offers_fix() is not None]
        bad = sum(bool(m.jargon()) for m in mine)
        good = sum(bool(m.offers_fix()) for m in scored)
        lines.append(f"| [`{path.removeprefix('src/')}`](../{path}) | {len(mine)} | {bad} ({_share(bad, len(mine))}) "
                     f"| {good} of {len(scored)} |")
    lines += ["", "---", "", "## 2. Complete Message Inventory"]
    for path in sorted({m.path for m in messages}):
        lines += ["", f"### `{path.removeprefix('src/variance_agent/')}`", "",
                  "| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |", "|---|---|---|---|---|"]
        for m in (m for m in messages if m.path == path):
            reasons = m.jargon()
            fix = m.offers_fix()
            notes = [m.not_shown] if m.not_shown else []
            notes += [m.wrapped] if m.wrapped else []
            if m.module == "analysis.py" and m.shown != m.text:
                notes.append(f"shown as '{_cell(m.shown)}'")
            notes += reasons
            if m.chips:
                notes.append("chips")
            lines.append(f"| `{Path(m.path).name}:{m.line}` | `{_cell(m.text)}` | {'**Yes**' if reasons else 'No'} "
                         f"| {'n/a' if fix is None else 'Yes' if fix else '**No**'} | {'; '.join(notes)} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--markdown", type=Path, help="write the inventory as Markdown to this path")
    parser.add_argument("--failing", action="store_true", help="list the chat messages that fail a check")
    args = parser.parse_args(argv)
    messages = inventory()
    if args.markdown:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                text=True, check=False).stdout.strip() or "unknown"
        args.markdown.write_text(markdown(messages, commit), encoding="utf-8")
    counted = [m for m in messages if m.seen_in_chat]
    bad = failing(messages)
    if args.failing:
        for m in bad:
            print(f"{m.path}:{m.line}\t{'; '.join(m.failing())}\t{m.shown[:160]}")
    print(f"{len(counted)} messages a chat reader can see; {sum(bool(m.jargon()) for m in counted)} with jargon; "
          f"{sum(m.offers_fix() is False for m in counted)} errors with no fix; {len(bad)} failing either check.",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
