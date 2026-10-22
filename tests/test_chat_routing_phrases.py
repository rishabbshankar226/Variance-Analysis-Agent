"""Natural phrasings the chat bot has to route (WS2 P1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.chat_helpers import SAMPLE_CSV, analysed, ask
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.intent import find_line_item, parse_intent
from variance_agent.chat.session import Phase, Session

NBSP = chr(0xA0)
CURLY = chr(0x2019)
REALWORLD = Path(__file__).resolve().parent / "fixtures" / "realworld"


@pytest.mark.parametrize(("text", "intent_id"), [
    ("show me the summary", "summary"),
    ("Show me the summary please", "summary"),
    ("can you show me the waterfall", "waterfall"),
    ("could you show us the executive memo", "executive_memo"),
    ("give me the summary", "summary"),
    ("give me the biggest risks", "biggest_risks"),
    ("show me the revenue", "filter_type_rev"),
    ("show me top 3", "top_n"),
    ("give me the top 3 variances", "top_n"),
    ("show me unfavorable", "filter_status_u"),
    ("unfavourable", "filter_status_u"),
    ("show all unfavourable variances", "filter_status_u"),
    ("favourable", "filter_status_f"),
    ("favourable versus unfavourable", "concept_f_vs_u"),
    ("where did we save money", "cost_savings"),
    (f"what{CURLY}s the short story", "tldr"),
    (f"show{NBSP}me{NBSP}the{NBSP}summary", "summary"),
    ("tell me about Marketing", "explain"),
    ("give me color on Marketing", "explain"),
    ("top 3 expenses", "top_n"),
    ("top 5 revenue lines", "top_n"),
])
def test_phrase_routes_to_its_intent(text: str, intent_id: str) -> None:
    assert parse_intent(text).intent_id == intent_id


def test_show_me_an_item_is_a_detail_lookup() -> None:
    parsed = parse_intent("show me Marketing")
    assert parsed.intent_id == "detail"
    assert parsed.captures["item"] == "Marketing"


def test_top_n_captures_the_kind_of_line() -> None:
    parsed = parse_intent("top 3 expenses")
    assert parsed.captures["count"] == "3"
    assert parsed.captures["kind"].lower().startswith("expense")


@pytest.mark.parametrize("text", ["show me the summary", "give me the summary"])
def test_polite_summary_request_gets_the_summary(text: str) -> None:
    assert "Analysis Complete" in ask(analysed(), text).text


def test_show_me_the_top_three_shows_three_rows() -> None:
    response = ask(analysed(), "show me the top 3")
    assert response.table is not None
    assert len(response.table) == 3


def test_top_zero_is_refused_rather_than_shown_as_top_one() -> None:
    response = ask(analysed(), "top 0")
    assert response.table is None
    assert "at least 1" in response.text


def test_top_expenses_only_lists_expense_rows() -> None:
    response = ask(analysed(), "top 3 expenses")
    assert response.table is not None
    assert len(response.table) == 3
    assert {row["Type"] for row in response.table} == {"Expense"}
    assert "Expense" in response.text


def test_top_revenue_only_lists_revenue_rows() -> None:
    response = ask(analysed(), "top 5 revenue")
    assert response.table is not None
    assert {row["Type"] for row in response.table} == {"Revenue"}
    assert len(response.table) == 2


@pytest.mark.parametrize("text", [
    "why is marketing over budget?",
    "why did marketing go up?",
    "Why is marketing so high",
    "explain why marketing is over",
])
def test_why_sentence_about_an_item_explains_that_item(text: str) -> None:
    response = ask(analysed(), text)
    assert "Driver Evidence: Marketing" in response.text


def test_why_sentence_about_an_item_by_word_explains_that_item() -> None:
    assert "Driver Evidence: Payroll" in ask(analysed(), "why did payroll go up?").text


def test_detail_sentence_about_an_item() -> None:
    response = ask(analysed(), "details on how marketing is doing")
    assert "Marketing" in response.text
    assert "No line item" not in response.text


def test_unknown_item_in_a_why_sentence_still_says_so() -> None:
    assert "No line item matching" in ask(analysed(), "why is zzzqq over budget?").text


# ---- export paths -----------------------------------------------------------


@pytest.mark.parametrize("text", [
    "download report now", "export report please now", "save csv today", "write audit here",
    "export excel to desktop",
])
def test_plain_words_after_export_are_not_taken_as_a_file_path(
    text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    session = analysed(session=Session(path_exports_enabled=True))
    response = ask(session, text)
    assert response.download is not None
    assert list(tmp_path.iterdir()) == []


def test_plain_words_after_export_are_not_refused_on_the_hosted_server() -> None:
    session = analysed(session=Session(path_exports_enabled=False))
    response = ask(session, "download report now")
    assert response.download is not None
    assert "turned off" not in response.text


def test_a_real_path_still_writes_a_file(tmp_path: Path) -> None:
    session = analysed(session=Session(path_exports_enabled=True))
    target = tmp_path / "out.md"
    response = ask(session, f"export report to {target}")
    assert response.download is None
    assert target.read_text(encoding="utf-8").startswith("#")


def test_a_real_path_is_refused_on_the_hosted_server(tmp_path: Path) -> None:
    session = analysed(session=Session(path_exports_enabled=False))
    response = ask(session, f"export report to {tmp_path / 'out.md'}")
    assert "turned off" in response.text
    assert not (tmp_path / "out.md").exists()


# ---- phases -----------------------------------------------------------------


@pytest.mark.parametrize("phase", [
    Phase.AWAITING_FILE, Phase.AWAITING_PERIOD, Phase.AWAITING_THRESHOLDS, Phase.EXPLORING,
])
def test_help_reports_the_phase_the_session_is_in(phase: Phase) -> None:
    session = Session()
    if phase == Phase.EXPLORING:
        analysed(session=session)
    else:
        session.phase = phase
    assert handle_message(session, "help").phase == phase


def _multi_period_session() -> Session:
    session = Session()
    path = REALWORLD / "fixture_e_wide_monthly.xlsx"
    handle_upload(session, path.read_bytes(), path.name)
    assert session.phase == Phase.AWAITING_PERIOD_CHOICE
    return session


def test_free_text_period_choice_is_not_accepted() -> None:
    session = _multi_period_session()
    response = handle_message(session, "banana")
    assert session.phase == Phase.AWAITING_PERIOD_CHOICE
    assert session.period is None
    assert response.chips is not None and "Q3" in response.chips


def test_period_choice_accepts_a_detected_period_in_any_case() -> None:
    session = _multi_period_session()
    handle_message(session, "q3")
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert session.period == "Q3"


def test_period_choice_without_a_stored_file_asks_for_one_instead_of_asserting() -> None:
    session = _multi_period_session()
    session.source_bytes = None
    response = handle_message(session, "Q3")
    assert "upload" in response.text.lower()
    assert session.phase == Phase.AWAITING_FILE


def test_analysis_without_thresholds_asks_for_them_instead_of_asserting() -> None:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "a.csv")
    session.period = "Q3 2026"
    session.phase = Phase.AWAITING_CURRENCY
    response = handle_message(session, "USD")
    assert "threshold" in response.text.lower()
    assert session.phase == Phase.AWAITING_THRESHOLDS


def test_exploring_without_a_result_restarts_instead_of_asserting() -> None:
    session = Session()
    session.phase = Phase.EXPLORING
    response = handle_message(session, "summary")
    assert "upload" in response.text.lower()
    assert session.phase == Phase.AWAITING_FILE


# ---- matching -----------------------------------------------------------------


def test_find_line_item_matches_across_unicode_spellings() -> None:
    items = [f"Bob{CURLY}s{NBSP}Burgers", "Rent"]
    assert find_line_item("bob's burgers", items) == items[:1]
    assert find_line_item(f"BOB{CURLY}S", items) == items[:1]


def test_find_line_item_lists_a_repeated_name_once() -> None:
    assert find_line_item("travel", ["Travel", "Rent", "Travel"]) == ["Travel"]


# ---- a period typed instead of clicking "Looks right" -----------------------------


def _at_confirmation() -> Session:
    session = _multi_period_session()
    handle_message(session, "Q3")
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    return session


def _single_period_at_confirmation() -> Session:
    session = Session()
    handle_message(session, "Line Item\tBudget\tActual\nRent\t100\t120\n")
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    return session


def test_typed_period_must_be_a_detected_one_when_the_file_has_several() -> None:
    session = _at_confirmation()
    response = handle_message(session, "FY2031")
    assert session.period == "Q3"
    assert session.phase == Phase.AWAITING_INTAKE_CONFIRMATION
    assert response.phase == Phase.AWAITING_INTAKE_CONFIRMATION


def test_typed_detected_period_re_reads_the_file_for_that_period() -> None:
    session = _at_confirmation()
    response = handle_message(session, "aug-26")
    assert session.period == "Aug-26"
    assert "Analyzed period:** Aug-26" in response.text


@pytest.mark.parametrize("text", [
    "may I change something?", "may I change something", "Can I switch to March",
    "what about the sep numbers",
])
def test_a_question_at_confirmation_is_not_taken_as_the_period(text: str) -> None:
    session = _single_period_at_confirmation()
    handle_message(session, text)
    assert session.period is None


def test_a_short_period_typed_at_confirmation_is_still_accepted() -> None:
    session = _single_period_at_confirmation()
    handle_message(session, "Q3 2026")
    assert session.period == "Q3 2026"
    assert session.phase == Phase.AWAITING_THRESHOLDS


# ---- keyword hijack by substring --------------------------------------------------

KEYWORD_FILE = b"""Line Item,Type,Budget,Actual
Product Sales,Revenue,100000,120000
Profit Sharing,Expense,10000,16000
HR,Expense,20000,25000
IT,Expense,5000,9000
Rent,Expense,15000,15000
"""


def test_an_item_named_in_full_beats_the_profit_keyword() -> None:
    session = analysed(KEYWORD_FILE)
    response = ask(session, "profit sharing looks high")
    assert "Here is what happened with **Profit Sharing**" in response.text


def test_the_profit_keyword_still_means_profitability() -> None:
    session = analysed(KEYWORD_FILE)
    assert "Profitability Standing" in ask(session, "how is our profit looking").text


@pytest.mark.parametrize("text", ["I am happy with three", "that is it for now thanks a lot"])
def test_short_account_names_do_not_match_inside_other_words(text: str) -> None:
    session = analysed(KEYWORD_FILE)
    response = ask(session, text)
    assert "what happened with" not in response.text


def test_a_short_account_name_matches_as_a_whole_word() -> None:
    session = analysed(KEYWORD_FILE)
    assert "what happened with **HR**" in ask(session, "hr looks high this quarter").text
