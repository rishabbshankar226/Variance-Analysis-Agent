"""Build messy FICTIONAL budget-vs-actual files for the Maya friction audit.

Every company, account and figure here is fictional ("Fictional Northwind Co.").
Run: .venv/bin/python .scratch/audit-maya/build_files.py
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

OUT = Path(__file__).resolve().parent / "files"
OUT.mkdir(exist_ok=True)

TITLE = "Fictional Northwind Co. (FICTIONAL DATA)"

# (GL, description, type, budget, actual) - unsigned, expense positive
LINES = [
    (4000, "Product Revenue", "Revenue", 500000, 540000),
    (4100, "Service Revenue", "Revenue", 200000, 185000),
    (5000, "Cost of Goods Sold", "Expense", 220000, 236000),
    (6000, "Salaries & Wages", "Expense", 180000, 191000),
    (6100, "Marketing - Digital", "Expense", 40000, 52000),
    (6200, "Rent", "Expense", 30000, 30000),
    (6300, "Travel", "Expense", 15000, 9000),
]


def save(wb: Workbook, name: str) -> None:
    wb.save(OUT / name)


def title_block(ws, *extra: str) -> int:
    """Write a title block, return the next free row."""
    ws.append([TITLE])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Budget vs Actual Report"])
    for e in extra:
        ws.append([e])
    ws.append([])
    return ws.max_row + 1


def f01_title_block() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    title_block(ws, "For the period ended September 30, 2026")
    ws.append(["GL Account", "Account Description", "Budget YTD", "Actual YTD"])
    for gl, d, _t, b, a in LINES:
        ws.append([gl, d, b, a])
    save(wb, "f01_title_block.xlsx")


def f02_signed_ledger() -> None:
    """Signed trial-balance style: revenue (credits) negative, expenses positive, no Type column."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Ledger"
    ws.append(["GL Account", "Account Description", "Budget", "Actual"])
    for gl, d, t, b, a in LINES:
        s = -1 if t == "Revenue" else 1
        ws.append([gl, d, s * b, s * a])
    save(wb, "f02_signed_ledger.xlsx")


def f03_thousands_caption() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    title_block(ws, "Q3 2026", "($ in thousands)")
    ws.append(["Account Description", "Type", "Budget", "Actual"])
    for _gl, d, t, b, a in LINES:
        ws.append([d, t, b / 1000, a / 1000])
    save(wb, "f03_thousands_caption.xlsx")


def f04_dashes() -> None:
    """Dashes for zero, typed as text the way exported reports show them."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Type", "Budget", "Actual"])
    ws.append(["Product Revenue", "Revenue", 500000, 540000])
    ws.append(["Grant Income", "Revenue", "-", 12000])
    ws.append(["Salaries & Wages", "Expense", 180000, 191000])
    ws.append(["Consulting", "Expense", 25000, "-"])
    ws.append(["Bad Debt", "Expense", " - ", " - "])
    ws.append(["Rent", "Expense", 30000, 30000])
    save(wb, "f04_dashes.xlsx")


def f05_blank_budgets() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Type", "Budget", "Actual"])
    ws.append(["Product Revenue", "Revenue", 500000, 540000])
    ws.append(["Salaries & Wages", "Expense", 180000, 191000])
    ws.append(["Legal Settlement", "Expense", None, 45000])
    ws.append(["Software Subscriptions", "Expense", None, 8000])
    ws.append(["Rent", "Expense", 30000, 30000])
    save(wb, "f05_blank_budgets.xlsx")


def f06_two_files() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(["GL Account", "Account Description", "Budget"])
    for gl, d, _t, b, _a in LINES:
        ws.append([gl, d, b])
    save(wb, "f06a_budget_only.xlsx")
    wb = Workbook()
    ws = wb.active
    ws.title = "Actuals"
    ws.append(["GL Account", "Account Description", "Actual"])
    for gl, d, _t, _b, a in LINES:
        ws.append([gl, d, a])
    save(wb, "f06b_actual_only.xlsx")


def f07_hidden_row() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Type", "Budget", "Actual"])
    for _gl, d, t, b, a in LINES:
        ws.append([d, t, b, a])
    ws.append(["Intercompany Elimination", "Expense", 0, -25000])
    ws.row_dimensions[ws.max_row].hidden = True
    save(wb, "f07_hidden_row.xlsx")


def f08_formula_no_cache() -> None:
    """openpyxl writes formulas with no cached value, like a file built by a script or never recalculated."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Type", "Budget", "Actual"])
    ws.append(["Product Revenue", "Revenue", 500000, 540000])
    ws.append(["Service Revenue", "Revenue", 200000, "=C3*0.925"])
    ws.append(["Salaries & Wages", "Expense", 180000, 191000])
    ws.append(["Rent", "Expense", 30000, 30000])
    save(wb, "f08_formula_no_cache.xlsx")


