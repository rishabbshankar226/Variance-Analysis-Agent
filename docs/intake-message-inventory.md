# Intake Message Inventory

This document lists every user-facing message of the intake workflow (reading a file and preparing it for analysis) in the source at commit `f35a00f`: `parsing.py`, `excel.py`, `analysis.py`, `intake.py`, `join.py`, `pdf_tables.py`, `ixbrl.py`, `statement_shape.py`, `ltm.py`, `metrics.py`, `chat/`. [`scripts/message_inventory.py`](../scripts/message_inventory.py) writes it, so it changes only with the code. The inventory before it was written by hand at `a3ce6bb`.

Per the definitions in [`.agents/rules/variance-intake.md`](../.agents/rules/variance-intake.md), which apply to a message Maya sees:
- **Jargon**: a snake_case key or `repr()` quoting, an exception name, CLI flag syntax (unless the message says it is optional), one of the words "normalize," "alias," "schema," "OOXML," "archive," "XML," "DTD," "payload," "Row Kind," "Unclassified", or an exit code.
- **Offers a Fix**: an error or refusal that tells the reader what to do, or offers chips that do it. A confirmation or a question is not scored (`n/a`), nor is a message shown inside another that carries the fix.

Placeholders such as `{line_item}` show the expression a message prints; they are values, so only the message's own words are checked, except that `!r` is repr quoting. The counts cover messages a chat reader can see; the rest are listed with the reason they are not. Engine messages from `analysis.py` are checked as `plain_analysis_error` shows them in the chat.

---

## 1. Summary

| Metric | Count | Percentage |
|---|---|---|
| **Messages a chat reader can see** | **233** | 100.0% |
| **Messages Containing Jargon** | **0** | 0.0% |
| **Plain-Language Messages** | **233** | 100.0% |
| **Errors and refusals scored for a fix** | **86** | 36.9% |
| **Errors Offering an Actionable Fix** | **86** | 100.0% of errors |
| **Errors With No Fix** | **0** | 0.0% of errors |
| Listed, not seen in the chat | 128 | |

### Breakdown by Component

| Component Source | Messages Seen | Jargon Messages | Errors Offering a Fix |
|---|---|---|---|
| [`variance_agent/analysis.py`](../src/variance_agent/analysis.py) | 18 | 0 (0.0%) | 18 of 18 |
| [`variance_agent/chat/earnings.py`](../src/variance_agent/chat/earnings.py) | 11 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/_common.py`](../src/variance_agent/chat/handlers/_common.py) | 3 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/_items.py`](../src/variance_agent/chat/handlers/_items.py) | 2 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/conversation.py`](../src/variance_agent/chat/handlers/conversation.py) | 13 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/explore.py`](../src/variance_agent/chat/handlers/explore.py) | 14 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/export.py`](../src/variance_agent/chat/handlers/export.py) | 4 | 0 (0.0%) | 2 of 2 |
| [`variance_agent/chat/handlers/lookup.py`](../src/variance_agent/chat/handlers/lookup.py) | 3 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/narrative.py`](../src/variance_agent/chat/handlers/narrative.py) | 2 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/rankings.py`](../src/variance_agent/chat/handlers/rankings.py) | 11 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/router.py`](../src/variance_agent/chat/handlers/router.py) | 7 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/run.py`](../src/variance_agent/chat/handlers/run.py) | 10 | 0 (0.0%) | 2 of 2 |
| [`variance_agent/chat/handlers/scenarios.py`](../src/variance_agent/chat/handlers/scenarios.py) | 6 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/setup.py`](../src/variance_agent/chat/handlers/setup.py) | 18 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/chat/handlers/status.py`](../src/variance_agent/chat/handlers/status.py) | 7 | 0 (0.0%) | 2 of 2 |
| [`variance_agent/chat/handlers/upload.py`](../src/variance_agent/chat/handlers/upload.py) | 14 | 0 (0.0%) | 5 of 5 |
| [`variance_agent/chat/handlers/workbook.py`](../src/variance_agent/chat/handlers/workbook.py) | 13 | 0 (0.0%) | 3 of 3 |
| [`variance_agent/chat/server.py`](../src/variance_agent/chat/server.py) | 4 | 0 (0.0%) | 4 of 4 |
| [`variance_agent/excel.py`](../src/variance_agent/excel.py) | 1 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/intake.py`](../src/variance_agent/intake.py) | 37 | 0 (0.0%) | 24 of 24 |
| [`variance_agent/ixbrl.py`](../src/variance_agent/ixbrl.py) | 5 | 0 (0.0%) | 5 of 5 |
| [`variance_agent/join.py`](../src/variance_agent/join.py) | 2 | 0 (0.0%) | 2 of 2 |
| [`variance_agent/ltm.py`](../src/variance_agent/ltm.py) | 10 | 0 (0.0%) | 10 of 10 |
| [`variance_agent/metrics.py`](../src/variance_agent/metrics.py) | 4 | 0 (0.0%) | 4 of 4 |
| [`variance_agent/parsing.py`](../src/variance_agent/parsing.py) | 9 | 0 (0.0%) | 0 of 0 |
| [`variance_agent/pdf_tables.py`](../src/variance_agent/pdf_tables.py) | 5 | 0 (0.0%) | 5 of 5 |

---

## 2. Complete Message Inventory

### `analysis.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `analysis.py:95` | `Row {row_number}: multiple aliases for '{display_name}': {', '.join(present)}. Supply one column per field.` | No | Yes | shown as 'Multiple columns match the same field. Please provide only one column for each field.' |
| `analysis.py:100` | `Row {row_number}: required field '{display_name}' was not found.{accepted}` | No | Yes | shown as 'Could not find a required '{display_name}' column. Please check your column headers or choose a different worksheet.' |
| `analysis.py:114` | `{line_item}: Statement Kind must be Balance Sheet or Cash Flow. Type one of those in the Statement Kind column.` | No | Yes |  |
| `analysis.py:147` | `{line_item}: Row Kind must be Detail, Total, or Subtotal.` | No | Yes | shown as 'Some subtotal or total rows could not be distinguished from detail rows. Please check summary line items.' |
| `analysis.py:151` | `{line_item}: ambiguous summary label; specify Row Kind as Detail, Total, or Subtotal.` | No | Yes | shown as 'Some subtotal or total rows could not be distinguished from detail rows. Please check summary line items.' |
| `analysis.py:164` | `{line_item}: multiple columns give its type ({', '.join(type_keys)}). Keep one Type column and upload the file again.` | No | Yes |  |
| `analysis.py:323` | `Multiple {line_type.value} summary rows were supplied without detail rows; aggregation would be ambiguous and could double count. Keep one total, or add the lines it totals, and upload the file again.` | No | Yes |  |
| `analysis.py:336` | `Multiple {line_type.value} summary rows have ambiguous scope; supply detail rows only or one reconciled total.` | No | Yes |  |
| `analysis.py:341` | `Summary '{summary.line_item}' does not reconcile to {line_type.value} detail rows; check for missing or overlapping data.` | No | Yes |  |
| `analysis.py:345` | `Summary '{summary.line_item}' does not reconcile to {line_type.value} detail rows; check for missing or overlapping data.` | No | Yes |  |
| `analysis.py:396` | `Comparison basis must be a ComparisonBasis value.` | No | **No** | check of the API's arguments |
| `analysis.py:414` | `segment mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:416` | `dollar variance mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:420` | `percentage mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:422` | `measure or direction mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:428` | `measure/direction metadata mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:435` | `comparison metadata mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:437` | `basis-point variance mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:439` | `statement kind mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:442` | `limit, benchmark or target outcome mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:445` | `F/U status mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:448` | `materiality mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:453` | `driver component reconciliation mismatch for {row.line_item!r}` | **Yes** | **No** | internal check; repr quoting |
| `analysis.py:461` | `material variance membership or sort order is incorrect` | No | **No** | internal check |
| `analysis.py:469` | `{line_type.value} aggregate metrics mismatch` | No | **No** | internal check |
| `analysis.py:490` | `{label} reconciliation mismatch` | No | **No** | internal check |
| `analysis.py:501` | `dataset contains no data rows` | No | **No** | a clause another message completes |
| `analysis.py:509` | `Configuration must be an AnalysisConfig instance.` | No | **No** | check of the API's arguments |
| `analysis.py:515` | `Rows must be a list of row objects.` | No | **No** | check of the API's arguments |
| `analysis.py:517` | `Dataset contains no data rows.` | No | **No** | check of the API's arguments |
| `analysis.py:519` | `Dataset exceeds the supported row count ({MAX_ROWS}).` | No | **No** | check of the API's arguments |
| `analysis.py:523` | `Materiality thresholds must be Decimal values initialized from strings.` | No | **No** | check of the API's arguments |
| `analysis.py:525` | `Materiality thresholds must be finite numbers.` | No | **No** | check of the API's arguments |
| `analysis.py:527` | `Materiality thresholds must be non-negative.` | No | **No** | check of the API's arguments |
| `analysis.py:530` | `Type map must be a dictionary of line-item strings to classifications.` | No | Yes |  |
| `analysis.py:534` | `Type map keys must be nonblank line-item strings.` | No | Yes |  |
| `analysis.py:539` | `Type map value for {item!r} must be Revenue, Expense, or Unclassified.` | **Yes** | Yes | check of the API's arguments; shown as 'Type map value for {item!r} must be Revenue, Expense, or not yet labeled revenue or expense.'; repr quoting |
| `analysis.py:561` | `Row {index}: Period conflicts with the reporting period. Give every row the reporting period, or leave the Period column out.` | No | Yes |  |
| `analysis.py:565` | `Row {index}: Line Item must be a label, text or a number. Type a label in that cell.` | No | Yes |  |
| `analysis.py:569` | `Row {index}: Line Item is blank. Type a label in that cell, or delete the row.` | No | Yes |  |
| `analysis.py:575` | `{line_item}: Currency must be a reporting currency code. Use USD, EUR or GBP in the Currency column.` | No | Yes |  |
| `analysis.py:579` | `{line_item}: row currency {row_currency} conflicts with reporting currency {config.currency}. Run each currency on its own; no currency is converted.` | No | Yes |  |
| `analysis.py:597` | `{line_item}: declared measure amounts cannot be float; supply exact numeric text.` | No | Yes |  |

