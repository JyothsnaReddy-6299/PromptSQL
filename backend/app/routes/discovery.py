"""
PromptSQL — Automated Data Discovery & Insights API Routes (Issue 15)
"""

from fastapi import APIRouter, Header, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.services.auth_service import get_current_user_id
from app.services.data_discovery_service import (
    discover_dataset_insights,
    invalidate_insights_cache
)

router = APIRouter(prefix="/insights", tags=["Data Discovery & Insights"])


class DiscoverRequest(BaseModel):
    table_name: Optional[str] = None
    force_refresh: bool = False
    filters: Optional[Dict[str, Any]] = None


class InvestigateRequest(BaseModel):
    insight_id: str
    suggested_question: str
    table_name: Optional[str] = None


@router.post("/discover")
def discover_insights(
    payload: Optional[DiscoverRequest] = None,
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):
    """
    Triggers automated dataset profiling and insights discovery for the authenticated user's active or requested dataset.
    Uses caching to prevent redundant execution on frequent component renders.
    """
    req_table = (payload.table_name if payload and payload.table_name else x_table_name)
    force = payload.force_refresh if payload else False
    filters = payload.filters if payload else None

    try:
        data = discover_dataset_insights(
            user_id=user_id,
            table_name=req_table,
            force_refresh=force,
            filters=filters
        )
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Automated data discovery failed: {str(e)}"
        )


@router.post("/cache/invalidate")
def invalidate_cache(
    payload: Optional[DiscoverRequest] = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    Invalidates cached insights for the user.
    """
    table = payload.table_name if payload else None
    invalidate_insights_cache(user_id=user_id, table_name=table)
    return {"success": True, "message": "Insights cache invalidated."}
