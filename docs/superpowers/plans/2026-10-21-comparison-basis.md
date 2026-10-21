# Comparison Basis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let one run compare Actual against Budget, Forecast, or Prior Period, detected from headers or chosen explicitly, with report, audit, chat, and commentary naming the comparison truthfully.

**Architecture:** `AnalysisConfig` carries a `ComparisonBasis` plus an optional display label. A new `comparison.py` module owns the vocabulary (synonyms, wording, period ordering) that intake, analysis, report, audit, CLI, and chat all share. Internally `budget` keeps meaning "the comparison amount", so the arithmetic in `analysis.py` does not change. Only the zero-comparison label depends on the basis.

**Tech Stack:** Python 3.11+, stdlib `decimal`/`dataclasses`/`enum`, pytest, jsonschema (tests), ruff, mypy --strict.

**Spec:** `docs/superpowers/specs/2026-10-21-comparison-basis-design.md`

## Prerequisite

Phase 2 intake work (currently uncommitted on `intake/phase-2-real-ledgers`) must be committed first. Create the feature branch `feat/comparison-basis` from that commit. The line numbers below are from the working tree on 2026-10-21 and are approximate.

## Global Constraints

- No new runtime dependencies. Must pass `mypy --strict` (no explicit or unimported `Any`) and `ruff check .`.
- Budget runs are byte-identical to today: every existing report golden, audit fixture, and test passes unchanged, except `tests/test_intake.py:53` and `tests/test_audit_schema_15.py::test_schema_15_is_supported_and_current`, which Tasks 5 and 3 update deliberately.
- `ComparisonBasis` values are `"budget"`, `"forecast"`, `"prior_period"`. CLI values are `budget`, `forecast`, `prior-period`.
- Zero-comparison labels: `N/A (Unbudgeted)` for Budget, `N/A (Not in forecast)` for Forecast, `N/A (New this period)` for Prior Period.
- Basis nouns: `budget`, `forecast`, `prior period`.
- One comparison per run. Intake never chooses between candidates of different bases.
- `budget` JSON keys keep their names. Pre-1.6 audit schemas are refused for non-Budget runs.

## Review Focus

1. **Excel year headers stored as numbers** (cell value `2025`, not `"2025"`) must be detected like text years. Test: Task 5, `test_numeric_year_headers_from_excel`.
2. **Two Actual columns for different years** (`FY2025 Actual`, `FY2024 Actual`) must become a Prior Period comparison, not first-match-wins. Test: Task 5, `test_two_dated_actual_columns_are_prior_period`.
3. **Two-digit and mixed fiscal-year spellings** (`FY24`, `FY2025`, `2023`) must order correctly. Test: Task 1, `test_order_period_labels_mixed_year_spellings`.
4. **`--commentary` text saying "budget"** on a non-Budget run. Test: Task 4, `test_commentary_uses_basis_noun`.
5. **Switching comparison in chat after an analysis already ran** ("compare to last year") must re-read the source with the new basis, not reuse the budget-mapped rows. Test: Task 7, `test_chat_switch_comparison_rereads_source`.

---

### Task 1: Comparison vocabulary and config fields

**Files:**
- Modify: `src/variance_agent/models.py` (add enum; `AnalysisConfig` at ~line 22)
- Create: `src/variance_agent/comparison.py`
- Test: `tests/test_comparison_basis.py`

**Interfaces:**
- Produces (in `models.py`):
  - `class ComparisonBasis(StrEnum)`: `BUDGET = "budget"`, `FORECAST = "forecast"`, `PRIOR_PERIOD = "prior_period"`
  - `AnalysisConfig.comparison_basis: ComparisonBasis = ComparisonBasis.BUDGET`
  - `AnalysisConfig.comparison_label: str | None = None` (appended after `currency`)
