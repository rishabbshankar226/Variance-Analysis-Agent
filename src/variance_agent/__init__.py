"""Variance Analysis Agent."""

from .api import analyze_table, analyze_file, analyze_panel
from .analysis import analyze_rows
from .audit import build_audit_record
from .models import AnalysisConfig, AnalysisResult
from .version import __version__ as __version__

__all__ = ["AnalysisConfig", "AnalysisResult", "analyze_rows", "build_audit_record", "analyze_table", "analyze_file", "analyze_panel"]
