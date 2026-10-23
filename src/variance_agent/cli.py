from __future__ import annotations

import argparse
import csv
import os
import sys
import unicodedata
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from zipfile import BadZipFile

from .audience import AudienceConfig, NEW_BASES, is_audience_result
from .measures import metric_inferences
from .analysis import analyze_rows
from .classification import explicit_line_type
from .audit import (SUPPORTED_SCHEMA_VERSIONS,
                    build_audit_record, sha256_bytes, serialize_audit_json)
from .currencies import CURRENCY_SYMBOLS
from .models import AnalysisConfig, ComparisonBasis, LineType
from .comparison import (
    FORECAST_SYNONYMS,
    PRIOR_PERIOD_SYNONYMS,
    order_period_labels,
    parse_compare_to,
    parse_period_label,
    select_strict_comparison,
)
from .parsing import normalize_row, load_input, load_json_value, parse_decimal, read_input_bytes, validate_input_format
from .output import write_text_outputs
from .numeric import financial_context
from .report import _safe_inline, render_markdown
from .xlsx import render_xlsx
from .limits import display_text

if TYPE_CHECKING:
    from .intake import IntakeResult


COMPARE_TO_HINT = "Rerun with --compare-to budget|forecast|prior-period."


def _year_columns_hint(rows: list[dict[str, object]]) -> str | None:
    """Point strict-mode users at assisted intake when the comparison lives in year-only columns."""
    labels = {key.replace("_", " ").upper() for row in rows for key in row}
    ordered = order_period_labels([label for label in labels if parse_period_label(label) is not None])
    if ordered is None or len(ordered) < 2:
        return None
    return (f"This file has year columns ({', '.join(ordered)}); rerun with --assisted to compare "
            "the newest year against the one before it (add --compare-to prior-period to require that).")


def _intake_error(intake_res: IntakeResult) -> str:
    message = intake_res.fatal_error_message or "Could not read input."
    if intake_res.comparison_choices:
        # Chat offers chips for this choice; the CLI names the flag that makes it.
        message = f"{message} {COMPARE_TO_HINT}"
    return message


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"


def _unit_name(scale: Decimal) -> str:
    if scale == Decimal("1000"):
        return "thousands"
    if scale == Decimal("1000000"):
        return "millions"
    return f"units of {scale}"


class Arguments(Protocol):
    input: str | None
    period: str | None
    dollar_threshold: Decimal | None
    percent_threshold: Decimal | None
    type_map: str | None
    check_only: bool
    sheet: str | None
    currency: str
    audit_schema_version: str
    output: str | None
    audit_json: str | None
    xlsx: str | None
    chat: bool
    hosted: bool
    no_browser: bool
    commentary: bool
    assisted: bool
    mapping: str | None
    compare_to: str | None
    preset: str
    per_share_threshold: Decimal | None
    count_threshold: Decimal | None
    bps_threshold: Decimal | None
    percent_values: str | None
    group_by: str | None
    long_output: str | None
    long_output_jsonl: str | None
    errors_output: str | None


def _decimal(text: str) -> Decimal:
    if any(symbol in text for symbol in CURRENCY_SYMBOLS.values()):
        raise argparse.ArgumentTypeError(
            "Thresholds must be numbers without currency symbols; select --currency separately."
        )
    try:
        return parse_decimal(text, field="threshold", line_item="Materiality")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid number: {text}") from exc


def _load_type_map(path: str | None) -> dict[str, LineType]:
    if not path:
        return {}
    return _parse_type_map(read_input_bytes(path))


