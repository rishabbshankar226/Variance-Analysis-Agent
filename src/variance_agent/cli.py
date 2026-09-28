from __future__ import annotations

import argparse
import csv
from decimal import Decimal, DecimalException
from pathlib import Path
from zipfile import BadZipFile

from .analysis import analyze_rows
from .audit import build_audit_record, sha256_file, serialize_audit_json
from .models import AnalysisConfig, LineType
from .parsing import load_file, load_json_value, parse_decimal
from .output import write_text_outputs
from .numeric import financial_context
from .report import render_markdown


def _decimal(text: str) -> Decimal:
    try:
        return parse_decimal(text, field="threshold", line_item="Materiality")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid number: {text}") from exc


def _load_type_map(path: str | None) -> dict[str, LineType]:
    if not path:
        return {}
    payload = load_json_value(Path(path).read_text(encoding="utf-8"))
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
    parser.add_argument("input", help="Input CSV, JSON, XLSX, or XLSM file.")
    parser.add_argument("--period", required=True, help="Reporting period shown in the report.")
    parser.add_argument(
        "--dollar-threshold",
        required=True,
        type=_decimal,
        help="Absolute dollar materiality threshold. Uses strict > semantics.",
    )
    parser.add_argument(
        "--percent-threshold",
        required=True,
        type=_decimal,
        help="Percentage threshold as a percent number (for example, 5 for 5%).",
    )
    parser.add_argument("--type-map", help="Optional JSON mapping of line item to Revenue/Expense.")
    parser.add_argument("-o", "--output", help="Write Markdown report to this path.")
    parser.add_argument(
        "--audit-json",
        help="Write a machine-readable audit/agent-context record with source provenance.",
    )
    return parser


def _same_path(first: Path, second: Path) -> bool:
    return first.resolve() == second.resolve() or (
        first.exists() and second.exists() and first.samefile(second)
    )


def _validate_output_paths(args: argparse.Namespace) -> None:
    inputs = [Path(args.input)]
    if args.type_map:
        inputs.append(Path(args.type_map))
    outputs = [Path(value) for value in (args.output, args.audit_json) if value]
    for index, output in enumerate(outputs):
        if any(_same_path(output, other) for other in inputs + outputs[:index]):
            raise ValueError("Input, type-map, report, and audit output paths must be distinct.")


@financial_context()
def _run(args: argparse.Namespace) -> int:
    _validate_output_paths(args)
    input_path = Path(args.input)
    # Capture provenance before any output is written.
    source_hash = sha256_file(input_path) if args.audit_json else None
    rows = load_file(input_path)
    if source_hash is not None and sha256_file(input_path) != source_hash:
        raise ValueError("Input changed while it was being read; retry with a stable file.")
    config = AnalysisConfig(
        period=args.period,
        dollar_threshold=args.dollar_threshold,
        percent_threshold=args.percent_threshold / Decimal("100"),
        type_map=_load_type_map(args.type_map),
    )
    result = analyze_rows(rows, config)
    report = render_markdown(result)
    record = (
        build_audit_record(result, source_name=input_path.name, source_sha256=source_hash)
        if args.audit_json else None
    )
    outputs = {}
    if args.output:
        outputs[Path(args.output)] = report
    if args.audit_json:
        outputs[Path(args.audit_json)] = serialize_audit_json(record)
    write_text_outputs(outputs)
    if not args.output:
        print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (OSError, ValueError, csv.Error, DecimalException, BadZipFile) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
