"""New earnings wording never captures existing plan wording."""
import json
from pathlib import Path

import pytest

from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.intent import parse_intent, KNOWLEDGE_INTENTS
from variance_agent.chat.session import Phase, Session


@pytest.mark.parametrize("phrase,intent", [
    ("what is consensus?", "concept_consensus"), ("what is earnings surprise?", "concept_surprise"),
    ("what do beat and miss mean?", "concept_beat_miss"), ("what are basis points?", "concept_bps"),
    ("how do guidance ranges work?", "concept_guidance_range"), ("what is standardized surprise?", "concept_standardized_surprise")])
def test_new_knowledge_routes_and_no_estimates(phrase: str, intent: str) -> None:
    assert parse_intent(phrase).intent_id == intent and intent in KNOWLEDGE_INTENTS
    reply = handle_message(Session(), phrase)
    assert "supplied" in reply.text.lower() and "no estimates" in reply.text.lower()


@pytest.mark.parametrize("phrase,intent", [("did we beat consensus", "earnings_consensus"),
    ("vs the street", "earnings_consensus"), ("margin in bps", "earnings_margins"),
    ("where are we vs guide", "earnings_guidance"), ("did we beat the plan", "tldr")])
def test_specific_earnings_routes(phrase: str, intent: str) -> None:
    assert parse_intent(phrase).intent_id == intent


def test_guidance_scenario_b_complete_chat_with_structured_table() -> None:
    session = Session(path_exports_enabled=False)
    reply = handle_upload(session, Path("tests/fixtures/multi_audience/guidance.csv").read_bytes(), "HALV.FAKE.csv")
    assert "earnings review" in reply.text.lower()
    reply = handle_message(session, "Review earnings")
    assert "Here's how I read your file" in reply.text
    for message in ("Looks right", "3Q26", "$10 or 2%", "USD"):
        reply = handle_message(session, message)
    assert session.phase is Phase.EXPLORING
    assert reply.table is not None
    row = reply.table[0]
    assert row["Guidance comparison"] == "$1,260.00"
    assert row["Guidance variance"] == "$27.50"
    assert row["Guidance % / bps"] == "2.2%"
    assert row["Guidance position"] == "Above range"
    followup = handle_message(session, "where are we vs guide")
    assert followup.table is not None and followup.table[0]["Guidance position"] == "Above range"
    report = handle_message(session, "export report")
    assert report.download and "Earnings Review" in next(iter(report.download.values()))
    audit = handle_message(session, "export audit")
    assert json.loads(next(iter(audit.download.values())))["audience"]["layout"] == "earnings"
    refusal = handle_message(session, "export report to /tmp/fictional.md")
    assert refusal.download is None and "turned off" in refusal.text.lower()


def test_pre_upload_consensus_choice_can_confirm_budget_metadata() -> None:
    session = Session()
    handle_message(session, "did we beat consensus")
    reply = handle_upload(session, b"Line Item,Budget,Consensus,Actual,Type\nRevenue,100,101,110,Revenue\n", "HALV.FAKE.csv")
    assert "Here's how I read your file" in reply.text and "Consensus" in reply.text
    assert session.earnings_mode is True


def test_explicit_pre_upload_review_handles_unreadable_file_without_losing_policy() -> None:
    session = Session(path_exports_enabled=False)
    handle_message(session, "did we beat consensus")
    reply = handle_upload(session, b"not a financial table", "HALV.FAKE.csv")
    assert "could not read" in reply.text.lower()
    assert session.path_exports_enabled is False


def test_rate_guidance_scale_is_confirmed_and_blank_consensus_is_not_a_rate_number() -> None:
    guidance = Session()
    handle_upload(guidance, b"Line Item,Measure,Better,Guidance Low,Guidance High,Actual\nGross Margin,Percent,Higher,.4,.42,41%\n",
                  "HALV.FAKE.csv")
    for message in ("Review earnings", "Looks right", "3Q26", "$10 or 2%", "USD"):
        reply = handle_message(guidance, message)
    assert "40%" in reply.text and "fractions" in reply.text
    handle_message(guidance, "Read bare rates as fractions")
    reply = handle_message(guidance, "25")
    assert guidance.phase is Phase.EXPLORING
    assert reply.table[0]["Guidance position"] == "Within range"
    missing = Session()
    handle_upload(missing, b"Line Item,Measure,Better,Consensus,Actual\nGross Margin,Percent,Higher,,40.6%\n", "HALV.FAKE.csv")
    for message in ("Review earnings", "Looks right", "3Q26", "$10 or 2%", "USD", "25"):
        reply = handle_message(missing, message)
    assert missing.phase is Phase.EXPLORING
    assert reply.table[0]["Consensus comparison"] == "N/A (No consensus)"
