"""
In-memory PDF / XLSX exports for the roster runs. Nothing touches disk.

PDF: landscape, PACE CUI look (CUI banner, logo, header colour, CUI
disclaimer footer, date / CUI / "Page X of Y" bottom line — same as the
Initial MEL and recurring-roster exports) plus the run's exact screening-aid
footer on every page. BTZ adds an MPF summary page, unit pages with fillable
Nominate / Do Not Nominate checkboxes (PyMuPDF widgets) and a commander
signature block.

XLSX: one sheet per table, real date cells formatted DD-MMM-YYYY, a footer /
notes row under each table, CUI header/footer, and a Report Info sheet.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

import fitz  # PyMuPDF
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    CondPageBreak, Flowable, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table,
    TableStyle,
)

from config.retention import CSS_PSDG, RULE_REFERENCES
from constants import (
    BODY_FONT, BOLD_FONT, PDF_CONTENT_FRAME_WIDTH, PDF_CUI_HEADER, PDF_FONT_SIZE_CUI,
    PDF_FONT_SIZE_FOOTER, PDF_FONT_SIZE_FOOTER_BOTTOM, PDF_FOOTER_BORDER_Y, PDF_FOOTER_BOTTOM_Y,
    PDF_FOOTER_CUI, PDF_HEADER_COLOR, PDF_HEADER_CUI_Y, PDF_HEADER_MAIN_Y, PDF_LOGO_SIZE, PDF_LOGO_X,
    PDF_MARGIN, PDF_PAGE_HEIGHT, date_display_format, default_logo, images_dir,
)
from pdf_templates import PDF_Template
from roster_exports import _NumberedCanvas, _set_cell, _wrap

from .common import INDEFINITE, Bucket, Column, RunResult, display_date

PDF_MEDIA_TYPE = "application/pdf"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_SCREENING_Y = 0.52 * inch
_CHECKBOX = 10  # points
_MIN_DATE_WIDTH = 54  # points: "15-JAN-2024" at 7.5pt plus padding


def quota_text(value) -> str:
    """BTZ quotas are exact 15% values (owner: no rounding) — always two decimals."""
    return f"{value:.2f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)


def cell_text(value, kind: str = "text") -> str:
    if value is None or value == "":
        return ""
    if kind == "decimal" and isinstance(value, (int, float)) and not isinstance(value, bool):
        return quota_text(value)
    if isinstance(value, (date, datetime)):
        return display_date(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value if v not in (None, ""))
    return str(value)


def export_filename(result: RunResult, fmt: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", result.run_id)
    extra = ""
    if result.run_id == "btz-quarterly":
        extra = "_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(result.params.get("quarter", "")))
    return f"{safe}{extra}_{result.as_of.isoformat()}.{fmt}"


# =============================================================================
# PDF
# =============================================================================

class RunReportDocument(PDF_Template):
    """Landscape CUI report for a roster run."""

    HEADER_BOTTOM = PDF_PAGE_HEIGHT - 1.8 * inch
    FRAME_BOTTOM = PDF_FOOTER_BORDER_Y + 0.1 * inch

    def __init__(self, buffer, result: RunResult, **kwargs):
        super().__init__(buffer, cycle=None, melYear=None, **kwargs)
        self.result = result
        self.logo_path = os.path.join(images_dir, default_logo)
        self.pas_info = {}
        frame = Frame(PDF_MARGIN, self.FRAME_BOTTOM, PDF_CONTENT_FRAME_WIDTH,
                      self.HEADER_BOTTOM - self.FRAME_BOTTOM, id="run")
        self.pageTemplates = []
        self.addPageTemplates([PageTemplate(id="run", frames=[frame], onPage=self.add_page_elements)])

    def add_header(self, canvas, doc):
        canvas.setFont(BOLD_FONT, PDF_FONT_SIZE_CUI)
        canvas.drawCentredString(self.page_width / 2, PDF_HEADER_CUI_Y, PDF_CUI_HEADER)
        self._add_logo(canvas, doc, PDF_HEADER_MAIN_Y)
        r = self.result
        x = PDF_LOGO_X + PDF_LOGO_SIZE + 0.25 * inch
        max_width = self.page_width - PDF_MARGIN - x
        canvas.setFillColorRGB(0, 0, 0)
        canvas.setFont(BOLD_FONT, 16)
        canvas.drawString(x, PDF_PAGE_HEIGHT - 0.72 * inch, r.title)
        canvas.setFont(BOLD_FONT, 11)
        line = f"As of {display_date(r.as_of)}"
        params = "; ".join(f"{k.replace('_', ' ')}: {cell_text(v)}" for k, v in r.params.items())
        if params:
            line += f"    |    {params}"
        if r.extra.get("pascode_filter"):
            line += f"    |    PASCODE: {', '.join(r.extra['pascode_filter'])}"
        canvas.drawString(x, PDF_PAGE_HEIGHT - 0.95 * inch, line[:160])
        canvas.setFont(BODY_FONT, 8)
        y = PDF_PAGE_HEIGHT - 1.13 * inch
        duty = f"Supports {CSS_PSDG}: " + " | ".join(r.duty)
        for text in _wrap(duty, BODY_FONT, 8, max_width)[:3]:
            canvas.drawString(x, y, text)
            y -= 10

    def add_footer(self, canvas, doc):
        super().add_footer(canvas, doc)
        canvas.setFont(BOLD_FONT, PDF_FONT_SIZE_FOOTER)
        canvas.drawCentredString(self.page_width / 2, _SCREENING_Y, self.result.footer)

    def _add_bottom_footer(self, canvas, doc):
        canvas.setFillColorRGB(0, 0, 0)
        canvas.setFont(BOLD_FONT, PDF_FONT_SIZE_FOOTER_BOTTOM)
        canvas.drawString(PDF_MARGIN, PDF_FOOTER_BOTTOM_Y, datetime.now().strftime(date_display_format))
        width = stringWidth(PDF_FOOTER_CUI, BOLD_FONT, PDF_FONT_SIZE_FOOTER_BOTTOM)
        canvas.drawString((self.page_width - width) / 2, PDF_FOOTER_BOTTOM_Y, PDF_FOOTER_CUI)
        # "Page X of Y" is drawn by _NumberedCanvas once the total is known.


_H_STYLE = ParagraphStyle("rh", fontName=BOLD_FONT, fontSize=8, leading=9.5, textColor=colors.white)
_B_STYLE = ParagraphStyle("rb", fontName=BODY_FONT, fontSize=7.5, leading=9)
_SECTION = ParagraphStyle("sec", fontName=BOLD_FONT, fontSize=12, leading=15, spaceBefore=8, spaceAfter=3,
                          textColor=PDF_HEADER_COLOR)
_SMALL = ParagraphStyle("sm", fontName=BODY_FONT, fontSize=8.5, leading=10.5, spaceAfter=3)
_SMALL_BOLD = ParagraphStyle("smb", parent=_SMALL, fontName=BOLD_FONT)


def _table_style(extra=None) -> TableStyle:
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), PDF_HEADER_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.96, 0.98)]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    return TableStyle(cmds + list(extra or []))


def _cell(value, kind) -> Paragraph:
    if kind == "list" and isinstance(value, (list, tuple)):
        text = "<br/>".join(escape(str(v)) for v in value if v not in (None, ""))
    else:
        text = escape(cell_text(value, kind))
    return Paragraph(text, _B_STYLE)


def _pdf_table(columns: list[Column], rows: list[dict], extra_cols=None, width=PDF_CONTENT_FRAME_WIDTH):
    """extra_cols: [(label, weight, factory(row_index, row) -> Flowable)] appended on the right."""
    cols = [c for c in columns if c.pdf_weight]
    extra_cols = list(extra_cols or [])
    weights = [c.pdf_weight for c in cols] + [w for _, w, _ in extra_cols]
    total = sum(weights)
    widths = [width * w / total for w in weights]
    # Dates never wrap: give date columns a minimum width, taken from the wide text columns.
    deficit = sum(max(0.0, _MIN_DATE_WIDTH - widths[i]) for i, c in enumerate(cols) if c.kind == "date")
    if deficit:
        donors = [i for i, c in enumerate(cols) if c.kind in ("list", "text") and c.pdf_weight >= 1.5]
        donor_total = sum(widths[i] for i in donors)
        for i, c in enumerate(cols):
            if c.kind == "date":
                widths[i] = max(widths[i], _MIN_DATE_WIDTH)
        for i in donors:
            widths[i] -= deficit * widths[i] / donor_total
    data = [[Paragraph(escape(c.label), _H_STYLE) for c in cols]
            + [Paragraph(escape(label), _H_STYLE) for label, _, _ in extra_cols]]
    for i, row in enumerate(rows):
        data.append([_cell(row.get(c.key), c.kind) for c in cols]
                    + [factory(i, row) for _, _, factory in extra_cols])
    extra_style = []
    if extra_cols:
        first = len(cols)
        extra_style.append(("ALIGN", (first, 1), (-1, -1), "CENTER"))
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(_table_style(extra_style))
    return table


def _section(title: str, count: int | None = None):
    text = escape(title) + (f"  ({count})" if count is not None else "")
    return Paragraph(text, _SECTION)


def _summary_lines(summary: dict) -> list[str]:
    lines = []
    for key, value in summary.items():
        if isinstance(value, dict):
            inner = ", ".join(f"{k}: {v}" for k, v in value.items())
            lines.append(f"{key.replace('_', ' ').capitalize()}: {inner or 'none'}")
        elif isinstance(value, list):
            for item in value:
                lines.append(f"{key.replace('_', ' ').capitalize()}: {item}")
        else:
            lines.append(f"{key.replace('_', ' ').capitalize()}: {cell_text(value)}")
    return lines


def _notes_block(result: RunResult) -> list:
    story = [_section("Notes")]
    for note in result.notes:
        story.append(Paragraph("&bull; " + escape(note), _SMALL))
    for warning in result.warnings:
        story.append(Paragraph("&bull; <b>Warning:</b> " + escape(warning), _SMALL))
    return story


def _bucket_story(bucket: Bucket) -> list:
    story = [CondPageBreak(1.2 * inch), _section(bucket.label, len(bucket.rows)),
             Paragraph(escape(bucket.description), _SMALL)]
    if not bucket.rows:
        story.append(Paragraph("None.", _SMALL))
    elif not bucket.pdf_rows:
        story.append(Paragraph(f"{len(bucket.rows)} member(s) — listed in the Excel export and on screen.",
                               _SMALL_BOLD))
    else:
        story.append(_pdf_table(bucket.columns, bucket.rows))
    return story


def _new_doc(buffer, result):
    return RunReportDocument(
        buffer, result,
        rightMargin=PDF_MARGIN, leftMargin=PDF_MARGIN, topMargin=PDF_MARGIN, bottomMargin=PDF_MARGIN,
        title=result.title, author="PACE", subject="CUI",
    )


def build_pdf(result: RunResult) -> bytes:
    if result.run_id == "btz-quarterly":
        return build_btz_pdf(result)
    buffer = BytesIO()
    doc = _new_doc(buffer, result)
    story = [_section("Summary")]
    summary_text = " &nbsp;|&nbsp; ".join(escape(line) for line in _summary_lines(result.summary))
    story.append(Paragraph(summary_text, _SMALL))
    story.append(_section(result.main_label, len(result.rows)))
    if result.rows:
        story.append(_pdf_table(result.columns, result.rows))
    else:
        story.append(Paragraph(f"No members matched as of {display_date(result.as_of)}.", _SMALL))
    for bucket in result.buckets:
        story.extend(_bucket_story(bucket))
    story.extend(_notes_block(result))
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()


# ----------------------------------------------------------------------------- BTZ

class _CheckboxSlot(Flowable):
    """Draws an empty box (prints on paper) and records where the fillable widget goes."""

    def __init__(self, registry: list, field_name: str, size: float = _CHECKBOX):
        super().__init__()
        self.registry = registry
        self.field_name = field_name
        self.size = size
        self.width = self.height = size

    def draw(self):
        self.canv.setLineWidth(0.8)
        self.canv.rect(0, 0, self.size, self.size, stroke=1, fill=0)
        x, y = self.canv.absolutePosition(0, 0)
        self.registry.append((self.canv.getPageNumber(), x, y, self.size, self.field_name))


def _field_token(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", text) or "NOPAS"


def _btz_summary_story(result: RunResult) -> list:
    quarter = result.extra.get("quarter", {})
    units = result.extra.get("units", [])
    cbb = result.extra.get("cbb", {})
    s = result.summary
    story = [_section("MPF Summary — " + str(quarter.get("label", "")))]
    head = ["PASCODE", "Unit", "Eligibles", "Unit size", "Quota"]
    data = [[Paragraph(h, _H_STYLE) for h in head]]
    for u in units:
        data.append([u["pascode"], Paragraph(escape(u["unit"] or ""), _B_STYLE), u["eligible_count"], u["size"],
                     quota_text(u["quota"]) if u["quota"] is not None else "CBB"])
    cbb_quota = cbb.get("quota")
    cbb_label = f" ({cbb['label']})" if cbb.get("label") else ""
    data.append([Paragraph("<b>CBB pool</b>", _B_STYLE),
                 Paragraph(escape(f"{len(cbb.get('pool_units', []))} small unit(s){cbb_label}"), _B_STYLE),
                 cbb.get("pool_total", 0), "SMALL (pooled)",
                 quota_text(cbb_quota) if cbb_quota is not None else "See CBB note"])
    data.append([Paragraph("<b>Total</b>", _B_STYLE), "", s.get("eligibles", 0), "",
                 quota_text(s.get("total_quota", 0))])
    widths = [PDF_CONTENT_FRAME_WIDTH * w for w in (0.12, 0.43, 0.12, 0.15, 0.18)]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(_table_style([
        ("ALIGN", (2, 1), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 1), (-1, -1), BODY_FONT),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("LINEABOVE", (0, -2), (-1, -2), 1, PDF_HEADER_COLOR),
    ]))
    story.append(table)
    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>CBB:</b> " + escape(str(cbb.get("note", ""))), _SMALL))
    if cbb.get("policy_note"):
        story.append(Paragraph("<b>Policy:</b> " + escape(str(cbb["policy_note"])), _SMALL))
    if cbb.get("requires_base_wide_roster"):
        story.append(Paragraph("<b>CBB math requires base-wide roster</b> — this upload covers one unit only.",
                               _SMALL))
    counts = (f"Excluded / listed separately: previously considered (GSR 5Q) {s.get('previously_considered', 0)}; "
              f"not RegAF {s.get('excluded_non_regaf', 0)}; DATA ISSUE {s.get('data_issue', 0)}. "
              f"A1Cs with a BTZ date before this quarter: {s.get('btz_date_before_quarter', 0)}; after: "
              f"{s.get('btz_date_after_quarter', 0)}. Officers excluded: {s.get('officers_excluded', 0)}.")
    story.append(Paragraph(escape(counts), _SMALL))
    story.extend(_notes_block(result))
    return story


def _signature_block(pas: str, quota_text: str) -> KeepTogether:
    line = "_" * 38
    rows = [
        [Paragraph(f"<b>Unit commander nominations</b> (unit quota: {escape(quota_text)})", _SMALL), ""],
        [Paragraph(f"Commander signature: {line}", _SMALL), Paragraph(f"Date: {'_' * 18}", _SMALL)],
        [Paragraph(f"Printed name, grade, duty title: {line}", _SMALL), ""],
    ]
    table = Table(rows, colWidths=[PDF_CONTENT_FRAME_WIDTH * 0.65, PDF_CONTENT_FRAME_WIDTH * 0.35])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, PDF_HEADER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 2), (1, 2)),
    ]))
    return KeepTogether([Spacer(1, 10), table])


def build_btz_pdf(result: RunResult) -> bytes:
    buffer = BytesIO()
    doc = _new_doc(buffer, result)
    slots: list = []
    story = _btz_summary_story(result)
    units = {u["pascode"]: u for u in result.extra.get("units", [])}

    by_unit: dict[str, list[dict]] = {}
    for row in result.rows:
        by_unit.setdefault(row["pascode"], []).append(row)
    for pas in sorted(by_unit):
        rows = by_unit[pas]
        u = units.get(pas, {})
        unit_quota = (quota_text(u["quota"]) if u.get("quota") is not None
                      else "pooled into CBB" if u.get("size") == "SMALL" else "n/a")
        token = _field_token(pas)
        story.append(PageBreak())
        story.append(_section(f"Unit {pas} — {u.get('unit') or rows[0].get('unit') or ''}"))
        story.append(Paragraph(escape(
            f"Eligibles: {len(rows)}  |  Unit size: {u.get('size', '')}  |  Quota: {unit_quota}  |  "
            f"{result.extra.get('quarter', {}).get('label', '')}"), _SMALL_BOLD))
        extra_cols = [
            ("Nominate", 0.75, lambda i, row, t=token: _CheckboxSlot(slots, f"btz_{t}_{i}_nominate")),
            ("Do Not Nominate", 0.85, lambda i, row, t=token: _CheckboxSlot(slots, f"btz_{t}_{i}_do_not_nominate")),
        ]
        story.append(_pdf_table(result.columns, rows, extra_cols))
        story.append(_signature_block(pas, unit_quota))

    if not by_unit:
        story.append(PageBreak())
        story.append(_section("Quota eligibles", 0))
        story.append(Paragraph("No RegAF A1C has a BTZ date in this quarter.", _SMALL))
    for bucket in result.buckets:
        story.append(PageBreak())
        story.extend(_bucket_story(bucket)[1:])

    doc.build(story, canvasmaker=_NumberedCanvas)
    return _add_checkbox_widgets(buffer.getvalue(), slots)


def _add_checkbox_widgets(pdf_bytes: bytes, slots: list) -> bytes:
    if not slots:
        return pdf_bytes
    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page_no, x, y, size, name in slots:
            page = pdf[page_no - 1]
            height = page.rect.height
            widget = fitz.Widget()
            widget.rect = fitz.Rect(x, height - y - size, x + size, height - y)
            widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
            widget.field_name = name
            widget.field_value = False
            widget.border_width = 1
            widget.border_color = (0, 0, 0)
            widget.fill_color = (1, 1, 1)
            page.add_widget(widget)
        return pdf.tobytes(garbage=3, deflate=True)
    finally:
        pdf.close()


# =============================================================================
# XLSX
# =============================================================================

_HEADER_FILL = PatternFill("solid", fgColor="17365D")
_XLSX_DATE_FORMAT = "DD-MMM-YYYY"


def _sheet_title(text: str, used: set) -> str:
    base = re.sub(r"[\[\]\:\*\?\/\\]", " ", text).strip()[:31] or "Sheet"
    title, n = base, 2
    while title.lower() in used:
        suffix = f" ({n})"
        title = base[:31 - len(suffix)] + suffix
        n += 1
    used.add(title.lower())
    return title


def _xlsx_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value if v not in (None, "")) or None
    if value == "":
        return None
    return value


def _write_table(ws, columns: list[Column], rows: list[dict], footer_lines: list[str],
                 extra_headers: list[str] = ()) -> None:
    headers = [c.label for c in columns] + list(extra_headers)
    for j, label in enumerate(headers, start=1):
        cell = _set_cell(ws, 1, j, label)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    widths = [len(h) for h in headers]
    for i, row in enumerate(rows, start=2):
        for j, col in enumerate(columns, start=1):
            value = _xlsx_value(row.get(col.key))
            if isinstance(value, bool):
                value = "Yes" if value else "No"
            cell = _set_cell(ws, i, j, value)
            if isinstance(value, date):
                cell.number_format = _XLSX_DATE_FORMAT
            elif col.kind == "decimal" and isinstance(value, (int, float)):
                cell.number_format = "0.00"
                widths[j - 1] = max(widths[j - 1], 12)
            elif value is not None:
                widths[j - 1] = max(widths[j - 1], min(len(str(value)), 60))
            if col.kind == "list":
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    for j, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = min(max(width + 2, 8), 60)
    ws.freeze_panes = "A2"
    last = len(rows) + 1
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{last}"
    r = last + 2
    for k, text in enumerate(footer_lines):
        cell = _set_cell(ws, r + k, 1, text)
        cell.font = Font(bold=(k == 0), italic=(k > 0))
    ws.oddHeader.center.text = "CUI"
    ws.oddFooter.center.text = "CUI"
    ws.oddFooter.right.text = "Page &P of &N"
    ws.page_setup.orientation = "landscape"
    ws.print_title_rows = "1:1"


def _info_sheet(wb, result: RunResult, used: set) -> None:
    ws = wb.create_sheet(_sheet_title("Report Info", used))
    rows = [
        ("Marking", "CUI"),
        ("Report", result.title),
        ("Run ID", result.run_id),
        ("As of", result.as_of),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Footer", result.footer),
    ]
    rows += [(f"Parameter: {k}", cell_text(v)) for k, v in result.params.items()]
    if result.extra.get("pascode_filter"):
        rows.append(("PASCODE filter", ", ".join(result.extra["pascode_filter"])))
    rows += [(f"Supports ({CSS_PSDG})", d) for d in result.duty]
    rows += [(f"Summary: {line.split(':', 1)[0]}", line.split(":", 1)[1].strip() if ":" in line else "")
             for line in _summary_lines(result.summary)]
    rows += [("Note", n) for n in result.notes]
    rows += [("Warning", w) for w in result.warnings]
    rows += [(f"Rule: {r[1]}", f"{r[2]} — {r[3]} — {r[4]}") for r in RULE_REFERENCES if r[0] == result.run_id]
    for i, (key, value) in enumerate(rows, start=1):
        _set_cell(ws, i, 1, key).font = Font(bold=True)
        cell = _set_cell(ws, i, 2, value)
        if isinstance(value, date):
            cell.number_format = _XLSX_DATE_FORMAT
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 110
    ws.oddHeader.center.text = "CUI"
    ws.oddFooter.center.text = "CUI"


def build_xlsx(result: RunResult) -> bytes:
    wb = Workbook()
    used: set = set()
    footer = [result.footer, "CUI"]

    if result.run_id == "btz-quarterly":
        ws = wb.active
        ws.title = _sheet_title("MPF Summary", used)
        units = result.extra.get("units", [])
        cbb = result.extra.get("cbb", {})
        unit_cols = [Column("pascode", "PASCODE"), Column("unit", "Unit"),
                     Column("eligible_count", "Eligibles", "int"), Column("size", "Unit size"),
                     Column("quota", "Quota (exact 15%)", "decimal"), Column("quota_note", "Quota note")]
        unit_rows = [dict(u) for u in units]
        unit_rows.append({"pascode": "CBB POOL", "unit": cbb.get("label") or "Central Base Board",
                          "eligible_count": cbb.get("pool_total", 0), "size": "SMALL (pooled)",
                          "quota": cbb.get("quota"), "quota_note": cbb.get("note", "")})
        unit_rows.append({"pascode": "TOTAL", "eligible_count": result.summary.get("eligibles", 0),
                          "quota": result.summary.get("total_quota", 0)})
        quarter = result.extra.get("quarter", {}).get("label", "")
        _write_table(ws, unit_cols, unit_rows, [result.footer, quarter] + result.notes)
        ws2 = wb.create_sheet(_sheet_title("Eligibles", used))
        _write_table(ws2, result.columns, result.rows, footer, extra_headers=["Nominate", "Do Not Nominate"])
        if result.rows:
            dv = DataValidation(type="list", formula1='"X"', allow_blank=True)
            ws2.add_data_validation(dv)
            n = len(result.columns)
            dv.add(f"{get_column_letter(n + 1)}2:{get_column_letter(n + 2)}{len(result.rows) + 1}")
    else:
        ws = wb.active
        ws.title = _sheet_title(result.main_label, used)
        _write_table(ws, result.columns, result.rows, footer + result.notes)

    for bucket in result.buckets:
        ws_b = wb.create_sheet(_sheet_title(bucket.label, used))
        _write_table(ws_b, bucket.columns, bucket.rows, [result.footer, bucket.description])
    _info_sheet(wb, result, used)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_export(result: RunResult, fmt: str) -> tuple[bytes, str]:
    if fmt == "pdf":
        return build_pdf(result), PDF_MEDIA_TYPE
    if fmt == "xlsx":
        return build_xlsx(result), XLSX_MEDIA_TYPE
    raise ValueError("format must be pdf or xlsx")


__all__ = ["INDEFINITE", "build_export", "build_pdf", "build_xlsx", "export_filename"]
