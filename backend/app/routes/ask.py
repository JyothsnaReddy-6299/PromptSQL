from fastapi import APIRouter
from pydantic import BaseModel
from app.database.connection import engine
import pandas as pd
from groq import Groq
from sqlalchemy import inspect
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    table_name: str


api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found in environment")

client = Groq(api_key=api_key)


def generate_sql(question, table):

    schema = get_schema(table)


    schema_text = "\n".join(schema)


    prompt = f"""

You are an expert MySQL engineer.


Table Name:

{table}



Columns:

{schema_text}



Rules:

1. Use ONLY available columns.

2. Return ONLY SQL.

3. MySQL syntax only.

4. Do not explain.

5. No markdown.



Question:

{question}


"""


    response = client.chat.completions.create(

        model="llama-3.3-70b-versatile",

        messages=[

            {

                "role":"system",

                "content":"Generate only MySQL queries"

            },

            {

                "role":"user",

                "content":prompt

            }

        ]

    )


    sql = response.choices[0].message.content.strip()


    sql = sql.replace("```sql","")

    sql = sql.replace("```","")


    return sql


@router.post("/ask")
def ask_question(payload: AskRequest):

    try:
        sql_query = generate_sql(payload.question, payload.table_name)

        df = pd.read_sql(sql_query, engine)

        return {


    "question":payload.question,


    "table":payload.table_name,


    "sql":sql_query,


    "total_rows":len(df),


    "columns":list(df.columns),


    "result":df.to_dict(

        orient="records"

    )

}

    except Exception as e:
        return {"error": str(e)}

def get_schema(table_name):

    inspector = inspect(engine)

    columns = inspector.get_columns(table_name)

    schema = []

    for column in columns:

        schema.append(

            f"{column['name']} ({column['type']})"

        )

    return schema