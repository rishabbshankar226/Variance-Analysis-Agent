from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal, DecimalException, localcontext
from typing import Callable, Iterable

from .models import (
    Aggregate,
    AnalysisConfig,
    AnalysisResult,
    AnalyzedRow,
    ComparisonBasis,
    DriverEvidence,
    DriverReconciliation,
    LineType,
    Status,
    SummaryVerification,
)
from .classification import explicit_line_type, infer_line_type
from .comparison import comparison_heading, zero_comparison_label
from .parsing import first_present, normalize_row, parse_decimal, is_missing
from .numeric import financial_context, ratio
from .currencies import validate_currency
from .limits import MAX_ROWS, validate_text

CLASSIFICATION_POLICY_ID = "flat-classification-v1"
DRIVER_POLICY_ID = "quantity-rate-reconcile-residual-v2"
AMOUNT_TOLERANCE = Decimal("0.01")
RELATIVE_DRIVER_TOLERANCE = Decimal("0.000001")


_LINE_ITEM_KEYS = ("line_item", "line", "item", "account", "account_name", "category")
_BUDGET_KEYS = ("budget", "budget_amount", "plan", "planned")
_ACTUAL_KEYS = ("actual", "actual_amount", "actuals")
_TYPE_KEYS = ("type", "line_type", "revenue_expense_type", "classification")

_SUMMARY_RE = re.compile(r"\b(grand\s+total|sub\s*total|subtotal|total)\b", re.IGNORECASE)
# A summary row names a whole category: "Total Revenue(s)", "Total Operating Expenses", "Total Costs and
# Expenses", "Revenues Total". "Income" counts only bare ("Total Income"): "Total Operating Income" is a
# profit measure, not a category, and still needs a Row Kind.
_TOTAL_WORD = r"(?:grand\s+total|sub\s*total|total)"
_CATEGORY_NAME = (
    r"(?:(?:(?:operating|net|other)\s+)?(?:revenues?|sales|expenses?|costs?(?:\s+and\s+expenses?)?|cogs|opex)"
    r"|income)"
)
_CATEGORY_SUMMARY_RE = re.compile(
    rf"(?:{_TOTAL_WORD}\s+{_CATEGORY_NAME}|{_CATEGORY_NAME}\s+{_TOTAL_WORD}|grand\s+total|sub\s*total|total)",
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
    row: dict[str, object],
    candidates: Iterable[str],
    display_name: str,
    row_number: int,
    *,
    list_accepted_names: bool = True,
) -> object:
    candidates = tuple(candidates)
    present = [key for key in candidates if key in row]
    if len(present) > 1:
        raise ValueError(f"Row {row_number}: multiple aliases for '{display_name}': "
                         + ", ".join(present) + ". Supply one column per field.")
    found = first_present(row, candidates)
    if found is None:
        accepted = f" Accepted names: {', '.join(candidates)}." if list_accepted_names else ""
        raise ValueError(f"Row {row_number}: required field '{display_name}' was not found.{accepted}")
    return found[1]


def _summary_candidate(line_item: str, row: dict[str, object]) -> tuple[bool, str]:
    if "row_kind" in row and not is_missing(row["row_kind"]):
        kind = str(row["row_kind"]).strip().casefold()
        if kind == "detail":
            return False, "explicit_detail"
        if kind in {"total", "subtotal"}:
            return True, "explicit_summary"
        raise ValueError(f"{line_item}: Row Kind must be Detail, Total, or Subtotal.")
    if _CATEGORY_SUMMARY_RE.fullmatch(line_item):
        return True, "inferred_summary"
    if _SUMMARY_RE.search(line_item):
        raise ValueError(f"{line_item}: ambiguous summary label; specify Row Kind as "
                         "Detail, Total, or Subtotal.")
    return False, "detail"


def _classify(
    line_item: str, row: dict[str, object], config: AnalysisConfig
) -> tuple[LineType, str]:
    if line_item in config.type_map:
        return config.type_map[line_item], "type_map"

    type_keys = [key for key in _TYPE_KEYS if key in row]
    if len(type_keys) > 1:
        raise ValueError(f"{line_item}: multiple classification aliases: {', '.join(type_keys)}.")
    type_field = first_present(row, _TYPE_KEYS)
    if type_field:
        explicit = explicit_line_type(type_field[1])
        if explicit:
            return explicit, "explicit_type"
        if type_field[1] is not None and str(type_field[1]).strip():
            return LineType.UNCLASSIFIED, "unrecognized_type"

    return infer_line_type(line_item)


