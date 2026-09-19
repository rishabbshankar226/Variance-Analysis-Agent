"""Variance Analysis Agent."""

from .analysis import analyze_rows
from .audit import build_audit_record
from .models import AnalysisConfig, AnalysisResult

__all__ = ["AnalysisConfig", "AnalysisResult", "analyze_rows", "build_audit_record"]
__version__ = "0.2.0"
