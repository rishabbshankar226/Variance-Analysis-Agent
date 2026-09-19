from decimal import Decimal

import pytest

from variance_agent.analysis import analyze_rows
from variance_agent.models import AnalysisConfig
from variance_agent.parsing import load_csv_text, parse_decimal
from variance_agent.report import render_markdown


def cfg(dollars="100", pct="0.05"):
    return AnalysisConfig(
        period="Q3 2026",
        dollar_threshold=Decimal(dollars),
        percent_threshold=Decimal(pct),
    )


def test_empty_dataset_fails_instead_of_reporting_false_zero_totals():
    with pytest.raises(ValueError, match="no data rows"):
        analyze_rows([], cfg())


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_financial_values_are_rejected(value):
    with pytest.raises(ValueError, match="finite number"):
        parse_decimal(value, field="Budget", line_item="Revenue")


def test_normalized_header_collision_fails_loudly():
    with pytest.raises(ValueError, match="normalize to the same key"):
        load_csv_text("Line Item,Actual,Actual $,Budget\nRevenue,10,11,9\n")


def test_summary_only_row_is_used_when_no_detail_exists():
    result = analyze_rows(
        [{"Line Item": "Total Revenue", "Budget": 100, "Actual": 120, "Type": "Revenue"}],
        cfg(),
    )
    assert result.revenue.actual == Decimal("120")
    assert result.rows[0].excluded_from_aggregation is False


def test_summary_row_is_excluded_when_same_type_detail_exists():
    result = analyze_rows(
        [
            {"Line Item": "Sales Revenue", "Budget": 100, "Actual": 120, "Type": "Revenue"},
            {"Line Item": "Total Revenue", "Budget": 100, "Actual": 120, "Type": "Revenue"},
        ],
        cfg(),
    )
    assert result.revenue.actual == Decimal("120")
    assert result.rows[1].excluded_from_aggregation is True
    assert [row.line_item for row in result.material_rows] == ["Sales Revenue"]


def test_multiple_summary_only_rows_are_rejected_as_ambiguous():
    with pytest.raises(ValueError, match="summary rows"):
        analyze_rows(
            [
                {"Line Item": "Total Revenue", "Budget": 100, "Actual": 120, "Type": "Revenue"},
                {"Line Item": "Grand Total Revenue", "Budget": 100, "Actual": 120, "Type": "Revenue"},
            ],
            cfg(),
        )


def test_report_marks_classification_incomplete_instead_of_claiming_zero_totals():
    result = analyze_rows(
        [{"Line Item": "Mystery", "Budget": 100, "Actual": 120}],
        cfg(),
    )
    report = render_markdown(result)
    assert "classification incomplete" in report
    assert "Net operating impact is N/A" in report


def test_report_marks_missing_revenue_as_not_available():
    result = analyze_rows(
        [{"Line Item": "Marketing Expense", "Budget": 100, "Actual": 120, "Type": "Expense"}],
        cfg(),
    )
    report = render_markdown(result)
    assert "Total Revenue: N/A (no Revenue rows supplied)" in report
    assert "Net operating impact is N/A" in report


def test_report_escapes_line_item_markdown_injection():
    result = analyze_rows(
        [
            {
                "Line Item": "Revenue\n## HACKED",
                "Budget": 100,
                "Actual": 120,
                "Type": "Revenue",
            }
        ],
        cfg(),
    )
    report = render_markdown(result)
    assert "\n## HACKED" not in report
    assert "Revenue ## HACKED" in report
