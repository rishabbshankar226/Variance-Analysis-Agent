"""Opted-in supplied comparisons and flat joins over the single-basis engine."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Mapping

from .analysis import analyze_rows, verify_result
from .audience import AudienceConfig, audience_config, validate_audience_config, effective_layout
from .audit import (build_audit_record, finalize_audience_record, audience_configuration,
                    validate_source_identity, comparison_details_record)
from .comparison import (basis_for_header, comparison_heading, display_outcome, extended_heading,
                         order_period_labels, parse_period_label, comparison_details)
from .json_types import JSONObject, JSONValue
from .limits import MAX_CELLS, MAX_ROWS
from .measures import absolute_cutoff, direction, format_measure, measure_kind, parse_measure_amount
from .models import AnalysisConfig, AnalysisResult, AnalyzedRow, ComparisonBasis, ComparisonDetails, MeasureKind
from .numeric import financial_context, ratio
from .parsing import is_missing, normalize_key, normalize_row
from .classification import infer_line_type
from .segments import SEGMENT_KEYS, read_segment
from .surprise import (SurpriseOptions, SurpriseStatistic, attach_statistics, verify_statistics,
                       statistic_record, statistics_configuration, render_statistics)
from .report import _pct, _safe_inline


@dataclass(frozen=True)
class UnavailableComparison:
    line_item: str
    measure: MeasureKind
    actual: Decimal
    reason: str
    segment: str = ""
    comparison_details: ComparisonDetails | None = None


@dataclass(frozen=True)
class ComparisonAnalysis:
    basis: ComparisonBasis
    result: AnalysisResult | None
    unavailable: tuple[UnavailableComparison, ...] = ()
    label: str | None = None


@dataclass(frozen=True)
class EstimateGap:
    line_item: str
    measure: MeasureKind
    estimate: Decimal
    consensus: Decimal
    variance: Decimal
    variance_percent: Decimal | None
    variance_bps: Decimal | None
    segment: str = ""


@dataclass(frozen=True)
class TableAnalysis:
    config: AudienceConfig
    comparisons: tuple[ComparisonAnalysis, ...]
    estimate_vs_consensus: tuple[EstimateGap, ...] = ()
    inferences: tuple[str, ...] = ()
    metric_order: tuple[tuple[str, str, MeasureKind], ...] = ()
    source_name: str | None = None
    source_sha256: str | None = None
    source_worksheet: str | None = None
    statistic_context: SurpriseOptions | None = None
    statistics: tuple[SurpriseStatistic, ...] = ()
    source_document: dict[str, object] | None = None
    source_transformations: dict[str, object] | None = None


def _canonical_rows(rows: list[dict[str, object]], raw_headers: tuple[str, ...], *, extended: bool = True) -> list[dict[str, object]]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Dataset contains no data rows.")
    if len(rows) > MAX_ROWS or sum(len(row) for row in rows) > MAX_CELLS:
        raise ValueError("Dataset exceeds the supported row or cell count.")
    canonical = []
    for row in rows:
        normalized = normalize_row(row)
        headers = {normalize_key(header): header for header in (raw_headers or tuple(row))}
        for key, original in headers.items() if extended else ():
            if key in {"est", "estimate"}:
                if original.strip().startswith("#") and key == "est":
                    normalized["estimator_count"] = normalized.pop(key, None)
                else:
                    raise ValueError(f"Column {original!r} could mean consensus or your own model; map or name it explicitly.")
        for key, target in {"low": "consensus_low", "high": "consensus_high", "std_dev": "dispersion",
                            "standard_deviation": "dispersion", "guide_low": "guidance_low",
                            "guide_high": "guidance_high"}.items() if extended else ():
            if key in normalized:
                if target in normalized:
                    raise ValueError(f"Columns {key} and {target} name the same field; map one explicitly.")
                normalized[target] = normalized.pop(key)
        canonical.append(normalized)
    return canonical


def _one_column(keys: list[str], candidates: list[str], name: str, *, required: bool = True) -> str | None:
    matches = [key for key in keys if key in candidates]
    if len(matches) > 1:
        raise ValueError(f"More than one {name} column found; map one explicitly: {', '.join(matches)}.")
    if not matches and required:
        raise ValueError(f"No {name} column found. Columns found: {', '.join(keys)}.")
    return matches[0] if matches else None


def _period_columns(keys: list[str], raw_headers: tuple[str, ...], *, extended: bool = True) -> tuple[list[str], dict[str, str]]:
    originals = {normalize_key(header): header for header in raw_headers}
    period_keys: dict[str, str] = {}
    for key in keys:
        original = originals.get(key, key.replace("_", " "))
        # Normalization loses the apostrophe: 3Q26 survives, Q3'26 needs its captured original.
        label = original.removesuffix(" Actual").removesuffix(" Actuals").strip()
        if parse_period_label(label, extended=extended) is not None:
            period_keys[label] = key
    if len(period_keys) < 2:
        return [], period_keys
    ordered = order_period_labels(list(period_keys), extended=extended)
    if ordered is None:
        raise ValueError(f"Could not order periods with mixed calendars, granularity, or duplicate labels: {', '.join(period_keys)}.")
    return ordered, period_keys


def _title(actual: str, previous: str) -> str | None:
    # Old parser labels retain their historical display, even under extended recognition.
    if parse_period_label(actual) is not None and parse_period_label(previous) is not None:
        return None
    current, prior = parse_period_label(actual, extended=True), parse_period_label(previous, extended=True)
    if current is None or prior is None or current[1] != "quarter" or prior[1] != "quarter":
        return None
    if current[0] - prior[0] == 1 and current[2] == prior[2]:
        return f"Prior Year ({previous})"
    if (current[0] * 4 + current[2]) - (prior[0] * 4 + prior[2]) == 1:
        return f"Prior Quarter ({previous})"
    return None


@financial_context()
def analyze_comparisons(
    rows: list[dict[str, object]], config: AnalysisConfig, bases: tuple[ComparisonBasis, ...], *,
    raw_headers: tuple[str, ...] = (), extended_headers: bool = True,
) -> TableAnalysis:
    """Analyze supplied bases separately. Missing cells are never replaced by zero."""
    if not bases or len(set(bases)) != len(bases) or not all(isinstance(b, ComparisonBasis) for b in bases):
        raise ValueError("Choose a nonempty list of distinct comparison bases.")
    cfg = audience_config(config, extended_headers=extended_headers)
    validate_audience_config(cfg)
    canonical = _canonical_rows(rows, raw_headers, extended=extended_headers)
    for row in canonical:
        if not extended_headers and "segment" in row:
            row["ignored_source_segment"] = row.pop("segment")
        segment, declared = read_segment(row, cfg)
        if declared:
            source = next(key for key in SEGMENT_KEYS if key in row)
            row["segment_source"] = source
            if source != "segment":
                del row[source]
            row["segment"] = segment
    keys = list(dict.fromkeys(key for row in canonical for key in row))
    actual_key = _one_column(keys, ["actual", "actual_amount", "actuals", "act", "actual_ytd", "actual_amt"], "Actual", required=False)
    original_headers = raw_headers or tuple(dict.fromkeys(k for row in rows for k in row))
    ordered, period_keys = _period_columns(keys, original_headers, extended=extended_headers)
    if actual_key is None and ordered:
        actual_key = period_keys[ordered[0]]
    if actual_key is None:
        raise ValueError("No Actual column found; map one explicitly.")
    line_key = _one_column(keys, ["line_item", "line", "item", "account", "account_name", "account_description", "category"], "Line Item")
    assert line_key is not None
    comparisons = []
    notes = []
    if len(bases) > 1:
        identities = set()
        for row in canonical:
            identity = (str(row.get(line_key, "")).strip().casefold(), str(row.get("segment", "")).strip().casefold(),
                        measure_kind(row.get("measure"), str(row.get(line_key, "Row"))))
            if identity in identities:
                raise ValueError(f"{row.get(line_key)}: comparison joins need a unique line item, segment, and measure.")
            identities.add(identity)
    for basis in bases:
        selected = [key for key in keys if basis_for_header(key, extended=extended_headers) is basis]
        comparison_key = _one_column(keys, selected, comparison_heading(basis, None), required=False)
        label = cfg.comparison_label if basis is ComparisonBasis.PRIOR_PERIOD else None
        title = None
        selected_cfg = replace(cfg, comparison_basis=basis, comparison_label=label, comparison_title=None)
        if comparison_key is None and basis is ComparisonBasis.PRIOR_PERIOD and ordered:
            comparison_key, label = period_keys[ordered[1]], ordered[1]
            title = _title(ordered[0], ordered[1])
            selected_cfg = replace(selected_cfg, comparison_label=label, actual_label=ordered[0], comparison_title=title)
            notes.append(f"Comparing {ordered[0]} against {label}; read periods newest first.")
        ranges = basis is ComparisonBasis.GUIDANCE and ("guidance_low" in keys or "guidance_high" in keys)
        if ranges and comparison_key is not None:
            raise ValueError("Guidance has both a point and a range; map the intended comparison explicitly.")
        if comparison_key is None and not ranges:
            raise ValueError(f"No {comparison_heading(basis, None)} column found. Columns found: {', '.join(keys)}.")
        available, unavailable = [], []
        for row in canonical:
            name = str(row.get(line_key, "")).strip()
            kind = measure_kind(row.get("measure"), name)
            absolute_cutoff(selected_cfg, kind, name)
            raw_actual = row.get(actual_key)
            actual = parse_measure_amount(raw_actual, kind=kind, config=selected_cfg, field="Actual", line_item=name)
            current = dict(row)
            # Remove other aliases for amounts: one selected amount per engine invocation.
            for key in ("budget", "budget_amount", "plan", "planned", "actual", "actual_amount", "actuals"):
                current.pop(key, None)
            current["line_item"], current["actual"] = name, raw_actual
            if line_key != "line_item":
                current.pop(line_key, None)
            value = row.get(comparison_key) if comparison_key is not None else None
            if ranges:
                low_raw, high_raw = row.get("guidance_low"), row.get("guidance_high")
                if is_missing(low_raw) != is_missing(high_raw):
                    raise ValueError(f"{name}: guidance range needs both low and high.")
                if not is_missing(low_raw):
                    low = parse_measure_amount(low_raw, kind=kind, config=selected_cfg, field="guidance low", line_item=name)
                    high = parse_measure_amount(high_raw, kind=kind, config=selected_cfg, field="guidance high", line_item=name)
                    if low > high:
                        raise ValueError(f"{name}: guidance low must not exceed high.")
                    midpoint = (low + high) / Decimal("2")
                    value = format(midpoint, "f") + "%" if kind is MeasureKind.PERCENT else midpoint
            if is_missing(value):
                if basis is not ComparisonBasis.CONSENSUS and len(bases) == 1:
                    raise ValueError(f"{name}: missing {comparison_heading(basis, None)} amount.")
                direction(row.get("better"), kind, infer_line_type(name)[0], name)
                unavailable.append(UnavailableComparison(name, kind, actual, f"N/A (No {basis.value.replace('_', ' ')})",
                                                         str(row.get("segment", "")),
                                                         comparison_details(current, actual, kind, selected_cfg)))
                continue
            current["budget"] = value
            available.append(current)
        result = analyze_rows(available, selected_cfg) if available else None
        comparisons.append(ComparisonAnalysis(basis, result, tuple(unavailable), label))
        notes.append(f"Comparing Actual against {comparison_heading(basis, label)}.")
    gaps = _estimate_gaps(tuple(comparisons))
    metric_order = tuple((str(row.get(line_key, "")).strip().casefold(), str(row.get("segment", "")).strip().casefold(),
                          measure_kind(row.get("measure"), str(row.get(line_key, "Row")))) for row in canonical)
    table = attach_statistics(TableAnalysis(cfg, tuple(comparisons), gaps, tuple(notes), metric_order))
    from .earnings import layout_note
    note = layout_note(table)
    return replace(table, inferences=(*table.inferences, note)) if note is not None else table


def _identity(row: AnalyzedRow) -> tuple[str, str, MeasureKind]:
    return (row.line_item.strip().casefold(), row.segment.casefold(), row.measure)


@financial_context()
def _estimate_gaps(comparisons: tuple[ComparisonAnalysis, ...]) -> tuple[EstimateGap, ...]:
    by_basis = {c.basis: c.result for c in comparisons}
    consensus, estimate = by_basis.get(ComparisonBasis.CONSENSUS), by_basis.get(ComparisonBasis.ESTIMATE)
    if consensus is None or estimate is None:
        return ()
    street = {_identity(row): row for row in consensus.rows}
    output = []
    for row in estimate.rows:
        match = street.get(_identity(row))
        if match is None:
            continue
        delta = row.budget - match.budget
        is_rate = row.measure is MeasureKind.PERCENT
        output.append(EstimateGap(row.line_item, row.measure, row.budget, match.budget, delta,
                                  ratio(delta, abs(match.budget)) if match.budget != 0 and not is_rate else None,
                                  delta * Decimal("100") if is_rate else None, row.segment))
    return tuple(output)


def _missing_record(row: UnavailableComparison) -> JSONObject:
    return {"line_item": row.line_item, "measure": str(row.measure), "segment": row.segment,
            "actual": format(row.actual, "f"), "comparison": None, "status": None, "display_label": None,
            "reason": row.reason, "comparison_details": comparison_details_record(row.line_item, row.comparison_details)}


def _gap_record(gap: EstimateGap) -> JSONObject:
    return {"line_item": gap.line_item, "segment": gap.segment, "measure": str(gap.measure),
            "estimate": format(gap.estimate, "f"), "consensus": format(gap.consensus, "f"),
            "variance": format(gap.variance, "f"),
            "variance_percent": None if gap.variance_percent is None else format(gap.variance_percent, "f"),
            "variance_bps": None if gap.variance_bps is None else format(gap.variance_bps, "f")}


def build_comparison_audit(
    table: TableAnalysis, *, source_name: str | None = None, source_sha256: str | None = None,
    schema_version: str | None = None, source_worksheet: str | None = None,
    transformations: Mapping[str, object] | None = None,
    source_document: Mapping[str, object] | None = None,
) -> JSONObject:
    if schema_version not in {None, "1.8"}:
        raise ValueError("Comparison sets and new comparisons require audit schema 1.8.")
    verify_comparisons(table)
    source_name = source_name if source_name is not None else table.source_name
    source_sha256 = source_sha256 if source_sha256 is not None else table.source_sha256
    source_worksheet = source_worksheet if source_worksheet is not None else table.source_worksheet
    source_document = source_document if source_document is not None else table.source_document
    transformations = transformations if transformations is not None else table.source_transformations
    validate_source_identity(source_name, source_sha256)
    source_sha256 = source_sha256.lower() if source_sha256 is not None else None
    records: list[JSONValue] = []
    for comparison in table.comparisons:
        if comparison.result is not None:
            child = build_audit_record(comparison.result, schema_version="1.8", source_name=source_name,
                                       source_sha256=source_sha256, source_worksheet=source_worksheet,
                                       transformations=transformations, source_document=source_document)
            child["unavailable_comparisons"] = [_missing_record(row) for row in comparison.unavailable]
            inferences = child.get("inferences")
            assert isinstance(inferences, list)
            inferences.extend(note for note in table.inferences if note not in inferences)
        else:
            child = {"schema_version": "1.8", "kind": "comparison_unavailable", "period": table.config.period,
                     "comparison": {"basis": str(comparison.basis), "label": comparison.label},
                     "source": {"name": source_name, "sha256": source_sha256},
                     "unavailable_comparisons": [_missing_record(row) for row in comparison.unavailable], "comparisons": [],
                     "audience": audience_configuration(replace(table.config, comparison_basis=comparison.basis))}
        if table.statistic_context is not None and comparison.basis is ComparisonBasis.CONSENSUS:
            _attach_statistic_record(child, table)
        finalize_audience_record(child)
        records.append(child)
    if len(records) == 1:
        record = records[0]
        assert isinstance(record, dict)
        return record
    root: JSONObject = {"schema_version": "1.8", "kind": "comparison_set", "period": table.config.period,
                        "source": {"name": source_name, "sha256": source_sha256}, "comparisons": records,
                        "comparison_order": [str(c.basis) for c in table.comparisons],
                        "estimate_vs_consensus": [_gap_record(gap) for gap in table.estimate_vs_consensus],
                        "inferences": list(table.inferences)}
    if table.statistic_context is not None:
        _attach_statistic_record(root, table)
    finalize_audience_record(root)
    return root


@financial_context()
def _render_comparisons(table: TableAnalysis) -> str:
    verify_comparisons(table)
    if effective_layout(table.config) == "earnings":
        from .earnings import render_earnings
        return render_earnings(table)
    if len(table.comparisons) == 1 and table.comparisons[0].result is not None and not table.comparisons[0].unavailable:
        from .report import render_markdown
        return render_markdown(table.comparisons[0].result)
    headings = ["Line Item", "Measure", "Segment"]
    maps = []
    order: dict[tuple[str, str, MeasureKind], tuple[str, MeasureKind, str]] = {}
    for comparison in table.comparisons:
        name = (extended_heading(comparison.result.config) if comparison.result is not None
                else comparison_heading(comparison.basis, comparison.label))
        headings.extend([f"{name}: Comparison", f"{name}: Actual", f"{name}: Variance", f"{name}: Surprise % / bps", f"{name}: Outcome"])
        mapping: dict[tuple[str, str, MeasureKind], AnalyzedRow | UnavailableComparison] = {}
        for row in comparison.result.rows if comparison.result is not None else ():
            key = _identity(row)
            mapping[key] = row
            order.setdefault(key, (row.line_item, row.measure, row.segment))
        for missing in comparison.unavailable:
            key = (missing.line_item.casefold(), missing.segment.casefold(), missing.measure)
            mapping[key] = missing
            order.setdefault(key, (missing.line_item, missing.measure, missing.segment))
        maps.append(mapping)
    if table.estimate_vs_consensus:
        headings.extend(["Estimate - Consensus", "Estimate - Consensus % / bps"])
    gaps = {(g.line_item.casefold(), g.segment.casefold(), g.measure): g for g in table.estimate_vs_consensus}
    lines = [f"# Comparison Review: {_safe_inline(table.config.period)}", "", "| " + " | ".join(_safe_inline(h) for h in headings) + " |",
             "|" + "|".join("---" for _ in headings) + "|"]
    segment_order = list(dict.fromkeys(key[1] for key in order))
    for key, (name, kind, segment) in sorted(order.items(), key=lambda item: segment_order.index(item[0][1])):
        cells = [_safe_inline(name), str(kind), _safe_inline(segment)]
        for comparison, mapping in zip(table.comparisons, maps, strict=True):
            entry = mapping.get(key)
            if entry is None:
                cells.extend([""] * 5)
            elif isinstance(entry, UnavailableComparison):
                cells.extend([entry.reason, format_measure(entry.actual, kind, table.config.currency), "", "", ""])
            else:
                delta = entry.variance_bps if kind is MeasureKind.PERCENT else entry.variance_dollars
                assert delta is not None
                cells.extend([format_measure(entry.budget, kind, table.config.currency),
                              format_measure(entry.actual, kind, table.config.currency),
                              format_measure(delta, kind, table.config.currency, variance=True),
                              format_measure(delta, kind, variance=True) if kind is MeasureKind.PERCENT else
                              _pct(entry.budget, entry.variance_dollars, entry.percent_label), display_outcome(entry, comparison.basis)])
        if table.estimate_vs_consensus:
            gap = gaps.get(key)
            cells.extend(["", ""] if gap is None else [format_measure(gap.variance, kind, table.config.currency),
                          format_measure(gap.variance_bps, kind, variance=True) if gap.variance_bps is not None
                          else _pct(gap.consensus, gap.variance, "N/A" if gap.consensus == 0 else None)])
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", *["- " + _safe_inline(note) for note in table.inferences], ""])
    return "\n".join(lines)


_LINE_ITEM_HEADERS = frozenset({"line_item", "account", "account_name", "account_description", "item", "category"})


def read_comparison_input(
    data: bytes, suffix: str, *, filename: str = "input", sheet: str | None = None, assisted: bool = False,
    column_mapping: Mapping[str, str] | None = None, per_share_lines: bool = False,
    metadata: dict[str, object] | None = None, hidden_rows: str | None = None,
) -> tuple[list[dict[str, object]], tuple[str, ...], str | None, tuple[str, ...]]:
    """Bounded captured-file intake for opt-in headers, retaining raw header identity."""
    import io
    from .parsing import load_input, load_json_value, _normalized_headers, _excel_loader
    from .excel import (HIDDEN_ROW_CHOICES, WorkbookFacts, cell_value, hidden_data_rows, hidden_rows_note,
                        hidden_rows_question, inspect_workbook, table_formulas_message)
    from .intake import _decode_text, _sniff_delimiter, _delimited_rows
    from .limits import MAX_INPUT_BYTES
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("Input exceeds the supported size (32 MiB).")
    if hidden_rows is not None:
        if hidden_rows not in HIDDEN_ROW_CHOICES:
            raise ValueError("hidden_rows must be include or exclude.")
        if suffix.lower() not in {".xlsx", ".xlsm"} or not (assisted or column_mapping):
            raise ValueError("hidden_rows requires assisted or mapped Excel input; strict intake reads every row as given.")
    if metadata is not None and column_mapping:
        metadata["transformations"] = {"column_mapping": dict(column_mapping)}
    if suffix.lower() == ".pdf":
        if not assisted:
            raise ValueError("PDF input requires --assisted.")
        if column_mapping:
            raise ValueError("PDF columns are selected by statement and period, not CSV column mappings.")
        from .intake import read_input_assisted, audit_transformations, CanonicalRole
        intake = read_input_assisted(data, suffix, filename=filename, sheet=sheet, per_share_lines=per_share_lines)
        if intake.has_fatal_errors or not intake.rows:
            raise ValueError(intake.fatal_error_message or "No comparable financial statement was found.")
        rows = []
        for pdf_row in intake.rows:
            row = normalize_row(pdf_row)
            row["Prior Period"] = row.pop("budget")
            rows.append(row)
        headers = tuple(dict.fromkeys(key for row in rows for key in row))
        if metadata is not None:
            metadata.update(intake_result=intake, document=intake.source_document(), transformations=audit_transformations(intake),
                            comparison_label=intake.comparison_label, comparison_basis=str(intake.comparison_basis),
                            actual_label=intake.column_mapping.get(CanonicalRole.ACTUAL))
        return rows, headers, intake.sheet_name, tuple([*intake.visible_transformations, *intake.reader_notes])
    notes: list[str] = []
    worksheet = None
    raw: list[list[object]] | None = None
    workbook_facts: WorkbookFacts | None = None
    worksheet_path = ""
    if suffix.lower() == ".csv" and not assisted and not column_mapping:
        parsed = load_input(data, suffix, source_name=filename, sheet=sheet)
        return parsed.rows, parsed.raw_headers, parsed.worksheet, ()
    if suffix.lower() == ".csv":
        if sheet is not None:
            raise ValueError("Worksheet selection requires Excel input.")
        text, encoding_note = _decode_text(data, filename) if assisted else (data.decode("utf-8-sig"), None)
        if encoding_note:
            notes.append(encoding_note)
        raw = _delimited_rows(text, _sniff_delimiter(text) if assisted else ",", filename)
    elif suffix.lower() in {".xlsx", ".xlsm"} and (assisted or column_mapping):
        workbook_facts = inspect_workbook(data)
        stored = workbook_facts.numbers
        with io.BytesIO(data) as source:
            workbook = _excel_loader()(source, read_only=True, data_only=True)
            try:
                if sheet is not None and sheet not in workbook.sheetnames:
                    raise ValueError(f"Worksheet {sheet!r} was not found; supply an exact sheet name.")
                ws = workbook.active if sheet is None else workbook[sheet]
                if ws is None:
                    raise ValueError("Excel input has no active worksheet.")
                ws.reset_dimensions()
                numbers = stored.get(ws._worksheet_path, {})
                raw = [[cell_value(cell, numbers=numbers, row=i, column=j) for j, cell in enumerate(cells, 1)]
                       for i, cells in enumerate(ws.iter_rows(), 1)]
                worksheet = ws.title
                worksheet_path = ws._worksheet_path
            finally:
                workbook.close()
    if raw is None and suffix.lower() == ".json" and column_mapping:
        payload = load_json_value(data.decode("utf-8-sig"))
        table = payload.get("rows", payload.get("data")) if isinstance(payload, dict) else payload
        if not isinstance(table, list) or not all(isinstance(row, dict) for row in table):
            raise ValueError("JSON input must contain row objects.")
        headers = tuple(dict.fromkeys(key for row in table for key in row))
        mapped_headers, ignored = _mapped_headers(headers, column_mapping)
        _normalized_headers(mapped_headers)
        renames = dict(zip(headers, mapped_headers, strict=True))
        output = [{renames[key]: value for key, value in row.items()} for row in table]
        return output, mapped_headers, None, ("Applied explicit column mapping.", *ignored)
    if raw is None:
        parsed = load_input(data, suffix, source_name=filename, sheet=sheet)
        rows, headers, worksheet = parsed.rows, parsed.raw_headers, parsed.worksheet
        if column_mapping:
            inverse = {source: target for target, source in column_mapping.items()}
            replacements = {normalize_key(source): target for source, target in inverse.items()}
            rows = [{replacements.get(k, k): v for k, v in row.items()} for row in rows]
            headers = tuple(inverse.get(header, header) for header in headers)
        return rows, headers, worksheet, tuple(notes)
    header_at = 0
    if assisted:
        candidates = []
        for index, record in enumerate(raw[:25]):
            labels = [str(v).strip() for v in record if v is not None]
            normalized = {normalize_key(v) for v in labels}
            normalized.update(role for role, source in (column_mapping or {}).items() if source in labels)
            if normalized & _LINE_ITEM_HEADERS:
                if normalized & {"actual", "actuals", "actual_amount", "act", "actual_ytd"} or sum(
                        parse_period_label(label, extended=True) is not None for label in labels) >= 2:
                    candidates.append(index)
        if not candidates:
            raise ValueError(f"Could not find a Line Item and Actual header in {filename!r}; map the columns explicitly.")
        header_at = candidates[0]
    if not raw:
        raise ValueError("Input contains no data.")
    headers = tuple("" if v is None else str(v).strip() for v in raw[header_at])
    line_items = [i for i, h in enumerate(headers) if normalize_key(h) in _LINE_ITEM_HEADERS]
    excluded: set[int] = set()
    hidden: list[tuple[int, str, bool]] = []
    if workbook_facts is not None and worksheet_path in workbook_facts.layouts:
        hidden = hidden_data_rows(workbook_facts.layouts[worksheet_path], raw, header_row=header_at + 1,
                                  line_item_column=line_items[0] if line_items else None)
        if hidden and hidden_rows == "exclude":
            excluded = {number for number, _, _ in hidden}
    if workbook_facts is not None and workbook_facts.may_have_unsaved_formulas(worksheet_path):
        # A formula Excel never calculated reads as blank; name it instead (R4).
        stop = table_formulas_message(
            workbook_facts, worksheet_path, filename, header_row=header_at + 1, headers=list(headers),
            rows={i + 1: raw[i] for i in range(header_at + 1, len(raw)) if i + 1 not in excluded},
            line_item_column=line_items[0] if line_items else None)
        if stop is not None:
            raise ValueError(stop)
    if hidden:
        # A file API run never prompts, so rows hidden in Excel need a declared choice (R3).
        if hidden_rows is None:
            raise ValueError(f"{hidden_rows_question(hidden)}\nChoose whether to count them "
                             "(hidden_rows='include' or 'exclude'; --hidden-rows on the command line).")
        notes.append(hidden_rows_note(hidden_rows, hidden))
    if metadata is not None:
        metadata["transformations"] = {"header_row_number": header_at + 1, "column_mapping": dict(column_mapping or {})}
    mapped_headers, ignored = _mapped_headers(headers, column_mapping or {})
    notes.extend(ignored)
    _normalized_headers(mapped_headers)  # collision, column, and header-text limits
    output = []
    for index, record in enumerate(raw[header_at + 1:], header_at + 2):
        if not record or all(v is None or v == "" for v in record) or index in excluded:
            continue
        if len(record) > len(headers) and any(v is not None and v != "" for v in record[len(headers):]):
            raise ValueError(f"Row {index}: populated cells appear beyond the header.")
        if len(record) != len(headers) and suffix.lower() == ".csv":
            raise ValueError(f"Row {index}: column count does not match header.")
        record = [*record, *([None] * max(0, len(headers) - len(record)))]
        if any(not header and value is not None and value != "" for header, value in zip(headers, record, strict=False)):
            raise ValueError(f"Row {index}: data appears under a blank header.")
        output.append({header: value for header, value in zip(mapped_headers, record, strict=False) if header})
    if header_at:
        notes.append(f"Read header row {header_at + 1}; skipped {header_at} title rows.")
    if column_mapping:
        notes.append("Applied the explicit column mapping.")
    return output, mapped_headers, worksheet, tuple(notes)


@financial_context()
def verify_comparisons(table: TableAnalysis) -> None:
    from .currencies import validate_currency
    from .limits import validate_text
    from .parsing import parse_decimal
    validate_audience_config(table.config)
    validate_currency(table.config.currency)
    validate_text(table.config.period, field="Period", nonblank=True)
    if not table.comparisons or len({c.basis for c in table.comparisons}) != len(table.comparisons):
        raise RuntimeError("Comparison list is empty or contains repeated bases.")
    for comparison in table.comparisons:
        if not isinstance(comparison.basis, ComparisonBasis):
            raise RuntimeError("Comparison basis is invalid.")
        if comparison.result is not None:
            verify_result(comparison.result)
            cfg = comparison.result.config
            if (cfg.comparison_basis, cfg.period, cfg.currency) != (comparison.basis, table.config.period, table.config.currency):
                raise RuntimeError("Comparison configuration mismatch.")
        if comparison.result is None and not comparison.unavailable:
            raise RuntimeError("A comparison needs analyzed or explicitly unavailable rows.")
        for absent in comparison.unavailable:
            validate_text(absent.line_item, field="Line Item", nonblank=True)
            validate_text(absent.segment, field="Segment")
            validate_text(absent.reason, field="Comparison availability reason", nonblank=True)
            if not isinstance(absent.measure, MeasureKind) or not isinstance(absent.actual, Decimal):
                raise RuntimeError("Unavailable comparison has invalid measure or amount.")
            parse_decimal(absent.actual, field="Actual", line_item=absent.line_item)
    verify_statistics(table)
    if table.estimate_vs_consensus != _estimate_gaps(table.comparisons):
        raise RuntimeError("Estimate against Consensus facts mismatch.")


def detect_comparison_bases(headers: tuple[str, ...]) -> tuple[ComparisonBasis, ...]:
    output = []
    for header in headers:
        key = normalize_key(header)
        basis = basis_for_header(key, extended=True)
        if key in {"guidance_low", "guidance_high", "guide_low", "guide_high"}:
            basis = ComparisonBasis.GUIDANCE
        if basis is not None and basis not in output:
            output.append(basis)
    periods = [header for header in headers if parse_period_label(header, extended=True) is not None]
    if len(periods) >= 2 and ComparisonBasis.PRIOR_PERIOD not in output:
        output.append(ComparisonBasis.PRIOR_PERIOD)
    return tuple(output)


def _mapped_headers(headers: tuple[str, ...], mapping: Mapping[str, str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """A chosen role suppresses competing aliases before normalized collisions are checked."""
    if any(source not in headers for source in mapping.values()):
        missing = next(source for source in mapping.values() if source not in headers)
        raise ValueError(f"Mapping file: source column {missing!r} was not found.")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Mapping file: one source column cannot supply multiple roles.")
    inverse = {source: role for role, source in mapping.items()}
    aliases = {"actual": {"actual", "actual_amount", "actuals", "act", "actual_ytd"},
               "segment": set(SEGMENT_KEYS),
               "line_item": {"line_item", "account_description", "account_name", "account", "category", "item"}}
    output, notes = [], []
    for header in headers:
        if header in inverse:
            role = inverse[header]
            output.append("Internal Estimate" if role == "estimate" else role)
            continue
        key = normalize_key(header)
        ignore = any(key in aliases.get(role, {role}) for role in mapping)
        basis = basis_for_header(key, extended=True)
        if basis is not None and str(basis) in mapping:
            ignore = True
        if "guidance" in mapping and key in {"guidance_low", "guidance_high", "guide_low", "guide_high"}:
            ignore = True
        if {"guidance_low", "guidance_high"} <= mapping.keys() and basis is ComparisonBasis.GUIDANCE:
            ignore = True
        if ignore:
            output.append("Ignored source " + header)
            notes.append(f"Ignored unselected comparison column {header!r} under the explicit mapping.")
        else:
            output.append(header)
    return tuple(output), tuple(notes)


def render_comparisons(table: TableAnalysis) -> str:
    return _render_comparisons(table) + render_statistics(table)


def _attach_statistic_record(record: JSONObject, table: TableAnalysis) -> None:
    from .audit import _canonical, sha256_bytes
    record["statistics"] = [statistic_record(stat) for stat in table.statistics]
    record["statistics_configuration"] = statistics_configuration(table)
    provenance = record.get("provenance")
    if isinstance(provenance, dict):
        provenance["configuration_sha256"] = sha256_bytes(_canonical({
            "base": provenance["configuration_sha256"], "statistics": record["statistics_configuration"]}))
