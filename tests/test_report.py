from decimal import Decimal

from variance_agent.analysis import analyze_rows
from variance_agent.models import AnalysisConfig
from variance_agent.report import render_markdown


def test_report_contract_sections():
    rows = [
        {"Line Item": "Sales Revenue", "Budget": 100000, "Actual": 120000, "Type": "Revenue"},
        {"Line Item": "Marketing Expense", "Budget": 20000, "Actual": 35000, "Type": "Expense"},
    ]
    result = analyze_rows(
        rows,
        AnalysisConfig(
            period="Q3 2026",
            dollar_threshold=Decimal("10000"),
            percent_threshold=Decimal("0.05"),
        ),
    )
    report = render_markdown(result)
    assert report.startswith("# FP&A Variance Report: Q3 2026")
    assert "## Executive Summary" in report
    assert "## Material Variances" in report
    assert "## Root Cause Analysis" in report
    assert "## Strategic Recommendations" in report
    assert "Hypothesis" in report
