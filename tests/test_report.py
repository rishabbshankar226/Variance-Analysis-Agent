from decimal import Decimal
from html import unescape

import pytest

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


@pytest.mark.parametrize('source', [
    'Licensing &copy; Revenue', 'Sales &#169;', 'Sales &#xA9;',
    'Sales &lt;Reviewed&gt;', 'R&D <Reviewed> Revenue', 'Sales &amp; Revenue',
    'Sales &copy Revenue',
])
@pytest.mark.parametrize('field', ['line_item', 'period'])
def test_source_text_remains_literal_when_html_entities_are_rendered(source, field):
    label = source if field == 'line_item' else 'Sales'
    period = source if field == 'period' else 'Q3'
    result = analyze_rows(
        [{'Line Item': label, 'Budget': '100', 'Actual': '120', 'Type': 'Revenue'}],
        AnalysisConfig(period, Decimal('1'), Decimal('.05')),
    )
    report = render_markdown(result)
    if field == 'period':
        displayed = report.splitlines()[0].removeprefix('# FP&A Variance Report: ')
    else:
        row = next(line for line in report.splitlines()
                   if line.startswith('| ') and not line.startswith('| Line Item |'))
        displayed = row.removeprefix('| ').split(' | ', 1)[0]
    assert unescape(displayed) == source


@pytest.mark.parametrize('currency, dollars, ratio, expected', [
    ('USD', '10000', '.05', '$10,000.00 or 5.0%'),
    ('USD', '10.005', '.00001', '$10.005 or 0.001%'),
    ('EUR', '.001', '.05005', '€0.001 or 5.005%'),
    ('GBP', '1234.567800', '.00001000', '£1,234.5678 or 0.001%'),
    ('USD', '0', '0', '$0.00 or 0.0%'),
    ('USD', '-0', '-0', '$0.00 or 0.0%'),
    ('USD', '1e-20', '1e-20', '$0.00000000000000000001 or 0.000000000000000001%'),
])
def test_report_shows_the_exact_materiality_thresholds(currency, dollars, ratio, expected):
    result = analyze_rows(
        [{'Line Item': 'Sales', 'Budget': '100', 'Actual': '120', 'Type': 'Revenue'}],
        AnalysisConfig('Q3', Decimal(dollars), Decimal(ratio), currency=currency),
    )
    assert f'Thresholds: {expected}' in render_markdown(result)


def test_displayed_dollar_threshold_explains_strict_materiality_boundary():
    result = analyze_rows(
        [
            {'Line Item': 'At limit', 'Budget': '100', 'Actual': '110.005', 'Type': 'Revenue'},
            {'Line Item': 'Above limit', 'Budget': '100', 'Actual': '110.006', 'Type': 'Revenue'},
        ],
        AnalysisConfig('Q3', Decimal('10.005'), Decimal('1')),
    )
    assert [row.line_item for row in result.material_rows] == ['Above limit']
    assert 'Thresholds: $10.005 or 100.0%' in render_markdown(result)


def test_displayed_percent_threshold_explains_strict_materiality_boundary():
    result = analyze_rows(
        [
            {'Line Item': 'At limit', 'Budget': '100', 'Actual': '100.005', 'Type': 'Revenue'},
            {'Line Item': 'Above limit', 'Budget': '100', 'Actual': '100.006', 'Type': 'Revenue'},
        ],
        AnalysisConfig('Q3', Decimal('100'), Decimal('.00005')),
    )
    assert [row.line_item for row in result.material_rows] == ['Above limit']
    assert 'Thresholds: $100.00 or 0.005%' in render_markdown(result)