### `chat/earnings.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `earnings.py:40` | `This file includes supplied earnings comparisons. Would you like an earnings review? I compare the numbers you supply and make no estimates.` | No | n/a | chips |
| `earnings.py:49` | `Choose Review earnings to use these supplied comparisons.` | No | n/a | chips |
| `earnings.py:69` | `Which supplied comparison should Actual be compared against?` | No | n/a | chips |
| `earnings.py:107` | `Upload the file to compare against supplied {basis_noun(basis)}.` | No | n/a |  |
| `earnings.py:146` | `Earnings review: Actual compared with supplied {titles}. I make no estimates.` | No | n/a | chips |
| `earnings.py:181` | `Compared with the supplied numbers. I make no estimates.` | No | n/a | chips |
| `earnings.py:188` | `Supplied rate changes in basis points.` | No | n/a |  |
| `earnings.py:189` | `Upload supplied rate rows with Measure Percent and choose whether Higher or Lower is better.` | No | n/a |  |
| `earnings.py:192` | `Finish confirming the file and your thresholds to compare the supplied numbers.` | No | n/a |  |
| `earnings.py:212` | `I could not read a supported financial table in this file. Upload a CSV, JSON or Excel table with a line item, Actual and your supplied comparison.` | No | n/a |  |
| `earnings.py:237` | `Upload your supplied earnings table or PDF filing for an earnings review. EPS is kept per share; share counts need your Higher/Lower choice.` | No | n/a |  |

### `chat/handlers/_common.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `_common.py:71` | `{lead}What reporting period does this analysis cover? (e.g., Q3 2026, October 2026, FY2026)` | No | n/a |  |
| `_common.py:73` | `{text} Your file's title says {periods}: choose {'it' if len(named) == 1 else 'one'} below, or type a different period.` | No | n/a | chips |
| `_common.py:84` | `I no longer have your file. Please upload it again using the drop zone above.` | No | n/a | chips |

### `chat/handlers/_items.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `_items.py:174` | `No line item matching '{display_q}' was found. Did you mean {names}?` | No | n/a | chips |
| `_items.py:182` | `No line item matching '{display_q}' was found. Available items: {items_list}` | No | n/a |  |

### `chat/handlers/conversation.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `conversation.py:75` | `I am ready to explore **{safe_inline(session.result.config.period)}** from this filing. Type 'summary' for its own printed totals, or drill into any line (e.g. 'why {safe_inline(session.result.rows[0].line_item)}').` | No | n/a |  |
| `conversation.py:128` | `I am ready to explore your **{cfg.period}** financial results. Currently tracking **{cur}** with materiality set at **{format_threshold_amount(cfg.dollar_threshold, cur)} or {format_threshold_pct(cfg.percent_threshold)}**. Overall net operating impact is a **{format_money(abs(net_impact), cur, places)} {status}** against {_noun(cfg)}. What would you like to review? You can ask for an 'executive memo', a 'waterfall' walk, 'run rate' projections, or drill down into any account (e.g. 'why {safe_inline(session.result.rows[0].line_item)}').` | No | n/a | chips |
| `conversation.py:128` | `Your file has been validated and loaded. Which reporting period does it cover? For example 'Q3 2026' or 'August 2026'.` | No | n/a | chips |
| `conversation.py:128` | `Next come the materiality thresholds: a dollar amount and a percentage, for example '$10,000 or 5%'.` | No | n/a | chips |
| `conversation.py:128` | `What currency are these figures reported in? For example 'USD', 'EUR' or 'GBP'.` | No | n/a | chips |
| `conversation.py:128` | `Some lines are not yet labeled revenue or expense. Choose 'Revenue', 'Expense' or 'Skip' for the line named above.` | No | n/a | chips |
| `conversation.py:128` | `**Welcome to the Variance Analysis Agent.** Every figure comes from exact, repeatable calculations. Drop a CSV, JSON or Excel workbook above to start, or ask about a variance concept.` | No | n/a | chips |
| `conversation.py:139` | `You're very welcome! Always glad to assist with institutional FP&A rigor. Feel free to test scenario simulations (e.g. 'what if revenue drops 5%?'), inspect causal drivers, or export the executive commentary memo whenever you're ready.` | No | n/a | chips |
| `conversation.py:165` | `**Institutional Variance Analysis Agent** I am an intelligent, deterministic financial analysis assistant built specifically for FP&A teams, controllers, and CFO organizations. **How I differ from a non-deterministic LLM:** • **100% Deterministic Calculations**: Zero hallucination. Every variance, percentage, and waterfall step is computed with 50-digit exact Decimal precision. • **Source Fingerprints**: Every analysis produces a SHA-256 fingerprint of the file it came from, for traceability. • **Conversational Fluency**: I interpret natural business queries, multi-turn follow-ups, and scenarios, giving you the ease of a conversational AI with the trustworthiness of an audited ledger. • **No AI Model In The Loop**: The calculations use standard-library Python and no language model sees or computes your numbers. {where}` | No | n/a | chips |
| `conversation.py:184` | `Here is what happened with **{safe_inline(row.line_item)}** in {cfg.period}: • **{_heading(cfg)}:** {format_money(row.budget, cfg.currency, places)} • **Actual:** {format_money(row.actual, cfg.currency, places)} • **Variance:** **{format_money(row.variance_dollars, cfg.currency, places)}** ({format_pct(row.budget, row.variance_dollars, row.percent_label)}, {status_desc}) Would you like to inspect its causal driver decomposition ('why {safe_inline(row.line_item)}') or simulate a change ('what if {safe_inline(row.line_item)} drops 5%')?` | No | n/a | chips |
| `conversation.py:210` | `**Note:** Net operating impact measures the overall variance contribution toward operating profit. Under standard financial rules, profit measures are not treated as additive revenue to prevent double-counting. Try asking: 'summary', 'what is net impact?', or 'totals'.` | No | n/a | chips |
| `conversation.py:221` | `**Note:** This analysis evaluates actual performance against {baseline} for the closed reporting period. To project full-year outcomes based on current pace, ask for 'run rate' or test scenarios with 'what if revenue drops 5%?'.` | No | n/a | chips |
| `conversation.py:241` | `I want to make sure I provide the exact figures you need. I couldn't find an account matching "{safe_inline(text if len(text) <= 80 else text[:80] + '…')}" in your current dataset. Here are a few ways we can explore your numbers: • **Account Driver Breakdown:** Ask 'why [Account Name]' (e.g. 'why {safe_inline(first_item)}') • **Profit Waterfall:** Ask for 'waterfall' to reconcile {noun} to actual operating profit • **Scenario Analysis:** Try 'what if revenue drops 5%?' or 'sensitivity' • **Management Commentary:** Ask for 'memo' or 'tldr' for executive highlights` | No | n/a | chips |

