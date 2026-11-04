"""Wei's batch run: every filing in a folder read as a single run reads one (docs/improve/PLAN.md, N2).

Each filing goes through the CLI's own single-filing run (`--assisted --long-output`), so its rows, refusals and
messages are exactly a single run's. The batch adds only a `file` column to those rows and a manifest with one row per
filing. A refusal records the message a single run prints; any other exception records `error` with its type, and the
batch goes on to the next filing. No arithmetic happens here.
"""

from __future__ import annotations

import csv
import io
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from .audit import sha256_bytes
from .json_types import JSONObject
from .long_output import LONG_FIELDS, _NUMERIC, _csv
from .output import write_text_outputs

FILING_SUFFIXES = (".htm", ".html", ".pdf")
MANIFEST_FIELDS = ("file", "source_sha256", "outcome", "rows", "message")


def filings(folder: Path) -> list[Path]:
    """The filings directly in a folder, by name; hidden files, subfolders and other kinds are left alone."""
    return sorted((path for path in folder.iterdir()
                   if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in FILING_SUFFIXES),
                  key=lambda path: path.name)


def _refusal(stderr: str) -> str:
    """The message a refused single run printed, without the program's prefix."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    said = next((line for line in reversed(lines) if line.startswith("variance-agent: error: ")), None)
    return said.removeprefix("variance-agent: error: ") if said is not None else " ".join(lines)


def run_batch(folder: Path, single: list[str], long_output: Path, manifest: Path) -> int:
    """Read every filing in `folder` with the single-run options `single`; 0 when all read, 2 when any did not."""
    from .cli import main
    found = filings(folder)
    if not found:
        raise ValueError(f"No .htm, .html or .pdf filings in '{folder}'. Put the filings to read directly in that folder.")
    for flag, target in (("--long-output", long_output), ("--manifest", manifest)):
        for filing in found:
            if target.resolve() == filing.resolve():
                raise ValueError(f"{flag} '{target}' would overwrite the filing '{filing.name}'. Choose another path.")
    rows: list[JSONObject] = []
    entries: list[JSONObject] = []
    fields: tuple[str, ...] = LONG_FIELDS
    with tempfile.TemporaryDirectory() as staging:
        out, report = Path(staging, "long.csv"), Path(staging, "report.md")
        for filing in found:
            entry: JSONObject = {"file": filing.name, "source_sha256": sha256_bytes(filing.read_bytes()),
                                        "outcome": "ok", "rows": 0, "message": ""}
            entries.append(entry)
            said = io.StringIO()
            try:
                with redirect_stderr(said), redirect_stdout(io.StringIO()):
                    code = main([str(filing), "--assisted", *single, "--long-output", str(out), "-o", str(report)])
            except SystemExit:
                entry.update(outcome="refused", message=_refusal(said.getvalue()))
                continue
            except Exception as exc:  # recorded, and the batch goes on (N2)
                entry.update(outcome="error", message=f"{type(exc).__name__}: {exc}")
                continue
            if code != 0:
                entry.update(outcome="refused", message=_refusal(said.getvalue()))
                continue
            reader = csv.DictReader(io.StringIO(out.read_text(encoding="utf-8")))
            fields = tuple(reader.fieldnames or fields)
            mine = list(reader)
            rows.extend({"file": filing.name, **row} for row in mine)
            entry["rows"] = len(mine)
            out.unlink()
    write_text_outputs({long_output: _csv(("file", *fields), rows, _NUMERIC),
                        manifest: _csv(MANIFEST_FIELDS, entries, {"rows"})})
    return 0 if all(entry["outcome"] == "ok" for entry in entries) else 2
