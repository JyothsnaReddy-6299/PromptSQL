from fastapi import APIRouter, Header, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
import re

from app.services.dataset_guard import (
    resolve_and_authorize_dataset,
    get_user_datasets,
    verify_all_referenced_tables,
    is_system_table
)
from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.sql_regenerator import regenerate_sql
from app.services.sql_executor import execute_sql

from app.services.result_interpreter import interpret_result
from app.services.aggregate_summary import generate_aggregate_summary
from app.services.summary_generator import generate_summary
from app.services.auth_service import get_current_user_id
from app.utils.error_sanitizer import sanitize_error_message

router = APIRouter()


class AskRequest(BaseModel):
    question: str


MAX_RETRIES = 2


@router.post("/ask")
def ask_question(
    payload: AskRequest,
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):
    # -----------------------------------------
    # Resolve and authorize requested dataset
    # -----------------------------------------
    table_name = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
    all_user_tables = get_user_datasets(user_id)

    # Restrict LLM query scope to user's authorized tables
    from app.database.connection import engine
    from sqlalchemy import inspect
    inspector = inspect(engine)

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

    try:
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
                if tbl not in user_tables and not is_system_table(tbl):
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

        # Multi-table authorization verification: every referenced table must be authorized
        verify_all_referenced_tables(physical_sql, user_id, user_tables)

        records = execute_sql(physical_sql)

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

    except HTTPException:
        raise
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        print("\nException (sanitized):", safe_msg)
        return {
            "success": False,
            "error": safe_msg
        }
