"""S3 characterization: every documented `variance-agent` command, run through `cli.main`.

Phase 4 splits `cli._run` into parse, read, analyse and write stages without changing behaviour (docs/improve/PLAN.md,
S3). Each command runs in an empty temporary directory holding copies of the repository inputs it names, at the
paths the documentation gives. Its stdout, stderr, exit code and every file it writes are compared with the snapshot
taken before the split: a text file whole, a workbook by a digest of each of its parts.

Commands come from README.md's ```sh blocks and its `--type-map examples/type_map.json`, the parser's epilog,
docs/api.md, docs/input-contract.md and the analyst guides under docs/analysts/. Each guide's command runs twice: as
the guide prints it, and as its reader ran it with -o and --audit-json (docs/analysts/evidence/stop-2/readers/*/
commands.txt; Owen's case run names the guide's owen_case_metrics.json). The docs/input-contract.md examples whose
inputs are not in the repository (exports/..., plan.csv, filings/...) run too and record the missing-input refusal.

Not run:
- `variance-agent --chat`, `--chat --no-browser` and `--chat --hosted` (README.md): a long-running server and a browser.
- README.md's install, test and release commands (python -m venv, pip install, pytest, ruff, mypy, compileall, build,
  twine, scripts/check_*.py): not `variance-agent` commands, and pip needs the network.
- Placeholders that name no file: `variance-agent FILE ...` (README.md), `actuals.csv --assisted --compare-file
  budget.csv` and `<10-Q .htm> --assisted --ltm-from <10-K .htm>` (docs/input-contract.md).
- docs/MULTI_AUDIENCE_2026-10.md's four commands: the README.md commands again, the panel one with output paths under
  /workspace/scratch instead of the working directory.
- Plans, QA logs, prompts and audit evidence (docs/*/PLAN.md, docs/analysts/REPORT.md, docs/qa/, docs/prompts/,
  docs/ui/, docs/improve/evidence/, docs/analysts/evidence/stop-ask-*/): records naming placeholders (<fixture>, FILE,
  act.csv) or scratch inputs outside the repository.

Regenerate the snapshot only for an approved behaviour change:
    .venv/bin/python -c "from tests.test_characterization_s3 import write; write()"
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shlex
import shutil
import tempfile
import zipfile
from pathlib import Path

from variance_agent.cli import main

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "tests" / "fixtures" / "characterization" / "s3_cli.json"
MA = "tests/fixtures/multi_audience/"
AN = "tests/fixtures/analysts/"
INPUT_FLAGS = {"--type-map", "--mapping", "--compare-file", "--ltm-from", "--metrics", "--panel", "--history"}
REPORTED = "-o report.md --audit-json audit.json"  # how the analyst guides' readers ran each command

THEO = f"{AN}theo_benchmark.csv --assisted --compare-to benchmark --period 'Oct 2026' --dollar-threshold 1 " \
       "--percent-threshold 1 --percent-values points --bps-threshold 1"
INES = f"{AN}ines_limits.csv --assisted --compare-to limit --period 'Oct 2026' --dollar-threshold 1 --percent-threshold 1"
CLARA_BS = f"{AN}hal-20250927.htm --assisted --sheet 'Consolidated Balance Sheets' --compare-to prior-period " \
           "--period 'Sep 2025' --dollar-threshold 1 --percent-threshold 1"
CLARA_CF = f"{AN}hal-20250927.htm --assisted --sheet 'Consolidated Statements of Cash Flows' --compare-to prior-period " \
           "--period FY2025 --dollar-threshold 1 --percent-threshold 1"
CLARA_COVENANTS = f"{AN}hal-20250927.htm --assisted --metrics {AN}clara_metrics.json --compare-file {AN}clara_covenants.csv " \
                  "--compare-to limit --period FY2025 --dollar-threshold 1 --percent-threshold 1 --multiple-threshold 0.1"
MARCUS_TARGETS = f"{AN}marcus_targets.csv --assisted --compare-to target --period 'Oct 2026' --dollar-threshold 1 " \
                 "--percent-threshold 1 --percent-values points --bps-threshold 1"
MARCUS_SCORECARD = f"{AN}marcus_holdings.csv --assisted --panel {AN}marcus_panel.csv --join-key Ticker " \
                   "--deciding-metric 'Diluted EPS' --period 'Q3 2026' --dollar-threshold 1 --percent-threshold 1 " \
                   "--per-share-threshold 0.01"
OWEN_LTM = f"{AN}hal-20260328.htm --assisted --ltm-from {AN}hal-20250927.htm --period 'LTM Mar 2026' " \
           "--dollar-threshold 1 --percent-threshold 1"
OWEN_CASE = f"{AN}hal-20260328.htm --assisted --ltm-from {AN}hal-20250927.htm --metrics {AN}owen_case_metrics.json " \
            f"--compare-file {AN}owen_case.csv --period 'LTM Mar 2026' --dollar-threshold 1 --percent-threshold 1"

# (where it is documented, the command after `variance-agent`)
COMMANDS: list[tuple[str, str]] = [
    ("README.md quick start", "examples/sample_variance.csv --period 'Q3 2026' --dollar-threshold 10000 --percent-threshold 5 "
                              "--output reports/q3-2026.md --audit-json reports/q3-2026.audit.json --xlsx reports/q3-2026.xlsx"),
    ("README.md check-only", "examples/sample_variance.csv --period 'Q3 2026' --dollar-threshold 10000 --percent-threshold 5 "
                             "--check-only"),
    ("README.md --type-map", "examples/sample_variance.csv --period 'Q3 2026' --dollar-threshold 10000 --percent-threshold 5 "
                             "--type-map examples/type_map.json --output reports/q3-2026.md --audit-json reports/q3-2026.audit.json"),
    ("README.md fpa", f"{MA}fpa.csv --period 3Q26 --dollar-threshold 10 --percent-threshold 2"),
    ("README.md earnings consensus", f"{MA}consensus.csv --preset earnings --compare-to consensus --period 3Q26 "
                                     "--dollar-threshold 10 --percent-threshold 2 --bps-threshold 25 --per-share-threshold 0.01 "
                                     "--count-threshold 1000"),
    ("README.md comparison set", f"{MA}comparison_set.csv --preset earnings --compare-to consensus,estimate,prior-period "
                                 "--period 3Q26 --dollar-threshold 10 --percent-threshold 2 --per-share-threshold 0.01"),
    ("README.md quant panel", f"{MA}panel.csv --preset quant --group-by Ticker,Period --compare-to consensus "
                              "--dollar-threshold 10 --percent-threshold 2 --bps-threshold 25 --per-share-threshold 0.01 "
                              "--count-threshold 1000 --long-output panel.csv --long-output-jsonl panel.jsonl --errors-output errors.csv"),
    ("README.md earnings outputs", f"{MA}consensus.csv --preset earnings --period 3Q26 --dollar-threshold 10 --percent-threshold 2 "
                                   "--bps-threshold 25 --per-share-threshold 0.01 --count-threshold 1000 "
                                   "-o earnings.md --xlsx earnings.xlsx --audit-json earnings.audit.json"),
    ("cli.py epilog", "examples/sample_variance.csv --period 'Q3 2026' --dollar-threshold 10000 --percent-threshold 5 -o report.md"),
    ("docs/api.md panel", f"{MA}panel.csv --group-by Ticker,Period --compare-to consensus --dollar-threshold 10 "
                          "--percent-threshold 2 --bps-threshold 25 --per-share-threshold 0.01 --count-threshold 1000 "
                          "--long-output panel.csv --long-output-jsonl panel.jsonl --errors-output errors.csv"),
    ("docs/input-contract.md currency", "examples/sample_eur.csv --period 'Q3 2026' --currency EUR --dollar-threshold 100 "
                                        "--percent-threshold 5 --output report.md --audit-json audit.json"),
    ("docs/input-contract.md check-only", "examples/sample_variance.csv --period 'Q3 2026' --dollar-threshold 100 "
                                          "--percent-threshold 5 --check-only"),
    ("docs/input-contract.md assisted xlsx", "exports/raw_erp_dump.xlsx --assisted --period 'Q3 2026' --dollar-threshold 10000 "
                                             "--percent-threshold 5"),
    ("docs/input-contract.md assisted csv", "exports/10k_extract.csv --assisted --period 'FY2025' --dollar-threshold 10000 "
                                            "--percent-threshold 5"),
    ("docs/input-contract.md forecast", "plan.csv --period 'Q3 2026' --compare-to forecast --dollar-threshold 10000 "
                                        "--percent-threshold 5"),
    ("docs/input-contract.md pdf", "filings/10-K-2025.pdf --assisted --period 'FY2025' --dollar-threshold 100000 "
                                   "--percent-threshold 5 --audit-json audit.json"),
    ("docs/analysts/theo.md", THEO),
    ("docs/analysts/ines.md", INES),
    ("docs/analysts/clara.md balance sheet", CLARA_BS),
    ("docs/analysts/clara.md cash flow", CLARA_CF),
    ("docs/analysts/clara.md covenants", CLARA_COVENANTS),
    ("docs/analysts/marcus.md targets", MARCUS_TARGETS),
    ("docs/analysts/marcus.md scorecard", MARCUS_SCORECARD),
    ("docs/analysts/owen.md LTM", OWEN_LTM),
    ("docs/analysts/owen.md case", OWEN_CASE),
    ("stop-2 readers theo", f"{THEO} {REPORTED}"),
    ("stop-2 readers ines", f"{INES} {REPORTED}"),
    ("stop-2 readers clara balance sheet", f"{CLARA_BS} {REPORTED}"),
    ("stop-2 readers clara cash flow", f"{CLARA_CF} {REPORTED}"),
    ("stop-2 readers clara covenants", f"{CLARA_COVENANTS} {REPORTED}"),
    ("stop-2 readers marcus targets", f"{MARCUS_TARGETS} {REPORTED}"),
    ("stop-2 readers owen LTM", f"{OWEN_LTM} {REPORTED}"),
    ("stop-2 readers owen case", f"{OWEN_CASE} {REPORTED}"),
]


def _inputs(argv: list[str]) -> list[str]:
    """The repository files a command reads: its input and each input flag's value."""
    named = [argv[0]] + [value for flag, value in zip(argv, argv[1:], strict=False) if flag in INPUT_FLAGS]
    return [name for name in named if (ROOT / name).is_file()]


