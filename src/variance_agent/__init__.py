"""Variance Analysis Agent."""

from .analysis import analyze_rows
from .audit import build_audit_record
from .models import AnalysisConfig, AnalysisResult
from .version import __version__ as __version__

__all__ = ["AnalysisConfig", "AnalysisResult", "analyze_rows", "build_audit_record"]
