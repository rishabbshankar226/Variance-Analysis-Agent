"""Tests for the deterministic chatbot (session, intent, handlers, server, CLI)."""

from __future__ import annotations

import json
import threading
from decimal import Decimal
from http import HTTPStatus
from http.client import HTTPConnection
from http.server import HTTPServer
from pathlib import Path
from typing import Any

import pytest

import variance_agent.cli as cli
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.intent import find_line_item, parse_intent
from variance_agent.chat.server import _ChatHandler
from variance_agent.chat.session import Phase, Session


# ===========================================================================
# 1. Session State Machine Tests
# ===========================================================================

def test_session_initial_state() -> None:
    session = Session()
    assert session.phase == Phase.AWAITING_FILE
    assert session.source_bytes is None
    assert session.result is None
    assert session.currency == "USD"
    assert session.type_map == {}
    assert session.unclassified_queue == []


def test_session_reset() -> None:
    session = Session()
    session.phase = Phase.EXPLORING
    session.source_bytes = b"dummy"
    session.source_name = "test.csv"
    session.period = "Q3 2026"
    session.dollar_threshold = Decimal("1000")
    session.percent_threshold = Decimal("0.05")
    session.unclassified_queue = ["Misc"]

    session.reset()
    assert session.phase == Phase.AWAITING_FILE
    assert session.source_bytes is None
    assert session.source_name is None
    assert session.period is None
    assert session.dollar_threshold is None
    assert session.percent_threshold is None
    assert session.unclassified_queue == []
    assert session.result is None


# ===========================================================================
# 2. Intent Parser Tests
# ===========================================================================

@pytest.mark.parametrize(
    ("text", "expected_intent"),
    [
        ("help", "help"),
        ("?", "help"),
        ("what can you do", "help"),
        ("reset", "reset"),
        ("start over", "reset"),
        ("clear", "reset"),
        ("summary", "summary"),
        ("overview", "summary"),
        ("kpi", "summary"),
        ("material", "material"),
        ("show material", "material"),
        ("unfavorable", "filter_status_u"),
        ("unfav", "filter_status_u"),
        ("red flags", "filter_status_u"),
        ("favorable", "filter_status_f"),
        ("fav", "filter_status_f"),
        ("good news", "filter_status_f"),
        ("revenue", "filter_type_rev"),
        ("rev", "filter_type_rev"),
        ("income", "filter_type_rev"),
        ("expenses", "filter_type_exp"),
        ("expense", "filter_type_exp"),
        ("costs", "filter_type_exp"),
        ("unclassified", "filter_type_unc"),
        ("warnings", "warnings"),
        ("data quality", "warnings"),
        ("recommendations", "recommendations"),
        ("next steps", "recommendations"),
        ("totals", "totals"),
        ("reconcile", "totals"),
        ("full report", "full_report"),
        ("export report", "export_report"),
        ("download report", "export_report"),
        ("export audit", "export_audit"),
        ("download audit", "export_audit"),
        # Financial concepts
        ("variance analysis", "concept_variance"),
        ("what is variance analysis?", "concept_variance"),
        ("favorable vs unfavorable", "concept_f_vs_u"),
        ("what is favorable?", "concept_fav"),
        ("what is unfavorable?", "concept_unfav"),
        ("what is materiality?", "concept_materiality"),
        ("what is net impact?", "concept_net_impact"),
        ("driver decomposition", "concept_drivers"),
        ("why unclassified matters?", "concept_unclassified"),
        ("audit trail", "concept_audit"),
        ("how to mitigate unfavorable", "concept_actions"),
        ("supported formats", "concept_formats"),
        ("budget vs forecast", "concept_budget_forecast"),
        ("timing vs permanent", "concept_timing_permanent"),
        ("operating leverage", "concept_operating_leverage"),
        ("financial kpis", "concept_kpis"),
        ("zero based budgeting", "concept_budgeting_methods"),
        # Advanced analytics
        ("biggest risks", "biggest_risks"),
        ("biggest wins", "biggest_wins"),
        ("did we hit revenue target?", "revenue_status"),
        ("did expenses stay in budget?", "expense_status"),
        ("burn rate", "budget_utilization"),
        ("highest percent", "top_percent"),
        ("row count", "metrics_count"),
        ("variance concentration", "variance_concentration"),
        ("pareto", "variance_concentration"),
        ("unbudgeted spend", "unbudgeted_spend"),
        ("cost savings", "cost_savings"),
        ("where did revenue fall short?", "revenue_misses"),
    ],
)
def test_parse_simple_intents(text: str, expected_intent: str) -> None:
    intent = parse_intent(text)
    assert intent.intent_id == expected_intent


def test_parse_top_n_intent() -> None:
    intent = parse_intent("top 5 variances")
    assert intent.intent_id == "top_n"
    assert intent.captures.get("count") == "5"

    intent2 = parse_intent("show top 10")
    assert intent2.intent_id == "top_n"
    assert intent2.captures.get("count") == "10"


def test_parse_explain_and_detail_intent() -> None:
    intent = parse_intent("why Software Engineering?")
    assert intent.intent_id == "explain"
    assert intent.captures.get("item") == "Software Engineering"

    intent2 = parse_intent("driver for Marketing")
    assert intent2.intent_id == "explain"
    assert intent2.captures.get("item") == "Marketing"

    intent3 = parse_intent("detail for Travel")
    assert intent3.intent_id == "detail"
    assert intent3.captures.get("item") == "Travel"


def test_parse_set_threshold_intent() -> None:
    intent = parse_intent("set threshold $20,000 or 8%")
    assert intent.intent_id == "set_threshold"
    assert intent.captures.get("spec") == "$20,000 or 8%"


