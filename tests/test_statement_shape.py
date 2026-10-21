"""Shaping a published income statement into revenue and expense lines (fictional figures)."""

from __future__ import annotations

from decimal import Decimal

from variance_agent.statement_shape import shape_income_statement


def _shape(rows: list[list[object]]):  # type: ignore[no-untyped-def]
    return shape_income_statement([["(In millions)"], ["Line Item", "Jun 2026", "Jun 2025"], *rows])


def _net(shaped) -> list[Decimal]:  # type: ignore[no-untyped-def]
    """Revenue minus expense per period, from the shaped rows."""
    totals = [Decimal(0), Decimal(0)]
    for label, *values, kind in shaped.rows[2:]:
        for i, value in enumerate(values):
            text = str(value).replace(",", "").replace("—", "0")
            amount = -Decimal(text[1:-1]) if text.startswith("(") else Decimal(text)
            totals[i] += amount if kind == "Revenue" else -amount
    return totals


def test_added_block_with_expenses_printed_negative() -> None:
    """Revenue and expense blocks with totals, then a nonoperating block that is added."""
    shaped = _shape([
        ["Passenger revenue", "16,100", "13,836"],
        ["Cargo revenue", "527", "430"],
        ["Total operating revenue", "16,627", "14,266"],
        ["Salaries and related costs", "4,686", "4,413"],
        ["Special charges (credits)", "(145)", "447"],
        ["Total operating expense", "4,541", "4,860"],
        ["Operating income", "12,086", "9,406"],
        ["Interest expense", "(343)", "(361)"],
        ["Interest income", "148", "167"],
        ["Total nonoperating expense, net", "(195)", "(194)"],
        ["Income before income taxes", "11,890", "9,212"],  # 1 below the exact sum: rounding
        ["Income tax expense", "2,000", "1,900"],
        ["Net income", "9,890", "7,312"],
    ])
    assert shaped.rows[1] == ["Line Item", "Jun 2026", "Jun 2025", "Type"]
    assert shaped.rows[2:] == [
        ["Passenger revenue", "16,100", "13,836", "Revenue"],
        ["Cargo revenue", "527", "430", "Revenue"],
        ["Salaries and related costs", "4,686", "4,413", "Expense"],
        ["Special charges (credits)", "(145)", "447", "Expense"],
        ["Interest expense", "343", "361", "Expense"],
        ["Interest income", "148", "167", "Revenue"],
        ["Income tax expense", "2,000", "1,900", "Expense"],
    ]
    assert shaped.subtotals == [
        "Total operating revenue", "Total operating expense", "Operating income",
        "Total nonoperating expense, net", "Income before income taxes", "Net income",
    ]
    assert shaped.unlabeled == []
    assert shaped.flipped == ["Interest expense"]
    assert _net(shaped) == [Decimal("9891"), Decimal("7312")]  # net income, within rounding


def test_subtracted_block_with_income_printed_negative() -> None:
    """Operating income, then lines subtracted from it: income shows as a negative."""
    shaped = _shape([
        ["Net sales", "6,566", "6,412"],
        ["Cost of sales", "4,502", "4,828"],
        ["Operating income", "2,064", "1,584"],
        ["Net interest expense", "411", "502"],
        ["Net other income", "(106)", "(92)"],
        ["Earnings before income taxes", "1,759", "1,174"],
        ["Provision for income taxes", "149", "174"],
        ["Net earnings", "1,610", "1,000"],
    ])
    assert shaped.rows[2:] == [
        ["Net sales", "6,566", "6,412", "Revenue"],
        ["Cost of sales", "4,502", "4,828", "Expense"],
        ["Net interest expense", "411", "502", "Expense"],
        ["Net other income", "106", "92", "Revenue"],
        ["Provision for income taxes", "149", "174", "Expense"],
    ]
    assert shaped.flipped == ["Net other income"]
    assert _net(shaped) == [Decimal("1610"), Decimal("1000")]


