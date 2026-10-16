# Audit Ledger (Variance-Analysis-Agent)

Audit baseline: `0880cf0bbb0d6c8a2a5a47d0614deec886e7bd7b` on `main`. Evidence locations in the table refer to that exact baseline, not to shifted lines in the patch. This audit covers this repository only.

The source is a deterministic Python CLI. There is no live LLM, tool-calling loop, web UI, provider SDK, or credential store. Runtime model schemas, network retries/timeouts, model token/step limits, PRNG isolation, and Monte Carlo statistics therefore have no active implementation to repair. No model client, speculative agent wrapper, mix model, dependency, or UI was added. The retained commentary prompt is a reference for consumers of already verified facts.

## Severity-ranked findings

| ID | Severity | file:line at baseline | Category | Root cause and reproduced evidence | Exact remediation and status |
|---|---|---|---|---|---|
| VA-01 | Critical | `src/variance_agent/parsing.py:249-276`, `:55-56` | Math | The workbook loader exposes numeric cells as binary floats before `Decimal(str(value))`. Stored Budget `9007199254740992.01` and Actual `9007199254740992.02` both became `9007199254740992.0`, erasing a cent of variance. | Preserve numeric XML text, keyed to physical cells, before library conversion. Use Decimal values for numeric cells while retaining library handling of strings/dates/formula caches. Regression verifies the exact cent. Fixed. |
| VA-02 | Critical | `src/variance_agent/parsing.py:217-220`, `:229-277`; `src/variance_agent/cli.py:114-115` | OWASP Agentic | Whole-file capture and ZIP/worksheet expansion had no byte, member, cell, or physical-coordinate bounds. A forged sparse coordinate or XML entity declaration reached the worksheet loader. | Bound captures, expanded archive content, member counts, physical rows/columns/cells; reject duplicate members, DTD/entities (including UTF-16), excessive XML depth, unordered/conflicting cells and malformed structures before loading. Inspect XML at alternative archive paths too. Inflated dimensions remain harmless. Fixed. |
| VA-03 | Major | `src/variance_agent/report.py:34-36`, `:54-68`, `:239-255` | Math | Independent two-place formatting breaks identities: two `0.005` actuals display as `0.00` each while total actual is `0.01`. | Choose a common report precision of at least two places that retains required fractional amounts; explicitly half-even quantize at that boundary and disclose additional precision. No account receives a fabricated penny adjustment. Fraction-oracle report properties reconcile every line and aggregate. Fixed. |
| VA-04 | Major | `src/variance_agent/numeric.py:44-48`; `src/variance_agent/report.py:39-44` | Math | Formatting rounds an already rounded 50-digit percentage ratio. A constructed exact ratio just above 5.05% displayed 5.0% instead of 5.1%. | Convert original Decimal operands to exact integer ratios and apply one half-even rounding to tenths of a percent at reporting. Public analytical ratio precision is preserved. Fixed. |
| VA-05 | Major | `src/variance_agent/analysis.py:152-161`; `src/variance_agent/report.py:229-231` | Math | Increasing precision does not prevent threshold cross-product exponent overflow/underflow. Valid threshold `1e999` with Budget `1e100` failed instead of returning nonmaterial; displaying a valid threshold multiplied it beyond Emax. | Compare exact integer cross-products without Decimal range loss. Scale percentage threshold text directly without overflowing arithmetic. Tests include very large and exact-subnormal inputs and preserve strict equality rules. Fixed. |
| VA-06 | Major | `src/variance_agent/analysis.py:194-207`, `:228-239`; `src/variance_agent/report.py:123-130` | Math | Tolerance-based support can omit an observed residual. Actual `132.009` versus Budget `100` was reported as fully explained by `20 + 12`, leaving `0.009` undisclosed. | Keep the documented support tolerances; append an explicit Unexplained residual component when accepted model effects differ from observed variance. Components sum exactly, diagnostics retain the model-only residual, and reporting requests its reconciliation. Fixed. |
| VA-07 | Major | `src/variance_agent/report.py:174-176`; `src/variance_agent/audit.py:139-165` | Math | Only `analyze_rows` runs final verification. Manually changed results could produce false totals and authoritative audit trust flags. | Reverify row, aggregate, percentage, status, materiality, ordering, and supported-component identities at both output boundaries. Tampered results fail. Corrected one hand-built test fixture whose unclassified row had been incorrectly marked nonmaterial. Fixed. |
| VA-08 | Major | `src/variance_agent/analysis.py:389-417`, `:426-427`; `src/variance_agent/parsing.py:109-123` | Architecture | Invalid public-API threshold or row types raised AttributeError; blank/nontext periods were accepted. Dataclass annotations supplied no runtime guard. | Validate configuration, thresholds, period, type maps, row containers, scalar financial fields and source text before use. Expected invalid inputs raise ValueError and CLI errors remain exit 2. Public call signatures are retained. Fixed. |
| VA-09 | Major | `src/variance_agent/analysis.py:426-483` | Math | A Period metadata column was ignored, allowing rows from different or missing periods to be aggregated under one report label. | Require nonblank run period; when Period is declared, validate every row against it. Period-free existing inputs remain supported. Fixed. |
| VA-10 | Major | `src/variance_agent/parsing.py:109-123`, `:176-196` | OWASP Agentic | API normalization silently skipped data under a null header; JSON's default decoder accepted NaN/Infinity in metadata despite the finite-data contract. | Reject populated unnamed fields and nonstandard JSON numeric constants throughout the decoded payload; retain duplicate-key and depth protections. Bound JSON value count and text. Fixed. |
| VA-11 | Major | `src/variance_agent/report.py:14-31`; `src/variance_agent/cli.py:157-158` | OWASP Agentic | Markdown escaping did not neutralize terminal escape sequences or bidirectional controls. A source label emitted terminal control bytes when the report printed. | Render such controls as visible escapes in reports and CLI error messages while preserving original audit strings as data. Existing Markdown/HTML escaping is retained. Fixed. |
| VA-12 | Major | `src/variance_agent/parsing.py:36-43`, `:46-84` | Math | `parse_decimal` checked finiteness but permitted extreme nonzero exponents and arbitrarily long numeric text until later arithmetic or serialization. | Bound numeric representation length and validate each numeric value against the fresh trapped financial context before use. Canonicalize extreme zero exponents as before. Fixed. |
| VA-13 | Major | `src/variance_agent/models.py:6,73`; `src/variance_agent/analysis.py:6`; `src/variance_agent/audit.py:8`; `src/variance_agent/parsing.py:10`; `pyproject.toml:21` | Architecture | Source boundary types use Any and untyped functions; CI has no strict type check. | Replaced explicit Any with object/recursive JSON types and explicit workbook/CLI protocols; annotated arithmetic context and packaging scripts; added strict mypy configuration with explicit/unimported Any bans. **Open gate:** installing and declaring mypy requires owner approval. Strict checking has not executed and no pass is claimed. |
| VA-14 | Polish | `src/variance_agent/analysis.py:177-181` | Math | Driver tolerance arithmetic runs even when no driver model is supplied. Exact minimum subnormal amounts fail in unused relative-tolerance multiplication. | Calculate tolerances only for complete candidate models. A valid no-driver exact-subnormal input now succeeds. Fixed. |
| VA-15 | Polish | `pyproject.toml:2,20-22`; `.gitignore:1-10`; `README.md:97-105` | Architecture | Direct build/development/Excel/release dependencies used unbounded lower-version constraints; checker cache and credential files were not ignored; verification documentation omitted packaging and strict typing. | Pin existing direct packages to live-resolved versions, document platform-specific transitive resolution, ignore checker cache and environment credential files, and give exact setup/package/check commands. No new third-party package was added. Fixed; checker addition remains gated under VA-13. |
| VA-16 | Polish | `prompt/variance_report_prompt.md:2-20`; `README.md:91-95` | OWASP Agentic | The optional reference prompt asks a model to orchestrate financial analysis from raw data, while trust flags alone cannot constrain downstream behavior. There is no live model path. | Restrict the reference to schema-validated deterministic audit facts, data-only source strings and grounded commentary. Explicitly require executable schema/time/retry/token/step/credential controls in any separate integration instead of implying the prompt supplies them. Fixed. |

