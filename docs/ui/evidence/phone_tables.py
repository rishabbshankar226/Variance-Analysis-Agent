"""Phase 4 exit check (T8): at 375 px every table either fits or shows its "More columns" cue.

Run from the repository root with the Playwright interpreter:

    ~/.venvs/vaa-shots/bin/python docs/ui/evidence/phone_tables.py docs/ui/evidence/phase-4/phone/

For each results reply of the sample file it checks every table, then shoots the table at its left
and right scroll extremes, and prints one line per table. It also prints the results view to PDF
(T12). Exits non-zero when a table overflows with no visible cue.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shots import SAMPLE, SETUP, serve, settle  # noqa: E402

REPLIES = ["Why Subscription Revenue?", "drivers", "biggest risks", "what if marketing is 10% lower", "waterfall"]

CHECK = """() => Array.from(document.querySelectorAll('.table-block:not(.seen)')).map((block, i) => {
  const wrap = block.querySelector('.data-table-wrapper');
  const cue = block.querySelector('.table-cue');
  return {i, fits: wrap.scrollWidth <= wrap.clientWidth, cue: getComputedStyle(cue).display !== 'none',
          scroll: wrap.scrollWidth, client: wrap.clientWidth};
})"""


def check(page: Page, out: Path, label: str) -> list[str]:
    failures = []
    for t in page.evaluate(CHECK):
        ok = t["fits"] or t["cue"]
        print(f"{label} table {t['i']}: scrollWidth {t['scroll']}, clientWidth {t['client']}, "
              f"{'fits' if t['fits'] else 'cue visible' if t['cue'] else 'NO CUE'}")
        if not ok:
            failures.append(f"{label} table {t['i']}")
        if t["fits"]:
            continue
        for end in ("left", "right"):
            page.evaluate("""([i, end]) => {
              const block = document.querySelectorAll('.table-block:not(.seen)')[i];
              const wrap = block.querySelector('.data-table-wrapper');
              wrap.scrollLeft = end === 'left' ? 0 : wrap.scrollWidth;
              wrap.dispatchEvent(new Event('scroll'));
              const log = document.getElementById('messages');
              log.style.scrollBehavior = 'auto';
              log.scrollTop = block.getBoundingClientRect().top - log.getBoundingClientRect().top + log.scrollTop - 120;
            }""", [t["i"], end])
            page.wait_for_timeout(150)
            page.screenshot(path=str(out / f"{label}_table{t['i']}_{end}.jpg"), type="jpeg", quality=80)
    return failures


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        proc, url = serve()
        try:
            page = browser.new_context(viewport={"width": 375, "height": 760}, color_scheme="light").new_page()
            page.goto(url)
            settle(page)
            page.locator("input[type=file]").first.set_input_files(SAMPLE)
            settle(page)
            for text, _ in SETUP:
                page.fill("#input", text)
                page.keyboard.press("Enter")
                settle(page)
            failures += check(page, out, "results")
            for n, reply in enumerate(REPLIES, 1):
                page.evaluate("() => document.querySelectorAll('.table-block').forEach((b) => b.classList.add('seen'))")
                page.fill("#input", reply)
                page.keyboard.press("Enter")
                settle(page)
                failures += check(page, out, f"reply{n}")
            page.emulate_media(media="print")
            page.pdf(path=str(out / "print_results.pdf"))
            print("printed", out / "print_results.pdf")
        finally:
            proc.terminate()
            proc.wait(timeout=10)
        browser.close()
    if failures:
        print("FAIL:", ", ".join(failures))
        raise SystemExit(1)
    print("PASS: every table fits or shows its cue at 375 px")


if __name__ == "__main__":
    main()
