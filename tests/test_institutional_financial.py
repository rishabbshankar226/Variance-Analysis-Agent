"""Independent reporting and source-precision regressions."""

from decimal import Decimal
from fractions import Fraction
from io import BytesIO
from random import Random
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

from variance_agent import AnalysisConfig, analyze_rows
from variance_agent.audit import build_audit_record
from variance_agent.parsing import load_bytes
from variance_agent.report import render_markdown


CONFIG = AnalysisConfig("Q3", Decimal("0"), Decimal("0"))


def _table_amounts(report):
    rows = {}
    for line in report.splitlines():
        if line.startswith("| Account "):
            cells = [cell.strip() for cell in line.split("|")[1:-1]]
            rows[cells[0]] = tuple(Decimal(value.replace("$", "").replace(",", ""))
                                  for value in cells[2:5])
    return rows


def test_fractional_cents_reconcile_details_and_total_without_allocating_pennies():
    result = analyze_rows([
        {"Line Item": "Account A", "Budget": "0", "Actual": ".005", "Type": "Revenue"},
        {"Line Item": "Account B", "Budget": "0", "Actual": ".005", "Type": "Revenue"},
    ], CONFIG)
    report = render_markdown(result)
    details = _table_amounts(report)
    assert sum(amounts[1] for amounts in details.values()) == result.revenue.actual
    assert "Total Revenue: $0.010 vs. $0.000 ($0.010" in report


def test_report_accounting_identities_against_fraction_oracle():
    rng = Random(20261016)
    for case in range(60):
        rows = []
        for index in range(7):
            budget, variance = rng.randrange(-100_000, 100_000), rng.choice((-7, -5, 5, 7))
            rows.append({"Line Item": f"Account {case}-{index}", "Type": "Revenue",
                         "Budget": str(Decimal(budget).scaleb(-3)),
                         "Actual": str(Decimal(budget + variance).scaleb(-3))})
        result = analyze_rows(rows, CONFIG)
        details = _table_amounts(render_markdown(result))
        for source in rows:
            budget, actual, variance = map(Fraction, details[source["Line Item"]])
            assert budget == Fraction(source["Budget"])
            assert actual == Fraction(source["Actual"])
            assert variance == actual - budget
        assert sum(Fraction(values[2]) for values in details.values()) == Fraction(
            result.revenue.variance_dollars)


def test_driver_residual_is_disclosed_and_components_reconcile_exactly():
    result = analyze_rows([{
        "Line Item": "Sales", "Budget": "100", "Actual": "132.009",
        "Budget Units": "10", "Actual Units": "12", "Budget Price": "10", "Actual Price": "11",
    }], CONFIG)
    row = result.rows[0]
    assert row.driver_evidence.reconciles
    assert sum(value for _, value in row.driver_evidence.components) == row.variance_dollars
    report = render_markdown(result)
    assert "Unexplained residual: $0.009" in report
    record = build_audit_record(result)
    components = record["material_variances"][0]["driver"]["components"]
    assert sum(Decimal(component["amount"]) for component in components) == row.variance_dollars


def test_percent_display_rounds_exact_ratio_once_at_reporting_boundary():
    budget = 2 * 10**49 - 1901
    variance = (101 * budget + 1) // 2000
    assert Fraction(variance, budget) > Fraction(101, 2000)
    result = analyze_rows([{"Line Item": "Sales", "Budget": str(budget),
                            "Actual": str(budget + variance)}], CONFIG)
    line = next(line for line in render_markdown(result).splitlines()
                if line.startswith("| Sales |"))
    assert "| 5.1% |" in line


def test_excel_financial_values_preserve_stored_decimal_xml():
    book = Workbook()
    book.active.append(["Line Item", "Budget", "Actual"])
    book.active.append(["Sales", 1.01, 1.02])
    capture = BytesIO()
    book.save(capture)
    book.close()
    with ZipFile(BytesIO(capture.getvalue())) as archive:
        contents = {item.filename: archive.read(item.filename) for item in archive.infolist()}
    contents["xl/worksheets/sheet1.xml"] = contents["xl/worksheets/sheet1.xml"].replace(
        b"<v>1.01</v>", b"<v>9007199254740992.01</v>").replace(
        b"<v>1.02</v>", b"<v>9007199254740992.02</v>")
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, content in contents.items():
            archive.writestr(name, content)
    result = analyze_rows(load_bytes(output.getvalue(), ".xlsx"), CONFIG)
    assert result.rows[0].budget == Decimal("9007199254740992.01")
    assert result.rows[0].actual == Decimal("9007199254740992.02")
    assert result.rows[0].variance_dollars == Decimal(".01")


