"""Financial domain knowledge base for the Variance Analysis Agent.

Provides rigorous, authoritative explanations of corporate FP&A concepts,
budget-vs-actual variance principles, materiality criteria, causal driver
decompositions, and audit compliance standards.
"""

from __future__ import annotations


def explain_variance_analysis() -> str:
    return (
        "**What is Variance Analysis?**\n\n"
        "Variance analysis is a fundamental FP&A (Financial Planning & Analysis) practice that "
        "compares **Actual financial performance** against a baseline (**Budget** or **Forecast**) "
        "over a specified reporting period.\n\n"
        "**Core Objectives:**\n"
        "• **Accountability:** Track whether revenue targets were achieved and operating expenses remained within approved limits.\n"
        "• **Management by Exception:** Screen out routine fluctuations to focus executive attention exclusively on **material** discrepancies.\n"
        "• **Causal Diagnosis:** Identify the underlying operational drivers (e.g., pricing, sales volume, headcount, vendor rates) behind financial deviations.\n"
        "• **Corrective Action:** Provide finance leaders with actionable recommendations for cost mitigation or growth optimization."
    )


def explain_favorable_unfavorable() -> str:
    return (
        "**Favorable (F) vs. Unfavorable (U) Variance**\n\n"
        "In corporate finance, variance direction is determined by its impact on **Operating Income**, "
        "not simply whether the math is positive or negative:\n\n"
        "**1. Revenue Lines:**\n"
        "• **Actual > Budget (Variance > 0):** **Favorable (F)** — generated more revenue than planned.\n"
        "• **Actual < Budget (Variance < 0):** **Unfavorable (U)** — fell short of the revenue target.\n\n"
        "**2. Expense Lines:**\n"
        "• **Actual > Budget (Variance > 0):** **Unfavorable (U)** — overspent relative to budget.\n"
        "• **Actual < Budget (Variance < 0):** **Favorable (F)** — underspent, preserving cash/margin.\n\n"
        "**Key Rule:** A *positive* expense variance is *unfavorable* because spending exceeded the budget allocation."
    )


def explain_materiality() -> str:
    return (
        "**Materiality Thresholds: Dollar Amount or Percent**\n\n"
        "Materiality determines which variances require executive investigation and operational explanation. "
        "This agent applies **two tests, and either one is enough**:\n\n"
        "A line item is flagged as **Material** if:\n"
        "• `|Variance Amount| > Dollar Threshold` **or**\n"
        "• `|Variance %| > Percent Threshold`, where the percent is taken against the absolute comparison amount\n\n"
        "**Why Two Tests:**\n"
        "• **Large moves on large lines:** the dollar test catches a $50,000 swing even when it is a small percentage of a big line.\n"
        "• **Large moves on small lines:** the percent test catches a line that doubled even when the dollar amount is small. Raise the percent threshold if small lines are creating noise.\n"
        "• **Strict Comparison:** Equality is not material (`>`, not `>=`; exactly meeting a threshold is excluded).\n"
        "• **Zero-Budget Handling:** If the comparison amount is $0.00, percentage variance is undefined, so only the dollar test applies."
    )


def explain_net_impact() -> str:
    return (
        "**Net Operating Impact**\n\n"
        "Net Operating Impact measures how budget deviations directly affect the company's bottom-line "
        "operating profit (revenue less all listed expenses):\n\n"
        "$$\\text{Net Operating Impact} = \\text{Total Revenue Variance} - \\text{Total Expense Variance}$$\n\n"
        "**Interpretation:**\n"
        "• **Positive Net Impact:** The company generated more net operating income than budgeted (revenue overperformance exceeded expense overruns, or cost savings offset revenue shortfalls).\n"
        "• **Negative Net Impact:** Net operating income fell below budget expectations.\n\n"
        "*Note: Unclassified line items are excluded from net impact until classified as Revenue or Expense, ensuring sign-reversal integrity.*"
    )


