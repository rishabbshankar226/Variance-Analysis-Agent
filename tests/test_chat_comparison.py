"""Chat: choosing and naming the comparison basis (Budget, Forecast, Prior Period)."""

from __future__ import annotations

import re
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
    "memo", "tldr",
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


def test_chat_forecast_upload_summary_never_says_budget() -> None:
    text = _upload_response("fixture_k_forecast.csv").text
    assert "Forecast from 'Forecast'" in text
    assert "budget" not in text.lower()


def test_chat_choosing_forecast_reply_never_says_budget() -> None:
    session = _upload("fixture_l_budget_and_forecast.csv")
    text = _ask(session, "Compare to forecast").text
    assert "Forecast from 'Forecast'" in text
    assert "budget" not in text.lower()


def test_chat_prior_period_upload_summary_names_prior_period() -> None:
    text = _upload_response("fixture_j_10k_three_years.csv").text
    assert "Prior Period (FY2024) from 'FY2024'" in text
    assert "budget" not in text.lower()


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


# --- Final review I1/I2: nothing calls a forecast or prior period a budget, plan or target ---

PLAN_WORDS = re.compile(r"\b(budget\w*|plan|planned|target\w*)\b", re.IGNORECASE)

# Every result prompt a non-Budget session can reach. `help` is excluded: it is the
# generic command list (it documents the `budget utilization` command by name).
ALL_RESULT_PROMPTS = [
    "summary", "top 3", "material", "unfavorable", "favorable", "revenue", "expenses",
    "totals", "warnings", "recommendations", "memo", "tldr", "profitability", "waterfall",
    "what if revenue drops 10%", "what if we cut expenses by 5%", "sensitivity", "run rate",
    "drivers summary", "biggest risks", "biggest wins", "revenue status", "expense status",
    "burn rate", "highest percent", "metrics", "pareto", "unbudgeted spend", "cost savings",
    "revenue misses", "did expenses stay in budget?", "compare revenue vs expenses",
]

FORECAST_BLANK = (
    b"Line Item,Type,Forecast,Actual\n"
    b"Subscription Revenue,Revenue,110000,115500\n"
    b"New Partner Revenue,Revenue,,2500\n"
    b"Payroll Expense,Expense,65000,68000\n"
)
PRIOR_BLANK = (
    b"Line Item,Type,FY2025,FY2024\n"
    b"Product Revenue,Revenue,120000,100000\n"
    b"New Segment Revenue,Revenue,5000,\n"
    b"Cost of Revenue,Expense,50000,45000\n"
)


def _no_plan_words(text: str, where: str) -> None:
    found = PLAN_WORDS.findall(text)
    assert not found, f"{where}: {found}"


@pytest.mark.parametrize("fixture_name", ["fixture_k_forecast.csv", "fixture_j_10k_three_years.csv"])
def test_non_budget_session_never_says_budget_plan_or_target(fixture_name: str) -> None:
    session = Session()
    _no_plan_words(_upload_response(fixture_name, session).text, "upload")
    _configure(session)
    assert session.result is not None and session.result.config.comparison_basis is not B
    assert session.result is not None
    item_prompts = [f"{verb} {row.line_item}" for row in session.result.rows for verb in ("why", "details")]
    for prompt in ALL_RESULT_PROMPTS + item_prompts:
        _no_plan_words(_ask(session, prompt).text, prompt)


@pytest.mark.parametrize(
    ("data", "noun", "zero_wording"),
    [(FORECAST_BLANK, "forecast", "not in forecast"), (PRIOR_BLANK, "prior period", "new this period")],
    ids=["forecast", "prior_period"],
)
def test_blank_comparison_prompt_names_the_basis(data: bytes, noun: str, zero_wording: str) -> None:
    session = Session()
    response = handle_upload(session, data, "blank.csv")
    assert session.phase == Phase.AWAITING_BLANK_BUDGET_CONFIRMATION
    assert f"blank {noun} values" in response.text and zero_wording in response.text
    _no_plan_words(response.text, "blank prompt")
    for chip in response.chips or []:
        _no_plan_words(chip, "blank chip")

    confirmed = _ask(session, (response.chips or [""])[0])
    _no_plan_words(confirmed.text, "blank confirmation")
    assert f"Treated blank {noun} values as 0" in confirmed.text
    assert session.parsed_rows is not None
    assert any(r["budget"] == Decimal("0") for r in session.parsed_rows)