## Verification suite and executed results

Local environment: Python 3.12.14. Existing dependency versions were resolved live: pytest 9.1.1, Ruff 0.17.1, jsonschema 4.26.0, openpyxl 3.1.5, build 1.6.1, twine 7.0.0; the isolated backend is hatchling 1.32.4.

| Check | Executed result |
|---|---|
| Original baseline suite | 292 passed in 1.58s |
| New regressions against archived baseline source | 60 failed, 2 passed in 0.92s; failures reproduce the defects, controls remain accepted |
| Patched complete suite | 354 passed in 1.76s |
| New deterministic regression cases | All 62 pass within the complete suite |
| Fraction-oracle properties | Existing 250 signed/zero-budget materiality cases plus 60 generated seven-account reporting cases pass |
| Audit schemas and full report fixtures | All original published schemas, five USD cases and EUR/GBP reports pass without changing any schema or reviewed financial/report golden |
| Ruff | All checks passed |
| Bytecode compilation | Passed for src, tests and scripts |
| Dependency consistency | pip check: no broken requirements found |
| Live dependency advisory lookup | OSV batch query returned no matched advisories for 41 installed runtime/development/release packages; full package/version request and response retained. This is a lookup result, not a guarantee of vulnerability absence. |
| Wheel and sdist build | Both built successfully with pinned hatchling 1.32.4 |
| Distribution metadata/content | twine and repository distribution checker pass |
| Clean installed console/CSV/JSON/audit checks | Both wheel and sdist pass in independent non-editable environments without Excel |
| Strict mypy | **[Not executed in runtime]**: checker absent; the launched command exits before analysis with `No module named mypy`. Dependency approval is required. |
| Hosted Python 3.11/3.13/3.14 and Windows CI | Pending the draft pull request run; local results do not establish those platforms. |