def f09_merged_header() -> None:
    """Two-row header: a merged 'Year to Date' band over Budget/Actual, merged 'Account' cell."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account", "Type", "Year to Date", None])
    ws.append([None, None, "Budget", "Actual"])
    ws.merge_cells("A1:A2")
    ws.merge_cells("B1:B2")
    ws.merge_cells("C1:D1")
    for _gl, d, t, b, a in LINES:
        ws.append([d, t, b, a])
    save(wb, "f09_merged_header.xlsx")


def f10_bom_csv() -> None:
    """CSV saved by Excel ('CSV UTF-8'): BOM, CRLF, quoted thousands separators, $ signs, accented label."""
    rows = ["Account Description,Type,Budget,Actual"]
    rows += [
        'Product Revenue,Revenue,"$500,000","$540,000"',
        'Service Revenue,Revenue,"$200,000","$185,000"',
        'Salaries & Wages,Expense,"$180,000","$191,000"',
        'Café & Catering,Expense,"$12,000","$14,500"',
        'Rent,Expense,"$30,000","$30,000"',
    ]
    (OUT / "f10_excel_bom.csv").write_bytes(("﻿" + "\r\n".join(rows) + "\r\n").encode("utf-8"))


def f11_period_columns() -> None:
    """Month and quarter columns side by side, as a planning tool exports them."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["GL Account", "Account Description", "Sep-26 Actual", "Sep-26 Budget", "Q3 Actual", "Q3 Budget"])
    for gl, d, _t, b, a in LINES:
        ws.append([gl, d, round(a / 3), round(b / 3), a, b])
    save(wb, "f11_period_columns.xlsx")


def f12_nested_subtotals() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "P&L"
    ws.append(["Account Description", "Budget", "Actual"])
    ws.append(["Product Revenue", 500000, 540000])
    ws.append(["Service Revenue", 200000, 185000])
    ws.append(["Total Revenue", 700000, 725000])
    ws.append(["Cost of Goods Sold", 220000, 236000])
    ws.append(["Gross Profit", 480000, 489000])
    ws.append(["Salaries & Wages", 180000, 191000])
    ws.append(["Marketing - Digital", 40000, 52000])
    ws.append(["Rent", 30000, 30000])
    ws.append(["Travel", 15000, 9000])
    ws.append(["Total Opex", 265000, 282000])
    ws.append(["Net Income", 215000, 207000])
    save(wb, "f12_nested_subtotals.xlsx")


def f13_var_columns() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Type", "Budget", "Actual", "Var $", "Var %"])
    for _gl, d, t, b, a in LINES:
        v = (a - b) if t == "Revenue" else (b - a)
        ws.append([d, t, b, a, v, round(v / b, 4) if b else None])
    save(wb, "f13_var_columns.xlsx")


def f14_realistic_combo() -> None:
    """What a controller actually sends: title block, $000s caption, signed ledger, dashes,
    nested subtotals, Var $ / Var % columns, a blank unbudgeted line. No Type column."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sep-26 BvA"
    title_block(ws, "Income Statement - Budget vs Actual", "Nine months ended September 30, 2026", "(in thousands)")
    ws.append(["GL Account", "Account Description", "Budget YTD", "Actual YTD", "Var $", "Var %"])
    data = [
        (4000, "Product Revenue", -500, -540),
        (4100, "Service Revenue", -200, -185),
        (None, "Total Revenue", -700, -725),
        (5000, "Cost of Goods Sold", 220, 236),
        (None, "Gross Profit", -480, -489),
        (6000, "Salaries & Wages", 180, 191),
        (6100, "Marketing - Digital", 40, 52),
        (6200, "Rent", 30, 30),
        (6400, "Bad Debt", "-", 4),
        (6500, "Legal Settlement", None, 45),
        (None, "Total Opex", 250, 322),
        (None, "Net Income", -230, -167),
    ]
    for gl, d, b, a in data:
        bn = 0 if b in ("-", None) else b
        an = 0 if a in ("-", None) else a
        v = bn - an
        pct = round(v / bn, 4) if bn else None
        ws.append([gl, d, b, a, v, pct])
    save(wb, "f14_realistic_combo.xlsx")


def f15_parens_csv() -> None:
    """Negatives in parentheses, an Excel-exported CSV with an accounting-style dash."""
    text = (
        "Account Description,Type,Budget,Actual\r\n"
        'Product Revenue,Revenue,"500,000","540,000"\r\n'
        'Returns & Allowances,Revenue,"(10,000)","(14,000)"\r\n'
        'Salaries & Wages,Expense,"180,000","191,000"\r\n'
        'FX Loss,Expense, - ,"2,500"\r\n'
    )
    (OUT / "f15_parens_dash.csv").write_bytes(text.encode("utf-8"))


def f16_cover_sheet() -> None:
    """Workbook whose first sheet is a cover/notes page and the data is on the second."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Cover"
    ws.append([TITLE])
    ws.append(["Q3 2026 Board Pack"])
    ws.append(["Prepared by FP&A"])
    ws2 = wb.create_sheet("BvA Detail")
    ws2.append(["Account Description", "Type", "Budget", "Actual"])
    for _gl, d, t, b, a in LINES:
        ws2.append([d, t, b, a])
    save(wb, "f16_cover_sheet.xlsx")


