"""End-to-end explicit metric columns; all examples are fictional HALV.FAKE."""
from decimal import Decimal
import io
from zipfile import ZipFile

import pytest
from variance_agent.cli import main
from variance_agent.intake import read_input_assisted
from variance_agent import analyze_rows
from variance_agent.xlsx import render_xlsx
from test_multi_audience_measures import config, metric


@pytest.mark.parametrize("assisted", [False, True])
def test_cli_rates_keep_their_units_and_need_all_cutoffs(tmp_path, capsys, assisted):
    source = tmp_path / "fictional.csv"
    source.write_text("Line Item,Measure,Better,Budget,Actual\nGross Margin,Percent,Higher,41.2%,40.6%\n")
    args = [str(source), "--period", "3Q26", "--dollar-threshold", "10", "--percent-threshold", "2"]
    if assisted:
        args.append("--assisted")
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2 and "--bps-threshold" in capsys.readouterr().err
    assert main([*args, "--bps-threshold", "25"]) == 0
    output = capsys.readouterr()
    assert "-60 bps" in output.out and "Gross Margin" in output.err


def test_assisted_does_not_scale_or_infer_currency_subtotals_from_rates():
    source = (b"Fictional Halvorsen Instruments (in millions)\nLine Item,Measure,Better,Budget,Actual\n"
              b"Gross Margin,Percent,Higher,41.2%,40.6%\nDiluted EPS,Per Share,Higher,0.84,0.91\n")
    intake = read_input_assisted(source, ".csv", filename="fictional.csv")
    assert not intake.has_fatal_errors, intake.fatal_error_message
    result = analyze_rows(intake.rows, config())
    assert result.rows[0].variance_bps == Decimal("-60")
    assert result.rows[1].variance_dollars == Decimal("0.07")


def test_new_workbook_uses_units_not_currency_styles_for_a_rate():
    result = analyze_rows([metric("Percent", "41.2%", "40.6%")], config())
    data = render_xlsx(result)
    with ZipFile(io.BytesIO(data)) as archive:
        text = "\n".join(archive.read(n).decode() for n in archive.namelist() if n.startswith("xl/worksheets/"))
    assert "-60 bps" in text and "40.6%" in text
