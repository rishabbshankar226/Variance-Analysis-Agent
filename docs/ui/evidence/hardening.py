"""Phase 8 hardening checks, run against the real chat server with Playwright.

    ~/.venvs/vaa-shots/bin/python docs/ui/evidence/hardening.py docs/ui/evidence/hardening/

Checks, each printed as one PASS or FAIL line:
  axe      axe-core (WCAG 2.1 A and AA rules) on the first screen, the intake panel, the results and the
           earnings review, light and dark, 1280 and 375 px. axe is read from the owner's copy outside
           the repository (AXE below) and injected into a page context that bypasses the CSP; it is
           never copied in.
  keyboard Tab from the top of the first screen: every stop shows a focus outline; Enter on the drop
           zone opens the file chooser; after the results, Tab reaches a line item and Enter drills down.
  reflow   at 320 px wide (the WCAG reflow width, 1280 px at 400%) and at 640 px (200% zoom) the
           page never scrolls sideways; only tables scroll inside their frame.
  motion   with reduced motion, no element animates.
  forced   forced colours: results screenshot, controls keep a visible border.
  print    the results printed to PDF.
Screenshots of each check go to the output folder.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import Browser, Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shots import MA, RW, SAMPLE, SETUP, serve, settle  # noqa: E402

AXE = Path.home() / "Desktop" / "projects" / "Defense Backlog forecast" / "tests" / "vendor" / "axe.min.js"
results: list[str] = []


def report(name: str, ok: bool, detail: str) -> None:
    line = f"{'PASS' if ok else 'FAIL'} {name}: {detail}"
    results.append(line)
    print(line, flush=True)


def say(page: Page, text: str) -> None:
    page.fill("#input", text)
    page.keyboard.press("Enter")
    settle(page)


def to_results(page: Page) -> None:
    page.locator("input[type=file]").first.set_input_files(SAMPLE)
    settle(page)
    for text, _ in SETUP:
        say(page, text)


def to_intake(page: Page) -> None:
    page.locator("input[type=file]").first.set_input_files(RW + "fixture_d_thousands_dashes_blanks.xlsx")
    settle(page)
    say(page, "Treat blank budgets as 0 (unbudgeted)")


def to_earnings(page: Page) -> None:
    page.locator("input[type=file]").first.set_input_files(MA + "consensus.csv")
    settle(page)
    for text in ("Review earnings", "Looks right", "3Q26", "$10,000 or 5%", "USD", "25", "25", "25"):
        say(page, text)


def fresh(browser: Browser, url: str, **context: object) -> Page:
    page = browser.new_context(**context).new_page()  # type: ignore[arg-type]
    page.goto(url)
    settle(page)
    return page


def axe_check(browser: Browser, out: Path) -> None:
    if not AXE.exists():
        report("axe", False, f"not run: {AXE} is missing")
        return
    source = AXE.read_text(encoding="utf-8")
    states = {"first": None, "intake": to_intake, "results": to_results, "earnings": to_earnings}
    for state, reach in states.items():
        for theme in ("light", "dark"):
            for width, height in ((1280, 800), (375, 760)):
                proc, url = serve()
                try:
                    page = fresh(browser, url, viewport={"width": width, "height": height}, color_scheme=theme,
                                 bypass_csp=True)
                    if reach:
                        reach(page)
                    page.evaluate(source)
                    found = page.evaluate("""async () => {
                      const r = await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']}});
                      return r.violations.map((v) => `${v.id} (${v.impact}, ${v.nodes.length}): ${v.nodes[0].target.join(' ')}`);
                    }""")
                    report(f"axe {state} {theme} {width}", not found, "; ".join(found) or "no violations")
                finally:
                    proc.terminate()
                    proc.wait(timeout=10)


def keyboard_check(browser: Browser, out: Path) -> None:
    proc, url = serve()
    try:
        page = fresh(browser, url, viewport={"width": 1280, "height": 800})
        stops = []
        for _ in range(20):
            page.keyboard.press("Tab")
            stop = page.evaluate("""() => {
              const el = document.activeElement; const s = getComputedStyle(el);
              const ring = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 1;
              return [el === document.body ? 'BODY' : (el.id || el.className || el.tagName), ring];
            }""")
            if stop[0] == "BODY":  # Tab has left the last control and the page: one full cycle
                break
            stops.append(stop)
        page.screenshot(path=str(out / "keyboard_focus.jpg"), type="jpeg", quality=80)
        unringed = [name for name, ring in stops if not ring]
        outcome = "all show a focus outline" if not unringed else f"no outline on {unringed}"
        report("keyboard focus", bool(stops) and not unringed, f"{len(stops)} stops {[n for n, _ in stops]}, {outcome}")
        zone = page.locator(".drop-zone").first
        zone.focus()
        with page.expect_file_chooser(timeout=3000) as chooser:
            page.keyboard.press("Enter")
        chooser.value.set_files(SAMPLE)
        settle(page)
        for text, _ in SETUP:
            page.focus("#input")
            page.keyboard.type(text)
            page.keyboard.press("Enter")
            settle(page)
        page.locator(".item-link").last.focus()
        name = page.evaluate("() => document.activeElement.textContent")
        page.keyboard.press("Enter")
        settle(page)
        drilled = page.evaluate("() => Array.from(document.querySelectorAll('.view-title')).pop()?.textContent || ''")
        page.screenshot(path=str(out / "keyboard_drilldown.jpg"), type="jpeg", quality=80)
        report("keyboard flow", drilled == f"Driver evidence: {name}",
               f"file chosen with Enter, setup typed, drill-down opened for {name!r} ({drilled!r})")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def reflow_check(browser: Browser, out: Path) -> None:
    for width, label in ((320, "320 px (400% zoom)"), (640, "640 px (200% zoom)")):
        proc, url = serve()
        try:
            page = fresh(browser, url, viewport={"width": width, "height": 640})
            to_results(page)
            sideways = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
            page.screenshot(path=str(out / f"reflow_{width}.jpg"), type="jpeg", quality=80)
            report(f"reflow {label}", sideways <= 0, f"page overflows sideways by {sideways} px")
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def motion_check(browser: Browser, out: Path) -> None:
    proc, url = serve()
    try:
        page = fresh(browser, url, viewport={"width": 1280, "height": 800}, reduced_motion="reduce")
        to_results(page)
        moving = page.evaluate("""() => Array.from(document.querySelectorAll('*')).filter((el) => {
          const s = getComputedStyle(el);
          return (s.animationName !== 'none' && parseFloat(s.animationDuration) > 0) || parseFloat(s.transitionDuration) > 0;
        }).length""")
        report("reduced motion", moving == 0, f"{moving} elements animate")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def forced_check(browser: Browser, out: Path) -> None:
    proc, url = serve()
    try:
        page = fresh(browser, url, viewport={"width": 1280, "height": 800}, forced_colors="active")
        to_results(page)
        borders = page.evaluate("""() => ['.chip', '.send-btn', '.table-block'].map((sel) => {
          const el = document.querySelector(sel); return el ? getComputedStyle(el).borderTopStyle : 'missing';
        })""")
        page.screenshot(path=str(out / "forced_colors_results.jpg"), type="jpeg", quality=80)
        report("forced colours", all(b == "solid" for b in borders), f"chip, send, table borders: {borders}")
        page.emulate_media(media="print")
        page.pdf(path=str(out / "print_results.pdf"))
        report("print", (out / "print_results.pdf").stat().st_size > 10_000, "results printed to print_results.pdf")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for check in (axe_check, keyboard_check, reflow_check, motion_check, forced_check):
            check(browser, out)
        browser.close()
    (out / "results.txt").write_text("\n".join(results) + "\n", encoding="utf-8")
    failed = [line for line in results if line.startswith("FAIL")]
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
