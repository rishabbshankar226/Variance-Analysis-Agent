"""Regression tests for defects found in the Chrome QA pass (docs/qa/CHROME_QA_2026-10-21.md).

Every expectation is taken from the independent oracle in
``tests/fixtures/chrome_qa/expected`` (``scripts/qa_oracle.py``), never from the
chatbot's own output.
"""

from __future__ import annotations

import copy
import json
import re
import socket
import threading
from decimal import Decimal
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
from typing import Any

import pytest

import variance_agent.cli as cli
from deterministic_conditioning.variance_bridge import generate_verified_commentary
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.intent import parse_intent
from variance_agent.chat.responses import Response, safe_inline
from variance_agent.chat.server import _ChatHandler
from variance_agent.chat.session import Phase, Session

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "chrome_qa"
EXPECTED = FIXTURES / "expected"
FALLBACK = "I couldn't find an account matching"


def oracle(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXPECTED / f"{name}.json").read_text(encoding="utf-8"))
    return data


def fixture_path(name: str) -> Path:
    return ROOT / "examples" / f"{name}.csv" if name.startswith("sample") else FIXTURES / f"{name}.csv"


def start(name: str, *steps: str) -> tuple[Session, Response]:
    session = Session()
    path = fixture_path(name)
    response = handle_upload(session, path.read_bytes(), path.name)
    for step in ("Q3 2026", "$10k or 5%", "USD", *steps):
        response = handle_message(session, step)
    return session, response


def explore(name: str, *steps: str) -> Session:
    session, _ = start(name, *steps)
    assert session.phase == Phase.EXPLORING
    return session


def money(text: str) -> Decimal:
    return Decimal(re.sub(r"[^\d.\-]", "", text))


def line_items(response: Response) -> list[str]:
    return [row.get("Line Item", "") for row in response.table or []]


# ---------------------------------------------------------------------------
# Commentary truthfulness (memo Strategic Takeaway and CLI --commentary)
# ---------------------------------------------------------------------------

COMMENTARY_CASES = [
    ("sample_variance", ()),
    ("fav_net", ()),
    ("unfav_net", ()),
    ("mixed_sign", ()),
    ("edge_values", ()),
    ("names", ()),
    ("structure", ("Skip all",)),
]


def assert_commentary_truthful(text: str, key: dict[str, Any]) -> None:
    totals = key["totals"]
    lower = text.lower()
    if totals["net_direction"] == "U":
        for phrase in ("outpaced", "surplus", "widening", "improving", "solid cash", "balanced performance", "beat"):
            assert phrase not in lower, f"{phrase!r} claimed on a net-unfavourable period: {text}"
    if totals["net_direction"] == "F":
        assert "shortfall" not in lower, text
    if not totals["actual_margin_negative"]:
        assert "negative territory" not in lower and "turned negative" not in lower, text
    if totals["margin_move"] != "up":
        assert "widening" not in lower and "improving operating margin" not in lower, text
    if key["material_count"]:
        assert "no unresolved variances" not in lower, text
    assert "cash" not in lower, f"cash is not an input field: {text}"

    directions = {line["line_item"]: line["direction"] for line in key["lines"]}
    review = re.match(r"Review (.+?) immediately", text)
    if review:
        assert directions[review.group(1)] == "U", text
    for name, direction in directions.items():
        if re.search(rf"Favorable variance (?:across|on) {re.escape(name)}\b", text):
            assert direction == "F", text


@pytest.mark.parametrize(("name", "steps"), COMMENTARY_CASES)
def test_cli_commentary_matches_oracle(name: str, steps: tuple[str, ...]) -> None:
    result = explore(name, *steps).result
    assert result is not None
    commentary, summary = generate_verified_commentary(result)
    key = oracle(name)
    assert summary.net_variance_dollars == Decimal(key["totals"]["net_operating_impact"])
    assert_commentary_truthful(commentary, key)


def test_cli_commentary_escapes_source_labels(tmp_path: Path) -> None:
    out = tmp_path / "names.md"
    code = cli.main([str(fixture_path("names")), "--period", "Q3 2026", "--dollar-threshold", "10000",
                     "--percent-threshold", "5", "--commentary", "-o", str(out)])
    assert code == 0
    commentary = out.read_text(encoding="utf-8").split("---")[0]
    assert "<b>" not in commentary and "&lt;b&gt;Bold&lt;/b&gt;" in commentary


