# Python and panel API

The offline API compares supplied numbers. It creates no estimates or investment recommendations. CSV and JSON use the standard library; Excel remains an optional extra. Financial values must be exact numeric text, integers or `Decimal` initialized from text. Floats are refused by the new API. Thresholds in `AudienceConfig` are `Decimal`; `percent_threshold` is a ratio (`Decimal("0.02")` means 2%). CLI percentages remain percent numbers (`--percent-threshold 2`).

```python
from decimal import Decimal
from variance_agent import analyze_table, analyze_file, analyze_panel
from variance_agent.api import AudienceOptions, PanelOptions
from variance_agent.audience import AudienceConfig
from variance_agent.models import ComparisonBasis

config = AudienceConfig("3Q26", Decimal("10"), Decimal("0.02"),
                        per_share_threshold=Decimal("0.01"),
                        bps_threshold=Decimal("25"), count_threshold=Decimal("1000"))
options = AudienceOptions(bases=(ComparisonBasis.CONSENSUS,))
file_result = analyze_file("tests/fixtures/multi_audience/consensus.csv", config,
                           options=options)
```

The three public functions, exported beside the four existing names, are:

```python
analyze_table(rows: list[dict[str, object]], config: AnalysisConfig, *,
              options: AudienceOptions | None = None) -> TableAnalysis
analyze_file(path: str | Path, config: AnalysisConfig, *,
             options: AudienceOptions | None = None) -> TableAnalysis
analyze_panel(rows: list[dict[str, object]], *, group_by: tuple[str, ...],
              options: PanelOptions) -> BatchResult
```

`AudienceOptions` chooses an ordered tuple of bases, assisted file intake, an optional worksheet and explicit column mapping. With no bases, exactly one detected basis is selected; multiple bases require an explicit choice. Period-column comparisons use the shared period ordering rules. These new APIs enable extended headers. The existing `analyze_rows` retains its opt-in rules and all four legacy signatures remain unchanged.

`TableAnalysis` contains configuration, independently verified single-basis results, unavailable comparisons, supplied Estimate versus Consensus gaps, source metric order and visible inferences. Each comparison keeps the original `Status` values. An absent comparison has no variance, status or materiality. A supplied zero is a real comparison. `analyze_file` captures once and records the file name, worksheet and SHA-256 of those exact bytes. In-memory calls leave source identity null. `build_comparison_audit` uses captured provenance unless explicitly overridden.

`PanelOptions` contains `config` and `audience`. `BatchResult.groups` contains a `GroupResult` for every group: ordered key values, either an analysis or one error reason. Global structure and key errors raise `ValueError` before any group runs. Expected amount, threshold and ambiguity errors fail only their group. Internal verification failures propagate. An empty panel is a global error. A panel where every group fails still produces an empty long dataset and one error record per group.

## Period and confirmation rules

With a `Period` group key, set `config.period` to `""`; each group's value becomes its period. A configured period together with that key is refused. Without it, a configured period is required. Group-key names are distinct after normalization, and values must be nonblank text. Keys conflicting with the fixed output fields or `error` are refused. Key values are preserved, including whitespace.

Panel analysis never prompts. Supply measure kinds, rate scale, direction and thresholds through columns, configuration, flags or mappings. A Currency row with neither a classification nor explicit Better fails its group and asks for Type or Better. Per Share's documented Higher default remains visible. Repeated metric identities within a group are refused to keep one record per metric and basis.

## CLI panel and exits

```sh
variance-agent tests/fixtures/multi_audience/panel.csv \
  --group-by Ticker,Period --compare-to consensus \
  --dollar-threshold 10 --percent-threshold 2 \
  --bps-threshold 25 --per-share-threshold 0.01 --count-threshold 1000 \
  --long-output panel.csv --long-output-jsonl panel.jsonl --errors-output errors.csv
```

`--errors-output` and at least one long output are required in panel mode. `--period` is refused when Period is a group key. Report, workbook, audit, commentary and check-only flags are refused for panels. Single-table comparisons can also export long CSV/JSONL. Chat does not accept these flags and keeps its hosted path-export policy.

- Exit 0: all groups succeeded (unchanged success meaning for a single run).
- Exit 2: invalid command, malformed capture, global keys/limits, or output-path failure (unchanged for single runs).
- Exit 3: at least one failed group; successful groups and one error row per failed group are written.

Input, mapping and type-map captures cannot also be output paths. All output paths must be distinct, including symlink/hardlink aliases. All outputs are staged before any destination is replaced. Each replacement is atomic; multiple replacements are not a filesystem transaction.

## Long output contract

CSV columns and JSON object keys begin with the group keys in declared order, followed by:

`line_item, segment, measure, basis, comparison_present, comparison, actual, variance, variance_percent, variance_bps, status, material, display_label, source_sha256`

Groups sort lexically by the tuple of exact group-key values. Within each group, metrics keep source row order and bases keep the requested order. Missing comparisons still emit a record, with null derived facts. Numbers are exact fixed-point decimal strings without display units. `variance_percent` is a ratio, `variance_bps` is in basis points, and only Percent measures carry bps. Status remains F/U/Neutral/Unclassified; display labels are derived separately. JSON booleans are native; CSV booleans are `true`/`false`. Null is JSON null or an empty CSV cell. UTF-8 exports use LF line endings and end in a newline when they have rows. An empty JSONL export is empty; CSV retains its header.

CSV protects untrusted text, including headers and error reasons, by prefixing an apostrophe if the first character after whitespace or control characters is `=`, `+`, `-` or `@`. Exact numeric fields are exempt; a comparison of `-0.10` stays numeric text. JSONL preserves text without this spreadsheet-specific prefix. Source SHA-256 is null for in-memory panels and the actual captured-file hash for CLI panels. Error CSV contains the declared keys, `error` and `source_sha256`.

## Limits and stability

File capture remains at most 32 MiB. Whole-table limits apply before grouping: at most 100,000 data rows, 256 columns, 1,000,000 cells, bounded text and numeric strings, and the existing nesting depth. No per-group cap resets permit a larger capture. Split larger universes into separate files and runs. A strict 100,000-row CSV may have at most 10 columns; assisted intake also counts its header/title rows against its bounded table scan.

Before 1.0, minor releases may add opt-in functions, defaulted metadata fields, comparison bases and schema versions. They may not change existing public parameter names/order, positional versus keyword-only behavior, defaults, old financial rules, fixed long-output columns/order/units, deterministic serialization, or legacy outputs for existing inputs. A required wire change needs an explicit new format/version. Unknown future enum members must not be assumed valid in an older closed audit schema. The four original names retain their exact signatures; signature tests pin the three new functions too.
