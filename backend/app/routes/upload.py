from fastapi import APIRouter, UploadFile, File
import pandas as pd
import os

from app.database.connection import engine

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def clean_table_name(filename: str):
    return filename.lower().replace(" ", "_").split(".")[0]


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    filepath = os.path.join(UPLOAD_DIR, file.filename)

    with open(filepath, "wb") as f:
        f.write(await file.read())

    # read file
    if file.filename.endswith(".csv"):
        df = pd.read_csv(filepath)
    else:
        df = pd.read_excel(filepath)

    table_name = clean_table_name(file.filename)

    # IMPORTANT: send to MySQL
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
        "missing_values": int(df.isnull().sum().sum())
    }