def _parse_type_map(data: bytes) -> dict[str, LineType]:
    payload = load_json_value(data.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Type map must be a JSON object of line item -> Revenue/Expense/Unclassified.")
    output: dict[str, LineType] = {}
    for item, value in payload.items():
        line_type = explicit_line_type(value)
        if line_type is not None:
            output[item] = line_type
        elif str(value).strip().lower() == "unclassified":
            output[item] = LineType.UNCLASSIFIED
        else:
            raise ValueError(
                f"Type map value for {item!r} must be Revenue, Expense or Unclassified."
            )
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="variance-agent",
        description="Generate an auditable FP&A variance report from CSV, JSON, or Excel data.",
    )
    parser.add_argument("input", nargs="?", default=None, help="Input CSV, JSON, XLSX, or XLSM file, or a PDF filing with --assisted.")
    parser.add_argument("--group-by", help="Panel keys, for example Ticker,Period. Mixed success exits 3; global errors exit 2.")
    parser.add_argument("--long-output", help="Write deterministic exact-number CSV.")
    parser.add_argument("--long-output-jsonl", help="Write deterministic exact-number JSON Lines.")
    parser.add_argument("--errors-output", help="Write one CSV error row per failed panel group (required with --group-by).")
    parser.add_argument("--period", help="Reporting period shown in the report.")
    parser.add_argument(
        "--dollar-threshold",
        type=_decimal,
        help="Absolute dollar materiality threshold. Uses strict > semantics.",
    )
    parser.add_argument(
        "--percent-threshold",
        type=_decimal,
        help="Percentage threshold as a percent number (for example, 5 for 5%%).",
    )
    parser.add_argument("--type-map", help="Optional JSON mapping of line item to Revenue/Expense.")
    parser.add_argument("--check-only", action="store_true",
                        help="Validate/analyze input and print a summary without writing outputs.")
    parser.add_argument("--sheet", help="Exact Excel worksheet name (default: active worksheet), or the statement to read from a PDF.")
    parser.add_argument("--currency", type=str.upper, choices=tuple(CURRENCY_SYMBOLS), default="USD",
                        help="Reporting currency (default USD); conflicting amounts are rejected.")
    parser.add_argument("--audit-schema-version", choices=SUPPORTED_SCHEMA_VERSIONS,
                        default=None, help="Audit JSON format version (legacy 1.7; explicit measures 1.8).")
    parser.add_argument("-o", "--output", help="Write Markdown report to this path.")
    parser.add_argument("--xlsx", help="Write a formatted Excel workbook to this path.")
    parser.add_argument(
        "--audit-json",
        help="Write a machine-readable audit/agent-context record with source provenance.",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Launch the interactive chatbot UI in your browser.",
    )
    parser.add_argument(
        "--hosted",
        action="store_true",
        help="With --chat: serve on 0.0.0.0:$PORT for a hosting platform, without "
             "opening a browser or writing exports to server paths.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="With --chat: print the local URL instead of opening the system browser.",
    )
    parser.add_argument(
        "--commentary",
        action="store_true",
        help="Include verified deterministic executive commentary in the Markdown report.",
    )
    parser.add_argument(
        "--assisted",
        action="store_true",
        help="Enable assisted file intake (detect header rows, map column synonyms, and convert accounting dashes).",
    )
    parser.add_argument(
        "--mapping",
        help="Path to saved layout mapping JSON file.",
    )
    parser.add_argument(
        "--compare-to",
        type=_comparison_argument,
        help="Comparison basis or comma list: budget, forecast, prior-period, consensus, estimate, guidance.",
    )
    parser.add_argument("--preset", choices=("fpa", "earnings", "quant"), default="fpa",
                        help="Header recognition: fpa preserves defaults; earnings/quant opt into new headers.")
    for flag in ("per-share-threshold", "count-threshold", "bps-threshold"):
        parser.add_argument("--" + flag, type=_decimal, help="Required absolute cutoff for its measure; strict >.")
    parser.add_argument("--percent-values", choices=("points", "fractions"), help="Interpret bare Percent values explicitly.")
    return parser


def _fold(path: Path) -> str:
    """Case- and Unicode-form-insensitive spelling: macOS and Windows treat these as one file."""
    return unicodedata.normalize("NFC", str(path.resolve())).casefold()


def _same_path(first: Path, second: Path) -> bool:
    return _fold(first) == _fold(second) or (
        first.exists() and second.exists() and first.samefile(second)
    )


