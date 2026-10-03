"""
mfr_word_generator.py
USAF Memorandum for Record (MFR) Word Document Generator
Per AFH 33-337 (The Tongue and Quill), Chapter 14
Header matches official AF letterhead format (Copperplate Gothic Bold, #2F5496)
"""

import os
from copy import deepcopy
from datetime import datetime

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from constants import (
    MFR_SEAL_IMAGE,
    MFR_DEPT_LINE,
    MFR_TITLE,
    images_dir,
)

# ── Layout / style constants ──────────────────────────────────────────────────

HDR_FONT      = "Copperplate Gothic Bold"   # AF letterhead font
HDR_PT        = 11                          # 11pt (22 half-points in XML)
HDR_COLOR     = RGBColor(0x2F, 0x54, 0x96) # #2F5496 navy blue

BODY_FONT     = "Times New Roman"
BODY_PT       = 12

# T&Q sig block: 4.5" from left page edge − 1" left margin = 3.5"
SIG_INDENT    = Inches(3.5)

# "Second line below" spacing (one blank line ≈ one line height at 12pt)
_LINE_PT      = 14

# Seal floating anchor position (EMU) — matches Pierce document exactly
_SEAL_X_EMU   = -571500   # from left margin (places seal at ~0.375" from page)
_SEAL_Y_EMU   =  524510   # from page top   (~0.573")
_SEAL_SIZE    =  962025   # 1.051" square


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_date(iso_date: str, fmt: str = "long") -> str:
    """ISO date (YYYY-MM-DD) → T&Q date string.
    fmt='long'  → '1 January 2026'
    fmt='short' → '1 Jan 2026'
    """
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
        return d.strftime("%-d %b %Y") if fmt == "short" else d.strftime("%-d %B %Y")
    except Exception:
        return iso_date


def _normalize_paras(raw: list) -> list:
    """Normalize paragraph entries to {'text': str, 'level': int}."""
    result = []
    for p in raw:
        if isinstance(p, str):
            result.append({'text': p, 'level': 0})
        elif isinstance(p, dict):
            result.append({'text': p.get('text', ''), 'level': int(p.get('level', 0))})
        else:
            result.append({'text': str(p), 'level': 0})
    return [p for p in result if p['text'].strip()]


def _para_label(level: int, counters: list, multi_main: bool = True) -> str:
    """Return T&Q paragraph label. Level-0 always numbered per T&Q Ch. 14."""
    if level == 0:
        return f"{counters[0]}."
    if level == 1:
        return f"{chr(96 + counters[1])}."
    return f"({counters[2]})"


def _hdr_font(run):
    """Apply header style: Copperplate Gothic Bold, 11pt, #2F5496."""
    run.font.name  = HDR_FONT
    run.font.size  = Pt(HDR_PT)
    run.font.color.rgb = HDR_COLOR
    run.font.bold  = True


def _body_font(run, bold: bool = False):
    """Apply body style: Times New Roman, 12pt, black."""
    run.font.name  = BODY_FONT
    run.font.size  = Pt(BODY_PT)
    run.font.bold  = bold


def _sp(para, before: float = 0, after: float = 0, line: float = _LINE_PT):
    pf = para.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after  = Pt(after)
    pf.line_spacing = Pt(line)


def _no_borders(table):
    tbl   = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    bd = OxmlElement("w:tblBorders")
    for side in ("top","left","bottom","right","insideH","insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"),   "none")
        el.set(qn("w:sz"),    "0")
        el.set(qn("w:color"), "auto")
        bd.append(el)
    tblPr.append(bd)


