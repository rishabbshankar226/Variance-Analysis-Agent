"""X8: what the comparison path cannot do, it refuses; a filing keeps its printed totals there (fictional files)."""

from __future__ import annotations

from pathlib import Path

import pytest

from variance_agent import cli

ANALYSTS = Path(__file__).resolve().parent / "fixtures" / "analysts"
TEN_Q, TEN_K = ANALYSTS / "hal-20260328.htm", ANALYSTS / "hal-20250927.htm"
NUMBERS = ["--dollar-threshold", "1", "--percent-threshold", "1"]


def _refusal(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)
    assert stopped.value.code == 2
    return capsys.readouterr().err.replace("\n", " ")


def test_the_ltm_run_still_builds_ltm(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    assert cli.main([str(TEN_Q), "--assisted", "--ltm-from", str(TEN_K), "--period", "LTM Mar 2026", *NUMBERS,
                     "-o", str(report)]) == 0
    assert "## LTM build" in report.read_text(encoding="utf-8")


@pytest.mark.parametrize(("extra", "named"), [
    (["--layout", "standard"], "--layout"),
    (["--long-output", "LONG"], "--long-output"),
    (["--layout", "standard", "--long-output", "LONG"], "--layout and --long-output"),
])
def test_an_export_or_layout_flag_with_ltm_refuses(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], named: str) -> None:
    extra = [str(tmp_path / "l.csv") if value == "LONG" else value for value in extra]
    err = _refusal([str(TEN_Q), "--assisted", "--ltm-from", str(TEN_K), "--period", "LTM Mar 2026", *NUMBERS, *extra,
                    "-o", str(tmp_path / "r.md")], capsys)
    verb = "they read" if " and " in named else "it reads"
    assert (f"{named} can't be combined with --ltm-from yet: {verb} the file another way, which doesn't build LTM. "
            f"Leave out {named}, or leave out --ltm-from.") in err
    assert not (tmp_path / "r.md").exists()


def test_a_limit_run_reads_alone_and_refuses_with_an_export_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = [str(ANALYSTS / "ines_limits.csv"), "--assisted", "--period", "Oct 2026", *NUMBERS]
    assert cli.main([*base, "--compare-to", "limit", "-o", str(tmp_path / "r.md")]) == 0
    err = _refusal([*base, "--compare-to", "limit", "--long-output", str(tmp_path / "l.csv")], capsys)
    assert ("--long-output can't be combined with --compare-to limit yet: it reads the file another way, which doesn't "
            "read Limit Kind, Buffer, Better or Tolerance. Leave out --long-output, or leave out --compare-to limit.") in err
    err = _refusal([*base, "--compare-to", "limit,benchmark"], capsys)
    assert "--compare-to limit, benchmark and target run one per run: give one of them alone." in err


def test_a_multiple_threshold_reaches_the_comparison_path(tmp_path: Path) -> None:
    data = tmp_path / "multiple.csv"
    data.write_text("Line Item,Measure,Better,Budget,Actual\nFictional leverage,Multiple,Lower,3.0x,3.5x\n", encoding="utf-8")
    long = tmp_path / "l.csv"
    assert cli.main([str(data), "--multiple-threshold", "0.1", "--period", "Q3", *NUMBERS, "--long-output", str(long),
                     "-o", str(tmp_path / "r.md")]) == 0
    assert "Fictional leverage" in long.read_text(encoding="utf-8")


def test_a_filing_on_the_comparison_path_is_headed_by_its_printed_totals(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    assert cli.main([str(TEN_K), "--assisted", "--period", "FY2025", *NUMBERS, "--long-output", str(tmp_path / "l.csv"),
                     "-o", str(report)]) == 0
    text = report.read_text(encoding="utf-8")
    assert "Net operating variance" not in text and "- Total Revenue:" not in text
    assert "- Net sales: $4,100,000,000.00 vs. $3,900,000,000.00" in text


def test_a_filing_workbook_refuses_on_the_comparison_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    err = _refusal([str(TEN_K), "--assisted", "--period", "FY2025", *NUMBERS, "--layout", "standard",
                    "--xlsx", str(tmp_path / "w.xlsx"), "-o", str(tmp_path / "r.md")], capsys)
    assert "--xlsx isn't available for a filing's income statement yet" in err
    assert not (tmp_path / "w.xlsx").exists()