def test_find_line_item_matching() -> None:
    candidates = ["Product Revenue", "Service Revenue", "Engineering Expenses", "Marketing"]

    # Exact match
    assert find_line_item("Marketing", candidates) == ["Marketing"]
    # Case-insensitive
    assert find_line_item("marketing", candidates) == ["Marketing"]
    # Prefix match
    assert find_line_item("Engine", candidates) == ["Engineering Expenses"]
    # Substring match
    assert find_line_item("Service", candidates) == ["Service Revenue"]
    # Ambiguous match (both have Revenue)
    assert find_line_item("Revenue", candidates) == ["Product Revenue", "Service Revenue"]
    # No match
    assert find_line_item("Nonexistent", candidates) == []
    # Quotes and brackets sanitization
    assert find_line_item('"Marketing"', candidates) == ["Marketing"]
    assert find_line_item("'Marketing'", candidates) == ["Marketing"]
    assert find_line_item("[Marketing]", candidates) == ["Marketing"]
    assert find_line_item("Marketing?", candidates) == ["Marketing"]
    # Empty and whitespace queries
    assert find_line_item("", candidates) == []
    assert find_line_item("   ", candidates) == []
    assert find_line_item('""', candidates) == []


# ===========================================================================
# 3. Handlers and Guided Conversation Flow Tests
# ===========================================================================

SAMPLE_CSV = b"""Line Item,Budget,Actual,Line Type
Product Sales,100000,120000,Revenue
Marketing,20000,25000,Expense
Office Supplies,5000,4800,Expense
Unknown Item,1000,1500,
"""


def test_full_conversation_lifecycle() -> None:
    session = Session()

    # 1. Upload file
    resp = handle_upload(session, SAMPLE_CSV, "test.csv")
    assert session.phase == Phase.AWAITING_PERIOD
    assert "Loaded 'test.csv' (4 data rows)" in resp.text
    assert session.parsed_rows is not None
    assert len(session.parsed_rows) == 4

    # 2. Set Period
    resp = handle_message(session, "Q3 2026")
    assert session.phase == Phase.AWAITING_THRESHOLDS
    assert "Period set to: **Q3 2026**" in resp.text
    assert session.period == "Q3 2026"

    # 3. Set Thresholds ($10,000 or 5%)
    resp = handle_message(session, "$10,000 or 5%")
    assert session.phase == Phase.AWAITING_CURRENCY
    assert session.dollar_threshold == Decimal("10000")
    assert session.percent_threshold == Decimal("0.05")

    # 4. Set Currency (USD)
    resp = handle_message(session, "USD")
    # "Unknown Item" has no type, so it should queue unclassified resolution
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED
    assert "Unknown Item" in resp.text
    assert "Revenue" in (resp.chips or [])

    # 5. Resolve Unclassified item
    resp = handle_message(session, "Expense")
    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert "Analysis Complete" in resp.text
    assert resp.table is not None

    # 5. Explore: summary
    resp = handle_message(session, "summary")
    assert "Analysis Complete" in resp.text
    assert "Net Operating Impact" in resp.text
    assert resp.table is not None

    # 6. Explore: material
    resp = handle_message(session, "material")
    assert "Material Variances" in resp.text
    assert any("Product Sales" in str(row) for row in (resp.table or []))

    # 7. Explore: unfavorable & favorable
    resp_u = handle_message(session, "unfavorable")
    assert "Unfavorable Variances" in resp_u.text

    resp_f = handle_message(session, "favorable")
    assert "Favorable Variances" in resp_f.text
    assert any("Product Sales" in str(row) for row in (resp_f.table or []))

    # 8. Explore: top N
    resp_top = handle_message(session, "top 2")
    assert "Top 2 Variances" in resp_top.text
    assert len(resp_top.table or []) <= 2

    # 9. Explore: explain / detail
    resp_exp = handle_message(session, "why Product Sales?")
    assert "Product Sales" in resp_exp.text

    resp_det = handle_message(session, "detail for Marketing")
    assert "Marketing" in resp_det.text

    # 10. Explore: totals & recommendations & warnings
    resp_tot = handle_message(session, "totals")
    assert "Aggregate Totals" in resp_tot.text

    resp_rec = handle_message(session, "recommendations")
    assert "Recommendations" in resp_rec.text

    resp_warn = handle_message(session, "warnings")
    assert "warnings" in resp_warn.text.lower()

    # 11. Explore: full report
    resp_rep = handle_message(session, "full report")
    assert "# FP&A Variance Report" in resp_rep.text

    # 12. Export report and audit
    resp_exp_rep = handle_message(session, "export report")
    assert resp_exp_rep.download is not None
    assert "variance_report_q3_2026.md" in resp_exp_rep.download

    resp_exp_aud = handle_message(session, "export audit")
    assert resp_exp_aud.download is not None
    assert "variance_audit_q3_2026.json" in resp_exp_aud.download

    # 13. Dynamic threshold change
    resp_thresh = handle_message(session, "threshold $3,000 or 4%")
    assert session.phase == Phase.EXPLORING
    assert session.dollar_threshold == Decimal("3000")
    assert session.percent_threshold == Decimal("0.04")
    assert "$3,000.00 or 4.0%" in resp_thresh.text

    # 14. Reset
    resp_rst = handle_message(session, "reset")
    assert session.phase == Phase.AWAITING_FILE
    assert session.result is None
    assert "Session cleared" in resp_rst.text


