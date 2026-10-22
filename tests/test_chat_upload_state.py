"""Chat uploads: a failed read changes nothing, a successful one starts the file afresh (WS2 P0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.chat_helpers import SAMPLE_CSV, analysed, ask, finish_setup
from variance_agent.audit import sha256_bytes
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session
from variance_agent.models import LineType, Status

BAD_FILE = b"not,a,valid\nfile"
REALWORLD = Path(__file__).resolve().parent / "fixtures" / "realworld"

FIRST_FILE = b"""Line Item,Budget,Actual,Line Type
Product Sales,100000,120000,Revenue
Misc Thing,1000,1500,
"""
SECOND_FILE = b"""Line Item,Type,Budget,Actual
Product Sales,Revenue,1000,1000
Misc Thing,Expense,1000,1200
"""


def test_failed_reupload_keeps_the_previous_file_and_analysis() -> None:
    session = analysed()
    response = handle_upload(session, BAD_FILE, "bad.csv")
    assert session.phase == Phase.EXPLORING
    assert response.phase == Phase.EXPLORING
    assert session.source_name == "data.csv"
    assert session.source_bytes == SAMPLE_CSV
    assert session.source_suffix == ".csv"
    assert session.result is not None
    assert response.text.startswith("⚠️")
    assert "Upload a different file" in (response.chips or [])


def test_failed_reupload_does_not_become_the_audit_source() -> None:
    session = analysed()
    handle_upload(session, BAD_FILE, "bad.csv")
    download = ask(session, "export audit").download
    assert download is not None
    audit = next(iter(download.values()))
    assert isinstance(audit, str)
    assert sha256_bytes(SAMPLE_CSV) in audit
    assert sha256_bytes(BAD_FILE) not in audit
    assert "bad.csv" not in audit


def test_failed_first_upload_leaves_the_session_empty() -> None:
    session = Session()
    response = handle_upload(session, BAD_FILE, "bad.csv")
    assert session.source_bytes is None
    assert session.source_name is None
    assert session.phase == Phase.AWAITING_FILE
    assert response.phase == Phase.AWAITING_FILE


def test_failed_reupload_mid_setup_keeps_the_phase() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "data.csv")
    assert session.phase == Phase.AWAITING_PERIOD
    response = handle_upload(session, BAD_FILE, "bad.csv")
    assert session.phase == Phase.AWAITING_PERIOD
    assert response.phase == Phase.AWAITING_PERIOD
    assert session.source_name == "data.csv"


def test_failed_upload_does_not_consume_the_intro_or_the_comparison_choice() -> None:
    session = Session()
    handle_message(session, "compare to forecast")
    handle_upload(session, BAD_FILE, "bad.csv")
    assert session.intro_shown is False
    assert session.compare_to is not None


def test_file_that_stops_on_a_comparison_choice_becomes_the_session_file() -> None:
    session = analysed()
    name = "fixture_l_budget_and_forecast.csv"
    response = handle_upload(session, (REALWORLD / name).read_bytes(), name)
    assert session.source_name == name
    assert session.result is None
    assert session.phase == Phase.AWAITING_FILE
    assert "Compare to forecast" in (response.chips or [])
    assert "Forecast from 'Forecast'" in ask(session, "Compare to forecast").text


def test_new_file_starts_with_none_of_the_old_choices() -> None:
    session = analysed(FIRST_FILE, "first.csv", unclassified="Revenue")
    session.currency = "EUR"
    assert session.type_map == {"Misc Thing": LineType.REVENUE}
    handle_upload(session, SECOND_FILE, "second.csv")
    assert session.type_map == {}
    assert session.period is None
    assert session.dollar_threshold is None
    assert session.percent_threshold is None
    assert session.currency == "USD"
    assert session.result is None
    assert session.last_focused_item is None
    assert session.last_table_items == []
    assert session.skipped_items == set()
    assert session.detected_period_pairs == []
    assert session.layout_mapping is None
    assert session.compare_to is None
    assert session.unclassified_queue == []
    assert session.source_name == "second.csv"


def test_earlier_type_choice_cannot_override_an_explicit_type_in_the_next_file() -> None:
    session = analysed(FIRST_FILE, "first.csv", unclassified="Revenue")
    handle_upload(session, SECOND_FILE, "second.csv")
    finish_setup(session)
    assert session.result is not None
    row = next(r for r in session.result.rows if r.line_item == "Misc Thing")
    assert row.line_type == LineType.EXPENSE
    assert row.status == Status.UNFAVORABLE


def test_deployment_policy_survives_a_new_upload() -> None:
    session = Session(path_exports_enabled=False)
    analysed(session=session)
    handle_upload(session, SECOND_FILE, "second.csv")
    assert session.path_exports_enabled is False
    assert session.intro_shown is True


@pytest.mark.parametrize("phase", [
    Phase.AWAITING_FILE, Phase.AWAITING_PERIOD, Phase.AWAITING_THRESHOLDS,
    Phase.AWAITING_CURRENCY, Phase.EXPLORING,
])
def test_upload_a_different_file_chip_points_at_the_drop_zone(phase: Phase) -> None:
    session = Session()
    if phase == Phase.EXPLORING:
        analysed(session=session)
    else:
        session.phase = phase
    period = session.period
    response = handle_message(session, "Upload a different file")
    assert "drop zone" in response.text
    assert session.phase == phase
    assert session.period == period


def test_upload_chip_is_not_taken_as_a_period_choice() -> None:
    session = Session()
    session.phase = Phase.AWAITING_PERIOD_CHOICE
    handle_message(session, "Upload a different file")
    assert session.period is None
    assert session.phase == Phase.AWAITING_PERIOD_CHOICE


def test_pasted_table_that_cannot_be_read_explains_why() -> None:
    session = Session()
    response = handle_message(session, "alpha\tbeta\nfoo\tbar\n")
    assert response.text.startswith("⚠️")
    assert "paste a table" in response.text.lower()
    assert session.source_bytes is None
    assert session.phase == Phase.AWAITING_FILE
