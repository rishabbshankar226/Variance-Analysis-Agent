from __future__ import annotations

import argparse
import csv
import os
import sys
import unicodedata
from dataclasses import replace
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from zipfile import BadZipFile

from .audience import AudienceConfig, NEW_BASES, OPT_IN_BASES, is_audience_result
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
from .parsing import normalize_key, normalize_row, load_input, load_json_value, parse_decimal, read_input_bytes, validate_input_format
from .output import write_text_outputs
from .numeric import financial_context
from .report import _safe_inline, render_markdown
from .xlsx import render_xlsx
from .limits import display_text

if TYPE_CHECKING:
    from .intake import IntakeResult


COMPARE_TO_HINT = "Rerun with --compare-to budget|forecast|prior-period."
HIDDEN_ROWS_HINT = "Rerun with --hidden-rows include to count them or --hidden-rows exclude to leave them out."


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
    if intake_res.needs_hidden_rows_choice:
        message = f"{message} {HIDDEN_ROWS_HINT}"
    return message


def _print_examination(intake_res: IntakeResult) -> None:
    """The workbook examination on stderr, only when it found something (stdout stays the report)."""
    exam = intake_res.workbook_examination
    if exam is not None and exam.findings:
        for line in exam.lines():
            print(f"[workbook] {line}", file=sys.stderr)


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
    hidden_rows: str | None
    ltm_from: str | None
    compare_file: str | None
    metrics: str | None
    panel: str | None
    join_key: str | None
    deciding_metric: str | None
    compare_to: str | None
    preset: str
    layout: str | None
    per_share_lines: bool | None
    headline: list[str] | None
    per_share_threshold: Decimal | None
    count_threshold: Decimal | None
    multiple_threshold: Decimal | None
    bps_threshold: Decimal | None
    percent_values: str | None
    group_by: str | None
    long_output: str | None
    long_output_jsonl: str | None
    errors_output: str | None
    history: str | None
    surprise_window: int
    entity: str | None


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
        usage="%(prog)s INPUT --period PERIOD --dollar-threshold N --percent-threshold N [options]\n"
              "       %(prog)s --chat [--no-browser | --hosted]",
        description="Compare supplied actuals with budgets, consensus, estimates, guidance or prior periods "
                    "in auditable reports and panels.",
        epilog="Example: variance-agent examples/sample_variance.csv --period 'Q3 2026' "
               "--dollar-threshold 10000 --percent-threshold 5 -o report.md",
    )
    # Groups only change how --help reads; every flag, default and type is as before.
    source = parser.add_argument_group("Input", "The file to analyze and how to read it.")
    source.add_argument("input", nargs="?", default=None,
                        help="Input CSV, JSON, XLSX, or XLSM file, or a PDF or Inline XBRL (.htm) filing with --assisted.")
    source.add_argument("--sheet", help="Exact Excel worksheet name (default: active worksheet), or the statement to read from a PDF.")
    source.add_argument(
        "--assisted",
        action="store_true",
        help="Enable assisted file intake (detect header rows, map column synonyms, and convert accounting dashes).",
    )
    source.add_argument(
        "--mapping",
        help="Path to saved layout mapping JSON file.",
    )
    source.add_argument("--ltm-from", metavar="PATH",
                        help="The 10-K whose fiscal year the input 10-Q continues: read the 10-Q's income statement "
                             "as LTM (fiscal year + year to date - prior year to date), compared with that fiscal year. "
                             "Needs --assisted.")
    source.add_argument("--compare-file", metavar="PATH",
                        help="A second file holding the comparison column (budget, forecast or prior period) for the "
                             "input's actuals, joined on an account column both carry, or else the exact line item. "
                             "Needs --assisted.")
    source.add_argument("--metrics", metavar="PATH",
                        help="A JSON file of derived metrics (name, signed numerator and denominator terms by XBRL "
                             "concept or exact label, statement and period) read from the input filing; needs "
                             "--compare-file with the case or covenant schedule. See docs/financial-rules.md.")
    source.add_argument("--panel", metavar="PATH",
                        help="A consensus panel for the input holdings sheet: label each holding by its "
                             "--deciding-metric against consensus and share the weights out. Needs --join-key.")
    source.add_argument("--join-key", metavar="COLUMN", help="The column the holdings sheet and the panel share (e.g. Ticker).")
    source.add_argument("--deciding-metric", metavar="NAME", help="The panel metric that decides a holding (e.g. Diluted EPS).")
    source.add_argument("--hidden-rows", choices=("include", "exclude"),
                        help="Count or leave out Excel rows hidden in the sheet; assisted intake asks when there are any.")
    source.add_argument("--type-map", help="Optional JSON mapping of line item to Revenue/Expense.")
    source.add_argument("--currency", type=str.upper, choices=tuple(CURRENCY_SYMBOLS), default="USD",
                        help="Reporting currency (default USD); conflicting amounts are rejected.")
    source.add_argument("--percent-values", choices=("points", "fractions"), help="Interpret bare Percent values explicitly.")

    analysis = parser.add_argument_group("Analysis", "The period, what Actual is compared with, and what counts as material.")
    analysis.add_argument("--period", help="Reporting period shown in the report.")
    analysis.add_argument(
        "--dollar-threshold",
        type=_decimal,
        help="Absolute dollar materiality threshold. Uses strict > semantics.",
    )
    analysis.add_argument(
        "--percent-threshold",
        type=_decimal,
        help="Percentage threshold as a percent number (for example, 5 for 5%%).",
    )
    analysis.add_argument(
        "--compare-to",
        type=_comparison_argument,
        help="Comparison basis or comma list: budget, forecast, prior-period, consensus, estimate, guidance; "
             "or, with --assisted and one per run, limit, benchmark or target (rows declare Limit Kind, Better, Tolerance).",
    )
    for flag in ("per-share-threshold", "count-threshold", "bps-threshold", "multiple-threshold"):
        analysis.add_argument("--" + flag, type=_decimal, help="Required absolute cutoff for its measure; strict >.")
    analysis.add_argument("--preset", choices=("fpa", "earnings", "quant"), default="fpa",
                          help="fpa: legacy headers/layout, per-share off; earnings: new headers, earnings layout, per-share on; "
                               "quant: new headers, long output required, no Markdown stdout, per-share off. No thresholds supplied.")
    analysis.add_argument("--layout", choices=("standard", "earnings"), help="Override the preset report layout.")
    analysis.add_argument("--headline", action="append", help="Headline line-item name; repeat to replace earnings defaults.")
    sharing = analysis.add_mutually_exclusive_group()
    sharing.add_argument("--per-share-lines", dest="per_share_lines", action="store_true", default=None,
                         help="Keep EPS/share counts in assisted filing intake (earnings preset default).")
    sharing.add_argument("--no-per-share-lines", dest="per_share_lines", action="store_false", help="Omit filing EPS/share counts.")

    outputs = parser.add_argument_group("Outputs", "Without an output flag the Markdown report is printed.")
    outputs.add_argument("-o", "--output", help="Write Markdown report to this path.")
    outputs.add_argument("--xlsx", help="Write a formatted Excel workbook to this path.")
    outputs.add_argument(
        "--audit-json",
        help="Write a machine-readable audit/agent-context record with source provenance.",
    )
    outputs.add_argument("--audit-schema-version", choices=SUPPORTED_SCHEMA_VERSIONS,
                         default=None,
                         help="Audit JSON format version (legacy 1.7; explicit measures 1.8; workbook examination and filings 1.9).")
    outputs.add_argument(
        "--commentary",
        action="store_true",
        help="Include verified deterministic executive commentary in the Markdown report.",
    )
    outputs.add_argument("--check-only", action="store_true",
                         help="Validate/analyze input and print a summary without writing outputs.")

    history = parser.add_argument_group("Surprise history and panels", "Supplied earnings history, and many entities at once.")
    history.add_argument("--history", help="CSV/JSON supplied surprise history, keyed by entity, metric and period.")
    history.add_argument("--surprise-window", type=_surprise_window, default=8, help="Most recent prior surprises (default 8, minimum 4).")
    history.add_argument("--entity", help="Entity identity for a single history comparison; otherwise read Ticker/Entity.")
    history.add_argument("--group-by", help="Panel keys, for example Ticker,Period. Mixed success exits 3; global errors exit 2.")
    history.add_argument("--long-output", help="Write deterministic exact-number CSV.")
    history.add_argument("--long-output-jsonl", help="Write deterministic exact-number JSON Lines.")
    history.add_argument("--errors-output", help="Write one CSV error row per failed panel group (required with --group-by).")

    chat = parser.add_argument_group("Chat", "The browser interface instead of a one-off report.")
    chat.add_argument(
        "--chat",
        action="store_true",
        help="Launch the interactive chatbot UI in your browser.",
    )
    chat.add_argument(
        "--hosted",
        action="store_true",
        help="With --chat: serve on 0.0.0.0:$PORT for a hosting platform, without "
             "opening a browser or writing exports to server paths.",
    )
    chat.add_argument(
        "--no-browser",
        action="store_true",
        help="With --chat: print the local URL instead of opening the system browser.",
    )
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
    history_arg = getattr(args, "history", None)
    if isinstance(history_arg, str) and history_arg:
        inputs.append(Path(history_arg))
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
    if args.preset == "quant" and not (args.long_output or args.long_output_jsonl):
        raise ValueError("--preset quant requires --long-output or --long-output-jsonl.")
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
    is_pdf = input_path.suffix.lower() in {".pdf", ".htm", ".html"}  # filings: --sheet names a statement
    if args.sheet is not None and input_path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"} and not is_pdf:
        raise ValueError("--sheet requires XLSX or XLSM input.")
    if getattr(args, "hidden_rows", None) is not None:
        if input_path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
            raise ValueError("--hidden-rows requires XLSX or XLSM input.")
        if not (getattr(args, "assisted", False) or getattr(args, "mapping", None)):
            raise ValueError("--hidden-rows requires --assisted or --mapping; strict intake reads every row as given.")
    if args.ltm_from and (not getattr(args, "assisted", False) or getattr(args, "mapping", None)):
        raise ValueError("--ltm-from needs --assisted (and no --mapping): LTM is built from the filings' own statements.")
    if any((args.panel, args.join_key, args.deciding_metric)) and not all((args.panel, args.join_key, args.deciding_metric)):
        raise ValueError("A holdings scorecard needs --panel, --join-key and --deciding-metric together.")
    if args.panel and (not getattr(args, "assisted", False) or getattr(args, "mapping", None) or args.compare_file
                       or args.metrics or args.ltm_from):
        raise ValueError("--panel needs --assisted, and no --mapping, --compare-file, --metrics or --ltm-from.")
    if args.metrics and not args.compare_file:
        raise ValueError("--metrics needs --compare-file: the metrics are compared with the case or covenant schedule "
                         "that file holds.")
    if args.metrics and (not getattr(args, "assisted", False) or getattr(args, "mapping", None)):
        raise ValueError("--metrics needs --assisted (and no --mapping): the metrics are read from the filing's statements.")
    if args.compare_file and not args.metrics and (
            not getattr(args, "assisted", False) or getattr(args, "mapping", None) or args.ltm_from):
        raise ValueError("--compare-file needs --assisted (and no --mapping or --ltm-from): each file is read on its own, "
                         "then the two are joined.")
    validate_input_format(input_path.suffix, assisted=bool(getattr(args, "assisted", False)), filename=input_path.name)
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
            or getattr(args, "preset", "fpa") != "fpa" or args.long_output or args.long_output_jsonl or args.history
            or args.layout is not None or args.headline or args.per_share_lines is True):
        return _run_comparisons(args, source_bytes, type_map_bytes, requested, mapping_obj)
    compare_to_basis = requested[0] if requested else None
    strict_without_basis = False
    if compare_to_basis in OPT_IN_BASES and not (getattr(args, "assisted", False) or getattr(args, "mapping", None)):
        raise ValueError(f"--compare-to {compare_to_basis.value} needs --assisted, which reads each row's declarations "
                         "(Limit Kind, Buffer, Better, Tolerance) beside its figures.")

    mapping_arg = getattr(args, "mapping", None)
    if isinstance(mapping_arg, str) and mapping_arg:
        from .intake import (
            GLRangeRule,
            apply_classification_rules,
            detect_signed_ledger,
            flip_ledger_signs,
            read_input_assisted,
            reconcile_declared_unit,
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
            hidden_rows=getattr(args, "hidden_rows", None) or mapping_obj.hidden_rows,
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
                # Reconciled with the amounts' number formats, as a caption would be (E1).
                rows = reconcile_declared_unit(intake_res, rows, target_scale, input_path.name)
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

        _print_examination(intake_res)
        parsed_rows = rows
        parsed_worksheet = intake_res.sheet_name
        comparison_basis = intake_res.comparison_basis
        comparison_label = intake_res.comparison_label
    elif getattr(args, "assisted", False):
        from .intake import read_input_assisted
        if args.panel:
            from .scorecard import build_scorecard
            assert args.join_key is not None and args.deciding_metric is not None
            panel = Path(args.panel)
            intake_res = build_scorecard(source_bytes, input_path.name, read_input_bytes(panel), panel.name,
                                         args.join_key, args.deciding_metric)
        elif args.metrics:
            from .metrics import compare_metrics
            assert args.compare_file is not None  # checked with the other flags above
            other, annual_path = Path(args.compare_file), Path(args.ltm_from) if args.ltm_from else None
            intake_res = compare_metrics(read_input_bytes(Path(args.metrics)), source_bytes, input_path.name,
                                         read_input_bytes(other), other.name,
                                         annual=read_input_bytes(annual_path) if annual_path else None,
                                         annual_name=annual_path.name if annual_path else None, compare_to=compare_to_basis)
        elif args.compare_file:
            from .join import join_files
            other = Path(args.compare_file)
            intake_res = join_files(source_bytes, input_path.name, read_input_bytes(other), other.name, sheet=args.sheet,
                                    compare_to=compare_to_basis, hidden_rows=getattr(args, "hidden_rows", None))
        elif args.ltm_from:
            from .ltm import build_ltm
            annual_path = Path(args.ltm_from)
            if compare_to_basis is not None:
                raise ValueError("--ltm-from compares LTM with the 10-K's fiscal year; leave out --compare-to.")
            if input_path.suffix.lower() not in {".htm", ".html"} or annual_path.suffix.lower() not in {".htm", ".html"}:
                raise ValueError("--ltm-from builds LTM from two Inline XBRL filings: give the 10-Q's and the 10-K's "
                                 ".htm documents from EDGAR.")
            intake_res = build_ltm(source_bytes, input_path.name, read_input_bytes(annual_path), annual_path.name,
                                   sheet=args.sheet)
        else:
            intake_res = read_input_assisted(
                source_bytes,
                input_path.suffix,
                filename=input_path.name,
                sheet=args.sheet,
                treat_blank_budgets_as_zero=True,
                compare_to=compare_to_basis,
                hidden_rows=getattr(args, "hidden_rows", None),
            )
        if intake_res.has_fatal_errors:
            raise ValueError(_intake_error(intake_res))
        parsed_rows = intake_res.rows
        parsed_worksheet = intake_res.sheet_name
        comparison_basis = intake_res.comparison_basis
        comparison_label = intake_res.comparison_label
        for transform in intake_res.visible_transformations:
            print(f"[assisted intake] {transform}", file=sys.stderr)
        _print_examination(intake_res)
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
        "multiple_threshold": getattr(args, "multiple_threshold", None),
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
            multiple_threshold=cast(Decimal | None, audience_args["multiple_threshold"]),
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
    if intake_res is not None and intake_res.scorecard is not None:
        from .scorecard import finish_scorecard
        finish_scorecard(intake_res, result)
    statement_checks = intake_res.statement_checks if intake_res is not None else []
    if result.config.comparison_basis in OPT_IN_BASES and args.xlsx:
        raise ValueError("--xlsx isn't available for a limit, benchmark or target comparison yet. Leave out --xlsx; "
                         "the report and the audit file hold every outcome.")
    if statement_checks and args.xlsx:
        raise ValueError("--xlsx isn't available for a balance sheet or cash flow comparison yet. Leave out --xlsx, "
                         "or choose the filing's income statement.")
    appendix = intake_res.report_appendix if intake_res is not None else []
    report = (render_markdown(result, statement_checks=statement_checks or None, appendix=appendix or None)
              if statement_checks or appendix else render_markdown(result))
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
    if args.chat and (args.group_by or args.long_output or args.long_output_jsonl or args.errors_output or args.history or args.entity):
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
    metadata: dict[str, object] = {}
    rows, headers, worksheet, notes = read_comparison_input(
        source_bytes, path.suffix, filename=path.name, sheet=args.sheet, assisted=args.assisted or layout is not None,
        column_mapping=columns or None,
        per_share_lines=args.per_share_lines if args.per_share_lines is not None else args.preset == "earnings",
        metadata=metadata,
        hidden_rows=getattr(args, "hidden_rows", None) or (layout.hidden_rows if layout is not None else None),
    )
    bases = requested
    extended = args.preset != "fpa" or any(basis in NEW_BASES for basis in bases) or layout is not None
    if not bases and not extended:
        bases = (ComparisonBasis(str(metadata["comparison_basis"])),) if "comparison_basis" in metadata else (ComparisonBasis.BUDGET,)
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
                for key in [key for key in row if normalize_key(key) == "better"]:
                    row.pop(key)
                row["Better"] = layout.better_directions[name]
    config = AudienceConfig(args.period, args.dollar_threshold, args.percent_threshold / Decimal("100"),
                            currency=args.currency, type_map=_parse_type_map(type_map_bytes) if type_map_bytes is not None else {},
                            per_share_threshold=option("per_share_threshold"), count_threshold=option("count_threshold"),
                            bps_threshold=option("bps_threshold"), percent_values=percent_values, extended_headers=True,
                            preset=args.preset, layout=args.layout, per_share_lines=args.per_share_lines,
                            headline_items=tuple(args.headline or ()))
    if isinstance(metadata.get("comparison_label"), str):
        config = replace(config, comparison_label=str(metadata["comparison_label"]))
    if isinstance(metadata.get("actual_label"), str):
        config = replace(config, actual_label=str(metadata["actual_label"]))
    table = analyze_comparisons(rows, config, bases, raw_headers=headers, extended_headers=extended)
    transformations = metadata.get("transformations", {})
    assert isinstance(transformations, dict)
    if layout is not None:
        from .mapping import mapping_sha256
        transformations["mapping_file_sha256"] = mapping_sha256(layout)
        if columns:
            transformations["column_mapping"] = columns
    document = metadata.get("document")
    table = replace(table, source_document=document if isinstance(document, dict) else None,
                    source_transformations=transformations or None, inferences=(*table.inferences, *notes))
    if args.history or table.statistic_context is not None or args.entity or args.surprise_window != 8:
        from .surprise import load_history, SurpriseOptions, attach_statistics, infer_entity
        table = attach_statistics(table, SurpriseOptions(history=load_history(args.history) if args.history else None,
                                                         window=args.surprise_window,
                                                         entity=args.entity or infer_entity(rows)))
    for note in table.inferences:
        print("[comparison intake] " + display_text(note), file=sys.stderr)
    for comparison in table.comparisons:
        if comparison.result is not None:
            for note in metric_inferences(comparison.result.rows, comparison.result.config):
                print("[measure intake] " + display_text(note), file=sys.stderr)
    if args.check_only:
        print(f"Validation passed: {len(rows)} rows, {len(bases)} comparison(s).")
        return 0
    report = render_comparisons(table) if args.output or args.preset != "quant" else ""
    outputs: dict[Path, str | bytes] = {}
    if args.output:
        outputs[Path(args.output)] = report
    if args.xlsx:
        outputs[Path(args.xlsx)] = render_comparison_xlsx(table)
    if args.audit_json:
        record = build_comparison_audit(table, source_name=path.name, source_sha256=sha256_bytes(source_bytes),
                                        schema_version=args.audit_schema_version, source_worksheet=worksheet)
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
    if not args.output and args.preset != "quant":
        print(report)
    return 0


def _surprise_window(value: str) -> int:
    try:
        window = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Surprise window must be an integer, minimum of 4.") from exc
    if window < 4:
        raise argparse.ArgumentTypeError(f"A surprise window of {window} is below the minimum of 4.")
    return window


if __name__ == "__main__":
    raise SystemExit(main())
