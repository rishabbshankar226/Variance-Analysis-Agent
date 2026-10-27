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

### Multiple (unreleased, opt-in)

A Multiple row (`3.25x`, or `3.25` with `Measure: Multiple`) uses Actual minus the
supplied comparison, shown in turns (`0.75x`), with percentage variance against
the comparison's absolute nonzero value. Its absolute cutoff is the required
`--multiple-threshold`, in turns, OR the percentage cutoff; strict `>`. A Better
direction is required, as for Percent and Count. An `x` on any other measure is an
unreadable amount. A computed ratio is shown to two places; the audit keeps the
exact value. Any further measure kind is a STOP-ASK.

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

### Descriptive surprise statistics (opt-in)

Standardized surprise uses Actual minus supplied Consensus divided by the sample
standard deviation of the most recent prior surprises for that entity, metric
and optional segment. Percent metric history is in bps, and its numerator is the
bps variance. Current and future periods are excluded. The default maximum
window is 8; a window below 4 is refused. With fewer than 4 prior surprises or
zero historical deviation, the statistic is null with a stated reason.

The sample variance is algebraically demeaned:
`(n * sum(x*x) - sum(x)*sum(x)) / (n * (n-1))`. Sums and cross-products use the
existing exact 50-significant-digit financial context and fail rather than
silently losing amount precision. The variance ratio may repeat and uses the
existing permitted 50-digit half-even ratio rounding. `Decimal.sqrt` is the
inexact square-root step, evaluated in that context with only Inexact locally
disabled. The final standardized ratio uses the same ratio rounding. No binary
float enters these calculations.

Dispersion surprise divides the same numerator by supplied estimate standard
deviation. Percent dispersion is supplied in percentage points and converted to
bps before division. Absent or zero dispersion produces null with a reason.
These are descriptive statistics of supplied numbers; they make no predictions.

## Limit, benchmark and target bases (unreleased, opt-in)

Selected with `--assisted --compare-to limit|benchmark|target`, one per run. Each
row declares what its comparison means; nothing is defaulted, and a missing
declaration refuses the row by name. These rows are never Revenue or Expense, and
the run has no revenue, expense or net totals (the audit records `totals` as null).
The words describe the supplied comparison and are never advice.

**Limit.** Each row declares `Limit Kind` Max or Min, and may declare a `Buffer`
(zero or more, in the row's unit). Breach is strictly beyond the limit: Actual >
limit for Max, Actual < limit for Min. A row exactly at its limit is At limit
(the owner's choice at STOP 2; it was Within). Headroom is limit minus Actual for
Max and Actual minus limit for Min, in the row's unit, also shown as a share of
the limit's absolute value. Near is 0 < headroom <= buffer, and only with a
declared buffer. Utilization is Actual divided by limit, for both kinds, and NM
for a zero limit (as is headroom's share). Order: Breach, At limit, Near, Within;
within each, headroom ascending. Status is Neutral.

Boundary cases: Actual = limit is At limit; a step past a Max (or below a Min) is
Breach; headroom equal to the buffer is Near, and a step more is Within; a zero
limit has NM utilization.

**Benchmark.** Each row declares `Better` Higher or Lower. Active difference is
Actual minus benchmark, in basis points for Percent rows. In line means |active|
<= a declared `Tolerance` (in the row's unit, percentage points for rates), or
exact equality without one. Otherwise the row is Higher than benchmark or Lower
than benchmark (the words describe the figures, never whether that is good). F or
U follows Better and the difference's sign; In line is Neutral.

Boundary cases: |active| equal to the tolerance is In line; a step more is Higher
or Lower than benchmark; without a tolerance, only zero is In line.

**Target.** Difference is Actual minus target, in basis points for Percent rows.
On target means |difference| <= a declared `Tolerance`, or exact equality without
one. Otherwise the row is Over or Under. A target is neutral: no F or U, and a
declared Better refuses the row.

## Derived metrics (unreleased, opt-in)

`--metrics PATH` declares each metric as a closed JSON structure: a `name`, a
`measure` (Currency or Multiple), an optional `better`, and signed lists of
`numerator` and, for a ratio, `denominator` terms. A term names one printed line
by XBRL `concept` or exact `label`, with its `statement` (income, balance_sheet,
cash_flow), its `period` (instant, fy, ytd, ltm) and a `sign` of 1 or -1. Unknown
keys refuse.

Each statement a term reads is first read and checked as on its own (footing and
identities). The value used is the term's stored XBRL value, whose sign the taxonomy fixes, so one metrics file means the same on every filing however a line is printed; the printed figure is cited beside it. `instant` is the balance
sheet's latest column; `fy` the 10-K's fiscal year; `ytd` the 10-Q's year to
date; `ltm` is FY + YTD - prior YTD by key, with `--ltm-from` and the same
continuity check as an LTM statement. A single cash flow line (D&A) is a flow; a
cash balance refuses as an LTM term.

The value is the sum of sign x term, divided by the denominator's sum for a ratio,
in exact Decimal (a repeating ratio rounds once, at the financial context's
precision). A missing term leaves that metric out by name. A zero or negative
denominator is NM with its reason. No expression is evaluated. The metrics are
compared with `--compare-file` (a case or a covenant schedule), joined by exact
metric name, and the schedule's declarations (Limit Kind, Buffer, Measure, Better)
apply. The report shows each value beside its formula. Audit 1.9 records every
term with its document, statement, column and context, and LTM terms with their
three components.
