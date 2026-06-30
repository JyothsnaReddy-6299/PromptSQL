from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from app.database.connection import engine
import pandas as pd
import os

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def clean_table_name(filename: str):

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


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    try:

        filepath = os.path.join(
            UPLOAD_DIR,
            file.filename
        )

        with open(filepath, "wb") as buffer:
            buffer.write(await file.read())

        # Read file
        if file.filename.endswith(".csv"):

            df = pd.read_csv(filepath)

        elif file.filename.endswith((".xlsx", ".xls")):

            df = pd.read_excel(filepath)

        else:

            raise HTTPException(
                status_code=400,
                detail="Unsupported file type."
            )

        # Clean column names
        df.columns = (
            df.columns
            .str.strip()
            .str.replace(" ", "_")
            .str.replace("-", "_")
            .str.replace("/", "_")
            .str.replace(r"[^A-Za-z0-9_]", "", regex=True)
        )

        table_name = clean_table_name(file.filename)

        # Convert numeric columns
        numeric_keywords = [
            "price",
            "sales",
            "amount",
            "cost",
            "salary",
            "profit",
            "revenue",
            "quantity",
            "total",
            "score",
            "marks",
            "age",
            "count",
            "rate",
            "income",
            "expense"
        ]

        for col in df.columns:

            col_lower = col.lower()

            if any(keyword in col_lower for keyword in numeric_keywords):

                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(",", "", regex=False)
                    .str.replace("$", "", regex=False)
                    .str.strip()
                )

                df[col] = pd.to_numeric(
                    df[col],
                    errors="coerce"
                )

        # Store in MySQL
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

            "missing_values": int(
                df.isnull().sum().sum()
            )

        }

    except SQLAlchemyError as e:

        raise HTTPException(
            status_code=500,
            detail=f"MySQL Error: {str(e)}"
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )