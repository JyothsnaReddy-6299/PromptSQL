from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from app.database.connection import engine
import pandas as pd
import os

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def clean_table_name(filename: str) -> str:
    """
    Convert filename into a valid MySQL table name.
    Example:
        data.xlsx -> data
        Sales Report.csv -> sales_report
    """
    table_name = filename.rsplit(".", 1)[0]
    table_name = table_name.replace(" ", "_")
    table_name = table_name.lower()

    return table_name


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    try:

        filepath = os.path.join(
            UPLOAD_DIR,
            file.filename
        )

        # Save uploaded file
        with open(filepath, "wb") as buffer:
            buffer.write(await file.read())


        # Read file
        if file.filename.endswith(".csv"):

            df = pd.read_csv(filepath)
            df.columns = (
            df.columns
            .str.strip()                 # Remove leading/trailing spaces
            .str.replace(" ", "_")       # Replace spaces with _
            .str.replace("-", "_")       # Replace - with _
            .str.replace("/", "_")       # Replace / with _
            .str.replace(r"[^A-Za-z0-9_]", "", regex=True)
        )

        elif file.filename.endswith((".xlsx", ".xls")):

            df = pd.read_excel(filepath)
            df.columns = (
            df.columns
            .str.strip()                 # Remove leading/trailing spaces
            .str.replace(" ", "_")       # Replace spaces with _
            .str.replace("-", "_")       # Replace - with _
            .str.replace("/", "_")       # Replace / with _
            .str.replace(r"[^A-Za-z0-9_]", "", regex=True)
        )

        else:

            raise HTTPException(

                status_code=400,

                detail="Unsupported file type"

            )


        # MySQL table name
        table_name = clean_table_name(

            file.filename

        )


        # Insert into MySQL
        df.to_sql(

            name=table_name,

            con=engine,

            if_exists="replace",

            index=False

        )


        rows = len(df)

        columns = len(df.columns)

        missing_values = int(

            df.isnull().sum().sum()

        )


        return {

            "filename": file.filename,

            "table_name": table_name,

            "rows": rows,

            "columns": columns,

            "missing_values": missing_values

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
        