### `chat/handlers/explore.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `explore.py:99` | `**What you can ask** I compare each line's Actual against your budget, forecast or prior period, flag the gaps big enough to matter, and say whether each one helped or hurt profit. Every figure comes from exact, repeatable calculations, never estimates. It is built for FP&A analysts, controllers and anyone preparing a month-end or quarter-end variance review. **Analysis** • 'memo' / 'briefing': a management briefing on the period, with a download • 'waterfall' / 'bridge': the walk from budget to actual operating profit, step by step • 'what if [line] [+/-X% or $Y]': profit and margin if one line changes • 'sensitivity': operating profit under five revenue and expense swings • 'run rate' / 'project year end': the annualised pace and a latest-estimate projection • 'drivers' / 'driver summary': which lines have driver data, and whether it reconciles • 'biggest risks': the largest material unfavorable variances • 'biggest wins': the largest favorable variances • 'revenue status': revenue against budget, line by line • 'expense status': expenses against budget, and the largest overspends • 'burn rate' / 'budget utilization': the share of the expense budget spent • 'variance concentration' / 'pareto': the share of the total variance in the top three lines • 'unbudgeted spend': lines with spending and no budget • 'cost savings': expense lines below budget • 'revenue misses': revenue lines below budget • 'highest percent': the largest variances in percentage terms • 'compare [line] vs [line]': two lines side by side, actual against budget, or revenue against expenses • 'sheets' / 'sheet <name>': list and switch Excel worksheets or PDF statements • 'metrics': line counts, the material share and the mix of lines **Concepts, any time** • 'what is materiality?': the dollar-or-percent test for what needs explaining • 'favorable vs unfavorable': why a revenue gain and an expense saving are both favorable • 'what is net impact?': how net operating impact is worked out • 'budget vs forecast': how a budget and a latest estimate differ • 'timing vs permanent': variances that reverse and variances that last • 'operating leverage': fixed and variable costs, and drop-through • 'what are financial kpis?': the measures a variance review reports • 'what is driver decomposition?': splitting a variance into price and volume • 'audit trail': what the audit file records, including source fingerprints **Exploring the results** • 'summary': the headline figures and net operating impact • 'material': every material variance • 'unfavorable' / 'favorable': one status only • 'revenue' / 'expenses': one type only • 'top 3': the largest variances by amount • 'totals': revenue and expense totals • 'warnings': data quality notes • 'recommendations': suggested next steps for the largest variances **One line in detail** • 'why [line]': what drove one line's variance • 'detail [line]': everything recorded for one line • 'threshold $X or Y%': run again with different materiality thresholds **Export and session** • 'export report': download the Markdown report • 'export excel': download the Excel workbook • 'export csv': download every row as CSV • 'export audit': download the audit file (JSON) • 'report': show the full report here • 'new': start over with a new file • 'help': show this list` | No | n/a | chips |
| `explore.py:109` | `Session cleared. Upload a new file to begin.` | No | n/a |  |
| `explore.py:128` | `No line item exceeded either configured materiality threshold.` | No | n/a | chips |
| `explore.py:148` | `**Material Variances** (Threshold: {format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or {format_threshold_pct(cfg.percent_threshold)})` | No | n/a | chips |
| `explore.py:168` | `No {label.lower()} variances found.` | No | n/a | chips |
| `explore.py:189` | `**{label} Variances** ({len(filtered)} item{'s' if len(filtered) != 1 else ''})` | No | n/a | chips |
| `explore.py:207` | `No {type_label(line_type)} rows found.` | No | n/a | chips |
| `explore.py:220` | `**{type_label(line_type)} Items** ({len(filtered)} row{'s' if len(filtered) != 1 else ''})` | No | n/a | chips |
| `explore.py:237` | `Please ask for at least 1 line, for example 'top 3'.` | No | n/a | chips |
| `explore.py:251` | `No {line_type.value if line_type else 'line item'} rows found.` | No | n/a | chips |
| `explore.py:266` | `**Top {count} {line_type.value + ' ' if line_type else ''}Variances by Absolute Amount**` | No | n/a | chips |
| `explore.py:280` | `I couldn't parse those thresholds. Use: 'threshold $10,000 or 5%', or adjust one: 'threshold $25,000' or 'threshold 8%'` | No | n/a | chips |
| `explore.py:290` | `Materiality thresholds are not fully specified. Please enter both: '$10,000 or 5%'` | No | n/a | chips |
| `explore.py:328` | `No data quality warnings.` | No | n/a | chips |

### `chat/handlers/export.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `export.py:99` | `**Layout Mapping Saved** Here are your confirmed layout settings. Save them as a file to reuse in future months; on the command line, that file is the optional '--mapping' setting: '''json {mapping_json} '''` | No | n/a | chips |
| `export.py:126` | `{written} written to '{safe_inline(str(target) if path.startswith('~') else path)}'.` | No | n/a | chips |
| `export.py:132` | `Could not write to '{safe_inline(path)}': {display_text(str(exc))}` | No | Yes | chips |
| `export.py:165` | `Saving to '{safe_inline(path)}' is turned off on this hosted version. Use **{chip}** to download the file instead.` | No | Yes | chips |

### `chat/handlers/lookup.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `lookup.py:112` | `Multiple matches found. Which one? {'\n'.join((f'• {safe_inline(m)}' for m in matches))}` | No | n/a | chips |
| `lookup.py:168` | `Multiple matches: {'\n'.join((f'• {safe_inline(m)}' for m in matches))}` | No | n/a | chips |
| `lookup.py:178` | `{len(named_rows)} line items are named '{safe_inline(matched_name)}'; here is each one.` | No | n/a | chips |

### `chat/handlers/narrative.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `narrative.py:324` | `**Causal Driver Models Overview** • **Lines with a reconciled driver model:** **{len(rows_reconciled)}** of **{len(result.rows)}** ({with_data}). • **Material variances covered:** **{coverage_pct}%** have a reconciled driver breakdown. A driver model splits a variance from {_noun(cfg)} into its causes, such as price and volume, or rate and volume.` | No | n/a | chips |
| `narrative.py:398` | `**The Executive TL;DR for {cfg.period}:** Operating Profit finished at **{format_money(actual_profit, cur, places)}**, {outcome} with operating margin standing at **{_pct_text(margin)}**. {revenue_clause}, while {expense_clause}.{driver_context}` | No | n/a | chips |

