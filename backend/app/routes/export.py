from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from io import BytesIO

from app.services.export_service import generate_pdf, generate_excel, generate_csv
from app.services.auth_service import get_current_user_id

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
def export_raw_csv(user_id: str = Depends(get_current_user_id)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text

    table_name = get_current_table()
    if not table_name:
        raise HTTPException(status_code=400, detail="No active dataset.")

    # Security check: verify user owns the dataset
    if "_usr_" in table_name:
        owner_id = "usr_" + table_name.split("_usr_")[-1]
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")

    try:
        # Fetch all columns and records from the database table
        query = f"SELECT * FROM `{table_name}`"
        with engine.connect() as conn:
            res = conn.execute(text(query))
            records = [dict(row._mapping) for row in res]

        csv_bytes = generate_csv(records)
        filename = f"{table_name.split('_usr_')[0]}.csv"
        return StreamingResponse(
            BytesIO(csv_bytes),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/raw/excel")
def export_raw_excel(user_id: str = Depends(get_current_user_id)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text

    table_name = get_current_table()
    if not table_name:
        raise HTTPException(status_code=400, detail="No active dataset.")

    # Security check: verify user owns the dataset
    if "_usr_" in table_name:
        owner_id = "usr_" + table_name.split("_usr_")[-1]
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")

    try:
        # Fetch all columns and records from the database table
        query = f"SELECT * FROM `{table_name}`"
        with engine.connect() as conn:
            res = conn.execute(text(query))
            records = [dict(row._mapping) for row in res]

        excel_bytes = generate_excel(records)
        filename = f"{table_name.split('_usr_')[0]}.xlsx"
        return StreamingResponse(
            BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

