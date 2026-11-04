"""Build b1.xlsx (a target row), b2.xlsx and b2n.xlsx (limit rows): fictional rates under percent number formats."""

import sys

from openpyxl import Workbook


def build(path: str, header: list[str], row: list[object], formats: dict[str, str]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    ws.append(row)
    for cell, code in formats.items():
        ws[cell].number_format = code
    wb.save(path)


build(sys.argv[1], ["Line Item", "Measure", "Actual", "Target", "Tolerance"],
      ["Fictional yield", "Percent", 0.402, 0.40, 0.0025], {"C2": "0.0%", "D2": "0.0%", "E2": "0.00%"})
build(sys.argv[2], ["Line Item", "Measure", "Actual", "Limit", "Limit Kind", "Buffer"],
      ["Fictional margin", "Percent", 0.41, 0.40, "Min", 0.005], {"C2": "0.0%", "D2": "0.0%", "F2": "0.0%"})
build(sys.argv[3], ["Line Item", "Measure", "Actual", "Limit", "Limit Kind", "Buffer"],
      ["Fictional margin", "Percent", 0.403, 0.40, "Min", 0.005], {"C2": "0.0%", "D2": "0.0%", "F2": "0.0%"})