### `chat/handlers/rankings.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `rankings.py:56` | `**No Material Risks Detected** There are zero material unfavorable variances exceeding your thresholds ({format_threshold_amount(cfg.dollar_threshold, cfg.currency)} or {format_threshold_pct(cfg.percent_threshold)}). All revenue targets and expense allocations performed within {_noun(cfg)} tolerance.` | No | n/a | chips |
| `rankings.py:125` | `**No Material Favorable Variances** No line items exceeded the favorable materiality thresholds. Check 'summary' or lower thresholds with 'threshold $X or Y%' to explore smaller variances.` | No | n/a | chips |
| `rankings.py:164` | `No line items with a non-zero {_noun(cfg)} were found.` | No | n/a | chips |
| `rankings.py:184` | `**Top Line Items by Percentage Variance** (Largest relative swings):` | No | n/a | chips |
| `rankings.py:330` | `Could not find a line item matching '{safe_inline(name1)}'.` | No | n/a | chips |
| `rankings.py:336` | `Could not find a line item matching '{safe_inline(name2)}'.` | No | n/a | chips |
| `rankings.py:343` | `Multiple matches for '{safe_inline(name1)}': {', '.join(matches1)}. Please be more specific.` | No | n/a | chips |
| `rankings.py:349` | `Multiple matches for '{safe_inline(name2)}': {', '.join(matches2)}. Please be more specific.` | No | n/a | chips |
| `rankings.py:362` | `Comparing '**{safe_inline(row1.line_item)}**' against itself. Account details:` | No | n/a | chips |
| `rankings.py:384` | `**Side-by-Side Comparison: {safe_inline(row1.line_item)} vs. {safe_inline(row2.line_item)}** {lead}` | No | n/a | chips |
| `rankings.py:430` | `**Zero Variance Volatility:** All line items performed exactly to {_noun(cfg)}.` | No | n/a | chips |

### `chat/handlers/router.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `router.py:85` | `Please type a message or upload a file.` | No | n/a |  |
| `router.py:96` | `That message is too long for me to read as a question (limit {MAX_ROUTING_CHARS} characters). Ask a shorter question. To load data, paste a table before any file is loaded, or type 'new' and use the drop zone.` | No | n/a |  |
| `router.py:144` | `**Technical Details:** ''' {detail} '''` | No | n/a | chips |
| `router.py:158` | `Choose the new file in the drop zone below. It replaces the current one once it has been read successfully; until then you can keep working with the current file.` | No | n/a | chips |
| `router.py:169` | `Please upload a file using the drop zone above, or paste a table copied from a spreadsheet.` | No | n/a |  |
| `router.py:213` | `This file has no {words} to compare. Upload a 10-K or 10-Q from EDGAR, and I'll read its statements.` | No | n/a |  |
| `router.py:223` | `Upload a file with Actual, {needs}, and I'll compare each row against its {header.lower()}.` | No | n/a |  |

### `chat/handlers/run.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `run.py:62` | `'{safe_inline(name)}' looks like the total of the {line_type} lines above it{figures}. A total that doesn't match its lines can't be checked, so I stopped instead of guessing. Leave it out of the line items, or upload a corrected file.` | No | Yes | chips |
| `run.py:92` | `I need your materiality thresholds first. Enter a dollar amount and a percentage, for example: '$10,000 or 5%'` | No | n/a | chips |
| `run.py:111` | `{text} {fix}` | No | Yes | chips |
| `run.py:205` | `Analysis complete, but **{remaining}** line item{'s are' if remaining != 1 else ' is'} not yet labeled revenue or expense. **'{item}'** is not yet labeled revenue or expense. Should it be:` | No | n/a | chips |
| `run.py:245` | `Rules applied! **{remaining}** item{'s' if remaining != 1 else ''} remaining. **'{item}'** is not yet labeled revenue or expense. Should it be:` | No | n/a | chips |
| `run.py:286` | `Please choose Revenue, Expense, or Skip for '{safe_inline(current_item)}'.` | No | n/a | chips |
| `run.py:299` | `Got it. {remaining} remaining. **'{next_item}'** is not yet labeled revenue or expense. Should it be:` | No | n/a | chips |
| `run.py:378` | `For **{safe_inline(name)}**, is Higher or Lower better?` | No | n/a | chips |
| `run.py:378` | `For **{safe_inline(name)}**, read {safe_inline(bare[0])} as {percent}%? Confirm fractions, or keep bare numbers as percentage points.` | No | n/a | chips |
| `run.py:378` | `What absolute threshold in {unit} should flag {kind} variances? Enter a non-negative number.` | No | n/a | chips |

### `chat/handlers/scenarios.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `scenarios.py:139` | `**P&L Variance Bridge (Waterfall Walk)** Reconciling baseline {_heading(cfg)} Operating Profit to Actual Operating Profit for **{safe_inline(session.period or '')}**: • **{_heading(cfg)} Operating Profit**: {format_money(budget_profit, cur, places)} • **Revenue Bridge Impact**: {format_money(rev_impact, cur, places)} ({rev_status}) • **Expense Bridge Impact**: {format_money(exp_impact, cur, places)} ({exp_status}) • **Actual Operating Profit**: {format_money(actual_profit, cur, places)} • **Net Profit Variance**: {format_money(net_var, cur, places)} ({status_text}) Each line item's contribution to operating profit is displayed in the bridge table below (positive values expand profit; negative values contract profit):` | No | n/a | chips |
| `scenarios.py:149` | `Please specify a simulation amount or percentage (e.g., 'what if revenue drops 5%?' or 'what if marketing increases $20,000?').` | No | n/a | chips |
| `scenarios.py:183` | `Could not parse numeric amount from '{safe_inline(raw_amount)}'.` | No | n/a | chips |
| `scenarios.py:194` | `A drop of more than 100% would take {safe_inline(target_clean)} below zero, which is not a meaningful scenario. Try a smaller percentage or a dollar amount.` | No | n/a | chips |
| `scenarios.py:222` | `Could not identify target '{safe_inline(target_clean)}'. You can simulate 'revenue', 'expenses', or a specific line item from your data.` | No | n/a | chips |
| `scenarios.py:230` | `**{safe_inline(matched_row.line_item)}** is not classified as Revenue or Expense, so I cannot tell whether a change helps or hurts profit. Classify it first: type 'new', upload the file again and label it when asked, or add a Type column to your file.` | No | n/a | chips |

### `chat/handlers/setup.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `setup.py:51` | `Period set to: **{safe_inline(session.period)}** Now set the materiality thresholds. Enter a dollar amount and a percentage, for example: '$10,000 or 5%' Or choose a preset below:` | No | n/a | chips |
| `setup.py:67` | `What would you like to change? You can choose a different {_sheet_word(session)} or upload a different file.` | No | n/a | chips |
| `setup.py:91` | `Period set to: **{safe_inline(session.period)}** Now set the materiality thresholds. Enter a dollar amount and a percentage, for example: '$10,000 or 5%' Or choose a preset below:` | No | n/a | chips |
| `setup.py:100` | `Please confirm if the layout looks right, or choose to change something.` | No | n/a | chips |
| `setup.py:116` | `{blanks.capitalize()} cannot stay blank in the analysis: a line with no amount is read as 0 ({zero_comparison_phrase(basis)}). Choose **{treat}** to continue, or upload a corrected file.` | No | n/a | chips |
| `setup.py:144` | `Found data for multiple periods in your file. Which period would you like to analyze?` | No | n/a | chips |
| `setup.py:165` | `Please upload a file using the drop zone above.` | No | n/a | chips |
| `setup.py:178` | `Please choose which period you would like to analyze. Pick one of the periods found in your file.` | No | n/a | chips |
| `setup.py:233` | `The reporting period cannot be blank. Please enter a period (e.g., Q3 2026).` | No | n/a |  |
| `setup.py:238` | `Please enter a short period label of up to {_MAX_PERIOD_CHARS} characters (e.g., Q3 2026, October 2026, FY2026).` | No | n/a | chips |
| `setup.py:245` | `'{safe_inline(period)}' looks like a command, not a reporting period. Enter the period this file covers first (e.g., Q3 2026, October 2026, FY2026).` | No | n/a | chips |
| `setup.py:255` | `Period set to: **{safe_inline(period)}** Now set the materiality thresholds. Enter a dollar amount and a percentage, for example: '$10,000 or 5%' Or choose a preset below:` | No | n/a | chips |
| `setup.py:269` | `I couldn't parse those thresholds. Please enter them as: '$10,000 or 5%'` | No | n/a | chips |
| `setup.py:280` | `Thresholds set: **{format_threshold_amount(dollar, session.currency)}** or **{format_threshold_pct(pct_ratio)}** What is the reporting currency?` | No | n/a | chips |
| `setup.py:312` | `Please choose a supported currency: USD, EUR, or GBP.` | No | n/a | chips |
| `setup.py:329` | `Choose Higher or Lower for this measure.` | No | n/a | chips |
| `setup.py:336` | `Choose how to read bare rates before the analysis.` | No | n/a | chips |
| `setup.py:343` | `Threshold must be non-negative.` | No | **No** | caught where it is raised |
| `setup.py:345` | `Enter a non-negative numeric threshold, such as 25.` | No | n/a |  |

