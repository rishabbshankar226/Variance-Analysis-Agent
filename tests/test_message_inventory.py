"""M6: the message inventory script reads every intake message from the source and checks it by the rules file."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("message_inventory", ROOT / "scripts" / "message_inventory.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["message_inventory"] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


INVENTORY = _script()


def _message(text: str, kind: str = "refusal", *, chips: bool = False, path: str = "src/variance_agent/intake.py",
             wrapped: str = "") -> object:
    return INVENTORY.Message(path, 1, kind, text, chips, "", wrapped)


def test_jargon_is_checked_by_the_rules_files_definitions() -> None:
    assert _message("Columns {a!r} and {b} normalize to the same key.").jargon() == ["repr quoting", "word 'normalize'"]
    assert _message("Supply an exact --sheet name.").jargon() == ["flag --sheet"]
    assert _message("Optionally pass --sheet to choose one.").jargon() == []
    assert _message("You can pass --sheet (optional) to choose one.").jargon() == []
    assert _message("Row Kind must be Detail.").jargon() == ["word 'Row Kind'"]
    assert _message("Field budget_ytd is blank.").jargon() == ["snake_case 'budget_ytd'"]
    assert _message("A ValueError was raised.").jargon() == ["exception name ValueError"]
    # A placeholder prints a value, not a key: '{line_item}' is not snake_case jargon.
    assert _message("{line_item}: the Budget cell is blank. Fill it in and upload the file again.").jargon() == []


def test_only_an_error_is_scored_for_a_fix() -> None:
    assert _message("The file is empty.").offers_fix() is False
    assert _message("The file is empty. Upload a file with a header row.").offers_fix() is True
    assert _message("Rates differ, so give two filings in one currency.").offers_fix() is True
    assert _message("Not here. If the filing puts them elsewhere, upload that document.").offers_fix() is True
    assert _message("Choose a sheet.", "error reply").offers_fix() is True
    assert _message("Period set to Q3 2026.", "reply").offers_fix() is None
    assert _message("Something failed.", "error reply", chips=True).offers_fix() is True
    assert _message("Excel archive is damaged.", wrapped="shown after a wrapper").offers_fix() is None


def test_the_inventory_lists_messages_the_chat_never_shows_without_counting_them() -> None:
    messages = INVENTORY.inventory()
    by_reason = {m.not_shown for m in messages}
    assert {"protocol reply", "strict reader (command line and API)", "internal check",
            "check of the API's arguments", "caught where it is raised"} <= by_reason
    server = [m for m in messages if m.module == "server.py" and m.text == "Invalid JSON."]
    assert server and all(not m.seen_in_chat for m in server)
    cells = [m for m in messages if m.wrapped.startswith("shown under \"Fix these cells")]
    assert cells and all(m.seen_in_chat and m.offers_fix() is None for m in cells)


def test_an_engine_error_is_checked_as_the_chat_shows_it() -> None:
    message = INVENTORY.Message("src/variance_agent/analysis.py", 1, "raise ValueError",
                                "Excel archive is corrupt.", False)
    assert message.shown != message.text
    assert message.jargon() == []


def test_the_markdown_keeps_the_inventorys_columns() -> None:
    text = INVENTORY.markdown(INVENTORY.inventory(), "abc1234")
    assert "| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |" in text
    assert "at commit `abc1234`" in text
