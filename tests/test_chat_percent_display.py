"""Percentages and thresholds the chat bot shows (WS2 P2)."""

from __future__ import annotations

from tests.chat_helpers import SAMPLE_CSV, analysed, ask
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session

NEGATIVE_BUDGET = (
    b"Line Item,Type,Budget,Actual\n"
    b"Sales,Revenue,1000,900\n"
    b"Rebate Expense,Expense,-1000,-500\n"
)


# ---- a negative cost budget: percent is of the absolute budget, like the engine ---------


def test_macro_comparison_uses_the_same_percent_as_the_summary() -> None:
    session = analysed(NEGATIVE_BUDGET)
    assert "50.0%" in ask(session, "summary").text
    table = ask(session, "compare actual vs budget").table
    assert table is not None
    expenses = next(row for row in table if row["Metric"] == "Total Expenses")
    assert expenses["Variance (%)"] == "+50.0%"


def test_memo_expense_percent_is_of_the_absolute_budget() -> None:
    memo = ask(analysed(NEGATIVE_BUDGET), "memo").text
    expense_line = next(line for line in memo.splitlines() if line.startswith("Total Operating Expenses"))
    assert "+50.0%" in expense_line
    assert "-50.0%" not in expense_line


def test_utilization_is_not_shown_against_a_negative_budget() -> None:
    session = analysed(NEGATIVE_BUDGET)
    for prompt in ("budget utilization", "expense status"):
        text = ask(session, prompt).text
        assert "Utilization" in text, prompt
        assert "Utilization:** 50.0%" not in text, prompt
        assert "N/A" in text, prompt


def test_normal_positive_budgets_keep_their_utilization() -> None:
    session = analysed()
    assert "Utilization:** **" in ask(session, "budget utilization").text
    assert "Budget Utilization:** " in ask(session, "expense status").text


# ---- thresholds are shown with every significant digit ------------------------------------


def _with_thresholds(spec: str) -> tuple[Session, str]:
    session = Session()
    handle_upload(session, SAMPLE_CSV, "a.csv")
    handle_message(session, "Q3 2026")
    set_text = handle_message(session, spec).text
    handle_message(session, "USD")
    assert session.phase == Phase.EXPLORING
    return session, set_text


def test_fractional_thresholds_are_not_rounded_in_the_confirmation() -> None:
    _, set_text = _with_thresholds("$2.505 or 0.125%")
    assert "**$2.505** or **0.125%**" in set_text


def test_fractional_thresholds_are_not_rounded_in_answers() -> None:
    session, _ = _with_thresholds("$2.505 or 0.125%")
    for prompt in ("summary", "material", "memo", "hello"):
        assert "$2.505 or 0.125%" in ask(session, prompt).text, prompt


def test_ordinary_thresholds_look_as_before() -> None:
    session, set_text = _with_thresholds("$10,000 or 5%")
    assert "**$10,000.00** or **5.0%**" in set_text
    assert "**Thresholds:** $10,000.00 or 5.0%" in ask(session, "summary").text
