from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

from app.database.connection import SessionLocal
from app.models.audit_log import AuditLog

from app.services.auth_service import get_current_user_id

router = APIRouter(prefix="/audit", tags=["Audit"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class AuditLogSchema(BaseModel):
    id: int
    user_id: str
    timestamp: datetime
    operation: str
    table_name: str
    generated_sql: str
    rows_affected: int
    status: str
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("", response_model=List[AuditLogSchema])
def get_audit_logs(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Returns audit history logs ordered by timestamp desc.
    """
    return (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
        .order_by(AuditLog.timestamp.desc())
        .all()
    )


@router.delete("/{log_id}")
def delete_audit_log(
    log_id: int,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    log = db.query(AuditLog).filter(AuditLog.id == log_id, AuditLog.user_id == user_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    db.delete(log)
    db.commit()
    return {"success": True, "message": f"Audit log {log_id} deleted successfully"}
