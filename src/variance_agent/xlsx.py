"""Formatted Excel workbook export written with the standard library only.

The workbook is plain SpreadsheetML in a zip archive: no third-party writer, no
shared-string table (text uses inline strings, which Excel never evaluates as
formulas) and fixed zip timestamps so the same analysis yields identical bytes.
"""

from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass, field
from decimal import Context, Decimal
from xml.sax.saxutils import escape

from .audience import is_audience_result
from .measures import format_measure
from .models import MeasureKind
from .analysis import verify_result
from .comparison import basis_noun, comparison_heading
from .currencies import CURRENCY_SYMBOLS
from .limits import display_text
from .models import Aggregate, AnalysisConfig, AnalysisResult, AnalyzedRow, ComparisonBasis, LineType, Status
from .numeric import financial_context, ratio
from .report import (
    _bottom_line,
    _data_request,
    _driver_sentence,
    _money,
    _recommendation,
    _report_places,
    _threshold_number,
)

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_XML_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_MAX_CELL_TEXT = 32767
_ROW_HEIGHT = 15.0
# Excel stores doubles; 17 significant digits round-trip every double exactly.
_EXCEL_DIGITS = Context(prec=17)

# cellXfs indices, in the order _styles_xml() emits them.
S_DEFAULT = 0
S_HEADER = 1
S_HEADER_NUM = 2
S_TEXT = 3
S_MONEY = 4
S_PCT = 5
S_TEXT_RIGHT = 6
S_FAVORABLE = 7
S_UNFAVORABLE = 8
S_NEUTRAL = 9
S_TITLE = 10
S_LABEL = 11
S_SECTION = 12
S_WRAP = 13
S_NOTE = 14
S_TOTAL_LABEL = 15
S_TOTAL_MONEY = 16
S_TOTAL_PCT = 17
S_TOTAL_TEXT_RIGHT = 18
S_BODY = 19
S_VALUE_LEFT = 20
S_HEADER_CENTER = 21
S_TEXT_CENTER = 22
S_LABEL_CELL = 23
S_COUNT = 24

_STATUS_STYLE = {
    Status.FAVORABLE: S_FAVORABLE,
    Status.UNFAVORABLE: S_UNFAVORABLE,
    Status.NEUTRAL: S_NEUTRAL,
    Status.UNCLASSIFIED: S_NEUTRAL,
}
_STATUS_WORD = {
    Status.FAVORABLE: "Favorable",
    Status.UNFAVORABLE: "Unfavorable",
    Status.NEUTRAL: "Neutral",
    Status.UNCLASSIFIED: "Unclassified",
}

CellValue = str | Decimal | None


@dataclass(frozen=True)
class _Cell:
    value: CellValue
    style: int = S_DEFAULT


@dataclass(frozen=True)
class _Row:
    cells: tuple[_Cell, ...]
    height: float | None = None


@dataclass
class _Sheet:
    name: str
    widths: tuple[float, ...]
    rows: list[_Row] = field(default_factory=list)
    freeze_header: bool = False
    autofilter: bool = False
    gridlines: bool = True
    merges: list[str] = field(default_factory=list)

    def add(self, *cells: _Cell, height: float | None = None) -> int:
        self.rows.append(_Row(tuple(cells), height))
        return len(self.rows)

    def blank(self) -> None:
        self.rows.append(_Row(()))

    def add_paragraph(self, text: str, style: int, span: int) -> None:
        """Write wrapped text across the first ``span`` columns of a new row."""
        row_number = self.add(_Cell(text, style), *(_Cell(None, style) for _ in range(span - 1)),
                              height=_wrapped_height(text, sum(self.widths[:span])))
        self.merges.append(f"A{row_number}:{_column(span)}{row_number}")


def _column(index: int) -> str:
    """1-based column number to its letter name."""
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _wrapped_height(text: str, width: float) -> float:
    # Excel does not re-measure wrapped rows on open, so estimate the line count.
    per_line = max(1, int(width * 1.1))
    return max(1, math.ceil(len(text) / per_line)) * _ROW_HEIGHT


def _xml_text(value: str) -> str:
    text = display_text(value)
    if len(text) > _MAX_CELL_TEXT:
        text = text[: _MAX_CELL_TEXT - 1] + "…"
    # display_text already neutralises C0/C1 controls; drop the remaining XML-illegal code points.
    text = "".join(
        f"\\u{ord(char):04x}" if ord(char) in (0xFFFE, 0xFFFF) else char for char in text
    )
    return escape(text)


def _number(value: Decimal) -> str:
    return format(_EXCEL_DIGITS.plus(value), "f")


def _cell_xml(reference: str, cell: _Cell) -> str:
    style = f' s="{cell.style}"' if cell.style else ""
    if cell.value is None:
        return f'<c r="{reference}"{style}/>' if cell.style else ""
    if isinstance(cell.value, Decimal):
        return f'<c r="{reference}"{style}><v>{_number(cell.value)}</v></c>'
    return (f'<c r="{reference}"{style} t="inlineStr"><is>'
            f'<t xml:space="preserve">{_xml_text(cell.value)}</t></is></c>')


def _last_column(sheet: _Sheet) -> int:
    return max([len(sheet.widths)] + [len(row.cells) for row in sheet.rows])


def _sheet_xml(sheet: _Sheet, *, selected: bool) -> str:
    last_col = _column(_last_column(sheet))
    last_row = max(1, len(sheet.rows))
    view_attrs = ' tabSelected="1"' if selected else ""
    if not sheet.gridlines:
        view_attrs += ' showGridLines="0"'
    if sheet.freeze_header:
        view = (f'<sheetView{view_attrs} workbookViewId="0">'
                '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                '<selection pane="bottomLeft" activeCell="A2" sqref="A2"/></sheetView>')
    else:
        view = f'<sheetView{view_attrs} workbookViewId="0"/>'
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width:g}" customWidth="1"/>'
        for index, width in enumerate(sheet.widths, start=1)
    )
    rows = []
    for row_number, row in enumerate(sheet.rows, start=1):
        cells = "".join(
            _cell_xml(f"{_column(col)}{row_number}", cell)
            for col, cell in enumerate(row.cells, start=1)
        )
        height = f' ht="{row.height:g}" customHeight="1"' if row.height else ""
        if cells or height:
            rows.append(f'<row r="{row_number}"{height}>{cells}</row>')
    parts = [
        _XML_DECL,
        f'<worksheet xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">',
        '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>',
        f'<dimension ref="A1:{last_col}{last_row}"/>',
        f"<sheetViews>{view}</sheetViews>",
        f'<sheetFormatPr defaultRowHeight="{_ROW_HEIGHT:g}"/>',
        f"<cols>{cols}</cols>",
        f"<sheetData>{''.join(rows)}</sheetData>",
    ]
    if sheet.autofilter:
        parts.append(f'<autoFilter ref="{_autofilter_ref(sheet)}"/>')
    if sheet.merges:
        merges = "".join(f'<mergeCell ref="{ref}"/>' for ref in sheet.merges)
        parts.append(f'<mergeCells count="{len(sheet.merges)}">{merges}</mergeCells>')
    parts += [
        '<pageMargins left="0.5" right="0.5" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>',
        '<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>',
        "</worksheet>",
    ]
    return "".join(parts)


def _autofilter_bounds(sheet: _Sheet) -> tuple[str, int]:
    return _column(len(sheet.widths)), max(2, len(sheet.rows))


def _autofilter_ref(sheet: _Sheet) -> str:
    column, row = _autofilter_bounds(sheet)
    return f"A1:{column}{row}"


