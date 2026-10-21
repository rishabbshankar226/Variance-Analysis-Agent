from __future__ import annotations

import argparse
import csv
import os
import sys
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Protocol, cast
from zipfile import BadZipFile

from .analysis import analyze_rows
from .audit import (CURRENT_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS,
                    build_audit_record, sha256_bytes, serialize_audit_json)
from .currencies import CURRENCY_SYMBOLS
from .models import AnalysisConfig, LineType
from .parsing import load_input, load_json_value, parse_decimal, read_input_bytes, validate_input_format
from .output import write_text_outputs
from .numeric import financial_context
from .report import render_markdown
from .limits import display_text


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
    chat: bool
    hosted: bool
    commentary: bool
    assisted: bool
    mapping: str | None


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
        raise ValueError("Type map must be a JSON object of line item -> Revenue/Expense.")
    output: dict[str, LineType] = {}
    for item, value in payload.items():
        text = str(value).strip().lower()
        if text in {"revenue", "income", "sales"}:
            output[item] = LineType.REVENUE
        elif text in {"expense", "expenses", "cost", "costs"}:
            output[item] = LineType.EXPENSE
        else:
            raise ValueError(f"Type map value for {item!r} must be Revenue or Expense.")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="variance-agent",
        description="Generate an auditable FP&A variance report from CSV, JSON, or Excel data.",
    )
    parser.add_argument("input", nargs="?", default=None, help="Input CSV, JSON, XLSX, or XLSM file.")
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
    parser.add_argument("--sheet", help="Exact Excel worksheet name (default: active worksheet).")
    parser.add_argument("--currency", type=str.upper, choices=tuple(CURRENCY_SYMBOLS), default="USD",
                        help="Reporting currency (default USD); conflicting amounts are rejected.")
    parser.add_argument("--audit-schema-version", choices=SUPPORTED_SCHEMA_VERSIONS,
                        default=CURRENT_SCHEMA_VERSION, help="Audit JSON format version.")
    parser.add_argument("-o", "--output", help="Write Markdown report to this path.")
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
    return parser


def _same_path(first: Path, second: Path) -> bool:
    return first.resolve() == second.resolve() or (
        first.exists() and second.exists() and first.samefile(second)
    )


def _validate_output_paths(args: Arguments) -> None:
    assert args.input is not None
    inputs = [Path(args.input)]
    if args.type_map:
        inputs.append(Path(args.type_map))
    if getattr(args, "mapping", None):
        inputs.append(Path(args.mapping))
    outputs = [Path(value) for value in (args.output, args.audit_json) if value]
    for index, output in enumerate(outputs):
        if any(_same_path(output, other) for other in inputs + outputs[:index]):
            raise ValueError("Input, type-map, report, and audit output paths must be distinct.")


