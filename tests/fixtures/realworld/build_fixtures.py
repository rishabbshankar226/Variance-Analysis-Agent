"""Build synthetic, fictional real-world fixtures for Phase 0.

All data generated here is entirely fictional and synthetic for FP&A test purposes.
"""

from __future__ import annotations

import csv
from pathlib import Path
from openpyxl import Workbook

FIXTURES_DIR = Path(__file__).resolve().parent


def build_fixture_a() -> None:
    """Fixture a: ERP budget-vs-actual Excel export with 4-row title block.
    
    Columns: GL Account, Account Description, Budget YTD, Actual YTD, Var $, Var %.
    Fictional Acme Corp ERP export.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Departmental_BvA"
    
    # 4-row title block
    ws.append(["FICTIONAL SYNTHETIC DATA - ACME CORP ERP EXPORT"])
    ws.append(["Report: YTD Departmental Variance Analysis"])
    ws.append(["Entity: 100 - North America (Fictional)"])
    ws.append(["Run Date: 2026-10-01 | Period: Q3 2026 | Currency: USD"])
    # Row 5: headers
    ws.append(["GL Account", "Account Description", "Budget YTD", "Actual YTD", "Var $", "Var %"])
    # Rows 6+: data rows
    ws.append(["6100", "Software Subscriptions", 120000, 135000, 15000, 0.125])
    ws.append(["6200", "Cloud Hosting Infrastructure", 250000, 240000, -10000, -0.040])
    ws.append(["6300", "Travel & Entertainment", 45000, 52000, 7000, 0.156])
    ws.append(["6400", "Professional Advisory Services", 80000, 95000, 15000, 0.188])
    ws.append(["6500", "Office Supplies & Facilities", 15000, 12000, -3000, -0.200])
    
    wb.save(FIXTURES_DIR / "fixture_a_erp_title_block.xlsx")
    wb.close()


def build_fixture_b() -> None:
    """Fixture b: Departmental P&L with nested subtotals.
    
    Subtotals: Total Revenue, Gross Profit, Total Operating Expenses, Net Income.
    """
    path = FIXTURES_DIR / "fixture_b_departmental_subtotals.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Line Item", "Budget", "Actual", "Notes"])
        writer.writerow(["Product Revenue", "500000", "520000", "Fictional detail"])
        writer.writerow(["Service Revenue", "200000", "190000", "Fictional detail"])
        writer.writerow(["Total Revenue", "700000", "710000", "Fictional subtotal"])
        writer.writerow(["Cost of Goods Sold", "300000", "310000", "Fictional detail"])
        writer.writerow(["Gross Profit", "400000", "400000", "Fictional subtotal"])
        writer.writerow(["R&D Expense", "120000", "125000", "Fictional detail"])
        writer.writerow(["Sales & Marketing Expense", "100000", "115000", "Fictional detail"])
        writer.writerow(["G&A Expense", "80000", "75000", "Fictional detail"])
        writer.writerow(["Total Operating Expenses", "300000", "315000", "Fictional subtotal"])
        writer.writerow(["Net Income", "100000", "85000", "Fictional subtotal"])


def build_fixture_c() -> None:
    """Fixture c: Signed-ledger export where revenue is negative (credit) and expenses positive."""
    path = FIXTURES_DIR / "fixture_c_signed_ledger.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Account", "Budget", "Actual", "Entity"])
        # Credits are stored negative in ERP
        writer.writerow(["Product Revenue", "-500000", "-520000", "Fictional Acme"])
        writer.writerow(["Services Revenue", "-200000", "-190000", "Fictional Acme"])
        writer.writerow(["Payroll Expense", "300000", "320000", "Fictional Acme"])
        writer.writerow(["Marketing Expense", "100000", "95000", "Fictional Acme"])
        writer.writerow(["Rent Expense", "50000", "50000", "Fictional Acme"])


def build_fixture_d() -> None:
    """Fixture d: Report in thousands ("($000s)" in the title) with accounting dashes and blank budgets."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    
    # Title in row 1 with ($000s)
    ws.append(["Acme Corp Operating Expense Summary ($000s) - Fictional"])
    # Row 2 headers
    ws.append(["Line Item", "Budget", "Actual", "Notes"])
    # Row 3: normal
    ws.append(["Salaries Expense", 500, 520, "In thousands"])
    # Row 4: accounting dash for zero spend
    ws.append(["Travel Expense", 40, "-", "Zero spend marked with accounting dash"])
    # Row 5: blank budget on unbudgeted project line
    ws.append(["New Cloud Migration Expense", "", 75, "Unbudgeted initiative"])
    # Row 6: normal
    ws.append(["Office Lease Expense", 80, 80, "In thousands"])
    
    wb.save(FIXTURES_DIR / "fixture_d_thousands_dashes_blanks.xlsx")
    wb.close()


