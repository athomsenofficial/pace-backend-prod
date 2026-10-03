import io
from fastapi import APIRouter, Body, Query, UploadFile, File
from error_handling import error_response
from fastapi.responses import JSONResponse, StreamingResponse
import pandas as pd
from typing import Dict
from session_manager import get_session, update_session
from roster_processor import recalculate_small_units, rescan_and_update_pascodes
from constants import PDF_COLUMNS

router = APIRouter(tags=["Roster"])


@router.get("/roster/preview/{session_id}")
async def get_roster_preview(
    session_id: str,
    category: str = "all",
    page: int = 1,
    page_size: int = 50
):
    """
    Get roster preview for review and editing.
    Returns all member data from the session including eligible,
    ineligible, discrepancy, BTZ, and small unit members.
    """
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        def df_to_list(df, category=''):
            if df is None:
                return []

            records = []

            if isinstance(df, list):
                records = df
            elif hasattr(df, 'to_dict'):
                records = df.to_dict('records')
            else:
                return []

            cleaned_records = []
            for idx, record in enumerate(records):
                if record.get('deleted', False):
                    continue

                clean_record = {k: v for k, v in record.items()
                               if k not in ['deleted', 'deletion_reason']}

                if category:
                    clean_record['member_id'] = f'row_{category}_{len(cleaned_records)}'
                else:
                    clean_record['member_id'] = f'row_{len(cleaned_records)}'

                cleaned_records.append(clean_record)

            return cleaned_records

        eligible_df = session.get('eligible_df', [])
        ineligible_df = session.get('ineligible_df', [])
        discrepancy_df = session.get('discrepancy_df', [])
        btz_df = session.get('btz_df', [])
        small_unit_df = session.get('small_unit_df', [])
        dataframe = session.get('dataframe', [])

        statistics = {
            "total_uploaded": len(df_to_list(dataframe)),
            "total_processed": (
                len(df_to_list(eligible_df, 'eligible')) +
                len(df_to_list(ineligible_df, 'ineligible')) +
                len(df_to_list(discrepancy_df, 'discrepancy')) +
                len(df_to_list(btz_df, 'btz'))
            ),
            "eligible": len(df_to_list(eligible_df, 'eligible')),
            "ineligible": len(df_to_list(ineligible_df, 'ineligible')),
            "discrepancy": len(df_to_list(discrepancy_df, 'discrepancy')),
            "btz": len(df_to_list(btz_df, 'btz')),
            "errors": len(session.get('error_log', []))
        }

        pascode_map = session.get('pascode_map', {})
        small_unit_sr = session.get('small_unit_sr')
        srid_pascode_map = session.get('srid_pascode_map', {})
        senior_rater_needed = bool(session.get('small_unit_df'))

        response = {
            "session_id": session_id,
            "cycle": session.get('cycle', 'SSG'),
            "year": session.get('year', 2025),
            "edited": session.get('edited', False),
            "statistics": statistics,
            "categories": {
                "eligible": df_to_list(eligible_df, 'eligible'),
                "ineligible": df_to_list(ineligible_df, 'ineligible'),
                "discrepancy": df_to_list(discrepancy_df, 'discrepancy'),
                "btz": df_to_list(btz_df, 'btz'),
                "small_unit": df_to_list(small_unit_df, 'small_unit')
            },
            "errors": session.get('error_log', []),
            "pascodes": session.get('pascodes', []),
            "pascode_unit_map": session.get('pascode_unit_map', {}),
            "custom_logo": session.get('custom_logo', {
                "uploaded": False,
                "filename": None
            }),
            "pascode_map": pascode_map,
            "srid_pascode_map": srid_pascode_map,
            "small_unit_sr": small_unit_sr,
            "senior_rater_needed": senior_rater_needed
        }

        return JSONResponse(content=response)

    except Exception as e:
        return error_response(500, f"Failed to retrieve roster preview: {str(e)}", context={"session_id": session_id}, exception=e)


