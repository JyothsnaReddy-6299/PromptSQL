import os
import re
import time
import uuid
import pandas as pd
from sqlalchemy import text, inspect

from app.database.connection import engine
from app.services.datatype_detector import detect_column_types
from app.services.data_cleaner import clean_dataframe
from app.services.table_manager import set_current_table


def clean_table_name(filename: str) -> str:
    """
    Creates a safe, sanitized SQL table identifier base from an uploaded filename.
    Strips dangerous characters (backticks, quotes, parentheses, semicolons, unicode, etc.)
    and replaces non-alphanumeric characters with underscores.
    Guarantees valid identifier characters [a-z0-9_] and non-empty name (Issue 17.3).
    """
    if not filename or not str(filename).strip():
        return "dataset"
    base = str(filename).rsplit(".", 1)[0] if "." in str(filename) else str(filename)
    # Remove backticks, quotes, brackets, semicolons, slashes
    base = re.sub(r"[`'\"\\;\(\)\[\]\{\}<>\/\?\*\|\&!@#\$%\^+=:]", "", base)
    # Replace whitespace, hyphens, and dots with underscores
    base = re.sub(r"[\s\-\.]+", "_", base)
    # Keep only ASCII alphanumeric and underscores
    base = re.sub(r"[^a-zA-Z0-9_]", "", base).strip("_").lower()
    if not base:
        base = "dataset"
    # Cap length to 40 characters to leave ample room for _usr_<id>
    if len(base) > 40:
        base = base[:40].rstrip("_")
    # Avoid reserved system table prefixes
    if base.startswith("mysql_") or base.startswith("sys_") or base.startswith("information_schema"):
        base = f"data_{base}"
    return base or "dataset"


def load_dataset(
    filepath: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None
) -> pd.DataFrame:
    """
    Loads dataset into pandas DataFrame.
    For Excel files (.xlsx, .xls), invokes intelligent header-row detection and multi-sheet resolution.
    For CSV files, reads with standard CSV parser.
    """
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        raise ValueError("The uploaded file is empty. Please upload a valid CSV, XLS, or XLSX file.")

    STANDARD_NA_VALUES = ['', '#N/A', '#NA', 'N/A', '<NA>', 'NULL', 'null', 'NaN', '-NaN']

    if filepath.endswith(".csv"):
        try:
            return pd.read_csv(filepath, keep_default_na=False, na_values=STANDARD_NA_VALUES)
        except pd.errors.EmptyDataError:
            raise ValueError("The uploaded CSV file is empty or contains no parseable columns.")
        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {str(e)}")
    elif filepath.endswith((".xlsx", ".xls")):
        try:
            from app.services.excel_header_service import load_excel_with_detected_header
            df, _ = load_excel_with_detected_header(
                filepath,
                sheet_name=sheet_name,
                header_row=header_row
            )
            return df
        except Exception as e:
            raise ValueError(f"Failed to parse Excel file: {str(e)}")
    else:
        raise ValueError("Unsupported file type. Please upload a CSV, XLS, or XLSX file.")


