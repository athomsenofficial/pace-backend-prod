import logging
import pandas as pd
import os
from reportlab.platypus import PageBreak
from reportlab.lib.units import inch

from session_manager import get_session
from constants import (
    MPF_LIST_COLUMNS, images_dir, default_logo, PDF_MARGIN, TEMP_DIR
)
from pdf_templates import PDF_Template, create_table, merge_pdfs
from pdf_utils import format_sig_name, clean_dataframe

logger = logging.getLogger(__name__)

class MPFListDocument(PDF_Template):
    """Document template for MPF List reports, inheriting from the base template."""
    def __init__(self, filename, cycle, melYear=None, **kwargs):
        super().__init__(filename, cycle, melYear, **kwargs)

# Simple table header for MPF list (no checkboxes)
MPF_LIST_HEADER_ROW = ['NAME', 'GRADE', 'UNIT', 'DAFSC', 'DOR', 'TAFMSD']

# Table widths for 6 columns (proportional)
MPF_LIST_TABLE_WIDTHS = [0.22, 0.08, 0.25, 0.12, 0.15, 0.15]

def generate_pascode_pdf(eligible_data, cycle, melYear, pascode, pas_info, output_filename, logo_path):
    """Generate a simple list-format PDF for a single pascode."""
    try:
        doc = MPFListDocument(
            output_filename, cycle=cycle, melYear=melYear,
            rightMargin=PDF_MARGIN, leftMargin=PDF_MARGIN,
            topMargin=PDF_MARGIN, bottomMargin=PDF_MARGIN
        )
        doc.logo_path = logo_path
        doc.pas_info = pas_info
        elements = []
        
        if eligible_data and len(eligible_data) > 0:
            table = create_table(doc, eligible_data, MPF_LIST_HEADER_ROW,
                                 MPF_LIST_TABLE_WIDTHS, "MPF ELIGIBLE ROSTER", len(eligible_data))
            elements.append(table)
            elements.append(PageBreak())
        
        doc.build(elements)
        return output_filename
    except Exception as e:
        logger.error(f"Error generating MPF PDF for pascode {pascode}: {e}")
        return None


def generate_small_unit_pdf(small_unit_data, senior_rater, cycle, melYear, pas_info, base_filename, logo_path):
    """Generate PDF for small unit data in MPF list format."""
    try:
        small_unit_filename = base_filename.replace('.pdf', '_small_unit.pdf')
        doc = MPFListDocument(
            small_unit_filename, cycle=cycle, melYear=melYear,
            rightMargin=PDF_MARGIN, leftMargin=PDF_MARGIN,
            topMargin=PDF_MARGIN, bottomMargin=PDF_MARGIN
        )
        
        srid_list = small_unit_data.values.tolist() if hasattr(small_unit_data, 'values') else small_unit_data
        
        doc.pas_info = {
            'srid': senior_rater.get('srid', 'N/A'),
            'fd name': senior_rater.get('senior_rater_name', 'N/A'),
            'signature_name': format_sig_name(
                senior_rater.get('senior_rater_first_name', ''),
                senior_rater.get('senior_rater_middle_name', ''),
                senior_rater.get('senior_rater_last_name', ''),
                senior_rater.get('senior_rater_name', 'N/A')
            ),
            'rank': senior_rater.get('senior_rater_rank', 'N/A'),
            'title': senior_rater.get('senior_rater_title', 'N/A'),
            'srid mpf': pas_info.get('srid mpf', 'N/A')
        }
        doc.logo_path = logo_path
        elements = []
        
        table = create_table(doc, srid_list, MPF_LIST_HEADER_ROW,
                             MPF_LIST_TABLE_WIDTHS, "MPF SENIOR RATER ROSTER", len(srid_list))
        elements.append(table)
        doc.build(elements)
        return small_unit_filename
    except Exception as e:
        logger.error(f"Error generating MPF small unit PDF: {e}")
        return None

def generate_mpf_list_pdf(session_id, output_filename, logo_path=None):
    """Generate a MPF list-format roster PDF from session data."""
    try:
        session = get_session(session_id)
        if not session:
            logger.error(f"Session {session_id} not found or expired")
            return None

        # Extract data from session
        eligible_df = clean_dataframe(session.get('eligible_df', []))
        small_unit_df = clean_dataframe(session.get('small_unit_df', []))
        
        cycle = session.get('cycle', 'SSG')
        year = session.get('year', 2025)
        pascodes = session.get('pascodes', [])
        pascode_unit_map = session.get('pascode_unit_map', {})
        senior_rater_data = session.get('senior_rater_data', {})

        if logo_path is None:
            logo_path = os.path.join(images_dir, default_logo)

        pdf_buffers = []

        # Generate PDFs for each PASCODE
        for pascode in pascodes:
            pascode_eligible = eligible_df[eligible_df['ASSIGNED_PAS'] == pascode]
            
            if pascode_eligible.empty:
                continue

            # Filter to MPF_LIST_COLUMNS
            pascode_data = pascode_eligible[MPF_LIST_COLUMNS].values.tolist()

            pas_info = senior_rater_data.get(pascode, {})
            unit_name = pascode_unit_map.get(pascode, pascode)
            
            # Generate temporary filename
            temp_filename = f"{TEMP_DIR}/mpf_{pascode}_{session_id}.pdf"
            
            pdf_file = generate_pascode_pdf(
                pascode_data, cycle, year, pascode, pas_info, temp_filename, logo_path
            )
            
            if pdf_file and os.path.exists(pdf_file):
                pdf_buffers.append(pdf_file)

        # Generate small unit PDF if needed
        if not small_unit_df.empty:
            small_unit_pascodes = small_unit_df['ASSIGNED_PAS'].unique().tolist()
            
            for pascode in small_unit_pascodes:
                pascode_small_unit = small_unit_df[small_unit_df['ASSIGNED_PAS'] == pascode]
                
                if pascode_small_unit.empty:
                    continue

                small_unit_data = pascode_small_unit[MPF_LIST_COLUMNS].values.tolist()
                
                pas_info = senior_rater_data.get(pascode, {})
                senior_rater = senior_rater_data.get(pascode, {})
                
                temp_filename = f"{TEMP_DIR}/mpf_small_{pascode}_{session_id}.pdf"
                
                small_pdf = generate_small_unit_pdf(
                    small_unit_data, senior_rater, cycle, year, pas_info, 
                    temp_filename, logo_path
                )
                
                if small_pdf and os.path.exists(small_pdf):
                    pdf_buffers.append(small_pdf)

        if not pdf_buffers:
            logger.error("No PDFs generated")
            return None

        # Merge all PDFs (merge_pdfs handles temp file cleanup)
        return merge_pdfs(pdf_buffers, output_filename)

    except Exception as e:
        logger.error(f"Error generating MPF roster PDF: {e}", exc_info=True)
        return None
