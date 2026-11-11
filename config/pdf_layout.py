"""
PDF generation layout — fonts, dimensions, colors, table configs, MFR constants.

Changes when: the PDF format, fonts, or visual layout changes.
"""

import logging
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import landscape, letter, letter as _letter_portrait
from reportlab.lib.units import inch
from reportlab.lib import colors

# ============================================================================
# FONT MANAGEMENT
# ============================================================================

# Paths relative to project root (one level up from config/)
_project_root = os.path.dirname(os.path.dirname(__file__))
font_path = os.path.join(_project_root, 'fonts', 'calibri.ttf')
font_bold_path = os.path.join(_project_root, 'fonts', 'calibrib.ttf')

font_regular = 'Calibri'
font_bold = 'Calibri-Bold'
font_fallback = 'Helvetica'
font_fallback_bold = 'Helvetica-Bold'

pdf_fonts = (font_fallback, font_fallback_bold)

_logger = logging.getLogger(__name__)

try:
    pdfmetrics.registerFont(TTFont(font_regular, font_path))
    pdfmetrics.registerFont(TTFont(font_bold, font_bold_path))
    pdf_fonts = (font_regular, font_bold)
    _logger.info("Successfully registered custom fonts for PDF generation.")
except Exception as e:
    _logger.warning(f"Could not load custom fonts ({e}). Using fallback fonts.")

BODY_FONT, BOLD_FONT = pdf_fonts

# ============================================================================
# PAGE DIMENSIONS
# ============================================================================

PDF_PAGE_WIDTH, PDF_PAGE_HEIGHT = landscape(letter)

# Margins and spacing
PDF_MARGIN = 0.5 * inch
PDF_CONTENT_FRAME_X = PDF_MARGIN
PDF_CONTENT_FRAME_Y = 1.05 * inch
PDF_CONTENT_FRAME_WIDTH = PDF_PAGE_WIDTH - (2 * PDF_MARGIN)
PDF_CONTENT_FRAME_HEIGHT = PDF_PAGE_HEIGHT - 2.735 * inch

# Header positioning
PDF_HEADER_CUI_Y = PDF_PAGE_HEIGHT - 0.3 * inch
PDF_HEADER_MAIN_Y = PDF_PAGE_HEIGHT - 0.8 * inch
PDF_HEADER_TITLE_Y_OFFSET = 0.1 * inch
PDF_HEADER_LINE_HEIGHT = 0.2 * inch
PDF_HEADER_SIGNATURE_X = 7.5 * inch
PDF_HEADER_PROMOTION_X = 5 * inch
PDF_HEADER_UNIT_DATA_X = 2 * inch

# Logo positioning
PDF_LOGO_SIZE = 1 * inch
PDF_LOGO_X = PDF_MARGIN
PDF_LOGO_Y_OFFSET = 0.8 * inch

# Footer positioning
PDF_FOOTER_BORDER_Y = 1.2 * inch
PDF_FOOTER_TEXT_Y = 0.75 * inch
PDF_FOOTER_BOTTOM_Y = 0.3 * inch

# ============================================================================
# FONT SIZES
# ============================================================================

PDF_FONT_SIZE_CUI = 10
PDF_FONT_SIZE_HEADER = 12
PDF_FONT_SIZE_SUBHEADER = 10
PDF_FONT_SIZE_FOOTER = 8
PDF_FONT_SIZE_FOOTER_BOTTOM = 12

# ============================================================================
# COLORS
# ============================================================================

PDF_HEADER_COLOR = colors.Color(23 / 255, 54 / 255, 93 / 255)  # #17365d
PDF_CHECKBOX_BORDER_COLOR = (0, 0, 0)
PDF_CHECKBOX_FILL_COLOR = (1, 1, 1)

# ============================================================================
# TEXT CONSTANTS
# ============================================================================

PDF_CUI_HEADER = 'CUI// CONTROLLED UNCLASSIFIED INFORMATION'
PDF_FOOTER_DISCLAIMER = (
    "The information herein is FOR OFFICIAL USE ONLY (CUI) information which must be protected under "
    "the Freedom of Information Act (5 U.S.C. 552) and/or the Privacy Act of 1974 (5 U.S.C. 552a). "
    "Unauthorized disclosure or misuse of this PERSONAL INFORMATION may result in disciplinary action, "
    "criminal and/or civil penalties."
)
PDF_FOOTER_CUI = "CUI"

# ============================================================================
# TABLE CONFIGURATIONS
# ============================================================================

INITIAL_MEL_TABLE_WIDTHS = [0.22, 0.07, 0.1, 0.08, 0.23, 0.1, 0.1, 0.1]
INITIAL_MEL_INELIGIBLE_TABLE_WIDTHS = [0.22, 0.07, 0.1, 0.08, 0.3, 0.23]
ELIGIBLE_TABLE_WIDTHS = [0.26, 0.08, 0.1, 0.1, 0.26, 0.05, 0.05, 0.05, 0.05]
INELIGIBLE_TABLE_WIDTHS = [0.25, 0.08, 0.1, 0.1, 0.25, 0.2]

ELIGIBLE_HEADER_ROW = ['FULL NAME', 'GRADE', 'PASCODE', 'DAFSC', 'UNIT', 'NRN', 'P', 'MP', 'PN']
INELIGIBLE_HEADER_ROW = ['FULL NAME', 'GRADE', 'PASCODE', 'DAFSC', 'UNIT', 'REASON NOT ELIGIBLE']
INITIAL_MEL_HEADER_ROW = ['FULL NAME', 'GRADE', 'DAS', 'DAFSC', 'UNIT', 'DOR', 'TAFMSD', 'PASCODE']
INITIAL_MEL_INELIGIBLE_HEADER_ROW = ['FULL NAME', 'GRADE', 'PASCODE', 'DAFSC', 'UNIT', 'REASON']

PDF_TABLE_ROW_HEIGHT = 30
PDF_TABLE_HEADER_PADDING = 4
PDF_TABLE_BORDER_WIDTH = 0.5

# ============================================================================
# CHECKBOX CONSTANTS (Final MEL)
# ============================================================================

PDF_CHECKBOX_SIZE = 11
PDF_CHECKBOX_START_X_PERCENT = 0.79
PDF_CHECKBOX_START_Y_PERCENT = 0.276
PDF_CHECKBOX_ROW_HEIGHT_PERCENT = 0.0295
PDF_CHECKBOX_COL_WIDTH_PERCENT = 0.045
PDF_CHECKBOX_MAX_ROWS_PER_PAGE = 20

# ============================================================================
# MFR CONSTANTS (per AFH 33-337 The Tongue and Quill)
# ============================================================================

MFR_PAGE_WIDTH, MFR_PAGE_HEIGHT = _letter_portrait

MFR_MARGIN = 1.0 * inch
MFR_HEADER_HEIGHT = 1.8 * inch

MFR_SEAL_IMAGE = 'dept_of_war.png'
MFR_SEAL_SIZE = 0.9 * inch

MFR_FONT_SIZE_HEADER = 11
MFR_FONT_SIZE_BODY = 12
MFR_FONT_SIZE_LABEL = 12

MFR_LINE_HEIGHT = 18

MFR_SIGNATURE_INDENT = 4.25 * inch
MFR_SIGNATURE_GAP = 4

MFR_DATE_FORMAT = "%d %b %Y"
MFR_DEPT_LINE = "DEPARTMENT OF THE AIR FORCE"
MFR_TITLE = "MEMORANDUM FOR RECORD"
