from fastapi import APIRouter, Header, Depends, HTTPException # fast api components
from pydantic import BaseModel #checks user input like the datatype is correct or not
from typing import Optional  #variable ca be none or string
import re

from app.services.table_manager import get_current_table
from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.sql_regenerator import regenerate_sql
from app.services.sql_executor import execute_sql

from app.services.result_interpreter import interpret_result
from app.services.aggregate_summary import generate_aggregate_summary
from app.services.summary_generator import generate_summary
from app.services.auth_service import get_current_user_id

router = APIRouter()


class AskRequest(BaseModel): #Defines request format.
    question: str


MAX_RETRIES = 2


@router.post("/ask")
def ask_question(
    payload: AskRequest,
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):

    try:

        # -----------------------------------------
        # Get current uploaded table
        # -----------------------------------------

        table_name = x_table_name or get_current_table()

        if table_name is None:
            return {
                "success": False,
                "error": "Please upload a dataset first."
            }

        # Security check: verify user owns the dataset
        if "_usr_" in table_name:
            owner_id = "usr_" + table_name.split("_usr_")[-1]
            if owner_id != user_id:
                raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")

        # Restrict LLM query scope strictly to active table by default, but dynamically include other tables if explicitly mentioned in the question
        from app.database.connection import engine
        from sqlalchemy import inspect
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()
        suffix = f"_{user_id}"
        all_user_tables = [t for t in all_tables if t.endswith(suffix) and t not in ["query_history", "audit_logs", "users"]]
        
        user_tables = [table_name]
        question_lower = payload.question.lower()
        for t in all_user_tables:
            if t != table_name:
                friendly_tbl = t.split("_usr_")[0].lower()
                friendly_clean = friendly_tbl.rstrip('s')
                
                # Check 1: Table name matching
                table_matched = (
                    friendly_tbl in question_lower or 
                    friendly_tbl.replace("_", " ") in question_lower or
                    (len(friendly_clean) > 3 and friendly_clean in question_lower) or
                    any(word in friendly_tbl for word in question_lower.split() if len(word) > 3)
                )
                
                # Check 2: Column name matching (dynamic context expansion)
                column_matched = False
                if not table_matched:
                    try:
                        for col in inspector.get_columns(t):
                            col_name = col["name"].lower()
                            # Skip common generic columns to prevent accidental joins
                            if col_name in ["id", "key", "date", "name", "city", "email", "status", "type"]:
                                continue
                            if any(word in col_name for word in question_lower.split() if len(word) > 3):
                                column_matched = True
                                break
                    except Exception:
                        pass
                
                if table_matched or column_matched:
                    user_tables.append(t)

        print("\n==============================")
        print("Current Table :", table_name)
        print("User Tables   :", user_tables)
        print("Question      :", payload.question)

        # -----------------------------------------
        # Generate SQL
        # -----------------------------------------

        sql_query = generate_sql(
            payload.question,
            table_name,
            user_id
        )

        print("\nGenerated SQL")
        print(sql_query)

        # Get base friendly table name
        friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name

        # -----------------------------------------
        # Validate SQL
        # -----------------------------------------

        for _ in range(MAX_RETRIES):
            # Translate all friendly table references to physical table names
            physical_sql = sql_query
            for t in user_tables:
                friendly_tbl = t.split("_usr_")[0]
                physical_sql = re.sub(rf"(?<!\w)\`?{re.escape(friendly_tbl)}\`?(?!\w)", f"`{t}`", physical_sql)

            # Auto-correct any generic or mismatched table references in FROM/JOIN clauses to use the active table
            from_join_tables = re.findall(r"\b(?:FROM|JOIN)\s+`?([a-zA-Z0-9_\-\(\)]+)`?", physical_sql, re.IGNORECASE)
            for tbl in from_join_tables:
                if tbl not in user_tables and tbl.lower() not in ["query_history", "audit_logs", "users"]:
                    physical_sql = re.sub(rf"(?<!\w)\`?{re.escape(tbl)}\`?(?!\w)", f"`{table_name}`", physical_sql)

            valid, message = validate_sql(
                physical_sql,
                user_tables
            )

            if valid:
                break

            print("\nValidation Failed")
            print(message)

            # Sanitize physical table name in error message so LLM sees friendly name
            sanitized_message = message
            for t in user_tables:
                friendly_tbl = t.split("_usr_")[0]
                sanitized_message = sanitized_message.replace(t, friendly_tbl)

            sql_query = regenerate_sql(
                payload.question,
                table_name,
                sql_query,
                sanitized_message,
                user_id
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

        physical_sql = sql_query
        for t in user_tables:
            friendly_tbl = t.split("_usr_")[0]
            physical_sql = re.sub(rf"(?<!\w)\`?{re.escape(friendly_tbl)}\`?(?!\w)", f"`{t}`", physical_sql)

        records = execute_sql(physical_sql)

        print("\nReturned Records :", len(records))

        if len(records) > 0:
            print(records[:3])

        # -----------------------------------------
        # Decide summary type
        # -----------------------------------------

        result_type = interpret_result(  # to detect whether summary is required or just the answer
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
        # Save to Query History
        # -----------------------------------------
        try:
            from app.database.connection import SessionLocal
            from app.models.history import QueryHistory
            from app.utils.json_helper import sanitize_for_json

            import json
            db_session = SessionLocal()
            db_history = QueryHistory(
                user_id=user_id,
                table_name=table_name,
                question=payload.question,
                generated_sql=sql_query,
                summary=summary,
                result_count=len(records),
                result_json=json.dumps(sanitize_for_json(records))
            )
            db_session.add(db_history)
            db_session.commit()
            db_session.close()
        except Exception as history_err:
            print("\nFailed logging query history:", str(history_err))

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