def explain_drivers() -> str:
    return (
        "**Causal Driver Decomposition**\n\n"
        "Variance amount (`Actual - Budget`) only tells *how much* an account moved. "
        "Driver decomposition reveals *why* it moved by isolating structural operating factors:\n\n"
        "**1. Revenue Decomposition (Price vs. Volume):**\n"
        "• **Volume Effect:** `(Actual Quantity - Budget Quantity) × Budget Rate`\n"
        "• **Rate/Price Effect:** `(Actual Rate - Budget Rate) × Actual Quantity`\n\n"
        "**2. Expense Decomposition (Rate vs. Volume/Headcount):**\n"
        "• **Volume/Headcount Effect:** Measures variance from team size, unit volume, or service hours.\n"
        "• **Rate Effect:** Measures variance from average compensation, hourly billing rate, or unit cost.\n\n"
        "**Evidence Standards in this Agent:**\n"
        "• **Supported Driver:** The component effects sum exactly to observed variance within mathematical tolerance.\n"
        "• **Hypothesis (Unsupported):** Driver data was provided but components do not reconcile to the total variance.\n"
        "• **Unexplained Residual:** Any discrepancy between observed variance and modeled drivers is explicitly isolated and flagged for audit review."
    )


def explain_unclassified() -> str:
    return (
        "**Why Line Item Classification Matters**\n\n"
        "Every financial line item must be classified as either **Revenue** or **Expense** because sign conventions "
        "are inverted:\n\n"
        "• If an unclassified item exceeds budget by $50,000, we cannot determine whether that is **Favorable** "
        "(+$50k Revenue) or **Unfavorable** (-$50k Expense overspend).\n"
        "• To protect financial statement integrity, unclassified rows are excluded from category totals and net operating impact until explicitly resolved.\n"
        "• You can classify items interactively in chat or supply a type mapping JSON file."
    )


def explain_audit_trail() -> str:
    return (
        "**Audit Trail & Verification Standards**\n\n"
        "This agent produces deterministic, reproducible outputs designed to support internal review: "
        "every number can be traced back to the file you supplied and recomputed.\n\n"
        "• **Zero Non-Determinism:** All math uses Python's Decimal context with 50 digits of precision and round-half-even ties.\n"
        "• **Source Fingerprints:** Source data bytes and type map files are fingerprinted with SHA-256 hashes.\n"
        "• **Recorded Context:** The generated audit JSON records exact source hashes, schema version, configuration parameters, and classification decision origins.\n"
        "• **Zero Hallucination:** Every number in chat and reports is computed directly from validated input rows; no language model calculates numbers.\n\n"
        "The audit file is evidence of how a result was produced. It is not a certification or a "
        "statement of regulatory compliance."
    )


def explain_mitigation_actions() -> str:
    return (
        "**Following up a material variance**\n\n"
        "This tool reports what moved and by how much; what to do about it is the reviewer's decision. "
        "A variance review usually asks these questions:\n\n"
        "**For an expense over budget:**\n"
        "1. **Rate or volume:** did the price per unit change, or the number of units (headcount, hours, orders)? "
        "`why [line]` shows the split when the file has driver columns.\n"
        "2. **Timing or lasting:** is it spending brought forward, or a new run rate? `run rate` shows the pace.\n"
        "3. **Committed or discretionary:** is the spending already contracted, or could it still change?\n\n"
        "**For revenue above budget:**\n"
        "1. **One-time or recurring:** an early contract close, or ongoing demand?\n"
        "2. **Price or volume:** more units sold, or a higher price per unit?"
    )