@router.put("/roster/member/{session_id}/{member_id}")
async def edit_roster_member(session_id: str, member_id: str, member_data: Dict):
    """Edit an existing member in the roster."""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        try:
            parts = member_id.split('_')
            if len(parts) >= 3 and parts[0] == 'row':
                category_name = parts[1]
                index = int(parts[2])
                category_key = f"{category_name}_df"
            else:
                return error_response(400, f"Invalid member_id format: {member_id}", context={"session_id": session_id, "member_id": member_id})
        except (ValueError, IndexError):
            return error_response(400, f"Invalid member_id format: {member_id}", context={"session_id": session_id, "member_id": member_id})

        data_list = session.get(category_key, [])

        if not isinstance(data_list, list):
            return error_response(404, f"Category {category_name} not found", context={"session_id": session_id, "category": category_name})

        if index >= len(data_list):
            return error_response(404, f"Member index {index} out of range for category {category_name}", context={"session_id": session_id, "index": index, "category": category_name})

        original_member = dict(data_list[index])

        filtered_updates = {}
        for key, value in member_data.items():
            if key in data_list[index]:
                filtered_updates[key] = value

        data_list[index].update(filtered_updates)

        pdf_list = session.get('pdf_dataframe', [])
        if isinstance(pdf_list, list):
            for i, pdf_member in enumerate(pdf_list):
                if (pdf_member.get('FULL_NAME') == original_member.get('FULL_NAME') and
                    pdf_member.get('SSAN') == original_member.get('SSAN')):
                    for key, value in filtered_updates.items():
                        if key in pdf_list[i]:
                            pdf_list[i][key] = value
                    break

        updates = {
            category_key: pd.DataFrame(data_list),
            'pdf_dataframe': pd.DataFrame(pdf_list) if pdf_list else pd.DataFrame(),
            'edited': True
        }
        update_session(session_id, **updates)

        rescan_and_update_pascodes(session_id)
        recalculate_small_units(session_id)

        return JSONResponse(content={
            "success": True,
            "message": "Member updated successfully",
            "member_id": member_id,
        })

    except Exception as e:
        return error_response(500, f"Failed to update member: {str(e)}", context={"session_id": session_id, "member_id": member_id}, exception=e)


@router.delete("/roster/member/{session_id}/{member_id}")
async def delete_roster_member(
    session_id: str,
    member_id: str,
    reason: str = Query(..., description="Reason for deletion"),
    hard_delete: bool = Query(False, description="Permanently delete if True")
):
    """Delete a member from the roster."""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        if not reason:
            return error_response(400, "Reason for deletion is required", context={"session_id": session_id, "member_id": member_id})

        try:
            parts = member_id.split('_')
            if len(parts) >= 3 and parts[0] == 'row':
                category_name = parts[1]
                index = int(parts[2])
                category_key = f"{category_name}_df"
            else:
                return error_response(400, f"Invalid member_id format: {member_id}", context={"session_id": session_id, "member_id": member_id})
        except (ValueError, IndexError):
            return error_response(400, f"Invalid member_id format: {member_id}", context={"session_id": session_id, "member_id": member_id})

        data_list = session.get(category_key, [])

        if not isinstance(data_list, list):
            return error_response(404, f"Category {category_name} not found", context={"session_id": session_id, "category": category_name})

        if index >= len(data_list):
            return error_response(404, f"Member index {index} out of range for category {category_name}", context={"session_id": session_id, "index": index, "category": category_name})

        # Capture member data BEFORE mutation for pdf_dataframe lookup
        deleted_member = dict(data_list[index])

        if hard_delete:
            data_list.pop(index)
        else:
            data_list[index]['deleted'] = True
            data_list[index]['deletion_reason'] = reason

        pdf_list = session.get('pdf_dataframe', [])
        if isinstance(pdf_list, list):
            for i, pdf_member in enumerate(pdf_list):
                if (pdf_member.get('FULL_NAME') == deleted_member.get('FULL_NAME') and
                    pdf_member.get('SSAN') == deleted_member.get('SSAN')):
                    if hard_delete:
                        pdf_list.pop(i)
                    else:
                        pdf_list[i]['deleted'] = True
                        pdf_list[i]['deletion_reason'] = reason
                    break

        updates = {
            category_key: pd.DataFrame(data_list) if data_list else pd.DataFrame(),
            'pdf_dataframe': pd.DataFrame(pdf_list) if pdf_list else pd.DataFrame(),
            'edited': True
        }

        update_session(session_id, **updates)
        rescan_and_update_pascodes(session_id)
        recalculate_small_units(session_id)

        return JSONResponse(content={
            "success": True,
            "message": f"Member {'permanently deleted' if hard_delete else 'marked as deleted'} successfully from {category_name}",
            "member_id": member_id,
            "category": category_name,
            "reason": reason,
            "hard_delete": hard_delete,
        })

    except Exception as e:
        return error_response(500, f"Failed to delete member: {str(e)}", context={"session_id": session_id, "member_id": member_id}, exception=e)


