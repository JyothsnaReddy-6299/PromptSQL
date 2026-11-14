from fastapi import APIRouter, UploadFile, File, HTTPException, Header, Depends, status
import os
import re
import secrets
from typing import Optional, List
from pydantic import BaseModel

from app.services.upload_service import upload_dataset
from app.services.auth_service import get_current_user_id
from app.services.table_manager import get_current_table, set_current_table
from app.services.dataset_guard import (
    resolve_and_authorize_dataset,
    get_user_datasets,
    safe_quote_table_name,
    is_system_table,
    validate_table_identifier_format
)
from app.utils.error_sanitizer import sanitize_error_message

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB limit
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), user_id: str = Depends(get_current_user_id)):
    raw_filename = file.filename or ""
    safe_filename = os.path.basename(raw_filename).strip()
    if not safe_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required."
        )

    _, ext = os.path.splitext(safe_filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a CSV, XLS, or XLSX file."
        )

    # Use unique isolated temp file name to prevent collision across concurrent tenant uploads
    temp_filename = f"{user_id}_{secrets.token_hex(8)}_{safe_filename}"
    filepath = os.path.join(UPLOAD_DIR, temp_filename)

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is empty. Please upload a valid CSV, XLS, or XLSX file."
            )
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File size exceeds the 50MB maximum allowed limit."
            )

        with open(filepath, "wb") as buffer:
            buffer.write(content)

        result = upload_dataset(
            filepath=filepath,
            filename=safe_filename,
            user_id=user_id
        )

        return result

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=sanitize_error_message(str(ve))
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=sanitize_error_message(str(e))
        )
    finally:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass


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
    from app.database.connection import engine
    from sqlalchemy import text, inspect

    # 1. Authorize and resolve dataset table strictly
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    safe_tbl = safe_quote_table_name(table_name, [table_name])

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
        count_query = f"SELECT COUNT(*) FROM {safe_tbl}"
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
                clean_col = col_name.replace("`", "``")
                if "varchar" in col_type or "text" in col_type or "char" in col_type:
                    col_sum_parts.append(f"SUM(CASE WHEN `{clean_col}` IS NULL OR `{clean_col}` = '' THEN 1 ELSE 0 END) AS `{clean_col}`")
                else:
                    col_sum_parts.append(f"SUM(CASE WHEN `{clean_col}` IS NULL THEN 1 ELSE 0 END) AS `{clean_col}`")
            
            missing_col_query = f"SELECT {', '.join(col_sum_parts)} FROM {safe_tbl}"
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
                conditions = []
                for col in col_info:
                    col_name = col["name"]
                    col_type = str(col["type"]).lower()
                    clean_col = col_name.replace("`", "``")
                    if "varchar" in col_type or "text" in col_type or "char" in col_type:
                        conditions.append(f"(`{clean_col}` IS NULL OR `{clean_col}` = '')")
                    else:
                        conditions.append(f"`{clean_col}` IS NULL")
                where_clause = " WHERE (" + " OR ".join(conditions) + ")"
            elif ":" in search_clean:
                parts = search_clean.split(":", 1)
                col_target = parts[0].strip()
                val_target = parts[1].strip()
                col_match = next((col for col in columns if col.lower() == col_target.lower()), None)
                if col_match:
                    col_match_info = next((c for c in col_info if c["name"] == col_match), None)
                    col_match_type = str(col_match_info["type"]).lower() if col_match_info else "varchar"
                    clean_col = col_match.replace("`", "``")

                    if val_target.lower() in ["null", "empty", "is null", "missing"]:
                        if "varchar" in col_match_type or "text" in col_match_type or "char" in col_match_type:
                            where_clause = f" WHERE (`{clean_col}` IS NULL OR `{clean_col}` = '')"
                        else:
                            where_clause = f" WHERE (`{clean_col}` IS NULL)"
                    else:
                        where_clause = f" WHERE CAST(`{clean_col}` AS CHAR) LIKE :search_term"
                        params["search_term"] = f"%{val_target}%"
            else:
                conditions = []
                for idx, col in enumerate(columns):
                    clean_col = col.replace("`", "``")
                    param_name = f"search_val_{idx}"
                    conditions.append(f"CAST(`{clean_col}` AS CHAR) LIKE :{param_name}")
                    params[param_name] = f"%{search_clean}%"
                if conditions:
                    where_clause = " WHERE (" + " OR ".join(conditions) + ")"

        # Sorting logic
        order_clause = ""
        if sort_col and sort_col in columns:
            clean_sort = sort_col.replace("`", "``")
            direction = "DESC" if sort_dir and sort_dir.upper() == "DESC" else "ASC"
            order_clause = f" ORDER BY `{clean_sort}` {direction}"

        # Get filtered total rows count if searching
        if where_clause:
            filter_count_query = f"SELECT COUNT(*) FROM {safe_tbl}{where_clause}"
            with engine.connect() as conn:
                display_total_rows = conn.execute(text(filter_count_query), params).scalar() or 0
        else:
            display_total_rows = total_rows

        # Execute paginated query
        sql_query = f"SELECT * FROM {safe_tbl}{where_clause}{order_clause} LIMIT {page_limit} OFFSET {offset}"
        with engine.connect() as conn:
            res = conn.execute(text(sql_query), params)
            records = [dict(row._mapping) for row in res]

        # Get column statistics for numeric columns
        column_stats = {}
        numeric_cols = [c for c, t in detected_types.items() if t == "numeric"]
        if numeric_cols:
            try:
                with engine.connect() as conn:
                    stats_select = []
                    for col in numeric_cols:
                        clean_col = col.replace("`", "``")
                        stats_select.append(f"MIN(`{clean_col}`) AS `{clean_col}_min`")
                        stats_select.append(f"MAX(`{clean_col}`) AS `{clean_col}_max`")
                        stats_select.append(f"AVG(`{clean_col}`) AS `{clean_col}_mean`")
                    
                    stats_sql = f"SELECT {', '.join(stats_select)} FROM {safe_tbl}"
                    stats_res = conn.execute(text(stats_sql)).first()
                    
                    if stats_res:
                        stats_map = dict(stats_res._mapping)
                        for col in numeric_cols:
                            clean_col = col.replace("`", "``")
                            c_min = stats_map.get(f"{clean_col}_min")
                            c_max = stats_map.get(f"{clean_col}_max")
                            c_mean = stats_map.get(f"{clean_col}_mean")
                            
                            count_sql = f"SELECT COUNT(*) FROM {safe_tbl} WHERE `{clean_col}` IS NOT NULL"
                            col_count = conn.execute(text(count_sql)).scalar() or 0
                            
                            median_val = 0.0
                            if col_count > 0:
                                offset = max(0, (col_count - 1) // 2)
                                median_sql = f"SELECT `{clean_col}` FROM {safe_tbl} WHERE `{clean_col}` IS NOT NULL ORDER BY `{clean_col}` LIMIT 1 OFFSET {offset}"
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
    except HTTPException:
        raise
    except Exception as e:
        return {
            "success": False,
            "error": sanitize_error_message(str(e))
        }


class SetActiveDatasetRequest(BaseModel):
    table_name: str


@router.get("/datasets")
def list_datasets(user_id: str = Depends(get_current_user_id)):
    try:
        datasets = get_user_datasets(user_id)
        return {"success": True, "datasets": datasets}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


@router.post("/datasets/active")
def set_active_dataset(req: SetActiveDatasetRequest, user_id: str = Depends(get_current_user_id)):
    try:
        verified_table = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=req.table_name)
        set_current_table(verified_table, user_id=user_id)
        return {"success": True, "table_name": verified_table}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


