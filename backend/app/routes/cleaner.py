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
from app.services.table_manager import get_current_table
from sqlalchemy import text
from app.utils.tz_helper import get_ist_time

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
    """Helper dependency to retrieve and verify ownership of the active dataset table via Header or active_table.txt."""
    table_name = x_table_name or get_current_table()
    if not table_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active dataset table selected."
        )
    if "_usr_" in table_name:
        owner_id = "usr_" + table_name.split("_usr_")[-1]
        if owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You do not own this dataset."
            )
    return ActiveTableContext(user_id, table_name)


class ImputeRequest(BaseModel): # basemodel is imp class of pydantic, define structure of data your API expects
    column_name: str
    strategy: str
    custom_value: Optional[str] = None


@router.post("/remove-duplicates")
def remove_duplicates(db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id

    try:
        # Get count before
        with engine.connect() as conn:
            count_before = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar() or 0

        temp_table = f"temp_dedup_{table_name}"
        
        # Copy unique rows to temp, truncate original, insert back
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{temp_table}`"))
            conn.execute(text(f"CREATE TABLE `{temp_table}` AS SELECT DISTINCT * FROM `{table_name}`"))
            conn.execute(text(f"TRUNCATE TABLE `{table_name}`"))
            conn.execute(text(f"INSERT INTO `{table_name}` SELECT * FROM `{temp_table}`"))
            conn.execute(text(f"DROP TABLE `{temp_table}`"))

            # Get count after
            count_after = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar() or 0

        rows_deleted = count_before - count_after

        # Save to Audit Log
        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="CLEAN",
            table_name=table_name,
            generated_sql=f"-- Deduplicate table by copying distinct records\nDELETE duplicates FROM `{table_name}`",
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
        return {"success": False, "error": str(e)}


@router.post("/impute")
def impute_column(req: ImputeRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id

    col = req.column_name
    strategy = req.strategy.lower()
    val = None
    sql_executed = ""
    rows_affected = 0

    try:
        if strategy == "drop":
            sql_executed = f"DELETE FROM `{table_name}` WHERE `{col}` IS NULL OR `{col}` = ''"
            with engine.begin() as conn:
                res = conn.execute(text(sql_executed))
                rows_affected = res.rowcount or 0

        else:
            # Impute value strategies (mean, median, mode, custom)
            query = f"SELECT `{col}` FROM `{table_name}` WHERE `{col}` IS NOT NULL AND `{col}` != ''"
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

            # Update rows where it is NULL
            sql_executed = f"UPDATE `{table_name}` SET `{col}` = :val WHERE `{col}` IS NULL OR `{col}` = ''"
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
        return {"success": False, "error": str(e)}


@router.get("/locate-missing")
def locate_missing(column_name: str, ctx: ActiveTableContext = Depends(get_active_context)):
    from sqlalchemy import inspect
    table_name = ctx.table_name
    if not column_name:
        raise HTTPException(status_code=400, detail="Column name is required.")

    try:
        inspector = inspect(engine)
        col_info = inspector.get_columns(table_name)
        columns = [c["name"] for c in col_info]

        if column_name not in columns:
            raise HTTPException(status_code=400, detail=f"Column '{column_name}' does not exist.")

        # Query total null count
        count_q = f"SELECT COUNT(*) FROM `{table_name}` WHERE `{column_name}` IS NULL OR `{column_name}` = ''"
        with engine.connect() as conn:
            total_missing = conn.execute(text(count_q)).scalar() or 0

        # Query sample rows where this column is missing
        sample_q = f"SELECT * FROM `{table_name}` WHERE `{column_name}` IS NULL OR `{column_name}` = '' LIMIT 20"
        with engine.connect() as conn:
            res = conn.execute(text(sample_q))
            rows = [dict(r._mapping) for r in res]

        return {
            "success": True,
            "column_name": column_name,
            "total_missing": total_missing,
            "columns": columns,
            "rows": rows
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


class UpdateCellRequest(BaseModel):
    column_name: str
    new_value: str
    row_data: dict


@router.post("/update-cell")
def update_cell(req: UpdateCellRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id

    col = req.column_name
    new_val = req.new_value
    row_data = req.row_data

    # Build WHERE clause dynamically to identify the specific row
    where_parts = []
    params = {"new_val": new_val}

    for k, v in row_data.items():
        if v is None or v == "":
            where_parts.append(f"`{k}` IS NULL")
        else:
            where_parts.append(f"`{k}` = :{k}")
            params[k] = v

    where_clause = " AND ".join(where_parts)
    sql_executed = f"UPDATE `{table_name}` SET `{col}` = :new_val WHERE {where_clause}"

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
        return {"success": False, "error": str(e)}


class ConvertTypeRequest(BaseModel):
    column_name: str
    target_type: str


@router.post("/convert-type")
def convert_type(req: ConvertTypeRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id

    col = req.column_name
    target = req.target_type.lower()

    try:
        if target == "numeric":
            clean_query = f"""
                UPDATE `{table_name}`
                SET `{col}` = NULL
                WHERE `{col}` IS NOT NULL 
                  AND `{col}` != '' 
                  AND `{col}` NOT REGEXP '^[+-]?[0-9]*\\\\.?[0-9]+$'
            """
            alter_query = f"ALTER TABLE `{table_name}` MODIFY `{col}` DOUBLE NULL"
            with engine.begin() as conn:
                conn.execute(text(clean_query))
                conn.execute(text(alter_query))

        elif target == "text":
            alter_query = f"ALTER TABLE `{table_name}` MODIFY `{col}` VARCHAR(255) NULL"
            with engine.begin() as conn:
                conn.execute(text(alter_query))

        elif target == "date":
            clean_query = f"""
                UPDATE `{table_name}`
                SET `{col}` = STR_TO_DATE(TRIM(`{col}`), '%Y-%m-%d')
                WHERE `{col}` IS NOT NULL AND `{col}` != ''
            """
            alter_query = f"ALTER TABLE `{table_name}` MODIFY `{col}` DATE NULL"
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
            generated_sql=f"ALTER TABLE `{table_name}` MODIFY `{col}` {target.upper()}",
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
        return {"success": False, "error": str(e)}


class StandardizeTextRequest(BaseModel):
    column_name: str
    operation: str  # "trim", "upper", "lower", "title"


@router.post("/standardize-text")
def standardize_text(req: StandardizeTextRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id

    col = req.column_name
    op = req.operation.lower()
    rows_affected = 0
    update_query = ""

    try:
        if op == "title":
            query = f"SELECT `id`, `{col}` FROM `{table_name}`"
            with engine.connect() as conn:
                df = pd.read_sql(query, conn)
            
            # Apply Title Case, preserving NULL values
            df[col] = df[col].apply(lambda x: str(x).title() if pd.notna(x) and x is not None else None)
            
            update_query = f"-- Title case update via Pandas\nUPDATE `{table_name}` SET `{col}` = :val WHERE `id` = :id"
            with engine.begin() as conn:
                for _, row in df.iterrows():
                    conn.execute(
                        text(f"UPDATE `{table_name}` SET `{col}` = :val WHERE `id` = :id"),
                        {"val": row[col], "id": int(row["id"])}
                    )
                rows_affected = len(df)
        else:
            if op == "trim":
                sql_func = f"TRIM(`{col}`)"
            elif op == "upper":
                sql_func = f"UPPER(`{col}`)"
            elif op == "lower":
                sql_func = f"LOWER(`{col}`)"
            else:
                return {"success": False, "error": f"Unsupported standardize operation: {op}"}

            update_query = f"UPDATE `{table_name}` SET `{col}` = {sql_func} WHERE `{col}` IS NOT NULL AND `{col}` != ''"
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
        return {"success": False, "error": str(e)}


class ExtractNumbersRequest(BaseModel):
    column_name: str


@router.post("/extract-numbers")
def extract_numbers(req: ExtractNumbersRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    col = req.column_name

    update_query = f"UPDATE `{table_name}` SET `{col}` = REGEXP_REPLACE(`{col}`, '[^0-9.-]', '') WHERE `{col}` IS NOT NULL AND `{col}` != ''"

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
        return {"success": False, "error": str(e)}


@router.get("/detect-numeric-text")
def detect_numeric_text_columns(ctx: ActiveTableContext = Depends(get_active_context)):
    from sqlalchemy import inspect
    table_name = ctx.table_name

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
            sample_q = f"SELECT `{col}` FROM `{table_name}` WHERE `{col}` IS NOT NULL AND `{col}` != '' LIMIT 20"
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
        return {"success": False, "error": str(e)}


class ExtractAndConvertRequest(BaseModel):
    column_name: str


@router.post("/extract-and-convert")
def extract_and_convert(req: ExtractAndConvertRequest, db: Session = Depends(get_db), ctx: ActiveTableContext = Depends(get_active_context)):
    table_name = ctx.table_name
    user_id = ctx.user_id
    col = req.column_name

    try:
        with engine.begin() as conn:
            # Step 1: Extract only numeric parts
            conn.execute(text(
                f"UPDATE `{table_name}` SET `{col}` = REGEXP_REPLACE(`{col}`, '[^0-9.-]', '') "
                f"WHERE `{col}` IS NOT NULL AND `{col}` != ''"
            ))
            # Step 2: Nullify non-numeric text residue
            conn.execute(text(
                f"UPDATE `{table_name}` SET `{col}` = NULL "
                f"WHERE `{col}` IS NOT NULL AND `{col}` NOT REGEXP '^[+-]?[0-9]*\\.?[0-9]+$'"
            ))
            # Step 3: Alter column type to DOUBLE
            conn.execute(text(f"ALTER TABLE `{table_name}` MODIFY `{col}` DOUBLE NULL"))

        audit_log = AuditLog(
            user_id=user_id,
            timestamp=get_ist_time(),
            operation="ALTER",
            table_name=table_name,
            generated_sql=f"-- Extract numbers + convert to DOUBLE for column `{col}`",
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
        return {"success": False, "error": str(e)}
