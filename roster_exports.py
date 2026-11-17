"""
In-memory PDF / XLSX exports for recurring rosters.

Both builders return bytes; nothing touches disk. The PDF reuses PACE's
PDF_Template (CUI banner, logo, CUI disclaimer footer, header colour, fonts)
with a roster-specific header and a "Page X of Y" footer.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Frame, PageTemplate, Paragraph, Table, TableStyle

from constants import (
    BODY_FONT, BOLD_FONT, PDF_CONTENT_FRAME_WIDTH, PDF_CUI_HEADER, PDF_FONT_SIZE_CUI,
    PDF_FONT_SIZE_FOOTER_BOTTOM, PDF_FOOTER_BOTTOM_Y, PDF_FOOTER_BORDER_Y, PDF_FOOTER_CUI,
    PDF_HEADER_COLOR, PDF_HEADER_CUI_Y, PDF_HEADER_MAIN_Y, PDF_LOGO_SIZE, PDF_LOGO_X, PDF_MARGIN,
    PDF_PAGE_HEIGHT, PDF_PAGE_WIDTH, date_display_format, default_logo, images_dir,
)
from pdf_templates import PDF_Template
from roster_rules import RosterResult

PDF_DATE_FORMAT = "%d-%b-%Y"  # PACE display format, e.g. 15-MAR-2024
_TEXT_WEIGHTS = {"full_name": 2.2, "unit": 2.0, "re_description": 2.0, "requirement_basis": 1.5}


def _display(value, kind: str) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime(PDF_DATE_FORMAT).upper()
    return str(value)


# =============================================================================
# PDF
# =============================================================================

class _NumberedCanvas(rl_canvas.Canvas):
    """Defers page output so each page can show 'Page X of Y'."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            text = f"Page {self._pageNumber} of {total}"
            self.setFont(BOLD_FONT, PDF_FONT_SIZE_FOOTER_BOTTOM)
            self.setFillColorRGB(0, 0, 0)
            width = stringWidth(text, BOLD_FONT, PDF_FONT_SIZE_FOOTER_BOTTOM)
            self.drawString(PDF_PAGE_WIDTH - PDF_MARGIN - width, PDF_FOOTER_BOTTOM_Y, text)
            super().showPage()
        super().save()


class RosterReportDocument(PDF_Template):
    """Landscape CUI report: PACE header/footer style with roster title, as-of, params, count."""

    HEADER_BOTTOM = PDF_PAGE_HEIGHT - 1.75 * inch
    FRAME_BOTTOM = PDF_FOOTER_BORDER_Y + 0.1 * inch

    def __init__(self, buffer, result: RosterResult, **kwargs):
        super().__init__(buffer, cycle=None, melYear=None, **kwargs)
        self.result = result
        self.logo_path = os.path.join(images_dir, default_logo)
        self.pas_info = {}
        # Own frame so table rows never overlap the footer rule or header block.
        frame = Frame(
            PDF_MARGIN, self.FRAME_BOTTOM, PDF_CONTENT_FRAME_WIDTH,
            self.HEADER_BOTTOM - self.FRAME_BOTTOM, id="roster",
        )
        self.pageTemplates = []
        self.addPageTemplates([PageTemplate(id="roster", frames=[frame], onPage=self.add_page_elements)])

    def add_header(self, canvas, doc):
        canvas.setFont(BOLD_FONT, PDF_FONT_SIZE_CUI)
        canvas.drawCentredString(self.page_width / 2, PDF_HEADER_CUI_Y, PDF_CUI_HEADER)
        self._add_logo(canvas, doc, PDF_HEADER_MAIN_Y)

        r = self.result
        x = PDF_LOGO_X + PDF_LOGO_SIZE + 0.25 * inch
        max_width = self.page_width - PDF_MARGIN - x
        canvas.setFillColorRGB(0, 0, 0)
        canvas.setFont(BOLD_FONT, 16)
        canvas.drawString(x, PDF_PAGE_HEIGHT - 0.75 * inch, r.rule.title)
        canvas.setFont(BOLD_FONT, 11)
        noun = "member" if len(r.rows) == 1 else "members"
        canvas.drawString(
            x, PDF_PAGE_HEIGHT - 1.0 * inch,
            f"As of {r.as_of.strftime(PDF_DATE_FORMAT).upper()}    |    {len(r.rows)} {noun}",
        )
        params = "Parameters: " + "; ".join(f"{label}: {value}" for label, value in r.param_summary())
        canvas.setFont(BODY_FONT, 9)
        y = PDF_PAGE_HEIGHT - 1.2 * inch
        for line in _wrap(params, BODY_FONT, 9, max_width)[:3]:
            canvas.drawString(x, y, line)
            y -= 11

    def _add_bottom_footer(self, canvas, doc):
        canvas.setFillColorRGB(0, 0, 0)
        canvas.setFont(BOLD_FONT, PDF_FONT_SIZE_FOOTER_BOTTOM)
        canvas.drawString(PDF_MARGIN, PDF_FOOTER_BOTTOM_Y, datetime.now().strftime(date_display_format))
        width = stringWidth(PDF_FOOTER_CUI, BOLD_FONT, PDF_FONT_SIZE_FOOTER_BOTTOM)
        canvas.drawString((self.page_width - width) / 2, PDF_FOOTER_BOTTOM_Y, PDF_FOOTER_CUI)
        # "Page X of Y" is drawn by _NumberedCanvas once the total is known.


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if stringWidth(trial, font, size) <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def build_pdf(result: RosterResult) -> bytes:
    buffer = BytesIO()
    doc = RosterReportDocument(
        buffer, result,
        rightMargin=PDF_MARGIN, leftMargin=PDF_MARGIN, topMargin=PDF_MARGIN, bottomMargin=PDF_MARGIN,
        title=result.rule.title, author="PACE", subject="CUI",
    )
    header_style = ParagraphStyle("rh", fontName=BOLD_FONT, fontSize=9, leading=11, textColor=colors.white)
    body_style = ParagraphStyle("rb", fontName=BODY_FONT, fontSize=9, leading=11)
    story = []

    if not result.rows:
        story.append(Paragraph(
            f"No members matched this roster as of {result.as_of.strftime(PDF_DATE_FORMAT).upper()}.",
            ParagraphStyle("empty", fontName=BODY_FONT, fontSize=11, leading=14),
        ))
    else:
        cols = result.columns
        weights = [_TEXT_WEIGHTS.get(c.key, 1.0) for c in cols]
        total = sum(weights)
        widths = [PDF_CONTENT_FRAME_WIDTH * w / total for w in weights]
        data = [[Paragraph(escape(c.label), header_style) for c in cols]]
        for row in result.rows:
            data.append([
                Paragraph(escape(_display(row.get(c.key), c.kind)), body_style) if c.kind == "text"
                else _display(row.get(c.key), c.kind)
                for c in cols
            ])
        table = Table(data, colWidths=widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PDF_HEADER_COLOR),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 1), (-1, -1), BODY_FONT),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.96, 0.98)]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)

    if result.warnings:
        story.append(Paragraph("<br/>Notes: " + escape(" ".join(result.warnings)), body_style))

    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