@router.post("/roster/member/{session_id}")
async def add_roster_member(session_id: str, data: Dict):
    """Add a new member to the roster."""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        category = data.get('category', 'eligible')
        member_data = data.get('data', {})
        reason = data.get('reason', '')
        run_eligibility_check = data.get('run_eligibility_check', True)
        senior_rater_info = data.get('senior_rater_info', {})

        if not reason:
            return error_response(400, "Reason for adding member is required", context={"session_id": session_id, "category": category})

        category_key = f"{category}_df"
        category_list = session.get(category_key, [])

        if not isinstance(category_list, list):
            category_list = []

        if category_list and len(category_list) > 0:
            template = category_list[0]
            new_member = {}

            for key in template.keys():
                if key in member_data:
                    new_member[key] = member_data[key]
                elif key == 'REASON' and category in ['ineligible', 'discrepancy']:
                    new_member[key] = reason
                elif key == 'member_id':
                    continue
                else:
                    new_member[key] = template.get(key, '')
        else:
            new_member = {}
            for col in PDF_COLUMNS:
                if col in member_data:
                    new_member[col] = member_data[col]
            if 'PAFSC' in member_data:
                new_member['PAFSC'] = member_data['PAFSC']

            if category in ['ineligible', 'discrepancy'] and 'REASON' not in new_member:
                new_member['REASON'] = reason

        if category == 'eligible':
            if not reason.lower().startswith('manual add'):
                reason = f"Manual add: {reason}"

        new_index = len(category_list)
        new_member['member_id'] = f"row_{category}_{new_index}"

        if 'ASSIGNED_PAS' in new_member:
            new_pascode = new_member['ASSIGNED_PAS']
            existing_pascodes = session.get('pascodes', [])

            pascode_updates = {}
            if new_pascode and new_pascode not in existing_pascodes:
                existing_pascodes.append(new_pascode)
                pascode_updates["pascodes"] = existing_pascodes

            if 'ASSIGNED_PAS_CLEARTEXT' in new_member:
                pascode_unit_map = session.get('pascode_unit_map', {})
                pascode_unit_map[new_pascode] = new_member['ASSIGNED_PAS_CLEARTEXT']
                pascode_updates["pascode_unit_map"] = pascode_unit_map

            if pascode_updates:
                update_session(session_id, **pascode_updates)

            if senior_rater_info and new_pascode:
                pascode_map = session.get('pascode_map', {})
                pascode_map[new_pascode] = {
                    'srid': senior_rater_info.get('SRID', ''),
                    'senior_rater_name': senior_rater_info.get('SENIOR_RATER_NAME', ''),
                    'senior_rater_rank': senior_rater_info.get('SENIOR_RATER_RANK', ''),
                    'senior_rater_title': senior_rater_info.get('SENIOR_RATER_TITLE', ''),
                    'pascode': new_pascode,
                    'unit_name': new_member.get('ASSIGNED_PAS_CLEARTEXT', '')
                }
                update_session(session_id, pascode_map=pascode_map)

        if senior_rater_info and senior_rater_info.get('SRID'):
            small_unit_sr = session.get('small_unit_sr', {})
            if not small_unit_sr:
                small_unit_sr = {
                    'srid': senior_rater_info.get('SRID', ''),
                    'senior_rater_name': senior_rater_info.get('SENIOR_RATER_NAME', ''),
                    'senior_rater_rank': senior_rater_info.get('SENIOR_RATER_RANK', ''),
                    'senior_rater_title': senior_rater_info.get('SENIOR_RATER_TITLE', '')
                }
                update_session(session_id, small_unit_sr=small_unit_sr)

        category_list.append(new_member)

        pdf_list = session.get('pdf_dataframe', [])
        if isinstance(pdf_list, list):
            pdf_new_member = new_member.copy()
            pdf_new_member.pop('member_id', None)
            pdf_list.append(pdf_new_member)
            update_session(session_id, pdf_dataframe=pd.DataFrame(pdf_list))

        update_dict = {
            category_key: pd.DataFrame(category_list),
            'edited': True
        }
        update_session(session_id, **update_dict)

        rescan_and_update_pascodes(session_id)
        recalculate_small_units(session_id)

        return JSONResponse(content={
            "success": True,
            "message": "Member added successfully",
            "member_id": member_data.get('member_id'),
            "category": category,
        })

    except Exception as e:
        return error_response(500, f"Failed to add member: {str(e)}", context={"session_id": session_id, "category": category}, exception=e)