### `chat/handlers/status.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `status.py:80` | `No classified Revenue rows exist in this dataset.` | No | n/a | chips |
| `status.py:87` | `Total revenue cannot be certified because there are still unclassified line items. Classify them first.` | No | Yes | chips |
| `status.py:146` | `No classified Expense rows exist in this dataset.` | No | n/a | chips |
| `status.py:153` | `Total expenses cannot be certified because there are still unclassified line items.` | No | Yes | chips |
| `status.py:273` | `**No {wording.heading}:** {wording.empty_state}` | No | n/a | chips |
| `status.py:325` | `**No Cost Savings:** No expense accounts operated below their budgeted allocation.` | No | n/a | chips |
| `status.py:377` | `**No Revenue Misses:** All revenue accounts met or exceeded the {_noun(cfg)}.` | No | n/a | chips |

### `chat/handlers/upload.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `upload.py:61` | `Covenant headroom is computed from a filing. Upload the 10-K's or 10-Q's .htm document from EDGAR first.` | No | n/a |  |
| `upload.py:64` | `Upload your metrics file: a JSON file declaring each ratio's terms (see docs/financial-rules.md, Derived metrics). Then I'll ask for the covenant schedule.` | No | n/a |  |
| `upload.py:77` | `Now upload the covenant schedule: each metric's name, its Limit, and its Limit Kind (Max or Min), with a Buffer where you have one.` | No | n/a |  |
| `upload.py:88` | `I couldn't compare these metrics. Upload the covenant schedule again, or type 'new' to start over.` | No | Yes |  |
| `upload.py:102` | `'{safe_inline(filename)}' {_half_wording(missing, key)}` | No | n/a |  |
| `upload.py:136` | `'{safe_inline(filename)}' replaces '{safe_inline(held_name)}': it {wording}` | No | n/a |  |
| `upload.py:148` | `I couldn't join these two files. Upload them again, or upload one file that holds both the comparison and Actual.` | No | Yes |  |
| `upload.py:180` | `{message.removesuffix(JOIN_FIX)}Choose **{chip}** to read them with a {basis_noun(basis)} of 0, or upload a corrected file.` | No | Yes | chips |
| `upload.py:195` | `I couldn't join these two files. Upload them again, or upload one file that holds both the comparison and Actual.` | No | Yes |  |
| `upload.py:220` | `LTM is built from a 10-Q and a 10-K filed on EDGAR. Upload the 10-Q's .htm document first.` | No | n/a |  |
| `upload.py:223` | `Upload the 10-K whose fiscal year this 10-Q continues. I'll build LTM as that fiscal year plus this year to date less last year to date, line by line by XBRL concept, and compare it with the fiscal year.` | No | n/a |  |
| `upload.py:233` | `I couldn't build LTM from these two filings.` | No | Yes | chips |
| `upload.py:398` | `Found **{count}** line item{'s' if count != 1 else ''} with {blanks} (such as {safe_inline(sample)}). Blank amounts cannot stay blank in the analysis, so they are read as 0. {treat}?` | No | n/a | chips |
| `upload.py:417` | `Found data for multiple periods in your file. Which period would you like to analyze?` | No | n/a | chips |

### `chat/handlers/workbook.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `workbook.py:37` | `No file has been uploaded yet. Please upload an Excel workbook (.xlsx or .xlsm) or a PDF filing first.` | No | n/a | chips |
| `workbook.py:46` | `The uploaded file **'{safe_inline(session.source_name)}'** is a {suffix.upper().lstrip('.')} file, which contains a single dataset rather than multiple worksheets.` | No | n/a | chips |
| `workbook.py:60` | `No readable {word}s found in '{safe_inline(session.source_name)}'.` | No | n/a |  |
| `workbook.py:86` | `**{word.capitalize()}s in '{safe_inline(session.source_name)}' ({len(sheets)} total):** {'\n'.join(sheet_list_md)} To switch {word}s, type '{_sheet_chip(session, '<name>').lower()}' (e.g., '{_sheet_chip(session, safe_inline(sheets[1] if len(sheets) > 1 else sheets[0])).replace('Statement ', 'statement ', 1).replace('Sheet ', 'sheet ', 1)}').` | No | n/a | chips |
| `workbook.py:92` | `No file has been uploaded yet. Please upload an Excel workbook (.xlsx or .xlsm) or a PDF filing first.` | No | n/a |  |
| `workbook.py:100` | `The uploaded file **'{safe_inline(session.source_name)}'** is a {suffix.upper().lstrip('.')} file, which does not have multiple worksheets.` | No | n/a |  |
| `workbook.py:138` | `{word.capitalize()} '{safe_inline(target_sheet)}' was not found in '{safe_inline(session.source_name)}'. Available {word}s: {available_str}.` | No | Yes | chips |
| `workbook.py:147` | `{word.capitalize()} **'{safe_inline(matched_sheet)}'** is already active.` | No | n/a | chips |
| `workbook.py:175` | `Failed to load {word} '{safe_inline(matched_sheet)}': {plain_err}` | No | Yes | chips |
| `workbook.py:215` | `Switched to {word} **'{safe_inline(matched_sheet)}'** ({row_count} data row{'s' if row_count != 1 else ''}). Current reporting period: **{safe_inline(session.period or 'Not set')}**.` | No | n/a |  |
| `workbook.py:226` | `Upload a workbook first; I'll ask about hidden rows if it has any.` | No | n/a |  |
| `workbook.py:251` | `Got it. I will compare Actual against the {noun} once you upload a file.` | No | n/a |  |
| `workbook.py:270` | `Could not compare against the {noun}: {plain_analysis_error(technical)}` | No | Yes | chips |

### `chat/server.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `server.py:210` | `Unexpected Host header.` | No | **No** | protocol reply |
| `server.py:230` | `Cross-origin requests are not allowed.` | No | **No** | protocol reply |
| `server.py:251` | `Something went wrong while handling that request. Please try again, or type reset to start over.` | No | Yes |  |
| `server.py:300` | `File not found.` | No | **No** | protocol reply |
| `server.py:302` | `Not found.` | No | **No** | protocol reply |
| `server.py:317` | `Not found.` | No | **No** | protocol reply |
| `server.py:323` | `Expected multipart/form-data.` | No | **No** | protocol reply |
| `server.py:332` | `The upload has no multipart boundary.` | No | **No** | protocol reply |
| `server.py:356` | `No file found in the upload. Please select a CSV, JSON, XLSX, XLSM, or PDF file.` | No | Yes |  |
| `server.py:374` | `Expected application/json.` | No | **No** | protocol reply |
| `server.py:383` | `Invalid JSON.` | No | **No** | protocol reply |
| `server.py:388` | `Expected a JSON object with a text string.` | No | **No** | protocol reply |
| `server.py:392` | `Empty message.` | No | **No** | protocol reply |
| `server.py:413` | `Invalid Content-Length.` | No | **No** | protocol reply |
| `server.py:418` | `That file is larger than the {MAX_INPUT_BYTES // (1024 * 1024)} MiB the chat accepts. Save just the sheet with the statement as a new file and upload that.` | No | Yes |  |
| `server.py:429` | `The upload arrived too slowly. Please try again.` | No | Yes |  |
| `server.py:483` | `Static file not found: {filename}` | No | **No** | protocol reply |

