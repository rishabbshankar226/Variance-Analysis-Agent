from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Iterable

from .models import (
    Aggregate,
    AnalysisConfig,
    AnalysisResult,
    AnalyzedRow,
    DriverEvidence,
    LineType,
    Status,
)
from .parsing import first_present, normalize_row, parse_decimal


_LINE_ITEM_KEYS = ("line_item", "line", "item", "account", "account_name", "category")
_BUDGET_KEYS = ("budget", "budget_amount", "plan", "planned")
_ACTUAL_KEYS = ("actual", "actual_amount", "actuals")
_TYPE_KEYS = ("type", "line_type", "revenue_expense_type", "classification")

_SUMMARY_RE = re.compile(r"\b(grand\s+total|sub\s*total|subtotal|total)\b", re.IGNORECASE)

# Conservative label cues. Anything not clearly matched remains Unclassified.
_REVENUE_RE = re.compile(r"\b(revenue|sales|income)\b", re.IGNORECASE)
_EXPENSE_RE = re.compile(
    r"\b(expense|expenses|cost|costs|cogs|opex|payroll|rent|marketing|freight|utilities)\b",
    re.IGNORECASE,
)

_DRIVER_MODELS = (
    ("volume / price", "budget_volume", "actual_volume", "budget_price", "actual_price", "Volume", "Price"),
    ("units / price", "budget_units", "actual_units", "budget_price", "actual_price", "Units", "Price"),
    (
        "headcount / rate",
        "budget_headcount",
        "actual_headcount",
        "budget_rate",
        "actual_rate",
        "Headcount",
        "Rate",
    ),
    (
        "customers / rate",
        "budget_customers",
        "actual_customers",
        "budget_rate",
        "actual_rate",
        "Customers",
        "Rate",
    ),
)


def _required_value(
    row: dict[str, Any], candidates: Iterable[str], display_name: str, row_number: int
) -> Any:
    found = first_present(row, candidates)
    if found is None:
        raise ValueError(
            f"Row {row_number}: required field '{display_name}' was not found. "
            f"Accepted names: {', '.join(candidates)}."
        )
    return found[1]


def _classify_explicit(value: Any) -> LineType | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"revenue", "income", "sales", "rev"}:
        return LineType.REVENUE
    if text in {"expense", "expenses", "cost", "costs", "opex", "cogs"}:
        return LineType.EXPENSE
    return None


def _classify(line_item: str, row: dict[str, Any], config: AnalysisConfig) -> LineType:
    if line_item in config.type_map:
        return config.type_map[line_item]

    type_field = first_present(row, _TYPE_KEYS)
    if type_field:
        explicit = _classify_explicit(type_field[1])
        if explicit:
            return explicit

    revenue_match = bool(_REVENUE_RE.search(line_item))
    expense_match = bool(_EXPENSE_RE.search(line_item))
    if revenue_match and not expense_match:
        return LineType.REVENUE
    if expense_match and not revenue_match:
        return LineType.EXPENSE
    return LineType.UNCLASSIFIED


def _percent_variance(budget: Decimal, actual: Decimal) -> tuple[Decimal | None, str | None]:
    if budget != 0:
        return (actual - budget) / budget, None
    if actual == 0:
        return Decimal("0"), None
    return None, "N/A (Unbudgeted)"


def _status(line_type: LineType, variance: Decimal) -> Status:
    if variance == 0:
        return Status.NEUTRAL
    if line_type == LineType.EXPENSE:
        return Status.UNFAVORABLE if variance > 0 else Status.FAVORABLE
    if line_type == LineType.REVENUE:
        return Status.FAVORABLE if variance > 0 else Status.UNFAVORABLE
    return Status.UNCLASSIFIED


def _driver_evidence(
    row: dict[str, Any], budget: Decimal, actual: Decimal, line_item: str
) -> DriverEvidence | None:
    tolerance = max(Decimal("0.01"), abs(budget) * Decimal("0.000001"), abs(actual) * Decimal("0.000001"))

    for model_name, bq, aq, br, ar, quantity_label, rate_label in _DRIVER_MODELS:
        required = (bq, aq, br, ar)
        if not all(key in row and row[key] not in (None, "") for key in required):
            continue

        budget_quantity = parse_decimal(row[bq], field=bq, line_item=line_item)
        actual_quantity = parse_decimal(row[aq], field=aq, line_item=line_item)
        budget_rate = parse_decimal(row[br], field=br, line_item=line_item)
        actual_rate = parse_decimal(row[ar], field=ar, line_item=line_item)

        modeled_budget = budget_quantity * budget_rate
        modeled_actual = actual_quantity * actual_rate
        reconciles = abs(modeled_budget - budget) <= tolerance and abs(modeled_actual - actual) <= tolerance

        quantity_effect = (actual_quantity - budget_quantity) * budget_rate
        rate_effect = (actual_rate - budget_rate) * actual_quantity

        return DriverEvidence(
            label=model_name,
            components=((f"{quantity_label} effect", quantity_effect), (f"{rate_label} effect", rate_effect)),
            reconciles=reconciles,
        )
    return None


