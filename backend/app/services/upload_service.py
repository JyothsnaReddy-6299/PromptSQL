import os
import pandas as pd

from app.database.connection import engine
from app.services.datatype_detector import detect_column_types
from app.services.data_cleaner import clean_dataframe
from app.services.table_manager import set_current_table


def clean_table_name(filename: str):
    """
    Creates a valid MySQL table name.
    Only the table name is cleaned.
    Column names remain EXACTLY as uploaded.
    """
    table_name = filename.rsplit(".", 1)[0]
    table_name = (
        table_name
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .lower()
    )
    return table_name


def load_dataset(filepath: str):
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        raise ValueError("The uploaded file is empty. Please upload a valid CSV, XLS, or XLSX file.")

    if filepath.endswith(".csv"):
        try:
            return pd.read_csv(filepath)
        except pd.errors.EmptyDataError:
            raise ValueError("The uploaded CSV file is empty or contains no parseable columns.")
        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {str(e)}")
    elif filepath.endswith((".xlsx", ".xls")):
        try:
            return pd.read_excel(filepath)
        except Exception as e:
            raise ValueError(f"Failed to parse Excel file: {str(e)}")
    else:
        raise ValueError("Unsupported file type. Please upload a CSV, XLS, or XLSX file.")


def upload_dataset(filepath: str, filename: str, user_id: str = "default_user"):
    """
    Complete upload pipeline.
    """
    # ------------------------
    # Read dataset
    # ------------------------
    df = load_dataset(filepath)

    if df.empty and len(df.columns) == 0:
        raise ValueError("The uploaded dataset contains no columns.")

    # ------------------------
    # Preserve ORIGINAL column names (stripped of surrounding whitespace)
    # ------------------------
    df.columns = [str(c).strip() for c in df.columns]
    valid_cols = [c for c in df.columns if c and not c.startswith("Unnamed:")]
    if not valid_cols:
        raise ValueError("The uploaded file does not contain any valid named columns.")
    df = df[valid_cols]

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
    
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS `{table_name}`"))
        conn.execute(text(sql_create))

    cleaned_df.to_sql(
        name=table_name,
        con=engine,
        if_exists="append",
        index=False
    )

    # ------------------------
    # Save current table (user-scoped)
    # ------------------------
    set_current_table(table_name, user_id=user_id)

    # ------------------------
    # Statistics
    # ------------------------
    return {
        "filename": filename,
        "table_name": table_name,
        "rows": len(cleaned_df),
        "columns": len(cleaned_df.columns),
        "missing_values": int(
            cleaned_df.isna().sum().sum()
        ),
        "detected_types": detected_types
    }
