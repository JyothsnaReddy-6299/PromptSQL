from fastapi import APIRouter, UploadFile, File, HTTPException, Header, Depends
import os
from typing import Optional

from app.services.upload_service import upload_dataset
from app.services.auth_service import get_current_user_id

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):

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
            user_id=user_id
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
    page: int = 1,
    limit: int = 100,
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
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

    # Security check: verify user owns the dataset
    if "_usr_" in table_name:
        owner_id = "usr_" + table_name.split("_usr_")[-1]
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")

    try:
        inspector = inspect(engine)
        col_info = inspector.get_columns(table_name)
        columns = [c["name"] for c in col_info]
        
        # Build live detected types mapping from database column schemas
        from app.services.datatype_detector import is_identifier_column_name
        detected_types = {}
        for col in col_info:
            col_name = col["name"]
            col_type = str(col["type"]).lower()
            if is_identifier_column_name(col_name):
                detected_types[col_name] = "text"
            elif "int" in col_type or "double" in col_type or "decimal" in col_type or "float" in col_type or "numeric" in col_type:
                detected_types[col_name] = "numeric"
            elif "date" in col_type or "timestamp" in col_type or "time" in col_type:
                detected_types[col_name] = "date"
            else:
                detected_types[col_name] = "text"

        # Get dynamic total rows count
        count_query = f"SELECT COUNT(*) FROM `{table_name}`"
        with engine.connect() as conn:
            total_rows = conn.execute(text(count_query)).scalar() or 0

        # Get dynamic missing cells count across all columns (datatype-aware to avoid MySQL type-comparison errors)
        col_missing = {}
        total_missing = 0
        if col_info:
            col_sum_parts = []
            for col in col_info:
                col_name = col["name"]
                col_type = str(col["type"]).lower()
                if "varchar" in col_type or "text" in col_type or "char" in col_type:
                    col_sum_parts.append(f"SUM(CASE WHEN `{col_name}` IS NULL OR `{col_name}` = '' THEN 1 ELSE 0 END) AS `{col_name}`")
                else:
                    col_sum_parts.append(f"SUM(CASE WHEN `{col_name}` IS NULL THEN 1 ELSE 0 END) AS `{col_name}`")
            
            missing_col_query = f"SELECT {', '.join(col_sum_parts)} FROM `{table_name}`"
            with engine.connect() as conn:
                row = conn.execute(text(missing_col_query)).first()
                if row:
                    col_missing = {k: int(v or 0) for k, v in dict(row._mapping).items()}
                    total_missing = sum(col_missing.values())

        # Pagination & Filtering logic
        page_num = max(1, page)
        page_limit = max(1, min(500, limit))
        offset = (page_num - 1) * page_limit

        where_clause = ""
        params = {}

        if search and columns:
            search_clean = search.strip()
            search_lower = search_clean.lower()

            if search_lower in ["null", "empty", "is null", "missing"]:
                # Match rows where ANY column is NULL or empty
                conditions = [f"(`{col}` IS NULL OR `{col}` = '') font" if False else f"(`{col}` IS NULL OR `{col}` = '')" for col in columns]
                where_clause = " WHERE (" + " OR ".join(conditions) + ")"
            elif ":" in search_clean:
                # Column-specific search e.g. "ORDER_ID:null" or "ORDER_ID:123"
                parts = search_clean.split(":", 1)
                col_target = parts[0].strip()
                val_target = parts[1].strip()
                if col_target in columns:
                    if val_target.lower() in ["null", "empty", "is null"]:
                        where_clause = f" WHERE (`{col_target}` IS NULL OR `{col_target}` = '')"
                    else:
                        where_clause = f" WHERE `{col_target}` LIKE :col_val"
                        params["col_val"] = f"%{val_target}%"
                else:
                    conditions = [f"`{col}` LIKE :search" for col in columns]
                    where_clause = " WHERE (" + " OR ".join(conditions) + ")"
                    params["search"] = f"%{search_clean}%"
            else:
                conditions = [f"`{col}` LIKE :search" for col in columns]
                where_clause = " WHERE (" + " OR ".join(conditions) + ")"
                params["search"] = f"%{search_clean}%"

        # Sorting
        order_clause = ""
        if sort_col and sort_col in columns:
            dir_keyword = "DESC" if sort_dir.upper() == "DESC" else "ASC"
            order_clause = f" ORDER BY `{sort_col}` {dir_keyword}"

        # Count total filtered rows matching search
        if where_clause:
            filtered_count_query = f"SELECT COUNT(*) FROM `{table_name}`{where_clause}"
            with engine.connect() as conn:
                display_total_rows = conn.execute(text(filtered_count_query), params).scalar() or 0
        else:
            display_total_rows = total_rows

        # Execute paginated query
        sql_query = f"SELECT * FROM `{table_name}`{where_clause}{order_clause} LIMIT {page_limit} OFFSET {offset}"
        with engine.connect() as conn:
            res = conn.execute(text(sql_query), params)
            records = [dict(row._mapping) for row in res]

        # Get column statistics for numeric columns (computed efficiently in SQL to prevent loading the entire dataset in Python memory)
        column_stats = {}
        numeric_cols = [c for c, t in detected_types.items() if t == "numeric"]
        if numeric_cols:
            try:
                with engine.connect() as conn:
                    # 1. Get min, max, mean in a single optimized query
                    stats_select = []
                    for col in numeric_cols:
                        stats_select.append(f"MIN(`{col}`) AS `{col}_min`")
                        stats_select.append(f"MAX(`{col}`) AS `{col}_max`")
                        stats_select.append(f"AVG(`{col}`) AS `{col}_mean`")
                    
                    stats_sql = f"SELECT {', '.join(stats_select)} FROM `{table_name}`"
                    stats_res = conn.execute(text(stats_sql)).first()
                    
                    if stats_res:
                        stats_map = dict(stats_res._mapping)
                        for col in numeric_cols:
                            c_min = stats_map.get(f"{col}_min")
                            c_max = stats_map.get(f"{col}_max")
                            c_mean = stats_map.get(f"{col}_mean")
                            
                            # 2. Get median using ordered offset
                            # Count non-null rows first
                            count_sql = f"SELECT COUNT(*) FROM `{table_name}` WHERE `{col}` IS NOT NULL"
                            col_count = conn.execute(text(count_sql)).scalar() or 0
                            
                            median_val = 0.0
                            if col_count > 0:
                                offset = max(0, (col_count - 1) // 2)
                                median_sql = f"SELECT `{col}` FROM `{table_name}` WHERE `{col}` IS NOT NULL ORDER BY `{col}` LIMIT 1 OFFSET {offset}"
                                median_val = conn.execute(text(median_sql)).scalar() or 0.0
                            
                            column_stats[col] = {
                                "min": float(c_min) if c_min is not None else 0.0,
                                "max": float(c_max) if c_max is not None else 0.0,
                                "mean": float(c_mean) if c_mean is not None else 0.0,
                                "median": float(median_val)
                            }
            except Exception as e:
                print("Failed to calculate column stats in SQL:", e)

        from app.utils.json_helper import sanitize_for_json
        return {
            "success": True,
            "table_name": table_name,
            "columns": columns,
            "records": sanitize_for_json(records),
            "total_rows": total_rows,
            "display_total_rows": display_total_rows,
            "page": page_num,
            "limit": page_limit,
            "total_missing": total_missing,
            "column_missing": col_missing,
            "detected_types": detected_types,
            "column_stats": column_stats
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


from pydantic import BaseModel

class SetActiveDatasetRequest(BaseModel):
    table_name: str

@router.get("/datasets")
def list_datasets(user_id: str = Depends(get_current_user_id)):
    from app.database.connection import engine
    from sqlalchemy import inspect
    try:
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()
        # Filter tables belonging only to this specific user (e.g. table_usr_usr_1)
        suffix = f"_{user_id}"
        datasets = [t for t in all_tables if t.endswith(suffix) and t not in ["query_history", "audit_logs", "users"]]
        return {"success": True, "datasets": datasets}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/datasets/active")
def set_active_dataset(req: SetActiveDatasetRequest, user_id: str = Depends(get_current_user_id)):
    from app.services.table_manager import set_current_table
    try:
        # Verify ownership
        if "_usr_" in req.table_name:
            owner_id = "usr_" + req.table_name.split("_usr_")[-1]
            if owner_id != user_id:
                raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")
        set_current_table(req.table_name)
        return {"success": True, "table_name": req.table_name}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.delete("/datasets/{table_name}")
def delete_dataset(table_name: str, user_id: str = Depends(get_current_user_id)):
    from app.database.connection import engine
    from sqlalchemy import text
    from app.services.table_manager import get_current_table, set_current_table
    from fastapi import HTTPException
    
    if table_name in ["query_history", "audit_logs", "users"]:
        raise HTTPException(status_code=400, detail="Cannot delete system tables")
        
    try:
        # Verify ownership
        if "_usr_" in table_name:
            owner_id = "usr_" + table_name.split("_usr_")[-1]
            if owner_id != user_id:
                raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")
                
        from sqlalchemy import inspect
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            raise HTTPException(status_code=404, detail="Dataset not found")
            
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE `{table_name}`"))
            
        # If this was the active table, clear active table
        if get_current_table() == table_name:
            set_current_table("")
            
        friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name
        return {"success": True, "message": f"Dataset {friendly_name} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