@financial_context()
def _run(args: Arguments) -> int:
    if args.chat:
        if args.check_only or args.output or args.audit_json:
            raise ValueError("--chat cannot be combined with --check-only, --output, or --audit-json.")
        from .chat.server import run_chat_server
        is_hosted = args.hosted or "RENDER" in os.environ or ("PORT" in os.environ and os.environ.get("PORT", "").isdigit())
        if is_hosted:
            return run_chat_server(
                host="0.0.0.0", port=int(os.environ.get("PORT", "10000")),
                initial_input=args.input, initial_sheet=args.sheet,
                open_browser=False, hosted=True,
            )
        return run_chat_server(initial_input=args.input, initial_sheet=args.sheet)

    assert args.input is not None
    assert args.period is not None
    assert args.dollar_threshold is not None
    assert args.percent_threshold is not None
    if args.check_only and (args.output or args.audit_json):
        raise ValueError("--check-only cannot be combined with --output or --audit-json.")
    _validate_output_paths(args)
    input_path = Path(args.input)
    if args.sheet is not None and input_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("--sheet requires XLSX or XLSM input.")
    validate_input_format(input_path.suffix)
    # Capture each input once, then use exactly those bytes for parsing and hashes.
    source_bytes = read_input_bytes(input_path)
    type_map_bytes = read_input_bytes(args.type_map) if args.type_map else None
    source_hash = sha256_bytes(source_bytes) if args.audit_json else None

    mapping_obj = None
    mapping_hash = None
    intake_res = None

    if getattr(args, "mapping", None):
        from .mapping import load_mapping, mapping_sha256
        from .intake import (
            GLRangeRule,
            apply_classification_rules,
            flip_ledger_signs,
            read_input_assisted,
            scale_rows_by_unit,
        )
        mapping_path = Path(args.mapping)
        mapping_obj = load_mapping(mapping_path.read_text(encoding="utf-8"))
        mapping_hash = mapping_sha256(mapping_obj)

        intake_res = read_input_assisted(
            source_bytes,
            input_path.suffix,
            filename=input_path.name,
            sheet=args.sheet,
            treat_blank_budgets_as_zero=mapping_obj.treat_blank_budgets_as_zero,
            selected_period=mapping_obj.period_column_selection,
        )
        if intake_res.has_fatal_errors:
            raise ValueError(intake_res.fatal_error_message or "Could not read input.")
        rows = list(intake_res.rows)
        if mapping_obj.exclude_totals:
            to_exclude = set(mapping_obj.exclude_totals)
            rows = [r for r in rows if str(r.get("line_item", "")).strip() not in to_exclude]
        if mapping_obj.unit_scale and mapping_obj.unit_scale != "1":
            rows, _ = scale_rows_by_unit(rows, Decimal(mapping_obj.unit_scale))
        if mapping_obj.flip_signs:
            items = [str(r.get("line_item", "")).strip() for r in rows if r.get("line_item")]
            rows, _ = flip_ledger_signs(rows, items)

        type_map: dict[str, LineType] = {}
        if type_map_bytes is not None:
            type_map = _parse_type_map(type_map_bytes)
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
    elif getattr(args, "assisted", False):
        from .intake import read_input_assisted
        intake_res = read_input_assisted(
            source_bytes,
            input_path.suffix,
            filename=input_path.name,
            sheet=args.sheet,
            treat_blank_budgets_as_zero=True,
        )
        if intake_res.has_fatal_errors:
            raise ValueError(intake_res.fatal_error_message or "Could not read input.")
        parsed_rows = intake_res.rows
        parsed_worksheet = intake_res.sheet_name
        for transform in intake_res.visible_transformations:
            print(f"[assisted intake] {transform}", file=sys.stderr)
    else:
        parsed = load_input(source_bytes, input_path.suffix, source_name=input_path.name, sheet=args.sheet)
        parsed_rows = parsed.rows
        parsed_worksheet = parsed.worksheet

    type_map_final = type_map if mapping_obj is not None else (_parse_type_map(type_map_bytes) if type_map_bytes is not None else {})
    config = AnalysisConfig(
        period=args.period,
        dollar_threshold=args.dollar_threshold,
        percent_threshold=args.percent_threshold / Decimal("100"),
        type_map=type_map_final,
        currency=args.currency,
    )
    result = analyze_rows(parsed_rows, config)
    if args.check_only:
        unclassified = sum(row.line_type == LineType.UNCLASSIFIED for row in result.rows)
        print(f"Validation passed: {len(result.rows)} rows, {len(result.material_rows)} material "
              f"variances, {unclassified} Unclassified, {len(result.warnings)} warnings; "
              f"reporting currency {config.currency}.")
        return 0
    report = render_markdown(result)
    if args.commentary:
        from deterministic_conditioning.variance_bridge import generate_verified_commentary
        commentary_text, _ = generate_verified_commentary(result)
        report = f"# Executive Commentary\n\n{commentary_text}\n\n---\n\n" + report
    outputs: dict[Path, str] = {}
    if args.output:
        outputs[Path(args.output)] = report
    if args.audit_json:
        transformations: dict[str, object] | None = None
        if mapping_obj is not None and intake_res is not None:
            transformations = {
                "header_row_number": mapping_obj.header_row_number,
                "column_mapping": mapping_obj.column_mapping,
                "ignored_columns": intake_res.ignored_columns,
                "sign_flip": mapping_obj.flip_signs,
                "flipped_line_items": intake_res.negative_revenue_items if mapping_obj.flip_signs else [],
                "unit_scale": mapping_obj.unit_scale if mapping_obj.unit_scale != "1" else None,
                "zero_reads": {
                    "accounting_dashes": 0,
                    "blank_budgets": len(intake_res.blank_budget_items) if mapping_obj.treat_blank_budgets_as_zero else 0,
                },
                "excluded_totals": mapping_obj.exclude_totals,
                "period_selection": mapping_obj.period_column_selection,
                "classification_rules": mapping_obj.classification_rules,
                "mapping_file_sha256": mapping_hash,
            }
        elif getattr(args, "assisted", False) and intake_res is not None:
            col_map = {role.value: name for role, name in intake_res.column_mapping.items()}
            transformations = {
                "header_row_number": intake_res.header_row_number,
                "column_mapping": col_map,
                "ignored_columns": intake_res.ignored_columns,
                "sign_flip": intake_res.detected_signed_ledger,
                "flipped_line_items": intake_res.negative_revenue_items if intake_res.detected_signed_ledger else [],
                "unit_scale": str(intake_res.detected_unit_multiplier) if intake_res.detected_unit_multiplier != Decimal("1") else None,
                "zero_reads": {
                    "accounting_dashes": 0,
                    "blank_budgets": len(intake_res.blank_budget_items),
                },
                "excluded_totals": intake_res.detected_totals,
                "period_selection": None,
                "classification_rules": None,
                "mapping_file_sha256": None,
            }
        record = build_audit_record(
            result, source_name=input_path.name, source_sha256=source_hash,
            schema_version=args.audit_schema_version,
            type_map_sha256=(sha256_bytes(type_map_bytes) if type_map_bytes is not None else None),
            source_worksheet=parsed_worksheet,
            transformations=transformations,
        )
        outputs[Path(args.audit_json)] = serialize_audit_json(record)
    write_text_outputs(outputs)
    if not args.output:
        print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = cast(Arguments, parser.parse_args(argv))
    if args.hosted and not args.chat:
        parser.error("--hosted requires --chat.")
    if not args.chat:
        missing: list[str] = []
        if not args.input:
            missing.append("input")
        if not args.period:
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
        parser.error(display_text(str(exc)))


if __name__ == "__main__":
    raise SystemExit(main())