def _styles_xml(places: int) -> str:
    fraction = "0" * places
    money = f"#,##0.{fraction};[Red]-#,##0.{fraction}"
    fonts = [
        '<font><sz val="11"/><color rgb="FF1F2937"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="11"/><color rgb="FF1F2937"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="16"/><color rgb="FF4C1D95"/><name val="Calibri"/><family val="2"/></font>',
        '<font><i/><sz val="10"/><color rgb="FF6B7280"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="11"/><color rgb="FF065F46"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="11"/><color rgb="FF991B1B"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="11"/><color rgb="FF374151"/><name val="Calibri"/><family val="2"/></font>',
        '<font><b/><sz val="12"/><color rgb="FF4C1D95"/><name val="Calibri"/><family val="2"/></font>',
    ]
    solid = ('<fill><patternFill patternType="solid"><fgColor rgb="FF{0}"/>'
             '<bgColor indexed="64"/></patternFill></fill>')
    fills = [
        '<fill><patternFill patternType="none"/></fill>',
        '<fill><patternFill patternType="gray125"/></fill>',
        solid.format("16213E"),  # 2 header
        solid.format("D1FAE5"),  # 3 favorable
        solid.format("FEE2E2"),  # 4 unfavorable
        solid.format("F3F4F6"),  # 5 neutral
        solid.format("EDE9FE"),  # 6 section
        solid.format("F9FAFB"),  # 7 total row
    ]
    borders = [
        "<border><left/><right/><top/><bottom/><diagonal/></border>",
        ('<border><left/><right/><top/><bottom style="thin"><color rgb="FFD1D5DB"/></bottom>'
         "<diagonal/></border>"),
        ('<border><left/><right/><top style="thin"><color rgb="FF6B7280"/></top>'
         '<bottom style="double"><color rgb="FF6B7280"/></bottom><diagonal/></border>'),
    ]

    def xf(num: int = 0, font: int = 0, fill: int = 0, border: int = 0,
           horizontal: str | None = None, wrap: bool = False, top: bool = False) -> str:
        attrs = f'numFmtId="{num}" fontId="{font}" fillId="{fill}" borderId="{border}" xfId="0"'
        attrs += "".join(
            f' {name}="1"' for name, used in (
                ("applyNumberFormat", num), ("applyFont", font), ("applyFill", fill),
                ("applyBorder", border), ("applyAlignment", horizontal or wrap or top),
            ) if used
        )
        align = ""
        if horizontal or wrap or top:
            align = "<alignment"
            align += f' horizontal="{horizontal}"' if horizontal else ""
            align += ' vertical="top"' if top else ' vertical="center"'
            align += ' wrapText="1"' if wrap else ""
            align += "/>"
        return f"<xf {attrs}>{align}</xf>" if align else f"<xf {attrs}/>"

    xfs = [
        xf(),                                                     # S_DEFAULT
        xf(font=2, fill=2, horizontal="left", wrap=True),         # S_HEADER
        xf(font=2, fill=2, horizontal="right", wrap=True),        # S_HEADER_NUM
        xf(border=1, top=True),                                   # S_TEXT
        xf(num=164, border=1),                                    # S_MONEY
        xf(num=165, border=1),                                    # S_PCT
        xf(border=1, horizontal="right"),                         # S_TEXT_RIGHT
        xf(font=5, fill=3, border=1, horizontal="center"),        # S_FAVORABLE
        xf(font=6, fill=4, border=1, horizontal="center"),        # S_UNFAVORABLE
        xf(font=7, fill=5, border=1, horizontal="center"),        # S_NEUTRAL
        xf(font=3),                                               # S_TITLE
        xf(font=1, top=True),                                     # S_LABEL
        xf(font=8, fill=6),                                       # S_SECTION
        xf(border=1, wrap=True, top=True),                        # S_WRAP
        xf(font=4, wrap=True, top=True),                          # S_NOTE
        xf(font=1, fill=7, border=2),                             # S_TOTAL_LABEL
        xf(num=164, font=1, fill=7, border=2),                    # S_TOTAL_MONEY
        xf(num=165, font=1, fill=7, border=2),                    # S_TOTAL_PCT
        xf(font=1, fill=7, border=2, horizontal="right"),         # S_TOTAL_TEXT_RIGHT
        xf(wrap=True, top=True),                                  # S_BODY
        xf(horizontal="left"),                                    # S_VALUE_LEFT
        xf(font=2, fill=2, horizontal="center", wrap=True),       # S_HEADER_CENTER
        xf(border=1, horizontal="center", top=True),              # S_TEXT_CENTER
        xf(font=1, border=1, top=True),                           # S_LABEL_CELL
    ]
    assert len(xfs) == S_COUNT
    return "".join([
        _XML_DECL,
        f'<styleSheet xmlns="{_MAIN_NS}">',
        '<numFmts count="2">',
        f'<numFmt numFmtId="164" formatCode="{escape(money)}"/>',
        '<numFmt numFmtId="165" formatCode="0.0%"/>',
        "</numFmts>",
        f'<fonts count="{len(fonts)}">{"".join(fonts)}</fonts>',
        f'<fills count="{len(fills)}">{"".join(fills)}</fills>',
        f'<borders count="{len(borders)}">{"".join(borders)}</borders>',
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>',
        f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs>',
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>',
        "</styleSheet>",
    ])