- Produces (in `comparison.py`):
  - `BUDGET_SYNONYMS`, `FORECAST_SYNONYMS`, `PRIOR_PERIOD_SYNONYMS: frozenset[str]`. These are normalized header forms. Budget = the current `intake._BUDGET_SYNONYMS` set. Forecast = `{"forecast", "fcst", "outlook", "projection", "projected"}`. Prior = `{"prior_year", "py", "last_year", "prior_period"}`.
  - `basis_for_header(normalized: str) -> ComparisonBasis | None`
  - `parse_compare_to(value: str) -> ComparisonBasis`: accepts `budget`/`forecast`/`prior-period`, case-insensitive. Raises `ValueError` otherwise.
  - `basis_noun(basis: ComparisonBasis) -> str`
  - `comparison_heading(basis: ComparisonBasis, label: str | None) -> str`
  - `zero_comparison_label(basis: ComparisonBasis) -> str`
  - `parse_period_label(text: str) -> tuple[int, str, int] | None`: returns (year, granularity, index)
  - `order_period_labels(labels: list[str]) -> list[str] | None`: newest first, or None
  - `comparison_statement(basis: ComparisonBasis, label: str | None, actual_label: str | None, all_periods: list[str] | None = None) -> str`
  - `select_strict_comparison(rows: list[dict[str, object]], basis: ComparisonBasis) -> list[dict[str, object]]`

- [ ] **Step 1: Write the failing tests**

```python
def test_config_defaults_to_budget():
    cfg = AnalysisConfig(period="Q3", dollar_threshold=Decimal("1"), percent_threshold=Decimal("0.05"))
    assert cfg.comparison_basis is ComparisonBasis.BUDGET and cfg.comparison_label is None

@pytest.mark.parametrize("header,basis", [("budget", B), ("plan", B), ("forecast", F), ("fcst", F),
    ("outlook", F), ("prior_year", P), ("py", P), ("last_year", P), ("actual", None), ("fy2025", None)])
def test_basis_for_header(header, basis): assert basis_for_header(header) is basis

def test_parse_compare_to():
    assert parse_compare_to("Prior-Period") is P
    with pytest.raises(ValueError): parse_compare_to("prior_year")

def test_wording():
    assert [basis_noun(b) for b in (B, F, P)] == ["budget", "forecast", "prior period"]
    assert comparison_heading(B, "FY2025") == "Budget"
    assert comparison_heading(F, None) == "Forecast"
    assert comparison_heading(P, "FY2024") == "Prior Period (FY2024)"
    assert [zero_comparison_label(b) for b in (B, F, P)] == [
        "N/A (Unbudgeted)", "N/A (Not in forecast)", "N/A (New this period)"]

def test_order_period_labels_mixed_year_spellings():
    assert order_period_labels(["FY24", "FY2025", "2023"]) == ["FY2025", "FY24", "2023"]
    assert order_period_labels(["Q2 2025", "Q3 2025"]) == ["Q3 2025", "Q2 2025"]
    assert order_period_labels(["Aug 2025", "Sep 2025", "2025-07"]) == ["Sep 2025", "Aug 2025", "2025-07"]
    assert order_period_labels(["FY2025", "Q3 2024"]) is None   # mixed granularity
    assert order_period_labels(["Q3", "Q2"]) is None            # no year
    assert order_period_labels(["FY2025", "FY2025"]) is None    # duplicate

def test_comparison_statement():
    assert comparison_statement(P, "FY2024", "FY2025") == "Comparing FY2025 against FY2024 (prior period)."
    assert comparison_statement(P, "FY2024", "FY2025", ["FY2025", "FY2024", "FY2023"]) == (
        "Found FY2025, FY2024, FY2023 — comparing FY2025 against FY2024.")
    assert comparison_statement(F, None, None) == "Comparing Actual against the forecast."

def test_select_strict_comparison():
    rows = [{"line_item": "A", "budget": "1", "forecast": "2", "actual": "3"}]
    assert select_strict_comparison(rows, B) is rows
    assert select_strict_comparison(rows, F) == [{"line_item": "A", "budget": "2", "actual": "3"}]
    with pytest.raises(ValueError, match="No prior period column"):
        select_strict_comparison(rows, P)
    with pytest.raises(ValueError, match="more than one forecast column"):
        select_strict_comparison([{"line_item": "A", "forecast": "1", "fcst": "2", "actual": "3"}], F)
```

