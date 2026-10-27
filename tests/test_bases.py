"""R13-R15: limit, benchmark and target bases (docs/analysts/PLAN.md). Every file here is fictional."""

from __future__ import annotations

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.fixtures.analysts.build_analysts import INES_LIMITS
from variance_agent import cli

ROOT = Path(__file__).resolve().parents[1]
HEADER = "Line Item,Actual,Limit,Limit Kind,Buffer\n"


def _run(tmp_path: Path, text: str, basis: str, *extra: str) -> tuple[dict[str, object], str]:
    path = tmp_path / "input.csv"
    path.write_text(text, encoding="utf-8")
    audit, report = tmp_path / "audit.json", tmp_path / "r.md"
    assert cli.main([str(path), "--assisted", "--compare-to", basis, "--period", "Oct 2026", "--dollar-threshold", "1",
                     "--percent-threshold", "1", "--audit-json", str(audit), "-o", str(report), *extra]) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads((ROOT / "schemas/audit-1.9.schema.json").read_text(encoding="utf-8"))).validate(record)
    return record, report.read_text(encoding="utf-8")


def _details(record: dict[str, object]) -> dict[str, dict[str, object]]:
    return {str(d["line_item"]): d for d in record["basis_details"]}  # type: ignore[union-attr, index]


# R13: limit -----------------------------------------------------------------------------------------


def test_ines_limits_are_labelled_and_ordered_by_severity(tmp_path: Path) -> None:
    record, report = _run(tmp_path, INES_LIMITS, "limit")
    assert (record["schema_version"], record["comparison"]["basis"], record["totals"]) == ("1.9", "limit", None)  # type: ignore[index]
    details = _details(record)
    assert {name: d["outcome"] for name, d in details.items()} == {
        "Desk A gross exposure": "Near", "Desk B gross exposure": "Breach", "Desk C liquidity reserve": "Breach",
        "Desk D liquidity reserve": "At limit", "Desk E net exposure": "Within"}
    # Fraction oracle: headroom is limit - actual for Max and actual - limit for Min; utilization actual / limit.
    for name, actual, limit, kind in [("Desk A gross exposure", 480, 500, "Max"), ("Desk B gross exposure", 510, 500, "Max"),
                                      ("Desk C liquidity reserve", 95, 100, "Min"), ("Desk D liquidity reserve", 100, 100, "Min"),
                                      ("Desk E net exposure", 300, 500, "Max")]:
        headroom = Fraction(limit - actual) if kind == "Max" else Fraction(actual - limit)
        assert Fraction(str(details[name]["headroom"])) == headroom, name
        assert Fraction(str(details[name]["utilization"])) == Fraction(actual, limit), name
    order = [line.split(" | ")[0].lstrip("| ") for line in report.splitlines() if line.startswith("| Desk")]
    assert order == ["Desk B gross exposure", "Desk C liquidity reserve", "Desk D liquidity reserve",
                     "Desk A gross exposure", "Desk E net exposure"]
    # Fraction oracle: headroom as a share of the limit's absolute value.
    assert Fraction(str(details["Desk B gross exposure"]["headroom_percent"])) == Fraction(-10, 500)
    assert {row["status"] for row in record["measure_rows"]} == {"Neutral"}  # type: ignore[union-attr, index]
    assert "**2 Breach, 1 At limit, 1 Near, 1 Within.**" in report
    for absent in ("Total Revenue", "Favorable", "Unfavorable", "Mitigation"):
        assert absent not in report