def build_fixture_e() -> None:
    """Fixture e: Wide monthly layout.
    
    Columns: Account, Jul-26 Budget, Jul-26 Actual, Aug-26 Budget, Aug-26 Actual, Q3 Budget, Q3 Actual.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Wide_P&L"
    
    # Fictional disclaimer in A1
    ws.append([
        "Account",
        "Jul-26 Budget", "Jul-26 Actual",
        "Aug-26 Budget", "Aug-26 Actual",
        "Sep-26 Budget", "Sep-26 Actual",
        "Q3 Budget", "Q3 Actual",
    ])
    ws.append([
        "Subscription Revenue (Fictional)",
        100000, 105000,
        100000, 102000,
        100000, 108000,
        300000, 315000,
    ])
    ws.append([
        "Consulting Revenue (Fictional)",
        50000, 48000,
        50000, 52000,
        50000, 49000,
        150000, 149000,
    ])
    ws.append([
        "Salaries Expense (Fictional)",
        80000, 82000,
        80000, 81000,
        80000, 85000,
        240000, 248000,
    ])
    ws.append([
        "Marketing Expense (Fictional)",
        30000, 35000,
        30000, 28000,
        30000, 33000,
        90000, 96000,
    ])
    
    wb.save(FIXTURES_DIR / "fixture_e_wide_monthly.xlsx")
    wb.close()


def build_fixture_f() -> None:
    """Fixture f: Budget and actuals as two separate files keyed by GL account number."""
    f_bgt = FIXTURES_DIR / "fixture_f_budget_separate.csv"
    with f_bgt.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["GL Account", "Account Description", "Budget", "Fictional Note"])
        writer.writerow(["4010", "SaaS Subscription Revenue", "120000", "Fictional"])
        writer.writerow(["4020", "Professional Services", "45000", "Fictional"])
        writer.writerow(["5010", "Salaries & Wages", "75000", "Fictional"])
        writer.writerow(["5020", "Cloud Hosting Infrastructure", "30000", "Fictional"])
        writer.writerow(["5030", "Marketing & Advertising", "20000", "Fictional"])

    f_act = FIXTURES_DIR / "fixture_f_actuals_separate.csv"
    with f_act.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["GL Account", "Account Name", "Actual", "Fictional Note"])
        writer.writerow(["4010", "SaaS Subscriptions", "128000", "Fictional"])
        writer.writerow(["4020", "Professional Consulting Fees", "42000", "Fictional"])
        writer.writerow(["5010", "Salaries and Wages", "79000", "Fictional"])
        writer.writerow(["5020", "Cloud Hosting & Bandwidth", "34000", "Fictional"])
        writer.writerow(["5030", "Marketing Campaigns", "23000", "Fictional"])


def build_fixture_g() -> None:
    """Fixture g: Workbook where data sits on second sheet named 'BvA', active sheet is a cover page."""
    wb = Workbook()
    
    # Active sheet: Cover Page
    ws_cover = wb.active
    ws_cover.title = "Cover Page"
    ws_cover.append(["Acme Corporation - Monthly Management Pack (Fictional)"])
    ws_cover.append(["Confidential - For Internal Use Only"])
    ws_cover.append(["Author: Corporate FP&A Team"])
    ws_cover.append(["Notice: Tabular ledger data is located on worksheet 'BvA'."])
    
    # Second sheet: BvA
    ws_bva = wb.create_sheet(title="BvA")
    ws_bva.append(["Line Item", "Budget", "Actual", "Fictional Note"])
    ws_bva.append(["Product Revenue", 500000, 520000, "Fictional"])
    ws_bva.append(["Consulting Revenue", 200000, 195000, "Fictional"])
    ws_bva.append(["Payroll Expense", 300000, 310000, "Fictional"])
    ws_bva.append(["Marketing Expense", 100000, 115000, "Fictional"])
    
    wb.save(FIXTURES_DIR / "fixture_g_cover_page_active.xlsx")
    wb.close()


def build_fixture_h() -> None:
    """Fixture h: 120-line GL export with account numbers and no Type column.
    
    4000–4999: 40 revenue rows
    5000–8999: 80 expense rows
    No Type column and descriptions avoid 'revenue' or 'expense' keywords.
    """
    path = FIXTURES_DIR / "fixture_h_120_line_gl.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Account", "Budget", "Actual", "Fictional Entity"])
        
        # 40 Revenue accounts: 4001 to 4040
        for i in range(1, 41):
            acct_num = 4000 + i
            writer.writerow([f"Account {acct_num} Stream {i}", "10000", "10500", "Fictional Acme"])
            
        # 80 Expense accounts: 5001 to 5080
        for i in range(1, 81):
            acct_num = 5000 + i
            writer.writerow([f"Account {acct_num} Center {i}", "5000", "5200", "Fictional Acme"])


def build_fixture_i() -> None:
    """Fixture i: Tab-separated block as if copied from Excel."""
    path = FIXTURES_DIR / "fixture_i_pasted_tsv.txt"
    rows = [
        ["Account", "Budget", "Actual", "Fictional Note"],
        ["Subscription Revenue", "100000", "115000", "Fictional"],
        ["Services Revenue", "50000", "47000", "Fictional"],
        ["Payroll Expense", "60000", "68000", "Fictional"],
        ["Marketing Expense", "20000", "23000", "Fictional"],
        ["Rent Expense", "15000", "15000", "Fictional"],
    ]
    content = "\n".join("\t".join(row) for row in rows)
    path.write_text(content, encoding="utf-8")


def build_fixture_j() -> None:
    """Fixture j: 10-K three-year comparison table."""
    path = FIXTURES_DIR / "fixture_j_10k_three_years.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Line Item", "Type", "FY2025", "FY2024", "FY2023"])
        writer.writerow(["Product Revenue", "Revenue", "120000", "100000", "90000"])
        writer.writerow(["Cost of Revenue", "Expense", "50000", "45000", "40000"])
        writer.writerow(["Operating Expenses", "Expense", "30000", "32000", "28000"])
        writer.writerow(["New Segment Revenue", "Revenue", "5000", "0", "0"])


def build_fixture_k() -> None:
    """Fixture k: Forecast comparison."""
    path = FIXTURES_DIR / "fixture_k_forecast.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Line Item", "Type", "Forecast", "Actual"])
        writer.writerow(["Subscription Revenue", "Revenue", "110000", "115500"])
        writer.writerow(["Payroll Expense", "Expense", "65000", "68000"])


def build_fixture_l() -> None:
    """Fixture l: Both budget and forecast columns."""
    path = FIXTURES_DIR / "fixture_l_budget_and_forecast.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Line Item", "Type", "Budget", "Forecast", "Actual"])
        writer.writerow(["Subscription Revenue", "Revenue", "100000", "110000", "115500"])
        writer.writerow(["Payroll Expense", "Expense", "60000", "65000", "68000"])


def build_fixture_m() -> None:
    """Fixture m: Two years in reverse order (2024, 2025)."""
    path = FIXTURES_DIR / "fixture_m_years_reversed.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Line Item", "Type", "2024", "2025"])
        writer.writerow(["Product Revenue", "Revenue", "100000", "120000"])
        writer.writerow(["Cost of Revenue", "Expense", "45000", "50000"])


def build_fixture_n() -> None:
    """Fixture n: Numeric years (integers) in Excel headers."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Line Item", "Type", 2025, 2024])
    ws.append(["Product Revenue", "Revenue", 120000, 100000])
    ws.append(["Cost of Revenue", "Expense", 50000, 45000])
    wb.save(FIXTURES_DIR / "fixture_n_numeric_years.xlsx")
    wb.close()


def main() -> None:
    build_fixture_a()
    build_fixture_b()
    build_fixture_c()
    build_fixture_d()
    build_fixture_e()
    build_fixture_f()
    build_fixture_g()
    build_fixture_h()
    build_fixture_i()
    build_fixture_j()
    build_fixture_k()
    build_fixture_l()
    build_fixture_m()
    build_fixture_n()
    print("Successfully built all 14 real-world fixtures in tests/fixtures/realworld/")


if __name__ == "__main__":
    main()
