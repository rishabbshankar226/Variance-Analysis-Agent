"""X53: a per-share row with no Measure refuses where a unit would scale it as money (fictional data)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from variance_agent import cli
from variance_agent.comparisons import read_comparison_input
from variance_agent.intake import read_input_assisted

CAPTION = "Fictional Co (in millions, except per share data)\n"
EPS_REFUSAL = ("'Basic EPS' looks like a per-share figure, which the caption's millions would scale as money. Add a "
               "Measure column that says Per Share for it, or leave the line out, then upload the file again.")


def _file(*lines: str, caption: str = CAPTION, header: str = "Line Item,Type,Budget,Actual") -> bytes:
    return (caption + header + "\n" + "\n".join(lines) + "\n").encode("utf-8")


K1 = _file("Net sales,Revenue,4000,4100", "Cost of sales,Expense,2250,2300", "Basic EPS,,5.50,6.10")


def _read(data: bytes):  # type: ignore[no-untyped-def]
    return read_input_assisted(data, ".csv", filename="k1.csv")


def test_fpa_intake_refuses_an_eps_row_a_caption_would_scale() -> None:
    result = _read(K1)
    assert result.has_fatal_errors and not result.rows
    assert result.fatal_error_message == EPS_REFUSAL


def test_the_comparison_path_refuses_it_too() -> None:
    with pytest.raises(ValueError) as refused:
        read_comparison_input(K1, ".csv", filename="k1.csv", assisted=True, per_share_lines=True)
    assert str(refused.value) == EPS_REFUSAL


@pytest.mark.parametrize("flag", [(), ("--per-share-lines",)])
def test_the_command_line_refuses_with_or_without_the_flag(
        tmp_path: Path, capsys: pytest.CaptureFixture[str], flag: tuple[str, ...]) -> None:
    source = tmp_path / "k1.csv"
    source.write_bytes(K1)
    with pytest.raises(SystemExit) as stop:
        cli.main([str(source), "--assisted", "--period", "FY2025", "--dollar-threshold", "1", "--percent-threshold", "1",
                  *flag])
    assert stop.value.code == 2
    assert EPS_REFUSAL in capsys.readouterr().err


def test_a_declared_per_share_row_reads_as_written() -> None:
    result = _read(_file("Net sales,Revenue,Currency,4000,4100", "Basic EPS,,Per Share,5.50,6.10",
                         header="Line Item,Type,Measure,Budget,Actual"))
    assert not result.has_fatal_errors, result.fatal_error_message
    eps = next(row for row in result.rows if row["line_item"] == "Basic EPS")
    assert (Decimal(str(eps["budget"])), Decimal(str(eps["actual"]))) == (Decimal("5.50"), Decimal("6.10"))
    assert next(row for row in result.rows if row["line_item"] == "Net sales")["actual"] == Decimal("4100000000")


def test_a_declared_currency_row_keeps_what_it_says() -> None:
    result = _read(_file("Net sales,Revenue,Currency,4000,4100", "Basic EPS,,Currency,5.50,6.10",
                         header="Line Item,Type,Measure,Budget,Actual"))
    assert not result.has_fatal_errors, result.fatal_error_message


def test_a_blank_measure_cell_is_no_declaration() -> None:
    result = _read(_file("Net sales,Revenue,Currency,4000,4100", "Basic EPS,,,5.50,6.10",
                         header="Line Item,Type,Measure,Budget,Actual"))
    assert result.has_fatal_errors and result.fatal_error_message == EPS_REFUSAL


def test_without_a_scaling_unit_an_eps_row_reads_unscaled() -> None:
    result = _read(_file("Net sales,Revenue,4000000000,4100000000", "Basic EPS,,5.50,6.10", caption=""))
    assert not result.has_fatal_errors, result.fatal_error_message
    eps = next(row for row in result.rows if row["line_item"] == "Basic EPS")
    assert Decimal(str(eps["actual"])) == Decimal("6.10")


def test_a_label_that_only_contains_the_letters_scales_as_money() -> None:
    result = _read(_file("Net sales,Revenue,4000,4100", "STEPS program costs,Expense,40,35"))
    assert not result.has_fatal_errors, result.fatal_error_message
    steps = next(row for row in result.rows if row["line_item"] == "STEPS program costs")
    assert steps["actual"] == Decimal("35000000")


def test_a_share_count_and_several_lines_are_named() -> None:
    result = _read(_file("Net sales,Revenue,4000,4100", "Weighted average shares outstanding,,160,158"))
    assert result.fatal_error_message == (
        "'Weighted average shares outstanding' looks like a share count, which the caption's millions would scale as "
        "money. Add a Measure column that says Count for it, or leave the line out, then upload the file again.")
    result = _read(_file("Net sales,Revenue,4000,4100", "Basic EPS,,5.50,6.10", "Diluted EPS,,5.40,6.00",
                         "Weighted average shares outstanding,,160,158", "Dividends per share,,1.00,1.10"))
    assert result.fatal_error_message == (
        "'Basic EPS', 'Diluted EPS', 'Weighted average shares outstanding' and 1 more look like per-share figures or "
        "share counts, which the caption's millions would scale as money. Add a Measure column that says Per Share or "
        "Count for them, or leave those lines out, then upload the file again.")