def explain_supported_formats() -> str:
    return (
        "**Supported Input File Formats & Schema**\n\n"
        "The agent accepts:\n"
        "• **CSV** (`.csv`) — comma-separated values, UTF-8\n"
        "• **JSON** (`.json`) — array of row objects\n"
        "• **Excel** (`.xlsx`, `.xlsm`) — modern OpenXML spreadsheets\n"
        "• **PDF** (`.pdf`) — 10-K and 10-Q filings: the income statement is read from the "
        "filing's tables and compared with the prior period (scanned PDFs can't be read)\n\n"
        "**Required Columns/Fields:**\n"
        "• `Line Item` (or `account`, `item`, `description`): Name of the line item\n"
        "• `Budget`: Baseline planned amount (or `Forecast` / the prior period when you compare to those)\n"
        "• `Actual`: Realized period amount\n\n"
        "**Sign convention:** enter costs as positive numbers (an expense of $500 is `500`, and spending "
        "above the comparison amount is unfavorable). A ledger that shows costs as negatives is detected "
        "and shown to you for confirmation before anything is flipped.\n\n"
        "**Optional Columns:**\n"
        "• `Line Type`: `Revenue` or `Expense`\n"
        "• `Period`: Reporting period identifier (e.g., `Q3 2026`)\n"
        "• Driver decomposition fields: `Budget Quantity`, `Actual Quantity`, `Budget Rate`, `Actual Rate`"
    )


def explain_budget_vs_forecast() -> str:
    return (
        "**Budget vs. Forecast vs. Prior Period (Variance Baselines)**\n\n"
        "Corporate FP&A relies on three distinct reference baselines, each serving a unique governance purpose:\n\n"
        "**1. Budget (AOP - Annual Operating Plan):**\n"
        "• **Nature:** A fixed, board-approved financial contract finalized before the fiscal year commences.\n"
        "• **Purpose:** Evaluates executive performance, sets departmental spending ceilings, and determines compensation milestones.\n"
        "• **Variance Meaning:** Did the company execute its committed operating plan?\n\n"
        "**2. Forecast (Latest Estimate / LE / Rolling Forecast):**\n"
        "• **Nature:** A dynamic projection updated monthly or quarterly reflecting current market realities and actual performance.\n"
        "• **Purpose:** Manages liquidity, operating pace, and forward-looking strategic decisions.\n"
        "• **Variance Meaning:** Is operating velocity accelerating or decelerating compared to recent trends?\n\n"
        "**3. Prior Period (YoY / MoM Historicals):**\n"
        "• **Nature:** Historical actuals from the comparable prior timeframe.\n"
        "• **Purpose:** Measures organic growth, margin expansion, and seasonal trends.\n\n"
        "**Key Rule:** Budget variance holds teams accountable to commitments; Forecast variance manages real-time trajectory."
    )


def explain_timing_vs_permanent() -> str:
    return (
        "**Timing vs. Permanent Variances**\n\n"
        "When explaining material deviations, financial analysts must distinguish between timing shifts and structural shifts:\n\n"
        "**1. Timing Variances (Reversible / Non-Structural):**\n"
        "• Caused by differences between the period when activity was budgeted vs. when accounting recognition occurs.\n"
        "• **Common Examples:**\n"
        "  - Contract signature delayed from September to October (revenue shift).\n"
        "  - Vendor invoice received earlier or later than anticipated.\n"
        "  - Prepayment amortizations and milestone billing lags.\n"
        "• **Action Required:** Monitor cash flow; does **not** require structural headcount cuts or budget re-allocations.\n\n"
        "**2. Permanent Variances (Structural / Run-Rate):**\n"
        "• Caused by fundamental operational shifts that alter future performance.\n"
        "• **Common Examples:**\n"
        "  - Product price increases or customer contract churn.\n"
        "  - Permanent salary adjustments or new software licensing tiers.\n"
        "• **Action Required:** Immediately re-baseline subsequent forecast quarters and initiate cost mitigation or revenue acceleration."
    )


