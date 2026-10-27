"""Decision 39: the fixes after Draw B, each pinned by a fictional filing (HALVORSEN.FAKE)."""

from __future__ import annotations

from decimal import Decimal

from tests.fixtures.ixbrl.build_ixbrl import operations_and_comprehensive_loss_filing
from variance_agent.intake import IntakeResult, read_input_assisted

M = Decimal(1_000_000)


def _read(data: bytes, **options: object) -> IntakeResult:
    return read_input_assisted(data, ".htm", filename="hal-20250927.htm", **options)  # type: ignore[arg-type]


def test_net_loss_printed_twice_keeps_its_name_and_is_the_bottom_line() -> None:
    result = _read(operations_and_comprehensive_loss_filing())
    assert not result.has_fatal_errors, result.fatal_error_message
    names = [str(r["line_item"]) for r in result.rows]
    assert "Operating expenses: Net loss" not in names
    assert not any(name.startswith("Operating expenses:") for name in names)
    # The bottom line is a subtotal the statement computes, so the arithmetic places interest income.
    assert not any("Couldn't tell" in note for note in result.reader_notes), result.reader_notes
    assert any(note.startswith("Left out 3 lines below 'Net loss'") for note in result.reader_notes), result.reader_notes


def test_interest_income_below_the_operating_loss_is_never_revenue() -> None:
    result = _read(operations_and_comprehensive_loss_filing())
    assert not result.has_fatal_errors, result.fatal_error_message
    revenue = [str(r["line_item"]) for r in result.rows if r["type"] == "Revenue"]
    assert revenue == ["Collaboration revenue"]
    interest = next(r for r in result.rows if r["line_item"] == "Interest income")
    assert (interest["type"], Decimal(str(interest["actual"])), Decimal(str(interest["budget"]))) == (
        "Expense", -27 * M, -34 * M)


def _engine(result: IntakeResult) -> dict[str, str]:
    from variance_agent.analysis import analyze_rows
    from variance_agent.models import AnalysisConfig, ComparisonBasis
    assert not result.has_fatal_errors, result.fatal_error_message
    config = AnalysisConfig("FY2025", Decimal(1), Decimal("0.01"), comparison_basis=ComparisonBasis.PRIOR_PERIOD)
    return {row.line_item: row.line_type.value for row in analyze_rows(result.rows, config).rows}


def test_a_line_the_arithmetic_cannot_place_is_not_typed_revenue_by_its_label() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import fact, income_filing, row
    # No subtotal covers 'Interest income', so the statement's arithmetic can't say whether it adds to income;
    # the filing prints its revenue ('Net sales'), so the line's label must not make it revenue (Decision 39).
    rows = [row("Net sales", fact("us-gaap:Revenues", "FY25", "4,100"), fact("us-gaap:Revenues", "FY24", "3,900")),
            row("Cost of sales", fact("us-gaap:CostOfRevenue", "FY25", "2,300"), fact("us-gaap:CostOfRevenue", "FY24", "2,250")),
            row("Gross margin", fact("us-gaap:GrossProfit", "FY25", "1,800"), fact("us-gaap:GrossProfit", "FY24", "1,650")),
            row("Interest income", fact("us-gaap:InvestmentIncomeInterest", "FY25", "27"),
                fact("us-gaap:InvestmentIncomeInterest", "FY24", "34"))]
    result = _read(income_filing(rows))
    types = _engine(result)
    assert types["Net sales"] == "Revenue"
    assert types["Interest income"] == "Unclassified"
    assert ("Left 'Interest income' unlabeled: the statement's arithmetic doesn't show whether it adds to or reduces "
            "income, and the filing's revenue is 'Net sales' (us-gaap:Revenues), which it is not part of") \
        in result.reader_notes


def test_a_lone_revenue_line_printed_as_a_total_reads_as_the_revenue_line() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import income_filing, income_rows
    rows = income_rows()
    rows[0] = rows[0].replace("<td>Net sales</td>", "<td>Total revenue, net</td>")
    result = _read(income_filing(rows))
    types = _engine(result)  # the engine's own Total check never stops a line the reader placed
    assert types["Total revenue, net"] == "Revenue"
    assert next(r for r in result.rows if r["line_item"] == "Total revenue, net")["Row Kind"] == "Detail"