def _make_anchor(run, width_emu=_SEAL_SIZE, height_emu=_SEAL_SIZE,
                 pos_x=_SEAL_X_EMU, pos_y=_SEAL_Y_EMU):
    """Convert the inline picture just added to 'run' into a floating anchor."""
    drawing = run._element.find(qn("w:drawing"))
    if drawing is None:
        return
    inline = drawing.find(qn("wp:inline"))
    if inline is None:
        return

    # Collect inner elements to transplant
    NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
    extent   = inline.find(qn("wp:extent"))
    docPr    = inline.find(qn("wp:docPr"))
    cNvGFP   = inline.find(qn("wp:cNvGraphicFramePr"))
    graphic  = inline.find(f"{{{NS_A}}}graphic")

    # Build anchor
    anc = OxmlElement("wp:anchor")
    anc.set("distT",         "0")
    anc.set("distB",         "0")
    anc.set("distL",         "114300")
    anc.set("distR",         "114300")
    anc.set("simplePos",     "0")
    anc.set("relativeHeight","251658752")
    anc.set("behindDoc",     "1")
    anc.set("locked",        "1")
    anc.set("layoutInCell",  "1")
    anc.set("allowOverlap",  "1")

    sp = OxmlElement("wp:simplePos"); sp.set("x","0"); sp.set("y","0")
    anc.append(sp)

    posH = OxmlElement("wp:positionH"); posH.set("relativeFrom","margin")
    oh   = OxmlElement("wp:posOffset"); oh.text = str(pos_x)
    posH.append(oh); anc.append(posH)

    posV = OxmlElement("wp:positionV"); posV.set("relativeFrom","page")
    ov   = OxmlElement("wp:posOffset"); ov.text = str(pos_y)
    posV.append(ov); anc.append(posV)

    if extent is not None:
        anc.append(deepcopy(extent))
    else:
        ext = OxmlElement("wp:extent")
        ext.set("cx", str(width_emu)); ext.set("cy", str(height_emu))
        anc.append(ext)

    eff = OxmlElement("wp:effectExtent")
    eff.set("l","0"); eff.set("t","0"); eff.set("r","9525"); eff.set("b","9525")
    anc.append(eff)

    wrap = OxmlElement("wp:wrapNone")
    anc.append(wrap)

    if docPr  is not None: anc.append(deepcopy(docPr))
    if cNvGFP is not None: anc.append(deepcopy(cNvGFP))
    if graphic is not None: anc.append(deepcopy(graphic))

    drawing.remove(inline)
    drawing.append(anc)


def _hdr_para(container, text: str = "") -> object:
    """Add a centered header-styled paragraph (Copperplate Gothic Bold, #2F5496)."""
    p = container.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _sp(p, before=0, after=0, line=HDR_PT * 1.2)
    if text:
        _hdr_font(p.add_run(text))
    return p


def _ordinal(n: int) -> str:
    """Return ordinal string: 1 → '1st', 2 → '2nd', 3 → '3rd', 4 → '4th', etc."""
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{['th','st','nd','rd','th'][min(n % 10, 4)]}"


# ── Main generator ────────────────────────────────────────────────────────────

