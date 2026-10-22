"""Engine hardening found in the 2026-10 bug hunt: ambient Decimal context, speed, mapping files."""

from __future__ import annotations

import json
import time
from decimal import ROUND_DOWN, Decimal, localcontext
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.analysis import analyze_rows
from variance_agent.audit import build_audit_record
from variance_agent.intake import read_input_assisted
from variance_agent.models import AnalysisConfig

CFG = AnalysisConfig("Q3", Decimal("10"), Decimal("0.05"))


# --- Caller's Decimal context must not change results (VA-19 sibling) ---


def test_audit_record_ignores_the_ambient_decimal_context() -> None:
    rows: list[dict[str, object]] = [
        {"Line Item": "Sales", "Budget": Decimal("100.1234567"), "Actual": Decimal("120.2469134")},
        {"Line Item": "Rent", "Budget": Decimal("50"), "Actual": Decimal("70.1")},
        {"Line Item": "Misc", "Budget": Decimal("5"), "Actual": Decimal("5")},
    ]
    result = analyze_rows(rows, CFG)
    baseline = build_audit_record(result)
    with localcontext() as context:
        context.prec = 4
        context.rounding = ROUND_DOWN
        altered = build_audit_record(result)
    assert altered == baseline


def test_assisted_intake_ignores_the_ambient_decimal_context() -> None:
    data = (
        b"Budget Report (in thousands)\nLine Item,Type,Budget,Actual\n"
        b"Sales,Revenue,\"12,345,678.123456\",100\n"
    )
    baseline = read_input_assisted(data, ".csv", filename="t.csv")
    with localcontext() as context:
        context.prec = 8
        altered = read_input_assisted(data, ".csv", filename="t.csv")
    assert baseline.rows[0]["budget"] == Decimal("12345678123.456000")
    assert altered.rows == baseline.rows


# --- Subtotal detection must stay near-linear ---


def test_assisted_intake_of_a_large_ledger_is_fast() -> None:
    lines = ["Line Item,Budget,Actual"]
    lines += [f"Account {i},{(i * 37) % 9973 + 1},{(i * 53) % 9967 + 1}" for i in range(8000)]
    started = time.perf_counter()
    result = read_input_assisted("\n".join(lines).encode("utf-8"), ".csv", filename="big.csv")
    elapsed = time.perf_counter() - started
    assert not result.has_fatal_errors and len(result.rows) == 8000
    # About 0.4 s on a laptop; the quadratic version took 9.6 s here and far longer on a slow runner.
    assert elapsed < 5.0, f"8,000 rows took {elapsed:.1f}s (was 9.6s before the fix)"


def _reference_detect(rows: list[dict[str, object]]) -> tuple[list[tuple[object, ...]], list[tuple[object, ...]]]:
    """The original quadratic algorithm, kept as the oracle for the indexed implementation."""
    from variance_agent.intake import _TOTAL_KEYWORD_RE

    tol = Decimal("0.01")
    reconciled: list[tuple[str, Decimal, Decimal, int, str]] = []
    unreconciled: list[tuple[object, ...]] = []
    detail_rows: list[int] = []
    detail_values: list[tuple[Decimal, Decimal]] = []
    for i, row in enumerate(rows):
        name = str(row["line_item"]).strip()
        b, a = Decimal(str(row["budget"])), Decimal(str(row["actual"]))
        is_total_kw = bool(_TOTAL_KEYWORD_RE.search(name))
        found = False
        sum_b = sum_a = Decimal("0")
        for j in range(len(detail_rows) - 1, -1, -1):
            length = len(detail_rows) - j
            sum_b += detail_values[j][0]
            sum_a += detail_values[j][1]
            if abs(b - sum_b) <= tol and abs(a - sum_a) <= tol and (length >= 2 or is_total_kw):
                reconciled.append((name, b, a, i, f"sum of {length} detail rows"))
                found = True
                break
        if found:
            continue
        prior = list(reconciled)
        for prev in prior:
            hit = next(
                (d for d, (db, da) in zip(detail_rows, detail_values)
                 if abs((prev[1] - db) - b) <= tol and abs((prev[2] - da) - a) <= tol),
                None,
            )
            if hit is not None:
                reconciled.append((name, b, a, i, f"{prev[0]} - {rows[hit]['line_item']}"))
                found = True
                break
            other = next(
                (p2 for p2 in prior if p2[3] != prev[3]
                 and abs((prev[1] - p2[1]) - b) <= tol and abs((prev[2] - p2[2]) - a) <= tol),
                None,
            )
            if other is not None:
                reconciled.append((name, b, a, i, f"{prev[0]} - {other[0]}"))
                found = True
                break
        if found:
            continue
        if is_total_kw:
            unreconciled.append((
                name, b, a, i,
                sum((v[0] for v in detail_values), Decimal("0")) if detail_rows else None,
                sum((v[1] for v in detail_values), Decimal("0")) if detail_rows else None,
            ))
        else:
            detail_rows.append(i)
            detail_values.append((b, a))
    return [tuple(r) for r in reconciled], unreconciled


