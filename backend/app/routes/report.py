import json
from io import BytesIO
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.connection import SessionLocal
from app.models.report import SavedReport
from app.services.export_service import generate_pdf, generate_excel, generate_csv

router = APIRouter(prefix="/reports", tags=["Reports"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ReportCreateSchema(BaseModel):
    user_id: Optional[str] = "default_user"
    title: str
    table_name: str
    question: str
    generated_sql: str
    summary: str
    records: list


class ReportRenameSchema(BaseModel):
    title: str


class ReportListSchema(BaseModel):
    id: int
    user_id: str
    title: str
    table_name: str
    question: str
    generated_sql: str
    summary: str
    timestamp: datetime

    class Config:
        from_attributes = True


class ReportDetailSchema(ReportListSchema):
    records: list


@router.get("", response_model=List[ReportListSchema])
def get_reports(
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    user_id = x_user_id or "default_user"
    return (
        db.query(SavedReport)
        .filter(SavedReport.user_id == user_id)
        .order_by(SavedReport.timestamp.desc())
        .all()
    )


@router.get("/{id}", response_model=ReportDetailSchema)
def get_report_detail(
    id: int,
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    user_id = x_user_id or "default_user"
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == id, SavedReport.user_id == user_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        records = json.loads(report.result_json)
    except Exception:
        records = []

    return ReportDetailSchema(
        id=report.id,
        user_id=report.user_id,
        title=report.title,
        table_name=report.table_name,
        question=report.question,
        generated_sql=report.generated_sql,
        summary=report.summary,
        timestamp=report.timestamp,
        records=records
    )


@router.post("", response_model=ReportListSchema)
def create_report(
    payload: ReportCreateSchema,
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    db_item = SavedReport(
        user_id=x_user_id or payload.user_id or "default_user",
        title=payload.title,
        table_name=payload.table_name,
        question=payload.question,
        generated_sql=payload.generated_sql,
        summary=payload.summary,
        result_json=json.dumps(payload.records)
    )
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/{id}", response_model=ReportListSchema)
def rename_report(
    id: int,
    payload: ReportRenameSchema,
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    user_id = x_user_id or "default_user"
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == id, SavedReport.user_id == user_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.title = payload.title
    db.commit()
    db.refresh(report)
    return report


@router.delete("/{id}")
def delete_report(
    id: int,
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    user_id = x_user_id or "default_user"
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == id, SavedReport.user_id == user_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    db.delete(report)
    db.commit()
    return {"success": True, "message": f"Deleted report {id}"}


@router.get("/{id}/export/{format}")
def export_saved_report(
    id: int,
    format: str,
    x_user_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    user_id = x_user_id or "default_user"
    report = (
        db.query(SavedReport)
        .filter(SavedReport.id == id, SavedReport.user_id == user_id)
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        records = json.loads(report.result_json)
    except Exception:
        records = []

    format = format.lower()

    if format == "pdf":
        file_bytes = generate_pdf(
            question=report.question,
            summary=report.summary,
            sql=report.generated_sql,
            records=records
        )
        media_type = "application/pdf"
        filename = f"{report.title.replace(' ', '_')}.pdf"
    elif format == "excel":
        file_bytes = generate_excel(records)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{report.title.replace(' ', '_')}.xlsx"
    elif format == "csv":
        file_bytes = generate_csv(records)
        media_type = "text/csv"
        filename = f"{report.title.replace(' ', '_')}.csv"
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid format. Supported: pdf, excel, csv"
        )

    return StreamingResponse(
        BytesIO(file_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