def _percent_variance(
    budget: Decimal, actual: Decimal, basis: ComparisonBasis
) -> tuple[Decimal | None, str | None]:
    if budget != 0:
        return ratio(actual - budget, abs(budget)), None
    if actual == 0:
        return Decimal("0"), None
    return None, zero_comparison_label(basis)


def _is_material(budget: Decimal, variance: Decimal, config: AnalysisConfig) -> bool:
    if abs(variance) > config.dollar_threshold:
        return True
    if budget == 0:
        return False
    variance_units, variance_scale = variance.as_integer_ratio()
    budget_units, budget_scale = budget.as_integer_ratio()
    threshold_units, threshold_scale = config.percent_threshold.as_integer_ratio()
    return (abs(variance_units) * budget_scale * threshold_scale
            > abs(budget_units) * threshold_units * variance_scale)


def _status(line_type: LineType, variance: Decimal) -> Status:
    if variance == 0:
        return Status.NEUTRAL
    if line_type == LineType.EXPENSE:
        return Status.UNFAVORABLE if variance > 0 else Status.FAVORABLE
    if line_type == LineType.REVENUE:
        return Status.FAVORABLE if variance > 0 else Status.UNFAVORABLE
    return Status.UNCLASSIFIED


def _driver_evidence(
    row: dict[str, object], budget: Decimal, actual: Decimal, line_item: str, currency: str = "USD"
) -> DriverEvidence | None:
    fallback = None
    for model_name, bq, aq, br, ar, quantity_label, rate_label in _DRIVER_MODELS:
        required = (bq, aq, br, ar)
        if not all(key in row and not is_missing(row[key]) for key in required):
            continue

        tolerance = max(
            AMOUNT_TOLERANCE,
            abs(budget) * RELATIVE_DRIVER_TOLERANCE,
            abs(actual) * RELATIVE_DRIVER_TOLERANCE,
        )

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
        variance_tolerance = max(AMOUNT_TOLERANCE, abs(variance) * RELATIVE_DRIVER_TOLERANCE)
        reconciles = reconciles and (
            abs(quantity_effect + rate_effect - variance) <= variance_tolerance
        )

        residuals: list[Decimal | None] = []
        calculations: tuple[Callable[[], Decimal], ...] = (
            lambda: modeled_budget - budget,
            lambda: modeled_actual - actual,
            lambda: quantity_effect + rate_effect - variance,
        )
        for calculation in calculations:
            with localcontext():
                try:
                    residuals.append(calculation())
                except DecimalException:
                    residuals.append(None)
        failures = []
        for name, residual, allowed in zip(("budget", "actual", "components"), residuals,
                                           (tolerance, tolerance, variance_tolerance)):
            if residual is None:
                failures.append(f"{name}_residual_unavailable")
            elif abs(residual) > allowed:
                failures.append(f"{name}_outside_tolerance")

        components: tuple[tuple[str, Decimal], ...] = (
            (f"{quantity_label} effect", quantity_effect),
            (f"{rate_label} effect", rate_effect),
        )
        if reconciles and residuals[2] is not None and residuals[2] != 0:
            components += (("Unexplained residual", residuals[2].copy_negate()),)
        evidence = DriverEvidence(
            label=model_name,
            components=components,
            reconciles=reconciles,
            reconciliation=DriverReconciliation(
                modeled_budget, modeled_actual, residuals[0], residuals[1], residuals[2], tolerance,
                variance_tolerance, tuple(failures),
            ),
        )
        if reconciles:
            return evidence
        if fallback is None:
            fallback = evidence
    return fallback


def _resolve_summary_rows(rows: list[AnalyzedRow]) -> list[AnalyzedRow]:
    verifications: dict[LineType, SummaryVerification] = {}
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
        budget_residual = summary.budget - sum((r.budget for r in details), Decimal("0"))
        if abs(budget_residual) > AMOUNT_TOLERANCE:
            raise ValueError(f"Summary {summary.line_item!r} does not reconcile to "
                             f"{line_type.value} detail rows; check for missing or overlapping data.")
        actual_residual = summary.actual - sum((r.actual for r in details), Decimal("0"))
        if abs(actual_residual) > AMOUNT_TOLERANCE:
            raise ValueError(f"Summary {summary.line_item!r} does not reconcile to "
                             f"{line_type.value} detail rows; check for missing or overlapping data.")
        verifications[line_type] = SummaryVerification(
            "reconciled_and_excluded", len(details), budget_residual,
            actual_residual, AMOUNT_TOLERANCE,
        )

    output = []
    for row in rows:
        verification = None
        if row.excluded_from_aggregation:
            verification = verifications.get(row.line_type)
            if verification is None:
                verification = SummaryVerification(
                    "unclassified" if row.line_type == LineType.UNCLASSIFIED
                    else "included_standalone", 0,
                )
        output.append(replace(
            row,
            excluded_from_aggregation=(
                row.excluded_from_aggregation and row.line_type in detail_types
            ),
            summary_verification=verification,
        ))
    return output


def _aggregate(
    rows: list[AnalyzedRow], line_type: LineType, basis: ComparisonBasis
) -> Aggregate:
    included = [
        row
        for row in rows
        if row.line_type == line_type and not row.excluded_from_aggregation
    ]
    budget = sum((row.budget for row in included), Decimal("0"))
    actual = sum((row.actual for row in included), Decimal("0"))
    variance = actual - budget
    pct, label = _percent_variance(budget, actual, basis)
    return Aggregate(
        budget=budget,
        actual=actual,
        variance_dollars=variance,
        variance_percent=pct,
        percent_label=label,
        status=_status(line_type, variance),
    )


def _validate_comparison(config: AnalysisConfig) -> None:
    if not isinstance(config.comparison_basis, ComparisonBasis):
        raise ValueError("Comparison basis must be a ComparisonBasis value.")
    if config.comparison_label is not None:
        validate_text(config.comparison_label, field="comparison_label", nonblank=True)


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
        expected_percent, expected_label = _percent_variance(
            row.budget, row.actual, config.comparison_basis)
        if (row.variance_percent, row.percent_label) != (expected_percent, expected_label):
            raise _verification_failure(f"percentage mismatch for {row.line_item!r}")
        if row.status != _status(row.line_type, row.variance_dollars):
            raise _verification_failure(f"F/U status mismatch for {row.line_item!r}")
        expected_material = _is_material(row.budget, row.variance_dollars, config)
        if row.material != expected_material:
            raise _verification_failure(f"materiality mismatch for {row.line_item!r}")
        driver = row.driver_evidence
        if driver is not None and driver.reconciles:
            if not driver.components or sum((amount for _, amount in driver.components),
                                             Decimal("0")) != row.variance_dollars:
                raise _verification_failure(f"driver component reconciliation mismatch for "
                                            f"{row.line_item!r}")

    expected_order = sorted(
        (row for row in rows if row.material and not row.excluded_from_aggregation),
        key=lambda row: abs(row.variance_dollars), reverse=True,
    )
    if material_rows != expected_order:
        raise _verification_failure("material variance membership or sort order is incorrect")

    for line_type, aggregate in ((LineType.REVENUE, revenue), (LineType.EXPENSE, expenses)):
        variance = aggregate.actual - aggregate.budget
        percent, label = _percent_variance(
            aggregate.budget, aggregate.actual, config.comparison_basis)
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
def verify_result(result: AnalysisResult) -> None:
    """Recheck derived facts at each reporting boundary, including Python callers."""
    validate_currency(result.config.currency)
    validate_text(result.config.period, field="Period", nonblank=True)
    _validate_comparison(result.config)
    if not result.rows:
        raise _verification_failure("dataset contains no data rows")
    _verify_result(list(result.rows), list(result.material_rows), result.revenue,
                   result.expenses, result.config)