def _fifty_three_week_filing() -> bytes:
    from tests.fixtures.ixbrl.build_ixbrl import fact, quarter_filing, row
    years = {"Y26": ("2024-12-29", "2026-01-03"), "Y24": ("2023-12-31", "2024-12-28"), "Y23": ("2023-01-01", "2023-12-30")}

    def line(label: str, concept: str, *values: str) -> str:
        return row(label, *(fact(concept, c, v) for c, v in zip(years, values, strict=True)))
    rows = [line("Net sales", "us-gaap:Revenues", "1,004", "1,145", "1,412"),
            line("Cost of sales", "us-gaap:CostOfRevenue", "500", "560", "700"),
            line("Net income", "us-gaap:NetIncomeLoss", "504", "585", "712")]
    return quarter_filing(rows, title="CONSOLIDATED STATEMENTS OF INCOME", periods=years)


def test_consecutive_52_53_week_years_are_named_by_their_end_month_not_as_a_gap() -> None:
    result = _read(_fifty_three_week_filing())
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.comparison_label == "Dec 2024"
    assert "Read the column for 2026-01-03 as Jan 2026" in result.reader_notes
    assert not any("FY2026" in note for note in result.reader_notes)


def test_years_that_name_cleanly_keep_their_fiscal_year_labels() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import income_filing
    result = _read(income_filing())
    assert result.comparison_label == "FY2024"


# Fix 5: a filing's income headline shows the filing's own printed totals, each from its fact.

def _report(data: bytes, **options: object) -> tuple[str, dict[str, object]]:
    import json
    import tempfile
    from pathlib import Path

    from variance_agent.cli import main
    with tempfile.TemporaryDirectory() as folder:
        source, out, audit = Path(folder, "hal-20250927.htm"), Path(folder, "r.md"), Path(folder, "a.json")
        source.write_bytes(data)
        extra = [str(v) for pair in options.items() for v in pair]
        code = main([str(source), "--assisted", "--compare-to", "prior-period", "--period", "FY2025",
                     "--dollar-threshold", "1", "--percent-threshold", "1", "-o", str(out), "--audit-json", str(audit),
                     *extra])
        assert code == 0
        return out.read_text(encoding="utf-8"), json.loads(audit.read_text(encoding="utf-8"))


def test_the_headline_is_the_filings_own_totals_not_revenue_less_expense() -> None:
    report, audit = _report(operations_and_comprehensive_loss_filing())
    summary = report.split("## Material Variances")[0]
    assert "- Collaboration revenue: $0.00 vs. $29,000,000.00 (-$29,000,000.00, -100.0%)" in summary
    assert "- Total operating expenses: $601,000,000.00 vs. $534,000,000.00 ($67,000,000.00, 12.5%)" in summary
    # Printed negative in both columns: the change says whether the loss grew (Decision 41, as R7 does for lines).
    assert "- Loss from operations: -$601,000,000.00 vs. -$505,000,000.00 (-$96,000,000.00, -19.0%, larger negative)" in summary
    assert "- Net loss: -$574,000,000.00 vs. -$471,000,000.00 (-$103,000,000.00, -21.9%, larger negative)" in summary
    assert "- Headline figures are the filing's own printed totals, each from its XBRL fact." in summary
    assert "Total Revenue" not in summary and "Total Expenses" not in summary and "net operating" not in summary
    assert audit["totals"] is None
    document = audit["source"]["document"]
    assert [item["line_item"] for item in document["headline"]["items"]] == [
        "Collaboration revenue", "Total operating expenses", "Loss from operations", "Net loss"]


def test_each_headline_figure_is_its_fact_and_its_change_matches_a_fraction_oracle() -> None:
    from fractions import Fraction
    _, audit = _report(operations_and_comprehensive_loss_filing())
    for item in audit["source"]["document"]["headline"]["items"]:
        actual, comparison = item["actual"], item["comparison"]
        assert actual["concept"] == comparison["concept"] == item["concept"] and not actual["dims"]
        change = Fraction(actual["displayed"]) - Fraction(comparison["displayed"])
        assert Fraction(item["change"]) == change
        if Fraction(comparison["displayed"]) != 0:
            exact = change / abs(Fraction(comparison["displayed"]))
            assert abs(Fraction(item["change_percent"]) - exact) < Fraction(1, 10**30)