def generate_mfr_docx(mfr_data: dict, output_path: str) -> str:
    """
    Generate a T&Q-compliant USAF Memorandum for Record (.docx).

    mfr_data keys:
        organization    : str   Unit/org name (header line 2)
        address_line_1  : str   Unit street/box address (header line 3, optional)
        address_line_2  : str   City/state/APO ZIP (header line 4, optional)
        base_location   : str   Legacy — used as address_line_1 if address_line_1 missing
        date            : str   ISO YYYY-MM-DD
        office_symbol   : str   FROM line
        memo_for        : str   Recipient (blank → MEMORANDUM FOR  RECORD)
        subject         : str   SUBJECT line
        paragraphs      : list  Body paragraphs (numbered if >1)
        signer_name     : str   Full name (auto-uppercased)
        signer_rank     : str   Rank abbreviation
        signer_branch   : str   USAF / ANG / AFRC
        signer_title    : str   Duty title / position
    """
    doc = Document()

    # ── Page setup ────────────────────────────────────────────────────────────
    # top_margin=0.7" (like Pierce); header fills from 0.5" header_distance
    # to ~1.75" visually, pushing body content down appropriately.
    for section in doc.sections:
        section.top_margin      = Inches(1.75)
        section.bottom_margin   = Inches(1.0)
        section.left_margin     = Inches(1.0)
        section.right_margin    = Inches(1.0)
        section.header_distance = Inches(0.5)
        section.page_width      = Inches(8.5)
        section.page_height     = Inches(11.0)

    # Zero out Normal style default spacing
    normal = doc.styles["Normal"]
    normal.font.name                     = BODY_FONT
    normal.font.size                     = Pt(BODY_PT)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after  = Pt(0)

    # ── WORD HEADER ───────────────────────────────────────────────────────────
    hdr     = doc.sections[0].header
    hdr.is_linked_to_previous = False

    # Clear default empty paragraph
    for p in list(hdr._element.findall(qn("w:p"))):
        hdr._element.remove(p)

    seal_path   = os.path.join(images_dir, MFR_SEAL_IMAGE)
    seal_exists = os.path.exists(seal_path)

    # Para 1: floating seal (behind text) + "DEPARTMENT OF THE AIR FORCE" centered
    p1 = hdr.add_paragraph()
    p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _sp(p1, before=HDR_PT * 1.2, after=0, line=HDR_PT * 1.2)

    if seal_exists:
        seal_run = p1.add_run()
        seal_run.add_picture(seal_path, width=Inches(1.05))
        _make_anchor(seal_run)

    dept_run = p1.add_run(MFR_DEPT_LINE)
    _hdr_font(dept_run)

    # Para 2: organization name — centered
    org = mfr_data.get("organization", "").strip()
    if org:
        _hdr_para(hdr, org)

    # Para 3: address line 1 — centered
    addr1 = (mfr_data.get("address_line_1") or
             mfr_data.get("base_location", "")).strip()
    if addr1:
        _hdr_para(hdr, addr1)

    # Para 4: address line 2 — centered
    addr2 = mfr_data.get("address_line_2", "").strip()
    if addr2:
        _hdr_para(hdr, addr2)

    # Word requires at least one paragraph at the end of a header story
    hdr.add_paragraph()

    # ── BODY ──────────────────────────────────────────────────────────────────

    def _blank(container=doc):
        """Insert one true blank line (empty paragraph, single-spaced at body pt)."""
        bp = container.add_paragraph()
        _sp(bp, before=0, after=0, line=BODY_PT)

    # DATE — right-aligned, no space_before (position controlled by top_margin)
    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _sp(date_p, before=0, after=0)
    _body_font(date_p.add_run(_format_date(mfr_data.get("date", ""), mfr_data.get("date_format", "long"))))

    # One blank line before MEMORANDUM FOR
    _blank()

    # MEMORANDUM FOR
    memo_for  = mfr_data.get("memo_for", "").strip()
    title_str = (f"MEMORANDUM FOR  {memo_for.upper()}" if memo_for
                 else "MEMORANDUM FOR  RECORD")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _sp(p, before=0, after=0)
    _body_font(p.add_run(title_str))

    # One blank line before FROM:
    _blank()

    # FROM:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _sp(p, before=0, after=0)
    _body_font(p.add_run("FROM:  "), bold=True)
    _body_font(p.add_run(mfr_data.get("office_symbol", "")))

    # One blank line between FROM: and SUBJECT: per T&Q
    _blank()

    # SUBJECT:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    _sp(p, before=0, after=0)
    _body_font(p.add_run("SUBJECT:  "), bold=True)
    _body_font(p.add_run(mfr_data.get("subject", "")))


    # REFERENCES — T&Q Ch.14: "References:" on 2nd line below SUBJECT
    # Single reference: inline after subject title (user handles in subject field)
    # Two or more: "References:" label, then (a), (b), (c)... lettered list
    references = mfr_data.get("references", [])
    if references:
        _blank()
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _sp(p, before=0, after=0)
        _body_font(p.add_run("References:  "), bold=True)
        _body_font(p.add_run(f"(a)  {references[0]}"))
        for i, ref in enumerate(references[1:], start=1):
            rp = doc.add_paragraph()
            rp.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _sp(rp, before=0, after=0)
            rp.paragraph_format.left_indent = Inches(0.9)
            _body_font(rp.add_run(f"({chr(97 + i)})  {ref}"))

    # BODY PARAGRAPHS — T&Q Ch. 14 numbering: 1,2,3 → a,b,c → (1),(2),(3)
    # level 0: left=0,  first_line=0     → "1." at 0",    wrap at 0"
    # level 1: left=0,  first_line=0.2"  → "a." at 0.2",  wrap at 0" (flush left)
    # level 2: left=0,  first_line=0.4"  → "(1)" at 0.4", wrap at 0" (flush left)
    _LEVEL_FIRST = [None, Inches(0.2), Inches(0.4)]

    paras    = _normalize_paras(mfr_data.get("paragraphs", []))
    counters = [0, 0, 0]   # [main, sub, subsub]

    # One blank line between SUBJECT: and first body paragraph
    _blank()

    for idx, para in enumerate(paras):
        level = min(para['level'], 2)
        if level == 0: counters[0] += 1; counters[1] = 0; counters[2] = 0
        if level == 1: counters[1] += 1; counters[2] = 0
        if level == 2: counters[2] += 1

        # Always number level-0 paragraphs (even if only one)
        label = _para_label(level, counters, multi_main=True)

        # Blank line between paragraphs (not before the very first one)
        if idx > 0:
            _blank()

        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _sp(p, before=0, after=0)

        # Sub/sub-sub: first line indented to label position, wrap returns to 0"
        if _LEVEL_FIRST[level]:
            p.paragraph_format.left_indent = Inches(0)
            p.paragraph_format.first_line_indent = _LEVEL_FIRST[level]

        if label:
            _body_font(p.add_run(f"{label}  "))

        _body_font(p.add_run(para['text']))

    # SIGNATURE BLOCK
    # T&Q: 5th line below last text (4 blank lines); 4.5" from left page edge
    for _ in range(4):
        blank = doc.add_paragraph()
        _sp(blank, before=0, after=0)

    signer_name   = mfr_data.get("signer_name",   "").upper()
    signer_rank   = mfr_data.get("signer_rank",   "")
    signer_branch = mfr_data.get("signer_branch", "USAF")
    signer_title  = mfr_data.get("signer_title",  "")
    sig_line      = f"{signer_name}, {signer_rank}, {signer_branch}"

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = SIG_INDENT
    _sp(p, before=0, after=0)
    _body_font(p.add_run(sig_line))

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = SIG_INDENT
    _sp(p, before=0, after=0)
    _body_font(p.add_run(signer_title))


    # ATTACHMENTS — T&Q Ch.14: "Attachment:" / "N Attachments:" flush left,
    # on the 3rd line below the signature element (2 blank lines after title).
    attachments = mfr_data.get("attachments", [])
    if attachments:
        _blank()
        _blank()
        n = len(attachments)
        atch_label = "Attachment:" if n == 1 else f"{n} Attachments:"
        lp = doc.add_paragraph()
        _sp(lp, before=0, after=0)
        _body_font(lp.add_run(atch_label), bold=True)
        if n == 1:
            ap = doc.add_paragraph()
            _sp(ap, before=0, after=0)
            ap.paragraph_format.left_indent = Inches(0.3)
            _body_font(ap.add_run(attachments[0]))
        else:
            for i, atch in enumerate(attachments, start=1):
                ap = doc.add_paragraph()
                _sp(ap, before=0, after=0)
                _body_font(ap.add_run(f"{i}.  {atch}"))

    # ENDORSEMENTS (INDORSEMENTS) — T&Q Ch.14 indorsement format
    # Each endorsement: numbered header "1st Ind, OFFICE  DATE", body, sig block,
    # and optional sub-attachments.
    endorsements = mfr_data.get("endorsements", [])
    end_counters_level = [None, Inches(0.2), Inches(0.4)]
    for end_idx, end_data in enumerate(endorsements):
        _blank()
        _blank()

        # Header line: "1st Ind, OFFICE/SYMBOL  DD Month YYYY"
        ord_str   = _ordinal(end_idx + 1)
        end_office = end_data.get("office_symbol", "")
        end_date   = _format_date(end_data.get("date", ""), end_data.get("date_format", "long"))
        ep = doc.add_paragraph()
        ep.alignment = WD_ALIGN_PARAGRAPH.LEFT
        _sp(ep, before=0, after=0)
        _body_font(ep.add_run(f"{ord_str} Ind, {end_office}  {end_date}"), bold=True)

        # Body paragraphs
        end_paras = _normalize_paras(end_data.get("paragraphs", []))
        end_cnts  = [0, 0, 0]
        for ei, epar in enumerate(end_paras):
            level = min(epar["level"], 2)
            if level == 0: end_cnts[0] += 1; end_cnts[1] = 0; end_cnts[2] = 0
            if level == 1: end_cnts[1] += 1; end_cnts[2] = 0
            if level == 2: end_cnts[2] += 1

            if ei == 0:
                _blank()
            else:
                _blank()

            label = _para_label(level, end_cnts)
            bp = doc.add_paragraph()
            bp.alignment = WD_ALIGN_PARAGRAPH.LEFT
            _sp(bp, before=0, after=0)
            if end_counters_level[level]:
                bp.paragraph_format.left_indent = Inches(0)
                bp.paragraph_format.first_line_indent = end_counters_level[level]
            if label:
                _body_font(bp.add_run(f"{label}  "))
            _body_font(bp.add_run(epar["text"]))

        # Signature block — T&Q: 5th line below last text (4 blank lines)
        for _ in range(4):
            blank_p = doc.add_paragraph()
            _sp(blank_p, before=0, after=0)

        end_name   = end_data.get("signer_name",   "").upper()
        end_rank   = end_data.get("signer_rank",   "")
        end_branch = end_data.get("signer_branch", "USAF")
        end_title  = end_data.get("signer_title",  "")
        end_sig    = f"{end_name}, {end_rank}, {end_branch}"

        sp = doc.add_paragraph()
        sp.paragraph_format.left_indent = SIG_INDENT
        _sp(sp, before=0, after=0)
        _body_font(sp.add_run(end_sig))

        tp = doc.add_paragraph()
        tp.paragraph_format.left_indent = SIG_INDENT
        _sp(tp, before=0, after=0)
        _body_font(tp.add_run(end_title))

        # Sub-attachments for this endorsement
        end_atchs = end_data.get("attachments", [])
        if end_atchs:
            _blank()
            _blank()
            en = len(end_atchs)
            ea_label = "Attachment:" if en == 1 else f"{en} Attachments:"
            ealp = doc.add_paragraph()
            _sp(ealp, before=0, after=0)
            _body_font(ealp.add_run(ea_label), bold=True)
            if en == 1:
                eap = doc.add_paragraph()
                _sp(eap, before=0, after=0)
                eap.paragraph_format.left_indent = Inches(0.3)
                _body_font(eap.add_run(end_atchs[0]))
            else:
                for i, a in enumerate(end_atchs, start=1):
                    eap = doc.add_paragraph()
                    _sp(eap, before=0, after=0)
                    _body_font(eap.add_run(f"{i}.  {a}"))

    doc.save(output_path)
    return output_path