def explain_operating_leverage() -> str:
    return (
        "**Operating Leverage & Fixed vs. Variable Costs**\n\n"
        "Operating leverage dictates how deviations in revenue flow through to bottom-line profitability (operating margin):\n\n"
        "**1. Cost Classification:**\n"
        "• **Fixed Costs:** Overhead that does not fluctuate with volume (e.g., office facilities, core software licenses, executive salaries).\n"
        "• **Variable Costs:** Expenses that move in direct proportion to volume (e.g., payment processing fees, cloud compute usage, raw materials).\n\n"
        "**2. Impact on Variance Analysis:**\n"
        "• **High Operating Leverage:** High proportion of fixed costs. A modest positive revenue variance generates an outsized surge in operating income (margin expansion), while a slight revenue miss causes severe margin compression.\n"
        "• **Drop-Through / Flow-Through:** The percentage of each revenue variance dollar that translates into net operating income. High drop-through indicates efficient operating leverage."
    )


def explain_kpis() -> str:
    return (
        "**Essential FP&A Variance Metrics & KPIs**\n\n"
        "Professional finance teams evaluate variance health through five core quantitative metrics:\n\n"
        "• **1. Revenue Target Achievement Rate:** `(Actual Revenue / Budget Revenue) × 100%` (Target: ≥ 100%).\n"
        "• **2. Expense Budget Utilization (Burn Rate):** `(Actual Expense / Budget Expense) × 100%` (Target: ≤ 100%).\n"
        "• **3. Net Operating Impact:** `Revenue Variance - Expense Variance` (Direct contribution to operating profit).\n"
        "• **4. Variance Concentration (Pareto Ratio):** The share of total portfolio variance driven by the top 3 line items (measures volatility concentration).\n"
        "• **5. Driver Reconciliation Rate:** Percentage of material variances explained by verified causal drivers (price, volume, rate)."
    )


def explain_budgeting_methods() -> str:
    return (
        "**Budgeting Methodologies & Variance Baselines**\n\n"
        "How a budget is constructed fundamentally impacts how its variances must be interpreted:\n\n"
        "**1. Incremental Budgeting:**\n"
        "• Takes prior year actuals as baseline and adjusts by a growth percentage.\n"
        "• **Risk:** Carries forward historical inefficiencies and spending bloat.\n"
        "• **Variance Focus:** Deviations primarily highlight unexpected growth or inflation.\n\n"
        "**2. Zero-Based Budgeting (ZBB):**\n"
        "• Every line item starts at $0.00 each cycle and must be justified from operational scratch.\n"
        "• **Advantage:** Eliminates obsolete spend; tightest cost discipline.\n"
        "• **Variance Focus:** Any expense variance directly indicates operational non-compliance with approved activities."
    )


def explain_ebitda_margin() -> str:
    return (
        "**Operating Profit & Margin Impact in Variance Analysis**\n\n"
        "In corporate financial reporting, profit metrics (Gross Margin, Operating Income, EBITDA) "
        "represent **calculated subtotals**, not independent additive accounts:\n\n"
        "**1. The Bottom-Line Formula:**\n"
        "$$\\text{Net Operating Impact} = \\text{Total Revenue Variance} - \\text{Total Expense Variance}$$\n"
        "• A **favorable revenue variance** directly increases operating profit.\n"
        "• An **unfavorable expense variance (overspend)** directly decreases operating profit.\n\n"
        "**What this tool calls operating profit:** total revenue minus all listed expense lines, "
        "and **operating margin** is that profit divided by revenue. The tool does not separate "
        "depreciation, amortization, interest or tax, so its operating profit is not EBITDA unless "
        "your expense lines already leave those out.\n\n"
        "**2. Operating Drop-Through / Flow-Through Ratio:**\n"
        "$$\\text{Flow-Through Rate} = \\frac{\\Delta \\text{Operating Profit}}{\\Delta \\text{Revenue Variance}} \\times 100\\%$$\n"
        "• **High Flow-Through (> 70%):** Operating leverage is working effectively; revenue expansion is not being consumed by incremental variable overhead.\n"
        "• **Low Flow-Through (< 30%):** Indicates cost bloat or escalating variable costs diluting incremental revenue gains.\n\n"
        "**Integrity Standard:** Subtotal rows (Gross Margin, Operating Income, Total Revenue) are marked `excluded_from_aggregation` "
        "in this engine to prevent double-counting line items."
    )