def test_a_lone_revenue_line_and_net_income_head_a_simple_statement() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import income_filing
    report, audit = _report(income_filing())
    summary = report.split("## Material Variances")[0]
    assert "- Net sales: $4,100,000,000.00 vs. $3,900,000,000.00 ($200,000,000.00, 5.1%)" in summary
    assert "- Net income: $1,450,000,000.00 vs. $1,330,000,000.00 ($120,000,000.00, 9.0%)" in summary
    assert "Total Expenses" not in summary


def test_revenue_printed_as_several_lines_without_a_total_is_named_not_summed() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import fact, income_filing, income_rows, row
    rows = income_rows()
    rows[0:1] = [row("Products", fact("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "FY25", "3,000"),
                     fact("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "FY24", "2,900")),
                 row("Services", fact("us-gaap:Revenues", "FY25", "1,100"), fact("us-gaap:Revenues", "FY24", "1,000"))]
    report, audit = _report(income_filing(rows))
    summary = report.split("## Material Variances")[0]
    assert ("- The filing prints its revenue as 2 lines with no total of its own ('Products', 'Services'), so no "
            "revenue figure heads this report.") in summary
    assert not any(item["line_item"] in {"Products", "Services"} for item in audit["source"]["document"]["headline"]["items"])


def test_an_ltm_headline_is_built_from_each_printed_totals_facts() -> None:
    from fractions import Fraction

    from tests.fixtures.ixbrl.build_ixbrl import income_filing, quarter_filing
    from variance_agent.ltm import build_ltm
    result = build_ltm(quarter_filing(), "hal-20260328.htm", income_filing(), "hal-20250927.htm")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.filing_headline is not None and result.ltm is not None
    assert result.ltm["headline"] == result.filing_headline
    items = {str(item["line_item"]): item for item in result.filing_headline["items"]}  # type: ignore[union-attr]
    assert sorted(items) == ["Net income", "Net sales"]
    sales = items["Net sales"]
    assert (sales["ltm"], sales["comparison"], sales["change"]) == ("4300000000", "4100000000", "200000000")
    weights = [(component["document"], component["weight"], Fraction(str(component["used"])))
               for component in sales["components"]]  # type: ignore[union-attr]
    assert weights == [("hal-20250927.htm", 1, 4100 * 10**6), ("hal-20260328.htm", 1, 2200 * 10**6),
                       ("hal-20260328.htm", -1, 2000 * 10**6)]
    assert Fraction(str(sales["ltm"])) == sum(weight * used for _, weight, used in weights)
    from variance_agent.report import _filing_headline_lines
    lines = _filing_headline_lines(result.filing_headline, "USD", 2)
    assert "- Net sales: $4,300,000,000.00 vs. $4,100,000,000.00 ($200,000,000.00, 4.9%)" in lines
    assert lines[-1].startswith("- Headline figures are LTM of the filing's own printed totals")


def test_filing_and_ltm_audits_with_a_headline_validate_against_schema_1_9() -> None:
    import json
    import tempfile
    from pathlib import Path

    from jsonschema import Draft202012Validator

    from tests.fixtures.ixbrl.build_ixbrl import income_filing, quarter_filing
    from variance_agent.cli import main
    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "audit-1.9.schema.json").read_text())
    validator = Draft202012Validator(schema)
    with tempfile.TemporaryDirectory() as folder:
        annual, quarter = Path(folder, "hal-20250927.htm"), Path(folder, "hal-20260328.htm")
        annual.write_bytes(income_filing())
        quarter.write_bytes(quarter_filing())
        for name, extra in (("plain", []), ("ltm", ["--ltm-from", str(annual)])):
            audit = Path(folder, f"{name}.json")
            source = annual if name == "plain" else quarter
            assert main([str(source), "--assisted", "--period", "X", "--dollar-threshold", "1", "--percent-threshold", "1",
                         "--audit-json", str(audit), "-o", str(Path(folder, f"{name}.md")), *extra]) == 0
            record = json.loads(audit.read_text())
            assert record["source"]["document"]["headline"]["items"], name
            assert not list(validator.iter_errors(record)), name


def test_a_dollar_sign_in_its_own_cell_after_a_blank_spacer_is_not_label_text() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import fact, income_filing, income_rows
    rows = income_rows()
    rows[0] = ("<tr><td>Net sales</td><td> </td><td>$</td><td>&#160;</td><td>"
               + fact("us-gaap:Revenues", "FY25", "4,100") + "</td><td> </td><td>$</td><td> </td><td>"
               + fact("us-gaap:Revenues", "FY24", "3,900") + "</td></tr>")
    result = _read(income_filing(rows))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.rows[0]["line_item"] == "Net sales"


def test_the_report_itself_says_why_a_line_is_a_credit_among_costs() -> None:
    report, _ = _report(operations_and_comprehensive_loss_filing())
    section = report.split("## How the filing was read", 1)
    assert len(section) == 2, report
    assert ("- Read 'Interest income' as a credit among costs: the filing's revenue is 'Collaboration revenue' "
            "(us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax), and this line is not part of it") in section[1]


def test_an_ltm_report_keeps_the_reading_notes_beside_its_build() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import fact, income_filing, income_rows, quarter_filing, quarter_rows, row
    annual = income_rows()
    annual[4:6] = [row("Other income, net", fact("us-gaap:OtherNonoperatingIncomeExpense", "FY25", "50"),
                       fact("us-gaap:OtherNonoperatingIncomeExpense", "FY24", "40")),
                   row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", "1,550"), fact("us-gaap:NetIncomeLoss", "FY24", "1,410"))]
    quarter = quarter_rows()
    quarter[4] = row("Other income, net", *(fact("us-gaap:OtherNonoperatingIncomeExpense", c, v) for c, v in
                                            zip(("Q26", "Q25", "YTD26", "YTD25"), ("13", "10", "25", "20"), strict=True)))
    quarter[5] = row("Net income", *(fact("us-gaap:NetIncomeLoss", c, v) for c, v in
                                     zip(("Q26", "Q25", "YTD26", "YTD25"), ("463", "395", "865", "770"), strict=True)))
    from variance_agent.ltm import build_ltm
    result = build_ltm(quarter_filing(quarter), "hal-20260328.htm", income_filing(annual), "hal-20250927.htm")
    assert not result.has_fatal_errors, result.fatal_error_message
    text = "\n".join(result.report_appendix)
    assert text.index("## How the filing was read") < text.index("## LTM build")
    assert "- Read 'Other income, net' as a credit among costs" in text


def test_an_investment_companys_statement_refuses_plainly_rather_than_reading_subtotals_as_lines() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import investment_company_filing
    # Net expenses and net investment income subtract a subtotal, which the shaper can't place. Before Decision 39
    # the bottom line was demoted to a detail line and every subtotal was analysed as a line; now it must add up.
    result = _read(investment_company_filing())
    assert result.has_fatal_errors
    assert result.fatal_error_message == (
        "I couldn't tell which lines 'Net increase (decrease) in net assets resulting from operations' adds up in the "
        "Consolidated Statements of Operations, so I can't check it and stopped instead of guessing. Upload a CSV or "
        "Excel copy of the statement, or the filing's PDF.")


def test_a_total_without_a_fact_in_one_column_is_left_out_of_the_headline_by_name() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import fact, income_filing, income_rows, row
    rows = income_rows()
    rows[0] = row("Net sales", "$" + fact("us-gaap:Revenues", "FY25", "4,100"), "—")
    rows[1] = row("Cost of sales", fact("us-gaap:CostOfRevenue", "FY25", "2,300"), "—")
    rows[2] = row("Gross margin", fact("us-gaap:GrossProfit", "FY25", "1,800"), "—")
    rows[3] = row("Research and development", fact("us-gaap:ResearchAndDevelopmentExpense", "FY25", "300"),
                  fact("us-gaap:ResearchAndDevelopmentExpense", "FY24", "1,370"))
    # The year before revenue: gross margin a dash, so net income is -(1,370 + 40) = (1,410).
    rows[5] = row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", "1,450"),
                  "(" + fact("us-gaap:NetIncomeLoss", "FY24", "1,410", sign="-") + ")")
    report, audit = _report(income_filing(rows))
    notes = audit["source"]["document"]["headline"]["notes"]
    assert "'Net sales' prints no tagged figure for FY2024, so it isn't in the headline." in notes
    assert "- 'Net sales' prints no tagged figure for FY2024, so it isn't in the headline." in report


# Fix 5 in the chat: a filing session never shows computed revenue, expense or net operating totals.

def _filing_session() -> object:
    from variance_agent.chat.handlers import handle_message, handle_upload
    from variance_agent.chat.session import Session
    session = Session()
    reply = handle_upload(session, operations_and_comprehensive_loss_filing(), "hal-20250927.htm")
    for answer in ("Looks right", "FY2025", "$1 or 1%", "USD"):
        if reply.text.startswith(("**Analysis Complete**", "#")):
            break
        reply = handle_message(session, answer)
    return session, reply


def test_the_chat_summary_of_a_filing_shows_its_own_printed_totals() -> None:
    session, reply = _filing_session()
    assert "**Net loss:** -$574,000,000.00 vs. -$471,000,000.00 (-$103,000,000.00, -21.9%, larger negative)" in reply.text
    assert "Total Revenue" not in reply.text and "Net Operating Impact" not in reply.text
    labels = [str(figure["label"]) for figure in reply.view["figures"]]  # type: ignore[index]
    assert labels == ["Collaboration revenue", "Total operating expenses", "Loss from operations", "Net loss"]


def test_questions_about_computed_totals_answer_with_the_filings_own() -> None:
    from variance_agent.chat.handlers import handle_message
    session, _ = _filing_session()
    for question in ("summary", "totals", "waterfall", "tldr", "memo", "profitability", "sensitivity", "run rate",
                     "compare actual vs budget"):
        reply = handle_message(session, question)
        assert "Net Operating Impact" not in reply.text and "Total Revenue" not in reply.text, question
        assert "**Net loss:**" in reply.text, question
    greeting = handle_message(session, "hello").text
    assert "net operating impact" not in greeting.lower()


def test_the_workbook_refuses_for_a_filings_income_statement() -> None:
    import tempfile
    from pathlib import Path

    import pytest

    from tests.fixtures.ixbrl.build_ixbrl import income_filing
    from variance_agent.cli import main
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder, "hal-20250927.htm")
        source.write_bytes(income_filing())
        with pytest.raises(SystemExit):
            main([str(source), "--assisted", "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "1",
                  "--xlsx", str(Path(folder, "out.xlsx"))])
        assert not Path(folder, "out.xlsx").exists()


