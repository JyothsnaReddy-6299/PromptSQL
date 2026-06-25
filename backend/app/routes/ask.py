from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.database.connection import engine


router = APIRouter()


class Question(BaseModel):
    question: str
    table: str


@router.post("/ask")
async def ask_ai(data: Question):

    question = data.question.lower()
    table = data.table


    sql = ""


    if "rows" in question:
        sql = f"SELECT COUNT(*) as total_rows FROM {table}"


    elif "columns" in question:
        sql = f"""
        SELECT COUNT(*)
        as total_columns
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='{table}'
        """


    else:

        return {

            "answer":"I don't understand yet",

            "sql":""

        }



    with engine.connect() as conn:

        result = conn.execute(text(sql))

        rows = result.fetchall()



    return {

        "answer": rows,

        "sql": sql

    }