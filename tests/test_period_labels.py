"""Period labels order correctly across the century boundary and common spellings."""

from __future__ import annotations

import pytest

from variance_agent.comparison import order_period_labels, parse_period_label


def test_two_digit_years_use_the_strptime_pivot() -> None:
    assert order_period_labels(["FY99", "FY00"]) == ["FY00", "FY99"]
    assert order_period_labels(["FY00", "FY99"]) == ["FY00", "FY99"]
    assert parse_period_label("FY68") == (2068, "year", 0)
    assert parse_period_label("FY69") == (1969, "year", 0)
    assert parse_period_label("FY25") == (2025, "year", 0)
    assert order_period_labels(["Q4-99", "Q1-00"]) == ["Q1-00", "Q4-99"]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("FY2025", (2025, "year", 0)),
        ("FY 2025", (2025, "year", 0)),
        ("fy 25", (2025, "year", 0)),
        ("2025", (2025, "year", 0)),
        ("Q3 2026", (2026, "quarter", 3)),
        ("Q3-26", (2026, "quarter", 3)),
        ("Sep 2026", (2026, "month", 9)),
        ("Sept 2026", (2026, "month", 9)),
        ("September 2026", (2026, "month", 9)),
        ("2026-09", (2026, "month", 9)),
    ],
)
def test_common_spellings_are_recognised(label: str, expected: tuple[int, str, int]) -> None:
    assert parse_period_label(label) == expected


@pytest.mark.parametrize("label", ["", "Budget", "Q5 2026", "Smarch 2026", "FY"])
def test_non_periods_are_not_recognised(label: str) -> None:
    assert parse_period_label(label) is None
