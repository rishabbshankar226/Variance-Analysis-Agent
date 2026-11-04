"""Build e1.xlsx: a fictional statement laid out like EDGAR's Financial_Report.xlsx, whose per-share lines say "EPS"."""

import sys

from openpyxl import Workbook


def build(path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Consolidated Statements of Ope"
    ws["A1"] = "CONSOLIDATED STATEMENTS OF OPERATIONS - USD ($) shares in Thousands, $ in Millions"
    ws.cell(1, 2, "12 Months Ended")
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=3)
    ws.cell(2, 2, "Sep. 27, 2025")
    ws.cell(2, 3, "Sep. 28, 2024")
    for line in (("Net sales", 4100, 3900), ("Cost of sales", 2300, 2250), ("Gross margin", 1800, 1650),
                 ("Total operating expenses", 550, 520), ("Operating income", 1250, 1130), ("Net income", 1000, 900),
                 ("Basic EPS", 6.1, 5.5), ("Diluted EPS", 6.0, 5.4)):
        ws.append(list(line))
    wb.save(path)


build(sys.argv[1])