@pytest.mark.parametrize(("name", "steps"), COMMENTARY_CASES)
def test_memo_takeaway_matches_oracle_and_cli(name: str, steps: tuple[str, ...]) -> None:
    session = explore(name, *steps)
    memo = handle_message(session, "memo").text
    takeaway = re.search(r"\*\*Strategic Takeaway:\*\* (.+)", memo)
    assert takeaway is not None
    assert_commentary_truthful(takeaway.group(1), oracle(name))
    assert session.result is not None
    assert takeaway.group(1) == safe_inline(generate_verified_commentary(session.result)[0])


def test_commentary_flags_unreconciled_driver_residual() -> None:
    csv = (b"Line Item,Type,Budget,Actual,Budget Volume,Actual Volume,Budget Price,Actual Price\n"
           b"Widget Revenue,Revenue,100000,130000,1000,1100,100,110\n"
           b"Rent Expense,Expense,10000,10000,,,,\n")
    session = Session()
    handle_upload(session, csv, "residual.csv")
    for step in ("Q3 2026", "$10k or 5%", "USD"):
        handle_message(session, step)
    assert session.result is not None
    commentary, summary = generate_verified_commentary(session.result)
    assert summary.unexplained_residual_exists is True
    assert commentary.startswith("While")


# ---------------------------------------------------------------------------
# What-if direction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "what if revenue drops 10%", "what if revenue drop 10%", "what if revenue decrease 10%",
    "what if revenue decreases 10%", "what if revenue fall 10%", "what if revenue falls 10%",
    "what if revenue dropped 10%", "what if we drop revenue by 10%", "what if we cut revenue by 10%",
])
def test_what_if_decrease_verbs_simulate_a_decrease(message: str) -> None:
    session = explore("fav_net")
    text = handle_message(session, message).text
    revenue = Decimal(oracle("fav_net")["totals"]["revenue"]["actual"])
    assert "Simulated Change: **-10.0%**" in text
    assert f"${revenue * Decimal('0.9'):,.2f}" in text


@pytest.mark.parametrize("message", ["what if revenue rises 10%", "what if revenue increases 10%",
                                     "what if we increase revenue by 10%"])
def test_what_if_increase_verbs_simulate_an_increase(message: str) -> None:
    text = handle_message(explore("fav_net"), message).text
    assert "Simulated Change: **+10.0%**" in text


def test_bot_suggested_what_if_chip_simulates_a_decrease() -> None:
    session = explore("fav_net")
    response = handle_message(session, "what if revenue drops 10%")
    assert response.chips is not None and "What if expenses drop 5%?" in response.chips
    text = handle_message(session, "What if expenses drop 5%?").text
    expenses = Decimal(oracle("fav_net")["totals"]["expenses"]["actual"])
    assert "Simulated Change: **-5.0%**" in text
    assert f"${expenses * Decimal('0.95'):,.2f}" in text


def test_what_if_aggregate_table_has_no_duplicate_rows() -> None:
    table = handle_message(explore("fav_net"), "what if revenue drops 10%").table or []
    metrics = [row["Metric"] for row in table]
    assert len(metrics) == len(set(metrics)), metrics


# ---------------------------------------------------------------------------
# Direction wording for neutral rows
# ---------------------------------------------------------------------------

def test_neutral_line_is_not_called_an_overrun() -> None:
    text = handle_message(explore("fav_net"), "rent expense").text
    assert "Rent Expense" in text
    assert "unfavorable" not in text.lower() and "overrun" not in text.lower()
    assert "in line with budget" in text


# ---------------------------------------------------------------------------
# Waterfall reconciliation and subtotal leaks
# ---------------------------------------------------------------------------

def test_waterfall_bars_sum_to_net_with_unclassified_rows() -> None:
    key = oracle("structure")
    table = handle_message(explore("structure", "Skip all"), "waterfall").table or []
    bars = [row for row in table if row["Type"] in {"Revenue", "Expense", "Unclassified"}]
    impact = sum((money(row["Profit Impact ($)"]) for row in bars), Decimal(0))
    assert impact == Decimal(key["totals"]["net_operating_impact"])
    for row in bars:
        if row["Type"] == "Unclassified":
            assert money(row["Profit Impact ($)"]) == 0