def f17_date_headers() -> None:
    """Header cells that are real Excel dates (Sep-26) with Budget/Actual on a second header row."""
    import datetime as dt

    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", dt.datetime(2026, 9, 1), dt.datetime(2026, 9, 1)])
    ws.append([None, "Budget", "Actual"])
    ws["B1"].number_format = "mmm-yy"
    ws["C1"].number_format = "mmm-yy"
    for _gl, d, _t, b, a in LINES:
        ws.append([d, b, a])
    save(wb, "f17_date_headers.xlsx")


def f18_no_type_unsigned() -> None:
    """Plain unsigned file with no Type column and no GL numbers: every line needs a label."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Budget", "Actual"])
    for _gl, d, _t, b, a in LINES:
        ws.append([d, b, a])
    save(wb, "f18_no_type_unsigned.xlsx")


def f19_signed_subtotals() -> None:
    """Signed ledger P&L with profit subtotals (credits negative), no title block, no GL column."""
    wb = Workbook()
    ws = wb.active
    ws.title = "P&L"
    for row in [
        ["Account Description", "Budget", "Actual"],
        ["Product Revenue", -500000, -540000],
        ["Service Revenue", -200000, -185000],
        ["Total Revenue", -700000, -725000],
        ["Cost of Goods Sold", 220000, 236000],
        ["Gross Profit", -480000, -489000],
        ["Salaries & Wages", 180000, 191000],
        ["Rent", 30000, 30000],
        ["Total Opex", 210000, 221000],
        ["Net Income", -270000, -268000],
    ]:
        ws.append(row)
    save(wb, "f19_signed_subtotals.xlsx")


def f20_rounded_thousands() -> None:
    """$000s report: details rounded, subtotal computed from unrounded figures (off by 1)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    title_block(ws, "Q3 2026", "($000s)")
    ws.append(["Account Description", "Type", "Budget", "Actual"])
    for row in [
        ["Product Revenue", "Revenue", 500, 540],
        ["Service Revenue", "Revenue", 200, 185],
        ["Total Revenue", None, 700, 725],
        ["Salaries & Wages", "Expense", 180, 191],
        ["Marketing - Digital", "Expense", 40, 52],
        ["Rent", "Expense", 30, 30],
        ["Total Opex", None, 251, 273],
    ]:
        ws.append(row)
    save(wb, "f20_rounded_thousands.xlsx")


def f21_section_headers() -> None:
    """Section caption rows with no amounts inside the table, and blank spacer rows."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Budget", "Actual"])
    for row in [
        ["REVENUE", None, None],
        ["Product Revenue", 500000, 540000],
        ["Service Revenue", 200000, 185000],
        [None, None, None],
        ["OPERATING EXPENSES", None, None],
        ["Salaries & Wages", 180000, 191000],
        ["Rent", 30000, 30000],
    ]:
        ws.append(row)
    save(wb, "f21_section_headers.xlsx")


def f22_budget_actual_prior() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Type", "Budget", "Actual", "Prior Year"])
    for _gl, d, t, b, a in LINES:
        ws.append([d, t, b, a, round(a * 0.9)])
    save(wb, "f22_budget_actual_prior.xlsx")


def f23_month_and_ytd() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["GL Account", "Account Description", "Sep-26 Actual", "Sep-26 Budget", "Actual YTD", "Budget YTD"])
    for gl, d, _t, b, a in LINES:
        ws.append([gl, d, round(a / 9), round(b / 9), a, b])
    save(wb, "f23_month_and_ytd.xlsx")


def f24_header_000() -> None:
    """Unit only in the column headers, no caption."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BvA"
    ws.append(["Account Description", "Type", "Budget ($000)", "Actual ($000)"])
    for _gl, d, t, b, a in LINES:
        ws.append([d, t, b / 1000, a / 1000])
    save(wb, "f24_header_000.xlsx")


if __name__ == "__main__":
    for fn in [
        f01_title_block,
        f02_signed_ledger,
        f03_thousands_caption,
        f04_dashes,
        f05_blank_budgets,
        f06_two_files,
        f07_hidden_row,
        f08_formula_no_cache,
        f09_merged_header,
        f10_bom_csv,
        f11_period_columns,
        f12_nested_subtotals,
        f13_var_columns,
        f14_realistic_combo,
        f15_parens_csv,
        f16_cover_sheet,
        f17_date_headers,
        f18_no_type_unsigned,
        f19_signed_subtotals,
        f20_rounded_thousands,
        f21_section_headers,
        f22_budget_actual_prior,
        f23_month_and_ytd,
        f24_header_000,
    ]:
        fn()
    print(sorted(p.name for p in OUT.iterdir()))
