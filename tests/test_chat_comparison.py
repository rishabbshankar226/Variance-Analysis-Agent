"""Chat: choosing and naming the comparison basis (Budget, Forecast, Prior Period)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tests.comparison_helpers import B, F, P, cfg
from variance_agent.analysis import analyze_rows
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.intent import parse_intent
from variance_agent.chat.responses import Response
from variance_agent.chat.session import Phase, Session
from variance_agent.models import ComparisonBasis

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "realworld"
RESULT_PROMPTS = [
    "summary", "top variances", "did expenses stay in budget?", "unbudgeted spend", "warnings",
]


def _new() -> Session:
    return Session()


def _upload_response(fixture_name: str, session: Session | None = None) -> Response:
    target = session if session is not None else Session()
    return handle_upload(target, (FIXTURES_DIR / fixture_name).read_bytes(), fixture_name)


def _upload(fixture_name: str, session: Session | None = None) -> Session:
    target = session if session is not None else Session()
    _upload_response(fixture_name, target)
    return target


def _ask(session: Session, text: str) -> Response:
    return handle_message(session, text)


def _configure(session: Session) -> None:
    answers = {
        Phase.AWAITING_INTAKE_CONFIRMATION: "Looks right",
        Phase.AWAITING_PERIOD: "FY2025",
        Phase.AWAITING_THRESHOLDS: "$1,000 or 5%",
        Phase.AWAITING_CURRENCY: "USD",
        Phase.RESOLVE_UNCLASSIFIED: "Expense",
    }
    while session.phase in answers:
        handle_message(session, answers[session.phase])
    assert session.phase == Phase.EXPLORING


def test_chat_forecast_session_never_says_budget() -> None:
    session = _upload("fixture_k_forecast.csv")
    _configure(session)
    for prompt in RESULT_PROMPTS:
        assert "budget" not in _ask(session, prompt).text.lower(), prompt


def test_chat_prior_period_session_never_says_budget() -> None:
    session = _upload("fixture_j_10k_three_years.csv")
    _configure(session)
    assert session.result is not None
    assert session.result.config.comparison_basis is P
    for prompt in RESULT_PROMPTS:
        assert "budget" not in _ask(session, prompt).text.lower(), prompt


def test_chat_result_tables_name_the_comparison() -> None:
    session = _upload("fixture_k_forecast.csv")
    _configure(session)
    response = _ask(session, "summary")
    assert response.table is not None
    assert "Forecast" in response.table[0]
    assert "Budget" not in response.table[0]


def test_chat_unbudgeted_wording_follows_basis() -> None:
    forecast = _upload("fixture_k_forecast.csv")
    _configure(forecast)
    assert "Spending Not in Forecast" in _ask(forecast, "unbudgeted spend").text

    prior = _upload("fixture_j_10k_three_years.csv")
    _configure(prior)
    text = _ask(prior, "unbudgeted spend").text
    assert "New Spending This Period" in text
    assert "New Segment Revenue" in text


def test_chat_unreconciled_drivers_name_the_comparison() -> None:
    rows: list[dict[str, object]] = [
        {"line_item": "Widgets", "type": "Revenue", "budget": "100000",
         "actual": "120000", "budget_volume": "10", "actual_volume": "10",
         "budget_price": "10", "actual_price": "10"},
    ]
    session = _new()
    session.result = analyze_rows(rows, cfg(F, dollar_threshold=Decimal("1000")))
    session.phase = Phase.EXPLORING
    text = _ask(session, "why Widgets").text
    assert "do not reconcile to Forecast/Actual" in text
    assert "budget" not in text.lower()


def test_chat_ambiguous_file_offers_chips() -> None:
    response = _upload_response("fixture_l_budget_and_forecast.csv")
    assert response.chips is not None
    assert response.chips[:2] == ["Compare to budget", "Compare to forecast"]


def test_chat_single_basis_file_offers_no_comparison_chips() -> None:
    response = _upload_response("fixture_b_departmental_subtotals.csv")
    assert not any(chip.startswith("Compare to") for chip in response.chips or [])


def test_chat_switch_comparison_rereads_source() -> None:
    session = _upload("fixture_l_budget_and_forecast.csv")
    _ask(session, "Compare to budget")
    _configure(session)
    assert session.result is not None
    assert session.result.config.comparison_basis is B

    response = _ask(session, "compare to forecast")
    assert session.compare_to is F
    assert session.intake_result is not None
    assert session.intake_result.comparison_basis is F
    assert session.parsed_rows is not None
    assert session.parsed_rows[0]["budget"] == Decimal("110000")
    assert session.result.config.comparison_basis is F
    assert "Forecast" in response.text
    assert "budget" not in response.text.lower()


def test_chat_compare_to_before_upload_is_used_on_upload() -> None:
    session = _new()
    _ask(session, "compare to forecast")
    assert session.compare_to is F
    _upload("fixture_l_budget_and_forecast.csv", session)
    assert session.intake_result is not None
    assert not session.intake_result.has_fatal_errors
    assert session.intake_result.comparison_basis is F


def test_chat_failed_switch_keeps_current_comparison() -> None:
    session = _upload("fixture_k_forecast.csv")
    _configure(session)
    response = _ask(session, "compare to budget")
    assert "No budget column found" in (session.last_technical_detail or "")
    assert response.text.startswith("⚠️")
    assert session.compare_to is None
    assert session.phase == Phase.EXPLORING
    assert session.result is not None
    assert session.result.config.comparison_basis is F


def test_chat_reset_clears_comparison_choice() -> None:
    session = _new()
    _ask(session, "compare to prior period")
    session.reset()
    assert session.compare_to is None


@pytest.mark.parametrize(
    ("text", "basis"),
    [
        ("compare to budget", "budget"),
        ("Compare to the forecast", "forecast"),
        ("compare to prior year", "prior year"),
        ("compare to last year", "last year"),
        ("compare to prior period?", "prior period"),
    ],
)
def test_set_comparison_intent(text: str, basis: str) -> None:
    intent = parse_intent(text)
    assert intent.intent_id == "set_comparison"
    assert intent.captures["basis"] == basis


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [("prior year", P), ("last year", P), ("prior period", P)],
)
def test_prior_period_phrases_choose_prior_period(phrase: str, expected: ComparisonBasis) -> None:
    session = _new()
    _ask(session, f"compare to {phrase}")
    assert session.compare_to is expected


def test_chat_explains_comparison_types() -> None:
    text = _ask(_new(), "what can I compare against?").text.lower()
    assert "prior period" in text
    assert "forecast" in text
    assert "--compare-to" in text