def test_gross_profit_and_a_signed_other_line() -> None:
    shaped = _shape([
        ["Product revenue", "1,250.4", "1,100.2"],
        ["Services revenue", "410.6", "388.1"],
        ["Total revenue", "1,661.0", "1,488.3"],
        ["Cost of revenue", "702.3", "640.0"],
        ["Gross profit", "958.7", "848.3"],
        ["Restructuring charges", "—", "12.4"],
        ["Total operating expenses", "—", "12.4"],
        ["Operating income", "958.7", "835.9"],
        ["Other income (expense), net", "(18.7)", "4.2"],
        ["Income before income taxes", "940.0", "840.1"],
    ])
    kinds = {row[0]: row[-1] for row in shaped.rows[2:]}
    assert kinds == {
        "Product revenue": "Revenue", "Services revenue": "Revenue",
        "Cost of revenue": "Expense", "Restructuring charges": "Expense",
        "Other income (expense), net": "Revenue",
    }
    assert shaped.rows[-1] == ["Other income (expense), net", "(18.7)", "4.2", "Revenue"]
    assert _net(shaped) == [Decimal("940.0"), Decimal("840.1")]


def test_comprehensive_income_opens_with_net_income() -> None:
    shaped = _shape([
        ["Net income", "805", "973"],
        ["Employee benefit plans", "(15)", "(23)"],
        ["Investments and other", "2", "(1)"],
        ["Total other comprehensive income (loss), net of tax", "(13)", "(24)"],
        ["Total comprehensive income", "792", "949"],
    ])
    assert shaped.rows[2:] == [
        ["Employee benefit plans", "15", "23", "Expense"],
        ["Investments and other", "2", "(1)", "Revenue"],
    ]
    assert shaped.subtotals[0] == "Net income"


def test_lines_the_arithmetic_cannot_settle_are_left_for_the_user() -> None:
    """Two equal lines: either could be the one subtracted, so neither is labeled."""
    shaped = _shape([
        ["Fees", "50", "50"],
        ["Charges", "50", "50"],
        ["Operating income", "0", "0"],
    ])
    assert shaped.unlabeled == ["Fees", "Charges"]
    assert shaped.notes[-1] == (
        "Couldn't tell from the statement's arithmetic whether 'Fees', 'Charges' add to or "
        "reduce income; you'll be asked to label them")
    assert [row[-1] for row in shaped.rows[2:]] == ["", ""]
    assert [row[1:3] for row in shaped.rows[2:]] == [["50", "50"], ["50", "50"]]


def test_subtotal_that_does_not_add_up_leaves_its_lines_unlabeled() -> None:
    shaped = _shape([
        ["Revenue", "100", "90"],
        ["Cost of revenue", "40", "30"],
        ["Gross profit", "99", "99"],
        ["Income tax expense", "10", "9"],
        ["Net income", "89", "90"],
    ])
    assert shaped.unlabeled == ["Revenue", "Cost of revenue"]
    single = _shape([["Fees", "50", "40"], ["Operating income", "60", "70"]])
    assert single.notes[-1] == (
        "Couldn't tell from the statement's arithmetic whether 'Fees' adds to or reduces "
        "income; you'll be asked to label it")
    assert {row[0]: row[-1] for row in shaped.rows[2:]}["Income tax expense"] == "Expense"


def test_notes_explain_every_change() -> None:
    shaped = _shape([
        ["Net sales", "6,566", "6,412"],
        ["Cost of sales", "4,502", "4,828"],
        ["Operating income", "2,064", "1,584"],
        ["Net other income", "(106)", "(92)"],
        ["Net earnings", "2,170", "1,676"],
    ])
    assert shaped.notes == [
        "Labeled 2 lines revenue and 1 line expense from how the statement adds up",
        "Read 'Net other income' as income: the statement prints it as (106) and "
        "subtracts it",
    ]
    assert shaped.audit_notes[0] == (
        "Left out 2 subtotals the statement computes from the lines above: "
        "Operating income, Net earnings")
    assert "Labeled 'Net sales' as revenue" in shaped.audit_notes


def test_total_costs_row_sums_only_the_costs_above_it() -> None:
    """Revenue with no total of its own, then costs and a "Total costs and expenses" row."""
    shaped = _shape([
        ["Revenues", "90,234", "80,539"],
        ["Cost of revenues", "36,474", "33,712"],
        ["Research and development", "13,808", "12,447"],
        ["General and administrative", "4,001", "3,710"],
        ["Total costs and expenses", "54,283", "49,869"],
        ["Income from operations", "35,951", "30,670"],
    ])
    assert shaped.unlabeled == []
    assert [row[-1] for row in shaped.rows[2:]] == ["Revenue", "Expense", "Expense", "Expense"]