@financial_context()
def analyze_rows(rows: list[dict[str, object]], config: AnalysisConfig) -> AnalysisResult:
    if not isinstance(config, AnalysisConfig):
        raise ValueError("Configuration must be an AnalysisConfig instance.")
    validate_currency(config.currency)
    validate_text(config.period, field="Period", nonblank=True)
    _validate_comparison(config)
    if not isinstance(rows, list):
        raise ValueError("Rows must be a list of row objects.")
    if not rows:
        raise ValueError("Dataset contains no data rows.")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"Dataset exceeds the supported row count ({MAX_ROWS}).")
    if not isinstance(config.dollar_threshold, Decimal) or not isinstance(
        config.percent_threshold, Decimal
    ):
        raise ValueError("Materiality thresholds must be Decimal values initialized from strings.")
    if not config.dollar_threshold.is_finite() or not config.percent_threshold.is_finite():
        raise ValueError("Materiality thresholds must be finite numbers.")
    if config.dollar_threshold < 0 or config.percent_threshold < 0:
        raise ValueError("Materiality thresholds must be non-negative.")

    if not isinstance(config.type_map, dict):
        raise ValueError("Type map must be a dictionary of line-item strings to classifications.")
    validated_type_map: dict[str, LineType] = {}
    for item, value in config.type_map.items():
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Type map keys must be nonblank line-item strings.")
        validate_text(item, field="Type map key", nonblank=True)
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
    normalized_rows = [normalize_row(row) for row in rows]
    has_period_column = any("period" in row for row in normalized_rows)
    comparison_field = comparison_heading(config.comparison_basis, config.comparison_label)

    for index, row in enumerate(normalized_rows, start=2):
        if has_period_column:
            period = validate_text(row.get("period"), field=f"Row {index} Period", nonblank=True)
            if period.strip() != config.period.strip():
                raise ValueError(f"Row {index}: Period conflicts with the reporting period.")
        line_item_raw = _required_value(row, _LINE_ITEM_KEYS, "Line Item", index)
        if isinstance(line_item_raw, (bool, list, dict, tuple, set)):
            raise ValueError(f"Row {index}: Line Item must be a scalar text or numeric label.")
        line_item = "" if line_item_raw is None else str(line_item_raw).strip()
        if not line_item:
            raise ValueError(f"Row {index}: Line Item is blank.")
        validate_text(line_item, field=f"Row {index} Line Item", nonblank=True)

        if "currency" in row and not is_missing(row["currency"]):
            row_currency = row["currency"]
            if not isinstance(row_currency, str):
                raise ValueError(f"{line_item}: Currency must be a reporting currency code.")
            row_currency = validate_currency(row_currency.strip().upper())
            if row_currency != config.currency:
                raise ValueError(f"{line_item}: row currency {row_currency} conflicts with "
                                 f"reporting currency {config.currency}.")

        # Budget runs keep 'Budget'; other runs name the comparison and do not list the
        # internal budget column aliases.
        budget = parse_decimal(
            _required_value(
                row, _BUDGET_KEYS, comparison_field, index,
                list_accepted_names=config.comparison_basis is ComparisonBasis.BUDGET,
            ),
            field=comparison_field,
            line_item=line_item,
            currency=config.currency,
        )
        actual = parse_decimal(
            _required_value(row, _ACTUAL_KEYS, "Actual", index),
            field="Actual",
            line_item=line_item,
            currency=config.currency,
        )

        line_type, classification_source = _classify(line_item, row, config)
        summary_candidate, summary_source = _summary_candidate(line_item, row)
        variance = actual - budget
        pct, pct_label = _percent_variance(budget, actual, config.comparison_basis)
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
                classification_source=classification_source,
                summary_source=summary_source,
                materiality_reason=("absolute_amount" if abs(variance) > config.dollar_threshold
                                    else "absolute_percent" if material
                                    else "below_or_equal_thresholds"),
            )
        )

    analyzed = _resolve_summary_rows(analyzed)

    normalized_names: dict[str, int] = {}
    for analyzed_row in analyzed:
        key = analyzed_row.line_item.strip().casefold()
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
            "Driver fields were present but did not reconcile to "
            + comparison_heading(config.comparison_basis, config.comparison_label)
            + "/Actual for: "
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

    revenue = _aggregate(analyzed, LineType.REVENUE, config.comparison_basis)
    expenses = _aggregate(analyzed, LineType.EXPENSE, config.comparison_basis)

    _verify_result(analyzed, material_rows, revenue, expenses, config)

    return AnalysisResult(
        config=config,
        rows=tuple(analyzed),
        material_rows=tuple(material_rows),
        revenue=revenue,
        expenses=expenses,
        warnings=tuple(warnings),
    )