@pytest.mark.parametrize("message", ["top 3", "pareto", "highest percent", "biggest wins", "biggest risks",
                                     "material", "revenue", "favorable"])
def test_subtotal_rows_never_appear_as_line_items(message: str) -> None:
    response = handle_message(explore("structure", "Skip all"), message)
    assert "Total Revenue" not in line_items(response)
    assert "**Total Revenue**" not in response.text


def test_pareto_total_excludes_subtotals() -> None:
    key = oracle("structure")
    total = sum((abs(Decimal(line["variance"])) for line in key["lines"]), Decimal(0))
    text = handle_message(explore("structure", "Skip all"), "pareto").text
    assert f"${total:,.2f}" in text


def test_top3_matches_oracle() -> None:
    key = oracle("structure")
    response = handle_message(explore("structure", "Skip all"), "top 3")
    assert line_items(response) == key["top3_by_abs"]


# ---------------------------------------------------------------------------
# Intake flow: no loops, no stale phase
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("steps", [
    ("Expense", "Skip"),
    ("Skip", "Skip"),
    ("Expense", "Skip all"),
    ("Skip all",),
])
def test_unclassified_resolution_always_reaches_exploring(steps: tuple[str, ...]) -> None:
    session, response = start("structure", *steps)
    assert session.phase == Phase.EXPLORING
    assert response.phase == Phase.EXPLORING
    assert "is Unclassified. Should it be" not in response.text


def test_failed_reclassification_rolls_back_without_stale_phase() -> None:
    # Classifying 'Project Phoenix' as Revenue breaks the 'Total Revenue' subtotal reconciliation.
    session, response = start("structure", "Revenue", "Skip all")
    assert response.phase == session.phase == Phase.EXPLORING
    assert "not applied" in response.text
    assert "Project Phoenix" not in session.type_map
    assert handle_message(session, "summary").phase == Phase.EXPLORING


def test_analysis_failure_keeps_session_phase_in_sync() -> None:
    session = Session()
    handle_upload(session, b"Line Item,Type,Actual\nA,Revenue,5\n", "nobudget.csv")
    response = Response(text="")
    for step in ("Q3 2026", "$10k or 5%", "USD"):
        response = handle_message(session, step)
    assert "Analysis failed" in response.text
    assert response.phase == session.phase == Phase.AWAITING_FILE


# ---------------------------------------------------------------------------
# Intents and the chip <-> intent contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("text", "intent"), [
    ("drivers", "driver_summary"),
    ("what are drivers?", "concept_drivers"),
    ("Net impact", "concept_net_impact"),
    ("Top 3 by dollars", "top_n"),
    ("Action playbook", "concept_actions"),
    ("Supported file formats", "concept_formats"),
    ("summary please", "summary"),
    ("summary.", "summary"),
    ("Summary?!", "summary"),
    ("memo please", "executive_memo"),
    ("waterfall.", "waterfall"),
    ("show me the biggest risks", "biggest_risks"),
    ("show me the biggest wins", "biggest_wins"),
    ("?", "help"),
    ("drivers please", "driver_summary"),
    ("thanks", "gratitude"),
    ("what if revenue drops 10%.", "what_if"),
])
def test_phrasing_tolerance(text: str, intent: str) -> None:
    assert parse_intent(text).intent_id == intent


def test_item_lookup_ignores_trailing_punctuation() -> None:
    text = handle_message(explore("sample_variance"), "detail payroll expense.").text
    assert "Payroll Expense" in text and "No line item matching" not in text


INPUT_CHIPS = {"Revenue", "Expense", "Skip", "Skip all", "Upload a different file", "USD", "EUR", "GBP"}


@pytest.mark.parametrize("name", ["sample_variance", "fav_net", "unfav_net", "mixed_sign", "edge_values",
                                  "names", "structure"])
