"""Fictional HALV.FAKE filing: EPS and share counts never become money totals."""
from decimal import Decimal
import json
from pathlib import Path

import jsonschema
import pytest

from variance_agent.api import AudienceOptions, analyze_file
from variance_agent.audience import AudienceConfig
from variance_agent.chat.handlers import handle_message, handle_upload
from variance_agent.chat.session import Phase, Session
from variance_agent.cli import main
from variance_agent.comparisons import build_comparison_audit
from variance_agent.intake import read_input_assisted
from variance_agent.parsing import normalize_row
from variance_agent.pdf_tables import extract_statement_tables
from variance_agent.statement_shape import shape_income_statement

PDF = Path("tests/fixtures/realworld/fixture_t_halvorsen_fake_eps.pdf")
COUNT_NAMES = ("Weighted average common shares outstanding: Basic", "Weighted average common shares outstanding: Diluted")
EPS_NAMES = ("Earnings per share: Basic", "Earnings per share: Diluted")


def test_extractor_retains_exact_printed_values_only_on_request() -> None:
    data = PDF.read_bytes()
    off = extract_statement_tables(data, PDF.name)
    on = extract_statement_tables(data, PDF.name, per_share_lines=True)
    assert extract_statement_tables(data, PDF.name) == off
    assert not any("Earnings per share" in str(row) for table in off for row in table.raw_rows)
    assert any("(per-share and share counts are not money totals)" in note for table in off for note in table.notes)
    header = next(row for row in on[0].raw_rows if row[0] == "Line Item")
    assert header[-2:] == ["Measure", "Better"]
    eps = [row for row in on[0].raw_rows if row and row[0] in EPS_NAMES]
    assert [row[1:3] for row in eps] == [["0.95", "0.88"], ["0.91", "0.84"]]
    assert all(row[-2:] == ["Per Share", "Higher"] for row in eps)
    assert any("Retained" in note and "Per Share" in note for note in on[0].notes)


def test_shaping_isolates_currency_and_intake_scales_only_money() -> None:
    table = extract_statement_tables(PDF.read_bytes(), PDF.name, per_share_lines=True)[0]
    shaped = shape_income_statement(table.raw_rows)
    assert shaped.shaped is True
    assert "Operating income" in shaped.subtotals
    assert not any("Earnings per share" in name for name in shaped.unlabeled)
    intake = read_input_assisted(PDF.read_bytes(), ".pdf", filename=PDF.name, per_share_lines=True)
    assert not intake.has_fatal_errors
    rows = {str(row["line_item"]): normalize_row(row) for row in intake.rows}
    assert rows[EPS_NAMES[1]]["actual"] == Decimal(".91")
    assert rows[EPS_NAMES[1]]["budget"] == Decimal(".84")
    assert rows["Revenue"]["actual"] == Decimal("1287500000")
    assert rows[COUNT_NAMES[1]]["actual"] == Decimal("52000000")
    assert rows[COUNT_NAMES[1]]["measure"] == "Count"
    assert not rows[COUNT_NAMES[1]].get("better")
    assert any("as printed" in note for note in intake.visible_transformations)


def flags() -> list[str]:
    return [str(PDF), "--assisted", "--preset", "earnings", "--period", "FY2026", "--dollar-threshold", "10000000",
            "--percent-threshold", "2", "--per-share-threshold", ".01", "--count-threshold", "1000000"]


def test_cli_requires_count_direction_and_records_pdf_provenance(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as failure:
        main(flags())
    assert failure.value.code == 2
    assert "Better" in capsys.readouterr().err
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"better_directions": {name: "Lower" for name in COUNT_NAMES}}))
    audit = tmp_path / "audit.json"
    assert main([*flags(), "--mapping", str(mapping), "--audit-json", str(audit)]) == 0
    record = json.loads(audit.read_text())
    eps = next(row for row in record["measure_rows"] if row["line_item"] == EPS_NAMES[1])
    assert eps["actual"] == "0.91" and eps["variance"] == "0.07"
    assert record["comparison"]["label"] == "FY2025"
    assert record["source"]["document"]["kind"] == "pdf" and record["source"]["document"]["pages"] == [1]
    assert any("Retained" in note for note in record["source"]["document"]["reader_notes"])
    assert record["totals"]["revenue"]["actual"] == "1287500000.0"
    jsonschema.validate(record, json.loads(Path("schemas/audit-1.8.schema.json").read_text()))
    assert main([*flags(), "--no-per-share-lines", "--audit-json", str(audit)]) == 0
    assert all(row["measure"] == "Currency" for row in json.loads(audit.read_text())["measure_rows"])


def test_file_api_preserves_independent_scale_and_capture(tmp_path: Path) -> None:
    config = AudienceConfig("FY2026", Decimal("10000000"), Decimal(".02"), per_share_threshold=Decimal(".01"),
                            count_threshold=Decimal("1000000"))
    table = analyze_file(PDF, config, options=AudienceOptions(assisted=True, preset="earnings",
                         better_directions={name: "Lower" for name in COUNT_NAMES}))
    record = build_comparison_audit(table)
    assert record["source"]["document"]["pages"] == [1]
    assert table.comparisons[0].result.revenue.actual == Decimal("1287500000")
    assert len(table.comparisons[0].result.rows) == 6
    assert record["transformations"]["unit_scale"] == "1000000"


def test_chat_explicit_earnings_filing_review_asks_count_direction() -> None:
    default = Session()
    handle_upload(default, PDF.read_bytes(), PDF.name)
    assert all("per share" not in str(row.get("line_item", "")).lower() for row in default.parsed_rows)
    session = Session(path_exports_enabled=False)
    handle_message(session, "review earnings")
    reply = handle_upload(session, PDF.read_bytes(), PDF.name)
    assert "Here's how I read your file" in reply.text and "Per Share" in reply.text
    for message in ("Looks right", "FY2026", "$10000000 or 2%", "USD", ".01", "Lower", "1000000", "Lower"):
        reply = handle_message(session, message)
    assert session.phase is Phase.EXPLORING
    eps = next(row for row in reply.table if row["Line Item"] == EPS_NAMES[1])
    assert eps["Actual"] == "$0.91/sh"
    audit = handle_message(session, "export audit")
    assert json.loads(next(iter(audit.download.values())))["source"]["document"]["pages"] == [1]


def test_explicit_mapping_overrides_printed_eps_direction(tmp_path: Path) -> None:
    mapping, audit = tmp_path / "mapping.json", tmp_path / "audit.json"
    mapping.write_text(json.dumps({"better_directions": {**{name: "Lower" for name in COUNT_NAMES}, EPS_NAMES[1]: "Lower"}}))
    assert main([*flags(), "--mapping", str(mapping), "--audit-json", str(audit)]) == 0
    eps = next(row for row in json.loads(audit.read_text())["measure_rows"] if row["line_item"] == EPS_NAMES[1])
    assert eps["better"] == "Lower" and eps["status"] == "U"


def test_explicit_off_matches_default_fpna_bytes(tmp_path: Path) -> None:
    audit, report = tmp_path / "audit.json", tmp_path / "report.md"
    args = [str(PDF), "--assisted", "--period", "FY2026", "--dollar-threshold", "10000000", "--percent-threshold", "2",
            "--audit-json", str(audit), "-o", str(report)]
    assert main(args) == 0
    before = audit.read_bytes(), report.read_bytes()
    assert main([*args, "--no-per-share-lines"]) == 0
    assert before == (audit.read_bytes(), report.read_bytes())


def test_only_supported_share_metrics_are_retained() -> None:
    from variance_agent.pdf_tables import _retained_measure
    assert _retained_measure("Shares used in per share calculations", "") == ""
    assert _retained_measure("Diluted EPS", "") == "Per Share"
    assert _retained_measure("Basic", "Weighted average shares") == "Count"