def test_handle_invalid_file_upload() -> None:
    session = Session()
    # Bad extension
    resp = handle_upload(session, b"dummy", "invalid.pdf")
    assert session.phase == Phase.AWAITING_FILE
    assert "⚠️" in resp.text
    assert "Unsupported input format" in resp.text

    # Corrupt CSV
    resp2 = handle_upload(session, b"Not,A,Valid\nFormat\n", "bad.csv")
    assert session.phase == Phase.AWAITING_FILE
    assert "⚠️" in resp2.text


def test_handle_blank_period() -> None:
    session = Session()
    session.phase = Phase.AWAITING_PERIOD
    resp = handle_message(session, "   ")
    assert session.phase == Phase.AWAITING_PERIOD
    assert "Please type a message" in resp.text


def test_handle_invalid_thresholds() -> None:
    session = Session()
    session.phase = Phase.AWAITING_THRESHOLDS
    resp = handle_message(session, "not numbers")
    assert session.phase == Phase.AWAITING_THRESHOLDS
    assert "couldn't parse" in resp.text.lower()


def test_knowledge_intents_across_phases() -> None:
    session = Session()

    # 1. Phase.AWAITING_FILE: asking a domain question
    resp1 = handle_message(session, "what is materiality?")
    assert session.phase == Phase.AWAITING_FILE
    assert "Materiality Thresholds" in resp1.text
    assert "Upload your financial file" in resp1.text

    # Advance to AWAITING_PERIOD
    handle_upload(session, SAMPLE_CSV, "test.csv")
    assert session.phase == Phase.AWAITING_PERIOD

    # 2. Phase.AWAITING_PERIOD: asking budget vs forecast
    resp2 = handle_message(session, "budget vs forecast")
    assert session.phase == Phase.AWAITING_PERIOD
    assert "Budget vs. Forecast" in resp2.text
    assert "What reporting period" in resp2.text

    # Advance to AWAITING_THRESHOLDS
    handle_message(session, "Q3 2026")
    assert session.phase == Phase.AWAITING_THRESHOLDS

    # 3. Phase.AWAITING_THRESHOLDS: asking timing vs permanent
    resp3 = handle_message(session, "timing vs permanent")
    assert session.phase == Phase.AWAITING_THRESHOLDS
    assert "Timing vs. Permanent" in resp3.text
    assert "materiality thresholds" in resp3.text

    # Advance to AWAITING_CURRENCY
    handle_message(session, "$10,000 or 5%")
    assert session.phase == Phase.AWAITING_CURRENCY

    # 4. Phase.AWAITING_CURRENCY: asking operating leverage
    resp4 = handle_message(session, "operating leverage")
    assert session.phase == Phase.AWAITING_CURRENCY
    assert "Operating Leverage" in resp4.text
    assert "reporting currency" in resp4.text

    # Advance to RESOLVE_UNCLASSIFIED
    handle_message(session, "USD")
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED

    # 5. Phase.RESOLVE_UNCLASSIFIED: asking unclassified explanation
    resp5 = handle_message(session, "why unclassified matters?")
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED
    assert "Why Line Item Classification Matters" in resp5.text
    assert "Classify 'Unknown Item'" in resp5.text


def test_advanced_analytics_handlers() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")
    assert session.phase == Phase.EXPLORING

    # 1. Biggest risks
    resp_risks = handle_message(session, "biggest risks")
    assert "Top Financial Risks" in resp_risks.text
    assert "Marketing" in resp_risks.text

    # 2. Biggest wins
    resp_wins = handle_message(session, "biggest wins")
    assert "Top Positive Performers" in resp_wins.text
    assert "Product Sales" in resp_wins.text

    # 3. Revenue status
    resp_rev = handle_message(session, "did we hit revenue target?")
    assert "Revenue Target Achieved" in resp_rev.text
    assert "Achievement Rate" in resp_rev.text

    # 4. Expense status
    resp_exp = handle_message(session, "did expenses stay in budget?")
    assert "Expenses Exceeded Budget" in resp_exp.text
    assert "Budget Utilization" in resp_exp.text

    # 5. Budget utilization
    resp_util = handle_message(session, "burn rate")
    assert "Budget Execution & Utilization" in resp_util.text
    assert "Expense Budget Utilization" in resp_util.text

    # 6. Top percent
    resp_pct = handle_message(session, "highest percent")
    assert "Top Line Items by Percentage Variance" in resp_pct.text
    assert resp_pct.table is not None

    # 7. Metrics count
    resp_met = handle_message(session, "row count")
    assert "Portfolio Metrics Breakdown" in resp_met.text
    assert "Total Line Items:** 4" in resp_met.text

    # 8. Variance concentration (Pareto)
    resp_conc = handle_message(session, "variance concentration")
    assert "Variance Concentration Analysis" in resp_conc.text
    assert "Top 3 Concentration" in resp_conc.text

    # 9. Unbudgeted spend
    resp_unb = handle_message(session, "unbudgeted spend")
    assert "No Unbudgeted Spending" in resp_unb.text

    # 10. Cost savings
    resp_sav = handle_message(session, "cost savings")
    assert "Expense Savings & Underspend Summary" in resp_sav.text
    assert "Office Supplies" in resp_sav.text

    # 11. Revenue misses
    resp_miss = handle_message(session, "where did revenue fall short?")
    assert "No Revenue Misses" in resp_miss.text

    # 12. Compare two different items
    resp_comp = handle_message(session, "compare Product Sales and Marketing")
    assert "Side-by-Side Comparison" in resp_comp.text
    assert resp_comp.table is not None
    assert len(resp_comp.table) == 2

    # 13. Compare item against itself
    resp_self = handle_message(session, "compare Marketing vs Marketing")
    assert "Comparing '**Marketing**' against itself" in resp_self.text
    assert resp_self.table is not None
    assert len(resp_self.table) == 1


