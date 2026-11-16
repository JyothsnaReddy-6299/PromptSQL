"""
PromptSQL — Privacy Guardian API Endpoints (Issue 16: Privacy Guardian)

Provides authenticated, tenant-isolated routes for:
1. Fetching privacy overview and column-level classification policies
2. Rescanning datasets locally for sensitive patterns
3. Updating column privacy policies (normal, sensitive, restricted, custom)
4. Inspecting privacy audit history
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.services.auth_service import get_current_user_id
from app.services.dataset_guard import resolve_and_authorize_dataset
from app.services.privacy_service import (
    get_privacy_overview,
    scan_and_save_dataset_privacy,
    update_column_policy,
    get_privacy_audit_logs
)
from app.utils.error_sanitizer import sanitize_error_message

router = APIRouter(prefix="/privacy", tags=["Privacy Guardian"])


class UpdatePolicyRequest(BaseModel):
    column_name: str
    policy: str
    status: Optional[str] = None


@router.get("/overview")
def get_dataset_privacy_overview(
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):
    """
    Returns high-level privacy statistics, column classification states,
    and active privacy policies for the authorized dataset.
    """
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    try:
        return get_privacy_overview(user_id=user_id, table_name=table_name)
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load privacy overview: {safe_msg}"
        )


@router.post("/scan")
def rescan_dataset_privacy(
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):
    """
    Triggers a fresh local sensitivity scan across table columns and sample values.
    """
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    try:
        scan_and_save_dataset_privacy(user_id=user_id, table_name=table_name, force_rescan=True)
        return get_privacy_overview(user_id=user_id, table_name=table_name)
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rescan dataset privacy: {safe_msg}"
        )


@router.put("/policy")
def modify_column_policy(
    payload: UpdatePolicyRequest,
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):
    """
    Updates the privacy policy for a column (normal, sensitive, restricted, custom).
    Validates tenant ownership and records an audit event.
    """
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    try:
        res = update_column_policy(
            user_id=user_id,
            table_name=table_name,
            column_name=payload.column_name,
            policy=payload.policy,
            status=payload.status
        )
        return res
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update column policy: {safe_msg}"
        )


@router.get("/audit")
def get_privacy_audit(
    limit: int = 50,
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):
    """
    Returns audit trail records for privacy operations on the active dataset.
    """
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    try:
        logs = get_privacy_audit_logs(user_id=user_id, table_name=table_name, limit=max(1, min(200, limit)))
        return {
            "success": True,
            "table_name": table_name,
            "logs": logs
        }
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch privacy audit logs: {safe_msg}"
        )