def upload_dataset(
    filepath: str,
    filename: str,
    user_id: str = "default_user",
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None
):
    """
    Complete upload pipeline. Supports multi-worksheet selection and intelligent header detection.
    """
    # ------------------------
    # Read dataset
    # ------------------------
    meta_info: Dict[str, Any] = {}
    if filepath.endswith((".xlsx", ".xls")):
        from app.services.excel_header_service import load_excel_with_detected_header
        df, meta_info = load_excel_with_detected_header(
            filepath,
            sheet_name=sheet_name,
            header_row=header_row
        )
    else:
        df = load_dataset(filepath)

    if df.empty and len(df.columns) == 0:
        raise ValueError("The uploaded dataset contains no columns.")

    # ------------------------
    # Preserve and sanitize column names
    # ------------------------
    sanitized_cols = []
    seen_cols: Dict[str, int] = {}
    for i, col in enumerate(df.columns):
        c_str = str(col).strip()
        if not c_str or c_str.startswith("Unnamed:"):
            c_str = f"Column_{i + 1}"
        lower_c = c_str.lower()
        if lower_c in seen_cols:
            seen_cols[lower_c] += 1
            c_str = f"{c_str}_{seen_cols[lower_c]}"
        else:
            seen_cols[lower_c] = 0
        sanitized_cols.append(c_str)
    df.columns = sanitized_cols

    # ------------------------
    # Detect datatypes
    # ------------------------
    detected_types = detect_column_types(df)

    print("\nDetected Types")
    print(detected_types)

    # ------------------------
    # Clean data
    # ------------------------
    cleaned_df = clean_dataframe(
        df,
        detected_types
    )

    # ------------------------
    # Table name
    # ------------------------
    table_name = clean_table_name(filename)
    if user_id and user_id != "default_user":
        safe_user_id = "".join([c if c.isalnum() else "_" for c in user_id])
        table_name = f"{table_name}_{safe_user_id}"
        if len(table_name) > 64:
            overflow = len(table_name) - 64
            cleaned_base = clean_table_name(filename)
            table_name = f"{cleaned_base[:-overflow]}_{safe_user_id}"

    # ------------------------
    # Store in MySQL (Enforce Primary Key creation to support Aiven DB rules)
    # ------------------------
    from sqlalchemy import text
    
    # Avoid primary key column name collision if user dataset already contains an 'id' column
    has_id_col = any(col.lower() == "id" for col in cleaned_df.columns)
    if has_id_col:
        pk_col = "_row_id"
        counter = 1
        while any(col.lower() == pk_col.lower() for col in cleaned_df.columns):
            pk_col = f"_row_id_{counter}"
            counter += 1
        col_defs = [f"`{pk_col}` INT AUTO_INCREMENT PRIMARY KEY"]
    else:
        col_defs = ["`id` INT AUTO_INCREMENT PRIMARY KEY"]

    for col in cleaned_df.columns:
        t_type = detected_types.get(col, "text")
        if t_type == "numeric":
            db_type = "DOUBLE"
        elif t_type == "date":
            db_type = "DATETIME"
        else:
            db_type = "TEXT"
        clean_col = str(col).replace("`", "``")
        col_defs.append(f"`{clean_col}` {db_type} NULL")
        
    sql_create = f"CREATE TABLE `{table_name}` (\n  " + ",\n  ".join(col_defs) + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
    
    # ------------------------
    # Safe Staging and Swap Table Activation (Issue 17.3)
    # Never drops the existing table until the new dataset is fully validated!
    # ------------------------
    staging_suffix = f"stg_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    staging_table = f"{table_name[:40]}_{staging_suffix}"
    backup_table = f"{table_name[:40]}_bak_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    sql_create_staging = f"CREATE TABLE `{staging_table}` (\n  " + ",\n  ".join(col_defs) + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"

    staging_created = False
    try:
        # 1. Create staging table
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS `{staging_table}`"))
            conn.execute(text(sql_create_staging))
            staging_created = True

        # 2. Populate staging table with cleaned records
        cleaned_df.to_sql(
            name=staging_table,
            con=engine,
            if_exists="append",
            index=False
        )

        # 3. Validate staging table integrity and row count
        with engine.connect() as conn:
            actual_rows = conn.execute(text(f"SELECT COUNT(*) FROM `{staging_table}`")).scalar()
            if actual_rows != len(cleaned_df):
                raise ValueError(
                    f"Data integrity error: Expected {len(cleaned_df)} rows in staging table, "
                    f"but found {actual_rows}. Aborting upload to preserve existing data."
                )

        # 4. Atomic activation / swap
        with engine.begin() as conn:
            inspector = inspect(conn)
            table_exists = inspector.has_table(table_name)
            if table_exists:
                # Safe swap: rename existing to backup, then staging to active table
                conn.execute(text(f"RENAME TABLE `{table_name}` TO `{backup_table}`, `{staging_table}` TO `{table_name}`"))
                conn.execute(text(f"DROP TABLE IF EXISTS `{backup_table}`"))
            else:
                conn.execute(text(f"RENAME TABLE `{staging_table}` TO `{table_name}`"))
            staging_created = False

    finally:
        # 5. Clean up abandoned staging table if activation did not complete
        if staging_created:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"DROP TABLE IF EXISTS `{staging_table}`"))
                    conn.execute(text(f"DROP TABLE IF EXISTS `{backup_table}`"))
            except Exception:
                pass

    # ------------------------
    # Save current table (user-scoped)
    # ------------------------
    set_current_table(table_name, user_id=user_id)

    # ------------------------
    # Statistics & Response Metadata
    # ------------------------
    resp = {
        "filename": filename,
        "table_name": table_name,
        "rows": len(cleaned_df),
        "columns": len(cleaned_df.columns),
        "missing_values": int(
            cleaned_df.isna().sum().sum()
        ),
        "detected_types": detected_types
    }
    if meta_info:
        resp["sheet_name"] = meta_info.get("sheet_name")
        resp["header_row"] = meta_info.get("header_row_1_based")
        resp["warnings"] = meta_info.get("warnings", [])
        resp["confidence"] = meta_info.get("confidence")
    return resp
