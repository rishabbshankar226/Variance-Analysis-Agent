# Financial rules and review evidence

All financial calculations remain deterministic Python Decimal operations in an
isolated context: 50 significant digits, round-half-even, exponent limits -999 to
999. Recurring percentage ratios may round; materiality uses exact cross-products.

Variance amount = Actual - Budget. Variance percent divides by the signed nonzero
Budget. A zero Budget/nonzero Actual is unbudgeted with a null percentage; a
zero/zero row has zero variance. Materiality is strict absolute amount OR absolute
percentage greater than the threshold. Equality is not material. For zero Budget,
only the amount comparison applies. Sorting uses absolute amount, stably.

Positive expense variance is unfavorable; positive Revenue variance is favorable.
Inputs must follow the documented positive-cost expense convention. Signed-ledger
transformations require explicit preprocessing; amounts are never silently made
absolute. Unclassified rows remain excluded from category totals.

## Classification and summaries

Type-map entries take precedence, then a recognized explicit Type, then conservative
label inference. An unrecognized populated Type remains Unclassified. Profit
measures are not treated as additive Revenue. Audit 1.3 records the actual source
of these decisions for material rows; public API records constructed manually may
have `unavailable` decision metadata.

Explicit Row Kind Detail/Total/Subtotal overrides summary label inference.
Ambiguous labels require an explicit Row Kind. One summary per classified category
may reconcile to supplied detail rows within 0.01 for both Budget and Actual and
then be excluded. A lone category summary remains included and is not claimed
verified against details. Multiple/nested summaries remain rejected.

Audit `summary_verifications` contains derived evidence for summaries, including
excluded rows: source of the summary decision, outcome, detail count, signed
residuals (summary minus detail sum), and applied tolerance. It contains no raw
input row dictionaries. Unclassified summaries do not verify category completeness.
Completeness refers to supplied classified rows with both categories present.

## Driver evidence

Current model order is volume/price, units/price, headcount/rate, customers/rate.
Incomplete models are skipped; malformed complete-model values fail validation.
The first reconciled complete model wins. If all complete models fail, the first
remains hypothesis evidence; no supported causal claim is made.

Budget/Actual reconciliation tolerance is
`max(0.01, abs(Budget)*0.000001, abs(Actual)*0.000001)`.
Component reconciliation tolerance is
`max(0.01, abs(Actual-Budget)*0.000001)`.
Quantity effect is `(Actual Quantity-Budget Quantity)*Budget Rate`;
rate effect is `(Actual Rate-Budget Rate)*Actual Quantity`.

Audit 1.3 exposes modeled balances, signed modeled-minus-observed residuals,
component-sum-minus-variance residual, applied tolerances, and explicit failure
reasons. Additional diagnostics do not change the original financial checks or
their short-circuit behavior. A hypothetical residual unrepresentable under the
same Decimal policy is null with a residual-unavailable reason; it is never rounded
silently or used to upgrade evidence to supported.

`materiality_reason` records the first successful comparison (amount first, then
percentage). It does not claim that only one comparison could have succeeded.
Report amounts/percentages are rounded for display; thresholds use exact values.