### `excel.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `excel.py:345` | `A sheet in the workbook is nested more than {MAX_XML_DEPTH} levels deep, more than I can read.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:350` | `Excel physical rows must increase within 1..{MAX_ROWS}.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:378` | `Excel worksheet exceeds the supported cell count ({MAX_CELLS}).` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:387` | `Excel cell contains an invalid physical coordinate.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:393` | `Excel cell coordinate conflicts with its physical row.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:396` | `Excel physical coordinates exceed {MAX_ROWS} rows or {MAX_COLUMNS} columns.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:399` | `Excel physical cell columns must be strictly increasing.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:411` | `Excel numeric literal exceeds the supported length.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:505` | `The workbook holds more than {MAX_ARCHIVE_MEMBERS} parts, more than I can read.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:507` | `The workbook holds two parts with the same name, so it is damaged.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:509` | `The workbook is larger than 64 MiB once unpacked, more than I can read.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:520` | `Excel part {member.filename} exceeds {_MAX_AUXILIARY_PART_BYTES // (1024 * 1024)} MiB.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:528` | `The workbook is larger than 64 MiB once unpacked, more than I can read.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:530` | `The workbook declares entities of its own, which workbooks saved by Excel don't, so this reader refuses it.` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:538` | `The workbook is damaged and can't be opened ({exc}).` | No | **No** | replaced in the chat by intake's workbook refusal |
| `excel.py:545` | `Excel numeric cell is missing its stored decimal representation.` | No | n/a | shown after "Could not read Excel file ..." |

### `intake.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `intake.py:650` | `{line_item}: required value in {field} is missing.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:653` | `{line_item}: field '{field}' must be numeric, not boolean.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:657` | `{line_item}: field '{field}' must be a finite number.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:663` | `{line_item}: field '{field}' must be a finite number.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:667` | `{line_item}: field '{field}' must be a numeric scalar.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:671` | `{line_item}: field '{field}' has a footnote mark or small digit ({marks}) in: {value}.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:680` | `{line_item}: required value in {field} is missing (marked {text}).` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:699` | `{line_item}: field '{field}' must be a finite number.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:703` | `{line_item}: field '{field}' has an unrecognized number format: {value}.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:708` | `{line_item}: field '{field}' currency {code} conflicts with reporting currency {currency}; no currency conversion is performed.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:719` | `{line_item}: field '{field}' is not numeric: {value}.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:725` | `{line_item}: field '{field}' must be a finite number.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:727` | `{line_item}: field '{field}' exceeds the supported numeric length.` | No | n/a | shown under "Fix these cells and upload the file again" |
| `intake.py:1349` | `Excel files require the optional Excel tools. Please install with: pip install 'variance-analysis-agent[excel]'` | No | Yes | a clause another message completes |
| `intake.py:1669` | `I could not read '{filename}' as text. Save it as a UTF-8 CSV (in Excel: Save As, then CSV UTF-8) and upload it again.` | No | Yes |  |
| `intake.py:1771` | `The file '{filename}' exceeds the supported file size limit of 32 MiB. Save just the sheet with the statement as a new file and upload that.` | No | Yes |  |
| `intake.py:1832` | `Unsupported input format '{suffix}'. Please use an Excel workbook (.xlsx, .xlsm), a CSV, TSV, JSON or PDF file.` | No | Yes |  |
| `intake.py:1878` | `'{filename}' has more than {MAX_COLUMNS} columns, which is more than I can read. Delete the columns the analysis doesn't need and upload the file again.` | No | Yes |  |
| `intake.py:1884` | `'{filename}' has more rows or cells than I can read (limits: {MAX_ROWS} rows and {MAX_CELLS} cells). Save just the rows the analysis needs as a new file and upload that.` | No | Yes |  |
| `intake.py:1891` | `I could not split '{filename}' into columns: {str(exc).rstrip('.')}. Save it from Excel as CSV and upload that.` | No | Yes |  |
| `intake.py:1976` | `Could not read JSON data from '{filename}': {str(exc).rstrip('.')}. Save the table as CSV or Excel and upload that instead.` | No | Yes |  |
| `intake.py:2029` | `The Excel file '{filename}' has a worksheet larger than I can read (at most {MAX_ROWS} rows and {MAX_CELLS} cells on any sheet, hidden sheets included). Export the sheet you need to CSV, or save a copy without the large sheet.` | No | Yes |  |
| `intake.py:2029` | `The Excel file '{filename}' could not be opened safely. Open it in Excel, save it again as .xlsx, and upload that.` | No | Yes |  |
| `intake.py:2045` | `Could not read Excel file '{filename}': {str(exc).rstrip('.')}. Open it in Excel, save the sheet with the statement as a new workbook, and upload that.` | No | Yes |  |
| `intake.py:2061` | `The Excel workbook '{filename}' contains no worksheets. Open it in Excel, check that it holds the statement, then save it and upload it again.` | No | Yes |  |
| `intake.py:2101` | `Worksheet '{chosen_sheet}' was not found in '{filename}'. Available sheets: {', '.join(sheetnames)}. Choose one of those sheets.` | No | Yes |  |
| `intake.py:2462` | `Sheet '{sheet_name}' has no {duration} columns. Choose one of: {named}.` | No | Yes |  |
| `intake.py:2474` | `has lines hidden in Excel, and leaving lines out would break the statement's subtotals. Count them, or unhide them` | No | Yes | a clause another message completes |
| `intake.py:2477` | `shows some amounts scaled by their number format, so their unit can't be read from the caption. Give the amounts a plain number format` | No | Yes | a clause another message completes |
| `intake.py:2480` | `'{chosen.name}' lists {_NOT_REVENUE_AND_EXPENSE[chosen.kind]}, which can't be compared as revenue and expense yet. Choose the income statement's sheet instead.` | No | Yes |  |
| `intake.py:2503` | `Sheet '{sheet_name}' {problem}, and upload the file again.` | No | Yes |  |
| `intake.py:2599` | `No statement called '{sheet}' was found in '{filename}'. Statements found: {', '.join(names)}. Choose one of those statements.` | No | Yes |  |
| `intake.py:2658` | `'{names_by_line[at]}' prints no figure for {chosen.labels[column]} in the {chosen.name}, and no subtotal there confirms it is 0, so I stopped instead of guessing. Choose another statement from this filing.` | No | Yes |  |
| `intake.py:2763` | `I couldn't check the {chosen.name}. Upload a CSV or Excel copy of the statement instead.` | No | Yes |  |
| `intake.py:3081` | `No statement called '{sheet}' was found in '{filename}'. Statements found: {', '.join(names)}. Choose one of those statements.` | No | Yes |  |
| `intake.py:3092` | `'{chosen.name}' lists {_NOT_REVENUE_AND_EXPENSE[chosen.kind]}, which can't be compared as revenue and expense yet. Upload the income statement instead, or a CSV or Excel copy of it.` | No | Yes |  |
| `intake.py:3307` | `The file '{filename}' contains no data. Upload a file with a header row (such as Line Item, Budget, Actual) and at least one line.` | No | Yes |  |
| `intake.py:3353` | `Could not find a header row with Line Item, Budget, and Actual columns in '{filename}' (a Forecast or Prior Year column can stand in for Budget). Add a header row that names those columns, and upload the file again.{hint}` | No | Yes |  |
| `intake.py:3353` | `Could not find a header row with Line Item, {comparison_heading(compare_to, None)}, and Actual columns in '{filename}'. Add a header row that names those columns, and upload the file again.` | No | Yes |  |
| `intake.py:3379` | `Sheet '{sheet_name}' has no separate table in {excel.block}. Choose one of its tables: {tables_named}.` | No | Yes |  |

