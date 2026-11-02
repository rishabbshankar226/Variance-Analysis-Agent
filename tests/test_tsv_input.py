"""X15: tab-separated files read with --assisted on every path, and refuse plainly without it (fictional)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from variance_agent import cli

PASTED = Path(__file__).resolve().parent / "fixtures" / "realworld" / "fixture_i_pasted_tsv.txt"
NUMBERS = ["--period", "Q3", "--dollar-threshold", "10", "--percent-threshold", "5"]


def _tsv(tmp_path: Path) -> Path:
    path = tmp_path / "pasted.tsv"
    shutil.copy(PASTED, path)
    return path


def test_a_tsv_reads_with_assisted(tmp_path: Path) -> None:
    report = tmp_path / "r.md"
    assert cli.main([str(_tsv(tmp_path)), "--assisted", *NUMBERS, "-o", str(report)]) == 0
    assert "## Executive Summary" in report.read_text(encoding="utf-8")


def test_a_tsv_reads_on_the_comparison_path(tmp_path: Path) -> None:
    path = tmp_path / "consensus.tsv"
    path.write_text("Line Item\tActual\tConsensus\nFictional Revenue\t120\t100\n", encoding="utf-8")
    report = tmp_path / "r.md"
    assert cli.main([str(path), "--assisted", "--preset", "earnings", "--compare-to", "consensus", *NUMBERS,
                     "-o", str(report)]) == 0
    assert "Fictional Revenue" in report.read_text(encoding="utf-8")


def test_a_tsv_without_assisted_says_how_to_read_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.main([str(_tsv(tmp_path)), *NUMBERS])
    assert ("Tab-separated files are read with --assisted, which detects the delimiter and lists every adjustment "
            "it makes.") in capsys.readouterr().err.replace("\n", " ")


def test_an_unknown_format_lists_every_format_that_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "notes.docx"
    path.write_bytes(b"fictional")
    with pytest.raises(SystemExit):
        cli.main([str(path), *NUMBERS])
    assert ("Unsupported input format '.docx'. Use CSV, JSON, XLSX, XLSM or XLS; with --assisted, also TSV, PDF or "
            "an EDGAR .htm filing.") in capsys.readouterr().err.replace("\n", " ")
