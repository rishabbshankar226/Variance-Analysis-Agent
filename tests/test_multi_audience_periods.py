"""New quarter vocabulary is opt-in; old labels keep old wording."""
import pytest
from variance_agent.comparison import parse_period_label, order_period_labels
from variance_agent.comparisons import analyze_comparisons
from variance_agent.models import ComparisonBasis as Basis
from variance_agent.report import render_markdown
from test_multi_audience_measures import config


@pytest.mark.parametrize("label", ["3Q26", "Q3 FY26", "F3Q26", "Q3'26", "3QFY26"])
def test_new_quarters_require_extended_recognition(label):
    assert parse_period_label(label) is None
    assert parse_period_label(label, extended=True) == (2026, "quarter", 3)


def test_new_quarter_relationships_and_legacy_wording():
    for prior, expected in [("3Q25", "Prior Year (3Q25)"), ("2Q26", "Prior Quarter (2Q26)")]:
        result = analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "3Q26": "110", prior: "100"}],
                                    config(), (Basis.PRIOR_PERIOD,)).comparisons[0].result
        assert expected in render_markdown(result)
    result = analyze_comparisons([{"Line Item": "Revenue", "Type": "Revenue", "FY2025": "110", "FY2024": "100"}],
                                config(period="FY2025"), (Basis.PRIOR_PERIOD,)).comparisons[0].result
    assert "Prior Period (FY2024)" in render_markdown(result)


@pytest.mark.parametrize("labels", [["Q3 FY26", "Q3 2025"], ["3Q26", "FY2025"], ["3Q26", "Q3'26"]])
def test_mixed_calendar_granularity_and_duplicate_periods_are_not_ordered(labels):
    assert order_period_labels(labels, extended=True) is None
