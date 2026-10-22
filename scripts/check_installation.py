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
import threading
import urllib.request

import variance_agent


def check_chat_page(command: Path, work: Path) -> None:
    """Start the installed `--chat` server and fetch the page and its assets over HTTP."""
    process = subprocess.Popen([str(command), "--chat", "--no-browser"], cwd=work,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    watchdog = threading.Timer(30, process.kill)
    watchdog.start()
    try:
        assert process.stdout is not None
        banner = process.stdout.readline()
        assert "running at http://" in banner, f"chat server did not start: {banner!r}"
        base = banner.rsplit(" ", 1)[1].strip()
        with urllib.request.urlopen(f"{base}/", timeout=10) as page:
            assert page.status == 200
            html = page.read().decode("utf-8")
            policy = page.headers.get("Content-Security-Policy", "")
        assert "<title>Variance Analysis Agent</title>" in html
        assert "default-src 'self'" in policy and "unsafe-inline" not in policy
        for asset, kind in (("chat.js", "javascript"), ("chat.css", "css")):
            with urllib.request.urlopen(f"{base}/static/{asset}", timeout=10) as response:
                assert response.status == 200 and kind in response.headers["Content-Type"], asset
                assert len(response.read()) > 1000, f"{asset} is empty"
        with urllib.request.urlopen(f"{base}/status", timeout=10) as response:
            assert json.loads(response.read())["status"] == "ok"
    finally:
        watchdog.cancel()
        process.terminate()
        process.communicate(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--without-excel", action="store_true")
    parser.add_argument("--without-pdf", action="store_true")
    args = parser.parse_args()
    assert importlib.metadata.version("variance-analysis-agent") == variance_agent.__version__
    root = Path(__file__).resolve().parents[1]
    package_file = variance_agent.__file__
    assert package_file is not None
    assert root / "src" not in Path(package_file).resolve().parents
    command = Path(sys.executable).parent / ("variance-agent.exe" if os.name == "nt"
                                             else "variance-agent")
    assert command.is_file(), "Installed console entry point is missing"
    if args.without_excel:
        assert importlib.util.find_spec("openpyxl") is None
    if args.without_pdf:
        assert importlib.util.find_spec("pdfplumber") is None
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
        check_chat_page(command, work)
        if args.without_excel:
            source = work / "input.xlsx"
            source.write_bytes(b"not a workbook")
            run = subprocess.run([str(command), str(source), "--period", "Q3",
                                  "--dollar-threshold", "1", "--percent-threshold", "5"],
                                 cwd=work, capture_output=True, text=True)
            assert run.returncode == 2
            assert "optional dependency" in run.stderr
        if args.without_pdf:
            source = work / "filing.pdf"
            source.write_bytes(b"%PDF-1.4 not read without the PDF tools")
            run = subprocess.run([str(command), str(source), "--assisted", "--period", "FY2025",
                                  "--dollar-threshold", "1", "--percent-threshold", "5"],
                                 cwd=work, capture_output=True, text=True)
            assert run.returncode == 2
            assert "pip install 'variance-analysis-agent[pdf]'" in run.stderr
    print(f"Installed {variance_agent.__version__}: console, CSV/JSON, audit provenance, chat page verified")


if __name__ == "__main__":
    main()
