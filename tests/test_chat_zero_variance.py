"""C5: a total that matches its comparison exactly is Neutral (in line), as the engine has it (fictional data)."""

from __future__ import annotations

import pytest

from tests.chat_helpers import analysed, ask

# Every line on budget, so every total and projection variance is exactly zero.
ON_BUDGET = b"""Line Item,Type,Budget,Actual
Fictional Product Sales,Revenue,100000,100000
Fictional Service Revenue,Revenue,50000,50000
Fictional Deposits,Revenue,0,0
Fictional Payroll,Expense,60000,60000
Fictional Rent,Expense,15000,15000
"""
# The same file one cent up on revenue: the boundary's other side keeps F and the old words.
ONE_CENT_UP = ON_BUDGET.replace(b"Fictional Product Sales,Revenue,100000,100000",
                                b"Fictional Product Sales,Revenue,100000,100000.01")


def _statuses(table: list[dict[str, object]] | None, column: str = "Status") -> list[object]:
    assert table is not None
    return [row[column] for row in table if column in row]


@pytest.mark.parametrize("prompt", ["compare actual vs budget", "run rate", "what if fictional deposits drops 10%"])
def test_a_zero_total_is_neutral_in_the_tables(prompt: str) -> None:
    statuses = _statuses(ask(analysed(ON_BUDGET), prompt).table)
    assert statuses and set(statuses) == {"Neutral"}


def test_only_the_unchanged_sensitivity_scenario_is_neutral() -> None:
    table = ask(analysed(ON_BUDGET), "sensitivity").table or []
    assert {row["Scenario"]: row["Status"] for row in table} == {
        "Severe Downside (-10% Rev, +5% Exp)": "U", "Moderate Downside (-5% Rev, +2% Exp)": "U",
        "Baseline Actuals (Current)": "Neutral", "Moderate Upside (+5% Rev, -2% Exp)": "F",
        "Strong Upside (+10% Rev, -5% Exp)": "F"}


def test_run_rate_variances_match_their_exact_values() -> None:
    from decimal import ROUND_HALF_EVEN, Decimal
    from fractions import Fraction

    from tests.chat_helpers import SAMPLE_CSV

    table = ask(analysed(SAMPLE_CSV), "run rate").table or []
    shown = {row["Projection Model"]: row["Var vs Budget ($)"] for row in table}
    ytd = Fraction(167000 - 120800) - Fraction(150000 - 100000)  # Actual profit - Budget profit, Q3: 9 of 12 months

    def money(value: Fraction) -> str:
        cents = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal("0.01"), ROUND_HALF_EVEN)
        return f"-${-cents:,.2f}" if cents < 0 else f"${cents:,.2f}"

    assert shown["Annualized Run-Rate (Current Pace)"] == money(ytd * Fraction(12, 9))  # Fraction oracle
    assert shown["Latest Estimate (LE: Actuals + Remaining Plan)"] == money(ytd)


def test_the_memo_says_in_line_and_held() -> None:
    response = ask(analysed(ON_BUDGET), "summarize for the board")
    assert "Operating Profit finished at **$75,000.00**, **in line with** the planned budget of **$75,000.00**" in response.text
    assert "Operating margin **held** at **50.0%**" in response.text
    assert "($0.00, +0.0%, in line)." in response.text
    assert "shortfall" not in response.text and "Favorable" not in response.text
    outcomes = _statuses(response.table, "Outcome")
    assert outcomes == ["In line", "In line", "Neutral"]


@pytest.mark.parametrize(("prompt", "words"), [
    ("budget utilization", "(in line with budget)"),
    ("compare actual vs budget", "Operating profit finished at **$75,000.00**, **in line with** the budget target of $75,000.00."),
    ("run rate", "in line with annual budget of"),
    ("hi", "Overall net operating impact is **in line with** budget."),
    ("are we profitable", "(in line with budget; margin change:"),
])
def test_a_zero_total_is_in_line_in_the_text(prompt: str, words: str) -> None:
    response = ask(analysed(ON_BUDGET), prompt)
    assert words in response.text
    assert "beat" not in response.text and "shortfall" not in response.text


@pytest.mark.parametrize(("prompt", "words"), [
    ("budget utilization", "(beat by $0.01)"),
    ("compare actual vs budget", "**$0.01 beat**"),
    ("hi", "**$0.01 favorable beat**"),
    ("are we profitable", "(favorable beat;"),
])
def test_one_cent_up_keeps_the_favorable_words(prompt: str, words: str) -> None:
    response = ask(analysed(ONE_CENT_UP), prompt)
    assert words in response.text


def test_one_cent_up_keeps_f_in_the_tables() -> None:
    response = ask(analysed(ONE_CENT_UP), "compare actual vs budget")
    assert _statuses(response.table) == ["F", "Neutral", "F"]
