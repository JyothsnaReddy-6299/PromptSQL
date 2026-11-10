from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
import json

from app.database.connection import SessionLocal
from app.models.history import QueryHistory
from app.services.auth_service import get_current_user_id
from app.services.dataset_guard import (
    resolve_and_authorize_dataset,
    get_user_datasets,
    verify_all_referenced_tables,
    is_system_table
)
from app.utils.error_sanitizer import sanitize_error_message

router = APIRouter(prefix="/history", tags=["History"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class HistoryCreateSchema(BaseModel):
    user_id: Optional[str] = "default_user"
    table_name: str
    question: str
    generated_sql: str
    summary: str
    result_count: int
    records: list


class HistorySchema(BaseModel):
    id: int
    user_id: str
    table_name: str
    question: str
    generated_sql: str
    summary: str
    result_count: int
    result_json: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=List[HistorySchema])
def get_history(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    return (
        db.query(QueryHistory)
        .filter(QueryHistory.user_id == user_id)
        .order_by(QueryHistory.timestamp.desc())
        .all()
    )


@router.post("", response_model=HistorySchema)
def create_history_item(
    payload: HistoryCreateSchema,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    # Validate table ownership and reject system tables
    verified_table = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=payload.table_name)

    db_item = QueryHistory(
        user_id=user_id,
        table_name=verified_table,
        question=payload.question,
        generated_sql=payload.generated_sql,
        summary=payload.summary,
        result_count=payload.result_count,
        result_json=json.dumps(payload.records)
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.post("/{id}/undo")
def undo_history_item(
    id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    # 1. Fetch query history item strictly belonging to authenticated user
    item = (
        db.query(QueryHistory)
        .filter(QueryHistory.id == id, QueryHistory.user_id == user_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Query history item not found or access denied.")
        
    if not item.undo_sql:
        raise HTTPException(status_code=400, detail="This query cannot be undone (no undo SQL statement is available).")

    # Guard against undoing operations on system tables
    if is_system_table(item.table_name):
        raise HTTPException(status_code=403, detail="Access denied. Cannot perform undo on protected system tables.")

    # Guard: verify undo SQL only references datasets owned by user
    user_datasets = get_user_datasets(user_id)
    verify_all_referenced_tables(item.undo_sql, user_id, user_datasets)
        
    from sqlalchemy import text
    from app.database.connection import engine
    from app.models.audit_log import AuditLog
    
    # 2. Execute undo SQL query transactionally
    try:
        queries = [q.strip() for q in item.undo_sql.split(";") if q.strip()]
        
        with engine.begin() as conn:
            for q in queries:
                conn.execute(text(q))
                
        # 3. Log the undo operation to Audit Logs
        try:
            db_log = AuditLog(
                user_id=user_id,
                operation="UNDO",
                table_name=item.table_name,
                generated_sql=item.undo_sql,
                rows_affected=len(queries),
                status="SUCCESS",
                error_message=None
            )
            db.add(db_log)
            db.commit()
        except Exception as audit_err:
            print("Failed logging undo operation to audit log:", audit_err)
            
        # 4. Delete the query history item
        db.delete(item)
        db.commit()
        
        return {"success": True, "message": "Database changes successfully rolled back!"}
        
    except HTTPException:
        raise
    except Exception as e:
        # Log failure to Audit Logs
        try:
            db_log = AuditLog(
                user_id=user_id,
                operation="UNDO",
                table_name=item.table_name,
                generated_sql=item.undo_sql,
                rows_affected=0,
                status="FAILURE",
                error_message=sanitize_error_message(str(e))
            )
            db.add(db_log)
            db.commit()
        except Exception as audit_err:
            print("Failed logging failed undo operation to audit log:", sanitize_error_message(str(audit_err)))
            
        raise HTTPException(status_code=500, detail=f"Failed to undo database change: {sanitize_error_message(str(e))}")


@router.delete("/{id}")
def delete_history_item(
    id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    item = (
        db.query(QueryHistory)
        .filter(QueryHistory.id == id, QueryHistory.user_id == user_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    db.delete(item)
    db.commit()
    return {"success": True, "message": f"Deleted history item {id}"}


@router.delete("")
def clear_history(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    db.query(QueryHistory).filter(QueryHistory.user_id == user_id).delete()
    db.commit()
    return {"success": True, "message": "Cleared all history"}
