from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from io import BytesIO
from typing import Optional

from app.services.export_service import generate_pdf, generate_excel, generate_csv
from app.services.auth_service import get_current_user_id
from app.services.dataset_guard import resolve_and_authorize_dataset, safe_quote_table_name
from app.database.connection import engine
from sqlalchemy import text

router = APIRouter(prefix="/export", tags=["Export"])


class ExportPDFRequest(BaseModel):
    question: str
    summary: str
    sql: str
    records: list


class ExportDataRequest(BaseModel):
    records: list


@router.post("/pdf")
def export_pdf(payload: ExportPDFRequest, user_id: str = Depends(get_current_user_id)):
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
def export_excel(payload: ExportDataRequest, user_id: str = Depends(get_current_user_id)):
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
def export_csv(payload: ExportDataRequest, user_id: str = Depends(get_current_user_id)):
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


@router.get("/raw/csv")
def export_raw_csv(x_table_name: Optional[str] = Header(None), user_id: str = Depends(get_current_user_id)):
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    try:
        query = f"SELECT * FROM {safe_tbl}"
        with engine.connect() as conn:
            res = conn.execute(text(query))
            records = [dict(row._mapping) for row in res]

        csv_bytes = generate_csv(records)
        friendly_name = table_name.split("_usr_")[0]
        filename = f"{friendly_name}.csv"
        return StreamingResponse(
            BytesIO(csv_bytes),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to export raw CSV data.")


@router.get("/raw/excel")
def export_raw_excel(x_table_name: Optional[str] = Header(None), user_id: str = Depends(get_current_user_id)):
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    try:
        query = f"SELECT * FROM {safe_tbl}"
        with engine.connect() as conn:
            res = conn.execute(text(query))
            records = [dict(row._mapping) for row in res]

        excel_bytes = generate_excel(records)
        friendly_name = table_name.split("_usr_")[0]
        filename = f"{friendly_name}.xlsx"
        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to export raw Excel data.")
