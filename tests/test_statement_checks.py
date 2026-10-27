"""R9: footing and identities for balance sheets and cash flow statements (docs/analysts/PLAN.md).

Lines are built here from invented figures in millions; every value is fictional.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from variance_agent.statement_checks import CheckLine, check_balance_sheet, check_cash_flow

COLUMNS = ["Sep 2025", "Sep 2024"]
STATEMENT = "Consolidated Balance Sheets"


def line(name: str, *values: str, concept: str = "", decimals: str = "-6", balance: str = "") -> CheckLine:
    return CheckLine(name, concept, tuple((Decimal(v) * 1_000_000, decimals) for v in values), balance)


def balance_sheet(**overrides: CheckLine) -> list[CheckLine]:
    lines = {
        "cash": line("Cash and cash equivalents", "2600", "2000"),
        "receivables": line("Accounts receivable, net", "800", "770"),
        "current": line("Total current assets", "3400", "2770", concept="us-gaap:AssetsCurrent"),
        "property": line("Property and equipment, net", "3100", "2700"),
        "assets": line("Total assets", "6500", "5470", concept="us-gaap:Assets"),
        "payables": line("Accounts payable", "900", "820"),
        "current_liabilities": line("Total current liabilities", "900", "820", concept="us-gaap:LiabilitiesCurrent"),
        "debt": line("Long-term debt", "1500", "1500"),
        "liabilities": line("Total liabilities", "2400", "2320", concept="us-gaap:Liabilities"),
        "stock": line("Common stock", "1", "1"),
        "capital": line("Additional paid-in capital", "1200", "1100"),
        "retained": line("Retained earnings", "2999", "2149"),
        "treasury": line("Treasury stock, at cost", "-100", "-100"),
        "equity": line("Total stockholders' equity", "4100", "3150", concept="us-gaap:StockholdersEquity"),
        "total": line("Total liabilities and stockholders' equity", "6500", "5470",
                      concept="us-gaap:LiabilitiesAndStockholdersEquity"),
    }
    lines.update(overrides)
    return list(lines.values())


def test_a_balanced_sheet_foots_every_subtotal_and_records_the_identity() -> None:
    checked = check_balance_sheet(balance_sheet(), STATEMENT, COLUMNS)
    assert checked.problem == ""
    names = [line.name for line in balance_sheet()]
    assert [names[i] for i, _ in checked.matches] == [
        "Total current assets", "Total assets", "Total current liabilities", "Total liabilities",
        "Total stockholders' equity", "Total liabilities and stockholders' equity"]
    terms = dict(checked.matches)
    assert [names[t] for t, _ in terms[names.index("Total liabilities and stockholders' equity")]] == [
        "Total liabilities", "Total stockholders' equity"]
    assert checked.identity == ("Total assets equals Total liabilities and stockholders' equity in Sep 2025 and Sep 2024, "
                                "within the rounding each figure's decimals state")
    assert checked.closing == len(names) - 1


@pytest.mark.parametrize(("printed", "holds"), [
    ("6500", True),          # exact
    ("6500.4", True),        # within the summed half-widths
    ("6501", True),          # exactly the summed half-widths (0.5m each side): closed intervals touch
    ("6501.000001", False),  # one dollar beyond
])
def test_the_balance_sheet_identity_straddles_the_rounding_boundary(printed: str, holds: bool) -> None:
    # Fraction oracle: the identity holds when |assets - (liabilities and equity)| <= 0.5m + 0.5m.
    oracle = abs(Fraction(6500) - Fraction(printed)) * 1_000_000 <= Fraction(1, 2) * 1_000_000 * 2
    assert oracle is holds
    lines = balance_sheet(total=line("Total liabilities and stockholders' equity", printed, "5470",
                                     concept="us-gaap:LiabilitiesAndStockholdersEquity"))
    # The equity block must still foot to the printed total for the identity to be the deciding check.
    lines[-2] = line("Total stockholders' equity", str(Decimal(printed) - 2400), "3150", concept="us-gaap:StockholdersEquity")
    lines[-3] = line("Treasury stock, at cost", str(Decimal(printed) - 2400 - 4200), "-100")
    checked = check_balance_sheet(lines, STATEMENT, COLUMNS)
    if holds:
        assert checked.problem == ""
    else:
        assert checked.problem == (
            "In the Consolidated Balance Sheets, Total assets ($6,500,000,000) and Total liabilities and stockholders' "
            "equity ($6,501,000,001) differ by more than their rounding in Sep 2025, so I stopped instead of guessing. "
            "Choose another statement from this filing.")


def test_mezzanine_equity_and_noncontrolling_interests_sit_between_liabilities_and_equity() -> None:
    lines = balance_sheet(
        equity=line("Total stockholders' equity", "3900", "3150", concept="us-gaap:StockholdersEquity"),
        total=line("Total liabilities and stockholders' equity", "6500", "5470",
                   concept="us-gaap:LiabilitiesAndStockholdersEquity"))
    lines[-4] = line("Retained earnings", "2799", "2149")
    lines.insert(lines.index(next(x for x in lines if x.name == "Total liabilities")) + 1,
                 line("Redeemable noncontrolling interest", "150", "0"))
    lines.insert(-1, line("Noncontrolling interests", "50", "0"))
    lines.insert(-1, line("Total equity", "3950", "3150",
                          concept="us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"))
    checked = check_balance_sheet(lines, STATEMENT, COLUMNS)
    assert checked.problem == ""
    terms = dict(checked.matches)[len(lines) - 1]
    assert [lines[t].name for t, _ in terms] == ["Total liabilities", "Redeemable noncontrolling interest", "Total equity"]


def test_no_total_liabilities_line_is_needed() -> None:
    lines = [x for x in balance_sheet() if x.name != "Total liabilities"]
    checked = check_balance_sheet(lines, STATEMENT, COLUMNS)
    assert checked.problem == ""
    terms = dict(checked.matches)[len(lines) - 1]
    assert [lines[t].name for t, _ in terms] == ["Total current liabilities", "Long-term debt", "Total stockholders' equity"]


@pytest.mark.parametrize("accumulated", [("Less accumulated depreciation", "1900", "1600"),
                                          ("Accumulated depreciation", "-1900", "-1600")])
def test_a_net_line_after_its_contra_is_a_subtotal(accumulated: tuple[str, str, str]) -> None:
    label, now, before = accumulated
    lines = balance_sheet()
    at = next(i for i, x in enumerate(lines) if x.name == "Property and equipment, net")
    lines[at:at] = [line("Property and equipment, at cost", "5000", "4300"), line(label, now, before)]
    checked = check_balance_sheet(lines, STATEMENT, COLUMNS)
    assert checked.problem == ""
    terms = dict(checked.matches)[at + 2]
    assert [(lines[t].name, w) for t, w in terms] == [("Property and equipment, at cost", 1),
                                                      (label, -1 if label.startswith("Less") else 1)]


def test_a_subtotal_that_nothing_adds_up_to_refuses_naming_it() -> None:
    # Off by 2m: beyond the three figures' summed half-widths (1.5m).
    lines = balance_sheet(current=line("Total current assets", "3402", "2770", concept="us-gaap:AssetsCurrent"))
    checked = check_balance_sheet(lines, STATEMENT, COLUMNS)
    assert checked.problem == ("I couldn't tell which lines 'Total current assets' adds up in the Consolidated Balance "
                               "Sheets, so I can't check it and stopped instead of guessing. Choose another statement "
                               "from this filing.")


def test_a_balance_sheet_without_its_identity_lines_refuses() -> None:
    lines = [x for x in balance_sheet() if x.name != "Total liabilities and stockholders' equity"]
    checked = check_balance_sheet(lines, STATEMENT, COLUMNS)
    assert checked.problem == ("I couldn't find both total assets and total liabilities and equity in the Consolidated "
                               "Balance Sheets, so I can't check that it balances and stopped instead of guessing. "
                               "Choose another statement from this filing.")


def test_lines_after_the_closing_total_are_supplemental() -> None:
    lines = [*balance_sheet(), line("Shares outstanding note line", "5", "5")]
    checked = check_balance_sheet(lines, STATEMENT, COLUMNS)
    assert (checked.problem, checked.closing) == ("", len(lines) - 2)


FLOWS = "Consolidated Statements of Cash Flows"
FLOW_COLUMNS = ["FY2025", "FY2024"]


def cash_flow() -> list[CheckLine]:
    return [
        line("Net income", "1450", "1330", concept="us-gaap:NetIncomeLoss"),
        line("Depreciation and amortization", "200", "180"),
        line("Increase in accounts receivable", "-30", "-20"),
        line("Net cash provided by operating activities", "1620", "1490",
             concept="us-gaap:NetCashProvidedByUsedInOperatingActivities"),
        line("Purchases of property and equipment", "-600", "-500"),
        line("Net cash used in investing activities", "-600", "-500",
             concept="us-gaap:NetCashProvidedByUsedInInvestingActivities"),
        line("Dividends paid", "-400", "-350"),
        line("Net cash used in financing activities", "-400", "-350",
             concept="us-gaap:NetCashProvidedByUsedInFinancingActivities"),
        line("Effect of exchange rate changes on cash", "-20", "10"),
        line("Net increase in cash, cash equivalents and restricted cash", "600", "650"),
        line("Cash, cash equivalents and restricted cash, beginning of year", "2000", "1350", balance="beginning"),
        line("Cash, cash equivalents and restricted cash, end of year", "2600", "2000", balance="ending"),
        line("Cash paid for interest", "45", "38"),
    ]


def test_cash_rolls_forward_from_beginning_to_ending_balance() -> None:
    lines = cash_flow()
    checked = check_cash_flow(lines, FLOWS, FLOW_COLUMNS)
    assert checked.problem == ""
    assert checked.closing == 11
    assert [lines[t].name for t, _ in dict(checked.matches)[11]] == [
        "Net increase in cash, cash equivalents and restricted cash",
        "Cash, cash equivalents and restricted cash, beginning of year"]
    assert [lines[t].name for t, _ in dict(checked.matches)[9]] == [
        "Net cash provided by operating activities", "Net cash used in investing activities",
        "Net cash used in financing activities", "Effect of exchange rate changes on cash"]
    assert checked.identity == ("Ending cash equals beginning cash plus the flows printed between them in FY2025 and "
                                "FY2024, within the rounding each figure's decimals state")


def test_net_income_opening_a_cash_flow_statement_is_a_line() -> None:
    checked = check_cash_flow(cash_flow(), FLOWS, FLOW_COLUMNS)
    assert 0 not in dict(checked.matches)


def test_beginning_cash_may_come_first() -> None:
    lines = cash_flow()
    begin = lines.pop(10)
    lines.insert(0, begin)
    checked = check_cash_flow(lines, FLOWS, FLOW_COLUMNS)
    assert checked.problem == ""
    assert [lines[t].name for t, _ in dict(checked.matches)[11]][-1] == "Net increase in cash, cash equivalents and restricted cash"


def test_without_a_net_change_line_ending_cash_foots_on_the_activities() -> None:
    lines = [x for x in cash_flow() if not x.name.startswith("Net increase")]
    checked = check_cash_flow(lines, FLOWS, FLOW_COLUMNS)
    assert checked.problem == ""


def test_cash_that_does_not_roll_forward_refuses() -> None:
    lines = cash_flow()
    lines[10] = line("Cash, cash equivalents and restricted cash, beginning of year", "2002", "1350", balance="beginning")
    checked = check_cash_flow(lines, FLOWS, FLOW_COLUMNS)
    assert checked.problem.startswith("I couldn't tell which lines 'Cash, cash equivalents and restricted cash, end of "
                                      "year' adds up in the Consolidated Statements of Cash Flows")


def test_a_cash_flow_statement_without_beginning_cash_refuses() -> None:
    lines = [x for x in cash_flow() if x.balance != "beginning"]
    checked = check_cash_flow(lines, FLOWS, FLOW_COLUMNS)
    assert checked.problem == ("I couldn't find the beginning and ending cash balances in the Consolidated Statements of "
                               "Cash Flows, so I can't check that cash rolls forward and stopped instead of guessing. "
                               "Choose another statement from this filing.")


def test_a_discontinued_operations_line_is_a_line_not_a_subtotal() -> None:
    lines = cash_flow()
    lines[3:4] = [line("Net cash provided by operating activities of continuing operations", "1620", "1490",
                       concept="us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
                  line("Net cash provided by discontinued operations", "10", "0",
                       concept="us-gaap:CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations"),
                  line("Net cash provided by operating activities", "1630", "1490",
                       concept="us-gaap:NetCashProvidedByUsedInOperatingActivities")]
    lines[11] = line("Net increase in cash, cash equivalents and restricted cash", "610", "650")
    lines[13] = line("Cash, cash equivalents and restricted cash, end of year", "2610", "2000", balance="ending")
    checked = check_cash_flow(lines, FLOWS, FLOW_COLUMNS)
    assert checked.problem == ""
    assert 4 not in dict(checked.matches)


def test_infinite_decimals_foot_exactly() -> None:
    lines = [line("Cash", "10", "8", decimals="INF"), line("Other", "5", "4", decimals="INF"),
             line("Total assets", "15", "12", decimals="INF", concept="us-gaap:Assets"),
             line("Payables", "15", "12", decimals="INF"),
             line("Total liabilities and equity", "15", "12", decimals="INF", concept="us-gaap:LiabilitiesAndStockholdersEquity")]
    assert check_balance_sheet(lines, STATEMENT, COLUMNS).problem == ""
    lines[2] = line("Total assets", "15.000001", "12", decimals="INF", concept="us-gaap:Assets")
    assert check_balance_sheet(lines, STATEMENT, COLUMNS).problem.startswith("I couldn't tell which lines 'Total assets'")


@pytest.mark.parametrize(("printed", "foots"), [("3401.5", True), ("3401.500001", False), ("3398.5", True)])
def test_a_subtotal_straddles_its_terms_summed_half_widths(printed: str, foots: bool) -> None:
    # Fraction oracle: |(2600 + 800) - printed| <= three half-widths of 0.5m.
    oracle = abs(Fraction(3400) - Fraction(printed)) <= Fraction(3, 2)
    assert oracle is foots
    lines = balance_sheet(current=line("Total current assets", printed, "2770", concept="us-gaap:AssetsCurrent"),
                          property=line("Property and equipment, net", str(6500 - Decimal(printed)), "2700"))
    problem = check_balance_sheet(lines, STATEMENT, COLUMNS).problem
    assert (problem == "") is foots, problem
