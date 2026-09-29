"""CSV validation must inspect physical columns before mapping header names."""

import pytest

from variance_agent.cli import main
from variance_agent.parsing import load_csv_text


@pytest.mark.parametrize("blank_header", ["", " ", "???"])
def test_repeated_unnamed_headers_cannot_hide_earlier_values(blank_header):
    source = f"Line Item,Budget,Actual,{blank_header},{blank_header}\nSales,100,120,999,\n"
    with pytest.raises(ValueError, match="data appears under a blank header"):
        load_csv_text(source)


def test_repeated_unnamed_columns_are_allowed_when_all_are_empty():
    assert load_csv_text("Line Item,Budget,Actual,,\nSales,100,120,,\n") == [
        {"line_item": "Sales", "budget": "100", "actual": "120"}
    ]


def test_quoted_commas_and_multiline_cells_preserve_column_alignment():
    text = 'Line Item,Budget,Actual,Notes,,\n"Sales, East","1,000",1200,"line one\nline two",,\n'
    assert load_csv_text(text) == [
        {
            "line_item": "Sales, East",
            "budget": "1,000",
            "actual": "1200",
            "notes": "line one\nline two",
        }
    ]


def test_empty_physical_lines_remain_ignored():
    text = "Line Item,Budget,Actual\n\nSales,100,120\n\nRent,50,55\n"
    assert len(load_csv_text(text)) == 2


def test_cli_rejects_hidden_csv_data_without_overwriting_report(tmp_path, capsys):
    source = tmp_path / "input.csv"
    source.write_text("Line Item,Budget,Actual,,\nSales,100,120,999,\n")
    report = tmp_path / "report.md"
    report.write_text("previous report")
    with pytest.raises(SystemExit) as error:
        main(
            [
                str(source),
                "--period",
                "Q3",
                "--dollar-threshold",
                "100",
                "--percent-threshold",
                "5",
                "--output",
                str(report),
            ]
        )
    assert error.value.code == 2
    assert "blank header" in capsys.readouterr().err
    assert report.read_text() == "previous report"
