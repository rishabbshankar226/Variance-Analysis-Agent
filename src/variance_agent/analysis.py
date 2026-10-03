from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal, localcontext
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
from .parsing import first_present, normalize_row, parse_decimal, is_missing
from .numeric import financial_context, ratio
from .currencies import validate_currency


_LINE_ITEM_KEYS = ("line_item", "line", "item", "account", "account_name", "category")
_BUDGET_KEYS = ("budget", "budget_amount", "plan", "planned")
_ACTUAL_KEYS = ("actual", "actual_amount", "actuals")
_TYPE_KEYS = ("type", "line_type", "revenue_expense_type", "classification")

_SUMMARY_RE = re.compile(r"\b(grand\s+total|sub\s*total|subtotal|total)\b", re.IGNORECASE)
_CATEGORY_SUMMARY_RE = re.compile(
    r"(?:(?:grand\s+total|sub\s*total|total)\s+"
    r"(?:revenue|sales|income|expenses?|costs?|cogs|opex)|"
    r"(?:revenue|sales|income|expenses?|costs?|cogs|opex)\s+"
    r"(?:grand\s+total|sub\s*total|total)|grand\s+total|sub\s*total|total)",
    re.IGNORECASE,
)
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
    candidates = tuple(candidates)
    present = [key for key in candidates if key in row]
    if len(present) > 1:
        raise ValueError(f"Row {row_number}: multiple aliases for '{display_name}': "
                         + ", ".join(present) + ". Supply one column per field.")
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


def _summary_candidate(line_item: str, row: dict[str, Any]) -> bool:
    if "row_kind" in row and not is_missing(row["row_kind"]):
        kind = str(row["row_kind"]).strip().casefold()
        if kind == "detail":
            return False
        if kind in {"total", "subtotal"}:
            return True
        raise ValueError(f"{line_item}: Row Kind must be Detail, Total, or Subtotal.")
    if _CATEGORY_SUMMARY_RE.fullmatch(line_item):
        return True
    if _SUMMARY_RE.search(line_item):
        raise ValueError(f"{line_item}: ambiguous summary label; specify Row Kind as "
                         "Detail, Total, or Subtotal.")
    return False


def _classify(line_item: str, row: dict[str, Any], config: AnalysisConfig) -> LineType:
    if line_item in config.type_map:
        return config.type_map[line_item]

    type_keys = [key for key in _TYPE_KEYS if key in row]
    if len(type_keys) > 1:
        raise ValueError(f"{line_item}: multiple classification aliases: {', '.join(type_keys)}.")
    type_field = first_present(row, _TYPE_KEYS)
    if type_field:
        explicit = _classify_explicit(type_field[1])
        if explicit:
            return explicit
        if type_field[1] is not None and str(type_field[1]).strip():
            return LineType.UNCLASSIFIED

    # Profit measures already net costs against revenue and are not additive sales.
    if re.search(r"\b(net|operating|gross)\s+(income|profit|earnings)\b", line_item, re.I):
        return LineType.UNCLASSIFIED

    revenue_match = bool(_REVENUE_RE.search(line_item))
    expense_match = bool(_EXPENSE_RE.search(line_item))
    if revenue_match and not expense_match:
        return LineType.REVENUE
    if expense_match and not revenue_match:
        return LineType.EXPENSE
    return LineType.UNCLASSIFIED


def _percent_variance(budget: Decimal, actual: Decimal) -> tuple[Decimal | None, str | None]:
    if budget != 0:
        return ratio(actual - budget, budget), None
    if actual == 0:
        return Decimal("0"), None
    return None, "N/A (Unbudgeted)"


def _is_material(budget: Decimal, variance: Decimal, config: AnalysisConfig) -> bool:
    if abs(variance) > config.dollar_threshold:
        return True
    if budget == 0:
        return False
    # Compare |variance| > threshold * |budget| without rounding a recurring ratio.
    with localcontext() as context:
        context.prec = max(context.prec, len(budget.as_tuple().digits)
                           + len(config.percent_threshold.as_tuple().digits))
        return abs(variance) > config.percent_threshold * abs(budget)


def _status(line_type: LineType, variance: Decimal) -> Status:
    if variance == 0:
        return Status.NEUTRAL
    if line_type == LineType.EXPENSE:
        return Status.UNFAVORABLE if variance > 0 else Status.FAVORABLE
    if line_type == LineType.REVENUE:
        return Status.FAVORABLE if variance > 0 else Status.UNFAVORABLE
    return Status.UNCLASSIFIED