def test_empty_file_upload_rejected() -> None:
    session = Session()
    empty_csv = b"Line Item,Budget,Actual\n"
    resp = handle_upload(session, empty_csv, "empty.csv")
    assert session.phase == Phase.AWAITING_FILE
    assert "⚠️" in resp.text
    assert "contains no data rows" in resp.text


def test_decimal_trap_recurring_division_safety() -> None:
    """Ensure repeating decimal ratios do not trigger Inexact traps."""
    recurring_csv = b"""Line Item,Budget,Actual,Line Type
Item A,3,1,Revenue
Item B,7,2,Expense
"""
    session = Session()
    handle_upload(session, recurring_csv, "recurring.csv")
    handle_message(session, "FY26")
    handle_message(session, "$1 or 1%")
    handle_message(session, "USD")
    assert session.phase == Phase.EXPLORING

    # These invoke ratio calculations with repeating 1/3 and 2/7 fractions
    resp1 = handle_message(session, "revenue status")
    assert "Achievement Rate:** 33.3%" in resp1.text

    resp2 = handle_message(session, "expense status")
    assert "Budget Utilization:** 28.6%" in resp2.text

    resp3 = handle_message(session, "variance concentration")
    assert "Variance Concentration Analysis" in resp3.text



# ===========================================================================
# 4. HTTP Server API Tests
# ===========================================================================

@pytest.fixture
def chat_server_url(tmp_path: Path) -> str:
    """Spin up an actual HTTP server on an OS-assigned ephemeral port in a thread."""
    session = Session()
    _ChatHandler.session = session
    _ChatHandler.initial_response = None

    from http.server import HTTPServer
    server = HTTPServer(("127.0.0.1", 0), _ChatHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"127.0.0.1:{port}"

    server.shutdown()
    server.server_close()


def test_http_server_get_index(chat_server_url: str) -> None:
    conn = HTTPConnection(chat_server_url)
    conn.request("GET", "/")
    res = conn.getresponse()
    assert res.status == HTTPStatus.OK
    body = res.read().decode("utf-8")
    assert "<title>Variance Analysis Agent</title>" in body
    conn.close()


def test_http_server_status_and_flow(chat_server_url: str) -> None:
    conn = HTTPConnection(chat_server_url)

    # 1. GET /status initially
    conn.request("GET", "/status")
    res = conn.getresponse()
    assert res.status == HTTPStatus.OK
    data = json.loads(res.read().decode("utf-8"))
    assert data["phase"] == "awaiting_file"

    # 2. POST /upload with multipart
    boundary = "----TestBoundary12345"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="sample.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
        f"{SAMPLE_CSV.decode('utf-8')}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    conn.request("POST", "/upload", body=body, headers=headers)
    res = conn.getresponse()
    assert res.status == HTTPStatus.OK
    upload_data = json.loads(res.read().decode("utf-8"))
    assert upload_data["phase"] == "awaiting_period"
    assert "Loaded 'sample.csv'" in upload_data["text"]

    # 3. POST /message (period)
    msg_body = json.dumps({"text": "Q1 2026"}).encode("utf-8")
    conn.request(
        "POST",
        "/message",
        body=msg_body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(msg_body))},
    )
    res = conn.getresponse()
    assert res.status == HTTPStatus.OK
    msg_data = json.loads(res.read().decode("utf-8"))
    assert msg_data["phase"] == "awaiting_thresholds"

    conn.close()


def test_http_server_staged_download(chat_server_url: str) -> None:
    conn = HTTPConnection(chat_server_url)

    # Manually setup session in exploring phase with result
    session = _ChatHandler.session
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "FY2026")
    handle_message(session, "$10,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")  # now in EXPLORING

    # Request export report
    msg_body = json.dumps({"text": "export report"}).encode("utf-8")
    conn.request(
        "POST",
        "/message",
        body=msg_body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(msg_body))},
    )
    res = conn.getresponse()
    export_data = json.loads(res.read().decode("utf-8"))
    download_url = export_data.get("download_url")
    assert download_url is not None

    # Fetch staged download
    conn.request("GET", download_url)
    res = conn.getresponse()
    assert res.status == HTTPStatus.OK
    assert "attachment;" in res.getheader("Content-Disposition", "")
    content = res.read().decode("utf-8")
    assert "# FP&A Variance Report" in content

    conn.close()


def test_http_server_download_unquoting(chat_server_url: str) -> None:
    """Ensure percent-encoded download URLs are unquoted correctly."""
    from variance_agent.chat.server import _downloads
    _downloads["test report.md"] = "# Test Content"

    conn = HTTPConnection(chat_server_url)
    # Request with %20 space encoding
    conn.request("GET", "/download/test%20report.md")
    res = conn.getresponse()
    assert res.status == HTTPStatus.OK
    body = res.read().decode("utf-8")
    assert body == "# Test Content"
    conn.close()


def test_http_server_upload_strips_windows_path(chat_server_url: str) -> None:
    """Ensure Windows or directory paths in uploaded filename are stripped to basename."""
    conn = HTTPConnection(chat_server_url)

    boundary = "----TestBoundary67890"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="C:\\Users\\Finance\\custom_variance.csv"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
        f"{SAMPLE_CSV.decode('utf-8')}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    conn.request("POST", "/upload", body=body, headers=headers)
    res = conn.getresponse()
    assert res.status == HTTPStatus.OK
    data = json.loads(res.read().decode("utf-8"))
    # Verifies only 'custom_variance.csv' appears in response text, not the C:\ path
    assert "custom\\_variance.csv" in data["text"]
    assert "Users" not in data["text"]
    assert "C:\\" not in data["text"]
    conn.close()


