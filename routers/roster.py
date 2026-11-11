import asyncio
import io
from fastapi import APIRouter, Body, Query, UploadFile, File
from error_handling import error_response
from fastapi.responses import JSONResponse, StreamingResponse
import pandas as pd
from typing import Dict, Optional
from session_manager import get_session, update_session
from roster_processor import roster_processor, recalculate_small_units, rescan_and_update_pascodes, recheck_member_eligibility
from constants import PDF_COLUMNS

router = APIRouter(tags=["Roster"])

VALID_CATEGORIES = {'eligible', 'ineligible', 'discrepancy', 'btz', 'small_unit'}


@router.get("/roster/preview/{session_id}")
def get_roster_preview(
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
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 50

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

                # member_id MUST encode the ORIGINAL stored index so edit/delete
                # resolve to the correct row even after we sort for display below
                # (and even when soft-deleted rows are skipped above).
                if category:
                    clean_record['member_id'] = f'row_{category}_{idx}'
                else:
                    clean_record['member_id'] = f'row_{idx}'

                # Surface the ineligible/discrepancy reason under a lowercase
                # `reason` key the frontend reads (the stored column is `REASON`).
                reason_val = record.get('REASON') or record.get('reason')
                clean_record['reason'] = reason_val if reason_val else None

                cleaned_records.append(clean_record)

            # Alphabetical by name (FULL_NAME is "LAST, FIRST") so the website
            # matches the generated PDF order and added members slot into place.
            cleaned_records.sort(key=lambda r: str(r.get('FULL_NAME', '') or '').upper())

            return cleaned_records

        eligible_df = session.get('eligible_df', [])
        ineligible_df = session.get('ineligible_df', [])
        discrepancy_df = session.get('discrepancy_df', [])
        btz_df = session.get('btz_df', [])
        small_unit_df = session.get('small_unit_df', [])
        dataframe = session.get('dataframe', [])

        # Cache df_to_list results to avoid redundant processing
        total_uploaded_list = df_to_list(dataframe)
        eligible_list = df_to_list(eligible_df, 'eligible')
        ineligible_list = df_to_list(ineligible_df, 'ineligible')
        discrepancy_list = df_to_list(discrepancy_df, 'discrepancy')
        btz_list = df_to_list(btz_df, 'btz')
        small_unit_list = df_to_list(small_unit_df, 'small_unit')

        statistics = {
            "total_uploaded": len(total_uploaded_list),
            "total_processed": (
                len(eligible_list) +
                len(ineligible_list) +
                len(discrepancy_list) +
                len(btz_list)
            ),
            "eligible": len(eligible_list),
            "ineligible": len(ineligible_list),
            "discrepancy": len(discrepancy_list),
            "btz": len(btz_list),
            "errors": len(session.get('error_log', []))
        }

        pascode_map = session.get('pascode_map', {})
        small_unit_sr = session.get('small_unit_sr')
        srid_pascode_map = session.get('srid_pascode_map', {})
        senior_rater_needed = bool(session.get('small_unit_df'))

        # Apply pagination
        all_categories = {
            "eligible": eligible_list,
            "ineligible": ineligible_list,
            "discrepancy": discrepancy_list,
            "btz": btz_list,
            "small_unit": small_unit_list
        }

        if category != "all" and category in all_categories:
            target_list = all_categories[category]
            total_records = len(target_list)
            total_pages = max(1, (total_records + page_size - 1) // page_size)
            start = (page - 1) * page_size
            end = start + page_size
            paginated = {category: target_list[start:end]}
            for k in all_categories:
                if k != category:
                    paginated[k] = []
        else:
            # Apply per-category pagination even for "all"
            paginated = {}
            total_records = 0
            for k, v in all_categories.items():
                start = (page - 1) * page_size
                end = start + page_size
                paginated[k] = v[start:end]
                total_records += len(v)
            total_pages = max(1, (max(len(v) for v in all_categories.values()) + page_size - 1) // page_size) if all_categories else 1

        response = {
            "session_id": session_id,
            "cycle": session.get('cycle', 'SSG'),
            "year": session.get('year', 2025),
            "edited": session.get('edited', False),
            "statistics": statistics,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_records": total_records,
                "total_pages": total_pages,
            },
            "categories": paginated,
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
        return error_response(500, "Failed to retrieve roster preview", context={"session_id": session_id}, exception=e)


@router.put("/roster/member/{session_id}/{member_id}")
async def edit_roster_member(session_id: str, member_id: str, member_data: Dict):
    """Edit an existing member in the roster."""
    return await asyncio.to_thread(_edit_roster_member_sync, session_id, member_id, member_data)

def _edit_roster_member_sync(session_id: str, member_id: str, member_data: Dict):
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

        if category_name not in VALID_CATEGORIES:
            return error_response(400, f"Invalid category: {category_name}", context={"session_id": session_id})

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

        # Re-check eligibility — member may need to move categories
        new_category = recheck_member_eligibility(session_id, data_list[index], category_name, index)

        rescan_and_update_pascodes(session_id)
        recalculate_small_units(session_id)

        return JSONResponse(content={
            "success": True,
            "message": "Member updated successfully",
            "member_id": member_id,
            "category_changed": new_category != category_name,
            "new_category": new_category,
        })

    except Exception as e:
        return error_response(500, "Failed to update member", context={"session_id": session_id, "member_id": member_id}, exception=e)


@router.delete("/roster/member/{session_id}/{member_id}")
async def delete_roster_member(
    session_id: str,
    member_id: str,
    reason: str = Query(..., description="Reason for deletion"),
    hard_delete: bool = Query(False, description="Permanently delete if True")
):
    """Delete a member from the roster."""
    return await asyncio.to_thread(_delete_roster_member_sync, session_id, member_id, reason, hard_delete)

def _delete_roster_member_sync(session_id, member_id, reason, hard_delete):
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

        if category_name not in VALID_CATEGORIES:
            return error_response(400, f"Invalid category: {category_name}", context={"session_id": session_id})

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
        return error_response(500, "Failed to delete member", context={"session_id": session_id, "member_id": member_id}, exception=e)


@router.post("/roster/member/{session_id}")
async def add_roster_member(session_id: str, data: Dict):
    """Add a new member to the roster."""
    return await asyncio.to_thread(_add_roster_member_sync, session_id, data)

def _add_roster_member_sync(session_id, data):
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        category = data.get('category', 'eligible')
        member_data = data.get('data', {})
        reason = data.get('reason', '')
        run_eligibility_check = data.get('run_eligibility_check', True)
        senior_rater_info = data.get('senior_rater_info', {})

        if category not in VALID_CATEGORIES:
            return error_response(400, f"Invalid category: {category}", context={"session_id": session_id})

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

        # Ensure ALL eligibility-relevant fields from the submitted data are present
        # on the new member, even when the category template only carries display
        # (PDF) columns. Without this, board_filter receives None for PAFSC / UIF /
        # REENL / AFSC and misclassifies the member — the "always placed in eligible"
        # bug. With the full data present, recheck_member_eligibility (below) runs the
        # same board_filter the initial upload uses and routes them to the right bucket.
        ELIGIBILITY_FIELDS = [
            'FULL_NAME', 'GRADE', 'DOR', 'TAFMSD', 'DATE_ARRIVED_STATION',
            'UIF_CODE', 'UIF_DISPOSITION_DATE', 'REENL_ELIG_STATUS', 'PAFSC',
            '2AFSC', '3AFSC', '4AFSC', 'ASSIGNED_PAS', 'ASSIGNED_PAS_CLEARTEXT',
            'DAFSC', 'GRADE_PERM_PROJ',
        ]
        for fld in ELIGIBILITY_FIELDS:
            if fld in member_data:
                new_member[fld] = member_data[fld]

        if category == 'eligible':
            if not reason.lower().startswith('manual add'):
                reason = f"Manual add: {reason}"

        new_index = len(category_list)
        new_member['member_id'] = f"row_{category}_{new_index}"

        # Accumulate all updates into a single dict for one update_session call
        batched_updates = {
            'edited': True
        }

        if 'ASSIGNED_PAS' in new_member:
            new_pascode = new_member['ASSIGNED_PAS']
            existing_pascodes = session.get('pascodes', [])

            if new_pascode and new_pascode not in existing_pascodes:
                existing_pascodes.append(new_pascode)
                batched_updates["pascodes"] = existing_pascodes

            if 'ASSIGNED_PAS_CLEARTEXT' in new_member:
                pascode_unit_map = session.get('pascode_unit_map', {})
                pascode_unit_map[new_pascode] = new_member['ASSIGNED_PAS_CLEARTEXT']
                batched_updates["pascode_unit_map"] = pascode_unit_map

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
                batched_updates["pascode_map"] = pascode_map

        if senior_rater_info and senior_rater_info.get('SRID'):
            small_unit_sr = session.get('small_unit_sr', {})
            if not small_unit_sr:
                small_unit_sr = {
                    'srid': senior_rater_info.get('SRID', ''),
                    'senior_rater_name': senior_rater_info.get('SENIOR_RATER_NAME', ''),
                    'senior_rater_rank': senior_rater_info.get('SENIOR_RATER_RANK', ''),
                    'senior_rater_title': senior_rater_info.get('SENIOR_RATER_TITLE', '')
                }
                batched_updates["small_unit_sr"] = small_unit_sr

        category_list.append(new_member)
        batched_updates[category_key] = pd.DataFrame(category_list)

        pdf_list = session.get('pdf_dataframe', [])
        if isinstance(pdf_list, list):
            pdf_new_member = new_member.copy()
            pdf_new_member.pop('member_id', None)
            pdf_list.append(pdf_new_member)
            batched_updates["pdf_dataframe"] = pd.DataFrame(pdf_list)

        update_session(session_id, **batched_updates)

        # Re-check eligibility — member may belong in a different category
        if run_eligibility_check:
            new_category = recheck_member_eligibility(
                session_id, new_member, category, len(category_list) - 1
            )
        else:
            new_category = category

        rescan_and_update_pascodes(session_id)
        recalculate_small_units(session_id)

        return JSONResponse(content={
            "success": True,
            "message": "Member added successfully",
            "member_id": new_member.get('member_id'),
            "category": new_category,
            "category_changed": new_category != category,
        })

    except Exception as e:
        return error_response(500, "Failed to add member", context={"session_id": session_id, "category": category}, exception=e)


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

        # Enforce 2MB logo size limit
        if len(logo_data) > 2 * 1024 * 1024:
            return error_response(400, "Logo file too large. Maximum size is 2MB.", context={"session_id": session_id})

        # Store logo in a separate Redis key to avoid bloating the session
        import base64
        from session_manager import _get_redis, _encrypt_data
        from constants import session_ttl
        logo_key = f"{session_id}_logo"
        encrypted_logo = _encrypt_data(base64.b64encode(logo_data).decode())
        _get_redis().set(logo_key, encrypted_logo, ex=session_ttl)

        update_session(
            session_id,
            custom_logo={
                "uploaded": True,
                "filename": logo.filename,
                "content_type": logo.content_type,
            },
            edited=True
        )

        return JSONResponse(content={
            "success": True,
            "message": "Logo uploaded successfully",
            "filename": logo.filename,
        })

    except Exception as e:
        return error_response(500, "Failed to upload logo", context={"session_id": session_id}, exception=e)


@router.get("/roster/logo/{session_id}")
def get_logo(session_id: str):
    """Get the custom logo for the roster"""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        custom_logo = session.get('custom_logo', {})

        if not custom_logo or not custom_logo.get('uploaded'):
            return error_response(404, "No custom logo found", context={"session_id": session_id})

        import base64
        from session_manager import _get_redis, _is_encrypted, _decrypt_data
        logo_key = f"{session_id}_logo"
        raw_logo = _get_redis().get(logo_key)
        if not raw_logo:
            return error_response(404, "Logo data not found or expired", context={"session_id": session_id})
        if _is_encrypted(raw_logo):
            raw_logo = _decrypt_data(raw_logo)
        logo_data = base64.b64decode(raw_logo)
        content_type = custom_logo.get('content_type', 'image/png')

        return StreamingResponse(
            io.BytesIO(logo_data),
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{custom_logo.get("filename", "logo.png")}"'
            }
        )

    except Exception as e:
        return error_response(500, "Failed to get logo", context={"session_id": session_id}, exception=e)


@router.delete("/roster/logo/{session_id}")
def delete_logo(session_id: str):
    """Delete the custom logo for the roster"""
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        from session_manager import _get_redis
        _get_redis().delete(f"{session_id}_logo")

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
        return error_response(500, "Failed to delete logo", context={"session_id": session_id}, exception=e)


@router.post("/roster/reprocess/{session_id}")
async def reprocess_roster(session_id: str, data: Optional[Dict] = Body(default=None)):
    """Reprocess the roster with updated eligibility rules"""
    try:
        # Body is optional — the frontend triggers reprocess with no payload.
        data = data or {}

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
        cycle = session.get('cycle', 'SSG')
        year = session.get('year', 2025)

        await asyncio.to_thread(roster_processor, dataframe, session_id, cycle, year)

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
        return error_response(500, "Failed to reprocess roster", context={"session_id": session_id}, exception=e)
