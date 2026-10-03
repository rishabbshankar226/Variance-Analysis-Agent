"""Exercise the installed console script in a clean, non-editable environment."""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import variance_agent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--without-excel", action="store_true")
    args = parser.parse_args()
    assert importlib.metadata.version("variance-analysis-agent") == variance_agent.__version__
    root = Path(__file__).resolve().parents[1]
    assert root / "src" not in Path(variance_agent.__file__).resolve().parents
    command = Path(sys.executable).parent / ("variance-agent.exe" if os.name == "nt"
                                             else "variance-agent")
    assert command.is_file(), "Installed console entry point is missing"
    if args.without_excel:
        assert importlib.util.find_spec("openpyxl") is None
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        help_run = subprocess.run([str(command), "--help"], cwd=work, capture_output=True,
                                  text=True)
        assert help_run.returncode == 0, help_run.stderr
        assert "--currency" in help_run.stdout
        rows = [{"Line Item":"Sales", "Budget":"100", "Actual":"132"},
                {"Line Item":"Rent Expense", "Budget":"50", "Actual":"65"}]
        for suffix, content in (
            (".csv", "Line Item,Budget,Actual\nSales,100,132\nRent Expense,50,65\n"),
            (".json", json.dumps(rows)),
        ):
            source = work / f"input{suffix}"
            source.write_text(content, encoding="utf-8")
            report, audit = work / "report.md", work / "audit.json"
            subprocess.run([str(command), str(source), "--period", "Q3", "--dollar-threshold",
                            "1", "--percent-threshold", "5", "--output", str(report),
                            "--audit-json", str(audit)], cwd=work, check=True)
            record = json.loads(audit.read_text("utf-8"))
            assert record["totals"]["revenue"]["actual"] == "132"
            assert record["provenance"]["tool_version"] == variance_agent.__version__
            assert record["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
            assert "Reporting Currency: USD" in report.read_text("utf-8")
        if args.without_excel:
            source = work / "input.xlsx"
            source.write_bytes(b"not a workbook")
            run = subprocess.run([str(command), str(source), "--period", "Q3",
                                  "--dollar-threshold", "1", "--percent-threshold", "5"],
                                 cwd=work, capture_output=True, text=True)
            assert run.returncode == 2
            assert "optional dependency" in run.stderr
    print(f"Installed {variance_agent.__version__}: console, CSV/JSON, audit provenance verified")


if __name__ == "__main__":
    main()