### `ixbrl.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `ixbrl.py:191` | `number words '{raw}'` | No | **No** | a clause another message completes |
| `ixbrl.py:195` | `'{raw}' is not a plain decimal` | No | **No** | a clause another message completes |
| `ixbrl.py:199` | `'{raw}' is not a figure in the {fmt or 'plain'} format` | No | **No** | a clause another message completes |
| `ixbrl.py:203` | `'{raw}' is not a figure in the {fmt} format` | No | **No** | a clause another message completes |
| `ixbrl.py:205` | `the {fmt} format` | No | **No** | a clause another message completes |
| `ixbrl.py:231` | `reading the filing took longer than 20 seconds` | No | **No** | a clause another message completes |
| `ixbrl.py:251` | `the filing has more contexts than can be read` | No | **No** | a clause another message completes |
| `ixbrl.py:264` | `the filing has more figures than can be read` | No | **No** | a clause another message completes |
| `ixbrl.py:276` | `the filing has more tables than can be read` | No | **No** | a clause another message completes |
| `ixbrl.py:283` | `a table in the filing has more rows than can be read` | No | **No** | a clause another message completes |
| `ixbrl.py:479` | `'{filename}' declares entities of its own, which filings on EDGAR don't, so this reader refuses it. Upload a CSV or Excel copy of the statement, or the filing's PDF.` | No | Yes |  |
| `ixbrl.py:489` | `'{filename}' is a web page without Inline XBRL figures, so it has no statements I can find. Upload the filing's 10-K or 10-Q document from its EDGAR folder, its PDF, or a CSV or Excel table.` | No | Yes |  |
| `ixbrl.py:546` | `The financial statements aren't in '{filename}' itself: it points to {elsewhere}, the annual report that holds them. Upload that document from the same EDGAR filing, or the statements as Excel or CSV.` | No | Yes |  |
| `ixbrl.py:549` | `I could not find the financial statements in '{filename}': no table there is titled as an income statement, balance sheet or cash flow statement and holds their tagged figures. If the filing puts them in another document (often Exhibit 13, the annual report), upload that document from the same EDGAR filing; otherwise upload the statements as Excel or CSV.` | No | Yes |  |
| `ixbrl.py:668` | `'{filename}' declares entities of its own, which filings on EDGAR don't, so this reader refuses it. Upload a CSV or Excel copy of the statement, or the filing's PDF.` | No | Yes |  |

### `join.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `join.py:78` | `'{comparison_name}' already has an Actual column, so it isn't the comparison half of a pair. Run it on its own, without --compare-file.` | **Yes** | Yes | command line only; flag --compare-file |
| `join.py:81` | `'{actual_name}' already has a comparison column, so it isn't the actuals half of a pair. Run it on its own, without --compare-file.` | **Yes** | Yes | command line only; flag --compare-file |
| `join.py:105` | `'{key}' appears more than once in '{name}', so I can't tell which row to join. Combine those rows, or give each its own {key_name}, and run again.` | No | Yes |  |
| `join.py:119` | `In '{one_name}' but not in '{other_name}': {_shown(only, one, by_account)}. Joining without them would change the totals without a trace. Add each line to the other file, or remove it, and run again.` | No | Yes |  |

### `ltm.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `ltm.py:82` | `No statement called '{sheet}' was found in '{quarter_name}'. Statements found: {', '.join((s.name for s in quarter_statements))}. Choose one of those statements.` | No | Yes |  |
| `ltm.py:86` | `LTM is built for income statements: a cash flow statement's beginning and ending cash are balances, which don't add across periods. Choose the income statement, or compare the cash flow statement on its own.` | No | Yes |  |
| `ltm.py:97` | `'{quarter_name}' has no {kind.replace('_', ' ')} statement to build LTM from. Compare the 10-Q on its own instead.` | No | Yes |  |
| `ltm.py:100` | `'{annual_name}' has no fiscal-year {kind.replace('_', ' ')} statement. Give the 10-K whose fiscal year the 10-Q continues instead.` | No | Yes |  |
| `ltm.py:103` | `'{quarter_name}' prints no prior year to date beside its current one, so LTM can't be built. Compare the 10-Q on its own instead.` | No | Yes |  |
| `ltm.py:126` | `'{quarter_name}' reports in {q_read.document_currency} and '{annual_name}' in {k_read.document_currency}; LTM adds them, so give two filings in one currency.` | No | Yes |  |
| `ltm.py:129` | `'{quarter_name}' reports its amounts in {currency}. This tool reports in USD, EUR or GBP only and converts no currency. Use filings that report in one of those to build LTM.` | No | Yes |  |
| `ltm.py:136` | `'{name}' ({concept}) is in '{quarter_name}' but not in '{annual_name}', so LTM can't be built line by line without changing a total. Compare the 10-Q on its own instead.` | No | Yes |  |
| `ltm.py:140` | `'{name}' ({concept}) is in '{annual_name}' but not in '{quarter_name}', so LTM can't be built line by line without changing a total. Compare the 10-Q on its own instead.` | No | Yes |  |
| `ltm.py:154` | `'{name}' reads as {str(row.get('type')).lower()} in '{quarter_name}' but as {str(k_row.get('type')).lower()} in '{annual_name}', so LTM can't add them. Compare the 10-Q on its own instead.` | No | Yes |  |

### `metrics.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `metrics.py:58` | `not valid JSON ({exc}).` | No | **No** | a clause another message completes |
| `metrics.py:61` | `expected {"metrics": [ ... ]} with at least one metric.` | No | **No** | a clause another message completes |
| `metrics.py:65` | `each metric needs a name.` | No | **No** | a clause another message completes |
| `metrics.py:69` | `unknown key '{unknown[0]}' in metric '{name}'.` | No | **No** | a clause another message completes |
| `metrics.py:71` | `metric '{name}' appears twice.` | No | **No** | a clause another message completes |
| `metrics.py:75` | `measure must be Currency or Multiple (metric '{name}').` | No | **No** | a clause another message completes |
| `metrics.py:78` | `better must be Higher or Lower (metric '{name}').` | No | **No** | a clause another message completes |
| `metrics.py:85` | `{key} must be a non-empty list of terms (metric '{metric}'). List at least one term for it in the metrics file.` | No | Yes |  |
| `metrics.py:91` | `unknown key '{extra[0]}' in a term of metric '{metric}'.` | No | **No** | a clause another message completes |
| `metrics.py:94` | `each term names a concept or a label, not both (metric '{metric}').` | No | **No** | a clause another message completes |
| `metrics.py:96` | `statement must be income, balance_sheet or cash_flow (metric '{metric}').` | **Yes** | **No** | a clause another message completes; snake_case 'balance_sheet' |
| `metrics.py:98` | `period must be instant, fy, ytd or ltm (metric '{metric}').` | No | **No** | a clause another message completes |
| `metrics.py:100` | `sign must be 1 or -1 (metric '{metric}').` | No | **No** | a clause another message completes |
| `metrics.py:126` | `The filings report in {' and '.join(codes)}; a metric adds their figures, so give filings in one currency.` | No | Yes |  |
| `metrics.py:130` | `'{primary_name}' reports its amounts in {self.currency}. This tool reports in USD, EUR or GBP only and converts no currency. Use filings that report in one of those.` | No | Yes |  |
| `metrics.py:154` | `the {_STATEMENTS[term.statement]} statement of '{document}' couldn't be read: {read.fatal_error_message}` | No | **No** | a clause another message completes |
| `metrics.py:161` | `no line {named} on the {_STATEMENTS[term.statement]} statement for {term.period}, so it can't be computed` | No | **No** | a clause another message completes |
| `metrics.py:164` | `more than one line {named} on the {_STATEMENTS[term.statement]} statement, so the term is ambiguous` | No | **No** | a clause another message completes |
| `metrics.py:173` | `a balance sheet line takes period instant, and only a balance sheet line does` | No | **No** | a clause another message completes |
| `metrics.py:179` | `'{line['line_item']}' prints no figure in that column of '{document}'` | No | **No** | a clause another message completes |
| `metrics.py:190` | `'{primary}' has no balance sheet` | No | **No** | a clause another message completes |
| `metrics.py:199` | `'{document}' has no {which} {_STATEMENTS[term.statement]} statement` | No | **No** | a clause another message completes |
| `metrics.py:204` | `an ltm term needs --ltm-from with the 10-K` | **Yes** | **No** | a clause another message completes; flag --ltm-from |
| `metrics.py:208` | `LTM needs the {_STATEMENTS[term.statement]} statement for the fiscal year and both years to date` | No | **No** | a clause another message completes |
| `metrics.py:218` | `'{line['line_item']}' is a cash balance, which doesn't add across periods, so it can't be an LTM term` | No | **No** | a clause another message completes |
| `metrics.py:313` | `No metric could be computed. Check that each metric names figures the filing reports. {' '.join((f'{n}.' for n in notes))}` | No | Yes |  |