# ===========================================================================
# 5. CLI Integration Tests
# ===========================================================================

def test_cli_chat_flag_invokes_server(monkeypatch: pytest.MonkeyPatch) -> None:
    invoked: dict[str, Any] = {}

    def mock_run_chat_server(
        host: str = "127.0.0.1",
        port: int = 0,
        initial_input: str | None = None,
        initial_sheet: str | None = None,
        open_browser: bool = True,
    ) -> int:
        invoked["host"] = host
        invoked["port"] = port
        invoked["initial_input"] = initial_input
        invoked["initial_sheet"] = initial_sheet
        return 0

    import variance_agent.chat.server as srv
    monkeypatch.setattr(srv, "run_chat_server", mock_run_chat_server)

    # Pure interactive chat launch
    rc = cli.main(["--chat"])
    assert rc == 0
    assert invoked["initial_input"] is None

    # Chat launch with initial file preloaded
    rc2 = cli.main(["examples/sample_variance.csv", "--chat"])
    assert rc2 == 0
    assert invoked["initial_input"] == "examples/sample_variance.csv"


def test_cli_chat_rejects_conflicting_output_flags() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--chat", "--check-only"])
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc2:
        cli.main(["--chat", "--output", "report.md"])
    assert exc2.value.code == 2


# ===========================================================================
# 6. Advanced Drill-Down, Export & Threshold Tests
# ===========================================================================

def test_concept_ebitda_margin_knowledge() -> None:
    session = Session()
    resp = handle_message(session, "what is ebitda impact?")
    assert "EBITDA & Operating Margin Impact" in resp.text
    assert "Bottom-Line Formula" in resp.text
    assert "Flow-Through Rate" in resp.text
    assert "excluded_from_aggregation" in resp.text


def test_export_csv_download() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")
    assert session.phase == Phase.EXPLORING

    resp = handle_message(session, "export csv")
    assert resp.download is not None
    assert "variance_data_q3_2026.csv" in resp.download
    csv_text = resp.download["variance_data_q3_2026.csv"]
    assert "Line Item,Type,Budget (USD),Actual (USD),Variance (USD),Variance (%),Status,Material" in csv_text
    assert "Product Sales" in csv_text
    assert "Marketing" in csv_text


def test_partial_threshold_adjustments() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")
    assert session.phase == Phase.EXPLORING
    assert session.dollar_threshold == Decimal("5000")
    assert session.percent_threshold == Decimal("0.05")

    # Adjust only dollar threshold
    resp_dollar = handle_message(session, "threshold $25,000")
    assert session.dollar_threshold == Decimal("25000")
    assert session.percent_threshold == Decimal("0.05")
    assert "$25,000.00" in resp_dollar.text

    # Adjust only percent threshold
    resp_pct = handle_message(session, "threshold 12%")
    assert session.dollar_threshold == Decimal("25000")
    assert session.percent_threshold == Decimal("0.12")
    assert "12.0%" in resp_pct.text


def test_contextual_multi_turn_drill_down() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$2,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")
    assert session.phase == Phase.EXPLORING

    # Show material variances: Product Sales ($20k), Marketing ($5k), Unknown Item (50%)
    resp_mat = handle_message(session, "material")
    assert resp_mat.table is not None
    assert session.last_table_items == ["Product Sales", "Marketing", "Unknown Item"]

    # Drill down with "#1"
    resp_why1 = handle_message(session, "why #1")
    assert "Driver Evidence: Product Sales" in resp_why1.text
    assert session.last_focused_item == "Product Sales"

    # Drill down with "2"
    resp_why2 = handle_message(session, "why 2")
    assert "Driver Evidence: Marketing" in resp_why2.text
    assert session.last_focused_item == "Marketing"

    # Detail with pronoun "detail it"
    resp_detail = handle_message(session, "detail it")
    assert "**Marketing**" in resp_detail.text

    # Drill down with "why last"
    resp_last = handle_message(session, "why last")
    assert "Driver Evidence: Unknown Item" in resp_last.text
    assert session.last_focused_item == "Unknown Item"

    # Drill down with "why?" (uses last focused item)
    resp_why_bare = handle_message(session, "why?")
    assert "Driver Evidence: Unknown Item" in resp_why_bare.text


