"""Write the reader guides in docs/analysts/ by running every command they show (PLAN.md, Phase 6).

Each guide is written from this script, so no guide shows a command that was not run or an output
that was not produced. Every input is fictional, from tests/fixtures/analysts/.

    .venv/bin/python docs/analysts/evidence/build_guides.py
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = "tests/fixtures/analysts"
TOOL = Path(sys.executable).parent / "variance-agent"

GUIDES: dict[str, tuple[str, str, list[tuple[str, str]], str]] = {
    "owen": (
        "Owen: LTM against the management case",
        "Owen is an investment banking analyst. He brings a target's last 10-K, its latest 10-Q and a management "
        "case, and asks for LTM revenue and EBITDA against the case and each statement year on year. He gets an LTM "
        "build with every component cited to its document and column, then the variance against the case. He never "
        "gets a valuation, multiples or enterprise value.",
        [("Build LTM from the 10-Q and the 10-K: the income statement's fiscal year plus this year to date less last "
          "year to date, line by line by XBRL concept, compared with the fiscal year.",
          f"{FIXTURES}/hal-20260328.htm --assisted --ltm-from {FIXTURES}/hal-20250927.htm --period 'LTM Mar 2026' "
          "--dollar-threshold 1 --percent-threshold 1"),
         ("Compare declared LTM revenue and EBITDA with the case. The metrics file names each term by XBRL concept "
          "and period; EBITDA here is net income plus interest plus D&A from the cash flow statement, as declared.",
          f"{FIXTURES}/hal-20260328.htm --assisted --ltm-from {FIXTURES}/hal-20250927.htm "
          f"--metrics {FIXTURES}/owen_case_metrics.json --compare-file {FIXTURES}/owen_case.csv "
          "--period 'LTM Mar 2026' --dollar-threshold 1 --percent-threshold 1")],
        "In the chat, upload the 10-Q, choose **Build LTM**, upload the 10-K when asked, and confirm the summary.",
    ),
    "clara": (
        "Clara: statement changes and covenant headroom",
        "Clara is a credit analyst. She brings filings and a covenant schedule, and asks for leverage and coverage "
        "against covenant levels and for balance sheet and cash flow changes. She gets ratios from formulas she "
        "declares, headroom against each supplied limit, and statement changes with their identity checks. She never "
        "gets a default EBITDA definition, a rating or a default probability.",
        [("Compare the balance sheet year on year. Every subtotal and the balance sheet identity are checked first.",
          f"{FIXTURES}/hal-20250927.htm --assisted --sheet 'Consolidated Balance Sheets' --compare-to prior-period "
          "--period 'Sep 2025' --dollar-threshold 1 --percent-threshold 1"),
         ("Compare the cash flow statement; cash must roll forward from beginning to ending balance.",
          f"{FIXTURES}/hal-20250927.htm --assisted --sheet 'Consolidated Statements of Cash Flows' --compare-to "
          "prior-period --period FY2025 --dollar-threshold 1 --percent-threshold 1"),
         ("Test the declared ratios against the covenant schedule. A metric the filing can't supply is left out by "
          "name.",
          f"{FIXTURES}/hal-20250927.htm --assisted --metrics {FIXTURES}/clara_metrics.json --compare-file "
          f"{FIXTURES}/clara_covenants.csv --compare-to limit --period FY2025 --dollar-threshold 1 "
          "--percent-threshold 1 --multiple-threshold 0.1")],
        "In the chat, upload the 10-K and type **compare balance sheets**, then **covenant headroom**: upload the "
        "metrics file and the covenant schedule when asked, and confirm.",
    ),
    "marcus": (
        "Marcus: drift from target and the holdings scorecard",
        "Marcus is a portfolio manager. He brings a holdings sheet with target and actual weights and a consensus "
        "panel for the holdings, and asks for drift from target and how the book's holdings reported. He gets drift "
        "in basis points labeled Over, Under or On target, and the weight share of holdings labeled Beat, Miss or In "
        "line. He never gets trades or rebalancing advice.",
        [("Drift of each holding's weight from its target, with a declared tolerance band.",
          f"{FIXTURES}/marcus_targets.csv --assisted --compare-to target --period 'Oct 2026' --dollar-threshold 1 "
          "--percent-threshold 1 --percent-values points --bps-threshold 1"),
         ("Label each holding by its diluted EPS against consensus and share the book's weight out by label.",
          f"{FIXTURES}/marcus_holdings.csv --assisted --panel {FIXTURES}/marcus_panel.csv --join-key Ticker "
          "--deciding-metric 'Diluted EPS' --period 'Q3 2026' --dollar-threshold 1 --percent-threshold 1 "
          "--per-share-threshold 0.01")],
        "In the chat, upload the weights file (its Target column is read as each holding's target), confirm, and "
        "answer the period, thresholds and basis-point cutoff; then ask **drift from target**.",
    ),
    "ines": (
        "Ines: which limits are breached or close",
        "Ines is a risk analyst. She brings exposures against limits by desk and metric, each limit marked Max or "
        "Min, and asks which limits are breached or close. She gets utilization and headroom labeled Breach, At limit, "
        "Near or Within, ordered by severity. She never gets VaR, stress results or predictions.",
        [("Each exposure against its limit; Near only where a row declares a buffer.",
          f"{FIXTURES}/ines_limits.csv --assisted --compare-to limit --period 'Oct 2026' --dollar-threshold 1 "
          "--percent-threshold 1")],
        "In the chat, upload the limits file (its Limit column is read as each row's limit), confirm, answer the "
        "period and thresholds, then ask **which limits are breached**.",
    ),
    "theo": (
        "Theo: active return against the benchmark",
        "Theo is an asset management analyst. He brings fund returns against benchmark returns, fees against budget, "
        "and AUM and flows against plan, and asks for active return and cost and asset variance. He gets active "
        "return in basis points, higher or lower than the benchmark, and the fee and AUM variances. He never gets "
        "attribution the file does not supply, or forecasts.",
        [("Each return and fee rate against its benchmark; In line within a declared tolerance.",
          f"{FIXTURES}/theo_benchmark.csv --assisted --compare-to benchmark --period 'Oct 2026' --dollar-threshold 1 "
          "--percent-threshold 1 --percent-values points --bps-threshold 1")],
        "In the chat, upload the returns file (its Benchmark column is read as each row's benchmark), confirm, answer "
        "the period, thresholds and basis-point cutoff, then ask **active return**. Fees and AUM against budget or "
        "plan use the ordinary budget comparison, as in Maya's example in the README.",
    ),
}


def main() -> None:
    for reader, (title, who, steps, chat) in GUIDES.items():
        parts = [f"# {title}", "", who, "", "Every file here is fictional (tests/fixtures/analysts/), and every command "
                 "below was run to produce the output shown (docs/analysts/evidence/build_guides.py).", ""]
        for what, arguments in steps:
            argv = [str(TOOL), *shlex.split(arguments)]
            done = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)
            if done.returncode != 0:
                raise SystemExit(f"{reader}: exit {done.returncode}: {done.stderr}")
            parts += [what, "", "```sh", f"variance-agent {arguments}", "```", "", "Output:", "", "````markdown",
                      done.stdout.rstrip(), "````", ""]
        parts += ["## In the chat", "", chat, ""]
        (ROOT / "docs" / "analysts" / f"{reader}.md").write_text("\n".join(parts), encoding="utf-8")
        print(f"wrote docs/analysts/{reader}.md")


if __name__ == "__main__":
    main()
