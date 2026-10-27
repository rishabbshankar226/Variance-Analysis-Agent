"""R11: LTM from a 10-K and a later 10-Q (docs/analysts/PLAN.md). Every filing here is fictional."""

from __future__ import annotations

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tests.fixtures.ixbrl.build_ixbrl import QUARTER_CONTEXTS, fact, income_filing, quarter_filing, quarter_rows, row
from variance_agent import cli

ROOT = Path(__file__).resolve().parents[1]
M = Decimal(1_000_000)
YTD = "Condensed Consolidated Statements of Operations, 6 Months Ended"


def _files(tmp_path: Path, quarter: bytes | None = None, annual: bytes | None = None) -> tuple[Path, Path]:
    q, k = tmp_path / "hal-20260328.htm", tmp_path / "hal-20250927.htm"
    q.write_bytes(quarter or quarter_filing())
    k.write_bytes(annual or income_filing())
    return q, k


def _run(tmp_path: Path, quarter: bytes | None = None, annual: bytes | None = None, *extra: str) -> list[str]:
    q, k = _files(tmp_path, quarter, annual)
    return [str(q), "--assisted", "--ltm-from", str(k), "--period", "LTM Mar 2026", "--dollar-threshold", "1",
            "--percent-threshold", "1", *extra]


def _audit(tmp_path: Path, *extra: str) -> dict[str, object]:
    audit = tmp_path / "audit.json"
    assert cli.main(_run(tmp_path, None, None, "--audit-json", str(audit), "-o", str(tmp_path / "r.md"), *extra)) == 0
    record = json.loads(audit.read_text(encoding="utf-8"))
    Draft202012Validator(json.loads((ROOT / "schemas/audit-1.9.schema.json").read_text(encoding="utf-8"))).validate(record)
    return record  # type: ignore[no-any-return]


def test_ltm_is_the_fiscal_year_plus_this_ytd_less_last_ytd(tmp_path: Path) -> None:
    record = _audit(tmp_path)
    rows = {row["line_item"]: row for row in record["measure_rows"]}  # type: ignore[union-attr, index]
    # Fraction oracle: FY + YTD - prior YTD, from the fixtures' printed figures.
    expected = {"Net sales": Fraction(4100 + 2200 - 2000), "Cost of sales": Fraction(2300 + 1200 - 1100),
                "Research and development": Fraction(300 + 160 - 150), "Interest expense": Fraction(50 + 25 - 20)}
    for name, ltm in expected.items():
        assert Fraction(rows[name]["actual"]) == ltm * 1_000_000, name
    assert Fraction(rows["Net sales"]["comparison"]) == 4100 * 1_000_000
    assert record["comparison"]["label"] == "FY2025"  # type: ignore[index]


def test_every_component_is_cited_by_document_column_and_context(tmp_path: Path) -> None:
    document = _audit(tmp_path)["source"]["document"]  # type: ignore[index]
    assert document["kind"] == "ltm"
    assert [d["name"] for d in document["documents"]] == ["hal-20250927.htm", "hal-20260328.htm"]
    sales = next(line for line in document["lines"] if line["line_item"] == "Net sales")
    assert [(c["document"], c["column"], c["context"], c["weight"], c["used"]) for c in sales["components"]] == [
        ("hal-20250927.htm", "FY2025", "FY25", 1, "4100000000"),
        ("hal-20260328.htm", "6 months to Mar 2026", "YTD26", 1, "2200000000"),
        ("hal-20260328.htm", "6 months to Mar 2025", "YTD25", -1, "2000000000")]


def test_the_report_shows_the_build(tmp_path: Path) -> None:
    _audit(tmp_path)
    report = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "## LTM build" in report
    assert ("| Net sales | $4,100,000,000.00 | $2,200,000,000.00 | $2,000,000,000.00 | $4,300,000,000.00 |") in report
    assert ("Built LTM as FY2025 from 'hal-20250927.htm' plus 6 months to Mar 2026 less 6 months to Mar 2025 from "
            "'hal-20260328.htm', line by line by XBRL concept") in report


def test_per_share_lines_are_not_computable_as_ltm(tmp_path: Path) -> None:
    notes = _audit(tmp_path)["source"]["document"]["reader_notes"]  # type: ignore[index]
    assert "Left out 'Basic (in dollars per share)': per-share amounts and share counts are not computable as LTM" in notes


@pytest.mark.parametrize(("periods", "message"), [
    ({**QUARTER_CONTEXTS, "YTD26": ("2025-09-29", "2026-03-28")},
     "The 10-Q's year to date starts 2025-09-29, but FY2025 in 'hal-20250927.htm' ends 2025-09-27, so the year to date "
     "should start 2025-09-28. LTM needs the 10-Q that follows that 10-K; upload the 10-K the 10-Q's year continues."),
    ({**QUARTER_CONTEXTS, "YTD25": ("2024-09-28", "2025-03-29")},
     "The 10-Q's prior year to date starts 2024-09-28, but FY2025 in 'hal-20250927.htm' starts 2024-09-29, so the two "
     "years don't line up. LTM needs the 10-Q that follows that 10-K; upload the 10-K the 10-Q's year continues."),
])
def test_continuity_is_checked_not_assumed(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                           periods: dict[str, tuple[str, str]], message: str) -> None:
    with pytest.raises(SystemExit):
        cli.main(_run(tmp_path, quarter_filing(periods=periods)))
    assert message in capsys.readouterr().err.replace("\n", " ")


def test_a_line_in_one_document_only_refuses(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    extra = row("Restructuring", *(fact("us-gaap:RestructuringCharges", c, v)
                                   for c, v in zip(("Q26", "Q25", "YTD26", "YTD25"), ("0", "0", "0", "0"), strict=True)))
    with pytest.raises(SystemExit):
        cli.main(_run(tmp_path, quarter_filing(quarter_rows(extra=[extra]))))
    assert ("'Restructuring' (us-gaap:RestructuringCharges) is in 'hal-20260328.htm' but not in 'hal-20250927.htm', so "
            "LTM can't be built line by line without changing a total. Compare the 10-Q on its own instead.") in (
        capsys.readouterr().err.replace("\n", " "))


def test_ltm_needs_assisted_intake(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    q, k = _files(tmp_path)
    with pytest.raises(SystemExit):
        cli.main([str(q), "--ltm-from", str(k), "--period", "LTM", "--dollar-threshold", "1", "--percent-threshold", "1"])
    assert "--ltm-from needs --assisted" in capsys.readouterr().err