(`B`, `F`, `P` are module-level aliases for the three enum members.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_comparison_basis.py -v`
Expected: FAIL with an ImportError for `ComparisonBasis` / `variance_agent.comparison`.

- [ ] **Step 3: Implement the enum, the config fields, and `comparison.py`**

`parse_period_label` recognizes these forms, case-insensitive, with an optional ` Actual`/` Actuals` suffix stripped first:
- `FY2025`, `FY25`, `2025` → `(year, "year", 0)`
- `Q3 2025`, `Q3-25` → `(year, "quarter", 3)`
- `Sep 2025`, `September 2025` → `(year, "month", 9)`
- `2025-09` → `(year, "month", 9)`

Two-digit years map to `2000 + yy`.

`order_period_labels` returns None when: any label fails to parse, granularities differ, or two labels parse to the same tuple. Otherwise it sorts by `(year, index)` descending and returns the original label text.

`select_strict_comparison` returns `rows` unchanged for BUDGET. For other bases, the error messages are:
- `"No {noun} column found. Columns found: {sorted keys}."`
- `"Found more than one {noun} column ({keys}); keep one and rerun."`

Otherwise it moves the single matching key's value to `budget` and removes every `BUDGET_SYNONYMS` key. It checks all rows' keys, not just the first row.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_comparison_basis.py -v && python -m mypy --strict src/variance_agent`
Expected: PASS; mypy reports no issues.

- [ ] **Step 5: Commit**

```bash
git add src/variance_agent/models.py src/variance_agent/comparison.py tests/test_comparison_basis.py
git commit -m "feat(comparison): add ComparisonBasis and shared comparison vocabulary"
```

---

### Task 2: Basis-aware zero-comparison label in analysis

**Files:**
- Modify: `src/variance_agent/analysis.py` (`_percent_variance` ~147, `_aggregate` ~317, `_verify_result` ~341, `analyze_rows` ~414)
- Test: `tests/test_comparison_basis.py`

**Interfaces:**
- Consumes: `ComparisonBasis`, `zero_comparison_label`, `AnalysisConfig.comparison_label` (Task 1)
- Produces: `_percent_variance(budget: Decimal, actual: Decimal, basis: ComparisonBasis) -> tuple[Decimal | None, str | None]`. `analyze_rows` validates `comparison_basis` (an `isinstance` check, ValueError otherwise) and `comparison_label` (`validate_text(..., field="comparison_label", nonblank=True)` when not None).

- [ ] **Step 1: Write the failing tests**

```python
ROWS = [{"line_item": "New Revenue", "type": "Revenue", "budget": "0", "actual": "200"},
        {"line_item": "Rent Expense", "type": "Expense", "budget": "100", "actual": "130"}]

@pytest.mark.parametrize("basis,label", [(B, "N/A (Unbudgeted)"), (F, "N/A (Not in forecast)"),
                                         (P, "N/A (New this period)")])
def test_zero_comparison_label_follows_basis(basis, label):
    result = analyze_rows(ROWS, _cfg(basis))
    assert result.rows[0].percent_label == label
    assert result.revenue.percent_label == label        # aggregate with zero comparison

def test_numbers_identical_across_bases():
    key = lambda r: [(x.variance_dollars, x.variance_percent, x.status, x.material) for x in r.rows]
    results = [analyze_rows(ROWS, _cfg(b)) for b in ComparisonBasis]
    assert key(results[0]) == key(results[1]) == key(results[2])

def test_blank_comparison_label_rejected():
    with pytest.raises(ValueError): analyze_rows(ROWS, _cfg(P, label="  "))
```

(`_cfg(basis, label=None, *, period="FY2025", dollar_threshold=Decimal("10"))` builds `AnalysisConfig(period=period, dollar_threshold=dollar_threshold, percent_threshold=Decimal("0.05"), comparison_basis=basis, comparison_label=label)`. It lives in `tests/conftest.py` so Tasks 3–4 reuse it, and `ROWS` lives there too.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_comparison_basis.py -k "zero_comparison or identical or blank_comparison" -v`
Expected: FAIL. The Forecast/Prior cases still return `N/A (Unbudgeted)`, and the blank-label case raises nothing.

- [ ] **Step 3: Thread `config.comparison_basis` into `_percent_variance`, `_aggregate`, and `_verify_result`; add the validation to `analyze_rows`**

`verify_result` must recompute with `result.config.comparison_basis` so reverification matches.

- [ ] **Step 4: Run the tests to verify they pass, plus the full suite**

Run: `python -m pytest -q`
Expected: all pass, including the existing Fraction-oracle tests and zero-budget goldens.

- [ ] **Step 5: Commit**

```bash
git add src/variance_agent/analysis.py tests/test_comparison_basis.py
git commit -m "feat(analysis): label zero comparison amounts by comparison basis"
```

---

### Task 3: Audit schema 1.6

**Files:**
- Modify: `src/variance_agent/audit.py` (version constants ~18; version sets in `build_audit_record`)
- Create: `schemas/audit-1.6.schema.json` (copy of 1.5 plus `comparison`)
- Modify: `tests/test_audit_schema_15.py` (the current-version assertion only)
- Test: `tests/test_audit_schema_16.py`

**Interfaces:**
- Consumes: `AnalysisConfig.comparison_basis/comparison_label` (Task 1)
- Produces:
  - `CURRENT_SCHEMA_VERSION = "1.6"`; `"1.6"` is appended to `SUPPORTED_SCHEMA_VERSIONS`.
  - For 1.6, `record["comparison"]` and `config_identity["comparison"]` both equal `{"basis": str(basis), "label": label}`.
  - 1.6 includes everything 1.5 does (diagnostics, worksheet, provenance, transformations).

- [ ] **Step 1: Write the failing tests**

```python
def test_16_is_current(): assert CURRENT_SCHEMA_VERSION == "1.6" and "1.5" in SUPPORTED_SCHEMA_VERSIONS

@pytest.mark.parametrize("basis", list(ComparisonBasis))
def test_16_records_comparison_and_validates(basis):
    record = build_audit_record(analyze_rows(ROWS, _cfg(basis, label="FY2024")), schema_version="1.6")
    assert record["comparison"] == {"basis": basis.value, "label": "FY2024"}
    _validator("1.6").validate(record)

def test_basis_changes_fingerprint_and_config_hash():
    a = build_audit_record(analyze_rows(ROWS, _cfg(B)), schema_version="1.6")
    b = build_audit_record(analyze_rows(ROWS, _cfg(P)), schema_version="1.6")
    assert a["analysis_fingerprint"] != b["analysis_fingerprint"]
    assert a["provenance"]["configuration_sha256"] != b["provenance"]["configuration_sha256"]

@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2", "1.3", "1.4", "1.5"])
def test_old_schema_refused_for_non_budget(version):
    with pytest.raises(ValueError, match="use --audit-schema-version 1.6"):
        build_audit_record(analyze_rows(ROWS, _cfg(F)), schema_version=version)

def test_old_schema_still_allowed_for_budget():
    build_audit_record(analyze_rows(ROWS, _cfg(B)), schema_version="1.5")

def test_16_schema_rejects_unknown_basis():
    record = build_audit_record(analyze_rows(ROWS, _cfg(B)), schema_version="1.6")
    record["comparison"]["basis"] = "stretch_target"
    with pytest.raises(ValidationError): _validator("1.6").validate(record)
```

Update `test_schema_15_is_supported_and_current` so it asserts only that `"1.5" in SUPPORTED_SCHEMA_VERSIONS`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_audit_schema_16.py -v`
Expected: FAIL (`CURRENT_SCHEMA_VERSION` is `"1.5"`; the schema file is missing).

- [ ] **Step 3: Implement it in `audit.py` and the schema**

Refusal message: `"Audit schema {version} records the comparison amount as a budget; use --audit-schema-version 1.6 for forecast or prior-period comparisons."` The check runs before any record is built.

In the schema, `comparison` is required: `basis` is an enum of the three values, and `label` is a string (minLength 1) or null. Each `budget` property description reads "The comparison amount (budget, forecast, or prior period per `comparison.basis`)." `additionalProperties: false` is preserved.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -q`
Expected: all pass. `tests/test_contract_fixtures.py` validates 1.6 through its per-version loop.

- [ ] **Step 5: Commit**

```bash
git add src/variance_agent/audit.py schemas/audit-1.6.schema.json tests/test_audit_schema_15.py tests/test_audit_schema_16.py
git commit -m "feat(audit): schema 1.6 records comparison basis; refuse older schemas for non-budget runs"
```

---

### Task 4: Report and commentary wording

**Files:**
- Modify: `src/variance_agent/report.py` (`_bottom_line` ~111, `_driver_sentence` ~155, `render_markdown` ~216)
- Modify: `deterministic_conditioning/variance_bridge.py`, `deterministic_conditioning/financial_commentary.py` (~lines 132, 139)
- Create: `tests/fixtures/contracts/forecast.report.md`, `tests/fixtures/contracts/prior_period.report.md`
- Test: `tests/test_comparison_report.py`

**Interfaces:**
- Consumes: `comparison_heading`, `basis_noun` (Task 1); basis-aware labels (Task 2)
- Produces: user-visible text only.
  - Table column: `comparison_heading(...)`.
  - Executive Summary gets `- Compared Against: {heading}` right after the Reporting Currency line, for non-Budget runs only.
  - `_bottom_line` direction text: `above/below/in line with {noun}`.
  - Driver mismatch text: `"... do not reconcile to {heading}/Actual."`

- [ ] **Step 1: Write the failing tests**

```python
PRIOR_ROWS = [  # same values as fixture_j's FY2025 vs FY2024 columns (Task 5)
    {"line_item": "Product Revenue", "type": "Revenue", "budget": "100000", "actual": "120000"},
    {"line_item": "Cost of Revenue", "type": "Expense", "budget": "45000", "actual": "50000"},
    {"line_item": "Operating Expenses", "type": "Expense", "budget": "32000", "actual": "30000"},
    {"line_item": "New Segment Revenue", "type": "Revenue", "budget": "0", "actual": "5000"}]

def test_prior_period_report_matches_golden():
    text = render_markdown(analyze_rows(PRIOR_ROWS, _cfg(P, "FY2024", period="FY2025")))
    assert text == (CONTRACTS / "prior_period.report.md").read_text(encoding="utf-8")
    assert "budget" not in text.lower()
    assert "| Line Item | Type | Prior Period (FY2024) | Actual |" in text
    assert "- Compared Against: Prior Period (FY2024)" in text
    assert "N/A (New this period)" in text

def test_forecast_report_matches_golden(): ...  # same shape, FORECAST rows from fixture_k, label None

def test_budget_report_has_no_compared_against_line():
    assert "Compared Against" not in render_markdown(analyze_rows(PRIOR_ROWS, _cfg(B)))

def test_commentary_uses_basis_noun():
    text, _ = generate_verified_commentary(analyze_rows(PRIOR_ROWS, _cfg(P, "FY2024")))
    assert "budget" not in text.lower()
```

Both goldens use `_cfg(..., dollar_threshold=Decimal("1000"))` (5% percent threshold). The forecast golden uses fixture_k's rows with `period="Q3 2026"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_comparison_report.py -v`
Expected: FAIL (the goldens are missing, and the header still says `Budget`).

- [ ] **Step 3: Implement the wording**

For BUDGET, every string stays byte-identical. Thread `basis_noun(result.config.comparison_basis)` from `generate_verified_commentary` into the two commentary sentences. For Budget they keep their current text; otherwise "budget limits" → "the {noun}" and "original budget projections" → "the {noun}".

- [ ] **Step 4: Generate the goldens and review them by hand**

Write a throwaway script in the scratchpad that renders `render_markdown(analyze_rows(rows, cfg))` for each golden case (the exact rows and config from the tests) to `tests/fixtures/contracts/prior_period.report.md` and `forecast.report.md`. Do not commit the script. Read both files and confirm: no "budget" anywhere, the headings are correct, `N/A (New this period)` / `N/A (Not in forecast)` appear where the comparison amount is zero, and the net impact sentence says "prior period" / "forecast".

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest -q`
Expected: all pass, with all existing goldens unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/variance_agent/report.py deterministic_conditioning tests/test_comparison_report.py tests/fixtures/contracts/forecast.report.md tests/fixtures/contracts/prior_period.report.md
git commit -m "feat(report): name the comparison basis in reports and commentary"
```

---

### Task 5: Intake detection

**Files:**
- Modify: `src/variance_agent/intake.py` (`match_column_synonym` ~234, `detect_header_row` ~651, `IntakeResult` ~151, `read_input_assisted` ~767, `_read_tsv_text`/`_read_csv_text`/`_read_excel_bytes`/`_read_json_bytes`, `_process_raw_table` ~937)
- Modify: `tests/fixtures/realworld/build_fixtures.py`; generate the fixtures below
- Modify: `tests/test_intake.py:53` (the forecast note no longer exists)
- Test: `tests/test_intake_comparison.py`

**Interfaces:**
- Consumes: synonyms, `basis_for_header`, `order_period_labels`, `parse_period_label`, `comparison_statement`, `select_strict_comparison` (Task 1)
- Produces:
  - `@dataclass(frozen=True) class ComparisonDetection`: `basis: ComparisonBasis | None` (None = stop and ask), `label: str | None`, `comparison_column: int | None`, `actual_column: int | None`, `candidates: tuple[str, ...]`, `message: str`
  - `detect_comparison_columns(header_cells: list[object], compare_to: ComparisonBasis | None) -> ComparisonDetection`
  - `IntakeResult` new fields: `comparison_basis: ComparisonBasis = ComparisonBasis.BUDGET`, `comparison_label: str | None = None`, `comparison_candidates: list[str] = field(default_factory=list)`
  - `read_input_assisted(..., compare_to: ComparisonBasis | None = None)`, threaded to every reader

Fixtures, with exact contents (all `Line Item,Type,...`):
- `fixture_j_10k_three_years.csv`: `FY2025,FY2024,FY2023`. Rows: Product Revenue 120000/100000/90000; Cost of Revenue 50000/45000/40000; Operating Expenses 30000/32000/28000; New Segment Revenue 5000/0/0.
- `fixture_k_forecast.csv`: `Forecast,Actual`. Rows: Subscription Revenue 110000/115500; Payroll Expense 65000/68000.
- `fixture_l_budget_and_forecast.csv`: `Budget,Forecast,Actual`. Rows: Subscription Revenue 100000/110000/115500; Payroll Expense 60000/65000/68000.
- `fixture_m_years_reversed.csv`: `2024,2025`. Rows: Product Revenue 100000/120000; Cost of Revenue 45000/50000.
- `fixture_n_numeric_years.xlsx`: header cells are the integers `2025`, `2024`, with fixture_m's values swapped into that column order.

- [ ] **Step 1: Write the failing tests**

```python
def test_forecast_column_detected():
    res = _read("fixture_k_forecast.csv")
    assert (res.comparison_basis, res.comparison_label) == (F, None)
    assert res.rows[0]["budget"] == Decimal("110000")
    assert "Comparing Actual against the forecast." in res.visible_transformations

def test_10k_three_years_compares_newest_two():
    res = _read("fixture_j_10k_three_years.csv")
    assert (res.comparison_basis, res.comparison_label) == (P, "FY2024")
    assert res.rows[0]["actual"] == Decimal("120000") and res.rows[0]["budget"] == Decimal("100000")
    assert "Found FY2025, FY2024, FY2023 — comparing FY2025 against FY2024." in res.visible_transformations

def test_reversed_year_columns(): ...      # fixture_m: actual is the 2025 column, label "2024"
def test_numeric_year_headers_from_excel(): ...  # fixture_n gives the same result as fixture_m

def test_two_dated_actual_columns_are_prior_period():
    res = _read_text("Line Item,Type,FY2025 Actual,FY2024 Actual\nRent Expense,Expense,130,100\n")
    assert (res.comparison_basis, res.comparison_label) == (P, "FY2024")
    assert res.rows[0]["actual"] == Decimal("130")

def test_budget_and_forecast_stops_and_asks():
    res = _read("fixture_l_budget_and_forecast.csv")
    assert res.has_fatal_errors and res.comparison_candidates == ["Budget", "Forecast"]
    assert "Budget" in res.fatal_error_message and "Forecast" in res.fatal_error_message

def test_compare_to_resolves_ambiguity():
    res = _read("fixture_l_budget_and_forecast.csv", compare_to=F)
    assert res.comparison_basis is F and res.rows[0]["budget"] == Decimal("110000")

def test_compare_to_missing_basis_errors():
    res = _read("fixture_k_forecast.csv", compare_to=P)
    assert res.has_fatal_errors and "No prior period column found" in res.fatal_error_message

def test_unorderable_periods_stop():
    res = _read_text("Line Item,Type,FY2025,Q3 2024\nRent Expense,Expense,1,2\n")
    assert res.has_fatal_errors and "FY2025" in res.fatal_error_message

def test_plain_budget_file_unchanged():
    res = _read_sample("examples/sample_variance.csv")
    assert res.comparison_basis is B and not any("Comparing" in t for t in res.visible_transformations)

def test_json_compare_to_forecast(): ...   # JSON rows with "forecast" key + compare_to=F map to budget
```

(Helpers: `_read(name, compare_to=None)` reads `FIXTURES_DIR / name` via `read_input_assisted(bytes, suffix, filename=name, compare_to=compare_to)`; `_read_text(csv, compare_to=None)` does the same for inline CSV text with suffix `.csv`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_intake_comparison.py -v`
Expected: FAIL (`compare_to` is an unexpected keyword; the fields are missing).

- [ ] **Step 3: Implement the detection**

The decision order in `detect_comparison_columns`:
1. **Named candidates.** These are cells where `basis_for_header(normalize_header(str(cell)))` is not None.
   - With `compare_to`, keep only that basis: zero matches → `"No {noun} column found. Columns found: {headers}."`; more than one → ask.
   - Without `compare_to`, more than one distinct basis → ask, with message `"This file has more than one column to compare against ({headers}). Which should Actual be compared against?"`.
   - Exactly one → choose it. `actual_column` is the ACTUAL-role column.
2. **Period-only columns**, used only when step 1 found no candidates. These are cells whose text, after stripping an `Actual`/`Actuals` word, passes `parse_period_label`. Two or more are required. `order_period_labels` gives the order; None → ask (the message lists the labels). The newest is Actual and the next newest is the comparison, with `label` = that header's period text (the `Actual` word stripped). A `compare_to` other than PRIOR_PERIOD → the "No {noun} column" error.
3. Otherwise → BUDGET with no message. This is today's behaviour, and the wide-layout period pairs stay as they are.

`match_column_synonym` returns `(CanonicalRole.BUDGET, None)` for every comparison synonym; remove the `"forecast"` special case. `detect_header_row` gains the period-only fallback (step 2) when LINE_ITEM is present. `_process_raw_table` calls `detect_comparison_columns(header_row, compare_to)`, overrides `roles[BUDGET]`/`roles[ACTUAL]` with the chosen columns, adds the `message` to `visible_transformations` when the basis is non-BUDGET, and returns a fatal `IntakeResult` with `comparison_candidates` when `basis is None`. `has_transformations` is True for a non-BUDGET basis. `_read_json_bytes` applies `select_strict_comparison` when `compare_to` is non-BUDGET.

- [ ] **Step 4: Run the tests to verify they pass, plus the full suite**

Run: `python -m pytest -q`
Expected: all pass, including `test_realworld_intake_baseline.py` and the Phase 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/variance_agent/intake.py tests/fixtures/realworld tests/test_intake.py tests/test_intake_comparison.py
git commit -m "feat(intake): detect forecast and prior-period comparison columns"
```

---

### Task 6: CLI `--compare-to`

**Files:**
- Modify: `src/variance_agent/cli.py` (`Arguments` ~38, `build_parser` ~76, `_run` ~154–330)
- Test: `tests/test_cli_comparison.py`

**Interfaces:**
- Consumes: `parse_compare_to`, `select_strict_comparison` (Task 1); `read_input_assisted(compare_to=...)` and the `IntakeResult` comparison fields (Task 5); audit 1.6 (Task 3)
- Produces: `--compare-to {budget,forecast,prior-period}` (default None), `Arguments.compare_to: str | None`

- [ ] **Step 1: Write the failing tests**

```python
def test_strict_compare_to_forecast(tmp_path):   # fixture_l, strict mode
    assert main([str(L), *BASE, "--compare-to", "forecast", "-o", str(out)]) == 0
    assert "| Forecast | Actual |" in out.read_text()

def test_strict_without_compare_to_is_today(tmp_path): ...  # fixture_l strict → Budget column used

def test_assisted_detects_10k(tmp_path, capsys):
    assert main([str(J), *BASE, "--assisted", "-o", str(out), "--audit-json", str(audit)]) == 0
    assert "Comparing FY2025 against FY2024" in capsys.readouterr().err
    assert json.loads(audit.read_text())["comparison"] == {"basis": "prior_period", "label": "FY2024"}

def test_old_audit_schema_refused_exit_2(tmp_path, capsys):
    rc = main([str(K), *BASE, "--assisted", "--audit-json", str(audit), "--audit-schema-version", "1.5"])
    assert rc == 2 and "1.6" in capsys.readouterr().err and not audit.exists()

def test_compare_to_missing_column_exit_2(tmp_path, capsys):
    assert main([str(K), *BASE, "--compare-to", "prior-period", "--check-only"]) == 2
```

(`BASE = ["--period", "FY2025", "--dollar-threshold", "1000", "--percent-threshold", "5"]`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_cli_comparison.py -v`
Expected: FAIL (unrecognized argument `--compare-to`).

- [ ] **Step 3: Implement it**

Strict path: if `compare_to` is set, `parsed_rows = select_strict_comparison(parsed_rows, basis)`, with label None. Assisted and mapping paths: pass `compare_to` to `read_input_assisted`, and take basis and label from `intake_res`. Then pass both into `AnalysisConfig`. The audit refusal must happen before outputs are staged, so no partial files are left behind.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/variance_agent/cli.py tests/test_cli_comparison.py
git commit -m "feat(cli): add --compare-to and carry comparison basis into analysis"
```

---

### Task 7: Chat

**Files:**
- Modify: `src/variance_agent/chat/session.py` (`Session` ~38), `chat/intent.py`, `chat/handlers.py` (the `read_input_assisted` calls ~96/207/275/308/2775, `_run_analysis` ~679, result-describing handlers including `_handle_unbudgeted` ~2438), `chat/knowledge.py`
- Test: `tests/test_chat_comparison.py`

**Interfaces:**
- Consumes: Tasks 1, 5
- Produces:
  - `Session.compare_to: ComparisonBasis | None = None`
  - Intent `"set_comparison"`, matching "compare to (the) budget|forecast|prior year|last year|prior period". It sets `session.compare_to`, re-reads `session.source_bytes` through `read_input_assisted(compare_to=...)`, and re-runs the analysis.
  - Chips for an ambiguous file: `[f"Compare to {basis_noun(b)}" for b in candidate bases]`
  - Knowledge entry `"comparison_types"`, matching "what can I compare against", which explains the three bases and `--compare-to`

- [ ] **Step 1: Write the failing tests** (drive the session with the same upload-then-ask helpers `tests/test_chat.py` uses)

```python
def test_chat_forecast_session_never_says_budget():
    session = _upload("fixture_k_forecast.csv"); _configure(session)
    for prompt in ["summary", "top variances", "did expenses stay in budget?", "unbudgeted spend", "warnings"]:
        assert "budget" not in _ask(session, prompt).text.lower(), prompt

def test_chat_ambiguous_file_offers_chips():
    response = _upload_response("fixture_l_budget_and_forecast.csv")
    assert response.chips[:2] == ["Compare to budget", "Compare to forecast"]

def test_chat_switch_comparison_rereads_source():
    session = _upload("fixture_l_budget_and_forecast.csv"); _ask(session, "Compare to budget"); _configure(session)
    _ask(session, "compare to forecast")
    assert session.intake_result.comparison_basis is F
    assert session.parsed_rows[0]["budget"] == Decimal("110000")

def test_chat_explains_comparison_types():
    assert "prior period" in _ask(_new(), "what can I compare against?").text.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_chat_comparison.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement it**

`_run_analysis` builds `AnalysisConfig` with `comparison_basis`/`comparison_label` from `session.intake_result` (Budget when there is none). Replace the user-visible "budget" wording in handlers that describe results with `basis_noun(config.comparison_basis)`. `_handle_unbudgeted` uses its heading and its empty-state text. Leave the intake-stage blank-budget prompts and the general finance concept answers alone.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -q`
Expected: all pass, including `tests/test_chat.py` unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/variance_agent/chat tests/test_chat_comparison.py
git commit -m "feat(chat): choose and name the comparison basis in conversation"
```

---

### Task 8: Prompt, docs, and full verification

**Files:**
- Modify: `prompt/variance_report_prompt.md`, `README.md` (Input contract; schema 1.6 sentence), `docs/input-contract.md`, `docs/financial-rules.md`, `docs/audit-contract.md`, `CHANGELOG.md`

- [ ] **Step 1: Update the docs**
  - Prompt: read `comparison.basis`/`comparison.label`, and never call a forecast or prior period a budget.
  - README/input contract: comparison columns, period-only year layouts, `--compare-to`, and the note that detection runs in assisted intake while strict mode needs `--compare-to`.
  - Financial rules: the three zero-comparison labels.
  - Audit contract and CHANGELOG: schema 1.6 and the refusal rule. README sentence: "The current audit schema is 1.6."

- [ ] **Step 2: Run the README verification suite**

Run each command from the README "Verification" section (pytest, ruff, mypy --strict, compileall, pip check, build, twine check, check_distribution).
Expected: every command exits 0.

- [ ] **Step 3: Commit**

```bash
git add prompt README.md docs CHANGELOG.md
git commit -m "docs: document comparison basis and audit schema 1.6"
```