def test_keep_blank_forecast_chip_keeps_blanks() -> None:
    session = Session()
    response = handle_upload(session, FORECAST_BLANK, "blank.csv")
    assert response.chips is not None and response.chips[1] == "Keep blank forecast values"
    confirmed = _ask(session, response.chips[1])
    assert "Treated blank" not in confirmed.text


def test_bad_forecast_cell_problem_names_forecast() -> None:
    data = b"Line Item,Type,Forecast,Actual\nSubscription Revenue,Revenue,abc,115500\nPayroll Expense,Expense,1,2\n"
    session = Session()
    text = handle_upload(session, data, "bad.csv").text
    assert "Forecast column" in text
    _no_plan_words(text, "problem")


def test_failed_basis_switch_reply_never_says_plan() -> None:
    session = _upload("fixture_j_10k_three_years.csv")
    _configure(session)
    text = _ask(session, "compare to forecast").text
    assert text.startswith("⚠️")
    _no_plan_words(text, "error reply")


FORECAST_MISSES = (
    b"Line Item,Type,Forecast,Actual\n"
    b"Subscription Revenue,Revenue,120000,100000\n"
    b"Services Revenue,Revenue,30000,31000\n"
    b"Payroll Expense,Expense,65000,72000\n"
    b"Rent Expense,Expense,10000,9000\n"
)
PRIOR_ON_TRACK = (
    b"Line Item,Type,FY2025,FY2024\n"
    b"Product Revenue,Revenue,100010,100000\n"
    b"Cost of Revenue,Expense,50000,50010\n"
)


@pytest.mark.parametrize(
    "data", [FORECAST_MISSES, PRIOR_ON_TRACK], ids=["forecast_misses", "prior_period_on_track"]
)
def test_miss_and_no_risk_branches_never_say_plan_or_target(data: bytes) -> None:
    session = Session()
    _no_plan_words(handle_upload(session, data, "inline.csv").text, "upload")
    _configure(session)
    assert session.result is not None
    item_prompts = [f"{verb} {row.line_item}" for row in session.result.rows for verb in ("why", "details")]
    for prompt in ALL_RESULT_PROMPTS + item_prompts:
        _no_plan_words(_ask(session, prompt).text, prompt)


# --- Final review I5: a new upload starts a fresh comparison choice ---


def test_new_upload_clears_previous_comparison_choice() -> None:
    session = _upload("fixture_l_budget_and_forecast.csv")
    _ask(session, "Compare to forecast")
    _configure(session)
    assert session.compare_to is F
    sample = Path(__file__).resolve().parent.parent / "examples" / "sample_variance.csv"
    response = handle_upload(session, sample.read_bytes(), sample.name)
    assert not response.text.startswith("⚠️"), response.text
    assert session.compare_to is None
    assert session.intake_result is not None and not session.intake_result.has_fatal_errors
    assert session.intake_result.comparison_basis is B


def test_mixed_named_and_year_columns_offer_both_chips() -> None:
    session = Session()
    data = b"Line Item,Type,Budget,FY2025,FY2024\nRent Expense,Expense,90,130,100\n"
    response = handle_upload(session, data, "mixed.csv")
    assert response.text.startswith("⚠️")
    assert response.chips is not None
    assert response.chips[:2] == ["Compare to budget", "Compare to prior period"]
    assert not any("--compare-to" in chip for chip in response.chips)
    assert "--compare-to" not in response.text

    _ask(session, "compare to prior period")
    assert session.intake_result is not None
    assert session.intake_result.comparison_basis is P


def test_empty_forecast_file_error_never_says_budget() -> None:
    session = Session()
    response = handle_upload(session, b"Line Item,Type,Forecast,Actual\n", "empty.csv")
    assert response.text.startswith("⚠️")
    _no_plan_words(response.text, "empty file")
    _no_plan_words(session.last_technical_detail or "", "technical detail")
