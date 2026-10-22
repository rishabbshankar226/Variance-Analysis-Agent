"""Chat hardening: hostile message sizes, digit bounds and pasted tables (WS2 P0)."""

from __future__ import annotations

import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path

import pytest

from tests.chat_helpers import SAMPLE_CSV, analysed
from variance_agent.analysis import analyze_rows
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat import intent as intent_module
from variance_agent.chat.intent import parse_intent
from variance_agent.chat.session import Phase, Session
from variance_agent.models import AnalysisConfig

HOSTILE_LENGTH = 20_000
HOSTILE_MESSAGES = {
    "what-if spaces": "what if" + " " * HOSTILE_LENGTH + "x",
    "compare spaces": "compare a" + " " * HOSTILE_LENGTH + "x",
    "show spaces": "show" + " " * HOSTILE_LENGTH + "x",
    "threshold digits": "threshold " + "1" * HOSTILE_LENGTH + "x",
    "why letters": "why " + "x" * HOSTILE_LENGTH,
    "why words": "why " + "abcdefghij " * (HOSTILE_LENGTH // 11),
    "compare separators": "compare a " + "to " * (HOSTILE_LENGTH // 3) + "b",
    "top digits": "top " + "9" * HOSTILE_LENGTH,
    "bare digits": "9" * HOSTILE_LENGTH,
    "what-if digits": "what if cut revenue by " + "1" * HOSTILE_LENGTH,
    "tabs": "what if\t" * (HOSTILE_LENGTH // 8),
}


# A regression here would hang for minutes, so every hostile message runs in a child process
# that is killed after SUBPROCESS_TIMEOUT seconds instead of hanging the test run.
SUBPROCESS_TIMEOUT = 10
CHILD = """
import sys, time
sys.path.insert(0, {root!r})
from tests.chat_helpers import analysed
from variance_agent.chat.handlers import handle_message
from variance_agent.chat.session import Phase, Session
phase = sys.argv[1]
session = analysed() if phase == "exploring" else Session()
if phase != "exploring":
    session.phase = Phase(phase)
text = sys.stdin.read()
before = (session.phase, session.period, session.last_focused_item)
start = time.perf_counter()
response = handle_message(session, text)
print(time.perf_counter() - start)
assert response.text
assert (session.phase, session.period, session.last_focused_item) == before
"""


def _assert_quick(phase: str, text: str) -> None:
    root = str(Path(__file__).resolve().parent.parent)
    try:
        done = subprocess.run(
            [sys.executable, "-c", CHILD.format(root=root), phase],
            input=text, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"no answer within {SUBPROCESS_TIMEOUT}s")
    assert done.returncode == 0, done.stderr[-500:]
    assert float(done.stdout.strip()) < 0.5


@pytest.mark.parametrize("label", sorted(HOSTILE_MESSAGES))
def test_hostile_message_is_answered_quickly_while_exploring(label: str) -> None:
    _assert_quick("exploring", HOSTILE_MESSAGES[label])


@pytest.mark.parametrize("label", ["what-if spaces", "compare separators", "threshold digits"])
@pytest.mark.parametrize(
    "phase", [Phase.AWAITING_FILE, Phase.AWAITING_PERIOD, Phase.AWAITING_THRESHOLDS],
)
def test_hostile_message_is_answered_quickly_in_early_phases(label: str, phase: Phase) -> None:
    _assert_quick(phase.value, HOSTILE_MESSAGES[label])


def test_overlong_message_gets_a_friendly_reply() -> None:
    session = analysed()
    response = handle_message(session, "why " + "x" * 2000)
    assert "too long" in response.text.lower()
    assert response.phase == Phase.EXPLORING


@pytest.mark.parametrize("label", sorted(HOSTILE_MESSAGES))
def test_hostile_parse_intent_alone_is_fast(label: str) -> None:
    script = (
        "import sys, time; sys.path.insert(0, sys.argv[1]);"
        "from variance_agent.chat.intent import parse_intent;"
        "t = time.perf_counter(); parse_intent(sys.stdin.read()); print(time.perf_counter() - t)"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", script, str(Path(__file__).resolve().parent.parent)],
            input=HOSTILE_MESSAGES[label], capture_output=True, text=True,
            timeout=SUBPROCESS_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"parse_intent did not return within {SUBPROCESS_TIMEOUT}s")
    assert float(done.stdout.strip()) < 0.5


@pytest.mark.parametrize("prefix", ["top ", "why ", "detail ", ""])
def test_giant_digit_runs_do_not_crash(prefix: str) -> None:
    session = analysed()
    response = handle_message(session, prefix + "9" * 4301)
    assert response.text


def test_digit_runs_are_bounded_where_they_are_parsed() -> None:
    assert parse_intent("top " + "9" * 450).intent_id != "top_n"
    assert parse_intent("top 999999999").intent_id == "top_n"


def _paste(rows: int) -> str:
    lines = ["Line Item\tType\tBudget\tActual"]
    for i in range(rows):
        kind = "Revenue" if i % 5 == 0 else "Expense"
        lines.append(f"Account number {i:04d} description\t{kind}\t{1000 + i}\t{1100 + i}")
    return "\n".join(lines) + "\n"


def test_long_pasted_table_still_parses() -> None:
    text = _paste(150)
    assert len(text) > 3 * intent_module.MAX_ROUTING_CHARS
    session = Session()
    response = handle_message(session, text)
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert session.source_name == "pasted_data.tsv"
    assert session.source_bytes == text.strip().encode("utf-8")
    assert "too long" not in response.text.lower()


def test_pasted_table_is_not_accepted_after_a_file_is_loaded() -> None:
    session = analysed()
    response = handle_message(session, _paste(150))
    assert "too long" in response.text.lower()
    assert session.phase == Phase.EXPLORING


NBSP = chr(0xA0)
CURLY_APOSTROPHE = chr(0x2019)
CURLY_OPEN, CURLY_CLOSE = chr(0x201C), chr(0x201D)
ZERO_WIDTH_SPACE = chr(0x200B)
IDEOGRAPHIC_SPACE = chr(0x3000)


def test_routing_copy_folds_unicode_but_originals_are_kept() -> None:
    normalize_for_routing = intent_module.normalize_for_routing
    messy = f"why{NBSP}{NBSP}Bob{CURLY_APOSTROPHE}s {CURLY_OPEN}Burgers{CURLY_CLOSE}?"
    assert normalize_for_routing(messy) == 'why Bob\'s "Burgers"?'
    fullwidth = "".join(chr(ord(c) + 0xFEE0) if c.isalnum() else c for c in "top 3")
    assert normalize_for_routing(fullwidth.replace(" ", IDEOGRAPHIC_SPACE)) == "top 3"
    assert normalize_for_routing(f"a{ZERO_WIDTH_SPACE}b  c\n d") == "ab c d"


def test_period_keeps_the_typed_text_not_the_routing_copy() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "a.csv")
    assert session.phase == Phase.AWAITING_PERIOD
    handle_message(session, f"FY{NBSP}2026.")
    assert session.period == f"FY{NBSP}2026"


# ---- a big file must not make every unmatched question slow ---------------------------------


def _big_session(lines: int = 20_000) -> Session:
    rows: list[dict[str, object]] = [
        {"line_item": f"Account {i:06d} operating cost centre",
         "type": "Expense" if i % 3 else "Revenue", "budget": str(1000 + i), "actual": str(1100 + i)}
        for i in range(lines)
    ]
    result = analyze_rows(rows, AnalysisConfig(
        period="Q3", dollar_threshold=Decimal("50"), percent_threshold=Decimal("0.05"),
    ))
    session = Session()
    session.phase = Phase.EXPLORING
    session.result = result
    return session


@pytest.mark.parametrize("prompt", [
    "why " + "x" * 300,
    "why account 99",
    "why accout 000099",
    "details on how zebra is doing",
    "show me banana",
    "tell me something about zebra crossing nothing",
    "profit sharing looks high",
], ids=["long-query", "partial-name", "typo", "sentence", "show-me", "unknown-sentence", "keyword"])
def test_unmatched_questions_on_a_big_file_stay_fast(prompt: str) -> None:
    session = _big_session()
    start = time.perf_counter()
    response = handle_message(session, prompt)
    assert time.perf_counter() - start < 0.5
    assert response.text


def test_a_typo_still_gets_a_suggestion_on_a_big_file() -> None:
    response = handle_message(_big_session(), "why accout 000099 operating cost centre")
    assert "Did you mean" in response.text
    assert "Account 000099 operating cost centre" in response.text


# ---- typed answers go through the same folding as commands -----------------------------------


def test_typed_threshold_in_full_width_digits_is_understood() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "a.csv")
    handle_message(session, "Q3 2026")
    fullwidth = "".join(chr(ord(c) + 0xFEE0) if c.isdigit() else c for c in "$10,000 or 5%")
    handle_message(session, fullwidth)
    assert session.phase == Phase.AWAITING_CURRENCY
    assert session.dollar_threshold == Decimal(10000)


def test_classification_answer_with_a_non_breaking_space_is_understood() -> None:
    csv = b"Line Item,Type,Budget,Actual\nSales,Revenue,100,120\nMystery,,50,70\n"
    session = Session()
    handle_upload(session, csv, "a.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$10 or 5%")
    handle_message(session, "USD")
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED
    handle_message(session, f"Skip{NBSP}all")
    assert session.phase == Phase.EXPLORING