@router.delete("/datasets/{table_name}")
def delete_dataset(table_name: str, user_id: str = Depends(get_current_user_id)):
    from app.database.connection import engine
    from sqlalchemy import text

    # 1. Authorize table strictly (rejects system tables and other tenants' tables)
    verified_table = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=table_name)
    
    # 2. Hard guard: system tables can never be deleted
    if is_system_table(verified_table):
        raise HTTPException(status_code=403, detail="Access denied. You do not have permission to access this dataset.")

    try:
        safe_tbl = safe_quote_table_name(verified_table, [verified_table])
        with engine.connect() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {safe_tbl}"))
            conn.commit()

        if get_current_table(user_id=user_id) == verified_table:
            set_current_table("", user_id=user_id)
            
        friendly_name = verified_table.split("_usr_")[0]
        return {"success": True, "message": f"Dataset {friendly_name} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_error_message(str(e)))


class ColumnDefinition(BaseModel):
    name: str
    type: str


class CreateTableRequest(BaseModel):
    table_name: str
    columns: List[ColumnDefinition]


class GenerateSchemaRequest(BaseModel):
    prompt: Optional[str] = None
    description: Optional[str] = None


@router.post("/datasets/generate-schema")
@router.post("/custom-tables/generate-schema")
def generate_custom_table_schema(
    req: GenerateSchemaRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    AI-Assisted Table Schema Generation:
    Takes a natural language description and infers table name and column definitions.
    Enforces PromptSQL conventions (auto-skips PK 'id', infers appropriate SQL types).
    """
    from app.services.table_schema_generator import generate_table_schema_from_prompt

    user_prompt = (req.prompt or req.description or "").strip()
    if not user_prompt:
        raise HTTPException(
            status_code=400,
            detail="A natural language description is required to generate a schema."
        )

    try:
        schema = generate_table_schema_from_prompt(user_prompt)
        return schema
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Schema generation failed: {safe_msg}"
        )


@router.post("/datasets/create")
def create_manual_table(req: CreateTableRequest, user_id: str = Depends(get_current_user_id)):
    from app.database.connection import engine
    from sqlalchemy import text
    from app.services.table_schema_generator import (
        validate_custom_table_schema,
        normalize_sql_type,
        ALLOWED_DATA_TYPES
    )
    
    # 1. Validate Table Name (alphanumeric + underscore only)
    validate_table_identifier_format(req.table_name)
    clean_table_name = re.sub(r'[^a-zA-Z0-9_]', '', req.table_name).lower()
    if not clean_table_name or is_system_table(clean_table_name):
        raise HTTPException(status_code=400, detail="Invalid table name")
        
    physical_table_name = f"{clean_table_name}_{user_id}"
    validate_table_identifier_format(physical_table_name)
    if is_system_table(physical_table_name):
        raise HTTPException(status_code=403, detail="Cannot create table with system table name")

    # Validate schema (reject reserved words, duplicate columns, id PK collision, invalid types)
    is_valid, validation_err = validate_custom_table_schema(clean_table_name, [c.dict() for c in req.columns])
    if not is_valid:
        raise HTTPException(status_code=400, detail=validation_err)

    # 2. Build Column Definitions SQL
    col_definitions = []
    # Always add an auto-incrementing id column as primary key
    col_definitions.append("`id` INT AUTO_INCREMENT PRIMARY KEY")
    
    for col in req.columns:
        clean_col_name = re.sub(r'[^a-zA-Z0-9_]', '', col.name).lower()
        if not clean_col_name or clean_col_name == "id":
            continue
            
        selected_type = normalize_sql_type(col.type)
        if selected_type not in ALLOWED_DATA_TYPES:
            selected_type = "VARCHAR(255)"
            
        col_definitions.append(f"`{clean_col_name}` {selected_type} NULL")
        
    if len(col_definitions) <= 1:
        raise HTTPException(status_code=400, detail="Table must have at least one column")
        
    # 3. Execute CREATE TABLE
    safe_tbl = safe_quote_table_name(physical_table_name, [physical_table_name])
    sql_create = f"CREATE TABLE {safe_tbl} (\n  " + ",\n  ".join(col_definitions) + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    
    try:
        with engine.begin() as conn:
            conn.execute(text(sql_create))
            
        set_current_table(physical_table_name, user_id=user_id)
        
        return {
            "success": True, 
            "table_name": physical_table_name,
            "message": f"Table '{clean_table_name}' created successfully!"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {sanitize_error_message(str(e))}")