def test_every_chip_routes_to_a_handler(name: str) -> None:
    steps = ("Skip all",) if name == "structure" else ()
    session, first = start(name, *steps)
    seeds = ["help", "summary", "memo", "tldr", "waterfall", "sensitivity", "run rate", "drivers",
             "biggest risks", "biggest wins", "totals", "highest percent", "pareto", "warnings",
             "what if revenue drops 10%", "unbudgeted spend", "cost savings", "revenue misses"]
    frontier = list(dict.fromkeys(seeds + (first.chips or [])))
    seen: set[str] = set()
    for _depth in range(2):
        found: list[str] = []
        for message in frontier:
            if message in seen:
                continue
            seen.add(message)
            probe = copy.deepcopy(session)
            response = handle_message(probe, message)
            if message not in seeds and message not in INPUT_CHIPS:
                assert parse_intent(message).intent_id != "unknown" or FALLBACK not in response.text, message
                assert FALLBACK not in response.text, message
            found.extend(chip for chip in response.chips or [] if chip not in seen)
        frontier = list(dict.fromkeys(found))


def test_welcome_chips_are_answered() -> None:
    session = Session()
    for chip in ("Supported file formats", "What is materiality?", "Budget vs forecast"):
        assert parse_intent(chip).intent_id.startswith("concept_"), chip
        assert "Please upload a file" not in handle_message(session, chip).text


# ---------------------------------------------------------------------------
# Escaping: the UI escapes once, so server text must decode cleanly
# ---------------------------------------------------------------------------

def test_chat_html_copies_stay_identical() -> None:
    packaged = ROOT / "src" / "variance_agent" / "static" / "chat.html"
    assert (ROOT / "static" / "chat.html").read_bytes() == packaged.read_bytes()


def test_chat_ui_decodes_server_escapes_before_rendering() -> None:
    html = (ROOT / "src" / "variance_agent" / "static" / "chat.html").read_text(encoding="utf-8")
    assert "function plainText(" in html
    assert "renderMarkdown(text) {\n    let html = escapeHtml(decodeServerEscapes(text));" in html
    assert "td.textContent = plainText(val);" in html


# ---------------------------------------------------------------------------
# HTTP robustness
# ---------------------------------------------------------------------------

@pytest.fixture
def server() -> Any:
    _ChatHandler.session = Session()
    _ChatHandler.initial_response = None
    httpd = HTTPServer(("127.0.0.1", 0), _ChatHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _post(httpd: HTTPServer, path: str, body: bytes, headers: dict[str, str]) -> int:
    conn = HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=10)
    conn.request("POST", path, body=body, headers=headers)
    status = conn.getresponse().status
    conn.close()
    return status


@pytest.mark.parametrize("body", [b"[1, 2]", b'{"text": 5}', b'"text"', b"null"])
def test_message_rejects_non_object_json_with_400(server: HTTPServer, body: bytes) -> None:
    assert _post(server, "/message", body, {"Content-Type": "application/json"}) == 400


def test_invalid_content_length_gets_400(server: HTTPServer) -> None:
    with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=10) as sock:
        sock.sendall(b"POST /message HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\n\r\n")
        assert b" 400 " in sock.recv(200)


def test_slow_client_cannot_block_the_server(server: HTTPServer, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _ChatHandler.timeout is not None and 0 < _ChatHandler.timeout <= 30
    monkeypatch.setattr(_ChatHandler, "timeout", 1)
    with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=10) as sock:
        sock.sendall(b"POST /message HTTP/1.1\r\nHost: x\r\nContent-Length: 500\r\n\r\n{\"te")
        conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/status")
        assert conn.getresponse().status == 200
        conn.close()


# ---------------------------------------------------------------------------
# Router visualizer
# ---------------------------------------------------------------------------

def test_visualizer_routes_typed_input_through_the_router() -> None:
    html = (ROOT / "deterministic_conditioning" / "ui" / "index.html").read_text(encoding="utf-8")
    assert "fetch('/api/route'" in html


def test_table_row_click_sends_the_drill_down_question() -> None:
    # sendMessage() reads the input box and ignores arguments, so rows must post directly.
    html = (ROOT / "src" / "variance_agent" / "static" / "chat.html").read_text(encoding="utf-8")
    assert "sendMessage(`Why" not in html
    assert "addUserMessage(question);\n              postMessage(question);" in html


