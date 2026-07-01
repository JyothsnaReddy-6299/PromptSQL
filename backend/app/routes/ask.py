from fastapi import APIRouter
from pydantic import BaseModel

from app.services.table_manager import get_current_table
from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.sql_regenerator import regenerate_sql
from app.services.sql_executor import execute_sql
from app.services.summary_generator import generate_summary

router = APIRouter()


class AskRequest(BaseModel):
    question: str


MAX_RETRIES = 2


@router.post("/ask")
def ask_question(payload: AskRequest):

    try:

        # -----------------------------------------
        # Step 1 : Get current uploaded table
        # -----------------------------------------

        table_name = get_current_table()

        if table_name is None:
            return {
                "success": False,
                "error": "Please upload a dataset first."
            }

        print(f"\nCurrent Table : {table_name}")
        print(f"Question      : {payload.question}")

        # -----------------------------------------
        # Step 2 : Generate SQL
        # -----------------------------------------

        sql_query = generate_sql(
            payload.question,
            table_name
        )

        print("\nGenerated SQL:")
        print(sql_query)

        # -----------------------------------------
        # Step 3 : Validate SQL
        # -----------------------------------------

        for attempt in range(MAX_RETRIES):

            is_valid, message = validate_sql(
                sql_query,
                table_name
            )

            if is_valid:
                break

            print(f"\nValidation Failed (Attempt {attempt + 1})")
            print(message)

            sql_query = regenerate_sql(
                question=payload.question,
                table_name=table_name,
                previous_sql=sql_query,
                error_message=message
            )

            print("\nRegenerated SQL:")
            print(sql_query)

        else:
            return {
                "success": False,
                "error": message
            }

        # -----------------------------------------
        # Step 4 : Execute SQL
        # -----------------------------------------

        records = execute_sql(sql_query)

        print(f"\nRecords Retrieved : {len(records)}")

        # -----------------------------------------
        # Step 5 : Generate Summary
        # -----------------------------------------

        summary = generate_summary(
            payload.question,
            records
        )

        # -----------------------------------------
        # Step 6 : Return Response
        # -----------------------------------------

        return {

            "success": True,

            "table_name": table_name,

            "summary": summary,

            "generated_sql": sql_query,

            "count": len(records),

            "result": records

        }

    except Exception as e:

        print("\nERROR:")
        print(str(e))

        return {

            "success": False,

            "error": str(e)

        }