def test_the_chat_offers_no_workbook_for_a_filing() -> None:
    from variance_agent.chat.handlers import handle_message
    session, reply = _filing_session()
    assert "Export Excel" not in (reply.chips or [])
    assert handle_message(session, "export excel").text == (
        "A workbook isn't available for this comparison yet. The report and the audit file are; type "
        "`export report` or `export audit`.")


# Decision 40: a filing report states the unit the filing prints in, and how label amounts are quoted.

UNIT_MILLIONS = ("The filing prints these figures in millions; this report shows them in full, and amounts inside line "
                 "labels are quoted as the filing prints them.")


def test_an_income_report_states_the_filings_unit() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import income_filing
    report, audit = _report(income_filing())
    summary = report.split("## Material Variances")[0]
    assert f"- Units: {UNIT_MILLIONS}" in summary
    assert audit["source"]["document"]["headline"]["unit"] == UNIT_MILLIONS


def test_a_balance_sheet_report_states_the_unit_its_labels_are_quoted_in() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import balance_rows, position_filing
    rows = balance_rows()
    # A label quoting an allowance as the filing prints it, in thousands (Draw C's fresh-eyes finding).
    rows = [r.replace("<td>Accounts receivable, net</td>",
                      "<td>Accounts receivable, net of allowance of $750 and $740</td>") for r in rows]
    data = position_filing("CONSOLIDATED BALANCE SHEETS", [r.replace('scale="6"', 'scale="3"').replace('decimals="-6"', 'decimals="-3"')
                                                             for r in rows])
    report, audit = _report(data, **{"--sheet": "Consolidated Balance Sheets"})
    unit = UNIT_MILLIONS.replace("millions", "thousands")
    assert "Accounts receivable, net of allowance of $750 and $740" in report
    assert f"- Units: {unit}" in report.split("## Lines")[0]
    assert f"Units: {unit}" in audit["source"]["document"]["reader_notes"]


