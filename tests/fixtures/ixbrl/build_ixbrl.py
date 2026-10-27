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


# Balance sheet and cash flow statements (PLAN.md R7-R9). The extra resources go in only when asked
# for, so the income fixtures keep their bytes.
POSITION_RESOURCES = """<xbrli:context id="I23"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:instant>2023-09-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
"""


def balance_rows() -> list[str]:
    def money(label: str, concept: str, now: str, before: str, *, sign: str | None = None) -> str:
        if sign:  # printed in parentheses: the instance holds it negative (sign="-")
            return row(label, "(" + fact(concept, "I25", now, sign=sign) + ")", "(" + fact(concept, "I24", before, sign=sign) + ")")
        return row(label, fact(concept, "I25", now), fact(concept, "I24", before))

    return [
        row("ASSETS"),
        row("Current assets:"),
        row("Cash and cash equivalents", "$" + fact("us-gaap:CashAndCashEquivalentsAtCarryingValue", "I25", "2,600"),
            "$" + fact("us-gaap:CashAndCashEquivalentsAtCarryingValue", "I24", "2,000")),
        money("Accounts receivable, net", "us-gaap:AccountsReceivableNetCurrent", "800", "770"),
        money("Total current assets", "us-gaap:AssetsCurrent", "3,400", "2,770"),
        money("Property and equipment, net", "us-gaap:PropertyPlantAndEquipmentNet", "3,100", "2,700"),
        money("Total assets", "us-gaap:Assets", "6,500", "5,470"),
        row("LIABILITIES AND STOCKHOLDERS' EQUITY"),
        money("Accounts payable", "us-gaap:AccountsPayableCurrent", "900", "820"),
        money("Total current liabilities", "us-gaap:LiabilitiesCurrent", "900", "820"),
        money("Long-term debt", "us-gaap:LongTermDebtNoncurrent", "1,500", "1,500"),
        money("Total liabilities", "us-gaap:Liabilities", "2,400", "2,320"),
        row("Commitments and contingencies (Note 9)"),
        row("Stockholders' equity:"),
        # Share counts and par value are tagged inside the label, as filings print them.
        row("Common stock, $" + fact("us-gaap:CommonStockParOrStatedValuePerShare", "I25", "0.01", unit="usdPerShare",
                                     scale="0", decimals="2") + " par value; "
            + fact("us-gaap:CommonStockSharesAuthorized", "I25", "500", unit="shares") + " shares authorized; "
            + fact("us-gaap:CommonStockSharesIssued", "I25", "120", unit="shares") + " and "
            + fact("us-gaap:CommonStockSharesIssued", "I24", "118", unit="shares") + " shares issued",
            fact("us-gaap:CommonStockValue", "I25", "1"), fact("us-gaap:CommonStockValue", "I24", "1")),
        money("Additional paid-in capital", "us-gaap:AdditionalPaidInCapital", "1,200", "1,100"),
        money("Retained earnings", "us-gaap:RetainedEarningsAccumulatedDeficit", "2,999", "2,149"),
        row("Treasury stock, at cost", "(" + fact("us-gaap:TreasuryStockValue", "I25", "100") + ")",
            "(" + fact("us-gaap:TreasuryStockValue", "I24", "100") + ")"),
        money("Total stockholders' equity", "us-gaap:StockholdersEquity", "4,100", "3,150"),
        money("Total liabilities and stockholders' equity", "us-gaap:LiabilitiesAndStockholdersEquity", "6,500", "5,470"),
    ]


