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
from app.services.table_translator import translate_query_tables, TableTranslationError
from app.services.sql_validator import validate_sql
from app.services.sql_regenerator import regenerate_sql
from app.services.sql_executor import execute_sql

from app.services.result_interpreter import interpret_result
from app.services.aggregate_summary import generate_aggregate_summary
from app.services.summary_generator import generate_summary
from app.services.auth_service import get_current_user_id
from app.core.config import get_settings
from app.utils.error_sanitizer import sanitize_error_message, get_safe_exception_message

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
        # Translate & Validate SQL (AST-Based)
        # -----------------------------------------
        validated_physical_sql: Optional[str] = None
        last_error_message: str = ""

        for _ in range(MAX_RETRIES):
            # 1. Translate friendly table references to physical table names via SQLGlot AST
            try:
                candidate_physical_sql = translate_query_tables(
                    sql_query=sql_query,
                    authorized_tables=user_tables,
                    user_id=user_id
                )
            except TableTranslationError as trans_err:
                last_error_message = str(trans_err)
                print("\nTable Translation Failed:")
                print(last_error_message)

                # Sanitize physical table names so LLM sees friendly names
                sanitized_message = last_error_message
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
                print("\nRegenerated SQL:")
                print(sql_query)
                continue

            # 2. Validate translated physical SQL using AST validator
            valid, message = validate_sql(
                candidate_physical_sql,
                user_tables
            )

            if valid:
                validated_physical_sql = candidate_physical_sql
                break

            last_error_message = message
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
                "error": last_error_message
            }

        # -----------------------------------------
        # Execute SQL
        # -----------------------------------------
        # CRITICAL: The SQL executed is byte-for-byte the exact same SQL that was validated!
        physical_sql = validated_physical_sql

        # Multi-table authorization verification: every referenced table must be authorized
        verify_all_referenced_tables(physical_sql, user_id, user_tables)

        exec_res = execute_sql(physical_sql)
        records = exec_res.records
        is_truncated = exec_res.is_truncated
        truncation_reason = exec_res.truncation_reason
        result_size_bytes = exec_res.result_size_bytes
        returned_rows = getattr(exec_res, "returned_rows", len(records))
        total_rows = getattr(exec_res, "total_rows", (len(records) if not is_truncated else None))

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
                records,
                is_truncated=is_truncated
            )
        else:
            print("Using LLM Summary")
            summary = generate_summary(
                payload.question,
                records,
                is_truncated=is_truncated
            )

        print("\nSummary")
        print(summary)

        # -----------------------------------------
        # Save to Query History (Bounded payload)
        # -----------------------------------------
        try:
            from app.database.connection import SessionLocal
            from app.models.history import QueryHistory
            import json

            # Apply bounded history persistence: cap stored records to protect database storage
            MAX_HISTORY_ROWS = 50
            MAX_HISTORY_BYTES = 128 * 1024  # 128 KB
            history_sample = records[:MAX_HISTORY_ROWS]
            history_payload = json.dumps(history_sample)
            while len(history_payload.encode("utf-8")) > MAX_HISTORY_BYTES and len(history_sample) > 1:
                history_sample = history_sample[:len(history_sample) // 2]
                history_payload = json.dumps(history_sample)

            db_session = SessionLocal()
            db_history = QueryHistory(
                user_id=user_id,
                table_name=table_name,
                question=payload.question,
                generated_sql=sql_query,
                summary=summary,
                result_count=returned_rows,
                result_json=history_payload
            )
            db_session.add(db_history)
            db_session.commit()
            db_session.close()
        except Exception as history_err:
            print("\nFailed logging query history:", sanitize_error_message(str(history_err)))

        # -----------------------------------------
        # Response
        # -----------------------------------------
        return {
            "success": True,
            "summary": summary,
            "generated_sql": sql_query,
            "count": len(records),
            "result": records,
            "is_truncated": is_truncated,
            "truncation_reason": truncation_reason,
            "returned_rows": returned_rows,
            "total_rows": total_rows,
            "result_size_bytes": result_size_bytes,
        }

    except HTTPException:
        raise
    except Exception as e:
        settings = get_settings()
        safe_msg = get_safe_exception_message(
            e,
            is_production=settings.is_production,
            context="query"
        )
        print("\nException (sanitized):", safe_msg)
        return {
            "success": False,
            "error": safe_msg
        }
