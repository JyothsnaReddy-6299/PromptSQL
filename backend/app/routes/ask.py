from fastapi import APIRouter
from pydantic import BaseModel

from app.services.table_manager import get_current_table
from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.sql_regenerator import regenerate_sql
from app.services.sql_executor import execute_sql

from app.services.result_interpreter import interpret_result
from app.services.aggregate_summary import generate_aggregate_summary
from app.services.summary_generator import generate_summary

router = APIRouter()


class AskRequest(BaseModel):
    question: str


MAX_RETRIES = 2


@router.post("/ask")
def ask_question(payload: AskRequest):

    try:

        # -----------------------------------------
        # Get current uploaded table
        # -----------------------------------------

        table_name = get_current_table()

        if table_name is None:
            return {
                "success": False,
                "error": "Please upload a dataset first."
            }

        print("\n==============================")
        print("Current Table :", table_name)
        print("Question      :", payload.question)

        # -----------------------------------------
        # Generate SQL
        # -----------------------------------------

        sql_query = generate_sql(
            payload.question,
            table_name
        )

        print("\nGenerated SQL")
        print(sql_query)

        # -----------------------------------------
        # Validate SQL
        # -----------------------------------------

        for _ in range(MAX_RETRIES):

            valid, message = validate_sql(
                sql_query,
                table_name
            )

            if valid:
                break

            print("\nValidation Failed")
            print(message)

            sql_query = regenerate_sql(
                payload.question,
                table_name,
                sql_query,
                message
            )

            print("\nRegenerated SQL")
            print(sql_query)

        else:

            return {
                "success": False,
                "error": message
            }

        # -----------------------------------------
        # Execute SQL
        # -----------------------------------------

        records = execute_sql(sql_query)

        print("\nReturned Records :", len(records))

        if len(records) > 0:
            print(records[:3])

        # -----------------------------------------
        # Decide summary type
        # -----------------------------------------

        result_type = interpret_result(
            sql_query,
            records
        )

        print("\nResult Type :", result_type)

        # -----------------------------------------
        # Generate Summary
        # -----------------------------------------

        if result_type in ["AGGREGATE", "GROUP_AGGREGATE"]:

            print("Using Aggregate Summary")

            summary = generate_aggregate_summary(
                payload.question,
                sql_query,
                records
            )

        else:

            print("Using LLM Summary")

            summary = generate_summary(
                payload.question,
                records
            )

        print("\nSummary")
        print(summary)

        # -----------------------------------------
        # Response
        # -----------------------------------------

        return {

            "success": True,

            "summary": summary,

            "generated_sql": sql_query,

            "count": len(records),

            "result": records

        }

    except Exception as e:

        print("\nException")
        print(str(e))

        return {

            "success": False,

            "error": str(e)

        }