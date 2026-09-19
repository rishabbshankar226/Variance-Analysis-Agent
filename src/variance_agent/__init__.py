"""Variance Analysis Agent."""

from .analysis import analyze_rows
from .models import AnalysisConfig, AnalysisResult

__all__ = ["AnalysisConfig", "AnalysisResult", "analyze_rows"]
__version__ = "0.1.0"
