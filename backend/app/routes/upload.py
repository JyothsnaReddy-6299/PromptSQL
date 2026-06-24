from fastapi import APIRouter, UploadFile, File
import os
import shutil
import pandas as pd
from sqlalchemy import create_engine

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATABASE_URL = "mysql+pymysql://root:your_password@localhost/ai_analytics"
engine = create_engine(DATABASE_URL)


def clean_table_name(name: str):
    return name.replace(" ", "_").replace("-", "_").split(".")[0]


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    filepath = os.path.join(UPLOAD_DIR, file.filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # READ FILE
    if file.filename.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    table_name = clean_table_name(file.filename)

    # STORE INTO MYSQL
    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="replace",
        index=False
    )

    return {
        "filename": file.filename,
        "table_name": table_name,
        "rows": len(df),
        "columns": len(df.columns),
        "missing_values": int(df.isnull().sum().sum()),
        "column_names": list(df.columns)
    }