def _validate_output_paths(args: Arguments) -> None:
    assert args.input is not None
    inputs = [Path(args.input)]
    if args.type_map:
        inputs.append(Path(args.type_map))
    mapping_arg = getattr(args, "mapping", None)
    if isinstance(mapping_arg, str) and mapping_arg:
        inputs.append(Path(mapping_arg))
    outputs = [Path(value) for value in (args.output, args.audit_json, args.xlsx,
               getattr(args, "long_output", None), getattr(args, "long_output_jsonl", None),
               getattr(args, "errors_output", None)) if value]
    for index, output in enumerate(outputs):
        if any(_same_path(output, other) for other in inputs + outputs[:index]):
            raise ValueError(
                "Input, type-map, report, audit, and workbook output paths must be distinct."
            )


@financial_context()
def _run(args: Arguments) -> int:
    if args.chat:
        if args.check_only or args.output or args.audit_json or args.xlsx:
            raise ValueError(
                "--chat cannot be combined with --check-only, --output, --audit-json, or --xlsx."
            )
        from .chat.server import run_chat_server
        # Hosting is asked for (--hosted) or announced by the platform (Render sets RENDER). A
        # stray PORT variable alone must not expose a local chat on every network interface.
        if args.hosted or "RENDER" in os.environ:
            port_text = os.environ.get("PORT", "10000")
            if not (port_text.isascii() and port_text.isdigit() and 0 < int(port_text) < 65536):
                raise ValueError(f"PORT must be a port number between 1 and 65535, not {port_text!r}.")
            return run_chat_server(
                host="0.0.0.0", port=int(port_text),
                initial_input=args.input, initial_sheet=args.sheet,
                open_browser=False, hosted=True,
            )
        return run_chat_server(initial_input=args.input, initial_sheet=args.sheet,
                               open_browser=not args.no_browser)

    assert args.input is not None
    if args.group_by:
        from .panel_cli import run_panel
        _validate_output_paths(args)
        return run_panel(args)
    if args.errors_output:
        raise ValueError("--errors-output requires --group-by.")
    assert args.period is not None
    assert args.dollar_threshold is not None
    assert args.percent_threshold is not None
    if args.check_only and (args.output or args.audit_json or args.xlsx):
        raise ValueError("--check-only cannot be combined with --output, --audit-json, or --xlsx.")
    _validate_output_paths(args)
    input_path = Path(args.input)
    is_pdf = input_path.suffix.lower() == ".pdf"
    if args.sheet is not None and input_path.suffix.lower() not in {".xlsx", ".xlsm"} and not is_pdf:
        raise ValueError("--sheet requires XLSX or XLSM input.")
    validate_input_format(input_path.suffix, assisted=bool(getattr(args, "assisted", False)))
    # Capture each input once, then use exactly those bytes for parsing and hashes.
    source_bytes = read_input_bytes(input_path)
    type_map_bytes = read_input_bytes(args.type_map) if args.type_map else None
    source_hash = sha256_bytes(source_bytes) if args.audit_json else None

    mapping_obj = None
    intake_res = None

    requested = tuple(parse_compare_to(value) for value in args.compare_to.split(",")) if args.compare_to else ()
    mapping_arg = getattr(args, "mapping", None)
    if isinstance(mapping_arg, str) and mapping_arg:
        from .mapping import load_mapping
        mapping_obj = load_mapping(read_input_bytes(mapping_arg))
    if not requested and mapping_obj is not None and mapping_obj.comparison_bases:
        requested = mapping_obj.comparison_bases
    if not requested and mapping_obj is not None and mapping_obj.comparison_basis is not None:
        requested = (mapping_obj.comparison_basis,)
    mapped_segment = mapping_obj is not None and "segment" in mapping_obj.column_mapping
    if (len(requested) > 1 or any(b in NEW_BASES for b in requested) or mapped_segment
            or getattr(args, "preset", "fpa") != "fpa" or args.long_output or args.long_output_jsonl):
        return _run_comparisons(args, source_bytes, type_map_bytes, requested, mapping_obj)
    compare_to_basis = requested[0] if requested else None
    strict_without_basis = False

    mapping_arg = getattr(args, "mapping", None)
    if isinstance(mapping_arg, str) and mapping_arg:
        from .intake import (
            GLRangeRule,
            apply_classification_rules,
            detect_signed_ledger,
            flip_ledger_signs,
            read_input_assisted,
            scale_rows_by_unit,
        )
        assert mapping_obj is not None

        intake_res = read_input_assisted(
            source_bytes,
            input_path.suffix,
            filename=input_path.name,
            sheet=args.sheet,
            treat_blank_budgets_as_zero=mapping_obj.treat_blank_budgets_as_zero,
            selected_period=mapping_obj.period_column_selection,
            # An explicit --compare-to wins over the basis saved in the mapping.
            compare_to=compare_to_basis if compare_to_basis is not None else mapping_obj.comparison_basis,
        )
        if intake_res.has_fatal_errors:
            raise ValueError(_intake_error(intake_res))
        rows = list(intake_res.rows)
        if mapping_obj.exclude_totals:
            to_exclude = set(mapping_obj.exclude_totals)
            rows = [r for r in rows if str(r.get("line_item", "")).strip() not in to_exclude]
            # The audit records every exclusion that was applied, the mapping's included.
            intake_res.detected_totals = [
                *intake_res.detected_totals,
                *(name for name in mapping_obj.exclude_totals if name not in intake_res.detected_totals),
            ]
        # Intake already applied any unit scale and revenue sign flip it detected (as the chat
        # does), so the mapping only adds what the file itself did not say.
        if mapping_obj.unit_scale and mapping_obj.unit_scale != "1":
            target_scale = Decimal(mapping_obj.unit_scale)
            detected_scale = intake_res.detected_unit_multiplier
            if detected_scale == Decimal("1"):
                rows = scale_rows_by_unit(rows, target_scale)
                intake_res.detected_unit_multiplier = target_scale
            elif detected_scale != target_scale:
                raise ValueError(
                    f"The file's title says amounts are in {_unit_name(detected_scale)}, but the "
                    f"mapping says {_unit_name(target_scale)}. Check the file, or update unit_scale "
                    "in the mapping."
                )
        if mapping_obj.flip_signs and not intake_res.detected_signed_ledger:
            rows, flipped = flip_ledger_signs(rows, detect_signed_ledger(rows).negative_revenue_items)
            intake_res.negative_revenue_items = flipped
            intake_res.detected_signed_ledger = bool(flipped)

        type_map: dict[str, LineType] = {}
        if type_map_bytes is not None:
            type_map = _parse_type_map(type_map_bytes)
            if mapping_obj.classification_rules:
                print("[mapping] --type-map is used; the mapping's classification_rules were not applied.",
                      file=sys.stderr)
        elif mapping_obj.classification_rules:
            gl_rules_data = cast(list[dict[str, object]], mapping_obj.classification_rules.get("gl_ranges", []))
            gl_rules = [
                GLRangeRule(
                    min_account=int(str(r["min"])),
                    max_account=int(str(r["max"])),
                    line_type=LineType[str(r["type"]).upper()],
                    match_count=0,
                )
                for r in gl_rules_data
            ]
            keywords_data = cast(dict[str, str], mapping_obj.classification_rules.get("keywords", {}))
            keywords = {kw: LineType[t.upper()] for kw, t in keywords_data.items()}
            bulk_def_str = mapping_obj.classification_rules.get("bulk_default")
            bulk_def = LineType[str(bulk_def_str).upper()] if bulk_def_str else None
            items = [str(r.get("line_item", "")).strip() for r in rows if r.get("line_item")]
            type_map = apply_classification_rules(items, gl_rules, keywords=keywords, bulk_default=bulk_def)

        parsed_rows = rows
        parsed_worksheet = intake_res.sheet_name
        comparison_basis = intake_res.comparison_basis
        comparison_label = intake_res.comparison_label
    elif getattr(args, "assisted", False):
        from .intake import read_input_assisted
        intake_res = read_input_assisted(
            source_bytes,
            input_path.suffix,
            filename=input_path.name,
            sheet=args.sheet,
            treat_blank_budgets_as_zero=True,
            compare_to=compare_to_basis,
        )
        if intake_res.has_fatal_errors:
            raise ValueError(_intake_error(intake_res))
        parsed_rows = intake_res.rows
        parsed_worksheet = intake_res.sheet_name
        comparison_basis = intake_res.comparison_basis
        comparison_label = intake_res.comparison_label
        for transform in intake_res.visible_transformations:
            print(f"[assisted intake] {transform}", file=sys.stderr)
    else:
        parsed = load_input(source_bytes, input_path.suffix, source_name=input_path.name, sheet=args.sheet)
        parsed_rows = parsed.rows
        parsed_worksheet = parsed.worksheet
        comparison_basis = ComparisonBasis.BUDGET
        comparison_label = None
        strict_without_basis = compare_to_basis is None
        if compare_to_basis is not None:
            try:
                parsed_rows = select_strict_comparison(parsed_rows, compare_to_basis)
            except ValueError as exc:
                year_hint = _year_columns_hint(parsed_rows)
                if compare_to_basis is ComparisonBasis.PRIOR_PERIOD and year_hint is not None:
                    raise ValueError(f"{exc} {year_hint}") from exc
                raise
            comparison_basis = compare_to_basis

    type_map_final = type_map if mapping_obj is not None else (_parse_type_map(type_map_bytes) if type_map_bytes is not None else {})
    audience_args = {
        "per_share_threshold": getattr(args, "per_share_threshold", None),
        "count_threshold": getattr(args, "count_threshold", None),
        "bps_threshold": getattr(args, "bps_threshold", None),
        "percent_values": getattr(args, "percent_values", None),
    }
    if mapping_obj is not None:
        for key, value in (mapping_obj.measure_options or {}).items():
            if audience_args.get(key) is None:
                try:
                    audience_args[key] = value if key == "percent_values" else _decimal(value)
                except argparse.ArgumentTypeError as exc:
                    raise ValueError(f"Mapping file: {key} must be a non-negative numeric threshold.") from exc
        if mapping_obj.better_directions:
            selected_rows = []
            for row in parsed_rows:
                canonical = normalize_row(row)
                label = str(canonical.get("line_item", ""))
                if label in mapping_obj.better_directions:
                    canonical["better"] = mapping_obj.better_directions[label]
                selected_rows.append(canonical)
            parsed_rows = selected_rows
    config = AnalysisConfig(
        period=args.period,
        dollar_threshold=args.dollar_threshold,
        percent_threshold=args.percent_threshold / Decimal("100"),
        type_map=type_map_final,
        currency=args.currency,
        comparison_basis=comparison_basis,
        comparison_label=comparison_label,
    )
    if any(value is not None for value in audience_args.values()):
        config = AudienceConfig(
            config.period, config.dollar_threshold, config.percent_threshold, type_map=config.type_map,
            currency=config.currency, comparison_basis=config.comparison_basis, comparison_label=config.comparison_label,
            per_share_threshold=cast(Decimal | None, audience_args["per_share_threshold"]),
            count_threshold=cast(Decimal | None, audience_args["count_threshold"]),
            bps_threshold=cast(Decimal | None, audience_args["bps_threshold"]),
            percent_values=cast(str | None, audience_args["percent_values"]),
        )
    try:
        result = analyze_rows(parsed_rows, config)
    except ValueError as exc:
        if strict_without_basis and "required field 'Budget' was not found" in str(exc):
            other_bases = FORECAST_SYNONYMS | PRIOR_PERIOD_SYNONYMS
            if any(key in other_bases for row in parsed_rows for key in row):
                raise ValueError(f"{exc} {COMPARE_TO_HINT}") from exc
            year_hint = _year_columns_hint(parsed_rows)
            if year_hint is not None:
                raise ValueError(f"{exc} {year_hint}") from exc
        raise
    if is_audience_result(result):
        for note in metric_inferences(result.rows, result.config):
            print("[measure intake] " + display_text(note), file=sys.stderr)
    if args.check_only:
        unclassified = sum(row.line_type == LineType.UNCLASSIFIED for row in result.rows)
        print(f"Validation passed: {_count(len(result.rows), 'row')}, "
              f"{_count(len(result.material_rows), 'material variance')}, {unclassified} Unclassified, "
              f"{_count(len(result.warnings), 'warning')}; reporting currency {config.currency}.")
        return 0
    report = render_markdown(result)
    if args.commentary:
        from deterministic_conditioning.variance_bridge import generate_verified_commentary
        commentary_text, _ = generate_verified_commentary(result)
        report = f"# Executive Commentary\n\n{_safe_inline(commentary_text)}\n\n---\n\n" + report
    outputs: dict[Path, str | bytes] = {}
    if args.output:
        outputs[Path(args.output)] = report
    if args.xlsx:
        outputs[Path(args.xlsx)] = render_xlsx(result)
    if args.audit_json:
        transformations: dict[str, object] | None = None
        if intake_res is not None:
            from .intake import audit_transformations
            transformations = audit_transformations(intake_res, mapping_obj)
        record = build_audit_record(
            result, source_name=input_path.name, source_sha256=source_hash,
            schema_version=args.audit_schema_version,
            type_map_sha256=(sha256_bytes(type_map_bytes) if type_map_bytes is not None else None),
            source_worksheet=parsed_worksheet,
            transformations=transformations,
            source_document=intake_res.source_document() if intake_res is not None else None,
        )
        outputs[Path(args.audit_json)] = serialize_audit_json(record)
    write_text_outputs(outputs)
    if not args.output:
        print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = cast(Arguments, parser.parse_args(argv))
    if args.chat and (args.group_by or args.long_output or args.long_output_jsonl or args.errors_output):
        parser.error("panel/long-output flags cannot be combined with --chat.")
    if args.hosted and not args.chat:
        parser.error("--hosted requires --chat.")
    if args.no_browser and not args.chat:
        parser.error("--no-browser requires --chat.")
    if not args.chat:
        missing: list[str] = []
        if not args.input:
            missing.append("input")
        if not args.period and not args.group_by:
            missing.append("--period")
        if args.dollar_threshold is None:
            missing.append("--dollar-threshold")
        if args.percent_threshold is None:
            missing.append("--percent-threshold")
        if missing:
            parser.error(f"the following arguments are required: {', '.join(missing)}")
    try:
        return _run(args)
    except (OSError, ValueError, csv.Error, DecimalException, BadZipFile, RuntimeError) as exc:
        # A problem with the data, not with the command line: one clear line, no usage banner.
        parser.exit(2, f"{parser.prog}: error: {display_text(str(exc))}\n")