def _normalise(text: str, here: Path, argv: list[str]) -> str:
    """The temporary directory as <tmp>, and on Windows each relative path the command names as it was typed."""
    for spelling in sorted({str(here.resolve()), str(here)}, key=len, reverse=True):  # /private/var/... before /var/...
        text = text.replace(spelling, "<tmp>")
    text = text.replace(str(ROOT), "<repo>")
    if os.sep != "/":  # Windows prints a path given as a/b as a\b, and a repr doubles the backslash
        for name in (arg for arg in argv if "/" in arg):
            text = text.replace(repr(str(Path(name)))[1:-1], name).replace(str(Path(name)), name)
    return text


def _contents(path: Path, here: Path, argv: list[str]) -> object:
    data = path.read_bytes()
    if path.suffix.lower() == ".xlsx":  # each part's digest, so a zlib build's own compression is not compared
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {name: hashlib.sha256(archive.read(name)).hexdigest() for name in sorted(archive.namelist())}
    return _normalise(data.decode("utf-8").replace(os.linesep, "\n"), here, argv)  # text mode writes os.linesep


def run(command: str) -> dict[str, object]:
    argv = shlex.split(command)
    with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
        here = Path(tmp)
        copied = _inputs(argv)
        for name in copied:
            (here / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, here / name)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code: object = main(argv)
            except SystemExit as exc:
                code = exc.code
            except Exception as exc:  # recorded, so a change in what escapes main is seen too
                code = f"raised {type(exc).__name__}: {exc}"
        written = {path.relative_to(here).as_posix(): _contents(path, here, argv) for path in sorted(here.rglob("*"))
                   if path.is_file() and path.relative_to(here).as_posix() not in copied}
        return {"command": command, "exit": code, "stdout": _normalise(out.getvalue(), here, argv),
                "stderr": _normalise(err.getvalue(), here, argv), "files": written}


def snapshot() -> dict[str, object]:
    found = {source: run(command) for source, command in COMMANDS}
    return json.loads(json.dumps(found, default=str))  # type: ignore[no-any-return]


def write() -> None:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def test_every_documented_command_runs_as_before_the_split() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = snapshot()
    assert list(actual) == list(expected) == [source for source, _ in COMMANDS]
    for source in expected:
        assert actual[source] == expected[source], source
