"""Conservative Revenue/Expense inference from a line-item label.

One classifier serves the analysis engine and assisted intake (signed-ledger detection), so a
label never counts as Revenue in one place and as something else in the other. Inference only
runs when there is no type-map entry and no recognised Type column; anything doubtful stays
Unclassified so the user decides.
"""

from __future__ import annotations

import re

from .models import LineType

REVENUE_RE = re.compile(r"\b(revenue|sales|income)\b", re.IGNORECASE)
EXPENSE_RE = re.compile(
    r"\b(expense|expenses|cost|costs|cogs|opex|payroll|rent|marketing|freight|utilities)\b",
    re.IGNORECASE,
)

# Cost nouns that make a line an expense even when a revenue word only qualifies them:
# "Sales Commissions", "Income Taxes", "Sales Returns and Allowances". Revenue stated net of
# them ("Revenue, net of returns") is still revenue.
_COST_NOUN_RE = re.compile(
    r"\b(tax|taxes|taxation|commission|commissions|salary|salaries|wage|wages|compensation|"
    r"provision|provisions|return|returns|bonus|bonuses|discount|discounts|allowance|allowances|"
    r"rebate|rebates|refund|refunds)\b",
    re.IGNORECASE,
)
_NET_OF_RE = re.compile(r"\bnet\s+of\b", re.IGNORECASE)

# Profit measures and subtotals already net costs against revenue; they are not additive.
_PROFIT_RES = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(net|operating|gross)\s+(income|profit|earnings|loss|margin)\b",
        r"\b(income|profit|earnings|loss)\s+(before|after)\b",
        r"\bpre[-\s]?tax\s+(income|profit|earnings|loss)\b",
        r"\b(income|profit|loss)\s+from\s+operations\b",
        r"\bcomprehensive\s+(income|loss)\b",
        r"\bebit(da)?\b",
        r"\bnopat\b",
    )
)


def explicit_line_type(value: object) -> LineType | None:
    """Revenue/Expense for the words a Type column or type map may use; None if unrecognised."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"revenue", "income", "sales", "rev"}:
        return LineType.REVENUE
    if text in {"expense", "expenses", "cost", "costs", "opex", "cogs"}:
        return LineType.EXPENSE
    return None


def is_profit_measure(label: str) -> bool:
    return any(pattern.search(label) for pattern in _PROFIT_RES)


def infer_line_type(label: str) -> tuple[LineType, str]:
    """Return ``(line type, reason)`` for a label; the reason is the audit's decision source."""
    if is_profit_measure(label):
        return LineType.UNCLASSIFIED, "non_additive_profit"
    if _COST_NOUN_RE.search(label) and not _NET_OF_RE.search(label):
        return LineType.EXPENSE, "label_inference"

    revenue_match = bool(REVENUE_RE.search(label))
    expense_match = bool(EXPENSE_RE.search(label))
    if revenue_match and not expense_match:
        return LineType.REVENUE, "label_inference"
    if expense_match and not revenue_match:
        return LineType.EXPENSE, "label_inference"
    return LineType.UNCLASSIFIED, "unclassified"
