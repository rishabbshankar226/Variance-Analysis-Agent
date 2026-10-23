"""Stable, offline table/file/panel APIs. Financial inputs use Decimal or exact text."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path

from .audience import audience_config, effective_per_share_lines, AudienceConfig
from .audit import sha256_bytes
from .comparisons import TableAnalysis, analyze_comparisons, detect_comparison_bases, read_comparison_input
from .limits import MAX_CELLS, MAX_COLUMNS, MAX_JSON_DEPTH, MAX_ROWS, validate_text
from .models import AnalysisConfig, ComparisonBasis
from .parsing import normalize_row, read_input_bytes

from .panel import BatchResult
from .surprise import SurpriseOptions, attach_statistics, infer_entity, validate_options


@dataclass(frozen=True, kw_only=True)
class AudienceOptions:
    """Explicit comparison order and file layout; no threshold defaults."""
    bases: tuple[ComparisonBasis, ...] = ()
    extended_headers: bool = True
    assisted: bool = False
    sheet: str | None = None
    column_mapping: dict[str, str] = field(default_factory=dict)
    surprise: SurpriseOptions | None = None
    preset: str | None = None
    layout: str | None = None
    per_share_lines: bool | None = None
    headline_items: tuple[str, ...] | None = None
    better_directions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class PanelOptions:
    """An empty config.period is required when Period is a grouping key."""
    config: AnalysisConfig
    audience: AudienceOptions = field(default_factory=AudienceOptions)


def validate_table(rows: list[dict[str, object]]) -> None:
    """Apply whole-capture limits before partitioning; never reset caps per group."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("Dataset contains no data rows.")
    if len(rows) > MAX_ROWS:
        raise ValueError("Dataset exceeds the supported row count.")
    cells = 0
    columns: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not all(isinstance(key, str) for key in row):
            raise ValueError("Each table row must be an object with text column names.")
        cells += len(row)
        columns.update(row)
        if cells > MAX_CELLS:
            raise ValueError("Dataset exceeds the supported cell count.")
        if len(columns) > MAX_COLUMNS:
            raise ValueError("Dataset exceeds the supported column count.")
        stack: list[tuple[object, int]] = [(row, 0)]
        while stack:
            value, depth = stack.pop()
            if depth > MAX_JSON_DEPTH:
                raise ValueError("Dataset exceeds the supported nesting depth.")
            if isinstance(value, str):
                validate_text(value, field="Table value")
            elif isinstance(value, dict):
                for key, item in value.items():
                    validate_text(key, field="Table column")
                    stack.append((item, depth + 1))
            elif isinstance(value, (list, tuple)):
                stack.extend((item, depth + 1) for item in value)
            elif value is not None and not isinstance(value, (bool, int, float, Decimal)):
                raise ValueError("Table values must be text, exact numbers, or JSON values.")


def _analyze_table(rows: list[dict[str, object]], config: AnalysisConfig, options: AudienceOptions,
                   *, raw_headers: tuple[str, ...] = ()) -> TableAnalysis:
    if any(isinstance(value, float) for row in rows for value in row.values()):
        raise ValueError("Financial table values cannot be float; supply Decimal or exact numeric text.")
    headers = raw_headers or tuple(dict.fromkeys(key for row in rows for key in row))
    bases = options.bases
    if not bases and not options.extended_headers:
        bases = (config.comparison_basis,)
    if not bases:
        bases = detect_comparison_bases(headers)
        if len(bases) > 1:
            raise ValueError("Multiple bases found; choose the comparison explicitly with AudienceOptions.bases.")
        if not bases:
            bases = (ComparisonBasis.PRIOR_PERIOD,)
    cfg = _configuration(config, options)
    if options.better_directions:
        transformed = []
        for raw in rows:
            row = normalize_row(raw)
            name = str(row.get("line_item", ""))
            if name in options.better_directions:
                row["better"] = options.better_directions[name]
            transformed.append(row)
        rows = transformed
    table = analyze_comparisons(rows, cfg, bases, raw_headers=headers, extended_headers=options.extended_headers)
    if options.surprise is not None:
        selected = options.surprise
        if selected.entity is None:
            selected = replace(selected, entity=infer_entity(rows))
        table = attach_statistics(table, selected)
    return table


def analyze_table(rows: list[dict[str, object]], config: AnalysisConfig, *,
                  options: AudienceOptions | None = None) -> TableAnalysis:
    """Analyze a table with explicit new-header recognition and no source-byte claim."""
    validate_table(rows)
    selected = options or AudienceOptions()
    if selected.column_mapping:
        from .comparisons import _mapped_headers
        headers = tuple(dict.fromkeys(key for row in rows for key in row))
        mapped, _ = _mapped_headers(headers, selected.column_mapping)
        renames = dict(zip(headers, mapped, strict=True))
        rows = [{renames[key]: value for key, value in row.items()} for row in rows]
    return _analyze_table(rows, config, selected)


def analyze_file(path: str | Path, config: AnalysisConfig, *, options: AudienceOptions | None = None) -> TableAnalysis:
    """Capture a bounded file once; provenance hashes exactly those input bytes."""
    selected = options or AudienceOptions()
    source = Path(path)
    data = read_input_bytes(source)
    cfg = _configuration(config, selected)
    metadata: dict[str, object] = {}
    rows, headers, worksheet, notes = read_comparison_input(data, source.suffix, filename=source.name,
                                                           sheet=selected.sheet, assisted=selected.assisted,
                                                           column_mapping=selected.column_mapping or None,
                                                           per_share_lines=effective_per_share_lines(cfg), metadata=metadata)
    if isinstance(metadata.get("comparison_label"), str):
        cfg = replace(cfg, comparison_label=str(metadata["comparison_label"]))
    if isinstance(metadata.get("actual_label"), str):
        cfg = replace(cfg, actual_label=str(metadata["actual_label"]))
    validate_table(rows)
    table = _analyze_table(rows, cfg, selected, raw_headers=headers)
    document = metadata.get("document")
    transformations = metadata.get("transformations")
    return replace(table, source_name=source.name, source_sha256=sha256_bytes(data), source_worksheet=worksheet,
                   inferences=(*table.inferences, *notes),
                   source_document=document if isinstance(document, dict) else None,
                   source_transformations=transformations if isinstance(transformations, dict) else None)


def analyze_panel(rows: list[dict[str, object]], *, group_by: tuple[str, ...], options: PanelOptions) -> BatchResult:
    """Validate the capture, then isolate data errors within each declared group."""
    from .panel import analyze_groups
    validate_table(rows)
    if options.audience.surprise is not None:
        validate_options(options.audience.surprise)
    if options.audience.column_mapping:
        from .comparisons import _mapped_headers
        headers = tuple(dict.fromkeys(key for row in rows for key in row))
        mapped, _ = _mapped_headers(headers, options.audience.column_mapping)
        renames = dict(zip(headers, mapped, strict=True))
        rows = [{renames[key]: value for key, value in row.items()} for row in rows]
    # normalize_row refuses duplicate normalized fields before grouping.
    normalized = [normalize_row(row) for row in rows]
    return analyze_groups(rows, normalized, group_by, options)


def _configuration(config: AnalysisConfig, options: AudienceOptions) -> AudienceConfig:
    cfg = audience_config(config)
    if options.preset is not None:
        cfg = replace(cfg, preset=options.preset)
    if options.layout is not None:
        cfg = replace(cfg, layout=options.layout)
    if options.per_share_lines is not None:
        cfg = replace(cfg, per_share_lines=options.per_share_lines)
    if options.headline_items is not None:
        cfg = replace(cfg, headline_items=options.headline_items)
    return cfg