@pytest.mark.parametrize(("actual", "limit", "kind", "buffer", "outcome"), [
    ("500", "500", "Max", "", "At limit"),        # equal to the limit (Decision 38; section 3 said Within)
    ("500", "500", "Max", "25", "At limit"),      # equal, with a buffer
    ("500.01", "500", "Max", "25", "Breach"),     # one step beyond a Max
    ("499.99", "500", "Max", "25", "Near"),       # headroom 0.01 within the buffer
    ("475", "500", "Max", "25", "Near"),          # headroom equal to the buffer: Near
    ("474.99", "500", "Max", "25", "Within"),     # one step beyond the buffer
    ("99.99", "100", "Min", "10", "Breach"),      # one step below a Min
    ("100", "100", "Min", "10", "At limit"),
    ("110", "100", "Min", "10", "Near"),
    ("110.01", "100", "Min", "10", "Within"),
])
def test_limit_labels_straddle_each_boundary(tmp_path: Path, actual: str, limit: str, kind: str, buffer: str,
                                             outcome: str) -> None:
    record, _ = _run(tmp_path, HEADER + f"Line,{actual},{limit},{kind},{buffer}\n", "limit")
    assert _details(record)["Line"]["outcome"] == outcome


def test_a_zero_limit_has_no_utilization(tmp_path: Path) -> None:
    record, report = _run(tmp_path, HEADER + "Line,5,0,Max,\n", "limit")
    assert (_details(record)["Line"]["utilization"], _details(record)["Line"]["outcome"]) == (None, "Breach")
    assert "| NM |" in report


@pytest.mark.parametrize(("row", "message"), [
    ("Line,5,10,,", "Line: is the limit a Max or a Min? Supply Limit Kind as Max or Min."),
    ("Line,5,10,Cap,", "Line: Limit Kind must be Max or Min."),
    ("Line,5,10,Max,-1", "Line: Buffer must be zero or more, in the row's own unit."),
])
def test_limit_declarations_are_required_and_checked(tmp_path: Path, capsys: pytest.CaptureFixture[str], row: str,
                                                     message: str) -> None:
    path = tmp_path / "input.csv"
    path.write_text(HEADER + row + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--compare-to", "limit", "--period", "Oct", "--dollar-threshold", "1",
                  "--percent-threshold", "1"])
    assert message in capsys.readouterr().err.replace("\n", " ")


