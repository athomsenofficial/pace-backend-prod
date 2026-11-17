import asyncio
import io
import uuid
from fastapi import APIRouter, Body, Query, UploadFile, File
from error_handling import error_response
from fastapi.responses import JSONResponse, StreamingResponse
import pandas as pd
from typing import Dict, Optional
from session_manager import get_session, update_session
from roster_processor import (
    roster_processor, recalculate_small_units, rescan_and_update_pascodes,
    place_member, is_truthy, format_date_for_display,
)
from date_parsing import parse_date
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
                if is_truthy(record.get('deleted', False)):
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

                # Editor state the UI shows as badges.
                clean_record['override'] = record.get('_override') == 'eligible'
                clean_record['override_reason'] = record.get('_override_reason') if clean_record['override'] else None
                clean_record['manual'] = is_truthy(record.get('_manual'))

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
            # Discrepancy members are also on the eligible list, so they are not
            # added again here (each member counts once).
            "total_processed": (
                len(eligible_list) +
                len(ineligible_list) +
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


# Fields a reviewer may set on a member from the editor (edit / add). Anything else in
# a request body is ignored.
EDITABLE_FIELDS = [
    'FULL_NAME', 'GRADE', 'DOR', 'TAFMSD', 'DATE_ARRIVED_STATION',
    'UIF_CODE', 'UIF_DISPOSITION_DATE', 'REENL_ELIG_STATUS', 'PAFSC',
    '2AFSC', '3AFSC', '4AFSC', 'ASSIGNED_PAS', 'ASSIGNED_PAS_CLEARTEXT',
    'DAFSC', 'GRADE_PERM_PROJ', 'SSAN',
]


def _parse_member_id(member_id: str):
    """'row_<category>_<index>' -> (category, index). Raises ValueError if malformed."""
    parts = member_id.split('_')
    if len(parts) < 3 or parts[0] != 'row':
        raise ValueError(member_id)
    index = int(parts[-1])
    category = '_'.join(parts[1:-1])  # small_unit contains an underscore
    return category, index


def _locate_member(session_id: str, session: dict, member_id: str):
    """
    Resolve a preview member_id to (category, index, record).
    Returns an error JSONResponse instead when the id is bad.
    """
    try:
        category, index = _parse_member_id(member_id)
    except (ValueError, IndexError):
        return error_response(400, f"Invalid member_id format: {member_id}", context={"session_id": session_id, "member_id": member_id})

    if category not in VALID_CATEGORIES:
        return error_response(400, f"Invalid category: {category}", context={"session_id": session_id})

    data_list = session.get(f"{category}_df", [])
    if not isinstance(data_list, list):
        return error_response(404, f"Category {category} not found", context={"session_id": session_id, "category": category})
    if index >= len(data_list):
        return error_response(404, f"Member index {index} out of range for category {category}", context={"session_id": session_id, "index": index, "category": category})

    return category, index, dict(data_list[index])


DATE_FIELDS = {'DOR', 'TAFMSD', 'DATE_ARRIVED_STATION', 'UIF_DISPOSITION_DATE'}


def _clean_value(value, field: str = None):
    """
    Trim strings and turn blanks into None so required-field checks work. Dates are
    stored in the roster's display format (DD-MMM-YYYY) whatever format the UI sent,
    so the PDF never mixes 2024-01-01 and 01-JAN-2024.
    """
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    if field in DATE_FIELDS and value is not None:
        parsed = parse_date(value)
        return format_date_for_display(parsed) if parsed else value
    return value


def _update_source_roster(session: dict, uid: str, updates: dict = None, remove: bool = False, append: dict = None):
    """
    Apply an editor change to the session's source roster ('dataframe'), which a
    re-process rebuilds every category from. Returns the new list.
    """
    rows = session.get('dataframe', [])
    rows = list(rows) if isinstance(rows, list) else []
    if append is not None:
        rows.append(append)
        return rows
    if not uid:
        return rows
    out = []
    for row in rows:
        if row.get('_uid') == uid:
            if remove:
                continue
            row = {**row, **(updates or {})}
        out.append(row)
    return out


def _refresh_derived(session_id: str):
    rescan_and_update_pascodes(session_id)
    recalculate_small_units(session_id)


@router.put("/roster/member/{session_id}/{member_id}")
async def edit_roster_member(session_id: str, member_id: str, member_data: Dict):
    """Edit an existing member in the roster."""
    return await asyncio.to_thread(_edit_roster_member_sync, session_id, member_id, member_data)

def _edit_roster_member_sync(session_id: str, member_id: str, member_data: Dict):
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        located = _locate_member(session_id, session, member_id)
        if not isinstance(located, tuple):
            return located
        category_name, index, member = located

        updates = {k: _clean_value(v, k) for k, v in member_data.items() if k in EDITABLE_FIELDS}
        member.update(updates)

        uid = member.get('_uid')
        if uid:
            update_session(session_id, dataframe=pd.DataFrame(_update_source_roster(session, uid, updates=updates)))

        # small_unit is a derived view of eligible: re-place from the eligible copy.
        source_category = 'eligible' if category_name == 'small_unit' else category_name
        new_category = place_member(session_id, member, source_category, index if category_name != 'small_unit' else None)

        _refresh_derived(session_id)

        return JSONResponse(content={
            "success": True,
            "message": "Member updated successfully",
            "member_id": member_id,
            "category_changed": new_category != source_category,
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

        if not reason or not reason.strip():
            return error_response(400, "Reason for deletion is required", context={"session_id": session_id, "member_id": member_id})

        located = _locate_member(session_id, session, member_id)
        if not isinstance(located, tuple):
            return located
        category_name, index, member = located
        uid = member.get('_uid')

        updates = {}
        for name in ('eligible', 'ineligible', 'discrepancy', 'btz', 'small_unit'):
            records = session.get(f'{name}_df', [])
            if not isinstance(records, list):
                continue
            new_records = []
            for i, record in enumerate(records):
                same = (record.get('_uid') == uid) if uid else (name == category_name and i == index)
                if not same:
                    new_records.append(record)
                elif not hard_delete:
                    new_records.append({**record, 'deleted': True, 'deletion_reason': reason})
                # hard delete: drop the record entirely
            updates[f'{name}_df'] = pd.DataFrame(new_records) if new_records else pd.DataFrame()

        if uid:
            if hard_delete:
                updates['dataframe'] = pd.DataFrame(_update_source_roster(session, uid, remove=True))
            else:
                updates['dataframe'] = pd.DataFrame(_update_source_roster(
                    session, uid, updates={'deleted': True, 'deletion_reason': reason}))

        update_session(session_id, edited=True, **updates)
        _refresh_derived(session_id)

        return JSONResponse(content={
            "success": True,
            "message": f"Member {'permanently deleted' if hard_delete else 'removed'} successfully",
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
    category = data.get('category', 'eligible') if isinstance(data, dict) else 'eligible'
    try:
        session = get_session(session_id)

        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        member_data = data.get('data', {}) or {}
        reason = (data.get('reason') or '').strip()
        run_eligibility_check = data.get('run_eligibility_check', True)
        senior_rater_info = data.get('senior_rater_info', {}) or {}

        if category not in VALID_CATEGORIES or category == 'small_unit':
            return error_response(400, f"Invalid category: {category}", context={"session_id": session_id})

        if not reason:
            return error_response(400, "Reason for adding member is required", context={"session_id": session_id, "category": category})

        # Build the member from the submitted fields only. (The old code copied missing
        # fields from another member on the roster, which leaked their data.)
        new_member = {col: None for col in PDF_COLUMNS}
        for fld in EDITABLE_FIELDS:
            if fld in member_data:
                new_member[fld] = _clean_value(member_data[fld], fld)
        missing = [f for f in ('FULL_NAME', 'GRADE', 'ASSIGNED_PAS') if not new_member.get(f)]
        if missing:
            return error_response(400, f"Missing required fields: {', '.join(missing)}", context={"session_id": session_id})

        new_member['_uid'] = f"m{uuid.uuid4().hex[:12]}"
        new_member['_manual'] = True

        batched_updates = {
            'edited': True,
            'dataframe': pd.DataFrame(_update_source_roster(session, None, append=dict(new_member))),
        }

        new_pascode = new_member.get('ASSIGNED_PAS')
        if senior_rater_info and new_pascode:
            pascode_map = session.get('pascode_map', {}) or {}
            pascode_map[new_pascode] = {
                'srid': senior_rater_info.get('SRID', ''),
                'senior_rater_name': senior_rater_info.get('SENIOR_RATER_NAME', ''),
                'senior_rater_rank': senior_rater_info.get('SENIOR_RATER_RANK', ''),
                'senior_rater_title': senior_rater_info.get('SENIOR_RATER_TITLE', ''),
                'pascode': new_pascode,
                'unit_name': new_member.get('ASSIGNED_PAS_CLEARTEXT', '')
            }
            batched_updates["pascode_map"] = pascode_map

        if senior_rater_info and senior_rater_info.get('SRID') and not session.get('small_unit_sr'):
            batched_updates["small_unit_sr"] = {
                'srid': senior_rater_info.get('SRID', ''),
                'senior_rater_name': senior_rater_info.get('SENIOR_RATER_NAME', ''),
                'senior_rater_rank': senior_rater_info.get('SENIOR_RATER_RANK', ''),
                'senior_rater_title': senior_rater_info.get('SENIOR_RATER_TITLE', '')
            }

        update_session(session_id, **batched_updates)

        # Same board_filter the upload uses decides where the member goes.
        if run_eligibility_check:
            new_category = place_member(session_id, new_member)
        else:
            new_category = place_member(session_id, new_member, status=category,
                                        reason=reason if category in ('ineligible', 'discrepancy') else None)

        _refresh_derived(session_id)

        return JSONResponse(content={
            "success": True,
            "message": "Member added successfully",
            "member_uid": new_member['_uid'],
            "category": new_category,
            "category_changed": new_category != category,
        })

    except Exception as e:
        return error_response(500, "Failed to add member", context={"session_id": session_id, "category": category}, exception=e)


@router.post("/roster/member/{session_id}/{member_id}/move-to-eligible")
async def move_member_to_eligible(session_id: str, member_id: str, data: Dict = Body(default=None)):
    """
    Reviewer override: put an ineligible / discrepancy member on the eligible list
    (e.g. the roster data is wrong). Requires a reason; the decision is kept through
    later edits and re-processing until it is undone.
    """
    return await asyncio.to_thread(_override_member_sync, session_id, member_id, (data or {}).get('reason', ''), True)


@router.post("/roster/member/{session_id}/{member_id}/clear-override")
async def clear_member_override(session_id: str, member_id: str):
    """Undo a "Move to Eligible" override; the eligibility filter decides again."""
    return await asyncio.to_thread(_override_member_sync, session_id, member_id, '', False)

def _override_member_sync(session_id: str, member_id: str, reason: str, set_override: bool):
    try:
        session = get_session(session_id)
        if not session:
            return error_response(404, "Session not found or expired", context={"session_id": session_id})

        reason = (reason or '').strip()
        if set_override and not reason:
            return error_response(400, "A reason is required to move a member to eligible", context={"session_id": session_id, "member_id": member_id})

        located = _locate_member(session_id, session, member_id)
        if not isinstance(located, tuple):
            return located
        category_name, index, member = located

        if set_override:
            flags = {'_override': 'eligible', '_override_reason': reason}
        else:
            flags = {'_override': None, '_override_reason': None}
        member.update(flags)

        uid = member.get('_uid')
        if uid:
            update_session(session_id, dataframe=pd.DataFrame(_update_source_roster(session, uid, updates=flags)))

        source_category = 'eligible' if category_name == 'small_unit' else category_name
        new_category = place_member(session_id, member, source_category, index if category_name != 'small_unit' else None)
        _refresh_derived(session_id)

        return JSONResponse(content={
            "success": True,
            "message": "Member moved to eligible" if set_override else "Override removed",
            "member_id": member_id,
            "new_category": new_category,
        })
    except Exception as e:
        return error_response(500, "Failed to update member eligibility", context={"session_id": session_id, "member_id": member_id}, exception=e)


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

        # Sessions created before members had stable ids: assign them now so the
        # editor can keep the source roster in step from here on.
        if any(not row.get('_uid') for row in dataframe_list):
            dataframe_list = [
                {**row, '_uid': row.get('_uid') or f"u{i}"} for i, row in enumerate(dataframe_list)
            ]
            update_session(session_id, dataframe=pd.DataFrame(dataframe_list))

        # The source roster already carries every add / delete / edit / override made
        # in the editor, so rebuilding from it keeps the reviewer's changes.
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
