"""E8: .xls and .htm get read by what they contain, or a refusal that names the fix.

Every file here is built in the test and fictional.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from variance_agent import cli
from variance_agent.chat.handlers import handle_upload
from variance_agent.chat.session import Session
from variance_agent.intake import read_input_assisted

BIFF = ("'old.xls' is in the Excel 97-2003 format (.xls), which I can't read. Open it in Excel, "
        "choose File > Save As, pick Excel Workbook (.xlsx), and upload that copy.")
WEB_XLS = ("'old.xls' is a web page saved with an .xls name, not an Excel workbook. Open it in Excel, "
           "choose File > Save As, pick Excel Workbook (.xlsx), and upload that copy, or export it as CSV.")
OTHER_XLS = ("'old.xls' isn't an Excel workbook I can read. Save it from Excel as an Excel Workbook (.xlsx) "
             "or as CSV, and upload that copy.")
HTM = ("'filing.htm' is a web page without Inline XBRL figures, so it has no statements I can find. Upload the "
       "filing's 10-K or 10-Q document from its EDGAR folder, its PDF, or a CSV or Excel table.")
STRICT_HTM = ("HTML filings are read with --assisted, which finds the financial statements in the filing and lists every "
              "adjustment it makes.")
RENAMED = "Read 'old.xls' as an Excel workbook: it is an .xlsx file with an .xls name."
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 504


def _xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in (["Line Item", "Budget", "Actual", "Type"], ["Revenue", 100, 110, "Revenue"]):
        sheet.append(row)
    capture = io.BytesIO()
    workbook.save(capture)
    return capture.getvalue()


def test_an_xlsx_named_xls_is_read_as_an_xlsx_with_a_note() -> None:
    result = read_input_assisted(_xlsx(), ".xls", filename="old.xls")
    assert not result.has_fatal_errors, result.fatal_error_message
    assert result.rows[0]["actual"] == 110
    assert result.visible_transformations[0] == RENAMED


@pytest.mark.parametrize(("data", "message"), [
    (OLE2, BIFF),
    (b"<html><body><table><tr><td>Revenue</td></tr></table></body></html>", WEB_XLS),
    (b"\xef\xbb\xbf  <!DOCTYPE html>\n<html></html>", WEB_XLS),
    (b"Line Item\tBudget\tActual\nRevenue\t100\t110\n", OTHER_XLS),
])
def test_an_xls_that_is_not_a_workbook_names_the_fix(data: bytes, message: str) -> None:
    result = read_input_assisted(data, ".xls", filename="old.xls")
    assert result.has_fatal_errors
    assert result.fatal_error_message == message


@pytest.mark.parametrize("suffix", [".htm", ".html"])
def test_a_web_filing_names_what_to_upload_instead(suffix: str) -> None:
    result = read_input_assisted(b"<html></html>", suffix, filename=f"filing{suffix}")
    assert result.fatal_error_message == HTM.replace("filing.htm", f"filing{suffix}")


def _run(path: Path, *extra: str) -> list[str]:
    return [str(path), "--period", "X", "--dollar-threshold", "1", "--percent-threshold", "1", *extra]


@pytest.mark.parametrize("assisted", [(), ("--assisted",)])
def test_the_cli_reads_a_renamed_xlsx_in_both_modes(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                    assisted: tuple[str, ...]) -> None:
    path = tmp_path / "old.xls"
    path.write_bytes(_xlsx())
    assert cli.main(_run(path, *assisted)) == 0
    assert "Revenue" in capsys.readouterr().out


@pytest.mark.parametrize("assisted", [(), ("--assisted",)])
def test_the_cli_refuses_a_legacy_workbook_with_the_save_as_fix(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                                assisted: tuple[str, ...]) -> None:
    path = tmp_path / "old.xls"
    path.write_bytes(OLE2)
    with pytest.raises(SystemExit) as stopped:
        cli.main(_run(path, *assisted))
    assert stopped.value.code == 2
    assert capsys.readouterr().err == f"variance-agent: error: {BIFF}\n"


@pytest.mark.parametrize(("assisted", "message"), [((), STRICT_HTM), (("--assisted",), HTM)])
def test_the_cli_refuses_a_web_page_that_is_not_a_filing(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                         assisted: tuple[str, ...], message: str) -> None:
    path = tmp_path / "filing.htm"
    path.write_bytes(b"<html></html>")
    with pytest.raises(SystemExit) as stopped:
        cli.main(_run(path, *assisted))
    assert stopped.value.code == 2
    assert capsys.readouterr().err == f"variance-agent: error: {message}\n"


def test_the_chat_explains_a_legacy_workbook() -> None:
    response = handle_upload(Session(), OLE2, "old.xls")
    assert response.level == "error"
    assert response.text == BIFF


def test_the_page_lets_these_files_reach_the_reader() -> None:
    script = (Path(__file__).resolve().parents[1] / "src/variance_agent/static/chat.js").read_text("utf-8")
    assert "const VALID_EXTENSIONS = ['.csv', '.json', '.xlsx', '.xlsm', '.xls', '.pdf', '.htm', '.html'];" in script