Reproduction and verification commands, with the repository root as working directory:

```sh
python -m pip install -e '.[dev,excel,release]'
python -m pytest -q
python -m ruff check .
python -m compileall -q src tests scripts
python -m pip check
python -m build --outdir dist
python -m twine check dist/*
python scripts/check_distribution.py dist
```

For each wheel/sdist, create a separate virtual environment, install that artifact, and run its interpreter on `scripts/check_installation.py --without-excel` followed by `-m pip check`. The script deliberately rejects editable source installations. No distribution is published to a package index.

Pending strict command:

```sh
python -m mypy --strict src/variance_agent scripts
```

## Approval proposal and remaining work

The concrete pending proposal adds only the development checker `mypy==2.4.0`, enables its existing strict configuration in CI, and pins its resolved supporting packages: ast_serialize 0.13.0, librt 0.16.0, mypy_extensions 1.1.0, and pathspec 1.1.1. The already installed typing_extensions 4.16.0 satisfies its remaining requirement. A pip dry-run and metadata report establish these versions; the checker has not been installed. The separate proposed diff is not part of the applied production patch.

The user explicitly required: “STOP and ask for human approval before ... adding any new third-party dependency.” This gate prevents completing VA-13 until approval. After approval, apply the proposal, execute strict checking, fix any reported errors, rerun affected verification and CI, and update the audit ledger and delivery. The pull request remains a draft meanwhile. This audit does not claim production readiness while that gate remains open.

No directory was deleted; no published schema or CLI signature was broken. Scope remains descriptive variance analysis on supplied data. Source completeness, authentic authorship, unsupported accounting sign transformations and causal inference remain external review responsibilities. There is no live model or browser surface on which to claim model-call or browser verification.
