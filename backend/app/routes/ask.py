from fastapi import APIRouter
from pydantic import BaseModel

from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.sql_executor import execute_sql
from app.services.summary_generator import generate_summary

router = APIRouter()


class AskRequest(BaseModel):
    question: str
    table_name: str


@router.post("/ask")
def ask_question(payload: AskRequest):

    try:

        # 1. Generate SQL
        sql_query = generate_sql(
            payload.question,
            payload.table_name
        )

        print("\nGenerated SQL:")
        print(sql_query)

        # 2. Validate SQL
        is_valid, message = validate_sql(
            sql_query,
            payload.table_name
        )

        if not is_valid:
            return {"error": message}

        # 3. Execute SQL
        records = execute_sql(sql_query)

        # 4. FULL RESULT (do NOT truncate this)
        total_count = len(records)

        # 5. ONLY SAMPLE goes to LLM (IMPORTANT FIX)
        summary_input = records[:20]

        summary = generate_summary(
            payload.question,
            summary_input
        )

        return {
            "summary": summary,
            "sql": sql_query,
            "count": total_count,
            "result": records   # full data returned here
        }

    except Exception as e:
        return {"error": str(e)}