def test_a_limit_file_without_compare_to_is_not_half_of_a_pair(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "input.csv"
    path.write_text(INES_LIMITS, encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--period", "Oct", "--dollar-threshold", "1", "--percent-threshold", "1"])
    err = capsys.readouterr().err.replace("\n", " ")
    assert "This file has a 'Limit' column: compare against it with --compare-to limit." in err
    from variance_agent.chat.handlers import handle_upload
    from variance_agent.chat.session import Session
    reply = handle_upload(Session(), INES_LIMITS.encode(), "limits.csv")
    assert "join the two" not in reply.text


def test_an_older_audit_schema_cannot_record_a_limit_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "input.csv"
    path.write_text(INES_LIMITS, encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--compare-to", "limit", "--period", "Oct", "--dollar-threshold", "1",
                  "--percent-threshold", "1", "--audit-json", str(tmp_path / "a.json"), "--audit-schema-version", "1.8"])
    assert "Audit schema 1.8 cannot record a limit, benchmark or target comparison; use --audit-schema-version 1.9." in (
        capsys.readouterr().err.replace("\n", " "))


def test_a_limit_run_refuses_a_workbook(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "input.csv"
    path.write_text(INES_LIMITS, encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--compare-to", "limit", "--period", "Oct", "--dollar-threshold", "1",
                  "--percent-threshold", "1", "--xlsx", str(tmp_path / "o.xlsx")])
    assert "--xlsx isn't available for a limit, benchmark or target comparison yet" in capsys.readouterr().err.replace("\n", " ")


def test_strict_mode_points_the_new_bases_at_assisted_intake(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "input.csv"
    path.write_text(INES_LIMITS, encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--compare-to", "limit", "--period", "Oct", "--dollar-threshold", "1", "--percent-threshold", "1"])
    assert "--compare-to limit needs --assisted" in capsys.readouterr().err


def test_a_repeating_utilization_is_rounded_once_by_the_engine_s_ratio_policy(tmp_path: Path) -> None:
    from variance_agent.numeric import ratio
    record, _ = _run(tmp_path, HEADER + "Line,1.10,3.30,Max,\n", "limit")
    assert Decimal(str(_details(record)["Line"]["utilization"])) == ratio(Decimal("1.10"), Decimal("3.30"))


# R14: benchmark (Theo) ------------------------------------------------------------------------------

from tests.fixtures.analysts.build_analysts import MARCUS_TARGETS, THEO_BENCHMARK  # noqa: E402


def test_theo_active_returns_in_basis_points_above_or_below(tmp_path: Path) -> None:
    record, report = _run(tmp_path, THEO_BENCHMARK, "benchmark", "--percent-values", "points", "--bps-threshold", "1")
    details = _details(record)
    # Fraction oracle: active difference = actual - benchmark, in basis points for rates.
    assert Fraction(str(details["Fund return"]["difference_bps"])) == (Fraction("7.25") - Fraction("6.80")) * 100
    assert {n: d["outcome"] for n, d in details.items()} == {
        "Fund return": "Higher than benchmark", "Tracking fund return": "In line",
        "Management fee rate": "Higher than benchmark"}
    statuses = {row["line_item"]: row["status"] for row in record["measure_rows"]}  # type: ignore[union-attr, index]
    assert statuses == {"Fund return": "F", "Tracking fund return": "Neutral", "Management fee rate": "U"}
    assert "| Fund return | 6.8% | 7.25% | 45 bps | 10 bps | Higher than benchmark | Favorable |" in report
    assert "| Management fee rate | 0.8% | 0.82% | 2 bps | none (exact) | Higher than benchmark | Unfavorable |" in report


@pytest.mark.parametrize(("actual", "tolerance", "outcome"), [
    ("5.05%", "0.05", "In line"), ("5.06%", "0.05", "Higher than benchmark"), ("4.95%", "0.05", "In line"),
    ("4.94%", "0.05", "Lower than benchmark"), ("5.00%", "", "In line"), ("5.01%", "", "Higher than benchmark"),
    ("4.99%", "", "Lower than benchmark"),
])
def test_benchmark_in_line_straddles_its_tolerance(tmp_path: Path, actual: str, tolerance: str, outcome: str) -> None:
    text = f"Line Item,Actual,Benchmark,Better,Tolerance,Measure\nFund,{actual},5.00%,Higher,{tolerance},Percent\n"
    record, _ = _run(tmp_path, text, "benchmark", "--percent-values", "points", "--bps-threshold", "1")
    assert _details(record)["Fund"]["outcome"] == outcome


def test_a_benchmark_row_needs_a_better_direction(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "input.csv"
    path.write_text("Line Item,Actual,Benchmark\nFund,7,6\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--compare-to", "benchmark", "--period", "Oct", "--dollar-threshold", "1",
                  "--percent-threshold", "1"])
    assert ("Fund: is Higher or Lower better against the benchmark? Supply Better as Higher or Lower."
            in capsys.readouterr().err.replace("\n", " "))


# R15: target (Marcus) -------------------------------------------------------------------------------


def test_marcus_drift_from_target_weights_in_basis_points(tmp_path: Path) -> None:
    record, report = _run(tmp_path, MARCUS_TARGETS, "target", "--percent-values", "points", "--bps-threshold", "1")
    details = _details(record)
    assert {n: d["outcome"] for n, d in details.items()} == {
        "NORDVIK.FAKE": "Over", "HALVORSEN.FAKE": "On target", "OSTRAVA.FAKE": "Under"}
    assert Fraction(str(details["OSTRAVA.FAKE"]["difference_bps"])) == -100
    assert {row["status"] for row in record["measure_rows"]} == {"Neutral"}  # type: ignore[union-attr, index]
    assert "| OSTRAVA.FAKE | 6% | 5% | -100 bps | 25 bps | Under |" in report


def test_a_target_takes_no_better_direction(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "input.csv"
    path.write_text("Line Item,Actual,Target,Better\nHolding,5,6,Higher\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main([str(path), "--assisted", "--compare-to", "target", "--period", "Oct", "--dollar-threshold", "1",
                  "--percent-threshold", "1"])
    assert ("Holding: a target is neutral, so it takes no Better direction; remove Better for this row."
            in capsys.readouterr().err.replace("\n", " "))