def test_server_re_download_availability() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    resp = handle_message(session, "export csv")
    assert resp.download is not None
    filename, content = next(iter(resp.download.items()))

    # Stage the download in server
    import variance_agent.chat.server as srv
    srv._downloads[filename] = content

    _ChatHandler.session = session
    _ChatHandler.initial_response = None
    server = HTTPServer(("127.0.0.1", 0), _ChatHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        conn = HTTPConnection("127.0.0.1", port)
        # First download
        conn.request("GET", f"/download/{filename}")
        r1 = conn.getresponse()
        assert r1.status == HTTPStatus.OK
        assert r1.read().decode("utf-8") == content

        # Second download should succeed as well (not 404)
        conn.request("GET", f"/download/{filename}")
        r2 = conn.getresponse()
        assert r2.status == HTTPStatus.OK
        assert r2.read().decode("utf-8") == content
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_waterfall_bridge_analysis() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    # Test 'waterfall'
    resp = handle_message(session, "waterfall")
    assert resp.table is not None
    assert "P&L Variance Bridge (Waterfall Walk)" in resp.text
    assert "Budget Operating Profit" in resp.text
    assert "Actual Operating Profit" in resp.text

    # Verify baseline and summary rows
    table = resp.table
    assert table[0]["Line Item"] == "1. Budget Operating Profit"
    assert table[0]["Type"] == "Baseline"
    assert table[-1]["Line Item"] == "🏁 Actual Operating Profit"
    assert table[-1]["Type"] == "Summary"

    # Verify table columns include Profit Impact
    assert "Profit Impact ($)" in table[0]
    assert "Var ($)" in table[0]

    # Test alternative phrasings
    resp_bridge = handle_message(session, "p&l bridge")
    assert resp_bridge.table is not None

    resp_walk = handle_message(session, "variance walk")
    assert resp_walk.table is not None

    resp_short = handle_message(session, "bridge")
    assert resp_short.table is not None


def test_waterfall_concept_vs_data_disambiguation() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    # Educational inquiry should route to knowledge explanation
    resp_edu = handle_message(session, "what is a variance bridge?")
    assert "P&L Variance Bridge" in resp_edu.text
    assert resp_edu.table is None

    resp_how = handle_message(session, "how does a p&l bridge work?")
    assert "P&L Variance Bridge" in resp_how.text
    assert resp_how.table is None

    # Analytical command should route to data waterfall
    resp_data = handle_message(session, "variance bridge")
    assert resp_data.table is not None
    assert "P&L Variance Bridge (Waterfall Walk)" in resp_data.text


def test_multi_worksheet_support() -> None:
    from openpyxl import Workbook
    import io

    wb = Workbook()
    ws1 = wb.active
    assert ws1 is not None
    ws1.title = "Summary_P&L"
    ws1.append(["Line Item", "Line Type", "Budget", "Actual"])
    ws1.append(["Product Sales", "Revenue", 200000, 220000])
    ws1.append(["Payroll", "Expense", 80000, 75000])

    ws2 = wb.create_sheet(title="Regional_Sales")
    ws2.append(["Line Item", "Line Type", "Budget", "Actual"])
    ws2.append(["North America", "Revenue", 120000, 130000])
    ws2.append(["Europe", "Revenue", 80000, 90000])

    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    excel_bytes = buf.getvalue()

    session = Session()
    upload_resp = handle_upload(session, excel_bytes, "quarterly_model.xlsx")
    assert session.available_sheets == ["Summary_P&L", "Regional_Sales"]
    assert "sheets available" in upload_resp.text

    # Complete configuration for Summary_P&L
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    assert session.phase == Phase.EXPLORING

    # List worksheets
    list_resp = handle_message(session, "sheets")
    assert "Worksheets in" in list_resp.text
    assert "quarterly" in list_resp.text
    assert "Regional" in list_resp.text
    assert "*(active)*" in list_resp.text

    # Switch sheet to Regional_Sales
    switch_resp = handle_message(session, "sheet Regional_Sales")
    assert "Switched to worksheet" in switch_resp.text
    assert session.worksheet == "Regional_Sales"
    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    # Check that rows from Regional_Sales are analyzed
    analyzed_items = [r.line_item for r in session.result.rows]
    assert "North America" in analyzed_items
    assert "Europe" in analyzed_items

    # Switching to already active sheet
    already_resp = handle_message(session, "sheet Regional_Sales")
    assert "already active" in already_resp.text

    # Case-insensitive / substring switch
    switch_sub = handle_message(session, "sheet summary")
    assert "Switched to worksheet" in switch_sub.text
    assert session.worksheet == "Summary_P&L"

    # Non-existent sheet
    bad_sheet_resp = handle_message(session, "sheet NonExistent")
    assert "was not found" in bad_sheet_resp.text


def test_sheet_listing_on_non_excel() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    resp = handle_message(session, "sheets")
    assert "single dataset rather than multiple worksheets" in resp.text


def test_global_reset_during_intake() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    assert session.phase == Phase.AWAITING_THRESHOLDS

    # Send reset
    resp = handle_message(session, "reset")
    assert session.phase == Phase.AWAITING_FILE
    assert session.source_bytes is None
    assert "Session cleared" in resp.text


def test_what_if_scenario_simulation() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    # 1. Macro revenue what-if
    resp_rev = handle_message(session, "what if revenue drops 5%?")
    assert "Scenario Analysis" in resp_rev.text
    assert "Total Revenue" in resp_rev.text
    assert "-5.0%" in resp_rev.text
    assert resp_rev.table is not None
    assert len(resp_rev.table) == 4
    metrics = [r["Metric"] for r in resp_rev.table]
    assert "Total Revenue" in metrics
    assert "Total Expenses" in metrics
    assert "Operating Profit" in metrics

    # 2. Macro expense what-if
    resp_exp = handle_message(session, "what if expenses are 10% higher?")
    assert "Scenario Analysis" in resp_exp.text
    assert "Total Expenses" in resp_exp.text
    assert "+10.0%" in resp_exp.text

    # 3. Line-item what-if with dollar amount
    resp_line = handle_message(session, "what if Marketing increases by $20,000?")
    assert "Scenario Analysis" in resp_line.text
    assert "Marketing" in resp_line.text
    assert "+$20,000.00" in resp_line.text
    assert resp_line.table is not None
    assert resp_line.table[0]["Metric"] == "Marketing"

    # 4. Line-item what-if with percentage drop
    resp_line_pct = handle_message(session, "what if Office Supplies is 10% lower?")
    assert "Scenario Analysis" in resp_line_pct.text
    assert "Office Supplies" in resp_line_pct.text
    assert "-10.0%" in resp_line_pct.text


def test_sensitivity_analysis_matrix() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    resp = handle_message(session, "sensitivity analysis")
    assert "Financial Sensitivity & Scenario Matrix" in resp.text
    assert resp.table is not None
    assert len(resp.table) == 5
    scenarios = [r["Scenario"] for r in resp.table]
    assert any("Severe Downside" in s for s in scenarios)
    assert any("Baseline Actuals" in s for s in scenarios)
    assert any("Strong Upside" in s for s in scenarios)

    # Alternate phrasing
    resp_scen = handle_message(session, "scenarios")
    assert resp_scen.table is not None


def test_run_rate_and_projections() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    resp = handle_message(session, "run rate")
    assert "Run-Rate & Full-Year (FY) Projections" in resp.text
    assert "Q3 (9 months elapsed)" in resp.text
    assert resp.table is not None
    models = [r["Projection Model"] for r in resp.table]
    assert any("Annualized Run-Rate" in m for m in models)
    assert any("Latest Estimate" in m for m in models)
    assert any("Full-Year Baseline Budget" in m for m in models)

    # Alternate phrasing
    resp_proj = handle_message(session, "project year end")
    assert resp_proj.table is not None


def test_conversational_intake_cleanup() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")

    # Conversational period with prefix and punctuation
    p_resp = handle_message(session, "The period is Q3 2026.")
    assert session.period == "Q3 2026"
    assert "Period set to: **Q3 2026**" in p_resp.text

    handle_message(session, "$5,000 or 5%")

    # Conversational currency with sentence framing
    handle_message(session, "in USD please")
    assert session.currency == "USD"
    assert session.phase == Phase.RESOLVE_UNCLASSIFIED


def test_shorthand_multipliers_and_threshold_priority() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")

    # Initial setup supports $10k shorthand
    handle_message(session, "$10k or 5%")
    assert session.dollar_threshold == Decimal("10000")
    assert session.percent_threshold == Decimal("0.05")

    handle_message(session, "USD")
    handle_message(session, "Expense")
    assert session.phase == Phase.EXPLORING

    # 1. 'what if threshold is...' routes to set_threshold and parses $25k shorthand
    t_resp = handle_message(session, "what if threshold is $25k or 8%")
    assert session.dollar_threshold == Decimal("25000")
    assert session.percent_threshold == Decimal("0.08")
    assert "Thresholds:" in t_resp.text
    assert "$25,000.00" in t_resp.text

    # 2. 'what if revenue drops $50k' uses k multiplier
    resp_k = handle_message(session, "what if revenue drops $50k")
    assert "Scenario Analysis" in resp_k.text
    assert "-$50,000.00" in resp_k.text
    assert resp_k.table is not None
    rev_row = next(r for r in resp_k.table if r["Metric"] == "Total Revenue")
    assert rev_row["Delta vs Baseline"] == "-$50,000.00"

    # 3. 'what if Marketing increases 15k'
    resp_mkt = handle_message(session, "what if Marketing increases 15k")
    assert "Scenario Analysis" in resp_mkt.text
    assert "+$15,000.00" in resp_mkt.text

    # 4. 'what if revenue grows 1.5M' uses M multiplier
    resp_m = handle_message(session, "what if revenue grows 1.5M")
    assert "Scenario Analysis" in resp_m.text
    assert "+$1,500,000.00" in resp_m.text


def test_executive_memo_generation() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    resp = handle_message(session, "memo")
    assert "Executive Management Briefing & Variance Commentary" in resp.text
    assert "### 1. Executive Summary" in resp.text
    assert "### 2. Top-Line Performance (Revenue)" in resp.text
    assert "### 3. Cost Discipline & Overruns (Expenses)" in resp.text
    assert "### 4. Governance & Material Variances" in resp.text
    assert "### 5. Prioritized Management Action Items" in resp.text

    assert resp.table is not None
    assert len(resp.table) == 3
    sections = [r["Section"] for r in resp.table]
    assert any("Top-Line" in s for s in sections)
    assert any("Cost" in s for s in sections)
    assert any("Bottom-Line" in s for s in sections)

    assert resp.download is not None
    assert "executive_memo_q3_2026.md" in resp.download
    memo_md = resp.download["executive_memo_q3_2026.md"]
    assert "Operating Profit" in memo_md

    # Alternate phrasing: 'cfo memo'
    resp_cfo = handle_message(session, "cfo memo")
    assert "Executive Management Briefing" in resp_cfo.text


def test_macro_comparisons() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    # 1. Actual vs Budget macro comparison
    resp_avb = handle_message(session, "compare actual and budget")
    assert "Executive Macro Comparison: Actual vs. Budget" in resp_avb.text
    assert resp_avb.table is not None
    metrics = [r["Metric"] for r in resp_avb.table]
    assert "Total Revenue" in metrics
    assert "Total Expenses" in metrics
    assert "Operating Profit" in metrics

    # Reverse order: budget vs actual
    resp_bva = handle_message(session, "compare budget vs actual")
    assert "Executive Macro Comparison: Actual vs. Budget" in resp_bva.text

    # 2. Revenue vs Expenses macro comparison
    resp_rve = handle_message(session, "compare revenue and expenses")
    assert "Macro Financial Comparison: Revenue vs. Expenses" in resp_rve.text
    assert resp_rve.table is not None
    cats = [r["Category"] for r in resp_rve.table]
    assert "Total Revenue" in cats
    assert "Total Expenses" in cats
    assert any("Operating Profit" in c for c in cats)


def test_driver_models_summary() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    resp = handle_message(session, "driver summary")
    assert "Causal Driver Models Overview" in resp.text
    assert resp.table is not None
    assert len(resp.table) == 4  # 4 rows in SAMPLE_CSV
    cols = list(resp.table[0].keys())
    assert "Line Item" in cols
    assert "Model" in cols
    assert "Reconciliation" in cols
    assert "Driver Components" in cols


def test_conversational_dialogue_across_phases() -> None:
    session = Session()

    # 1. Greeting in AWAITING_FILE
    g_resp = handle_message(session, "hello")
    assert "Welcome to the Variance Analysis Agent" in g_resp.text
    assert session.phase == Phase.AWAITING_FILE

    # 2. Identity query in AWAITING_FILE
    id_resp = handle_message(session, "who are you?")
    assert "Institutional Variance Analysis Agent" in id_resp.text
    assert "100% Deterministic Calculations" in id_resp.text
    assert session.phase == Phase.AWAITING_FILE

    handle_upload(session, SAMPLE_CSV, "test.csv")
    assert session.phase == Phase.AWAITING_PERIOD

    # 3. Greeting in AWAITING_PERIOD
    g_period = handle_message(session, "good morning")
    assert "Your file has been validated and loaded" in g_period.text
    assert session.phase == Phase.AWAITING_PERIOD

    handle_message(session, "Q3 2026")
    assert session.phase == Phase.AWAITING_THRESHOLDS

    # 4. Help inquiry in AWAITING_THRESHOLDS
    h_thresh = handle_message(session, "can you help me?")
    assert "Available Commands & Intelligence" in h_thresh.text

    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")
    assert session.phase == Phase.EXPLORING

    # 5. Greeting in EXPLORING (contextual)
    g_exploring = handle_message(session, "hi there")
    assert "ready to explore your **Q3 2026** financial results" in g_exploring.text

    # 6. Gratitude in EXPLORING
    thanks = handle_message(session, "thanks so much!")
    assert "You're very welcome" in thanks.text

    # 7. Identity in EXPLORING
    id_exploring = handle_message(session, "what are you?")
    assert "Institutional Variance Analysis Agent" in id_exploring.text


def test_colloquial_fpa_phrasing() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    # 1. TL;DR
    tldr = handle_message(session, "give me the tldr")
    assert "The Executive TL;DR for Q3 2026" in tldr.text
    assert "Operating Profit" in tldr.text

    # 2. Profitability standing
    prof = handle_message(session, "are we in the black or the red?")
    assert "firmly **in the black** (profitable)" in prof.text
    assert prof.table is not None

    # 3. Natural conversational drill-down with 'tell me about'
    mkt = handle_message(session, "tell me about Marketing")
    assert "Marketing" in mkt.text

    # 4. Natural conversational drill-down with 'give me more color on'
    sales = handle_message(session, "give me more color on Product Sales")
    assert "Product Sales" in sales.text

    # 5. Colloquial cash bleed routing
    bleed = handle_message(session, "where are we bleeding money?")
    assert "Top Financial Risks" in bleed.text


def test_conversational_demonstratives_and_ordinals() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    # Show top 3 to populate candidate items
    top3 = handle_message(session, "top 3")
    assert top3.table is not None
    assert len(session.last_table_items) == 3

    # 1. "why the top one?" -> resolves to 1st item
    top_item = session.last_table_items[0]
    first_resp = handle_message(session, "why the top one?")
    assert top_item in first_resp.text
    assert session.last_focused_item == top_item

    # 2. "why did that happen?" -> resolves to last_focused_item
    that_resp = handle_message(session, "why did that happen?")
    assert top_item in that_resp.text

    # 3. "explain the second one" -> resolves to 2nd item
    second_item = session.last_table_items[1]
    second_resp = handle_message(session, "explain the second one")
    assert second_item in second_resp.text
    assert session.last_focused_item == second_item

    # 4. "tell me about the last one" -> resolves to 3rd item
    last_item = session.last_table_items[2]
    last_resp = handle_message(session, "tell me about the last one")
    assert last_item in last_resp.text
    assert session.last_focused_item == last_item

    # 5. "what about it?" -> resolves to last_focused_item
    it_resp = handle_message(session, "what about it?")
    assert last_item in it_resp.text


def test_conversational_executive_strategic_inquiries() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    # 1. "how did we do?" -> TL;DR
    how_did_we_do = handle_message(session, "how did we do?")
    assert "The Executive TL;DR for Q3 2026" in how_did_we_do.text

    # 2. "did we beat plan?" -> TL;DR
    beat_plan = handle_message(session, "did we beat plan?")
    assert "The Executive TL;DR for Q3 2026" in beat_plan.text

    # 3. "what should we do?" -> Recommendations
    recs = handle_message(session, "what should we do?")
    assert "Strategic Recommendations" in recs.text
    assert "Mitigation" in recs.text

    # 4. "are there any warnings?" -> Warnings
    warnings = handle_message(session, "are there any warnings?")
    assert "No data quality warnings" in warnings.text

    # 5. "summarize this for the board" -> Executive Memo
    board_memo = handle_message(session, "summarize this for the board")
    assert "Executive Management Briefing & Variance Commentary" in board_memo.text
    assert board_memo.download is not None


def test_conversational_inverted_what_if() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "test.csv")
    handle_message(session, "Q3 2026")
    handle_message(session, "$5,000 or 5%")
    handle_message(session, "USD")
    handle_message(session, "Expense")

    # "what if we cut Marketing by 10%?"
    cut_sim = handle_message(session, "what if we cut Marketing by 10%?")
    assert 'Scenario Analysis ("What-If" Simulation)' in cut_sim.text
    assert "Marketing" in cut_sim.text
    assert "-10.0%" in cut_sim.text

    # "what if we increase Product Sales by 5%?"
    inc_sim = handle_message(session, "what if we increase Product Sales by 5%?")
    assert 'Scenario Analysis ("What-If" Simulation)' in inc_sim.text
    assert "Product Sales" in inc_sim.text
    assert "+5.0%" in inc_sim.text




