from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from io import BytesIO

from app.services.export_service import generate_pdf, generate_excel, generate_csv

router = APIRouter(prefix="/export", tags=["Export"])


class ExportPDFRequest(BaseModel):
    question: str
    summary: str
    sql: str
    records: list


class ExportDataRequest(BaseModel):
    records: list


@router.post("/pdf")
def export_pdf(payload: ExportPDFRequest):
    try:
        pdf_bytes = generate_pdf(
            question=payload.question,
            summary=payload.summary,
            sql=payload.sql,
            records=payload.records
        )
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=query_report.pdf"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/excel")
def export_excel(payload: ExportDataRequest):
    try:
        excel_bytes = generate_excel(payload.records)
        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=query_results.xlsx"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/csv")
def export_csv(payload: ExportDataRequest):
    try:
        csv_bytes = generate_csv(payload.records)
        return StreamingResponse(
            BytesIO(csv_bytes),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=query_results.csv"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
