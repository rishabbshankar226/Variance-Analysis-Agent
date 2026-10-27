"""Fictional files for the new readers (docs/analysts/PLAN.md R13-R17). Every name and figure is invented."""

from __future__ import annotations

# Ines (risk): exposures against limits by desk, each limit a Max or a Min, buffers where declared.
INES_LIMITS = """Line Item,Actual,Limit,Limit Kind,Buffer
Desk A gross exposure,480,500,Max,25
Desk B gross exposure,510,500,Max,25
Desk C liquidity reserve,95,100,Min,
Desk D liquidity reserve,100,100,Min,10
Desk E net exposure,300,500,Max,
"""

# Theo (asset management): fund returns against benchmark returns, and fees against budget-like benchmarks.
THEO_BENCHMARK = """Line Item,Actual,Benchmark,Better,Tolerance,Measure
Fund return,7.25%,6.80%,Higher,0.10,Percent
Tracking fund return,5.00%,5.05%,Higher,0.05,Percent
Management fee rate,0.82%,0.80%,Lower,,Percent
"""

# Marcus (portfolio manager): holdings' actual weights against target weights.
MARCUS_TARGETS = """Line Item,Actual,Target,Tolerance,Measure
NORDVIK.FAKE,12.40%,12.00%,0.25,Percent
HALVORSEN.FAKE,7.90%,8.00%,0.25,Percent
OSTRAVA.FAKE,5.00%,6.00%,0.25,Percent
"""

# Marcus (portfolio manager): the book's holdings and a consensus panel for them (R18).
MARCUS_HOLDINGS = """Ticker,Weight
NORDVIK.FAKE,12.40%
HALVORSEN.FAKE,7.90%
OSTRAVA.FAKE,5.00%
BRAVIK.FAKE,3.00%
"""

MARCUS_PANEL = """Ticker,Line Item,Actual,Consensus,Measure,Better
NORDVIK.FAKE,Diluted EPS,1.25,1.10,Per Share,Higher
NORDVIK.FAKE,Revenue,500,480,Currency,Higher
HALVORSEN.FAKE,Diluted EPS,0.80,0.80,Per Share,Higher
OSTRAVA.FAKE,Diluted EPS,0.40,0.55,Per Share,Higher
TROLL.FAKE,Diluted EPS,2.00,1.90,Per Share,Higher
"""