def test_indexed_subtotal_detection_matches_the_reference_algorithm() -> None:
    import random

    from variance_agent.intake import detect_subtotals_and_totals

    rng = random.Random(20261021)
    pool = [Decimal(v) for v in (0, 0, 1, 2, 3, 5, 10, 100, 250)]
    for _ in range(400):
        rows: list[dict[str, object]] = []
        for i in range(rng.randint(1, 14)):
            roll = rng.random()
            if roll < 0.55 or not rows:
                budget, actual, name = rng.choice(pool), rng.choice(pool), f"Item {i}"
            elif roll < 0.8:
                block = rng.randint(1, min(4, len(rows)))
                budget = sum((Decimal(str(r["budget"])) for r in rows[-block:]), Decimal(0))
                actual = sum((Decimal(str(r["actual"])) for r in rows[-block:]), Decimal(0))
                name = rng.choice([f"Subtotal {i}", f"Group {i}", f"Total {i}"])
            else:
                budget = Decimal(rng.randint(0, 600)) / rng.choice([1, 100])
                actual = Decimal(rng.randint(0, 600)) / rng.choice([1, 100])
                name = rng.choice([f"Net Income {i}", f"Plug {i}"])
            rows.append({"line_item": name, "budget": budget, "actual": actual})
        expected_reconciled, expected_unreconciled = _reference_detect(rows)
        found = detect_subtotals_and_totals(rows)
        assert [
            (t.line_item, t.budget, t.actual, t.row_index, t.formula_description)
            for t in found.reconciled_totals
        ] == expected_reconciled
        assert [
            (t.line_item, t.budget, t.actual, t.row_index, t.sum_budget, t.sum_actual)
            for t in found.unreconciled_totals
        ] == expected_unreconciled


def test_subtotal_detection_still_finds_block_subtotals() -> None:
    body = (
        "Line Item,Budget,Actual\nProduct A,300,310\nProduct B,200,190\nRevenue Subtotal,500,500\n"
        "Rent,100,120\nUtilities,40,35\nTotal Expenses,140,155\n"
    )
    result = read_input_assisted(body.encode("utf-8"), ".csv", filename="t.csv")
    assert sorted(result.detected_totals) == ["Revenue Subtotal", "Total Expenses"]
    assert [r["line_item"] for r in result.rows] == ["Product A", "Product B", "Rent", "Utilities"]


# --- Assisted CSV reading keeps quoted newlines, finds delimiters and enforces limits ---


def test_quoted_newline_survives_assisted_csv_reading() -> None:
    data = b'Line Item,Budget,Actual\n"Marketing\nExpense",100,120\nRent,50,50\n'
    result = read_input_assisted(data, ".csv", filename="t.csv")
    assert not result.has_fatal_errors
    assert result.rows[0]["line_item"] == "Marketing\nExpense"


@pytest.mark.parametrize("delimiter", [";", "\t"])
def test_semicolon_and_tab_delimited_csv_files_are_read(delimiter: str) -> None:
    text = delimiter.join(["Line Item", "Type", "Budget", "Actual"]) + "\n"
    text += delimiter.join(["Sales", "Revenue", "100", "120"]) + "\n"
    text += delimiter.join(["Rent", "Expense", "50", "70"]) + "\n"
    result = read_input_assisted(text.encode("utf-8"), ".csv", filename="t.csv")
    assert not result.has_fatal_errors
    assert [r["line_item"] for r in result.rows] == ["Sales", "Rent"]