def _pct_cell(percent: Decimal | None, label: str | None, *, total: bool = False) -> _Cell:
    if label:
        return _Cell(label, S_TOTAL_TEXT_RIGHT if total else S_TEXT_RIGHT)
    if percent is None:
        return _Cell("N/A", S_TOTAL_TEXT_RIGHT if total else S_TEXT_RIGHT)
    return _Cell(percent, S_TOTAL_PCT if total else S_PCT)


def _status_cell(status: Status) -> _Cell:
    return _Cell(_STATUS_WORD[status], _STATUS_STYLE[status])


def _heading(cfg: AnalysisConfig) -> str:
    """Column name for the comparison amount: 'Budget', 'Forecast' or 'Prior Period (FY2024)'."""
    return display_text(comparison_heading(cfg.comparison_basis, cfg.comparison_label))


def _against(cfg: AnalysisConfig) -> str:
    """'budget' on Budget runs, else 'the forecast' / 'the prior period'."""
    noun = basis_noun(cfg.comparison_basis)
    return noun if cfg.comparison_basis is ComparisonBasis.BUDGET else f"the {noun}"


def _evidence_label(row: AnalyzedRow) -> str:
    if row.driver_evidence is None:
        return "No driver data"
    return "Supported driver" if row.driver_evidence.reconciles else "Hypothesis (unreconciled)"


def _aggregate_cells(label: str, aggregate: Aggregate) -> tuple[_Cell, ...]:
    return (
        _Cell(label, S_TEXT),
        _Cell(aggregate.budget, S_MONEY),
        _Cell(aggregate.actual, S_MONEY),
        _Cell(aggregate.variance_dollars, S_MONEY),
        _pct_cell(aggregate.variance_percent, aggregate.percent_label),
        _status_cell(aggregate.status),
    )


def _unavailable_cells(label: str, *, total: bool = False) -> tuple[_Cell, ...]:
    text_style = S_TOTAL_TEXT_RIGHT if total else S_TEXT_RIGHT
    return (
        (_Cell(label, S_TOTAL_LABEL if total else S_TEXT),)
        + tuple(_Cell("N/A", text_style) for _ in range(4))
        + (_Cell("N/A", S_NEUTRAL),)
    )


