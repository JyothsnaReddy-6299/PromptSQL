import os
import pandas as pd

from sqlalchemy import inspect
from app.database.connection import engine
from app.services.datatype_detector import detect_mysql_types


UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def clean_table_name(filename):
    """
    Clean only the table name.
    Column names are preserved exactly.
    """

    table_name = os.path.splitext(filename)[0]

    table_name = (
        table_name
        .strip()
        .replace(" ", "_")
        .replace("-", "_")
    )

    return table_name


def upload_dataset(upload_file):

    filename = upload_file.filename

    filepath = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    with open(filepath, "wb") as f:
        f.write(upload_file.file.read())

    # Read file
    if filename.endswith(".csv"):
        df = pd.read_csv(filepath)

    else:
        df = pd.read_excel(filepath)

    # Remove only leading/trailing spaces
    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    # Detect MySQL data types
    dtype_mapping = detect_mysql_types(df)

    table_name = clean_table_name(filename)

    inspector = inspect(engine)

    if table_name in inspector.get_table_names():

        with engine.begin() as conn:
            conn.exec_driver_sql(
                f"DROP TABLE `{table_name}`"
            )

    df.to_sql(
        table_name,
        engine,
        if_exists="replace",
        index=False,
        dtype=dtype_mapping
    )

    return {
        "table_name": table_name,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns)
    }