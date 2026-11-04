"""Screenshots of every chat screen Phases 2 and 3 of the improvement pass changed (docs/improve/PLAN.md).

Reuses the interface redesign's harness (docs/ui/evidence/shots.py), as the analysts run's harness does
(docs/analysts/evidence/shots_analysts.py). Every file uploaded is fictional and built here, mostly
from the very fixtures the Phase 2 and 3 tests pin, so each screen shows a tested case.

    .venv/bin/python docs/improve/evidence/phase-3/shots_phase3.py --build <scratch dir>
    .venv/bin/python docs/improve/evidence/phase-3/shots_phase3.py --check <scratch dir>
    ~/.venvs/vaa-shots/bin/python docs/improve/evidence/phase-3/shots_phase3.py <out dir> <scratch dir> [names]

The project venv builds the files and, with --check, drives each scenario through the chat handlers
in Python, printing the phase after every step; the harness's venv takes the screenshots.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "docs" / "ui" / "evidence"))
sys.path.insert(0, str(ROOT))

SETUP = [("say", "Q3 2026", ""), ("say", "$10,000 or 5%", ""), ("say", "USD", "results")]
UNTYPED = str(ROOT / "docs" / "ui" / "evidence" / "untyped_fictional.csv")


def scenarios(files: Path) -> dict[str, list[tuple[str, str, str]]]:
    """name -> steps, as shots.py takes them: ("upload", path, label), ("say", text, label)."""
    def up(name: str, label: str) -> tuple[str, str, str]:
        return ("upload", str(files / name), label)

    return {
        # Phase 2
        "c5-zero-line": [up("on_budget.csv", "")] + SETUP + [("say", "summary", "summary")],
        "x5-currency": [up("euro.csv", "")] + SETUP[:2] + [("say", "USD", "currency")],
        "x6-month-and-ytd": [up("month_ytd.csv", "period-choice"), ("say", "Sep-26", "intake-summary")],
        "x1-footnote": [up("footnote.csv", "refusal")],
        "x4-pound-caption": [up("pounds.xlsx", "intake-summary")],
        "x7-signed-ledger": [up("signed_ledger.csv", "intake-summary")],
        "x3-pdf-caption": [up("captioned.pdf", "intake-summary")],
        # Phase 3: spreadsheets
        "x16-sections": [up("sections.csv", "intake-summary")],
        "x20-zero-section": [up("zero_section.xlsx", "intake-summary")],
        "x23-header-units": [up("units.csv", "intake-summary")],
        "x24-two-row-header": [up("two_row.xlsx", "intake-summary")],
        "m3-bare-years": [up("years.xlsx", "period-choice"), ("say", "2026", "intake-summary")],
        "x31-percent-format": [up("percent.xlsx", "intake-summary"), ("say", "Looks right", "")]
        + SETUP[:2] + [("say", "USD", "bps"), ("say", "50", "results")],
        "x35-period-chip": [up("titled.xlsx", ""), ("say", "Looks right", "period-chip"),
                            ("say", "Q3 2026", "period-set")],
        "x21-whole-after-half": [up("bud.csv", "half"), ("upload", str(ROOT / "examples" / "sample_variance.csv"),
                                                         "whole-file")],
        "x36-unbudgeted": [up("bud.csv", ""), up("act.csv", "offer"),
                           ("say", "Treat them as 0 (unbudgeted)", "joined")],
        "x22-unreconciled-total": [up("rounded.csv", ""), ("say", "Looks right", "")] + SETUP[:2]
        + [("say", "USD", "offer"), ("say", "Leave Total Opex out", "left-out")],
        "x27-not-yet-labeled": [("upload", UNTYPED, "")] + SETUP[:2]
        + [("say", "USD", "question"), ("say", "Skip all", "results")],
        # One upload each: after a refusal the page waits on its own drop zone, not the file input.
        "m6-empty-file": [up("empty.csv", "refusal")],
        "m6-no-header": [up("no_header.csv", "refusal")],
        # Phase 3: filings
        "m1-statements-elsewhere": [up("hal-elsewhere-20250927.htm", "refusal")],
        "m2-runs-on": [up("hal-runs-on-20250927.htm", "refusal")],
        "m5-numbered-copies": [up("hal-copies-20250927.htm", "intake-summary")],
        "c4-credit-by-year": [up("hal-credit-20250927.htm", "intake-summary")],
        "c3m-sign-ambiguity": [up("hal-ambiguous-20250927.htm", "refusal")],
        "x30-filing-currency": [up("hal-yen-20250927.htm", ""), ("say", "Looks right", ""), ("say", "FY2025", ""),
                                ("say", "$1 or 1%", ""), ("say", "USD", "refusal")],
    }


def build(scratch: Path) -> None:
    from openpyxl import Workbook  # type: ignore[import-untyped]

    from tests.fixtures.ixbrl.build_ixbrl import (
        all_statements_filing,
        document,
        fact,
        income_filing,
        income_rows,
        row,
        statement,
    )
    from tests.test_chat_period_chips import _book as titled_book
    from tests.test_chat_unreconciled_total import ROUNDED
    from tests.test_chat_zero_variance import ON_BUDGET
    from tests.test_currency_conflicts import EURO_FILE
    from tests.test_excel_bands_and_blocks import _year_bands
    from tests.test_excel_zero_section import _book as zero_section_book
    from tests.test_ixbrl_statements_elsewhere import _without_statements
    from tests.test_join_unbudgeted import BUDGET, EXTRA_ACTUAL
    from tests.test_pdf_intake import _captioned_statement
    from tests.test_percent_formats import BOTH
    from tests.test_percent_formats import _book as percent_book
    from tests.test_period_choice import MONTH_AND_YTD
    from tests.test_section_headings import HEADED
    from tests.test_signed_profit_lines import PROFITABLE
    from tests.test_two_row_headers import _book as two_row_book

    scratch.mkdir(parents=True, exist_ok=True)

    def write(name: str, data: bytes | str) -> None:
        (scratch / name).write_bytes(data.encode("utf-8") if isinstance(data, str) else data)

    def book(name: str, rows: list[list[object]]) -> None:
        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        for line in rows:
            sheet.append(line)
        capture = io.BytesIO()
        workbook.save(capture)
        write(name, capture.getvalue())

    write("on_budget.csv", ON_BUDGET)
    write("euro.csv", EURO_FILE)
    write("month_ytd.csv", MONTH_AND_YTD)
    write("footnote.csv", "Line Item,Type,Budget,Actual\nProduct Revenue,Revenue,900,950¹\nStaff Costs,Expense,800,820\n")
    book("pounds.xlsx", [["Fictional Northwind Ltd (FICTIONAL DATA)"], ["Budget vs Actual (£000)"],
                         ["Line Item", "Type", "Budget", "Actual"], ["Fictional Sales", "Revenue", 1200, 1350],
                         ["Fictional Rent", "Expense", 300, 310]])
    write("signed_ledger.csv", PROFITABLE)
    _captioned_statement(scratch / "captioned.pdf", "CONSOLIDATED STATEMENTS OF OPERATIONS (In millions)", None)
    write("sections.csv", HEADED)
    write("zero_section.xlsx", zero_section_book(0))
    write("units.csv", "Line Item,Budget ($000),Actual ($000)\nFictional Sales,250,275\nFictional Rent,100,104\n")
    write("two_row.xlsx", two_row_book(True))
    write("years.xlsx", _year_bands(True))
    write("percent.xlsx", percent_book(BOTH))
    write("titled.xlsx", titled_book("Budget vs Actual Report Q3 2026 ($ in thousands)"))
    write("bud.csv", BUDGET)
    write("act.csv", EXTRA_ACTUAL)
    write("rounded.csv", ROUNDED)
    write("empty.csv", "")
    write("no_header.csv", "Name,Amount\nFictional Sales,100\nFictional Rent,40\n")
    write("hal-elsewhere-20250927.htm", _without_statements(b'<p>See <a href="fake-20261231ex13.htm">Exhibit 13</a>.</p>'))
    sheet = statement("CONSOLIDATED BALANCE SHEETS", [
        row("Cash", fact("us-gaap:Cash", "I25", "500"), fact("us-gaap:Cash", "I24", "400")),
        row("Total assets", fact("us-gaap:Assets", "I25", "500"), fact("us-gaap:Assets", "I24", "400")),
        row("Accounts payable", fact("us-gaap:AccountsPayableCurrent", "I25", "200"),
            fact("us-gaap:AccountsPayableCurrent", "I24", "150"))])
    write("hal-runs-on-20250927.htm", document(sheet + "<table>" + "".join(income_rows()) + "</table>"))
    write("hal-copies-20250927.htm", income_filing([
        row("Net sales", fact("us-gaap:Revenues", "FY25", "1,000"), fact("us-gaap:Revenues", "FY24", "900")),
        row("Depreciation", fact("us-gaap:Depreciation", "FY25", "100"), fact("us-gaap:Depreciation", "FY24", "90")),
        row("Deferred income taxes", fact("us-gaap:DeferredIncomeTaxExpenseBenefit", "FY25", "20"),
            fact("us-gaap:DeferredIncomeTaxExpenseBenefit", "FY24", "10")),
        row("Other costs", fact("us-gaap:OtherCostAndExpenseOperating", "FY25", "30"),
            fact("us-gaap:OtherCostAndExpenseOperating", "FY24", "25")),
        row("Deferred income taxes", fact("us-gaap:DeferredIncomeTaxesAndTaxCredits", "FY25", "5"),
            fact("us-gaap:DeferredIncomeTaxesAndTaxCredits", "FY24", "4")),
        row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", "845"), fact("us-gaap:NetIncomeLoss", "FY24", "771"))]))
    credit = income_rows()
    credit[4:6] = [row("Other income, net", fact("us-gaap:OtherNonoperatingIncomeExpense", "FY25", "50"),
                       "(" + fact("us-gaap:OtherNonoperatingIncomeExpense", "FY24", "40", sign="-") + ")"),
                   row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", "1,550"),
                       fact("us-gaap:NetIncomeLoss", "FY24", "1,330"))]
    write("hal-credit-20250927.htm", income_filing(credit))
    def money(label: str, concept: str, now: str, before: str) -> str:
        """A line whose figures print in parentheses where the instance holds them negative."""
        return row(label, *("(" + fact(concept, context, text.strip("()"), sign="-") + ")" if text.startswith("(")
                            else fact(concept, context, text) for context, text in (("FY25", now), ("FY24", before))))
    # C3m's case (tests/test_statement_sign_ambiguity.py): a one-unit line beside a zero, within R5's rounding.
    write("hal-ambiguous-20250927.htm", income_filing([
        money("Fictional net revenues", "us-gaap:Revenues", "900", "800"),
        money("Fictional costs", "us-gaap:CostOfRevenue", "600", "550"),
        money("Operating income", "us-gaap:OperatingIncomeLoss", "300", "250"),
        money("Other expense, net", "us-gaap:OtherNonoperatingIncomeExpense", "0", "(1)"),
        money("Interest expense", "us-gaap:InterestExpense", "(40)", "(20)"),
        money("Interest income", "us-gaap:InvestmentIncomeInterest", "6", "4"),
        money("Income before income taxes",
              "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
              "266", "234")]))
    write("hal-yen-20250927.htm", all_statements_filing().replace(b"iso4217:USD", b"iso4217:JPY"))


def check(scratch: Path) -> None:
    """Drive each scenario through the chat handlers, printing the phase and the reply's first line."""
    from variance_agent.chat.handlers import handle_message, handle_upload
    from variance_agent.chat.session import Session

    for name, steps in scenarios(scratch).items():
        session = Session()
        print(f"== {name}")
        for kind, arg, label in steps:
            if kind == "upload":
                reply = handle_upload(session, Path(arg).read_bytes(), Path(arg).name)
            else:
                reply = handle_message(session, arg)
            text = reply.text.replace("Welcome to the Variance Analysis Agent.", "").strip()
            lines = [line for line in text.splitlines() if line.strip() and not line.startswith(("I compare", "Type"))]
            print(f"  {kind} {Path(arg).name if kind == 'upload' else arg!r} [{label}] -> {session.phase.value} "
                  f"{reply.level or ''} chips={reply.chips} | {(lines[0] if lines else '')[:140]}")


def main(out: Path, scratch: Path, only: list[str]) -> None:
    import shots  # type: ignore[import-not-found]  # the redesign harness; needs Playwright

    out.mkdir(parents=True, exist_ok=True)
    shots.SCENARIOS = scenarios(scratch)
    for path in shots.run(out, ["light"], ["d", "m"], only or list(shots.SCENARIOS)):
        print(path)


if __name__ == "__main__":
    if sys.argv[1] == "--build":
        build(Path(sys.argv[2]))
    elif sys.argv[1] == "--check":
        check(Path(sys.argv[2]))
    else:
        main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3].split(",") if len(sys.argv) > 3 else [])