def _summary_sheet(result: AnalysisResult, places: int) -> _Sheet:
    cfg = result.config
    symbol = CURRENCY_SYMBOLS[cfg.currency]
    unclassified = sum(row.line_type == LineType.UNCLASSIFIED for row in result.rows)
    classification_incomplete = unclassified > 0
    has_revenue = any(row.line_type == LineType.REVENUE and not row.excluded_from_aggregation
                      for row in result.rows)
    has_expenses = any(row.line_type == LineType.EXPENSE and not row.excluded_from_aggregation
                       for row in result.rows)

    sheet = _Sheet("Summary", (34, 18, 18, 18, 12, 14), gridlines=False)
    sheet.add(_Cell(f"FP&A Variance Report: {cfg.period}", S_TITLE), height=26)
    sheet.add(_Cell("Period", S_LABEL), _Cell(cfg.period))
    sheet.add(_Cell("Reporting Currency", S_LABEL), _Cell(cfg.currency))
    sheet.add(_Cell("Materiality Thresholds", S_LABEL), _Cell(
        f"{symbol}{_threshold_number(cfg.dollar_threshold, 2)} or "
        f"{_threshold_number(cfg.percent_threshold, 1, scale=2)}% of {_against(cfg)}"
    ))
    if cfg.comparison_basis is not ComparisonBasis.BUDGET:
        sheet.add(_Cell("Compared Against", S_LABEL), _Cell(_heading(cfg)))
    sheet.add(_Cell("Rows Analysed", S_LABEL), _Cell(Decimal(len(result.rows)), S_VALUE_LEFT))
    sheet.add(_Cell("Material Variances", S_LABEL),
              _Cell(Decimal(len(result.material_rows)), S_VALUE_LEFT))
    sheet.add(_Cell("Classification", S_LABEL), _Cell(
        f"Incomplete: {unclassified} Unclassified row(s)" if classification_incomplete
        else "Complete"
    ))
    sheet.blank()

    sheet.add(
        _Cell("Metric", S_HEADER), _Cell(f"{_heading(cfg)} ({cfg.currency})", S_HEADER_NUM),
        _Cell(f"Actual ({cfg.currency})", S_HEADER_NUM),
        _Cell(f"Variance ({cfg.currency})", S_HEADER_NUM), _Cell("Var %", S_HEADER_NUM),
        _Cell("Status", S_HEADER_CENTER), height=20,
    )
    for label, aggregate, present in (
        ("Total Revenue", result.revenue, has_revenue),
        ("Total Expenses", result.expenses, has_expenses),
    ):
        if classification_incomplete:
            sheet.add(*_aggregate_cells(f"{label} (classified subtotal)", aggregate))
        elif present:
            sheet.add(*_aggregate_cells(label, aggregate))
        else:
            sheet.add(*_unavailable_cells(label))

    if classification_incomplete or not has_revenue or not has_expenses:
        sheet.add(*_unavailable_cells("Net Operating Impact", total=True))
    else:
        budget_profit = result.revenue.budget - result.expenses.budget
        actual_profit = result.revenue.actual - result.expenses.actual
        impact = result.revenue.variance_dollars - result.expenses.variance_dollars
        status = (Status.FAVORABLE if impact > 0 else Status.UNFAVORABLE if impact < 0
                  else Status.NEUTRAL)
        if budget_profit != 0:
            percent: Decimal | None = ratio(impact, abs(budget_profit))
        else:
            percent = Decimal("0") if impact == 0 else None
        sheet.add(
            _Cell("Net Operating Impact", S_TOTAL_LABEL),
            _Cell(budget_profit, S_TOTAL_MONEY),
            _Cell(actual_profit, S_TOTAL_MONEY),
            _Cell(impact, S_TOTAL_MONEY),
            _pct_cell(percent, None, total=True),
            _status_cell(status),
        )
    sheet.blank()

    span = len(sheet.widths)
    sheet.add(*(_Cell("Bottom Line" if col == 0 else None, S_SECTION) for col in range(span)))
    sheet.add_paragraph(_bottom_line(
        result, classification_incomplete=classification_incomplete,
        has_revenue=has_revenue, has_expenses=has_expenses, places=places, plain=True,
    ), S_BODY, span)
    if result.warnings:
        sheet.blank()
        sheet.add(*(_Cell("Data Quality Notes" if col == 0 else None, S_SECTION)
                    for col in range(span)))
        for warning in result.warnings:
            sheet.add_paragraph(warning, S_BODY, span)
    sheet.blank()
    precision = (f" {places} decimal places preserve fractional amounts and exact "
                 "detail-to-total reconciliation." if places > 2 else "")
    sheet.add_paragraph(
        f"Amounts are in {cfg.currency}. Var % is variance divided by the absolute {basis_noun(cfg.comparison_basis)}. "
        f"Favorable means revenue above {_against(cfg)} or expenses below {_against(cfg)}." + precision
        + " Excel stores numbers in double precision; use the CSV or audit JSON export "
        "when exact decimal values are required.",
        S_NOTE, span,
    )
    return sheet


def _materiality_text(row: AnalyzedRow, result: AnalysisResult) -> str:
    cfg = result.config
    if row.materiality_reason == "absolute_amount":
        return (f"Exceeds {CURRENCY_SYMBOLS[cfg.currency]}"
                f"{_threshold_number(cfg.dollar_threshold, 2)} amount threshold")
    if row.materiality_reason == "absolute_percent":
        return f"Exceeds {_threshold_number(cfg.percent_threshold, 1, scale=2)}% threshold"
    return row.materiality_reason


def _material_sheet(result: AnalysisResult) -> _Sheet:
    currency = result.config.currency
    heading = _heading(result.config)
    sheet = _Sheet("Material Variances", (34, 13, 19, 19, 19, 12, 14, 26, 34),
                   freeze_header=True, autofilter=True)
    sheet.add(
        _Cell("Line Item", S_HEADER), _Cell("Type", S_HEADER),
        _Cell(f"{heading} ({currency})", S_HEADER_CENTER), _Cell(f"Actual ({currency})", S_HEADER_CENTER),
        _Cell(f"Variance ({currency})", S_HEADER_CENTER), _Cell("Var %", S_HEADER_CENTER),
        _Cell("Status", S_HEADER_CENTER), _Cell("Driver Evidence", S_HEADER),
        _Cell("Why Material", S_HEADER), height=20,
    )
    if not result.material_rows:
        sheet.add(_Cell("No material variances", S_TEXT))
    for row in result.material_rows:
        sheet.add(
            _Cell(row.line_item, S_TEXT), _Cell(str(row.line_type), S_TEXT),
            _Cell(row.budget, S_MONEY), _Cell(row.actual, S_MONEY),
            _Cell(row.variance_dollars, S_MONEY),
            _pct_cell(row.variance_percent, row.percent_label),
            _status_cell(row.status), _Cell(_evidence_label(row), S_TEXT),
            _Cell(_materiality_text(row, result), S_TEXT),
        )
    return sheet


