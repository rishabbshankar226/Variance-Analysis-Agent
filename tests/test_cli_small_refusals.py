"""X28, X29: a malformed mapping and a check-only run with long outputs refuse plainly (fictional data)."""

from __future__ import annotations

from pathlib import Path

import pytest

from variance_agent import cli

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_variance.csv"
NUMBERS = ["--period", "Q3", "--dollar-threshold", "10", "--percent-threshold", "5"]


def _err(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)
    assert stopped.value.code == 2
    return capsys.readouterr().err.replace("\n", " ")


@pytest.mark.parametrize(("content", "message"), [
    (b"{oops", "Mapping file is not valid JSON at line 1, column 2. Save it again from the chat (\"save mapping\"), "
               "or fix the JSON there."),
    (b"\xff\xfe{}", "Mapping file is not UTF-8 text."),
    (b"[]", "Mapping file must be a JSON object."),
])
def test_a_malformed_mapping_says_mapping_file(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes, message: str) -> None:
    mapping = tmp_path / "m.json"
    mapping.write_bytes(content)
    assert message in _err([str(SAMPLE), *NUMBERS, "--mapping", str(mapping), "-o", str(tmp_path / "r.md")], capsys)


@pytest.mark.parametrize("flag", ["--long-output", "--long-output-jsonl"])
def test_check_only_refuses_a_long_output(tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: str) -> None:
    out = tmp_path / "long.out"
    err = _err([str(SAMPLE), *NUMBERS, "--check-only", flag, str(out)], capsys)
    assert ("--check-only cannot be combined with --output, --audit-json, --xlsx, --long-output or "
            "--long-output-jsonl.") in err
    assert not out.exists()


def test_check_only_alone_still_validates(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([str(SAMPLE), *NUMBERS, "--check-only"]) == 0
    assert "Validation passed" in capsys.readouterr().out
