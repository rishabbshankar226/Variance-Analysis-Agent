# Financial rules and review evidence

All financial calculations remain deterministic Python Decimal operations in an
isolated context: 50 significant digits, round-half-even, exponent limits -999 to
999. Recurring percentage ratios may round; materiality uses exact cross-products.
Numeric inputs are checked against this context before analysis. Context traps
include DivisionByZero, InvalidOperation, Overflow, Underflow, and Inexact;
recurring ratios alone permit Inexact. Python callers must initialize Decimal
thresholds from strings. Exact subnormals are accepted within the context's
representable range; absent drivers do not perform unused tolerance arithmetic.

Variance amount = Actual - comparison amount. "Budget" below is the comparison amount: Budget by default, or the Forecast or Prior Period amount when that basis is selected. Favorability, materiality, and arithmetic are identical for all three bases.

Variance percent divides by the absolute nonzero
Budget. A zero Budget/nonzero Actual is unbudgeted with a null percentage; a
zero/zero row has zero variance. The zero-comparison label depends on the basis: `N/A (Unbudgeted)` for Budget, `N/A (Not in forecast)` for Forecast, and `N/A (New this period)` for Prior Period. Materiality is strict absolute amount OR absolute
percentage greater than the threshold. Equality is not material. For zero Budget,
only the amount comparison applies. Sorting uses absolute amount, stably.

Positive expense variance is unfavorable; positive Revenue variance is favorable.
Inputs must follow the documented positive-cost expense convention. Signed-ledger
transformations require explicit preprocessing; amounts are never silently made
absolute. Unclassified rows remain excluded from category totals.
The configured period must be nonblank text. If a Period column is present, every
row must supply that reporting period; missing or conflicting periods fail.

## Classification and summaries

Type-map entries take precedence, then a recognized explicit Type, then conservative
label inference. Type maps and the Type column accept the same words: Revenue, Income,
Sales, Rev; Expense, Expenses, Cost, Costs, Opex, COGS; and in a type map also
Unclassified (an explicit decision to leave a line out of the totals).

Label inference is deliberately narrow. A cost noun (tax, commission, salary/wages,
compensation, provision, returns, bonus, discount, allowance, rebate, refund) makes a
line an Expense even when a revenue word only qualifies it: `Sales Commissions`,
`Income Taxes` and `Sales Returns and Allowances` are expenses, so an overrun is
unfavorable and stays out of Total Revenue. Revenue stated net of such a cost
(`Revenue, net of returns`) stays Revenue. Profit measures and subtotals are never
additive and stay Unclassified: net, operating and gross income/profit/earnings/loss/
margin, income or profit before/after anything, pre-tax income, income from operations,
comprehensive income, EBIT, EBITDA, NOPAT. Labels with both a revenue and an expense
word (`Sales and Marketing`) remain Unclassified. Assisted intake's signed-ledger
detection uses the same classifier. An unrecognized populated Type remains Unclassified. Profit
measures are not treated as additive Revenue. Audit 1.3 records the actual source
of these decisions for material rows; public API records constructed manually may
have `unavailable` decision metadata.

Explicit Row Kind Detail/Total/Subtotal overrides summary label inference. A label that
names a whole category is recognised as a summary: `Total Revenue(s)`, `Total Sales`,
`Total Operating Revenue`, `Total Net Sales`, `Total Expenses`, `Total Operating Expenses`,
`Total Costs and Expenses`, `Total Opex`, `Total COGS`, `Total Income`, and the reversed
`Revenues Total`. `Total Operating Income` and other `Total ...` labels stay ambiguous and
need a Row Kind. A recognised summary still has to reconcile to its details.
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
For an accepted nonzero residual, an Unexplained residual component equals the
observed variance minus the two modeled effects. The reported component tuple
then sums exactly to observed variance. The diagnostic component_residual still
describes the two modeled effects before this adjustment; it is not concealed or
assigned to a quantity/rate cause. Reports request reconciliation of that residual.

`materiality_reason` records the first successful comparison (amount first, then
percentage). It does not claim that only one comparison could have succeeded.
Report amounts share at least two decimal places and retain additional fractional
places whenever needed for exact detail/total and driver reconciliation. A report
precision note explains additional places. Quantization uses ROUND_HALF_EVEN only
at this reporting boundary; no pennies are allocated to accounts. Percentages use
exact integer ratios and one half-even rounding to tenths of a percent, avoiding a
second rounding of the 50-digit API ratio. The threshold line preserves
every significant fractional digit of the configured cutoffs, including fractional
cents and small percentages; materiality comparisons use those exact values.

Report labels and periods escape source Markdown/HTML characters, including
ampersands. Literal entity text such as `&copy;` remains source text when rendered;
audit records retain the original labels and periods.
Terminal and bidirectional formatting controls are shown as visible escapes in
reports and CLI errors. Report and audit builders independently reverify derived
financial identities before serializing results from Python callers.

## Opted-in measure kinds

Currency rules above are unchanged. Per Share and Count use Actual minus the
supplied comparison and percentage variance against its absolute nonzero value.
Per Share uses its per-share absolute cutoff OR the percentage cutoff; Count
uses its count absolute cutoff OR the percentage cutoff. At zero comparison,
only the absolute test applies. Their absolute cutoffs are required even when a
particular row would pass the percentage test.

Percent inputs represent percentage points. Basis-point variance is exactly
`(Actual - comparison) * 100`. It has no relative percentage variance; display
`N/A (rate)`. Only the required bps cutoff applies. Every cutoff test is strict
`>`; equality is not material. Higher/Lower controls the status of noncurrency
rows; absent Per Share direction defaults visibly to Higher. Missing Percent or
Count direction needs a user choice. Revenue/Expense Type controls Currency;
a contradictory Better is an error. Scored unclassified Currency rows remain
non-additive. Noncurrency rows do not affect Currency completeness or net impact.

Units are displayed as currency/share, bps, or units, following the existing
ASCII minus/no-leading-plus conventions. Amount arithmetic remains exact in the
financial context. Money scaling and subtotal inference never apply to a declared
rate, per-share value, or count. A standalone count is in its supplied units;
there is no inference that a caption about money also scales counts.

## Supplied earnings bases (unreleased)

Consensus, Estimate, and Guidance reuse single-basis variance and materiality.
Consensus displays Beat for a material favorable row, Miss for material
unfavorable, and In line for a scored nonmaterial/neutral row. Unscored rows get
none of those three outcomes. Status itself remains F/U/Neutral/Unclassified.
Blank consensus has no status; supplied zero consensus remains real, its ratio
is null, and only the absolute materiality test applies. Estimate, Guidance, and
Prior Period never acquire consensus outcome vocabulary.

Guidance midpoint is `(low + high) / 2` in the financial context, verified at the
engine and output boundaries. Low > High is an error. Actual equal to either
end is Within range; strict crossings are Below range or Above range.
Estimate against Consensus describes the difference between two supplied
numbers, divided by absolute nonzero Consensus, or multiplied by 100 for a
rate difference in bps. It does not generate an estimate or investment advice.

### Segment scope

Reconcile at most one supplied Currency summary per category within each segment, using the existing inclusive 0.01 reconciliation tolerance. Never reconcile across segments or synthesize consolidated totals. Unsegmented consolidated rows remain a separate bucket. Duplicate names across segments are distinct; duplicates within the same segment still warn. Labels containing slashes do not imply hierarchy.