def test_row_numbers_in_messages_count_physical_lines_including_blank_ones() -> None:
    data = b"Line Item,Budget,Actual\nRent,50,50\n\n\nFees,10,oops\n"
    result = read_input_assisted(data, ".csv", filename="t.csv")
    assert result.fatal_error_message is not None
    assert "Row 5" in result.fatal_error_message


def test_assisted_csv_enforces_the_row_limit() -> None:
    from variance_agent import limits

    rows = limits.MAX_ROWS + 1
    data = ("Line Item,Budget,Actual\n" + "x,1,1\n" * rows).encode("utf-8")
    result = read_input_assisted(data, ".csv", filename="t.csv")
    assert result.has_fatal_errors
    assert result.fatal_error_message is not None and "row" in result.fatal_error_message.lower()


# --- Mapping files are validated, not trusted ---


def _write_mapping(path: Path, **overrides: object) -> Path:
    mapping: dict[str, object] = {
        "header_row_number": 1,
        "column_mapping": {"line_item": "Line Item", "budget": "Budget", "actual": "Actual"},
        "unit_scale": "1",
        "flip_signs": False,
        "exclude_totals": [],
    }
    mapping.update(overrides)
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


def _run(tmp_path: Path, mapping: Path) -> int:
    source = tmp_path / "in.csv"
    source.write_text("Line Item,Type,Budget,Actual\nRent,Expense,100,90\n", encoding="utf-8")
    try:
        return cli.main([
            str(source), "--mapping", str(mapping), "--period", "Q3", "--dollar-threshold", "10",
            "--percent-threshold", "5", "-o", str(tmp_path / "r.md"),
        ])
    except SystemExit as exit_info:
        return int(exit_info.code or 0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"unit_scale": "0"},
        {"unit_scale": "-1000"},
        {"unit_scale": "abc"},
        {"column_mapping": 5},
        {"exclude_totals": 5},
        {"header_row_number": 0},
        {"classification_rules": {"gl_ranges": [{"min": 1}]}},
        {"classification_rules": {"keywords": {"Rent": "BOGUS"}}},
    ],
)
def test_malformed_mapping_files_exit_2_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], overrides: dict[str, object],
) -> None:
    mapping = _write_mapping(tmp_path / "m.json", **overrides)
    assert _run(tmp_path, mapping) == 2
    err = capsys.readouterr().err
    error_line = err.strip().splitlines()[-1]  # the usage banner above it also names --mapping
    assert "Traceback" not in err
    assert error_line.startswith("variance-agent: error: Mapping file")


def test_oversized_mapping_file_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mapping = tmp_path / "m.json"
    mapping.write_text(" " * (2 * 1024 * 1024) + "{}", encoding="utf-8")
    assert _run(tmp_path, mapping) == 2
    assert "too large" in capsys.readouterr().err.lower()


def test_mapping_rules_are_spelled_canonically_so_the_audit_validates() -> None:
    from variance_agent.mapping import load_mapping

    loaded = load_mapping(json.dumps({
        "classification_rules": {
            "gl_ranges": [{"min": 4000, "max": 4999, "type": "revenue"}],
            "keywords": {"Rent": "expense"},
            "bulk_default": "EXPENSE",
        },
    }))
    assert loaded.classification_rules == {
        "gl_ranges": [{"min": 4000, "max": 4999, "type": "Revenue"}],
        "keywords": {"Rent": "Expense"},
        "bulk_default": "Expense",
    }


def test_type_map_overriding_mapping_rules_is_announced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    mapping = _write_mapping(tmp_path / "m.json", classification_rules={"keywords": {"Rent": "Expense"}})
    type_map = tmp_path / "types.json"
    type_map.write_text(json.dumps({"Rent": "Expense"}), encoding="utf-8")
    source = tmp_path / "in.csv"
    source.write_text("Line Item,Type,Budget,Actual\nRent,Expense,100,90\n", encoding="utf-8")
    code = cli.main([
        str(source), "--mapping", str(mapping), "--type-map", str(type_map), "--period", "Q3",
        "--dollar-threshold", "10", "--percent-threshold", "5", "-o", str(tmp_path / "r.md"),
    ])
    assert code == 0
    assert "--type-map is used" in capsys.readouterr().err