def test_an_ltm_report_states_each_filings_unit() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import income_filing, quarter_filing
    from variance_agent.ltm import build_ltm
    result = build_ltm(quarter_filing(), "hal-20260328.htm", income_filing(), "hal-20250927.htm")
    assert result.filing_headline is not None and result.filing_headline["unit"] == UNIT_MILLIONS.replace(
        "The filing prints", "Both filings print")


def test_the_chat_summary_of_a_filing_states_its_unit() -> None:
    _, reply = _filing_session()
    assert f"Units: {UNIT_MILLIONS}" in reply.text


# Decision 41: label text, section names, credit notes and the headline cue.

def _balance_sheet_with(label_row: str) -> bytes:
    from tests.fixtures.ixbrl.build_ixbrl import POSITION_RESOURCES, balance_rows, document, fact, statement
    rows = [label_row if r.startswith("<tr><td>Common stock, $") else r for r in balance_rows()]
    hidden = (fact("us-gaap:CommonStockParOrStatedValuePerShare", "I25", "0.01", unit="usdPerShare", scale="0",
                   decimals="2", fact_id="p1")
              + fact("us-gaap:CommonStockParOrStatedValuePerShare", "I24", "0.01", unit="usdPerShare", scale="0",
                     decimals="2", fact_id="p2")
              + fact("us-gaap:CommonStockSharesAuthorized", "I25", "500", unit="shares", fact_id="a1")
              + fact("us-gaap:CommonStockSharesAuthorized", "I24", "500", unit="shares", fact_id="a2"))
    body = statement("CONSOLIDATED BALANCE SHEETS", rows)
    return document(body, hidden).replace("</ix:resources>", POSITION_RESOURCES + "</ix:resources>").encode("utf-8")