@router.post("/roster/logo/{session_id}")
async def upload_logo(session_id: str, logo: UploadFile = File(...)):
    """Upload a custom logo for the roster"""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        allowed_types = ['image/png', 'image/jpeg', 'image/jpg']
        if logo.content_type not in allowed_types:
            return error_response(400, "Invalid file type. Only PNG and JPG files are allowed.", context={"session_id": session_id, "content_type": logo.content_type})

        logo_data = await logo.read()

        update_session(
            session_id,
            custom_logo={
                "uploaded": True,
                "filename": logo.filename,
                "content_type": logo.content_type,
                "data": logo_data.hex()
            },
            edited=True
        )

        return JSONResponse(content={
            "success": True,
            "message": "Logo uploaded successfully",
            "filename": logo.filename,
        })

    except Exception as e:
        return error_response(500, f"Failed to upload logo: {str(e)}", context={"session_id": session_id}, exception=e)


@router.get("/roster/logo/{session_id}")
async def get_logo(session_id: str):
    """Get the custom logo for the roster"""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        custom_logo = session.get('custom_logo', {})

        if not custom_logo or not custom_logo.get('uploaded'):
            return error_response(404, "No custom logo found", context={"session_id": session_id})

        logo_data = bytes.fromhex(custom_logo.get('data', ''))
        content_type = custom_logo.get('content_type', 'image/png')

        return StreamingResponse(
            io.BytesIO(logo_data),
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename={custom_logo.get('filename', 'logo.png')}"
            }
        )

    except Exception as e:
        return error_response(500, f"Failed to get logo: {str(e)}", context={"session_id": session_id}, exception=e)


@router.delete("/roster/logo/{session_id}")
async def delete_logo(session_id: str):
    """Delete the custom logo for the roster"""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        update_session(
            session_id,
            custom_logo={"uploaded": False, "filename": None},
            edited=True
        )

        return JSONResponse(content={
            "success": True,
            "message": "Logo deleted successfully",
        })

    except Exception as e:
        return error_response(500, f"Failed to delete logo: {str(e)}", context={"session_id": session_id}, exception=e)


@router.post("/roster/reprocess/{session_id}")
async def reprocess_roster(session_id: str, data: Dict = Body(...)):
    """Reprocess the roster with updated eligibility rules"""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        preserve_edits = data.get('preserve_manual_edits', True)
        categories = data.get('categories', [])

        dataframe_list = session.get('dataframe', [])
        pdf_list = session.get('pdf_dataframe', [])

        if not dataframe_list:
            return error_response(400, "No roster data found to reprocess", context={"session_id": session_id})

        dataframe = pd.DataFrame(dataframe_list)
        pdf_dataframe = pd.DataFrame(pdf_list) if pdf_list else pd.DataFrame()

        update_session(
            session_id,
            reprocessed=True,
            reprocess_timestamp=pd.Timestamp.now().isoformat(),
            edited=True
        )

        return JSONResponse(content={
            "success": True,
            "message": "Roster reprocessed successfully",
            "preserve_edits": preserve_edits,
            "categories": categories,
        })

    except Exception as e:
        return error_response(500, f"Failed to reprocess roster: {str(e)}", context={"session_id": session_id}, exception=e)
