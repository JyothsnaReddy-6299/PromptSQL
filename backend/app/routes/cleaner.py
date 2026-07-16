from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.database.connection import SessionLocal
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/clean", tags=["Data Cleaner"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ImputeRequest(BaseModel):
    column_name: str
    strategy: str
    custom_value: Optional[str] = None


@router.post("/remove-duplicates")
def remove_duplicates(db: Session = Depends(get_db)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text
    from datetime import datetime

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset table selected."}

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
            user_id="default_user",
            timestamp=datetime.utcnow(),
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
def impute_column(req: ImputeRequest, db: Session = Depends(get_db)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text
    from datetime import datetime

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset table selected."}

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
            if strategy == "mean":
                q = f"SELECT AVG(CAST(`{col}` AS DECIMAL(15,4))) FROM `{table_name}` WHERE `{col}` IS NOT NULL AND `{col}` != ''"
                with engine.connect() as conn:
                    val = conn.execute(text(q)).scalar()
                    if val is not None:
                        val = float(val)
                    else:
                        val = 0
            elif strategy == "median":
                q = f"SELECT `{col}` FROM `{table_name}` WHERE `{col}` IS NOT NULL AND `{col}` != ''"
                with engine.connect() as conn:
                    vals = []
                    for row in conn.execute(text(q)):
                        try:
                            vals.append(float(row[0]))
                        except:
                            pass
                if vals:
                    vals.sort()
                    n = len(vals)
                    if n % 2 == 1:
                        val = vals[n // 2]
                    else:
                        val = (vals[n // 2 - 1] + vals[n // 2]) / 2.0
                else:
                    val = 0
            elif strategy == "mode":
                q = f"SELECT `{col}`, COUNT(*) as cnt FROM `{table_name}` WHERE `{col}` IS NOT NULL AND `{col}` != '' GROUP BY `{col}` ORDER BY cnt DESC LIMIT 1"
                with engine.connect() as conn:
                    row = conn.execute(text(q)).first()
                    val = row[0] if row else ""
            elif strategy == "custom":
                val = req.custom_value or ""
            else:
                return {"success": False, "error": f"Unsupported imputation strategy: {req.strategy}"}

            sql_executed = f"UPDATE `{table_name}` SET `{col}` = :val WHERE `{col}` IS NULL OR `{col}` = ''"
            with engine.begin() as conn:
                res = conn.execute(text(sql_executed), {"val": val})
                rows_affected = res.rowcount or 0

        # Save to Audit Log
        audit_log = AuditLog(
            user_id="default_user",
            timestamp=datetime.utcnow(),
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


class UpdateCellRequest(BaseModel):
    column_name: str
    new_value: str
    row_data: dict


@router.post("/update-cell")
def update_cell(req: UpdateCellRequest, db: Session = Depends(get_db)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text
    from datetime import datetime

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset table selected."}

    col = req.column_name
    new_val = req.new_value
    row_data = req.row_data

    # Build WHERE clause dynamically to identify the specific row
    where_parts = []
    params = {"new_val": new_val}

    for k, v in row_data.items():
        # Represent NULL values correctly in SQL
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
            user_id="default_user",
            timestamp=datetime.utcnow(),
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
def convert_type(req: ConvertTypeRequest, db: Session = Depends(get_db)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text
    from datetime import datetime

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset table selected."}

    col = req.column_name
    target = req.target_type.lower()

    try:
        if target == "numeric":
            # 1. Nullify any non-numeric strings to prevent casting warnings/failures
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
            # Standardise to YYYY-MM-DD or standard datetime string convert
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
            user_id="default_user",
            timestamp=datetime.utcnow(),
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
    operation: str  # "trim", "upper", "lower"

@router.post("/standardize-text")
def standardize_text(req: StandardizeTextRequest, db: Session = Depends(get_db)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text
    from datetime import datetime

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset table selected."}

    col = req.column_name
    op = req.operation.lower()

    if op == "trim":
        sql_func = f"TRIM(`{col}`)"
    elif op == "upper":
        sql_func = f"UPPER(`{col}`)"
    elif op == "lower":
        sql_func = f"LOWER(`{col}`)"
    else:
        return {"success": False, "error": f"Unsupported standardize operation: {op}"}

    update_query = f"UPDATE `{table_name}` SET `{col}` = {sql_func} WHERE `{col}` IS NOT NULL AND `{col}` != ''"

    try:
        with engine.begin() as conn:
            res = conn.execute(text(update_query))
            rows_affected = res.rowcount or 0

        # Save to Audit Log
        audit_log = AuditLog(
            user_id="default_user",
            timestamp=datetime.utcnow(),
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
def extract_numbers(req: ExtractNumbersRequest, db: Session = Depends(get_db)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text
    from datetime import datetime

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset table selected."}

    col = req.column_name

    # In MySQL 8.0, we can use REGEXP_REPLACE to remove all non-numeric and non-decimal point characters
    # Regex: `[^0-9.-]` matches anything that is NOT a digit, dot, or minus sign.
    update_query = f"UPDATE `{table_name}` SET `{col}` = REGEXP_REPLACE(`{col}`, '[^0-9.-]', '') WHERE `{col}` IS NOT NULL AND `{col}` != ''"

    try:
        with engine.begin() as conn:
            res = conn.execute(text(update_query))
            rows_affected = res.rowcount or 0

        # Save to Audit Log
        audit_log = AuditLog(
            user_id="default_user",
            timestamp=datetime.utcnow(),
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


class CapOutliersRequest(BaseModel):
    column_name: str
    lower_percentile: float = 0.05
    upper_percentile: float = 0.95

@router.post("/cap-outliers")
def cap_outliers(req: CapOutliersRequest, db: Session = Depends(get_db)):
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text
    from datetime import datetime
    import pandas as pd

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset table selected."}

    col = req.column_name

    try:
        # We will load the column data, calculate the percentiles using pandas, and then run an UPDATE query
        query = f"SELECT `{col}` FROM `{table_name}` WHERE `{col}` IS NOT NULL"
        
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
            
        # Convert to numeric, dropping non-convertibles just for statistical calculation
        numeric_series = pd.to_numeric(df[col], errors='coerce').dropna()
        
        if len(numeric_series) == 0:
            return {"success": False, "error": "No valid numeric data found to calculate percentiles."}

        lower_val = float(numeric_series.quantile(req.lower_percentile))
        upper_val = float(numeric_series.quantile(req.upper_percentile))
        
        # Update values less than lower threshold
        sql_lower = f"UPDATE `{table_name}` SET `{col}` = :lower_val WHERE `{col}` < :lower_val AND `{col}` IS NOT NULL"
        # Update values greater than upper threshold
        sql_upper = f"UPDATE `{table_name}` SET `{col}` = :upper_val WHERE `{col}` > :upper_val AND `{col}` IS NOT NULL"

        with engine.begin() as conn:
            res_lower = conn.execute(text(sql_lower), {"lower_val": lower_val})
            rows_lower = res_lower.rowcount or 0
            
            res_upper = conn.execute(text(sql_upper), {"upper_val": upper_val})
            rows_upper = res_upper.rowcount or 0
            
            rows_affected = rows_lower + rows_upper

        audit_log = AuditLog(
            user_id="default_user",
            timestamp=datetime.utcnow(),
            operation="CLEAN",
            table_name=table_name,
            generated_sql=f"-- Cap Outliers\n{sql_lower};\n{sql_upper};",
            rows_affected=rows_affected,
            status="SUCCESS"
        )
        db.add(audit_log)
        db.commit()

        return {
            "success": True,
            "message": f"Successfully capped outliers. {rows_affected} rows adjusted to bounds [{lower_val:.2f}, {upper_val:.2f}].",
            "rows_affected": rows_affected,
            "lower_bound": lower_val,
            "upper_bound": upper_val
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/detect-numeric-text")
def detect_numeric_text_columns():
    """Scan text columns and detect which ones contain numeric-like values (e.g. '1234 USD', '$450.00')."""
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text, inspect
    import re

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset."}

    try:
        inspector = inspect(engine)
        col_info = inspector.get_columns(table_name)

        # Get only text/varchar columns
        text_columns = [
            c["name"] for c in col_info
            if "varchar" in str(c["type"]).lower() or "text" in str(c["type"]).lower() or "char" in str(c["type"]).lower()
        ]

        suspicious_columns = []
        numeric_pattern = re.compile(r'^[\s$£€₹]?[\d,]+\.?\d*[\s]?[a-zA-Z%]*$')

        for col in text_columns:
            # Sample up to 20 non-null values
            sample_q = f"SELECT `{col}` FROM `{table_name}` WHERE `{col}` IS NOT NULL AND `{col}` != '' LIMIT 20"
            with engine.connect() as conn:
                rows = [r[0] for r in conn.execute(text(sample_q))]

            if not rows:
                continue

            # Count how many match a numeric-like pattern
            numeric_like = sum(1 for v in rows if numeric_pattern.match(str(v).strip()))
            ratio = numeric_like / len(rows)

            if ratio >= 0.7:  # 70%+ values look numeric
                # Check if column name hints at numeric (salary, price, amount, cost, total, qty, revenue etc.)
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
def extract_and_convert(req: ExtractAndConvertRequest, db: Session = Depends(get_db)):
    """Extract numbers from a text column AND immediately convert the column datatype to DOUBLE."""
    from app.services.table_manager import get_current_table
    from app.database.connection import engine
    from sqlalchemy import text
    from datetime import datetime

    table_name = get_current_table()
    if not table_name:
        return {"success": False, "error": "No active dataset."}

    col = req.column_name

    try:
        with engine.begin() as conn:
            # Step 1: Extract only the numeric part (remove currency symbols, units, text)
            conn.execute(text(
                f"UPDATE `{table_name}` SET `{col}` = REGEXP_REPLACE(`{col}`, '[^0-9.-]', '') "
                f"WHERE `{col}` IS NOT NULL AND `{col}` != ''"
            ))
            # Step 2: Nullify anything that still can't be cast to a number
            conn.execute(text(
                f"UPDATE `{table_name}` SET `{col}` = NULL "
                f"WHERE `{col}` IS NOT NULL AND `{col}` NOT REGEXP '^[+-]?[0-9]*\\.?[0-9]+$'"
            ))
            # Step 3: Alter column type to DOUBLE
            conn.execute(text(f"ALTER TABLE `{table_name}` MODIFY `{col}` DOUBLE NULL"))

        audit_log = AuditLog(
            user_id="default_user",
            timestamp=datetime.utcnow(),
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

