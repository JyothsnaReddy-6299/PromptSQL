from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
import json

from app.database.connection import SessionLocal
from app.models.history import QueryHistory

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
    user_id: Optional[str] = "default_user",
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
    db: Session = Depends(get_db)
):
    db_item = QueryHistory(
        user_id=payload.user_id or "default_user",
        table_name=payload.table_name,
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


@router.delete("/{id}")
def delete_history_item(
    id: int,
    user_id: Optional[str] = "default_user",
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
    user_id: Optional[str] = "default_user",
    db: Session = Depends(get_db)
):
    db.query(QueryHistory).filter(QueryHistory.user_id == user_id).delete()
    db.commit()
    return {"success": True, "message": "Cleared all history"}
