"""Balance sheets and cash flow statements from Inline XBRL filings (docs/analysts/PLAN.md R7-R9).

Every filing here is built by tests/fixtures/ixbrl/build_ixbrl.py and is fictional.
"""

from __future__ import annotations

from decimal import Decimal

from tests.fixtures.ixbrl.build_ixbrl import (
    all_statements_filing,
    balance_rows,
    cash_flow_rows,
    position_filing,
    row,
)
from variance_agent.ixbrl import Statement, read_statements

M = Decimal(1_000_000)


def _statement(data: bytes, kind: str) -> Statement:
    found = [s for s in read_statements(data, "hal-20250927.htm") if s.kind == kind]
    assert len(found) == 1, [s.name for s in found]
    return found[0]


def _values(statement: Statement, label: str) -> list[Decimal | None]:
    line = next(line for line in statement.lines if line.label == label)
    return [None if key is None else key.displayed for key in line.keys]


# R8 and the label cell -------------------------------------------------------------------------


def test_figures_tagged_inside_a_label_are_label_text_not_the_line() -> None:
    sheet = _statement(position_filing("CONSOLIDATED BALANCE SHEETS", balance_rows()), "balance_sheet")
    label = "Common stock, $0.01 par value; 500 shares authorized; 120 and 118 shares issued"
    line = next(line for line in sheet.lines if line.label == label)
    assert (line.concept, line.measure, _values(sheet, label)) == ("us-gaap:CommonStockValue", "Currency", [1 * M, 1 * M])
    assert not sheet.left_out


def test_a_cash_flow_statement_is_one_statement_over_its_duration_columns() -> None:
    flows = _statement(all_statements_filing(), "cash_flow")
    assert (flows.name, flows.labels) == ("Consolidated Statements of Cash Flows", ["FY2025", "FY2024"])


def test_beginning_and_ending_cash_take_the_duration_columns_by_date() -> None:
    flows = _statement(all_statements_filing(), "cash_flow")
    begin = next(line for line in flows.lines if line.label.endswith("beginning of year"))
    end = next(line for line in flows.lines if line.label.endswith("end of year"))
    assert [key.period for key in begin.keys if key] == [("instant", "2024-09-28"), ("instant", "2023-09-30")]
    assert [key.period for key in end.keys if key] == [("instant", "2025-09-27"), ("instant", "2024-09-28")]
    assert [key.displayed for key in begin.keys if key] == [2000 * M, 1350 * M]
    assert [key.displayed for key in end.keys if key] == [2600 * M, 2000 * M]


def test_a_cash_line_that_would_be_both_a_beginning_and_an_ending_balance_refuses() -> None:
    rows = cash_flow_rows()
    # The day before FY2025 starts is FY2024's end: one fact at each places one way, the other the other.
    rows.insert(-2, row("Cash, mixed", "".join(r for r in []) or
                        '<ix:nonFraction name="us-gaap:Cash" contextRef="I25" unitRef="usd" decimals="-6" scale="6"'
                        ' format="ixt:num-dot-decimal">5</ix:nonFraction>',
                        '<ix:nonFraction name="us-gaap:Cash" contextRef="I23" unitRef="usd" decimals="-6" scale="6"'
                        ' format="ixt:num-dot-decimal">5</ix:nonFraction>'))
    flows = _statement(position_filing("CONSOLIDATED STATEMENTS OF CASH FLOWS", rows), "cash_flow")
    assert flows.problem == ("I could not read every figure of 'Cash, mixed' in the Consolidated Statements of Cash Flows: "
                             "its balances fall at the end of one column and the start of another. Upload the filing's "
                             "PDF, or a CSV or Excel copy of the statement.")


def test_a_balance_sheet_keeps_its_instant_columns() -> None:
    sheet = _statement(all_statements_filing(), "balance_sheet")
    assert (sheet.name, sheet.labels) == ("Consolidated Balance Sheets", ["Sep 2025", "Sep 2024"])


# Statement assembly shapes from Draw A, rebuilt fictional -------------------------------------------

from tests.fixtures.ixbrl.build_ixbrl import POSITION_RESOURCES, document, fact, statement  # noqa: E402


def _filing(body: str, resources: str = "") -> bytes:
    return document(body).replace("</ix:resources>", POSITION_RESOURCES + resources + "</ix:resources>").encode("utf-8")