def _actions_sheet(result: AnalysisResult, places: int, top_root_causes: int) -> _Sheet:
    cfg = result.config
    sheet = _Sheet("Root Causes & Actions", (6, 32, 24, 90), gridlines=False)
    sheet.add(_Cell("#", S_HEADER_CENTER), _Cell("Line Item", S_HEADER), _Cell("Evidence", S_HEADER),
              _Cell("Explanation", S_HEADER), height=20)
    top_rows = result.material_rows[:top_root_causes]
    if not top_rows:
        sheet.add(_Cell("—", S_TEXT_CENTER), _Cell("", S_TEXT), _Cell("", S_TEXT),
                  _Cell("No material variance requires root-cause analysis.", S_WRAP))
    for rank, row in enumerate(top_rows, start=1):
        sentence = _driver_sentence(row, cfg.currency, places, _heading(cfg), plain=True)
        prefix = display_text(row.line_item)
        for tag in (" (Supported driver): ", " (Hypothesis): "):
            sentence = sentence.removeprefix(prefix + tag)
        sheet.add(
            _Cell(Decimal(rank), S_TEXT_CENTER), _Cell(row.line_item, S_TEXT),
            _Cell(_evidence_label(row), S_TEXT), _Cell(sentence, S_WRAP),
            height=_wrapped_height(sentence, sheet.widths[3]),
        )
    sheet.blank()

    sheet.add(_Cell("", S_HEADER), _Cell("Action", S_HEADER), _Cell("Recommendation", S_HEADER),
              _Cell(None, S_HEADER), height=20)
    sheet.merges.append(f"C{len(sheet.rows)}:D{len(sheet.rows)}")
    actions = [
        ("Mitigation", _recommendation(result, Status.UNFAVORABLE, "Mitigation", places,
                                       plain=True).removeprefix("- Mitigation: ")),
        ("Optimization", _recommendation(result, Status.FAVORABLE, "Optimization", places,
                                         plain=True).removeprefix("- Optimization: ")),
        ("Data Request", _data_request(top_rows, plain=True)),
    ]
    for kind, text in actions:
        number = sheet.add(
            _Cell(None, S_TEXT), _Cell(kind, S_LABEL_CELL), _Cell(text, S_WRAP), _Cell(None, S_WRAP),
            height=_wrapped_height(text, sheet.widths[2] + sheet.widths[3]),
        )
        sheet.merges.append(f"C{number}:D{number}")
    return sheet


def _all_rows_sheet(result: AnalysisResult, places: int) -> _Sheet:
    cfg = result.config
    sheet = _Sheet("All Rows", (34, 13, 19, 19, 19, 12, 14, 12, 14, 22, 60),
                   freeze_header=True, autofilter=True)
    sheet.add(
        _Cell("Line Item", S_HEADER), _Cell("Type", S_HEADER),
        _Cell(f"{_heading(cfg)} ({cfg.currency})", S_HEADER_CENTER),
        _Cell(f"Actual ({cfg.currency})", S_HEADER_CENTER),
        _Cell(f"Variance ({cfg.currency})", S_HEADER_CENTER), _Cell("Var %", S_HEADER_CENTER),
        _Cell("Status", S_HEADER_CENTER), _Cell("Material", S_HEADER),
        _Cell("Excluded From Totals", S_HEADER), _Cell("Classification Source", S_HEADER),
        _Cell("Driver Evidence", S_HEADER), height=32,
    )
    for row in result.rows:
        driver = ""
        if row.driver_evidence:
            components = "; ".join(
                f"{name}: {_money(value, cfg.currency, places)}"
                for name, value in row.driver_evidence.components
            )
            state = "Reconciles" if row.driver_evidence.reconciles else "Unreconciled"
            driver = f"{row.driver_evidence.label} ({state}): {components}"
        sheet.add(
            _Cell(row.line_item, S_TEXT), _Cell(str(row.line_type), S_TEXT),
            _Cell(row.budget, S_MONEY), _Cell(row.actual, S_MONEY),
            _Cell(row.variance_dollars, S_MONEY),
            _pct_cell(row.variance_percent, row.percent_label),
            _status_cell(row.status), _Cell("Yes" if row.material else "No", S_TEXT),
            _Cell("Yes" if row.excluded_from_aggregation else "No", S_TEXT),
            _Cell(row.classification_source, S_TEXT), _Cell(driver, S_TEXT),
        )
    return sheet


