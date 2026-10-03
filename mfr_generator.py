"""
mfr_generator.py
USAF Memorandum for Record (MFR) PDF Generator
Per AFH 33-337 (The Tongue and Quill)

Header layout: seal + org info CENTERED per T&Q standard.
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

from constants import (
    BODY_FONT, BOLD_FONT,
    MFR_PAGE_WIDTH, MFR_PAGE_HEIGHT, MFR_MARGIN,
    MFR_SEAL_IMAGE, MFR_SEAL_SIZE,
    MFR_FONT_SIZE_HEADER, MFR_FONT_SIZE_BODY, MFR_FONT_SIZE_LABEL,
    MFR_LINE_HEIGHT, MFR_SIGNATURE_INDENT, MFR_SIGNATURE_GAP,
    MFR_DATE_FORMAT, MFR_DEPT_LINE, MFR_TITLE,
    images_dir,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_date(iso_date: str) -> str:
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
        return d.strftime("%-d %b %Y")
    except Exception:
        return iso_date


def _wrap_text(text: str, font: str, size: float, max_width: float) -> list:
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [""]


def _new_page(c, page_width, page_height):
    c.showPage()
    return page_height - MFR_MARGIN


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_mfr_pdf(mfr_data: dict, output_path: str) -> str:
    """
    Generate a USAF Memorandum for Record PDF per AFH 33-337.

    mfr_data keys:
        organization   : str   Unit/org name (centered in letterhead)
        base_location  : str   Base, State ZIP (optional, centered)
        date           : str   ISO date YYYY-MM-DD
        office_symbol  : str   FROM line
        memo_for       : str   Recipient name/title (leave blank for RECORD)
        subject        : str   SUBJECT line
        paragraphs     : list  Body paragraphs (auto-numbered if >1)
        signer_name    : str   Full name (auto-uppercased)
        signer_rank    : str   Rank abbreviation
        signer_branch  : str   USAF / ANG / AFRC
        signer_title   : str   Position/title
    """
    w, h = MFR_PAGE_WIDTH, MFR_PAGE_HEIGHT
    margin = MFR_MARGIN
    content_width = w - 2 * margin
    center_x = w / 2

    c = pdf_canvas.Canvas(output_path, pagesize=letter)
    c.setTitle("Memorandum for Record")

    # -----------------------------------------------------------------------
    # HEADER — centered letterhead block (T&Q standard)
    # -----------------------------------------------------------------------
    seal_path = os.path.join(images_dir, MFR_SEAL_IMAGE)
    seal_size = MFR_SEAL_SIZE

    header_top = h - margin   # y of top of printable area

    # --- Seal centered ---
    seal_x = margin
    seal_y = header_top - seal_size   # bottom-left corner of seal image
    if os.path.exists(seal_path):
        c.drawImage(
            seal_path,
            seal_x, seal_y,
            width=seal_size,
            height=seal_size,
            preserveAspectRatio=True,
            mask='auto',
        )

    # --- Text block below seal ---
    lh = MFR_LINE_HEIGHT
    text_y = header_top  # text starts at top of seal image

    # "DEPARTMENT OF THE AIR FORCE" — Bold, centered
    c.setFont(BOLD_FONT, MFR_FONT_SIZE_HEADER)
    text_y -= lh  # first line: DEPT OF THE AIR FORCE
    c.drawCentredString(center_x, text_y, MFR_DEPT_LINE)

    # Organization name — regular, centered (user input, not hardcoded)
    organization = mfr_data.get('organization', '').strip()
    if organization:
        c.setFont(BODY_FONT, MFR_FONT_SIZE_HEADER)
        text_y -= lh
        c.drawCentredString(center_x, text_y, organization)

    # Base / location line — regular, centered (optional)
    base_location = mfr_data.get('base_location', '').strip()
    if base_location:
        c.setFont(BODY_FONT, MFR_FONT_SIZE_HEADER)
        text_y -= lh
        c.drawCentredString(center_x, text_y, base_location)

    # Date — right-aligned, one line below the header block (seal + text)
    date_str = _format_date(mfr_data.get('date', ''))
    c.setFont(BODY_FONT, MFR_FONT_SIZE_BODY)
    date_y = min(text_y, seal_y) - lh * 1.5
    c.drawRightString(w - margin, date_y, date_str)

    y = date_y - lh * 2

    # -----------------------------------------------------------------------
    # TITLE LINE
    # "MEMORANDUM FOR RECORD" or "MEMORANDUM FOR [recipient]"
    # -----------------------------------------------------------------------
    memo_for = mfr_data.get('memo_for', '').strip()
    if memo_for:
        title_line = f"MEMORANDUM FOR {memo_for.upper()}"
    else:
        title_line = MFR_TITLE  # "MEMORANDUM FOR RECORD"

    c.setFont(BOLD_FONT, MFR_FONT_SIZE_BODY)
    c.drawString(margin, y, title_line)
    y -= lh * 2

    # -----------------------------------------------------------------------
    # FROM line
    # -----------------------------------------------------------------------
    label_font = BOLD_FONT
    label_size = MFR_FONT_SIZE_LABEL
    body_size  = MFR_FONT_SIZE_BODY

    from_label = "FROM:  "
    c.setFont(label_font, label_size)
    c.drawString(margin, y, from_label)
    c.setFont(BODY_FONT, body_size)
    c.drawString(margin + stringWidth(from_label, label_font, label_size), y,
                 mfr_data.get('office_symbol', ''))
    y -= lh * 1.5

    # -----------------------------------------------------------------------
    # SUBJECT line (wraps)
    # -----------------------------------------------------------------------
    subj_label = "SUBJECT:  "
    subj_x = margin + stringWidth(subj_label, label_font, label_size)
    subj_max_w = content_width - (subj_x - margin)

    c.setFont(label_font, label_size)
    c.drawString(margin, y, subj_label)

    subject_lines = _wrap_text(mfr_data.get('subject', ''), BODY_FONT, body_size, subj_max_w)
    c.setFont(BODY_FONT, body_size)
    for i, line in enumerate(subject_lines):
        if i == 0:
            c.drawString(subj_x, y, line)
        else:
            y -= lh
            c.drawString(subj_x, y, line)
    y -= lh * 2

    # -----------------------------------------------------------------------
    # BODY PARAGRAPHS
    # -----------------------------------------------------------------------
    paragraphs = [p for p in mfr_data.get('paragraphs', []) if p.strip()]
    multi = len(paragraphs) > 1

    for idx, para_text in enumerate(paragraphs):
        if y < margin + 1.5 * inch:
            y = _new_page(c, w, h)

        if multi:
            prefix = f"{idx + 1}.  "
            c.setFont(BOLD_FONT, body_size)
            c.drawString(margin, y, prefix)
            para_x = margin + stringWidth(prefix, BOLD_FONT, body_size)
        else:
            para_x = margin

        para_max_w = content_width - (para_x - margin)
        lines = _wrap_text(para_text, BODY_FONT, body_size, para_max_w)

        c.setFont(BODY_FONT, body_size)
        for i, line in enumerate(lines):
            if y < margin + 0.75 * inch:
                y = _new_page(c, w, h)
            c.drawString(para_x if i == 0 else margin, y, line)
            y -= lh
        y -= lh

    # -----------------------------------------------------------------------
    # SIGNATURE BLOCK (right-indented at MFR_SIGNATURE_INDENT)
    # -----------------------------------------------------------------------
    sig_needed = MFR_SIGNATURE_GAP * lh + 3 * lh
    if y < margin + sig_needed:
        y = _new_page(c, w, h)

    y -= MFR_SIGNATURE_GAP * lh

    signer_name   = mfr_data.get('signer_name',   '').upper()
    signer_rank   = mfr_data.get('signer_rank',   '')
    signer_branch = mfr_data.get('signer_branch', 'USAF')
    signer_title  = mfr_data.get('signer_title',  '')

    sig_line = f"{signer_name}, {signer_rank}, {signer_branch}"

    c.setFont(BOLD_FONT, body_size)
    c.drawString(MFR_SIGNATURE_INDENT, y, sig_line)
    y -= lh

    c.setFont(BODY_FONT, body_size)
    c.drawString(MFR_SIGNATURE_INDENT, y, signer_title)

    c.save()
    return output_path
