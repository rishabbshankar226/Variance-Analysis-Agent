"""Independent answer key for the Chrome QA fixtures.

Stdlib only: this deliberately imports nothing from ``variance_agent`` so the
chatbot is never graded against its own arithmetic. Rules follow
``docs/financial-rules.md``:

* variance = actual - budget; percent = variance / |budget|, N/A when budget is 0
  (0/0 is a 0% neutral row);
* revenue up is favourable, expense up is unfavourable, zero is neutral;
* material when |variance| > dollar threshold OR |percent| > percent threshold
  (strict, percent test skipped for a zero budget);
* a single category "Total ..." row that reconciles to its detail rows is excluded;
* rows without a recognised type stay unclassified and out of the totals.

Usage::

    python scripts/qa_oracle.py                      # write expected/*.json
    python scripts/qa_oracle.py --generate-large     # (re)create large.csv first
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "chrome_qa"
EXPECTED_DIR = FIXTURE_DIR / "expected"
FIXTURES = (
    ROOT / "examples" / "sample_variance.csv",
    ROOT / "examples" / "sample_eur.csv",
    FIXTURE_DIR / "fav_net.csv",
    FIXTURE_DIR / "unfav_net.csv",
    FIXTURE_DIR / "mixed_sign.csv",
    FIXTURE_DIR / "edge_values.csv",
    FIXTURE_DIR / "names.csv",
    FIXTURE_DIR / "structure.csv",
    FIXTURE_DIR / "large.csv",
)
DOLLAR_THRESHOLD = Decimal("10000")
PERCENT_THRESHOLD = Decimal("5")  # percent points

_SUMMARY = re.compile(
    r"(?:grand\s+total|sub\s*total|total)\s+(?:revenue|sales|income|expenses?|costs?|opex)"
    r"|(?:revenue|sales|income|expenses?|costs?|opex)\s+(?:grand\s+total|sub\s*total|total)",
    re.IGNORECASE,
)
_REVENUE_WORDS = re.compile(r"\b(revenue|sales|income)\b", re.IGNORECASE)
_EXPENSE_WORDS = re.compile(
    r"\b(expenses?|costs?|cogs|opex|payroll|rent|marketing|freight|utilities)\b", re.IGNORECASE
)
TENTH = Decimal("0.1")
MAX_LISTED = 50  # keeps large.json reviewable


@dataclass
class Line:
    line_item: str
    type: str
    budget: Decimal
    actual: Decimal
    summary: bool

    @property
    def variance(self) -> Decimal:
        return self.actual - self.budget


def money(text: str) -> Decimal:
    cleaned = text.strip().replace(",", "")
    for symbol in "$€£":
        cleaned = cleaned.replace(symbol, "")
    return Decimal(cleaned)


def line_type(name: str, explicit: str) -> str:
    explicit = explicit.strip().lower()
    if explicit in {"revenue", "expense"}:
        return explicit.capitalize()
    if explicit:
        return "Unclassified"
    revenue, expense = bool(_REVENUE_WORDS.search(name)), bool(_EXPENSE_WORDS.search(name))
    if revenue and not expense:
        return "Revenue"
    if expense and not revenue:
        return "Expense"
    return "Unclassified"


def pct(variance: Decimal, base: Decimal) -> str:
    if base == 0:
        return "0.0" if variance == 0 else "N/A"
    return str((variance / abs(base) * 100).quantize(TENTH, rounding=ROUND_HALF_EVEN))


def direction(kind: str, variance: Decimal) -> str:
    if kind == "Unclassified":
        return "Unclassified"
    if variance == 0:
        return "Neutral"
    favourable = variance > 0 if kind == "Revenue" else variance < 0
    return "F" if favourable else "U"


def is_material(budget: Decimal, variance: Decimal) -> bool:
    if abs(variance) > DOLLAR_THRESHOLD:
        return True
    return budget != 0 and abs(variance) * 100 > abs(budget) * PERCENT_THRESHOLD


def compute(path: Path) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        raw = list(csv.DictReader(handle))
    lines: list[Line] = []
    for row in raw:
        name = row["Line Item"].strip()
        budget, actual = money(row["Budget"]), money(row["Actual"])
        kind = line_type(name, row.get("Type") or "")
        lines.append(Line(name, kind, budget, actual, bool(_SUMMARY.fullmatch(name))))

    for kind in ("Revenue", "Expense"):
        details = [ln for ln in lines if ln.type == kind and not ln.summary]
        for summary in (ln for ln in lines if ln.type == kind and ln.summary):
            reconciles = (summary.budget == sum((d.budget for d in details), Decimal(0))
                          and summary.actual == sum((d.actual for d in details), Decimal(0)))
            summary.summary = bool(details) and reconciles

    detail = [ln for ln in lines if not ln.summary]

    def total(kind: str) -> dict[str, str]:
        rows = [ln for ln in detail if ln.type == kind]
        budget = sum((ln.budget for ln in rows), Decimal(0))
        actual = sum((ln.actual for ln in rows), Decimal(0))
        return {"budget": str(budget), "actual": str(actual), "variance": str(actual - budget),
                "percent": pct(actual - budget, budget),
                "direction": direction(kind, actual - budget)}

    revenue, expenses = total("Revenue"), total("Expense")
    rev_b, rev_a = Decimal(revenue["budget"]), Decimal(revenue["actual"])
    budget_profit = rev_b - Decimal(expenses["budget"])
    actual_profit = rev_a - Decimal(expenses["actual"])
    net = actual_profit - budget_profit
    budget_margin = pct(budget_profit, rev_b) if rev_b else "N/A"
    actual_margin = pct(actual_profit, rev_a) if rev_a else "N/A"
    if "N/A" in (budget_margin, actual_margin):
        margin_move = "N/A"
    else:
        delta = Decimal(actual_margin) - Decimal(budget_margin)
        margin_move = "up" if delta > 0 else "down" if delta < 0 else "flat"

    def view(ln: Line) -> dict[str, object]:
        return {"line_item": ln.line_item, "type": ln.type, "budget": str(ln.budget),
                "actual": str(ln.actual), "variance": str(ln.variance),
                "percent": pct(ln.variance, ln.budget),
                "direction": direction(ln.type, ln.variance),
                "material": is_material(ln.budget, ln.variance)}

    by_abs = sorted(detail, key=lambda ln: abs(ln.variance), reverse=True)
    material = [ln.line_item for ln in by_abs if is_material(ln.budget, ln.variance)]
    classified = [ln for ln in by_abs if ln.type != "Unclassified"]
    fav = [ln for ln in classified if direction(ln.type, ln.variance) == "F"]
    unfav = [ln for ln in classified if direction(ln.type, ln.variance) == "U"]
    return {
        "fixture": path.name,
        "thresholds": {"dollar": str(DOLLAR_THRESHOLD), "percent": str(PERCENT_THRESHOLD)},
        "lines": [view(ln) for ln in detail] if len(detail) <= MAX_LISTED else f"{len(detail)} rows",
        "excluded_summaries": [ln.line_item for ln in lines if ln.summary],
        "unclassified": [ln.line_item for ln in detail if ln.type == "Unclassified"],
        "totals": {
            "revenue": revenue,
            "expenses": expenses,
            "budget_operating_profit": str(budget_profit),
            "actual_operating_profit": str(actual_profit),
            "net_operating_impact": str(net),
            "net_direction": "F" if net > 0 else "U" if net < 0 else "Neutral",
            "budget_margin_pct": budget_margin,
            "actual_margin_pct": actual_margin,
            "margin_move": margin_move,
            "actual_margin_negative": actual_profit < 0,
        },
        "material_count": len(material),
        "material_items": material if len(material) <= MAX_LISTED else material[:MAX_LISTED],
        "top3_by_abs": [ln.line_item for ln in by_abs[:3]],
        "largest_favourable": fav[0].line_item if fav else None,
        "largest_unfavourable": unfav[0].line_item if unfav else None,
    }


def generate_large(path: Path, rows: int = 5000) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["Line Item", "Type", "Budget", "Actual"])
        for i in range(1, rows + 1):
            budget = 1000 + i
            writer.writerow([f"Account {i:05d}", "Revenue" if i % 3 == 0 else "Expense",
                             budget, budget + (i * 37) % 2001 - 1000])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate-large", action="store_true")
    args = parser.parse_args()
    if args.generate_large:
        generate_large(FIXTURE_DIR / "large.csv")
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    for fixture in FIXTURES:
        key = compute(fixture)
        out = EXPECTED_DIR / f"{fixture.stem}.json"
        out.write_text(json.dumps(key, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{fixture.name}: written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