def test_a_balance_sheet_printed_as_two_titled_tables_reads_as_one() -> None:
    rows = balance_rows()
    split = next(i for i, r in enumerate(rows) if "LIABILITIES AND" in r)
    body = (statement("CONSOLIDATED BALANCE SHEETS — ASSETS", rows[:split])
            + statement("CONSOLIDATED BALANCE SHEETS — LIABILITIES AND EQUITY", rows[split:]))
    sheet = _statement(_filing(body), "balance_sheet")
    assert [line.label for line in sheet.lines][-1] == "Total liabilities and stockholders' equity"
    assert len(sheet.lines) == 15


def test_a_cash_flow_title_without_of_is_a_cash_flow_statement() -> None:
    flows = _statement(_filing(statement("Condensed Consolidated Statements Cash Flows", cash_flow_rows())), "cash_flow")
    assert flows.name == "Condensed Consolidated Statements Cash Flows"


def test_a_cash_table_of_instants_titled_like_the_statement_is_not_the_statement() -> None:
    reconciliation = [row("Cash and cash equivalents", fact("us-gaap:CashAndCashEquivalentsAtCarryingValue", "I25", "2,500"),
                          fact("us-gaap:CashAndCashEquivalentsAtCarryingValue", "I24", "1,900")),
                      row("Restricted cash", fact("us-gaap:RestrictedCash", "I25", "100"), fact("us-gaap:RestrictedCash", "I24", "100")),
                      row("Total cash, cash equivalents and restricted cash shown in the statements of cash flows",
                          fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I25", "2,600"),
                          fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I24", "2,000"))]
    body = (statement("Cash reported in the statements of cash flows", reconciliation)
            + statement("CONSOLIDATED STATEMENTS OF CASH FLOWS", cash_flow_rows()))
    flows = _statement(_filing(body), "cash_flow")
    assert flows.lines[0].label == "Net income"


QUARTER_RESOURCES = "".join(
    f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999'
    f'</xbrli:identifier></xbrli:entity><xbrli:period>{period}</xbrli:period></xbrli:context>'
    for cid, period in [
        ("Q3_25", "<xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate>"),
        ("Q3_24", "<xbrli:startDate>2024-07-01</xbrli:startDate><xbrli:endDate>2024-09-30</xbrli:endDate>"),
        ("YTD_25", "<xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate>"),
        ("YTD_24", "<xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-09-30</xbrli:endDate>"),
        ("E_0630_25", "<xbrli:instant>2025-06-30</xbrli:instant>"), ("E_0630_24", "<xbrli:instant>2024-06-30</xbrli:instant>"),
        ("E_1231_24", "<xbrli:instant>2024-12-31</xbrli:instant>"), ("E_1231_23", "<xbrli:instant>2023-12-31</xbrli:instant>"),
        ("E_0930_25", "<xbrli:instant>2025-09-30</xbrli:instant>"), ("E_0930_24", "<xbrli:instant>2024-09-30</xbrli:instant>"),
    ])


def test_three_and_nine_month_columns_in_one_table_each_take_their_own_beginning_cash() -> None:
    cash = "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"

    def four(label: str, concept: str, values: tuple[str, str, str, str], contexts: tuple[str, str, str, str]) -> str:
        return row(label, *(fact(concept, c, v) for v, c in zip(values, contexts, strict=True)))

    durations = ("Q3_25", "Q3_24", "YTD_25", "YTD_24")
    rows = [four("Net income", "us-gaap:NetIncomeLoss", ("100", "90", "300", "270"), durations),
            four("Net cash provided by operating activities", "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                 ("100", "90", "300", "270"), durations),
            four("Net increase in cash",
                 "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
                 ("100", "90", "300", "270"), durations),
            four("Cash at beginning of period", cash, ("1,200", "1,000", "1,000", "820"),
                 ("E_0630_25", "E_0630_24", "E_1231_24", "E_1231_23")),
            four("Cash at end of period", cash, ("1,300", "1,090", "1,300", "1,090"),
                 ("E_0930_25", "E_0930_24", "E_0930_25", "E_0930_24"))]
    found = [s for s in read_statements(_filing(statement("CONDENSED CONSOLIDATED STATEMENTS OF CASH FLOWS", rows),
                                                 QUARTER_RESOURCES), "hal.htm") if s.kind == "cash_flow"]
    assert [(s.name, s.problem) for s in found] == [
        ("Condensed Consolidated Statements of Cash Flows, 3 Months Ended", ""),
        ("Condensed Consolidated Statements of Cash Flows, 9 Months Ended", "")]
    quarter, year_to_date = found
    assert _values(quarter, "Cash at beginning of period") == [1200 * M, 1000 * M]
    assert _values(year_to_date, "Cash at beginning of period") == [1000 * M, 820 * M]
    assert _values(year_to_date, "Cash at end of period") == [1300 * M, 1090 * M]


def test_a_note_table_titled_near_a_mention_of_the_statement_is_not_the_statement() -> None:
    segment = [row("Segment revenues", fact("us-gaap:Revenues", "FY25", "4,100"), fact("us-gaap:Revenues", "FY24", "3,900")),
               row("Segment costs", fact("us-gaap:CostOfRevenue", "FY25", "2,300"), fact("us-gaap:CostOfRevenue", "FY24", "2,250")),
               row("Segment margin", fact("us-gaap:GrossProfit", "FY25", "1,800"), fact("us-gaap:GrossProfit", "FY24", "1,650"))]
    body = (statement("Depreciation by segment is shown in the consolidated statements of cash flows", segment)
            + statement("CONSOLIDATED STATEMENTS OF CASH FLOWS", cash_flow_rows()))
    flows = _statement(_filing(body), "cash_flow")
    assert flows.lines[0].label == "Net income"


def test_a_singular_cash_flow_title_is_a_cash_flow_statement() -> None:
    flows = _statement(_filing(statement("CONSOLIDATED STATEMENTS OF CASH FLOW", cash_flow_rows())), "cash_flow")
    assert flows.name == "Consolidated Statements of Cash Flow"


# R7: comparing a balance sheet or cash flow statement --------------------------------------------

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from variance_agent import cli  # noqa: E402
from variance_agent.analysis import analyze_rows  # noqa: E402
from variance_agent.comparison import display_outcome  # noqa: E402
from variance_agent.intake import IntakeResult, read_input_assisted  # noqa: E402
from variance_agent.models import AnalysisConfig, ComparisonBasis, LineType, Status  # noqa: E402
from variance_agent.report import render_markdown  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BALANCE = "Consolidated Balance Sheets"
FLOWS = "Consolidated Statements of Cash Flows"
IDENTITY = ("Checked every subtotal and the balance sheet identity: Total assets equals Total liabilities and stockholders' "
            "equity in Sep 2025 and Sep 2024, within the rounding each figure's decimals state")
CHANGE_NOTE = ("Compared each line as an Increase or Decrease of its printed figure: a figure printed in parentheses is "
               "negative, so a larger outflow or deduction shows as a Decrease")


def _read(sheet: str) -> IntakeResult:
    return read_input_assisted(all_statements_filing(), ".htm", filename="hal-20250927.htm", sheet=sheet,
                               compare_to=ComparisonBasis.PRIOR_PERIOD)


def _analyse(result: IntakeResult, period: str = "Sep 2025") -> tuple[object, ...]:
    config = AnalysisConfig(period, Decimal("1"), Decimal("0.01"), comparison_basis=ComparisonBasis.PRIOR_PERIOD,
                            comparison_label=result.comparison_label)
    analysis = analyze_rows(result.rows, config)
    return analysis, config


def test_a_balance_sheet_reads_every_line_and_subtotal_at_its_printed_value() -> None:
    result = _read(BALANCE)
    assert not result.has_fatal_errors, result.fatal_error_message
    assert [(r["line_item"], r["Row Kind"]) for r in result.rows][:5] == [
        ("Cash and cash equivalents", "Detail"), ("Accounts receivable, net", "Detail"), ("Total current assets", "Total"),
        ("Property and equipment, net", "Detail"), ("Total assets", "Total")]
    treasury = next(r for r in result.rows if r["line_item"] == "Treasury stock, at cost")
    assert (treasury["actual"], treasury["budget"], treasury["Statement Kind"]) == (-100 * M, -100 * M, "balance_sheet")
    assert IDENTITY in result.visible_transformations
    assert CHANGE_NOTE in result.visible_transformations
    assert result.detected_totals == []
    record = result.source_document()
    assert record is not None
    identity = record["identities"][0]  # type: ignore[index]
    assert (record["statement_kind"], identity["identity"], identity["rule"], identity["left"], identity["right"],
            identity["columns"], identity["holds"]) == (
        "balance_sheet", "balance_sheet", "total assets = total liabilities and equity", "Total assets",
        "Total liabilities and stockholders' equity", ["Sep 2025", "Sep 2024"], True)
    assert {"subtotal": "Total liabilities and stockholders' equity", "terms": [
        {"line_item": "Total liabilities", "weight": 1}, {"line_item": "Total stockholders' equity", "weight": 1}]} in (
        identity["footing"])


def test_a_cash_flow_statement_ends_at_ending_cash_and_lists_the_supplemental_lines() -> None:
    result = _read(FLOWS)
    assert not result.has_fatal_errors, result.fatal_error_message
    assert [r["line_item"] for r in result.rows][-2:] == [
        "Cash, cash equivalents and restricted cash, beginning of year", "Cash, cash equivalents and restricted cash, end of year"]
    assert ("Left out 1 line after 'Cash, cash equivalents and restricted cash, end of year' (supplemental disclosures): "
            "'Cash paid for interest'") in result.visible_transformations
    record = result.source_document()
    assert record is not None
    assert [line["line_item"] for line in record["lines"] if line["left_out"]] == ["Cash paid for interest"]  # type: ignore[index, union-attr]
    assert any("'Cash paid for interest'" in check for check in result.statement_checks)


def test_statement_lines_are_never_revenue_or_expense_and_carry_no_judgement() -> None:
    analysis, config = _analyse(_read(BALANCE))
    rows = analysis.rows  # type: ignore[attr-defined]
    assert {(row.line_type, row.classification_source) for row in rows} == {(LineType.UNCLASSIFIED, "statement")}
    assert {row.status for row in rows} == {Status.NEUTRAL}
    assert analysis.revenue.actual == 0 and analysis.expenses.actual == 0  # type: ignore[attr-defined]
    assert not any("Unclassified" in warning for warning in analysis.warnings)  # type: ignore[attr-defined]
    labels = {row.line_item: display_outcome(row, ComparisonBasis.PRIOR_PERIOD) for row in rows}
    assert (labels["Cash and cash equivalents"], labels["Long-term debt"], labels["Treasury stock, at cost"]) == (
        "Increase", "No change", "No change")


def test_a_cash_outflow_that_grows_is_a_decrease_of_its_printed_figure() -> None:
    analysis, _ = _analyse(_read(FLOWS), "FY2025")
    capex = next(row for row in analysis.rows if row.line_item == "Purchases of property and equipment")  # type: ignore[attr-defined]
    assert (capex.actual, capex.budget, capex.variance_dollars) == (-600 * M, -500 * M, -100 * M)
    assert display_outcome(capex, ComparisonBasis.PRIOR_PERIOD) == "Decrease, larger negative"


@pytest.mark.parametrize(("better", "label"), [("Higher", "Decrease, larger negative (U)"),
                                               ("Lower", "Decrease, larger negative (F)")])
def test_a_declared_better_direction_gives_a_statement_line_f_or_u(better: str, label: str) -> None:
    result = _read(FLOWS)
    for row_dict in result.rows:
        if row_dict["line_item"] == "Purchases of property and equipment":
            row_dict["Better"] = better
    analysis, _ = _analyse(result, "FY2025")
    capex = next(row for row in analysis.rows if row.line_item == "Purchases of property and equipment")  # type: ignore[attr-defined]
    assert display_outcome(capex, ComparisonBasis.PRIOR_PERIOD) == label


def test_the_report_shows_the_identity_and_each_change_without_totals_or_advice() -> None:
    result = _read(BALANCE)
    analysis, _ = _analyse(result)
    report = render_markdown(analysis, statement_checks=result.statement_checks)  # type: ignore[arg-type]
    assert report.startswith("# Statement Comparison: Sep 2025\n")
    assert IDENTITY in report
    assert "| Cash and cash equivalents | $2,000,000,000.00 | $2,600,000,000.00 | $600,000,000.00 | 30.0% | Increase | Yes |" in report
    for absent in ("Total Revenue", "Total Expenses", "Net operating", "Mitigation", "Optimization", "Unclassified"):
        assert absent not in report


def _cli(tmp_path: Path, sheet: str, period: str, *extra: str) -> list[str]:
    path = tmp_path / "hal-20250927.htm"
    path.write_bytes(all_statements_filing())
    return [str(path), "--assisted", "--sheet", sheet, "--compare-to", "prior-period", "--period", period,
            "--dollar-threshold", "1", "--percent-threshold", "1", *extra]


def test_the_cli_records_a_statement_comparison_in_audit_19(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    assert cli.main(_cli(tmp_path, BALANCE, "Sep 2025", "--audit-json", str(audit), "-o", str(tmp_path / "r.md"))) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads((ROOT / "schemas/audit-1.9.schema.json").read_text(encoding="utf-8"))).validate(record)
    assert (record["schema_version"], record["totals"]) == ("1.9", None)
    assert record["source"]["document"]["statement_kind"] == "balance_sheet"
    assert {row["classification_source"] for row in record["material_variances"]} == {"statement"}
    assert record["source"]["document"]["identities"][0]["left"] == "Total assets"
    assert "# Statement Comparison" in (tmp_path / "r.md").read_text(encoding="utf-8")


def test_the_cli_refuses_a_workbook_for_a_statement_comparison(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main(_cli(tmp_path, FLOWS, "FY2025", "--xlsx", str(tmp_path / "out.xlsx")))
    assert ("--xlsx isn't available for a balance sheet or cash flow comparison yet. Leave out --xlsx, or choose the "
            "filing's income statement.") in capsys.readouterr().err.replace("\n", " ")
    assert not (tmp_path / "out.xlsx").exists()


def test_a_balance_sheet_that_does_not_balance_refuses_on_the_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tag = (b'name="us-gaap:LiabilitiesAndStockholdersEquity" contextRef="I25" unitRef="usd" decimals="-6" scale="6" '
           b'format="ixt:num-dot-decimal">')
    data = all_statements_filing().replace(tag + b"6,500", tag + b"6,503")
    assert data != all_statements_filing()
    path = tmp_path / "hal-20250927.htm"
    path.write_bytes(data)
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--sheet", BALANCE, "--compare-to", "prior-period", "--period", "Sep 2025",
                  "--dollar-threshold", "1", "--percent-threshold", "1"])
    assert "so I can't check it and stopped instead of guessing" in capsys.readouterr().err.replace("\n", " ")


def test_the_chat_compares_a_balance_sheet_without_asking_for_labels() -> None:
    from variance_agent.chat.handlers import handle_message, handle_upload
    from variance_agent.chat.session import Session

    session = Session()
    handle_upload(session, all_statements_filing(), "hal-20250927.htm")
    for message in ["statement Consolidated Balance Sheets", "Looks right", "Sep 2025", "$10,000 or 5%"]:
        handle_message(session, message)
    reply = handle_message(session, "USD")
    assert reply.text.startswith("# Statement Comparison: Sep 2025")
    assert IDENTITY in reply.text
    assert "labeled revenue or expense" not in reply.text and reply.chips == ["Export report", "Export audit"]
    assert handle_message(session, "waterfall").text.startswith("# Statement Comparison")
    assert handle_message(session, "export excel").text == (
        "A workbook isn't available for this comparison yet. The report and the audit file are; type "
        "`export report` or `export audit`.")


def test_an_unlabeled_subtotal_is_named_by_its_concept_not_as_the_section_s_total() -> None:
    rows = balance_rows()
    at = next(i for i, r in enumerate(rows) if "Treasury stock" in r)
    rows[at:at] = [row("", fact("us-gaap:StockholdersEquityBeforeTreasuryStock", "I25", "4,200"),
                       fact("us-gaap:StockholdersEquityBeforeTreasuryStock", "I24", "3,250"))]
    sheet = _statement(position_filing("CONSOLIDATED BALANCE SHEETS", rows), "balance_sheet")
    labels = [line.label for line in sheet.lines]
    assert "Total, printed without a label (us-gaap:StockholdersEquityBeforeTreasuryStock)" in labels
    assert labels.count("Total stockholders' equity") == 1



@pytest.mark.parametrize(("comparison", "actual", "label"), [
    ("-500", "-600", "Decrease, larger negative"), ("-600", "-500", "Increase, smaller negative"),
    ("0", "-5", "Decrease, larger negative"), ("10", "-20", "Decrease"), ("-5", "5", "Increase"), ("-5", "-5", "No change"),
])
def test_a_negative_printed_figure_says_whether_it_grew_or_shrank(comparison: str, actual: str, label: str) -> None:
    config = AnalysisConfig("FY", Decimal("1"), Decimal("0.01"), comparison_basis=ComparisonBasis.PRIOR_PERIOD)
    analysis = analyze_rows([{"Line Item": "Line", "Budget": comparison, "Actual": actual,
                              "Statement Kind": "cash_flow"}], config)
    assert display_outcome(analysis.rows[0], ComparisonBasis.PRIOR_PERIOD) == label