def test_a_figure_inside_nested_hidden_spans_is_printed_once() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import fact, row
    # Draw D: one filing agent wraps each label figure in two hidden-fact spans, one per period.
    label = ('Common stock, $<span style="-sec-ix-hidden:p1"><span style="-sec-ix-hidden:p2">0.01</span></span> par '
             'value; <span style="-sec-ix-hidden:a1"><span style="-sec-ix-hidden:a2">500</span></span> shares authorized')
    data = _balance_sheet_with(row(label, fact("us-gaap:CommonStockValue", "I25", "1"),
                                   fact("us-gaap:CommonStockValue", "I24", "1")))
    result = _read(data, sheet="Consolidated Balance Sheets")
    assert not result.has_fatal_errors, result.fatal_error_message
    names = [str(r["line_item"]) for r in result.rows]
    assert "Common stock, $0.01 par value; 500 shares authorized" in names, names


def test_a_line_after_a_cash_flow_sections_net_cash_is_not_named_by_that_section() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import cash_flow_rows, fact, position_filing, row
    rows = cash_flow_rows() + [row("Cash, cash equivalents and restricted cash, end of year",
                                   fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I25", "2,600"),
                                   fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I24", "2,000"))]
    result = _read(position_filing("CONSOLIDATED STATEMENTS OF CASH FLOWS", rows), sheet="Consolidated Statements of Cash Flows")
    assert not result.has_fatal_errors, result.fatal_error_message
    names = [str(r["line_item"]) for r in result.rows]
    assert not any(name.startswith("Financing activities:") for name in names), names
    assert "Cash, cash equivalents and restricted cash, end of year" in names
    assert any("'Supplemental disclosure: Cash, cash equivalents and restricted cash, end of year'" in note
               for note in result.reader_notes), result.reader_notes


def test_a_line_printed_as_dashes_is_never_called_a_credit_among_costs() -> None:
    from tests.fixtures.ixbrl.build_ixbrl import fact, quarter_filing, row
    # Draw D: dashes in both compared years, a credit only in the third year the statement prints.
    years = {"Y25": ("2025-01-01", "2025-12-31"), "Y24": ("2024-01-01", "2024-12-31"), "Y23": ("2023-01-01", "2023-12-31")}

    def line(label: str, concept: str, *cells: str) -> str:
        printed = []
        for context, text in zip(years, cells, strict=True):
            if text == "—":
                printed.append(fact(concept, context, "—", fmt="ixt:fixed-zero"))
            elif text.startswith("("):
                printed.append("(" + fact(concept, context, text.strip("()"), sign="-") + ")")
            else:
                printed.append(fact(concept, context, text))
        return row(label, *printed)
    rows = [line("Net sales", "us-gaap:Revenues", "1,004", "1,145", "1,412"),
            line("Cost of sales", "us-gaap:CostOfRevenue", "500", "560", "700"),
            line("Restructuring", "us-gaap:RestructuringCharges", "—", "—", "(14)"),
            line("Net income", "us-gaap:NetIncomeLoss", "504", "585", "726")]
    result = _read(quarter_filing(rows, title="CONSOLIDATED STATEMENTS OF INCOME", periods=years))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert not any("'Restructuring' as a credit among costs" in note for note in result.reader_notes), result.reader_notes
