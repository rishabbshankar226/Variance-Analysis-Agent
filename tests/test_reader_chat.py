"""Phase 6: each new reader reaches a first answer in the chat from an upload. Every file here is fictional."""

from __future__ import annotations

from pathlib import Path

from tests.fixtures.analysts.build_analysts import INES_LIMITS, MARCUS_TARGETS, THEO_BENCHMARK
from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing, income_filing, quarter_filing
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.responses import Response
from variance_agent.chat.session import Session

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "analysts"


def _answer_until_report(session: Session, reply: Response, answers: list[str]) -> Response:
    for answer in answers:
        if reply.text.startswith("#"):
            break
        reply = handle_message(session, answer)
    return reply


def test_ines_uploads_limits_and_gets_them_by_severity() -> None:
    session = Session()
    first = handle_upload(session, INES_LIMITS.encode(), "desk_limits.csv")
    assert "Read the 'Limit' column as each row's limit" in first.text and "Looks right" in (first.chips or [])
    reply = _answer_until_report(session, first, ["Looks right", "Oct 2026", "$1 or 1%", "USD"])
    assert reply.text.startswith("# Limit Comparison: Oct 2026")
    assert "**2 Breach, 1 At limit, 1 Near, 1 Within.**" in reply.text
    assert handle_message(session, "which limits are breached").text.startswith("# Limit Comparison")


def test_theo_uploads_returns_and_gets_active_return() -> None:
    session = Session()
    first = handle_upload(session, THEO_BENCHMARK.encode(), "fund_returns.csv")
    reply = _answer_until_report(session, first, ["Looks right", "Oct 2026", "$1 or 1%", "USD", "1"])
    assert reply.text.startswith("# Benchmark Comparison: Oct 2026")
    assert "| Fund return | 6.8% | 7.25% | 45 bps |" in reply.text
    assert handle_message(session, "active return").text.startswith("# Benchmark Comparison")


def test_marcus_uploads_weights_and_gets_drift_from_target() -> None:
    session = Session()
    first = handle_upload(session, MARCUS_TARGETS.encode(), "weights.csv")
    reply = _answer_until_report(session, first, ["Looks right", "Oct 2026", "$1 or 1%", "USD", "1"])
    assert reply.text.startswith("# Target Comparison: Oct 2026")
    assert "| OSTRAVA.FAKE | 6% | 5% | -100 bps | 25 bps | Under |" in reply.text
    assert handle_message(session, "drift from target").text.startswith("# Target Comparison")


def test_clara_uploads_a_10k_and_compares_balance_sheets_then_covenant_headroom() -> None:
    session = Session()
    handle_upload(session, all_statements_filing(), "hal-20250927.htm")
    switched = handle_message(session, "compare balance sheets")
    assert "Consolidated Balance Sheets" in switched.text
    reply = _answer_until_report(session, switched, ["Looks right", "Sep 2025", "$1 or 1%", "USD"])
    assert reply.text.startswith("# Statement Comparison: Sep 2025")
    ask = handle_message(session, "covenant headroom")
    assert ask.ask_upload and ask.text.startswith("Upload your metrics file")
    schedule = handle_upload(session, (FIXTURES / "clara_metrics.json").read_bytes(), "clara_metrics.json")
    assert schedule.ask_upload and schedule.text.startswith("Now upload the covenant schedule")
    read = handle_upload(session, (FIXTURES / "clara_covenants.csv").read_bytes(), "clara_covenants.csv")
    # The chat keeps the period, thresholds and currency already set for this filing; only the turns cutoff is asked.
    reply = _answer_until_report(session, read, ["Looks right", "0.1"])
    assert reply.text.startswith("# Limit Comparison: Sep 2025")
    assert "| Gross leverage | Max | 1.25x | 0.88x |" in reply.text


def test_owen_builds_ltm_from_two_uploads() -> None:
    session = Session()
    handle_upload(session, quarter_filing(), "hal-20260328.htm")
    handle_message(session, "Build LTM")
    read = handle_upload(session, income_filing(), "hal-20250927.htm")
    reply = _answer_until_report(session, read, ["Looks right", "LTM Mar 2026", "$1 or 1%", "USD"])
    assert "Total Revenue:** $4,300,000,000.00 vs. $4,100,000,000.00" in reply.text


def test_the_committed_guide_inputs_match_their_builders() -> None:
    from tests.fixtures.analysts.build_analysts import files
    for name, data in files().items():
        assert (FIXTURES / name).read_bytes() == data, name
