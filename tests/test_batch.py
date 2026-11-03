"""N2: Wei's batch run over a folder of filings (fictional Inline XBRL filings built here)."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import pytest

from tests.fixtures.ixbrl.build_ixbrl import income_filing
from tests.test_ixbrl_statements_elsewhere import _without_statements
from variance_agent import cli

NUMBERS = ["--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "1"]
QUARTER = Path(__file__).resolve().parent / "fixtures" / "analysts" / "hal-20260328.htm"


def _folder(tmp_path: Path) -> Path:
    folder = tmp_path / "filings"
    folder.mkdir()
    (folder / "alpha-20250927.htm").write_bytes(income_filing())
    (folder / "beta-20260328.htm").write_bytes(QUARTER.read_bytes())
    (folder / "gamma-20250927.htm").write_bytes(_without_statements())
    (folder / "notes.txt").write_text("not a filing", encoding="utf-8")
    (folder / ".hidden.htm").write_bytes(income_filing())
    return folder


def _batch(tmp_path: Path, folder: Path, *extra: str) -> tuple[int, list[dict[str, str]], list[dict[str, str]]]:
    long, manifest = tmp_path / "batch.csv", tmp_path / "manifest.csv"
    code = cli.main(["--batch", str(folder), *NUMBERS, "--long-output", str(long), "--manifest", str(manifest), *extra])
    read = lambda path: list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))  # noqa: E731
    return code, read(long), read(manifest)


def _single(tmp_path: Path, filing: Path) -> list[dict[str, str]]:
    out = tmp_path / f"single-{filing.stem}.csv"
    assert cli.main([str(filing), "--assisted", *NUMBERS, "--long-output", str(out), "-o", str(tmp_path / "r.md")]) == 0
    return list(csv.DictReader(io.StringIO(out.read_text(encoding="utf-8"))))


def test_a_batch_reads_each_filing_and_records_one_that_refuses(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    code, rows, manifest = _batch(tmp_path, folder)
    assert code == 2
    assert [(m["file"], m["outcome"]) for m in manifest] == [
        ("alpha-20250927.htm", "ok"), ("beta-20260328.htm", "ok"), ("gamma-20250927.htm", "refused")]
    assert manifest[2]["message"].startswith("I could not find the financial statements in 'gamma-20250927.htm'")
    for entry in manifest:
        assert entry["source_sha256"] == hashlib.sha256((folder / entry["file"]).read_bytes()).hexdigest()
    for name in ("alpha-20250927.htm", "beta-20260328.htm"):
        mine = [{k: v for k, v in row.items() if k != "file"} for row in rows if row["file"] == name]
        assert mine == _single(tmp_path, folder / name)
        assert int(next(m["rows"] for m in manifest if m["file"] == name)) == len(mine)
    assert list(rows[0])[0] == "file"


def test_a_batch_where_every_filing_reads_exits_0(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    (folder / "gamma-20250927.htm").unlink()
    code, _, manifest = _batch(tmp_path, folder)
    assert code == 0 and {m["outcome"] for m in manifest} == {"ok"}


def test_an_unexpected_exception_is_an_error_and_the_batch_goes_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from variance_agent import comparisons
    real = comparisons.read_comparison_input

    def flaky(data, suffix, *, filename="input", **options):  # type: ignore[no-untyped-def]
        if filename.startswith("alpha"):
            raise KeyError("boom")  # not a refusal a single run turns into a message
        return real(data, suffix, filename=filename, **options)
    monkeypatch.setattr(comparisons, "read_comparison_input", flaky)
    code, rows, manifest = _batch(tmp_path, _folder(tmp_path))
    assert code == 2
    assert (manifest[0]["outcome"], manifest[0]["message"]) == ("error", "KeyError: 'boom'")
    assert manifest[1]["outcome"] == "ok" and {row["file"] for row in rows} == {"beta-20260328.htm"}


def test_a_filing_named_like_a_formula_is_protected(tmp_path: Path) -> None:
    folder = tmp_path / "filings"
    folder.mkdir()
    (folder / "=x.htm").write_bytes(income_filing())
    code, rows, manifest = _batch(tmp_path, folder)
    assert code == 0 and manifest[0]["file"] == "'=x.htm" and rows[0]["file"] == "'=x.htm"


def test_an_empty_folder_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    with pytest.raises(SystemExit) as raised:
        _batch(tmp_path, folder)
    assert raised.value.code == 2
    assert f"No .htm, .html or .pdf filings in '{folder}'" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [["-o", "r.md"], ["--xlsx", "w.xlsx"], ["--audit-json", "a.json"]])
def test_a_batch_refuses_a_single_runs_outputs(tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str]) -> None:
    with pytest.raises(SystemExit):
        _batch(tmp_path, _folder(tmp_path), *extra)
    assert f"--batch can't be combined with {extra[0]}" in capsys.readouterr().err


def test_a_batch_never_writes_over_a_filing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["--batch", str(folder), *NUMBERS, "--long-output", str(folder / "alpha-20250927.htm"),
                  "--manifest", str(tmp_path / "m.csv")])
    assert "would overwrite the filing" in capsys.readouterr().err
    assert (folder / "alpha-20250927.htm").read_bytes() == income_filing()
