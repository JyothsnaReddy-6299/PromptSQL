from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import pandas as pd
import re

from app.database.connection import SessionLocal, engine
from app.models.audit_log import AuditLog
from app.services.auth_service import get_current_user_id
from app.services.dataset_guard import (
    resolve_and_authorize_dataset,
    safe_quote_table_name,
    is_system_table,
    validate_table_identifier_format,
    SAFE_IDENTIFIER_REGEX
)
from sqlalchemy import text
from app.utils.tz_helper import get_ist_time
from app.utils.error_sanitizer import sanitize_error_message

router = APIRouter(prefix="/clean", tags=["Data Cleaner"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ActiveTableContext:
    def __init__(self, user_id: str, table_name: str):
        self.user_id = user_id
        self.table_name = table_name


def get_active_context(
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
) -> ActiveTableContext:
    """Helper dependency to retrieve and verify ownership of the active dataset table via Header or user-scoped active table."""
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    return ActiveTableContext(user_id, table_name)


def validate_column_identifier(col_name: str) -> str:
    """Validates that a column identifier conforms to safe regex."""
    if not col_name or not isinstance(col_name, str):
        raise HTTPException(status_code=400, detail="Column name is required.")
    clean = col_name.strip().strip("`")
    if not SAFE_IDENTIFIER_REGEX.match(clean) or len(clean) > 64:
        raise HTTPException(status_code=400, detail="Invalid column identifier.")
    return clean


class ImputeRequest(BaseModel):
    column_name: str
    strategy: str
    custom_value: Optional[str] = None


@router.post("/remove-duplicates")
def remove_duplicates(db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        pk_cols = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        col_info = inspector.get_columns(table_name)
        data_cols = [c["name"] for c in col_info if c["name"] not in pk_cols]

        if pk_cols and data_cols and len(pk_cols) == 1:
            # Table has a surrogate or single primary key: delete duplicate records where non-PK data columns match
            pk_col = pk_cols[0]
            clean_pk = pk_col.replace("`", "``")
            match_conditions = " AND ".join([f"t1.`{c.replace('`', '``')}` <=> t2.`{c.replace('`', '``')}`" for c in data_cols])
            del_sql = f"DELETE t1 FROM {safe_tbl} t1 JOIN {safe_tbl} t2 ON t1.`{clean_pk}` > t2.`{clean_pk}` AND {match_conditions}"
            with engine.begin() as conn:
                res = conn.execute(text(del_sql))
                rows_deleted = res.rowcount or 0
                count_after = conn.execute(text(f"SELECT COUNT(*) FROM {safe_tbl}")).scalar() or 0
        else:
            # Fallback for tables without a primary key or composite PKs
            with engine.connect() as conn:
                count_before = conn.execute(text(f"SELECT COUNT(*) FROM {safe_tbl}")).scalar() or 0

            temp_table = f"temp_dedup_{table_name}"
            safe_temp = f"`{temp_table.replace('`', '``')}`"
            
            # Copy unique rows to temp, truncate original, insert back
            with engine.begin() as conn:
                conn.execute(text("SET SESSION sql_require_primary_key = 0"))
                conn.execute(text(f"DROP TABLE IF EXISTS {safe_temp}"))
                conn.execute(text(f"CREATE TABLE {safe_temp} AS SELECT DISTINCT * FROM {safe_tbl}"))
                conn.execute(text(f"TRUNCATE TABLE {safe_tbl}"))
                conn.execute(text(f"INSERT INTO {safe_tbl} SELECT * FROM {safe_temp}"))
                conn.execute(text(f"DROP TABLE {safe_temp}"))

                # Get count after
                count_after = conn.execute(text(f"SELECT COUNT(*) FROM {safe_tbl}")).scalar() or 0

            rows_deleted = count_before - count_after

        # Save to Audit Log
        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="CLEAN",
            table_name=table_name,
            generated_sql=f"-- Deduplicate table by copying distinct records\nDELETE duplicates FROM {safe_tbl}",
            rows_affected=rows_deleted,
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()

        return {
            "success": True,
            "message": f"Successfully removed {rows_deleted} duplicate rows.",
            "rows_affected": rows_deleted,
            "total_rows": count_after
        }
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


@router.post("/impute")
def impute_column(req: ImputeRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    col = validate_column_identifier(req.column_name)
    strategy = req.strategy.lower()
    val = None
    sql_executed = ""
    rows_affected = 0

    try:
        from sqlalchemy import inspect
        inspector = inspect(engine)
        col_info = inspector.get_columns(table_name)
        col_meta = next((c for c in col_info if c["name"] == col), None)
        if not col_meta:
            return {"success": False, "error": f"Column '{col}' does not exist."}
        col_type = str(col_meta["type"]).lower()
        is_text = "varchar" in col_type or "text" in col_type or "char" in col_type

        safe_col = f"`{col.replace('`', '``')}`"

        if strategy == "drop":
            if is_text:
                sql_executed = f"DELETE FROM {safe_tbl} WHERE {safe_col} IS NULL OR {safe_col} = ''"
            else:
                sql_executed = f"DELETE FROM {safe_tbl} WHERE {safe_col} IS NULL"
                
            with engine.begin() as conn:
                res = conn.execute(text(sql_executed))
                rows_affected = res.rowcount or 0

        else:
            # Impute value strategies (mean, median, mode, custom)
            if is_text:
                query = f"SELECT {safe_col} FROM {safe_tbl} WHERE {safe_col} IS NOT NULL AND {safe_col} != ''"
            else:
                query = f"SELECT {safe_col} FROM {safe_tbl} WHERE {safe_col} IS NOT NULL"
                
            with engine.connect() as conn:
                df = pd.read_sql(query, conn)

            if strategy == "mean":
                series = pd.to_numeric(df[col], errors='coerce').dropna()
                val = float(series.mean()) if not series.empty else 0.0

            elif strategy == "median":
                series = pd.to_numeric(df[col], errors='coerce').dropna()
                val = float(series.median()) if not series.empty else 0.0

            elif strategy == "mode":
                series = df[col].dropna()
                val = str(series.mode()[0]) if not series.empty else ""

            elif strategy == "custom":
                val = req.custom_value or ""
                if not is_text:
                    if "date" in col_type or "timestamp" in col_type:
                        try:
                            parsed_date = pd.to_datetime(val, dayfirst=True, errors='raise')
                            if "timestamp" in col_type or "datetime" in col_type:
                                val = parsed_date.strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                val = parsed_date.strftime("%Y-%m-%d")
                        except Exception:
                            pass

            # Update rows where it is NULL
            if is_text:
                sql_executed = f"UPDATE {safe_tbl} SET {safe_col} = :val WHERE {safe_col} IS NULL OR {safe_col} = ''"
            else:
                sql_executed = f"UPDATE {safe_tbl} SET {safe_col} = :val WHERE {safe_col} IS NULL"
                
            with engine.begin() as conn:
                res = conn.execute(text(sql_executed), {"val": val})
                rows_affected = res.rowcount or 0

        # Save to Audit Log
        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="CLEAN",
            table_name=table_name,
            generated_sql=sql_executed + (f" -- Imputed value: {val}" if strategy != "drop" else ""),
            rows_affected=rows_affected,
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()

        return {
            "success": True,
            "message": f"Successfully processed column '{col}' using {strategy} strategy.",
            "rows_affected": rows_affected,
            "imputed_value": str(val) if val is not None else None
        }
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


@router.get("/locate-missing")
def locate_missing(column_name: str, ctx: ActiveTableContext = Depends(get_active_context)):
    from sqlalchemy import inspect
    table_name = ctx.table_name
    col = validate_column_identifier(column_name)
    safe_tbl = safe_quote_table_name(table_name, [table_name])
    safe_col = f"`{col.replace('`', '``')}`"

    try:
        inspector = inspect(engine)
        col_info = inspector.get_columns(table_name)
        columns = [c["name"] for c in col_info]

        if col not in columns:
            raise HTTPException(status_code=400, detail=f"Column '{col}' does not exist.")

        col_meta = next((c for c in col_info if c["name"] == col), None)
        col_type = str(col_meta["type"]).lower() if col_meta else "varchar"
        is_text = "varchar" in col_type or "text" in col_type or "char" in col_type

        # Query total null count
        if is_text:
            count_q = f"SELECT COUNT(*) FROM {safe_tbl} WHERE {safe_col} IS NULL OR {safe_col} = ''"
        else:
            count_q = f"SELECT COUNT(*) FROM {safe_tbl} WHERE {safe_col} IS NULL"
            
        with engine.connect() as conn:
            total_missing = conn.execute(text(count_q)).scalar() or 0

        # Query sample rows where this column is missing
        if is_text:
            sample_q = f"SELECT * FROM {safe_tbl} WHERE {safe_col} IS NULL OR {safe_col} = '' LIMIT 20"
        else:
            sample_q = f"SELECT * FROM {safe_tbl} WHERE {safe_col} IS NULL LIMIT 20"
            
        with engine.connect() as conn:
            res = conn.execute(text(sample_q))
            rows = [dict(r._mapping) for r in res]

        return {
            "success": True,
            "column_name": col,
            "total_missing": total_missing,
            "columns": columns,
            "rows": rows
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


class UpdateCellRequest(BaseModel):
    column_name: str
    new_value: str
    row_data: dict


@router.post("/update-cell")
def update_cell(req: UpdateCellRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    col = validate_column_identifier(req.column_name)
    safe_col = f"`{col.replace('`', '``')}`"
    new_val = req.new_value
    row_data = req.row_data

    # Build WHERE clause dynamically to identify the specific row
    where_parts = []
    params = {"new_val": new_val}

    for idx, (k, v) in enumerate(row_data.items()):
        valid_k = validate_column_identifier(k)
        param_key = f"cond_{idx}"
        safe_k = f"`{valid_k.replace('`', '``')}`"
        if v is None or v == "":
            where_parts.append(f"{safe_k} IS NULL")
        else:
            where_parts.append(f"{safe_k} = :{param_key}")
            params[param_key] = v

    where_clause = " AND ".join(where_parts) if where_parts else "1=1"
    sql_executed = f"UPDATE {safe_tbl} SET {safe_col} = :new_val WHERE {where_clause}"

    try:
        with engine.begin() as conn:
            res = conn.execute(text(sql_executed), params)
            rows_affected = res.rowcount or 0

        # Save to Audit Log
        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="UPDATE",
            table_name=table_name,
            generated_sql=sql_executed + f" -- New value: {new_val}",
            rows_affected=rows_affected,
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()

        return {
            "success": True,
            "message": f"Successfully updated cell '{col}' to '{new_val}'.",
            "rows_affected": rows_affected
        }
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


class ConvertTypeRequest(BaseModel):
    column_name: str
    target_type: str


@router.post("/convert-type")
def convert_type(req: ConvertTypeRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    col = validate_column_identifier(req.column_name)
    safe_col = f"`{col.replace('`', '``')}`"
    target = req.target_type.lower()

    try:
        if target == "numeric":
            clean_query = f"""
                UPDATE {safe_tbl}
                SET {safe_col} = NULL
                WHERE {safe_col} IS NOT NULL 
                  AND {safe_col} != '' 
                  AND {safe_col} NOT REGEXP '^[+-]?[0-9]*\\\\.?[0-9]+$'
            """
            alter_query = f"ALTER TABLE {safe_tbl} MODIFY {safe_col} DOUBLE NULL"
            with engine.begin() as conn:
                conn.execute(text(clean_query))
                conn.execute(text(alter_query))

        elif target == "text":
            alter_query = f"ALTER TABLE {safe_tbl} MODIFY {safe_col} VARCHAR(255) NULL"
            with engine.begin() as conn:
                conn.execute(text(alter_query))

        elif target == "date":
            clean_query = f"""
                UPDATE {safe_tbl}
                SET {safe_col} = STR_TO_DATE(TRIM({safe_col}), '%Y-%m-%d')
                WHERE {safe_col} IS NOT NULL AND {safe_col} != ''
            """
            alter_query = f"ALTER TABLE {safe_tbl} MODIFY {safe_col} DATE NULL"
            with engine.begin() as conn:
                conn.execute(text(clean_query))
                conn.execute(text(alter_query))
        else:
            return {"success": False, "error": f"Unsupported target type: {req.target_type}"}

        # Save to Audit Log
        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="ALTER",
            table_name=table_name,
            generated_sql=f"ALTER TABLE {safe_tbl} MODIFY {safe_col} {target.upper()}",
            rows_affected=0,
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()

        return {
            "success": True,
            "message": f"Successfully converted column '{col}' datatype to {target.upper()}."
        }
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


class StandardizeTextRequest(BaseModel):
    column_name: str
    operation: str  # "trim", "upper", "lower", "title"


@router.post("/standardize-text")
def standardize_text(req: StandardizeTextRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    col = validate_column_identifier(req.column_name)
    safe_col = f"`{col.replace('`', '``')}`"
    op = req.operation.lower()
    rows_affected = 0
    update_query = ""

    try:
        if op == "title":
            query = f"SELECT `id`, {safe_col} FROM {safe_tbl}"
            with engine.connect() as conn:
                df = pd.read_sql(query, conn)
            
            # Apply Title Case, preserving NULL values
            df[col] = df[col].apply(lambda x: str(x).title() if pd.notna(x) and x is not None else None)
            
            update_query = f"-- Title case update via Pandas\nUPDATE {safe_tbl} SET {safe_col} = :val WHERE `id` = :id"
            with engine.begin() as conn:
                for _, row in df.iterrows():
                    conn.execute(
                        text(f"UPDATE {safe_tbl} SET {safe_col} = :val WHERE `id` = :id"),
                        {"val": row[col], "id": int(row["id"])}
                    )
                rows_affected = len(df)
        else:
            if op == "trim":
                sql_func = f"TRIM({safe_col})"
            elif op == "upper":
                sql_func = f"UPPER({safe_col})"
            elif op == "lower":
                sql_func = f"LOWER({safe_col})"
            else:
                return {"success": False, "error": f"Unsupported standardize operation: {op}"}

            update_query = f"UPDATE {safe_tbl} SET {safe_col} = {sql_func} WHERE {safe_col} IS NOT NULL AND {safe_col} != ''"
            with engine.begin() as conn:
                res = conn.execute(text(update_query))
                rows_affected = res.rowcount or 0

        # Save to Audit Log
        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="CLEAN",
            table_name=table_name,
            generated_sql=update_query,
            rows_affected=rows_affected,
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()

        return {
            "success": True,
            "message": f"Successfully standardized text in '{col}' using {op.upper()}.",
            "rows_affected": rows_affected
        }
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


class ExtractNumbersRequest(BaseModel):
    column_name: str


@router.post("/extract-numbers")
def extract_numbers(req: ExtractNumbersRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    col = validate_column_identifier(req.column_name)
    safe_col = f"`{col.replace('`', '``')}`"

    update_query = f"UPDATE {safe_tbl} SET {safe_col} = REGEXP_REPLACE({safe_col}, '[^0-9.-]', '') WHERE {safe_col} IS NOT NULL AND {safe_col} != ''"

    try:
        with engine.begin() as conn:
            res = conn.execute(text(update_query))
            rows_affected = res.rowcount or 0

        # Save to Audit Log
        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="CLEAN",
            table_name=table_name,
            generated_sql=update_query,
            rows_affected=rows_affected,
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()

        return {
            "success": True,
            "message": f"Successfully extracted numbers from '{col}'. You can now convert it to numeric.",
            "rows_affected": rows_affected
        }
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


@router.get("/detect-numeric-text")
def detect_numeric_text_columns(ctx: ActiveTableContext = Depends(get_active_context)):
    from sqlalchemy import inspect
    table_name = ctx.table_name
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    try:
        inspector = inspect(engine)
        col_info = inspector.get_columns(table_name)

        # Exclude common identifier columns that shouldn't be cast to numeric
        exclude_kws = ["id", "code", "zip", "phone", "ssn", "pin", "card", "account", "serial", "number", "mobile", "key"]
        text_columns = [
            c["name"] for c in col_info
            if ("varchar" in str(c["type"]).lower() or "text" in str(c["type"]).lower() or "char" in str(c["type"]).lower())
            and not any(kw in c["name"].lower() for kw in exclude_kws)
        ]

        suspicious_columns = []
        numeric_pattern = re.compile(r'^[\s$£€₹]?[\d,]+\.?\d*[\s]?[a-zA-Z%]*$')

        for col in text_columns:
            safe_col = f"`{col.replace('`', '``')}`"
            sample_q = f"SELECT {safe_col} FROM {safe_tbl} WHERE {safe_col} IS NOT NULL AND {safe_col} != '' LIMIT 20"
            with engine.connect() as conn:
                rows = [r[0] for r in conn.execute(text(sample_q))]

            if not rows:
                continue

            numeric_like = sum(1 for v in rows if numeric_pattern.match(str(v).strip()))
            ratio = numeric_like / len(rows)

            if ratio >= 0.7:
                col_lower = col.lower()
                name_hints = any(kw in col_lower for kw in [
                    "salary", "price", "amount", "cost", "total", "revenue", "qty", "quantity",
                    "fee", "tax", "discount", "income", "profit", "rate", "score", "marks", "value"
                ])
                suspicious_columns.append({
                    "column": col,
                    "sample_values": rows[:5],
                    "numeric_ratio": round(ratio, 2),
                    "name_hint": name_hints
                })

        return {"success": True, "suspicious_columns": suspicious_columns}
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}


class ExtractAndConvertRequest(BaseModel):
    column_name: str


@router.post("/extract-and-convert")
def extract_and_convert(req: ExtractAndConvertRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    safe_tbl = safe_quote_table_name(table_name, [table_name])

    col = validate_column_identifier(req.column_name)
    safe_col = f"`{col.replace('`', '``')}`"

    try:
        with engine.begin() as conn:
            # Step 1: Extract only numeric parts
            conn.execute(text(
                f"UPDATE {safe_tbl} SET {safe_col} = REGEXP_REPLACE({safe_col}, '[^0-9.-]', '') "
                f"WHERE {safe_col} IS NOT NULL AND {safe_col} != ''"
            ))
            # Step 2: Nullify non-numeric text residue
            conn.execute(text(
                f"UPDATE {safe_tbl} SET {safe_col} = NULL "
                f"WHERE {safe_col} IS NOT NULL AND {safe_col} NOT REGEXP '^[+-]?[0-9]*\\.?[0-9]+$'"
            ))
            # Step 3: Alter column type to DOUBLE
            conn.execute(text(f"ALTER TABLE {safe_tbl} MODIFY {safe_col} DOUBLE NULL"))

        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="ALTER",
            table_name=table_name,
            generated_sql=f"-- Extract numbers + convert to DOUBLE for column {safe_col}",
            rows_affected=0,
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()

        return {
            "success": True,
            "message": f"Column '{col}' cleaned and converted to NUMERIC (DOUBLE) successfully."
        }
    except Exception as e:
        return {"success": False, "error": sanitize_error_message(str(e))}
