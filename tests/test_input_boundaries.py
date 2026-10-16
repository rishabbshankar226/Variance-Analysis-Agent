"""Public API and data-only input failures must be actionable and bounded."""

from dataclasses import replace
from decimal import Decimal

import pytest

from variance_agent import AnalysisConfig, analyze_rows
from variance_agent.audit import build_audit_record
from variance_agent.cli import main
from variance_agent.parsing import load_bytes, load_json_text, normalize_row, parse_decimal
from variance_agent.report import render_markdown


CONFIG = AnalysisConfig("Q3", Decimal("1"), Decimal(".05"))
ROWS = [{"Line Item": "Sales", "Budget": "100", "Actual": "120"}]


@pytest.mark.parametrize("value", ["1", 1, 1.0, None, True])
def test_invalid_threshold_types_raise_validation_errors(value):
    with pytest.raises(ValueError, match="threshold|Decimal"):
        analyze_rows(ROWS, replace(CONFIG, dollar_threshold=value))


@pytest.mark.parametrize("period", ["", "  ", None, True, ["Q3"]])
def test_period_must_be_nonblank_text(period):
    with pytest.raises(ValueError, match="[Pp]eriod"):
        analyze_rows(ROWS, replace(CONFIG, period=period))


@pytest.mark.parametrize("row", [None, 1, "Sales", ["Sales", 100, 120]])
def test_invalid_row_types_raise_validation_errors(row):
    with pytest.raises(ValueError, match="[Rr]ow"):
        analyze_rows([row], CONFIG)


@pytest.mark.parametrize("row", [{None: "hidden", "Budget": 1}, {"???": "hidden"}])
def test_unnamed_populated_api_fields_cannot_disappear(row):
    with pytest.raises(ValueError, match="header|[Cc]olumn"):
        normalize_row(row)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_json_constants_are_rejected_in_metadata(constant):
    with pytest.raises(ValueError, match="finite|constant"):
        load_json_text('[{"Line Item":"Sales","Budget":100,"Actual":120,"Notes":'
                       + constant + '}]')


@pytest.mark.parametrize("value", ["9" * 5000, Decimal("1e-999999")],
                         ids=["long-coefficient", "extreme-scale"])
def test_numeric_literals_are_bounded_before_analysis_or_serialization(value):
    with pytest.raises(ValueError, match="precision|range|length"):
        parse_decimal(value, field="Budget", line_item="Sales")


def test_declared_period_cannot_mix_or_omit_reporting_periods():
    for periods in (("Q3", "Q4"), ("Q3", None)):
        rows = [dict(ROWS[0], Period=period) for period in periods]
        with pytest.raises(ValueError, match="[Pp]eriod"):
            analyze_rows(rows, CONFIG)


def test_byte_capture_is_bounded_before_decoding():
    with pytest.raises(ValueError, match="size|bytes|MiB"):
        load_bytes(b" " * (32 * 1024 * 1024 + 1), ".json")


@pytest.mark.parametrize("function", [render_markdown, build_audit_record])
def test_output_boundaries_reject_tampered_financial_results(function):
    result = analyze_rows(ROWS, CONFIG)
    corrupted = replace(result, revenue=replace(result.revenue, actual=Decimal("999")))
    with pytest.raises((ValueError, RuntimeError), match="verification|reconcil|mismatch"):
        function(corrupted)


def test_cli_blank_period_preserves_existing_outputs(tmp_path, capsys):
    source, report, audit = tmp_path / "input.csv", tmp_path / "report.md", tmp_path / "audit.json"
    source.write_text("Line Item,Budget,Actual\nSales,100,120\n")
    report.write_text("existing report")
    audit.write_text("existing audit")
    with pytest.raises(SystemExit) as error:
        main([str(source), "--period", " ", "--dollar-threshold", "1", "--percent-threshold", "5",
              "--output", str(report), "--audit-json", str(audit)])
    assert error.value.code == 2
    assert "eriod" in capsys.readouterr().err
    assert report.read_text() == "existing report"
    assert audit.read_text() == "existing audit"


@pytest.mark.parametrize("field", ["line_item", "period"])
def test_rendered_source_text_cannot_emit_terminal_or_bidi_controls(field):
    payload = "Sales\x1b[2J\u202e123"
    row = dict(ROWS[0], Type="Revenue")
    cfg = CONFIG
    if field == "line_item":
        row["Line Item"] = payload
    else:
        cfg = replace(CONFIG, period=payload)
    report = render_markdown(analyze_rows([row], cfg))
    assert "\x1b" not in report
    assert "\u202e" not in report
    assert "123" in report


def test_valid_subnormal_amounts_do_not_trigger_unused_driver_arithmetic():
    result = analyze_rows([{"Line Item": "Sales", "Budget": "1e-1048", "Actual": "2e-1048"}],
                          replace(CONFIG, dollar_threshold=Decimal("0")))
    assert result.rows[0].variance_dollars == Decimal("1e-1048")
