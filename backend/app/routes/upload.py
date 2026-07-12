from fastapi import APIRouter, UploadFile, File, HTTPException, Header
import os
from typing import Optional

from app.services.upload_service import upload_dataset

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), x_user_id: Optional[str] = Header(None)):

    try:

        filepath = os.path.join(
            UPLOAD_DIR,
            file.filename
        )

        with open(filepath, "wb") as buffer:
            buffer.write(await file.read())

        result = upload_dataset(
            filepath=filepath,
            filename=file.filename,
            user_id=x_user_id or "default_user"
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
def get_preview(
    search: Optional[str] = None,
    sort_col: Optional[str] = None,
    sort_dir: Optional[str] = "ASC",
    x_table_name: Optional[str] = Header(None)
):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text, inspect

    table_name = x_table_name or get_current_table()
    if not table_name:
        return {
            "success": False,
            "error": "No dataset uploaded yet."
        }

    try:
        inspector = inspect(engine)
        col_info = inspector.get_columns(table_name)
        columns = [c["name"] for c in col_info]
        
        # Get dynamic total rows count
        count_query = f"SELECT COUNT(*) FROM `{table_name}`"
        with engine.connect() as conn:
            total_rows = conn.execute(text(count_query)).scalar() or 0

        # Get dynamic missing cells count across all columns (datatype-aware to avoid MySQL type-comparison errors)
        if col_info:
            sum_parts = []
            for col in col_info:
                col_name = col["name"]
                col_type = str(col["type"]).lower()
                if "varchar" in col_type or "text" in col_type or "char" in col_type:
                    sum_parts.append(f"SUM(CASE WHEN `{col_name}` IS NULL OR `{col_name}` = '' THEN 1 ELSE 0 END)")
                else:
                    sum_parts.append(f"SUM(CASE WHEN `{col_name}` IS NULL THEN 1 ELSE 0 END)")
            
            missing_query = f"SELECT ({' + '.join(sum_parts)}) FROM `{table_name}`"
            with engine.connect() as conn:
                total_missing = conn.execute(text(missing_query)).scalar() or 0
        else:
            total_missing = 0

        # Build preview query with server-side column search and sorting
        if search and columns:
            conditions = [f"`{col}` LIKE :search" for col in columns]
            where_clause = " OR ".join(conditions)
            if sort_col and sort_col in columns:
                dir_keyword = "DESC" if sort_dir.upper() == "DESC" else "ASC"
                sql_query = f"SELECT * FROM `{table_name}` WHERE {where_clause} ORDER BY `{sort_col}` {dir_keyword} LIMIT 100"
            else:
                sql_query = f"SELECT * FROM `{table_name}` WHERE {where_clause} LIMIT 100"
            params = {"search": f"%{search}%"}
        else:
            if sort_col and sort_col in columns:
                dir_keyword = "DESC" if sort_dir.upper() == "DESC" else "ASC"
                sql_query = f"SELECT * FROM `{table_name}` ORDER BY `{sort_col}` {dir_keyword} LIMIT 100"
            else:
                sql_query = f"SELECT * FROM `{table_name}` LIMIT 100"
            params = {}

        with engine.connect() as conn:
            res = conn.execute(text(sql_query), params)
            records = [dict(row._mapping) for row in res]

        from app.utils.json_helper import sanitize_for_json
        return {
            "success": True,
            "table_name": table_name,
            "columns": columns,
            "records": sanitize_for_json(records),
            "total_rows": total_rows,
            "total_missing": total_missing
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
