"""Shell adapter for the offline panel API; never prompts or emits a giant report."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sys

from .api import AudienceOptions, PanelOptions, analyze_panel
from .audience import AudienceConfig, NEW_BASES
from .audit import sha256_bytes
from .cli import Arguments, _parse_type_map
from .comparison import parse_compare_to
from .comparisons import read_comparison_input
from .limits import display_text
from .measures import metric_inferences
from .long_output import errors_csv, long_csv, long_jsonl
from .mapping import load_mapping
from .surprise import load_history, SurpriseOptions
from .output import write_text_outputs
from .parsing import normalize_key, normalize_row, parse_decimal, read_input_bytes


def run_panel(args: Arguments) -> int:
    assert args.input is not None and args.group_by is not None
    assert args.dollar_threshold is not None and args.percent_threshold is not None
    if args.output or args.audit_json or args.xlsx or args.check_only or args.commentary:
        raise ValueError("--group-by uses long outputs and errors output; report, audit, workbook and check-only flags are unsupported.")
    if not (args.long_output or args.long_output_jsonl) or not args.errors_output:
        raise ValueError("--group-by requires --long-output or --long-output-jsonl, plus --errors-output.")
    if "period" in [normalize_key(key) for key in args.group_by.split(",")] and args.period is not None:
        raise ValueError("A Period group key cannot be combined with --period.")
    source = Path(args.input)
    data = read_input_bytes(source)
    mapping = load_mapping(read_input_bytes(args.mapping)) if args.mapping else None
    bases = tuple(parse_compare_to(value) for value in args.compare_to.split(",")) if args.compare_to else ()
    if not bases and mapping is not None:
        bases = mapping.comparison_bases or ((mapping.comparison_basis,) if mapping.comparison_basis is not None else ())
    columns = dict(mapping.column_mapping) if mapping else {}
    if "budget" in columns and len(bases) == 1:
        columns[str(bases[0])] = columns.pop("budget")
    rows, headers, _, notes = read_comparison_input(data, source.suffix, filename=source.name, sheet=args.sheet,
                                                   assisted=args.assisted, column_mapping=columns or None)
    # Restore raw header identities (# Est. versus Est.) before the public table API.
    originals = {normalize_key(header): header for header in headers}
    rows = [{originals.get(key, key): value for key, value in row.items()} for row in rows]
    if mapping is not None and mapping.better_directions:
        for row in rows:
            normalized = normalize_row(row)
            name = str(normalized.get("line_item", ""))
            if name in mapping.better_directions:
                for key in [key for key in row if normalize_key(key) == "better"]:
                    row.pop(key)
                row["better"] = mapping.better_directions[name]
    def threshold(name: str) -> Decimal | None:
        explicit = getattr(args, name, None)
        if isinstance(explicit, Decimal):
            return explicit
        value = (mapping.measure_options or {}).get(name) if mapping is not None else None
        return parse_decimal(value, field=name, line_item="Mapping file") if value is not None else None
    percent_values = args.percent_values
    if percent_values is None and mapping is not None:
        percent_values = (mapping.measure_options or {}).get("percent_values")
    cfg = AudienceConfig(args.period or "", args.dollar_threshold, args.percent_threshold / Decimal("100"),
                         currency=args.currency, type_map=_parse_type_map(read_input_bytes(args.type_map)) if args.type_map else {},
                         per_share_threshold=threshold("per_share_threshold"), bps_threshold=threshold("bps_threshold"),
                         count_threshold=threshold("count_threshold"), percent_values=percent_values, extended_headers=True,
                         preset=args.preset, layout=args.layout, per_share_lines=args.per_share_lines,
                         headline_items=tuple(args.headline or ()))
    batch = analyze_panel(rows, group_by=tuple(args.group_by.split(",")), options=PanelOptions(config=cfg,
                           audience=AudienceOptions(bases=bases, extended_headers=(args.preset != "fpa" or mapping is not None
                               or any(basis in NEW_BASES for basis in bases)), surprise=(SurpriseOptions(
                               history=load_history(args.history) if args.history else None,
                               window=args.surprise_window, entity=args.entity)
                               if args.history or args.entity or args.surprise_window != 8 else None))))
    batch = replace(batch, source_sha256=sha256_bytes(data), source_name=source.name)
    outputs: dict[Path, str | bytes] = {Path(args.errors_output): errors_csv(batch)}
    if args.long_output:
        outputs[Path(args.long_output)] = long_csv(batch)
    if args.long_output_jsonl:
        outputs[Path(args.long_output_jsonl)] = long_jsonl(batch)
    write_text_outputs(outputs)
    failures = sum(group.error is not None for group in batch.groups)
    all_notes = list(notes)
    for group in batch.groups:
        if group.analysis is not None:
            all_notes.extend(group.analysis.inferences)
            for comparison in group.analysis.comparisons:
                if comparison.result is not None:
                    all_notes.extend(metric_inferences(comparison.result.rows, comparison.result.config))
    for note in dict.fromkeys(all_notes):
        print("[panel intake] " + display_text(note), file=sys.stderr)
    print(f"Panel: {len(batch.groups) - failures} successful groups; {failures} failed groups.", file=sys.stderr)
    return 3 if failures else 0
