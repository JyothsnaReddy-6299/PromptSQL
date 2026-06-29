from fastapi import APIRouter
from pydantic import BaseModel

from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.sql_executor import execute_sql
from app.services.summary_generator import generate_summary
from app.services.response_generator import generate_response
from app.services.question_classifier import is_analytical

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

        total_count = len(records)
        

        # 4. Generate response
        if is_analytical(payload.question):
            summary = generate_summary(
                payload.question,
                records[:20]
            )
        else:
            summary = generate_response(
                payload.question,
                records
            )

        return {
            "summary": summary,
            "sql": sql_query,
            "count": total_count,
            "result": records
        }

    except Exception as e:
        print(e)
        return {"error": str(e)}