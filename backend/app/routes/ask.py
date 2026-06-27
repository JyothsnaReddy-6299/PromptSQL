from fastapi import APIRouter
from pydantic import BaseModel
from app.database.connection import engine
from sqlalchemy import inspect
from groq import Groq
from dotenv import load_dotenv
import pandas as pd
import os

load_dotenv()

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    table_name: str


api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found in environment")

client = Groq(api_key=api_key)


def get_schema(table_name):

    inspector = inspect(engine)

    columns = inspector.get_columns(table_name)

    schema = []

    for column in columns:

        schema.append(

            f"{column['name']} ({column['type']})"

        )

    return schema


def generate_sql(question, table):

    schema = get_schema(table)
    schema_text = "\n".join(schema)

    prompt = f"""
You are a STRICT MySQL query generator.

You must follow these rules:
1. Use ONLY the columns listed below
2. NEVER invent column names
3. If a column is not present, ignore it
4. Output ONLY SQL (no explanation, no markdown)
5. Do NOT reorder or assume columns

TABLE: {table}

COLUMNS:
{schema_text}

IMPORTANT MAPPING RULES:
- "product category" = product_category (if exists)
- "order id" = order_id (if exists)
- "employee name" = employee_name (if exists)

QUESTION:
{question}

Return ONLY valid MySQL query:
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are a strict SQL generator. Never hallucinate columns."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    sql = response.choices[0].message.content.strip()

    sql = sql.replace("```sql", "").replace("```", "")

    return sql

@router.post("/ask")
def ask_question(payload: AskRequest):

    try:

        sql_query = generate_sql(
            payload.question,
            payload.table_name
        )

        df = pd.read_sql(sql_query, engine)
        print("GENERATED SQL:", sql_query)

        records = df.to_dict(orient="records")

        if len(records) == 0:
            summary = "No matching records found."

        else:
            # safer than your previous logic
           names = []

for row in records:
    if "employee_name" in row:
        names.append(row["employee_name"])
    elif "order_id" in row:
        names.append(row["order_id"])
    else:
        names.append(list(row.values())[0])

            summary = (
                f"{payload.question.capitalize()} are "
                + ", ".join(names)
            )

        return {
            "summary": summary,
            "sql": sql_query,
            "count": len(records),
            "result": records
        }

    except Exception as e:

        return {
            "error": str(e)
        }