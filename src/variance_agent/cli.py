from __future__ import annotations

import argparse
import csv
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
    parsed = load_input(source_bytes, input_path.suffix, source_name=input_path.name, sheet=args.sheet)
    config = AnalysisConfig(
        period=args.period,
        dollar_threshold=args.dollar_threshold,
        percent_threshold=args.percent_threshold / Decimal("100"),
        type_map=_parse_type_map(type_map_bytes) if type_map_bytes is not None else {},
        currency=args.currency,
    )
    result = analyze_rows(parsed.rows, config)
    if args.check_only:
        unclassified = sum(row.line_type == LineType.UNCLASSIFIED for row in result.rows)
        print(f"Validation passed: {len(result.rows)} rows, {len(result.material_rows)} material "
              f"variances, {unclassified} Unclassified, {len(result.warnings)} warnings; "
              f"reporting currency {config.currency}.")
        return 0
    report = render_markdown(result)
    outputs: dict[Path, str] = {}
    if args.output:
        outputs[Path(args.output)] = report
    if args.audit_json:
        record = build_audit_record(
            result, source_name=input_path.name, source_sha256=source_hash,
            schema_version=args.audit_schema_version,
            type_map_sha256=(sha256_bytes(type_map_bytes) if type_map_bytes is not None else None),
            source_worksheet=parsed.worksheet,
        )
        outputs[Path(args.audit_json)] = serialize_audit_json(record)
    write_text_outputs(outputs)
    if not args.output:
        print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = cast(Arguments, parser.parse_args(argv))
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