def _aggregate(rows: list[AnalyzedRow], line_type: LineType) -> Aggregate:
    included = [
        row
        for row in rows
        if row.line_type == line_type and not row.excluded_from_aggregation
    ]
    budget = sum((row.budget for row in included), Decimal("0"))
    actual = sum((row.actual for row in included), Decimal("0"))
    variance = actual - budget
    pct, label = _percent_variance(budget, actual)
    return Aggregate(
        budget=budget,
        actual=actual,
        variance_dollars=variance,
        variance_percent=pct,
        percent_label=label,
        status=_status(line_type, variance),
    )


def analyze_rows(rows: list[dict[str, Any]], config: AnalysisConfig) -> AnalysisResult:
    if config.dollar_threshold < 0 or config.percent_threshold < 0:
        raise ValueError("Materiality thresholds must be non-negative.")

    analyzed: list[AnalyzedRow] = []
    warnings: list[str] = []

    for index, source_row in enumerate(rows, start=2):
        row = normalize_row(source_row)
        line_item_raw = _required_value(row, _LINE_ITEM_KEYS, "Line Item", index)
        line_item = str(line_item_raw).strip()
        if not line_item:
            raise ValueError(f"Row {index}: Line Item is blank.")

        budget = parse_decimal(
            _required_value(row, _BUDGET_KEYS, "Budget", index),
            field="Budget",
            line_item=line_item,
        )
        actual = parse_decimal(
            _required_value(row, _ACTUAL_KEYS, "Actual", index),
            field="Actual",
            line_item=line_item,
        )

        line_type = _classify(line_item, row, config)
        excluded = bool(_SUMMARY_RE.search(line_item))
        variance = actual - budget
        pct, pct_label = _percent_variance(budget, actual)
        material = abs(variance) > config.dollar_threshold or (
            pct is not None and abs(pct) > config.percent_threshold
        )
        driver = _driver_evidence(row, budget, actual, line_item)

        analyzed.append(
            AnalyzedRow(
                line_item=line_item,
                line_type=line_type,
                budget=budget,
                actual=actual,
                variance_dollars=variance,
                variance_percent=pct,
                percent_label=pct_label,
                status=_status(line_type, variance),
                material=material,
                excluded_from_aggregation=excluded,
                driver_evidence=driver,
                raw=row,
            )
        )

    normalized_names: dict[str, int] = {}
    for row in analyzed:
        key = row.line_item.strip().casefold()
        normalized_names[key] = normalized_names.get(key, 0) + 1
    duplicates = sorted(
        row.line_item
        for row in analyzed
        if normalized_names[row.line_item.strip().casefold()] > 1
    )
    duplicate_unique = list(dict.fromkeys(duplicates))
    if duplicate_unique:
        warnings.append(
            "Duplicate line-item names detected; confirm these are intentional dimensional rows: "
            + ", ".join(duplicate_unique[:5])
            + ("..." if len(duplicate_unique) > 5 else "")
        )

    unclassified = [row.line_item for row in analyzed if row.line_type == LineType.UNCLASSIFIED]
    if unclassified:
        sample = ", ".join(unclassified[:5])
        suffix = "..." if len(unclassified) > 5 else ""
        warnings.append(
            f"{len(unclassified)} row(s) are Unclassified and excluded from Revenue/Expense totals: "
            f"{sample}{suffix}"
        )

    excluded = [row.line_item for row in analyzed if row.excluded_from_aggregation]
    if excluded:
        warnings.append(
            f"{len(excluded)} subtotal/total row(s) were excluded from detail aggregation to avoid double counting."
        )

    nonreconciling = [
        row.line_item
        for row in analyzed
        if row.driver_evidence is not None and not row.driver_evidence.reconciles
    ]
    if nonreconciling:
        warnings.append(
            "Driver fields were present but did not reconcile to Budget/Actual for: "
            + ", ".join(nonreconciling[:5])
            + ("..." if len(nonreconciling) > 5 else "")
        )

    material_rows = sorted(
        (row for row in analyzed if row.material),
        key=lambda row: abs(row.variance_dollars),
        reverse=True,
    )

    revenue = _aggregate(analyzed, LineType.REVENUE)
    expenses = _aggregate(analyzed, LineType.EXPENSE)

    # Final deterministic verification.
    for row in analyzed:
        assert row.variance_dollars == row.actual - row.budget
        expected_material = abs(row.variance_dollars) > config.dollar_threshold or (
            row.variance_percent is not None
            and abs(row.variance_percent) > config.percent_threshold
        )
        assert row.material == expected_material
    assert material_rows == sorted(
        material_rows, key=lambda row: abs(row.variance_dollars), reverse=True
    )
    revenue_rows = [
        row for row in analyzed
        if row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
    ]
    expense_rows = [
        row for row in analyzed
        if row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
    ]
    assert revenue.budget == sum((row.budget for row in revenue_rows), Decimal("0"))
    assert revenue.actual == sum((row.actual for row in revenue_rows), Decimal("0"))
    assert expenses.budget == sum((row.budget for row in expense_rows), Decimal("0"))
    assert expenses.actual == sum((row.actual for row in expense_rows), Decimal("0"))

    return AnalysisResult(
        config=config,
        rows=tuple(analyzed),
        material_rows=tuple(material_rows),
        revenue=revenue,
        expenses=expenses,
        warnings=tuple(warnings),
    )
