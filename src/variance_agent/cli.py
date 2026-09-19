from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from .analysis import analyze_rows
from .audit import build_audit_record, sha256_file, write_audit_json
from .models import AnalysisConfig, LineType
from .parsing import load_file
from .report import render_markdown


def _decimal(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", "").replace("$", "").strip())
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"Invalid number: {text}") from exc


def _load_type_map(path: str | None) -> dict[str, LineType]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input)
    rows = load_file(input_path)
    config = AnalysisConfig(
        period=args.period,
        dollar_threshold=args.dollar_threshold,
        percent_threshold=args.percent_threshold / Decimal("100"),
        type_map=_load_type_map(args.type_map),
    )
    result = analyze_rows(rows, config)
    report = render_markdown(result)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    else:
        print(report)
    if args.audit_json:
        record = build_audit_record(
            result,
            source_name=input_path.name,
            source_sha256=sha256_file(input_path),
        )
        write_audit_json(args.audit_json, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
