"""Typed public surfaces; all data belongs to fictional HALV.FAKE."""
import hashlib
import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent import analyze_file, analyze_panel, analyze_table
from variance_agent.api import AudienceOptions, PanelOptions
from variance_agent.audience import AudienceConfig
from variance_agent.models import ComparisonBasis


def config(period: str = "3Q26") -> AudienceConfig:
    return AudienceConfig(period, Decimal("10"), Decimal(".02"))


def test_new_public_signatures_and_legacy_constructors() -> None:
    from variance_agent import AnalysisConfig, AnalysisResult, analyze_rows, build_audit_record
    assert str(inspect.signature(analyze_table)) == ("(rows: 'list[dict[str, object]]', "
        "config: 'AnalysisConfig', *, options: 'AudienceOptions | None' = None) -> 'TableAnalysis'")
    assert list(inspect.signature(analyze_file).parameters) == ["path", "config", "options"]
    assert list(inspect.signature(analyze_panel).parameters) == ["rows", "group_by", "options"]
    assert list(inspect.signature(AnalysisConfig).parameters) == ["period", "dollar_threshold", "percent_threshold",
                                                                             "type_map", "currency", "comparison_basis",
                                                                             "comparison_label"]
    assert list(inspect.signature(AnalysisResult).parameters) == ["config", "rows", "material_rows", "revenue", "expenses", "warnings"]
    assert list(inspect.signature(analyze_rows).parameters) == ["rows", "config"]
    assert list(inspect.signature(build_audit_record).parameters) == ["result", "source_name", "source_sha256",
                                                                                 "schema_version", "type_map_sha256", "source_worksheet",
                                                                                 "transformations", "source_document"]


def test_file_hash_and_memory_source(tmp_path: Path) -> None:
    payload = b"Line Item,Consensus,Actual,Type\nRevenue,100,110,Revenue\n"
    path = tmp_path / "HALV.FAKE.csv"
    path.write_bytes(payload)
    file = analyze_file(path, config())
    assert file.source_sha256 == hashlib.sha256(payload).hexdigest()
    assert file.source_name == path.name
    memory = analyze_table([{"Line Item": "Revenue", "Consensus": "100", "Actual": "110", "Type": "Revenue"}], config())
    assert memory.source_sha256 is None
    assert file.comparisons[0].result.rows == memory.comparisons[0].result.rows


def test_basis_needs_explicit_choice_when_ambiguous() -> None:
    rows = [{"Line Item": "Revenue", "Consensus": "100", "Model": "101", "Actual": "110"}]
    with pytest.raises(ValueError, match="choose.*comparison"):
        analyze_table(rows, config())
    table = analyze_table(rows, config(), options=AudienceOptions(bases=(ComparisonBasis.CONSENSUS, ComparisonBasis.ESTIMATE)))
    assert len(table.comparisons) == 2


def test_exact_amounts_and_whole_table_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [{"Line Item": "Revenue", "Consensus": "100", "Actual": 1.1}]
    with pytest.raises(ValueError, match="float"):
        analyze_table(rows, config())
    import variance_agent.api as api
    monkeypatch.setattr(api, "MAX_ROWS", 1)
    with pytest.raises(ValueError, match="row"):
        analyze_table(rows * 2, config())


def test_panel_limits_are_global(monkeypatch: pytest.MonkeyPatch) -> None:
    import variance_agent.api as api
    monkeypatch.setattr(api, "MAX_CELLS", 5)
    rows = [{"Ticker": ticker, "Line Item": "Revenue", "Consensus": "100", "Actual": "110"}
            for ticker in ("HALV.FAKE", "CORD.FAKE")]
    with pytest.raises(ValueError, match="cell"):
        analyze_panel(rows, group_by=("Ticker",), options=PanelOptions(config=config()))


def test_auxiliary_text_nesting_and_column_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    import variance_agent.api as api
    row = {"Line Item": "Revenue", "Consensus": "100", "Actual": "110"}
    monkeypatch.setattr(api, "MAX_COLUMNS", 2)
    with pytest.raises(ValueError, match="column"):
        analyze_table([row], config())
    monkeypatch.setattr(api, "MAX_COLUMNS", 256)
    monkeypatch.setattr(api, "MAX_JSON_DEPTH", 1)
    with pytest.raises(ValueError, match="nesting"):
        analyze_table([{**row, "metadata": {"a": {"b": "c"}}}], config())
    monkeypatch.setattr(api, "MAX_JSON_DEPTH", 128)
    with pytest.raises(ValueError, match="text length"):
        analyze_table([{**row, "metadata": "x" * (128 * 1024 + 1)}], config())
    with pytest.raises(ValueError, match="numeric length"):
        analyze_table([{**row, "Actual": "1" * 4097}], config())


def test_file_audit_uses_captured_provenance(tmp_path: Path) -> None:
    from variance_agent.comparisons import build_comparison_audit
    path = tmp_path / "HALV.FAKE.csv"
    path.write_text("Line Item,Consensus,Actual,Type\nRevenue,100,110,Revenue\n")
    table = analyze_file(path, config())
    record = build_comparison_audit(table)
    assert record["source"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["source"]["name"] == path.name


def test_new_signatures_pin_keyword_only_defaults() -> None:
    assert str(inspect.signature(analyze_file)) == (
        "(path: 'str | Path', config: 'AnalysisConfig', *, options: 'AudienceOptions | None' = None) -> 'TableAnalysis'")
    assert str(inspect.signature(analyze_panel)) == (
        "(rows: 'list[dict[str, object]]', *, group_by: 'tuple[str, ...]', options: 'PanelOptions') -> 'BatchResult'")


def test_public_type_annotations_resolve() -> None:
    from typing import get_type_hints
    from variance_agent.panel import BatchResult
    assert get_type_hints(analyze_panel)["return"] is BatchResult
    assert get_type_hints(analyze_file)["return"].__name__ == "TableAnalysis"
    assert get_type_hints(analyze_table)["return"].__name__ == "TableAnalysis"