def _quoted(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _package(sheets: list[_Sheet], places: int) -> bytes:
    names = [sheet.name for sheet in sheets]
    for name in names:
        if len(name) > 31 or any(char in name for char in "[]:*?/\\"):
            raise ValueError(f"Invalid worksheet name: {name!r}")
    sheet_entries = "".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(names, start=1)
    )
    defined = "".join(
        f'<definedName name="_xlnm._FilterDatabase" localSheetId="{index}" hidden="1">'
        f"{escape(_quoted(sheet.name))}!$A$1:${'$'.join(map(str, _autofilter_bounds(sheet)))}"
        "</definedName>"
        for index, sheet in enumerate(sheets) if sheet.autofilter
    )
    workbook = (
        f'{_XML_DECL}<workbook xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">'
        '<bookViews><workbookView activeTab="0"/></bookViews>'
        f"<sheets>{sheet_entries}</sheets>"
        + (f"<definedNames>{defined}</definedNames>" if defined else "")
        + "</workbook>"
    )
    workbook_rels = (
        f'{_XML_DECL}<Relationships xmlns="{_PKG_REL_NS}">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="{_REL_NS}/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(sheets) + 1)
        )
        + f'<Relationship Id="rId{len(sheets) + 1}" Type="{_REL_NS}/styles" Target="styles.xml"/>'
        + "</Relationships>"
    )
    root_rels = (
        f'{_XML_DECL}<Relationships xmlns="{_PKG_REL_NS}">'
        f'<Relationship Id="rId1" Type="{_REL_NS}/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    sheet_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
    content_types = (
        f'{_XML_DECL}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="{sheet_type}"/>'
            for index in range(1, len(sheets) + 1)
        )
        + '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )
    parts = [
        ("[Content_Types].xml", content_types),
        ("_rels/.rels", root_rels),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", workbook_rels),
        ("xl/styles.xml", _styles_xml(places)),
    ] + [
        (f"xl/worksheets/sheet{index}.xml", _sheet_xml(sheet, selected=index == 1))
        for index, sheet in enumerate(sheets, start=1)
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


@financial_context()
def render_xlsx(result: AnalysisResult, *, top_root_causes: int = 5) -> bytes:
    """Render the analysis as a formatted, deterministic Excel workbook."""
    verify_result(result)
    if isinstance(top_root_causes, bool) or not isinstance(top_root_causes, int) or top_root_causes < 1:
        raise ValueError("top_root_causes must be a positive integer.")
    places = _report_places(result)
    if is_audience_result(result):
        sheet = _Sheet("Measures", (34, 16, 20, 20, 20, 14, 14, 14), freeze_header=True, autofilter=True)
        sheet.add(*(_Cell(text, S_HEADER) for text in
                    ("Line Item", "Measure", _heading(result.config), "Actual", "Variance", "Var %", "Status", "Material")))
        for row in result.rows:
            variance = row.variance_bps if row.measure is MeasureKind.PERCENT else row.variance_dollars
            assert variance is not None
            from .report import _pct
            sheet.add(_Cell(row.line_item, S_TEXT), _Cell(str(row.measure), S_TEXT),
                      _Cell(format_measure(row.budget, row.measure, result.config.currency), S_TEXT_RIGHT),
                      _Cell(format_measure(row.actual, row.measure, result.config.currency), S_TEXT_RIGHT),
                      _Cell(format_measure(variance, row.measure, result.config.currency, variance=True), S_TEXT_RIGHT),
                      _Cell(_pct(row.budget, row.variance_dollars, row.percent_label), S_TEXT_RIGHT),
                      _status_cell(row.status), _Cell("Yes" if row.material else "No", S_TEXT))
        return _package([sheet], places)
    sheets = [
        _summary_sheet(result, places),
        _material_sheet(result),
        _actions_sheet(result, places, top_root_causes),
        _all_rows_sheet(result, places),
    ]
    return _package(sheets, places)
