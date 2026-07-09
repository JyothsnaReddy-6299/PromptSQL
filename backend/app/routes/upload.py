from fastapi import APIRouter, UploadFile, File, HTTPException
import os

from app.services.upload_service import upload_dataset

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    try:

        filepath = os.path.join(
            UPLOAD_DIR,
            file.filename
        )

        with open(filepath, "wb") as buffer:
            buffer.write(await file.read())

        result = upload_dataset(
            filepath=filepath,
            filename=file.filename
        )

        return result

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/preview")
def get_preview():
    from app.services.table_manager import get_current_table
    from app.services.sql_executor import execute_sql

    table_name = get_current_table()
    if not table_name:
        return {
            "success": False,
            "error": "No dataset uploaded yet."
        }

    try:
        # Fetch up to 100 rows for preview
        sql_query = f"SELECT * FROM `{table_name}` LIMIT 100"
        records = execute_sql(sql_query)
        columns = list(records[0].keys()) if records else []
        return {
            "success": True,
            "table_name": table_name,
            "columns": columns,
            "records": records
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }