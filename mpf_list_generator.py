import pandas as pd
import os
from io import BytesIO
from fastapi.responses import StreamingResponse
from reportlab.platypus import PageBreak
from reportlab.lib.units import inch

from session_manager import get_session
from constants import (
    MPF_LIST_COLUMNS, images_dir, default_logo, PDF_MARGIN
)
from pdf_templates import PDF_Template, create_table, merge_pdfs

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
        print(f"Error generating MPF PDF for pascode {pascode}: {e}")
        return None

def _format_sig_name(first, middle, last, fallback='N/A'):
    """Format name for signature block: FIRST M. LAST"""
    first = (first or '').strip()
    middle = (middle or '').strip()
    last = (last or '').strip()
    if first or last:
        parts = []
        if first:
            parts.append(first)
        if middle:
            mi = middle if middle.endswith('.') else middle[0] + '.'
            parts.append(mi)
        if last:
            parts.append(last)
        return ' '.join(parts).upper()
    return (fallback or 'N/A').upper()


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
            'signature_name': _format_sig_name(
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
        print(f"Error generating MPF small unit PDF: {e}")
        return None

def generate_mpf_list_pdf(session_id, output_filename, logo_path=None):
    """Generate a MPF list-format roster PDF from session data."""
    try:
        session = get_session(session_id)
        if not session:
            print(f"Error: Session {session_id} not found or expired")
            return None

        # Safely get data with defaults
        def clean_dataframe(records):
            """Convert records to DataFrame if needed, filtering out soft-deleted."""
            if isinstance(records, pd.DataFrame):
                df = records.copy()
            elif isinstance(records, list):
                df = pd.DataFrame(records)
            else:
                return pd.DataFrame()

            # Filter out soft-deleted records
            if 'deleted' in df.columns:
                df = df[df['deleted'] != True]
                df = df.drop(columns=['deleted'])

            if 'FULL_NAME' in df.columns and not df.empty:
                df = df.sort_values(
                    by='FULL_NAME',
                    key=lambda s: s.astype(str).str.upper(),
                    kind='stable',
                    na_position='last',
                ).reset_index(drop=True)

            return df

        # Extract data from session
        eligible_df = clean_dataframe(session.get('eligible_df', []))
        small_unit_df = clean_dataframe(session.get('small_unit_df', []))
        
        cycle = session.get('cycle', 'SSG')
        year = session.get('year', 2025)
        pascodes = session.get('pascodes', [])
        pascode_unit_map = session.get('pascode_unit_map', {})
        senior_rater_data = session.get('senior_rater_data', {})

        if logo_path is None:
            logo_path = os.path.join(os.path.dirname(__file__), images_dir, default_logo)

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
            temp_filename = f"/tmp/mpf_{pascode}_{session_id}.pdf"
            
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
                
                temp_filename = f"/tmp/mpf_small_{pascode}_{session_id}.pdf"
                
                small_pdf = generate_small_unit_pdf(
                    small_unit_data, senior_rater, cycle, year, pas_info, 
                    temp_filename, logo_path
                )
                
                if small_pdf and os.path.exists(small_pdf):
                    pdf_buffers.append(small_pdf)

        if not pdf_buffers:
            print("Error: No PDFs generated")
            return None

        # Merge all PDFs
        final_pdf = merge_pdfs(pdf_buffers, output_filename)
        
        # Clean up temporary files
        for pdf_file in pdf_buffers:
            try:
                if os.path.exists(pdf_file):
                    os.remove(pdf_file)
            except Exception as e:
                print(f"Warning: Could not remove temporary file {pdf_file}: {e}")

        return final_pdf

    except Exception as e:
        print(f"Error generating MPF roster PDF: {e}")
        import traceback
        traceback.print_exc()
        return None