def _driver_evidence(
    row: dict[str, Any], budget: Decimal, actual: Decimal, line_item: str, currency: str = "USD"
) -> DriverEvidence | None:
    tolerance = max(
        Decimal("0.01"),
        abs(budget) * Decimal("0.000001"),
        abs(actual) * Decimal("0.000001"),
    )

    fallback = None
    for model_name, bq, aq, br, ar, quantity_label, rate_label in _DRIVER_MODELS:
        required = (bq, aq, br, ar)
        if not all(key in row and not is_missing(row[key]) for key in required):
            continue

        budget_quantity = parse_decimal(row[bq], field=bq, line_item=line_item, currency=currency)
        actual_quantity = parse_decimal(row[aq], field=aq, line_item=line_item, currency=currency)
        budget_rate = parse_decimal(row[br], field=br, line_item=line_item, currency=currency)
        actual_rate = parse_decimal(row[ar], field=ar, line_item=line_item, currency=currency)

        modeled_budget = budget_quantity * budget_rate
        modeled_actual = actual_quantity * actual_rate
        reconciles = (
            abs(modeled_budget - budget) <= tolerance
            and abs(modeled_actual - actual) <= tolerance
        )

        quantity_effect = (actual_quantity - budget_quantity) * budget_rate
        rate_effect = (actual_rate - budget_rate) * actual_quantity
        variance = actual - budget
        variance_tolerance = max(Decimal("0.01"), abs(variance) * Decimal("0.000001"))
        reconciles = reconciles and (
            abs(quantity_effect + rate_effect - variance) <= variance_tolerance
        )

        evidence = DriverEvidence(
            label=model_name,
            components=(
                (f"{quantity_label} effect", quantity_effect),
                (f"{rate_label} effect", rate_effect),
            ),
            reconciles=reconciles,
        )
        if reconciles:
            return evidence
        if fallback is None:
            fallback = evidence
    return fallback


def _resolve_summary_rows(rows: list[AnalyzedRow]) -> list[AnalyzedRow]:
    detail_types = {
        row.line_type
        for row in rows
        if not row.excluded_from_aggregation and row.line_type != LineType.UNCLASSIFIED
    }

    for line_type in (LineType.REVENUE, LineType.EXPENSE):
        summaries = [
            row
            for row in rows
            if row.line_type == line_type and row.excluded_from_aggregation
        ]
        if line_type not in detail_types and len(summaries) > 1:
            raise ValueError(
                f"Multiple {line_type.value} summary rows were supplied without detail rows; "
                "aggregation would be ambiguous and could double count."
            )

    for line_type in (LineType.REVENUE, LineType.EXPENSE):
        details = [r for r in rows if r.line_type == line_type and not r.excluded_from_aggregation]
        summaries = [r for r in rows if r.line_type == line_type and r.excluded_from_aggregation]
        if not details or not summaries:
            continue
        # Without hierarchy metadata, multiple summaries cannot be assigned safely.
        if len(summaries) > 1:
            raise ValueError(f"Multiple {line_type.value} summary rows have ambiguous scope; "
                             "supply detail rows only or one reconciled total.")
        summary = summaries[0]
        if (abs(summary.budget - sum((r.budget for r in details), Decimal("0"))) > Decimal("0.01")
                or abs(summary.actual - sum((r.actual for r in details), Decimal("0"))) > Decimal("0.01")):
            raise ValueError(f"Summary {summary.line_item!r} does not reconcile to "
                             f"{line_type.value} detail rows; check for missing or overlapping data.")

    return [
        replace(
            row,
            excluded_from_aggregation=(
                row.excluded_from_aggregation and row.line_type in detail_types
            ),
        )
        for row in rows
    ]


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


def _verification_failure(message: str) -> RuntimeError:
    return RuntimeError(f"Final verification failed: {message}")


def _verify_result(
    rows: list[AnalyzedRow],
    material_rows: list[AnalyzedRow],
    revenue: Aggregate,
    expenses: Aggregate,
    config: AnalysisConfig,
) -> None:
    for row in rows:
        if row.variance_dollars != row.actual - row.budget:
            raise _verification_failure(f"dollar variance mismatch for {row.line_item!r}")
        expected_percent, expected_label = _percent_variance(row.budget, row.actual)
        if (row.variance_percent, row.percent_label) != (expected_percent, expected_label):
            raise _verification_failure(f"percentage mismatch for {row.line_item!r}")
        if row.status != _status(row.line_type, row.variance_dollars):
            raise _verification_failure(f"F/U status mismatch for {row.line_item!r}")
        expected_material = _is_material(row.budget, row.variance_dollars, config)
        if row.material != expected_material:
            raise _verification_failure(f"materiality mismatch for {row.line_item!r}")

    expected_order = sorted(
        (row for row in rows if row.material and not row.excluded_from_aggregation),
        key=lambda row: abs(row.variance_dollars), reverse=True,
    )
    if material_rows != expected_order:
        raise _verification_failure("material variance membership or sort order is incorrect")

    for line_type, aggregate in ((LineType.REVENUE, revenue), (LineType.EXPENSE, expenses)):
        variance = aggregate.actual - aggregate.budget
        percent, label = _percent_variance(aggregate.budget, aggregate.actual)
        if (aggregate.variance_dollars, aggregate.variance_percent, aggregate.percent_label,
                aggregate.status) != (variance, percent, label, _status(line_type, variance)):
            raise _verification_failure(f"{line_type.value} aggregate metrics mismatch")

    revenue_rows = [
        row
        for row in rows
        if row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
    ]
    expense_rows = [
        row
        for row in rows
        if row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
    ]

    checks = (
        (revenue.budget, sum((row.budget for row in revenue_rows), Decimal("0")), "revenue budget"),
        (revenue.actual, sum((row.actual for row in revenue_rows), Decimal("0")), "revenue actual"),
        (expenses.budget, sum((row.budget for row in expense_rows), Decimal("0")), "expense budget"),
        (expenses.actual, sum((row.actual for row in expense_rows), Decimal("0")), "expense actual"),
    )
    for observed, expected, label in checks:
        if observed != expected:
            raise _verification_failure(f"{label} reconciliation mismatch")