# =============================================================================
# XLSX
# =============================================================================

_HEADER_FILL = PatternFill("solid", fgColor="17365D")
_XLSX_DATE_FORMAT = "DD-MMM-YYYY"


def _set_cell(ws, row: int, col: int, value):
    cell = ws.cell(row=row, column=col, value=value)
    # openpyxl treats any str starting with "=" as a formula; force literal text.
    if isinstance(value, str) and value.startswith("="):
        cell.data_type = "s"
    return cell


def build_xlsx(result: RosterResult) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Roster"
    cols = result.columns

    for j, col in enumerate(cols, start=1):
        cell = _set_cell(ws, 1, j, col.label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    widths = [len(c.label) for c in cols]
    for i, row in enumerate(result.rows, start=2):
        for j, col in enumerate(cols, start=1):
            value = row.get(col.key)
            if value == "":
                value = None
            cell = _set_cell(ws, i, j, value)
            if isinstance(value, date):
                cell.number_format = _XLSX_DATE_FORMAT
                widths[j - 1] = max(widths[j - 1], 11)
            elif value is not None:
                widths[j - 1] = max(widths[j - 1], len(str(value)))

    for j, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = min(max(width + 2, 8), 45)
    ws.freeze_panes = "A2"
    if result.rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(result.rows) + 1}"
    ws.oddHeader.center.text = "CUI"
    ws.oddFooter.center.text = "CUI"
    ws.oddFooter.right.text = "Page &P of &N"
    ws.page_setup.orientation = "landscape"
    ws.print_title_rows = "1:1"

    info = wb.create_sheet("Report Info")
    info_rows = [
        ("Marking", "CUI"),
        ("Roster", result.rule.title),
        ("Roster ID", result.rule.id),
        ("As of", result.as_of),
        ("Row count", len(result.rows)),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]
    info_rows += [(f"Parameter: {label}", value) for label, value in result.param_summary()]
    citations = sorted({p.citation for p in result.rule.params if p.citation})
    info_rows += [("Citation", c) for c in citations]
    info_rows += [("Note", w) for w in result.warnings]
    for i, (key, value) in enumerate(info_rows, start=1):
        _set_cell(info, i, 1, key).font = Font(bold=True)
        cell = _set_cell(info, i, 2, value)
        if isinstance(value, date):
            cell.number_format = _XLSX_DATE_FORMAT
    info.column_dimensions["A"].width = 48
    info.column_dimensions["B"].width = 60
    info.oddHeader.center.text = "CUI"
    info.oddFooter.center.text = "CUI"

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