def test_extreme_materiality_cross_products_do_not_overflow_or_underflow():
    large = analyze_rows([{"Line Item": "Sales", "Budget": "1e100", "Actual": "1.1e100"}],
                         AnalysisConfig("Q3", Decimal("1e999"), Decimal("1e999")))
    assert not large.rows[0].material
    small = analyze_rows([{"Line Item": "Sales", "Budget": "1e-1048", "Actual": "2e-1048"}],
                         AnalysisConfig("Q3", Decimal("1"), Decimal("1e-1048")))
    assert small.rows[0].material


def test_large_valid_percentage_threshold_can_be_reported():
    result = analyze_rows([{"Line Item": "Sales", "Budget": "100", "Actual": "120"}],
                          AnalysisConfig("Q3", Decimal("1"), Decimal("1e999")))
    report = render_markdown(result)
    percentage = report.split("Thresholds: ", 1)[1].split(" or ", 1)[1].split("%", 1)[0]
    assert Decimal(percentage.replace(",", "")) == Decimal("1e1001")


def test_negative_baseline_percentage_variance_preserves_sign_polarity():
    from variance_agent.analysis import _percent_variance
    from variance_agent.report import _pct

    # Negative baseline with positive growth (transition from loss to profit)
    # Budget: -100, Actual: 50 -> Variance: +150 (Favorable)
    pct, label = _percent_variance(Decimal("-100"), Decimal("50"))
    assert pct == Decimal("1.5")  # +150%, not -150%
    assert label is None
    assert _pct(Decimal("-100"), Decimal("150")) == "150.0%"

    # Negative baseline with worsening loss
    # Budget: -100, Actual: -150 -> Variance: -50 (Unfavorable)
    pct_loss, _ = _percent_variance(Decimal("-100"), Decimal("-150"))
    assert pct_loss == Decimal("-0.5")  # -50%, not +50%
    assert _pct(Decimal("-100"), Decimal("-50")) == "-50.0%"

    # Full report rendering table verification
    cfg = AnalysisConfig("Q3", Decimal("10"), Decimal("0.05"))
    result = analyze_rows([{"Line Item": "Rev", "Budget": "-100", "Actual": "50", "Type": "Revenue"}], cfg)
    report = render_markdown(result)
    assert "| Rev | Revenue | -$100.00 | $50.00 | $150.00 | 150.0% | F |" in report


def test_financial_context_traps_float_operations():
    from decimal import FloatOperation
    import pytest
    from variance_agent.numeric import financial_context

    with financial_context():
        with pytest.raises(FloatOperation):
            Decimal(1.5)

        with pytest.raises(FloatOperation):
            _ = Decimal("100") > 50.0

        with pytest.raises(FloatOperation):
            _ = Decimal("100") <= 50.0


def test_ratio_isolates_from_ambient_global_context_mutation():
    import decimal
    from variance_agent.numeric import ratio

    original_prec = decimal.getcontext().prec
    try:
        decimal.getcontext().prec = 4
        result = ratio(Decimal("1"), Decimal("3"))
        assert result == Decimal("0.33333333333333333333333333333333333333333333333333")
    finally:
        decimal.getcontext().prec = original_prec


def test_cli_main_handles_runtime_error_without_raw_traceback(monkeypatch):
    import pytest
    from variance_agent import cli

    def _failing_run(_args):
        raise RuntimeError("Final verification failed: test integrity mismatch")

    monkeypatch.setattr(cli, "_run", _failing_run)
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["dummy.csv", "--period", "Q3", "--dollar-threshold", "10", "--percent-threshold", "5"])
    assert exc_info.value.code == 2


def test_write_text_outputs_applies_umask_permissions_to_new_files(tmp_path):
    import os
    from variance_agent.output import write_text_outputs

    report_path = tmp_path / "new_report.md"
    write_text_outputs({report_path: "# FP&A Report\n"})
    current_umask = os.umask(0)
    os.umask(current_umask)
    expected_mode = 0o666 & ~current_umask
    actual_mode = report_path.stat().st_mode & 0o777
    assert actual_mode == expected_mode

