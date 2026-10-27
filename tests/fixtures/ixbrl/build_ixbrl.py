"""Build fictional Inline XBRL filings for the reader's tests (company HALVORSEN.FAKE, all values invented)."""

from __future__ import annotations

HEADER = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
 xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
 xmlns:us-gaap="http://fasb.org/us-gaap/2024" xmlns:hal="http://halvorsen.fake/2025"><head><title>HALVORSEN.FAKE 10-K</title>
<style>.x{color:red}</style><script>var trap = "<ix:nonFraction name='us-gaap:Revenues'>9</ix:nonFraction>";</script></head><body>
<div style="display:none"><ix:header><ix:hidden>{hidden}</ix:hidden><ix:resources>
<xbrli:context id="FY25"><xbrli:entity>
<xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>2024-09-29</xbrli:startDate><xbrli:endDate>2025-09-27</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="FY24"><xbrli:entity>
<xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>2023-10-01</xbrli:startDate><xbrli:endDate>2024-09-28</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="FY25_products"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier>
<xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:ProductMember</xbrldi:explicitMember>
</xbrli:segment></xbrli:entity>
<xbrli:period><xbrli:startDate>2024-09-29</xbrli:startDate><xbrli:endDate>2025-09-27</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="FY24_products"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier>
<xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:ProductMember</xbrldi:explicitMember>
</xbrli:segment></xbrli:entity>
<xbrli:period><xbrli:startDate>2023-10-01</xbrli:startDate><xbrli:endDate>2024-09-28</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="FY25_services"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier>
<xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:ServiceMember</xbrldi:explicitMember>
</xbrli:segment></xbrli:entity>
<xbrli:period><xbrli:startDate>2024-09-29</xbrli:startDate><xbrli:endDate>2025-09-27</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="FY24_services"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier>
<xbrli:segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:ServiceMember</xbrldi:explicitMember>
</xbrli:segment></xbrli:entity>
<xbrli:period><xbrli:startDate>2023-10-01</xbrli:startDate><xbrli:endDate>2024-09-28</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="I25"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>2025-09-27</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="I24"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>2024-09-28</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
<xbrli:unit id="usdPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>
<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
</ix:resources></ix:header></div>
"""


def fact(name: str, context: str, text: str, *, unit: str = "usd", scale: str = "6", decimals: str = "-6",
         fmt: str = "ixt:num-dot-decimal", sign: str | None = None, fact_id: str = "") -> str:
    attributes = f'name="{name}" contextRef="{context}" unitRef="{unit}" decimals="{decimals}" scale="{scale}"'
    attributes += f' format="{fmt}"' if fmt else ""
    attributes += f' sign="{sign}"' if sign else ""
    attributes += f' id="{fact_id}"' if fact_id else ""
    return f"<ix:nonFraction {attributes}>{text}</ix:nonFraction>"


def row(label: str, *cells: str) -> str:
    return "<tr><td>" + label + "</td>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"


def income_rows(net_sales: tuple[str, str] = ("4,100", "3,900")) -> list[str]:
    return [
        row("Net sales", "$" + fact("us-gaap:Revenues", "FY25", net_sales[0]),
            "$" + fact("us-gaap:Revenues", "FY24", net_sales[1])),
        row("Cost of sales", fact("us-gaap:CostOfRevenue", "FY25", "2,300"), fact("us-gaap:CostOfRevenue", "FY24", "2,250")),
        row("Gross margin", fact("us-gaap:GrossProfit", "FY25", "1,800"), fact("us-gaap:GrossProfit", "FY24", "1,650")),
        row("Research and development", fact("us-gaap:ResearchAndDevelopmentExpense", "FY25", "300"),
            fact("us-gaap:ResearchAndDevelopmentExpense", "FY24", "280")),
        row("Interest expense", "(" + fact("us-gaap:InterestExpense", "FY25", "50") + ")",
            "(" + fact("us-gaap:InterestExpense", "FY24", "40") + ")"),
        row("Net income", fact("us-gaap:NetIncomeLoss", "FY25", "1,450"), fact("us-gaap:NetIncomeLoss", "FY24", "1,330")),
        row("Basic (in dollars per share)",
            fact("us-gaap:EarningsPerShareBasic", "FY25", "6.10", unit="usdPerShare", scale="0", decimals="2"),
            fact("us-gaap:EarningsPerShareBasic", "FY24", "5.50", unit="usdPerShare", scale="0", decimals="2")),
    ]


def document(body: str, hidden: str = "") -> str:
    return HEADER.replace("{hidden}", hidden) + body + "</body></html>"


def statement(title: str, rows: list[str], caption: str = "(In millions, except per-share amounts)") -> str:
    return f"<p><b>HALVORSEN.FAKE</b></p><p>{title}</p><p>{caption}</p><table>" + "".join(rows) + "</table>"


def income_filing(rows: list[str] | None = None, hidden: str = "", extra: str = "") -> bytes:
    body = statement("CONSOLIDATED STATEMENTS OF OPERATIONS", rows or income_rows()) + extra
    return document(body, hidden).encode("utf-8")
