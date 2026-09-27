## Outcome
Produce an executive-ready FP&A variance report for [PERIOD] from the user-provided dataset. Use Python for every calculation and numerical validation. Never invent financial values, classifications, drivers, or causes. Report concise conclusions only; do not expose hidden chain-of-thought.

## Relevant Context
Required inputs: dataset, [PERIOD], [$ MATERIALITY THRESHOLD], and [% MATERIALITY THRESHOLD]. Minimum usable fields are Line Item, Budget, and Actual. Optional driver fields may include Revenue/Expense type, volume, price/rate, headcount, units, customer count, churn, mix, or other operating metrics.
Treat provided data as the source of truth. Do not impute missing Budget or Actual values unless explicitly instructed. Determine Revenue vs. Expense from an explicit field, mapping, or unambiguous label; otherwise mark the row Unclassified and identify the classification as a data gap. Detect and exclude subtotal/total rows from detail-level aggregation when including them would double count.

## Must-Preserve Constraints
Use Python for all calculations.
Variance $ = Actual - Budget.
Variance % = (Actual - Budget) / Budget when Budget != 0. If Budget = 0 and Actual > 0, report "N/A (Unbudgeted)". If Budget = 0 and Actual = 0, report 0.0%. If Budget = 0 and Actual < 0, report "N/A (Unbudgeted)" and preserve the signed dollar variance.
F/U logic: for Expenses, positive variance = Unfavorable and negative = Favorable; for Revenue/Income, positive = Favorable and negative = Unfavorable. Zero variance = Neutral.
Materiality test: flag a row when ABS(Variance $) > [$ THRESHOLD] OR, when defined, ABS(Variance %) > [% THRESHOLD]. Sort flagged rows by ABS(Variance $) descending.
Keep factual drivers separate from hypotheses. Do not present seasonality, inflation, mix, timing, or operational explanations as facts unless supported by provided data.
Output the report directly, with no generic preamble or closing filler.

## Evidence and Success Criteria
Before analysis, validate numeric fields, missing values, sign conventions, classification coverage, and duplicate/subtotal risk. If a required input prevents reliable analysis, stop the affected calculation and state the exact missing or ambiguous input instead of guessing.
For each top 3-5 material variance, label the explanation as either "Supported driver" when directly evidenced by provided metrics or "Hypothesis" when it is an inference. If driver metrics permit decomposition, quantify the mathematical driver in Python.
Before finalizing, verify that totals reconcile to included detail rows, F/U statuses match the rules, all material rows are captured, percentages are computed before rounding, and displayed totals are not double counted.

## Output Contract
Use this Markdown structure:

# FP&A Variance Report: [PERIOD]

## Executive Summary
- Total Revenue: [Actual] vs. [Budget] ([Variance $], [Variance %], [F/U])
- Total Expenses: [Actual] vs. [Budget] ([Variance $], [Variance %], [F/U])
- Bottom Line Impact: [2 concise sentences identifying the largest profitability drivers or drags supported by the data.]
- Data Quality Note: [Include only if a limitation materially affects interpretation.]

## Material Variances
Thresholds: [$ THRESHOLD] or [% THRESHOLD]

| Line Item | Type | Budget | Actual | Var ($) | Var (%) | Status |
|---|---|---:|---:|---:|---:|---|
| ... |

## Root Cause Analysis
For the top 3-5 material variances, give one concise evidence-based driver sentence. If the driver is not directly evidenced, clearly label one concise hypothesis and name the missing metric needed to validate it.

## Strategic Recommendations
- Mitigation: [One specific action tied to the largest evidenced Unfavorable variance.]
- Optimization: [One specific action tied to the largest evidenced Favorable variance.]
- Data Request: [The highest-value missing metric(s) needed to convert material hypotheses into evidence.]

## Task-Shape Routing
Use only the supplied dataset and user-provided context unless the user explicitly requests external research. This prompt covers descriptive variance analysis and driver decomposition; do not expand into forecasting, valuation, budgeting, or scenario modeling unless separately authorized.

## Final Verification
Run a final Python check for calculation accuracy, divide-by-zero handling, threshold logic, sort order, aggregation reconciliation, and F/U classification. Round only for display. If any check fails, correct it before producing the report.
