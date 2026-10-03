"""Filesystem contracts exercised on both Linux and Windows CI runners."""

import os

import pytest

from variance_agent.cli import main


def arguments(source, report, audit):
    return [str(source), "--period", "Q3", "--dollar-threshold", "1",
            "--percent-threshold", "5", "--output", str(report), "--audit-json", str(audit)]


def test_hardlink_output_cannot_replace_an_input(tmp_path):
    source, report, audit = tmp_path/"source.csv", tmp_path/"report.md", tmp_path/"audit.json"
    original = "Line Item,Budget,Actual\nSales,10,12\n"
    source.write_text(original)
    os.link(source, audit)
    with pytest.raises(SystemExit) as error:
        main(arguments(source, report, audit))
    assert error.value.code == 2
    assert source.read_text() == audit.read_text() == original
    assert not report.exists()


def test_relative_path_alias_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path/"source.csv"
    source.write_text("Line Item,Budget,Actual\nSales,10,12\n")
    with pytest.raises(SystemExit) as error:
        main(arguments(source, "./source.csv", "audit.json"))
    assert error.value.code == 2
    assert not (tmp_path/"audit.json").exists()


def test_second_replace_failure_has_documented_partial_publication(tmp_path, monkeypatch):
    source, report, audit = tmp_path/"source.csv", tmp_path/"report.md", tmp_path/"audit.json"
    source.write_text("Line Item,Budget,Actual\nSales,10,12\n")
    report.write_text("old report")
    audit.write_text("old audit")
    replace = os.replace
    calls = 0
    def fail_second(first, second):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected second replacement failure")
        return replace(first, second)
    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(SystemExit) as error:
        main(arguments(source, report, audit))
    assert error.value.code == 2
    assert "# FP&A Variance Report" in report.read_text()
    assert audit.read_text() == "old audit"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["audit.json", "report.md", "source.csv"]
