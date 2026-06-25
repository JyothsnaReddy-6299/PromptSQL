from fastapi import APIRouter, UploadFile, File
<<<<<<< HEAD
import pandas as pd
import os

from app.database.connection import engine
=======
import os
import shutil
import pandas as pd
from sqlalchemy import create_engine
>>>>>>> 5c5ce2251e911f794b066c7be088e1183b3f9cdb

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATABASE_URL = "mysql+pymysql://root:your_password@localhost/ai_analytics"
engine = create_engine(DATABASE_URL)


def clean_table_name(name: str):
    return name.replace(" ", "_").replace("-", "_").split(".")[0]

def clean_table_name(filename: str):
    return filename.lower().replace(" ", "_").split(".")[0]


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
<<<<<<< HEAD

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

=======

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

>>>>>>> 5c5ce2251e911f794b066c7be088e1183b3f9cdb
    return {
        "filename": file.filename,
        "table_name": table_name,
        "rows": len(df),
        "columns": len(df.columns),
<<<<<<< HEAD
        "missing_values": int(df.isnull().sum().sum())
=======
        "missing_values": int(df.isnull().sum().sum()),
        "column_names": list(df.columns)
>>>>>>> 5c5ce2251e911f794b066c7be088e1183b3f9cdb
    }