@financial_context()
def analyze_rows(rows: list[dict[str, Any]], config: AnalysisConfig) -> AnalysisResult:
    validate_currency(config.currency)
    if not rows:
        raise ValueError("Dataset contains no data rows.")
    if not config.dollar_threshold.is_finite() or not config.percent_threshold.is_finite():
        raise ValueError("Materiality thresholds must be finite numbers.")
    if config.dollar_threshold < 0 or config.percent_threshold < 0:
        raise ValueError("Materiality thresholds must be non-negative.")

    # The exported Python API must uphold the same classification contract as
    # CLI type-map loading. Copy the mapping to detach caller-owned state.
    validated_type_map: dict[str, LineType] = {}
    for item, value in config.type_map.items():
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Type map keys must be nonblank line-item strings.")
        try:
            validated_type_map[item] = LineType(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Type map value for {item!r} must be Revenue, Expense, "
                             "or Unclassified.") from exc
    config = replace(
        config,
        type_map=validated_type_map,
        dollar_threshold=parse_decimal(config.dollar_threshold, field="dollar_threshold",
                                       line_item="Materiality"),
        percent_threshold=parse_decimal(config.percent_threshold, field="percent_threshold",
                                        line_item="Materiality"),
    )

    # Validate threshold precision/range even if no row reaches a comparison.
    +config.dollar_threshold
    +config.percent_threshold

    analyzed: list[AnalyzedRow] = []
    warnings: list[str] = []

    for index, source_row in enumerate(rows, start=2):
        row = normalize_row(source_row)
        line_item_raw = _required_value(row, _LINE_ITEM_KEYS, "Line Item", index)
        if isinstance(line_item_raw, (bool, list, dict, tuple, set)):
            raise ValueError(f"Row {index}: Line Item must be a scalar text or numeric label.")
        line_item = "" if line_item_raw is None else str(line_item_raw).strip()
        if not line_item:
            raise ValueError(f"Row {index}: Line Item is blank.")

        if "currency" in row and not is_missing(row["currency"]):
            row_currency = row["currency"]
            if not isinstance(row_currency, str):
                raise ValueError(f"{line_item}: Currency must be a reporting currency code.")
            row_currency = validate_currency(row_currency.strip().upper())
            if row_currency != config.currency:
                raise ValueError(f"{line_item}: row currency {row_currency} conflicts with "
                                 f"reporting currency {config.currency}.")

        budget = parse_decimal(
            _required_value(row, _BUDGET_KEYS, "Budget", index),
            field="Budget",
            line_item=line_item,
            currency=config.currency,
        )
        actual = parse_decimal(
            _required_value(row, _ACTUAL_KEYS, "Actual", index),
            field="Actual",
            line_item=line_item,
            currency=config.currency,
        )

        line_type = _classify(line_item, row, config)
        summary_candidate = _summary_candidate(line_item, row)
        variance = actual - budget
        pct, pct_label = _percent_variance(budget, actual)
        material = _is_material(budget, variance, config)
        driver = _driver_evidence(row, budget, actual, line_item, config.currency)

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
                excluded_from_aggregation=summary_candidate,
                driver_evidence=driver,
                raw=row,
            )
        )

    analyzed = _resolve_summary_rows(analyzed)

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

    unclassified = [
        row.line_item for row in analyzed if row.line_type == LineType.UNCLASSIFIED
    ]
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
        (
            row
            for row in analyzed
            if row.material and not row.excluded_from_aggregation
        ),
        key=lambda row: abs(row.variance_dollars),
        reverse=True,
    )

    revenue = _aggregate(analyzed, LineType.REVENUE)
    expenses = _aggregate(analyzed, LineType.EXPENSE)

    _verify_result(analyzed, material_rows, revenue, expenses, config)

    return AnalysisResult(
        config=config,
        rows=tuple(analyzed),
        material_rows=tuple(material_rows),
        revenue=revenue,
        expenses=expenses,
        warnings=tuple(warnings),
    )
