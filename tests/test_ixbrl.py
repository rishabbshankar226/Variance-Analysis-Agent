"""The Inline XBRL filing reader (PLAN.md R1, R5, R6). Every filing here is fictional (HALVORSEN.FAKE)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.fixtures.ixbrl.build_ixbrl import document, fact, income_filing, income_rows, row, statement
from variance_agent import cli
from variance_agent.chat.handlers import handle_upload
from variance_agent.chat.session import Session
from variance_agent.intake import IntakeResult, read_input_assisted
from variance_agent.ixbrl import _transform, read_statements
from variance_agent.models import ComparisonBasis

ROOT = Path(__file__).resolve().parents[1]
M = Decimal(1_000_000)


@pytest.mark.parametrize(("fmt", "text", "expected"), [
    ("ixt:num-dot-decimal", "1,234.56", Decimal("1234.56")),
    ("ixt:numdotdecimal", "1 234", Decimal("1234")),
    ("ixt:num-comma-decimal", "1.234,56", Decimal("1234.56")),
    ("ixt:numcommadecimal", "12,5", Decimal("12.5")),
    ("ixt:fixed-zero", "—", Decimal(0)),
    ("ixt:zerodash", "-", Decimal(0)),
    ("ixt-sec:numwordsen", "None", Decimal(0)),
    ("ixt-sec:numwordsen", "two", Decimal(2)),
    ("", "1234.5", Decimal("1234.5")),
])
def test_each_format_transform(fmt: str, text: str, expected: Decimal) -> None:
    assert _transform(fmt, text) == expected


@pytest.mark.parametrize(("fmt", "text"), [("ixt:num-dot-decimal", "1.234,5"), ("ixt:date-monthname-day-year-en", "May 1"),
                                           ("ixt-sec:numwordsen", "a great many"), ("", "1,234")])
def test_a_figure_its_format_does_not_describe_is_refused(fmt: str, text: str) -> None:
    with pytest.raises(ValueError):
        _transform(fmt, text)


def _read(data: bytes, **options: object) -> IntakeResult:
    return read_input_assisted(data, ".htm", filename="hal-20250927.htm", **options)  # type: ignore[arg-type]


def _amounts(result: IntakeResult) -> list[tuple[str, str, Decimal, Decimal]]:
    assert not result.has_fatal_errors, result.fatal_error_message
    return [(str(r["line_item"]), str(r["type"]), Decimal(str(r["budget"])), Decimal(str(r["actual"]))) for r in result.rows]


def test_an_income_statement_reads_at_full_scale_without_scaling_the_caption_again() -> None:
    result = _read(income_filing())
    assert result.comparison_basis is ComparisonBasis.PRIOR_PERIOD
    assert result.comparison_label == "FY2024"
    assert _amounts(result) == [
        ("Net sales", "Revenue", 3900 * M, 4100 * M),
        ("Cost of sales", "Expense", 2250 * M, 2300 * M),
        ("Research and development", "Expense", 280 * M, 300 * M),
        ("Interest expense", "Expense", 40 * M, 50 * M),
    ]
    assert result.detected_unit_multiplier == Decimal(1)
    notes = result.visible_transformations
    assert notes[0] == "Read 'Consolidated Statements of Operations' from the Inline XBRL filing"
    assert "Left out 'Basic (in dollars per share)' (per-share and share counts are not money totals)" in notes
    assert result.source_kind == "ixbrl"


def test_each_line_carries_its_xbrl_key_with_stored_and_printed_values() -> None:
    result = _read(income_filing())
    document_record = result.source_document()
    assert document_record is not None and document_record["kind"] == "ixbrl"
    lines = {line["line_item"]: line for line in document_record["lines"]}  # type: ignore[union-attr, index]
    interest = lines["Interest expense"]["columns"][0]
    assert interest == {"label": "FY2025", "concept": "us-gaap:InterestExpense", "context": "FY25",
                        "period": ["duration", "2024-09-29", "2025-09-27"], "dims": [],
                        "stored": "50000000", "displayed": "-50000000", "decimals": "-6"}


@pytest.mark.parametrize(("cell", "sign", "stored", "displayed"), [
    ("({f})", "-", -50, -50),  # sign and parentheses
    ("{f}", "-", -50, 50),  # sign only: the instance holds it negative, the page prints it plain
    ("({f})", None, 50, -50),  # parentheses only: printed negative, held positive
    ("$ ({f})", None, 50, -50),
    ("(${f})", None, 50, -50),
    ("-{f}", None, 50, -50),
    ("−{f}", None, 50, -50),
])
def test_sign_and_printed_negation_are_kept_apart(cell: str, sign: str | None, stored: int, displayed: int) -> None:
    rows = income_rows()
    rows[4] = row("Interest expense", cell.format(f=fact("us-gaap:InterestExpense", "FY25", "50", sign=sign)),
                  cell.format(f=fact("us-gaap:InterestExpense", "FY24", "40", sign=sign)))
    lines = read_statements(income_filing(rows), "hal.htm")[0].lines
    key = next(line for line in lines if line.label == "Interest expense").keys[0]
    assert key is not None
    assert (key.stored, key.displayed) == (stored * M, displayed * M)


def test_parentheses_split_across_cells_still_negate() -> None:
    rows = income_rows()
    rows[4] = ("<tr><td>Interest expense</td><td>(</td><td>" + fact("us-gaap:InterestExpense", "FY25", "50")
               + "</td><td>)</td><td>(</td><td>" + fact("us-gaap:InterestExpense", "FY24", "40") + "</td><td>)</td></tr>")
    key = next(line for line in read_statements(income_filing(rows), "hal.htm")[0].lines if line.label == "Interest expense").keys[0]
    assert key is not None and key.displayed == -50 * M


def test_an_unbalanced_parenthesis_refuses_the_line() -> None:
    rows = income_rows()
    rows[4] = row("Interest expense", "(" + fact("us-gaap:InterestExpense", "FY25", "50"), fact("us-gaap:InterestExpense", "FY24", "40"))
    problem = read_statements(income_filing(rows), "hal.htm")[0].problem
    assert "'Interest expense'" in problem and "a parenthesis that opens or closes on one side only" in problem


def test_a_minus_inside_the_tagged_figure_is_refused() -> None:
    rows = income_rows()
    rows[4] = row("Interest expense", fact("us-gaap:InterestExpense", "FY25", "-50"), fact("us-gaap:InterestExpense", "FY24", "40"))
    assert "a minus sign inside the tagged figure" in read_statements(income_filing(rows), "hal.htm")[0].problem


@pytest.mark.parametrize(("scale", "text", "expected"), [("-2", "5.2", Decimal("0.052")), ("0", "41", Decimal(41)),
                                                         ("3", "41", Decimal(41_000)), ("9", "4.1", Decimal(4_100_000_000))])
def test_scale_is_an_exact_power_of_ten(scale: str, text: str, expected: Decimal) -> None:
    rows = income_rows()
    rows[3] = row("Research and development", fact("us-gaap:ResearchAndDevelopmentExpense", "FY25", text, scale=scale),
                  fact("us-gaap:ResearchAndDevelopmentExpense", "FY24", text, scale=scale))
    statement_ = read_statements(income_filing(rows), "hal.htm")[0]
    key = next(line for line in statement_.lines if line.label.startswith("Research")).keys[0]
    assert key is not None and key.stored == expected


def test_a_hidden_fact_printed_through_its_reference_is_the_cells_figure() -> None:
    hidden = fact("us-gaap:ResearchAndDevelopmentExpense", "FY24", "—", fmt="ixt:fixed-zero", fact_id="h1")
    rows = income_rows()
    rows[3] = row("Research and development", fact("us-gaap:ResearchAndDevelopmentExpense", "FY25", "0", fmt=""),
                  '<span style="-sec-ix-hidden:h1">—</span>')
    rows[5] = row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", "1,750"), fact("us-gaap:NetIncomeLoss", "FY24", "1,610"))
    key = next(line for line in read_statements(income_filing(rows, hidden=hidden), "hal.htm")[0].lines
               if line.label.startswith("Research")).keys[1]
    assert key is not None and key.stored == 0 and key.context == "FY24"


def test_a_subtotal_that_does_not_foot_refuses_the_statement() -> None:
    rows = income_rows()
    rows[2] = row("Gross margin", fact("us-gaap:GrossProfit", "FY25", "1,900"), fact("us-gaap:GrossProfit", "FY24", "1,650"))
    result = _read(income_filing(rows))
    assert result.has_fatal_errors
    assert result.fatal_error_message is not None
    assert "'Gross margin'" in result.fatal_error_message and "stopped instead of guessing" in result.fatal_error_message


@pytest.mark.parametrize(("gross", "decimals", "foots"), [
    ("1,800", "-6", True),  # exact
    ("1,801", "-6", True),  # off 1M, within 0.5M + 0.5M + 0.5M
    ("1,802", "-6", False),  # off 2M: beyond the three half-units
    ("1,801.0", "-5", True),  # off 1.0M, within 0.5M + 0.5M + 0.05M
    ("1,801.1", "-5", False),  # off 1.1M, beyond 1.05M: mixed decimals use each fact's own
])
def test_footing_uses_each_facts_own_rounding(gross: str, decimals: str, foots: bool) -> None:
    rows = income_rows()
    rows[2] = row("Gross margin", fact("us-gaap:GrossProfit", "FY25", gross, decimals=decimals),
                  fact("us-gaap:GrossProfit", "FY24", "1,650"))
    rows[5] = row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", str(Decimal(gross.replace(",", "")) - 350)),
                  fact("us-gaap:NetIncomeLoss", "FY24", "1,330"))
    result = _read(income_filing(rows))
    assert result.has_fatal_errors is not foots, result.fatal_error_message


def test_footing_boundary_is_closed() -> None:
    # Off by exactly the summed half-widths (0.5M + 0.5M + 0.5M = 1.5M) is consistent; 1.5M + 1 is not.
    from variance_agent.intake import _foots
    assert _foots([(Decimal("4100000000"), "-6", 1), (Decimal("-2300000000"), "-6", 1)], (Decimal("1801500000"), "-6"))
    assert not _foots([(Decimal("4100000000"), "-6", 1), (Decimal("-2300000000"), "-6", 1)], (Decimal("1801500001"), "-6"))
    assert _foots([(Decimal("41"), "INF", 1)], (Decimal("41"), "INF"))
    assert not _foots([(Decimal("41"), "INF", 1)], (Decimal("41.0001"), "INF"))


def test_the_face_statement_is_read_not_a_note_with_the_same_title() -> None:
    note = statement("NOTE 9 - CONSOLIDATED STATEMENTS OF OPERATIONS BY QUARTER", income_rows(("9,999", "8,888")))
    result = _read(income_filing(extra=note))
    assert _amounts(result)[0][3] == 4100 * M


def test_a_balance_sheet_is_listed_but_not_compared_yet() -> None:
    sheet = statement("CONSOLIDATED BALANCE SHEETS", [
        row("Cash", fact("us-gaap:Cash", "I25", "500"), fact("us-gaap:Cash", "I24", "400")),
        row("Inventory", fact("us-gaap:InventoryNet", "I25", "300"), fact("us-gaap:InventoryNet", "I24", "250")),
        row("Total assets", fact("us-gaap:Assets", "I25", "800"), fact("us-gaap:Assets", "I24", "650"))])
    result = _read(income_filing(extra=sheet), sheet="Consolidated Balance Sheets")
    assert result.fatal_error_message == ("'Consolidated Balance Sheets' lists assets, liabilities and equity, which "
                                          "can't be compared as revenue and expense yet. Choose an income statement "
                                          "instead: Consolidated Statements of Operations.")


@pytest.mark.parametrize("prolog", [b'<!DOCTYPE html [<!ENTITY x "y">]>', b'<!ENTITY x "y">', b"<!doctype x [ ]>"])
def test_entity_declarations_and_doctype_subsets_are_refused_before_reading(prolog: bytes) -> None:
    assert _read(prolog + income_filing()).fatal_error_message == (
        "'hal-20250927.htm' declares an XML entity or document type subset, which this reader refuses. "
        "Upload the filing's PDF, or a CSV or Excel copy of the statement.")


def test_a_plain_html_doctype_is_read() -> None:
    assert not _read(b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "x.dtd">' + income_filing()).has_fatal_errors


def test_a_problem_in_one_statement_leaves_the_others_readable() -> None:
    sheet = statement("CONSOLIDATED BALANCE SHEETS", [
        row("Cash", "(" + fact("us-gaap:Cash", "I25", "500"), fact("us-gaap:Cash", "I24", "400")),
        row("Inventory", fact("us-gaap:InventoryNet", "I25", "300"), fact("us-gaap:InventoryNet", "I24", "250")),
        row("Total assets", fact("us-gaap:Assets", "I25", "800"), fact("us-gaap:Assets", "I24", "650"))])
    result = _read(income_filing(extra=sheet))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert "a parenthesis that opens or closes on one side only" in (
        _read(income_filing(extra=sheet), sheet="Consolidated Balance Sheets").fatal_error_message or "")


def test_a_web_page_without_xbrl_figures_is_refused_plainly() -> None:
    message = _read(b"<html><body><table><tr><td>Revenue</td><td>4,100</td></tr></table></body></html>").fatal_error_message
    assert message == ("'hal-20250927.htm' is a web page without Inline XBRL figures, so it has no statements I can find. "
                       "Upload the filing's 10-K or 10-Q document from its EDGAR folder, its PDF, or a CSV or Excel table.")


def test_the_cli_reads_a_filing_and_records_its_keys_in_audit_19(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "hal-20250927.htm"
    path.write_bytes(income_filing())
    audit = tmp_path / "audit.json"
    assert cli.main([str(path), "--assisted", "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "1",
                     "--audit-json", str(audit), "-o", str(tmp_path / "r.md")]) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads((ROOT / "schemas/audit-1.9.schema.json").read_text(encoding="utf-8"))).validate(record)
    assert record["schema_version"] == "1.9"
    assert record["source"]["document"]["kind"] == "ixbrl"
    assert "Revenue" in (tmp_path / "r.md").read_text(encoding="utf-8")


def test_strict_mode_points_html_filings_at_assisted_intake(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "hal-20250927.htm"
    path.write_bytes(income_filing())
    with pytest.raises(SystemExit):
        cli.main([str(path), "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "1"])
    assert ("HTML filings are read with --assisted, which finds the financial statements in the filing and lists "
            "every adjustment it makes.") in capsys.readouterr().err


def test_the_chat_reads_an_uploaded_filing() -> None:
    session = Session()
    response = handle_upload(session, income_filing(), "hal-20250927.htm")
    assert "Consolidated Statements of Operations" in response.text
    assert "**Statement:**" in response.text


def test_document_text_in_scripts_is_never_read() -> None:
    assert all(line.label != "trap" for line in read_statements(income_filing(), "hal.htm")[0].lines)
    assert document("<p>x</p>")  # the builder itself carries the script trap


def test_one_axis_breakdown_lines_are_printed_lines_and_their_total_foots() -> None:
    rows = income_rows()
    rows[0:1] = [row("Products", fact("us-gaap:Revenues", "FY25_products", "3,000"), fact("us-gaap:Revenues", "FY24_products", "2,900")),
                 row("Services", fact("us-gaap:Revenues", "FY25_services", "1,100"), fact("us-gaap:Revenues", "FY24_services", "1,000")),
                 row("Total net sales", fact("us-gaap:Revenues", "FY25", "4,100"), fact("us-gaap:Revenues", "FY24", "3,900"))]
    result = _read(income_filing(rows))
    assert [(line, kind) for line, kind, *_ in _amounts(result)][:3] == [("Products", "Revenue"), ("Services", "Revenue"),
                                                                         ("Cost of sales", "Expense")]
    assert "Total net sales" in result.detected_totals
    record = result.source_document()
    assert record is not None
    products = next(line for line in record["lines"] if line["line_item"] == "Products")  # type: ignore[union-attr, index]
    assert products["columns"][0]["dims"] == [{"axis": "srt:ProductOrServiceAxis", "member": "us-gaap:ProductMember"}]


def test_a_breakdown_that_does_not_add_up_to_its_total_refuses() -> None:
    rows = income_rows()
    rows[0:1] = [row("Products", fact("us-gaap:Revenues", "FY25_products", "3,000"), fact("us-gaap:Revenues", "FY24_products", "2,900")),
                 row("Total net sales", fact("us-gaap:Revenues", "FY25", "4,100"), fact("us-gaap:Revenues", "FY24", "3,900"))]
    assert _read(income_filing(rows)).has_fatal_errors


def test_a_subtotal_named_net_income_before_taxes_is_a_subtotal() -> None:
    rows = income_rows()
    rows[5:6] = [row("Net income (loss) before income taxes", fact("us-gaap:IncomeLossBeforeTaxes", "FY25", "1,450"),
                     fact("us-gaap:IncomeLossBeforeTaxes", "FY24", "1,330")),
                 row("Income taxes", fact("us-gaap:IncomeTaxExpenseBenefit", "FY25", "450"),
                     fact("us-gaap:IncomeTaxExpenseBenefit", "FY24", "330")),
                 row("Net income (loss)", fact("us-gaap:NetIncomeLoss", "FY25", "1,000"), fact("us-gaap:NetIncomeLoss", "FY24", "1,000"))]
    result = _read(income_filing(rows))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert "Net income (loss) before income taxes" in result.detected_totals


def test_a_label_wrapped_onto_the_row_above_names_the_figures_row() -> None:
    rows = income_rows()
    rows[3:4] = ["<tr><td>Research and development, including</td></tr>",
                 row("", fact("us-gaap:ResearchAndDevelopmentExpense", "FY25", "300"),
                     fact("us-gaap:ResearchAndDevelopmentExpense", "FY24", "280"))]
    names = [line for line, *_ in _amounts(_read(income_filing(rows)))]
    assert "Research and development, including" in names


def test_an_untagged_dash_reads_as_zero_and_is_not_part_of_the_label() -> None:
    rows = income_rows()
    rows.insert(4, row("Restructuring", "—", fact("us-gaap:RestructuringCharges", "FY24", "0", fmt="")))
    result = _read(income_filing(rows))
    restructuring = next(r for r in result.rows if r["line_item"] == "Restructuring")
    assert Decimal(str(restructuring["actual"])) == 0


def test_a_total_named_only_by_its_concept_is_a_subtotal() -> None:
    rows = income_rows()
    rows[4:6] = [row("Interest expense", "(" + fact("us-gaap:InterestExpense", "FY25", "50") + ")",
                     "(" + fact("us-gaap:InterestExpense", "FY24", "40") + ")"),
                 row("Net other expense", "(" + fact("us-gaap:NonoperatingIncomeExpense", "FY25", "50") + ")",
                     "(" + fact("us-gaap:NonoperatingIncomeExpense", "FY24", "40") + ")"),
                 row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", "1,450"), fact("us-gaap:NetIncomeLoss", "FY24", "1,330"))]
    result = _read(income_filing(rows))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert "Net other expense" in result.detected_totals


def test_an_unlabeled_figures_row_after_a_section_is_that_sections_total() -> None:
    rows = income_rows()
    rows[0:3] = ["<tr><td>Revenues:</td></tr>",
                 row("Rental income", fact("us-gaap:Revenues", "FY25_products", "4,000"),
                     fact("us-gaap:Revenues", "FY24_products", "3,800")),
                 row("Other", fact("us-gaap:Revenues", "FY25_services", "100"), fact("us-gaap:Revenues", "FY24_services", "100")),
                 row("", fact("us-gaap:Revenues", "FY25", "4,100"), fact("us-gaap:Revenues", "FY24", "3,900")),
                 row("Cost of sales", fact("us-gaap:CostOfRevenue", "FY25", "2,300"), fact("us-gaap:CostOfRevenue", "FY24", "2,250")),
                 row("Gross margin", fact("us-gaap:GrossProfit", "FY25", "1,800"), fact("us-gaap:GrossProfit", "FY24", "1,650"))]
    result = _read(income_filing(rows))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert "Total Revenues" in result.detected_totals


def test_a_subtotal_named_first_figure_is_read_as_the_line_it_prints() -> None:
    # Nothing above "Total revenues" adds up to it, so it is never dropped as a subtotal.
    rows = [row("Total revenues", fact("us-gaap:Revenues", "FY25", "4,100"), fact("us-gaap:Revenues", "FY24", "3,900")),
            *income_rows()[1:]]
    result = _read(income_filing(rows))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.rows[0]["line_item"] == "Total revenues" and result.rows[0]["type"] == "Revenue"


def test_zero_width_characters_are_not_part_of_a_label() -> None:
    rows = income_rows()
    rows[1] = row("Cost of sales​ ​", fact("us-gaap:CostOfRevenue", "FY25", "2,300"), fact("us-gaap:CostOfRevenue", "FY24", "2,250"))
    assert "Cost of sales" in [line for line, *_ in _amounts(_read(income_filing(rows)))]


def test_a_total_concept_used_for_a_detail_line_is_read_as_a_line() -> None:
    rows = income_rows()
    rows[3] = row("Operating expenses", fact("us-gaap:OperatingExpenses", "FY25", "300"),
                  fact("us-gaap:OperatingExpenses", "FY24", "280"))
    result = _read(income_filing(rows))
    assert not result.has_fatal_errors, result.fatal_error_message
    assert "Operating expenses" in [r["line_item"] for r in result.rows]


def test_a_comprehensive_statement_opening_with_net_income_reads() -> None:
    oci = statement("CONSOLIDATED STATEMENTS OF COMPREHENSIVE INCOME", [
        row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", "1,450"), fact("us-gaap:NetIncomeLoss", "FY24", "1,330")),
        row("Foreign currency translation", fact("us-gaap:OtherComprehensiveIncomeForeignCurrency", "FY25", "50"),
            fact("us-gaap:OtherComprehensiveIncomeForeignCurrency", "FY24", "30")),
        row("Comprehensive income", fact("us-gaap:ComprehensiveIncomeNetOfTax", "FY25", "1,500"),
            fact("us-gaap:ComprehensiveIncomeNetOfTax", "FY24", "1,360"))])
    result = _read(income_filing(extra=oci), sheet="Consolidated Statements of Comprehensive Income")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert [r["line_item"] for r in result.rows] == ["Net income", "Foreign currency translation"]


def test_a_title_printed_inside_the_table_names_its_statement() -> None:
    sheet = statement("CONSOLIDATED BALANCE SHEETS", [
        row("Cash", fact("us-gaap:Cash", "I25", "500"), fact("us-gaap:Cash", "I24", "400")),
        row("Inventory", fact("us-gaap:InventoryNet", "I25", "300"), fact("us-gaap:InventoryNet", "I24", "250")),
        row("Total assets", fact("us-gaap:Assets", "I25", "800"), fact("us-gaap:Assets", "I24", "650"))])
    inline_title = ("<table><tr><td>CONSOLIDATED STATEMENTS OF OPERATIONS</td></tr><tr><td>(In millions)</td></tr>"
                    + "".join(income_rows()) + "</table>")
    names = [s.name for s in read_statements(document(sheet + inline_title).encode("utf-8"), "hal.htm")]
    assert names == ["Consolidated Balance Sheets", "Consolidated Statements of Operations"]


def test_an_untitled_table_of_other_periods_does_not_continue_a_statement() -> None:
    sheet = statement("CONSOLIDATED BALANCE SHEETS", [
        row("Cash", fact("us-gaap:Cash", "I25", "500"), fact("us-gaap:Cash", "I24", "400")),
        row("Inventory", fact("us-gaap:InventoryNet", "I25", "300"), fact("us-gaap:InventoryNet", "I24", "250")),
        row("Total assets", fact("us-gaap:Assets", "I25", "800"), fact("us-gaap:Assets", "I24", "650"))])
    untitled = "<table>" + "".join(income_rows()) + "</table>"
    statements = read_statements(document(sheet + untitled).encode("utf-8"), "hal.htm")
    assert [(s.name, len(s.lines)) for s in statements] == [("Consolidated Balance Sheets", 3)]


@pytest.mark.parametrize("title", ["CONSOLIDATED STATEMENTS OF LOSS", "Consolidated Income Statements"])
def test_other_income_statement_titles_are_found(title: str) -> None:
    statement_ = read_statements(document(statement(title, income_rows())).encode("utf-8"), "hal.htm")[0]
    assert statement_.kind == "income"


def test_a_title_split_across_spans_inside_a_word_is_found() -> None:
    title = "<span>CONSOLIDATED STATEM</span><span>ENTS OF</span> <span>OPE</span><span>RATIONS</span>"
    body = ("<p>" + "</p><p>".join(f"page header {n}" for n in range(30)) + "</p>" + statement(title, income_rows()))
    assert read_statements(document(body).encode("utf-8"), "hal.htm")[0].name == "Consolidated Statements of Operations"