def explain_variance_bridge() -> str:
    return (
        "**P&L Variance Bridge (Waterfall Analysis) Principles**\n\n"
        "A **Variance Bridge** (or Waterfall Chart) reconciles how an organization moved from its **Budgeted Operating Income** "
        "to its **Actual Operating Income** across an operating period:\n\n"
        "**1. Step-by-Step Mathematical Walk:**\n"
        "$$\\text{Actual Operating Income} = \\text{Budget Operating Income} + \\Delta \\text{Revenue} - \\Delta \\text{Expenses}$$\n\n"
        "• **Baseline:** Starts at Budget Net Operating Income (`Budget Revenue - Budget Expenses`).\n"
        "• **Positive Drivers (Green):** Revenue beats and expense underspend (cost savings) add directly to operating profit.\n"
        "• **Negative Drivers (Red):** Revenue shortfalls and expense overruns subtract from operating profit.\n"
        "• **Final Total:** Concludes at realized Actual Net Operating Income (`Actual Revenue - Actual Expenses`).\n\n"
        "**2. Why Finance Teams Require Bridge Analysis:**\n"
        "• **Isolation of Accountability:** Separates commercial topline performance (sales volume/pricing) from operational cost control (departmental opex).\n"
        "• **Executive Clarity:** Answers the board-level question: *'Why did we miss/beat our profit target by $X?'* in a single structured view.\n\n"
        "Ask `waterfall` or `bridge` anytime to compute this exact reconciliation for your loaded financial data."
    )


def explain_comparison_types() -> str:
    return (
        "**What You Can Compare Actuals Against**\n\n"
        "Each analysis compares Actual against one basis:\n\n"
        "• **Budget:** The approved plan for the period (the default).\n"
        "• **Forecast:** The latest estimate, re-projected during the year.\n"
        "• **Prior period:** Actual results from an earlier period, such as last year.\n\n"
        "I detect the basis from your column headers. When a file has more than one, I ask which to use. "
        "Switch at any time with `compare to budget`, `compare to forecast` or `compare to prior period`. "
        "On the command line, pass `--compare-to budget`, `--compare-to forecast` or `--compare-to prior-period`."
    )


def explain_consensus() -> str:
    return ("Consensus is the estimate summary supplied in your file, such as a mean of analysts' estimates. "
            "I compare Actual with that supplied figure and make no estimates. "
            "Keep GAAP and adjusted measures consistent yourself; I never relabel one as the other.")


def explain_surprise() -> str:
    return ("An earnings surprise is Actual minus supplied Consensus. Surprise percent divides that difference by "
            "the absolute Consensus, including when Consensus is a loss. A zero or missing Consensus has no ratio. "
            "I compare supplied numbers and make no estimates.")


def explain_beat_miss() -> str:
    return ("Against supplied Consensus, a material favorable result is a Beat and a material unfavorable result is a Miss. "
            "A scored result below or equal to your cutoffs is In line. An unclassified or missing comparison gets no such label. "
            "Direction comes from Type or your Better choice. I compare supplied numbers and make no estimates.")


def explain_bps() -> str:
    return ("One basis point is 0.01 percentage points. A supplied margin moving from 41.2% to 40.6% changes by -60 bps. "
            "Rate materiality compares absolute bps with your cutoff, using strictly greater than. "
            "I compare supplied numbers and make no estimates.")


def explain_guidance_ranges() -> str:
    return ("A supplied guidance range is compared at its exact midpoint. Actual at either endpoint is Within range; "
            "below the low is Below range and above the high is Above range. These positions do not imply a forecast. "
            "I compare supplied numbers and make no estimates.")


def explain_standardized_surprise() -> str:
    return ("Standardized surprise divides the current supplied Actual-minus-Consensus surprise by the sample standard deviation "
            "of prior supplied surprises for the same entity and metric. Current and future periods are excluded. "
            "At least four prior observations and nonzero deviation are required. Rate histories use bps. "
            "It describes the supplied history and is not predictive. I make no estimates.")