def cash_flow_rows() -> list[str]:
    def flow(label: str, concept: str, now: str, before: str, *, out: tuple[bool, bool] = (False, False),
             sign: tuple[bool, bool] = (False, False)) -> str:
        cells = []
        for context, text, printed_out, negative in (("FY25", now, out[0], sign[0]), ("FY24", before, out[1], sign[1])):
            tag = fact(concept, context, text, sign="-" if negative else None)
            cells.append(f"({tag})" if printed_out else tag)
        return row(label, *cells)

    return [
        row("Operating activities:"),
        flow("Net income", "us-gaap:NetIncomeLoss", "1,450", "1,330"),
        flow("Depreciation and amortization", "us-gaap:DepreciationDepletionAndAmortization", "200", "180"),
        flow("Increase in accounts receivable", "us-gaap:IncreaseDecreaseInAccountsReceivable", "30", "20", out=(True, True)),
        flow("Net cash provided by operating activities", "us-gaap:NetCashProvidedByUsedInOperatingActivities",
             "1,620", "1,490"),
        row("Investing activities:"),
        flow("Purchases of property and equipment", "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "600", "500",
             out=(True, True)),
        flow("Net cash used in investing activities", "us-gaap:NetCashProvidedByUsedInInvestingActivities", "600", "500",
             out=(True, True), sign=(True, True)),
        row("Financing activities:"),
        flow("Dividends paid", "us-gaap:PaymentsOfDividends", "400", "350", out=(True, True)),
        flow("Net cash used in financing activities", "us-gaap:NetCashProvidedByUsedInFinancingActivities", "400", "350",
             out=(True, True), sign=(True, True)),
        flow("Effect of exchange rate changes on cash",
             "us-gaap:EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "20", "10",
             out=(True, False), sign=(True, False)),
        flow("Net increase in cash, cash equivalents and restricted cash",
             "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
             "600", "650"),
        row("Cash, cash equivalents and restricted cash, beginning of year",
            fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I24", "2,000"),
            fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I23", "1,350")),
        row("Cash, cash equivalents and restricted cash, end of year",
            "$" + fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I25", "2,600"),
            "$" + fact("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "I24", "2,000")),
        row("Supplemental disclosure:"),
        flow("Cash paid for interest", "us-gaap:InterestPaidNet", "45", "38"),
    ]


def position_filing(title: str, rows: list[str], caption: str = "(In millions, except per-share amounts)") -> bytes:
    body = statement(title, rows, caption)
    return document(body).replace("</ix:resources>", POSITION_RESOURCES + "</ix:resources>").encode("utf-8")


def all_statements_filing() -> bytes:
    body = (statement("CONSOLIDATED STATEMENTS OF OPERATIONS", income_rows())
            + statement("CONSOLIDATED BALANCE SHEETS", balance_rows())
            + statement("CONSOLIDATED STATEMENTS OF CASH FLOWS", cash_flow_rows()))
    return document(body).replace("</ix:resources>", POSITION_RESOURCES + "</ix:resources>").encode("utf-8")


# A 10-Q for LTM (PLAN.md R11): the second quarter of fiscal 2026, after the 10-K's year ended
# 2025-09-27. Year-to-date columns start the day after that year ends, and a year earlier.
QUARTER_CONTEXTS = {
    "YTD26": ("2025-09-28", "2026-03-28"), "YTD25": ("2024-09-29", "2025-03-29"),
    "Q26": ("2025-12-28", "2026-03-28"), "Q25": ("2024-12-29", "2025-03-29"),
}


def _contexts(periods: dict[str, tuple[str, str]]) -> str:
    return "".join(
        f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0009999999'
        f'</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>{start}</xbrli:startDate>'
        f'<xbrli:endDate>{end}</xbrli:endDate></xbrli:period></xbrli:context>' for cid, (start, end) in periods.items())


def quarter_rows(*, net_sales: str = "2,200", extra: list[str] | None = None) -> list[str]:
    def line(label: str, concept: str, quarter: tuple[str, str], ytd: tuple[str, str], *, out: bool = False) -> str:
        cells = [fact(concept, c, v) for c, v in zip(("Q26", "Q25", "YTD26", "YTD25"), (*quarter, *ytd), strict=True)]
        return row(label, *(f"({cell})" if out else cell for cell in cells))

    return [
        line("Net sales", "us-gaap:Revenues", ("1,150", "1,020"), (net_sales, "2,000")),
        line("Cost of sales", "us-gaap:CostOfRevenue", ("620", "560"), ("1,200", "1,100")),
        line("Gross margin", "us-gaap:GrossProfit", ("530", "460"), ("1,000", "900")),
        line("Research and development", "us-gaap:ResearchAndDevelopmentExpense", ("80", "75"), ("160", "150")),
        line("Interest expense", "us-gaap:InterestExpense", ("13", "10"), ("25", "20"), out=True),
        *(extra or []),
        line("Net income", "us-gaap:NetIncomeLoss", ("437", "375"), ("815", "730")),
        row("Basic (in dollars per share)",
            *(fact("us-gaap:EarningsPerShareBasic", c, v, unit="usdPerShare", scale="0", decimals="2")
              for c, v in zip(("Q26", "Q25", "YTD26", "YTD25"), ("1.80", "1.60", "3.40", "3.10"), strict=True))),
    ]


def quarter_filing(rows: list[str] | None = None, *, title: str = "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS",
                   periods: dict[str, tuple[str, str]] | None = None) -> bytes:
    body = statement(title, rows or quarter_rows())
    resources = _contexts(periods or QUARTER_CONTEXTS)
    return document(body).replace("</ix:resources>", resources + "</ix:resources>").encode("utf-8")