def test_download_header_does_not_reflect_raw_period(server: HTTPServer) -> None:
    from variance_agent.chat import server as server_module

    server_module._downloads['executive_memo_q3_"x"_2026;_evil=1.md'] = "memo"
    conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    conn.request("GET", "/download/executive_memo_q3_%22x%22_2026%3B_evil%3D1.md")
    response = conn.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Disposition") == 'attachment; filename="executive_memo_q3__x__2026__evil_1.md"'
    conn.close()


def test_no_match_reply_stays_short_on_large_files() -> None:
    session = explore("large")
    text = handle_message(session, "why zzz nothing").text
    assert "No line item matching" in text
    assert len(text) < 2000
    assert "and 4980 more" in text


# ---------------------------------------------------------------------------
# Deferred follow-ups (M7-M15, L1, L3)
# ---------------------------------------------------------------------------

def start_csv(csv: bytes, period: str = "Q3 2026", *steps: str) -> tuple[Session, Response]:
    session = Session()
    response = handle_upload(session, csv, "inline.csv")
    for step in (period, "$10k or 5%", "USD", *steps):
        response = handle_message(session, step)
    return session, response


ZERO_REVENUE_BUDGET = b"Line Item,Type,Budget,Actual\nNew Revenue,Revenue,0,5000\nRent Expense,Expense,1000,1200\n"
ZERO_REVENUE_ACTUAL = b"Line Item,Type,Budget,Actual\nLost Revenue,Revenue,5000,0\nRent Expense,Expense,1000,1200\n"


def _rendered(response: Response) -> str:
    cells = " ".join(v for row in response.table or [] for v in row.values())
    return f"{response.text} {cells}"


@pytest.mark.parametrize("csv", [ZERO_REVENUE_BUDGET, ZERO_REVENUE_ACTUAL])
@pytest.mark.parametrize("message", ["memo", "tldr", "profitability", "run rate", "sensitivity",
                                     "what if expenses drop 5%", "compare revenue vs expenses"])
def test_zero_baseline_percentages_show_na(csv: bytes, message: str) -> None:
    session, _ = start_csv(csv)
    rendered = _rendered(handle_message(session, message))
    assert not re.search(r"(?<![\d.])[+-]?0\.0(?:%| pts)", rendered), rendered


def test_zero_revenue_budget_margin_is_na_in_memo() -> None:
    session, _ = start_csv(ZERO_REVENUE_BUDGET)
    memo = handle_message(session, "memo").text
    assert "EBITDA margin **moved** from N/A to **76.0%** (N/A)" in memo


def test_memo_unbudgeted_percent_has_no_plus_sign() -> None:
    memo = handle_message(explore("edge_values"), "memo").text
    assert "+N/A" not in memo
    assert "(N/A (Unbudgeted))" in memo


def test_unbudgeted_revenue_is_not_called_spending() -> None:
    text = handle_message(explore("edge_values"), "unbudgeted spend").text
    spending, _, revenue = text.partition("Unbudgeted revenue")
    assert "Unbudgeted Consulting" in spending and "New Product Revenue" not in spending
    assert "New Product Revenue" in revenue


@pytest.mark.parametrize("command", ["summary", "memo", "top 3"])
def test_period_step_rejects_commands(command: str) -> None:
    session = Session()
    path = fixture_path("sample_variance")
    handle_upload(session, path.read_bytes(), path.name)
    response = handle_message(session, command)
    assert session.phase == Phase.AWAITING_PERIOD and session.period is None
    assert "looks like a command" in response.text


@pytest.mark.parametrize("period", ["Q3 2026", "FY2026", "October 2026", "H1 2026", "Q3-2024", "Month 7"])
def test_period_step_accepts_periods(period: str) -> None:
    session = Session()
    path = fixture_path("sample_variance")
    handle_upload(session, path.read_bytes(), path.name)
    handle_message(session, period)
    assert session.period == period


def test_run_rate_states_its_assumption() -> None:
    text = handle_message(explore("sample_variance"), "run rate").text
    assert "year-to-date" in text
    session, _ = start_csv(fixture_path("sample_variance").read_bytes(), "Spring sprint")
    text = handle_message(session, "run rate").text
    assert "was not recognised" in text