def _comparison_argument(value: str) -> str:
    tokens = [token.strip().lower() for token in value.split(",")]
    try:
        bases = [parse_compare_to(token) for token in tokens]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if len(set(bases)) != len(bases):
        raise argparse.ArgumentTypeError("Choose each comparison basis only once.")
    return ",".join(tokens)


def _run_comparisons(
    args: Arguments, source_bytes: bytes, type_map_bytes: bytes | None, requested: tuple[ComparisonBasis, ...],
    mapping: object,
) -> int:
    from .comparisons import (analyze_comparisons, build_comparison_audit, read_comparison_input,
                              render_comparisons, detect_comparison_bases)
    from .mapping import LayoutMapping
    from .xlsx import render_comparison_xlsx
    assert args.input is not None and args.period is not None
    assert args.dollar_threshold is not None and args.percent_threshold is not None
    layout = mapping if isinstance(mapping, LayoutMapping) else None
    if args.commentary:
        raise ValueError("Executive commentary is not available for a multi-measure comparison review.")
    path = Path(args.input)
    columns = dict(layout.column_mapping) if layout is not None else {}
    if "budget" in columns and len(requested) == 1:
        columns[str(requested[0])] = columns.pop("budget")
    rows, headers, worksheet, notes = read_comparison_input(
        source_bytes, path.suffix, filename=path.name, sheet=args.sheet, assisted=args.assisted or layout is not None,
        column_mapping=columns or None,
    )
    bases = requested
    if not bases:
        bases = detect_comparison_bases(headers)
        if len(bases) > 1:
            raise ValueError("Multiple comparison bases found; choose --compare-to with one basis or an explicit comma list.")
        if not bases:
            bases = (ComparisonBasis.PRIOR_PERIOD,)
    def option(name: str) -> Decimal | None:
        supplied = getattr(args, name, None)
        if isinstance(supplied, Decimal):
            return supplied
        if layout is not None and name in (layout.measure_options or {}):
            return parse_decimal((layout.measure_options or {})[name], field=name, line_item="Mapping file")
        return None
    percent_values = getattr(args, "percent_values", None)
    if percent_values is None and layout is not None:
        percent_values = (layout.measure_options or {}).get("percent_values")
    if layout is not None and layout.better_directions:
        for row in rows:
            canonical = normalize_row(row)
            name = str(canonical.get("line_item", ""))
            if name in layout.better_directions:
                row["Better"] = layout.better_directions[name]
    config = AudienceConfig(args.period, args.dollar_threshold, args.percent_threshold / Decimal("100"),
                            currency=args.currency, type_map=_parse_type_map(type_map_bytes) if type_map_bytes is not None else {},
                            per_share_threshold=option("per_share_threshold"), count_threshold=option("count_threshold"),
                            bps_threshold=option("bps_threshold"), percent_values=percent_values, extended_headers=True)
    table = analyze_comparisons(rows, config, bases, raw_headers=headers)
    for note in (*notes, *table.inferences):
        print("[comparison intake] " + display_text(note), file=sys.stderr)
    for comparison in table.comparisons:
        if comparison.result is not None:
            for note in metric_inferences(comparison.result.rows, comparison.result.config):
                print("[measure intake] " + display_text(note), file=sys.stderr)
    if args.check_only:
        print(f"Validation passed: {len(rows)} rows, {len(bases)} comparison(s).")
        return 0
    only = table.comparisons[0]
    report = (render_markdown(only.result) if len(bases) == 1 and only.result is not None and not only.unavailable
              else render_comparisons(table))
    outputs: dict[Path, str | bytes] = {}
    if args.output:
        outputs[Path(args.output)] = report
    if args.xlsx:
        outputs[Path(args.xlsx)] = render_comparison_xlsx(table)
    if args.audit_json:
        record = build_comparison_audit(table, source_name=path.name, source_sha256=sha256_bytes(source_bytes),
                                        schema_version=args.audit_schema_version, source_worksheet=worksheet)
        # Input-layout notes are facts too; recompute both digests after adding them.
        from .audit import finalize_audience_record
        inferences = record.get("inferences")
        if isinstance(inferences, list):
            inferences.extend(notes)
            finalize_audience_record(record)
        outputs[Path(args.audit_json)] = serialize_audit_json(record)
    if args.long_output or args.long_output_jsonl:
        from .panel import BatchResult, GroupResult
        from .long_output import long_csv, long_jsonl
        batch = BatchResult((), (GroupResult((), table),), sha256_bytes(source_bytes), path.name)
        if args.long_output:
            outputs[Path(args.long_output)] = long_csv(batch)
        if args.long_output_jsonl:
            outputs[Path(args.long_output_jsonl)] = long_jsonl(batch)
    write_text_outputs(outputs)
    if not args.output:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
