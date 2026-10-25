"""Screenshot harness for the interface redesign (docs/ui/PLAN.md, Appendix A of the run prompt).

Run from the repository root with a Playwright interpreter that lives outside the repository:

    ~/.venvs/vaa-shots/bin/python docs/ui/evidence/shots.py docs/ui/evidence/after/ [--themes light,dark]
        [--sizes d,t,m] [--only first,sample]

Each scenario starts a fresh `variance-agent --chat --no-browser` server and a fresh browser
context, because the server holds one shared session and the page remembers its visitor in
localStorage. Replies are typed into #input, never clicked by chip text. Every file used here is
fictional: the repository's examples and fixtures, plus untyped_fictional.csv in this folder.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
SIZES = {"d": (1280, 800), "t": (768, 1024), "m": (375, 760)}
SAMPLE = "examples/sample_variance.csv"
MA = "tests/fixtures/multi_audience/"
RW = "tests/fixtures/realworld/"
SETUP = [("Q3 2026", "thresholds"), ("$10,000 or 5%", "currency"), ("USD", "results")]

# A step is ("upload", path, label), ("say", text, label) or ("shot", "", label).
# label "" means take no screenshot after the step.
Step = tuple[str, str, str]
SCENARIOS: dict[str, list[Step]] = {
    "first": [("shot", "", "first"), ("say", "help", "help")],
    "sample": [("upload", SAMPLE, "upload")]
    + [("say", text, label) for text, label in SETUP]
    + [("say", "Why Subscription Revenue?", "drilldown"),
       ("say", "drivers", "drivers"), ("say", "biggest risks", "risks"),
       ("say", "what if marketing is 10% lower", "whatif"), ("say", "summary", "summary")],
    "intake": [("upload", RW + "fixture_d_thousands_dashes_blanks.xlsx", "blank-budget"),
               ("say", "Treat blank budgets as 0 (unbudgeted)", "intake-summary"),
               ("say", "Looks right", "period")],
    "period-choice": [("upload", RW + "fixture_e_wide_monthly.xlsx", "period-choice")],
    "comparison": [("upload", RW + "fixture_l_budget_and_forecast.csv", "comparison-choice")],
    "unclassified": [("upload", str(HERE / "untyped_fictional.csv"), "upload")]
    + [("say", text, label) for text, label in SETUP[:2]]
    + [("say", "USD", "unclassified"), ("say", "Expense", "unclassified-next")],
    "error": [("upload", RW + "fixture_q_scanned_no_text.pdf", "unreadable")],
    "earnings": [("upload", MA + "consensus.csv", "offer"), ("say", "Review earnings", "intake-summary"),
                 ("say", "Looks right", ""), ("say", "3Q26", ""), ("say", "$10,000 or 5%", ""),
                 ("say", "USD", "measure"), ("say", "25", ""), ("say", "25", ""), ("say", "25", "review")],
    "comparison-set": [("upload", MA + "comparison_set.csv", "intake-summary"), ("say", "Looks right", ""),
                       ("say", "3Q26", ""), ("say", "$10,000 or 5%", ""), ("say", "USD", ""),
                       ("say", "25", "result")],
    "pdf": [("upload", RW + "fixture_t_halvorsen_fake_eps.pdf", "intake-summary"), ("say", "Looks right", "")]
    + [("say", text, label) for text, label in SETUP],
}


def serve() -> tuple[subprocess.Popen[str], str]:
    proc = subprocess.Popen([".venv/bin/variance-agent", "--chat", "--no-browser"],
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    for _ in range(20):
        match = re.search(r"http://\S+", proc.stdout.readline())
        if match:
            return proc, match.group(0)
    proc.terminate()
    raise RuntimeError("the chat server printed no URL")


def settle(page: Page) -> None:
    """Wait for the page to finish the request in flight, then for rendering to stop."""
    # Polled with evaluate, because wait_for_function compiles its predicate with eval, which the page's CSP refuses.
    page.wait_for_timeout(150)
    for _ in range(900):
        if not page.evaluate("() => document.body.classList.contains('is-busy')"):
            break
        page.wait_for_timeout(100)
    else:
        raise TimeoutError("the page stayed busy for 90 seconds")
    page.wait_for_timeout(400)


def run(out: Path, themes: list[str], sizes: list[str], only: list[str]) -> list[Path]:
    written: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scenario, steps in SCENARIOS.items():
            if only and scenario not in only:
                continue
            for theme in themes:
                for size in sizes:
                    w, h = SIZES[size]
                    proc, url = serve()
                    context = browser.new_context(viewport={"width": w, "height": h}, color_scheme=theme)
                    page = context.new_page()
                    n = 0

                    stem = f"{scenario}_{theme}_{size}"

                    def shot(label: str, page: Page = page, stem: str = stem) -> None:
                        nonlocal n
                        # The log scrolls inside #messages: show the newest reply from its first line, and
                        # when it is taller than the log, its last line too. Smooth scrolling is turned off
                        # first so the page's own scroll-to-bottom cannot land after ours.
                        tall = page.evaluate("""() => {
                          const log = document.getElementById('messages');
                          log.style.scrollBehavior = 'auto';
                          const replies = log.querySelectorAll('.message.agent');
                          const last = replies[replies.length - 1];
                          if (!last) return false;
                          const top = last.getBoundingClientRect().top - log.getBoundingClientRect().top + log.scrollTop;
                          log.scrollTop = Math.max(0, top - 16);
                          return last.offsetHeight + 16 > log.clientHeight;
                        }""")
                        for suffix in ("", "-end") if tall else ("",):
                            if suffix:
                                page.evaluate("() => { const log = document.getElementById('messages');"
                                              " log.scrollTop = log.scrollHeight; }")
                            page.wait_for_timeout(150)
                            n += 1
                            path = out / f"{stem}_{n:02d}_{label}{suffix}.jpg"
                            page.screenshot(path=str(path), type="jpeg", quality=80)
                            written.append(path)

                    try:
                        page.goto(url)
                        settle(page)
                        for kind, arg, label in steps:
                            if kind == "upload":
                                page.locator("input[type=file]").first.set_input_files(arg)
                            elif kind == "say":
                                page.fill("#input", arg)
                                page.keyboard.press("Enter")
                            if kind != "shot":
                                settle(page)
                            if label:
                                shot(label)
                        print(f"{stem}: {n} screenshots", flush=True)
                    finally:
                        context.close()
                        proc.terminate()
                        proc.wait(timeout=10)
        browser.close()
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--themes", default="light,dark")
    parser.add_argument("--sizes", default="d,t,m")
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    written = run(args.out, args.themes.split(","), args.sizes.split(","), [s for s in args.only.split(",") if s])
    total = sum(path.stat().st_size for path in written)
    print(f"{len(written)} screenshots, {total / 1048576:.1f} MiB, in {args.out}")


if __name__ == "__main__":
    main()