### `parsing.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `parsing.py:47` | `{line_item}: field '{field}' must be a finite number.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:49` | `{line_item}: field '{field}' exceeds the supported numeric length.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:64` | `{line_item}: required field '{field}' is missing.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:66` | `{line_item}: field '{field}' must be numeric, not boolean.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:72` | `{line_item}: field '{field}' must be a numeric scalar.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:74` | `{line_item}: field '{field}' exceeds the supported numeric length.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:77` | `{line_item}: required field '{field}' is missing.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:84` | `{line_item}: field '{field}' must be a finite number.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:87` | `{line_item}: field '{field}' has an invalid numeric format: {value!r}.` | **Yes** | **No** | re-check of a value already read (API); repr quoting |
| `parsing.py:91` | `{line_item}: field '{field}' currency {code} conflicts with reporting currency {currency}; no FX conversion is performed.` | No | **No** | re-check of a value already read (API) |
| `parsing.py:98` | `{line_item}: field '{field}' is not numeric: {value!r}.` | **Yes** | **No** | re-check of a value already read (API); repr quoting |
| `parsing.py:118` | `Columns {seen[key]!r} and {original!r} normalize to the same key {key!r}.` | **Yes** | **No** | strict reader (command line and API); repr quoting; word 'normalize' |
| `parsing.py:125` | `Dataset exceeds the supported column count ({MAX_COLUMNS}).` | No | **No** | strict reader (command line and API) |
| `parsing.py:131` | `Each row must be an object with named columns.` | No | **No** | strict reader (command line and API) |
| `parsing.py:133` | `Row exceeds the supported column count ({MAX_COLUMNS}).` | No | **No** | strict reader (command line and API) |
| `parsing.py:142` | `Row data appears under a blank column header.` | No | **No** | strict reader (command line and API) |
| `parsing.py:145` | `Columns {originals[key]!r} and {original!r} normalize to the same key {key!r}.` | **Yes** | **No** | strict reader (command line and API); repr quoting; word 'normalize' |
| `parsing.py:162` | `CSV input has no header row.` | No | **No** | strict reader (command line and API) |
| `parsing.py:169` | `CSV row {reader.line_num}: column count does not match header.` | No | **No** | strict reader (command line and API) |
| `parsing.py:171` | `CSV row {reader.line_num}: data appears under a blank header.` | No | **No** | strict reader (command line and API) |
| `parsing.py:174` | `CSV exceeds the supported row or cell count.` | No | **No** | strict reader (command line and API) |
| `parsing.py:182` | `Duplicate JSON key: '{key}'.` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:200` | `JSON exceeds the supported value count.` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:210` | `JSON nesting exceeds the supported depth.` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:215` | `JSON constant '{value}' is not a finite number.` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:225` | `JSON nesting exceeds the supported depth.` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:234` | `JSON input contains both 'rows' and 'data'; supply one dataset.` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:237` | `JSON input must be a list of row objects or contain a 'rows'/'data' list.` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:239` | `Every JSON row must be an object.` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:241` | `Dataset exceeds the supported row count ({MAX_ROWS}).` | No | n/a | shown after "Could not read JSON data ..." |
| `parsing.py:249` | `Excel input requires the optional dependency: pip install 'variance-analysis-agent[excel]'` | No | **No** | a clause another message completes |
| `parsing.py:259` | `HTML filings are read with --assisted, which finds the financial statements in the filing and lists every adjustment it makes.` | **Yes** | **No** | strict reader (command line and API); flag --assisted |
| `parsing.py:266` | `PDF files are read with --assisted, which finds the financial statements in the filing and lists every adjustment it makes.` | **Yes** | **No** | strict reader (command line and API); flag --assisted |
| `parsing.py:273` | `Tab-separated files are read with --assisted, which detects the delimiter and lists every adjustment it makes.` | **Yes** | **No** | strict reader (command line and API); flag --assisted |
| `parsing.py:279` | `Unsupported input format '{suffix}'. Use CSV, JSON, XLSX, XLSM or XLS; with --assisted, also TSV, PDF or an EDGAR .htm filing.` | **Yes** | Yes | strict reader (command line and API); flag --assisted |
| `parsing.py:294` | `Input exceeds the supported size (32 MiB).` | No | **No** | strict reader (command line and API) |
| `parsing.py:322` | `Worksheet selection requires XLSX or XLSM input.` | No | **No** | strict reader (command line and API) |
| `parsing.py:324` | `Worksheet name must be text.` | No | **No** | strict reader (command line and API) |
| `parsing.py:347` | `Worksheet {sheet!r} was not found; supply an exact --sheet name.` | **Yes** | Yes | strict reader (command line and API); repr quoting; flag --sheet |
| `parsing.py:350` | `Excel input has no active worksheet.` | No | **No** | strict reader (command line and API) |
| `parsing.py:359` | `Excel input is empty.` | No | **No** | strict reader (command line and API) |
| `parsing.py:373` | `Excel row {row_number}: data appears under a blank header beyond the header row.` | No | **No** | strict reader (command line and API) |
| `parsing.py:377` | `Excel row {row_number}: data appears under a blank header.` | No | **No** | strict reader (command line and API) |
| `parsing.py:393` | `Invalid Excel workbook {source_name!r}: {exc}` | **Yes** | **No** | strict reader (command line and API); repr quoting |
| `parsing.py:397` | `Unsupported input format '{suffix}'. Use CSV, JSON, XLSX, or XLSM.` | No | Yes | strict reader (command line and API) |

### `pdf_tables.py`

| Source | Message Text | Jargon? | Offers Fix? | Notes / Jargon Rationale |
|---|---|---|---|---|
| `pdf_tables.py:197` | `PDF files require the optional PDF tools. Please install with: pip install 'variance-analysis-agent[pdf]'` | No | Yes | a clause another message completes |
| `pdf_tables.py:215` | `Reading '{filename}' took too long. Save just the financial statement pages as a new PDF and upload that.` | No | Yes |  |
| `pdf_tables.py:234` | `'{filename}' has {page_count} pages, more than the {max_pages} we can read at once. Save just the financial statement pages as a new PDF and upload that.` | No | Yes |  |
| `pdf_tables.py:254` | `'{filename}' looks like a scanned image, so there is no text to read. Export the statement to Excel or CSV, or use a PDF saved from the filing itself, not a scan.` | No | Yes |  |
| `pdf_tables.py:295` | `We couldn't find an income statement, balance sheet or cash flow statement in '{filename}'. Export the statement to Excel or CSV and upload that instead.` | No | Yes |  |
| `pdf_tables.py:305` | `The PDF reader returned a word without a position. Export the statement to Excel or CSV and upload that instead.` | No | Yes |  |
