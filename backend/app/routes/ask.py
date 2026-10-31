from fastapi import APIRouter, Header, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import re
import json

from app.services.table_manager import get_current_table
from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.sql_regenerator import regenerate_sql
from app.services.sql_executor import execute_sql

from app.services.result_interpreter import interpret_result
from app.services.aggregate_summary import generate_aggregate_summary
from app.services.summary_generator import generate_summary
from app.services.auth_service import get_current_user_id
from app.services.query_planner import resolve_or_create_plan, compile_plan_to_sql
from app.services.metric_service import get_authorized_dataset_columns
from app.database.connection import engine, SessionLocal
from app.models.history import QueryHistory
from app.utils.json_helper import sanitize_for_json
from sqlalchemy import text

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

        # -----------------------------------------
        # 1. Structured Metrics & Ambiguity / Clarification Engine
        # -----------------------------------------
        try:
            plan_result = resolve_or_create_plan(payload.question, table_name, user_id)

            if plan_result.get("needs_clarification"):
                return {
                    "success": True,
                    "needs_clarification": True,
                    "clarification_id": plan_result["clarification_id"],
                    "prompt": plan_result["prompt"],
                    "options": plan_result["options"],
                    "original_question": payload.question
                }

            plan = plan_result.get("plan")
            # Only compile via structured planner if a metric and dimensions/ordering were structured
            if plan and (plan.get("grouping_dimensions") or plan.get("limit") or plan.get("filters") or plan.get("metric_id")):
                allowed_cols = get_authorized_dataset_columns(table_name, user_id)
                planned_sql, planned_params = compile_plan_to_sql(plan, table_name, allowed_cols)

                # Execute deterministic SQL
                with engine.connect() as conn:
                    res = conn.execute(text(planned_sql), planned_params)
                    records = [dict(row._mapping) for row in res]

                result_type = interpret_result(planned_sql, records)
                if result_type in ["AGGREGATE", "GROUP_AGGREGATE"]:
                    summary = generate_aggregate_summary(payload.question, planned_sql, records)
                else:
                    summary = generate_summary(payload.question, records)

                # Save to query history
                try:
                    db_session = SessionLocal()
                    db_history = QueryHistory(
                        user_id=user_id,
                        table_name=table_name,
                        question=payload.question,
                        generated_sql=planned_sql,
                        summary=summary,
                        result_count=len(records),
                        result_json=json.dumps(sanitize_for_json(records))
                    )
                    db_session.add(db_history)
                    db_session.commit()
                    db_session.close()
                except Exception as history_err:
                    print("\nFailed logging query history:", str(history_err))

                return {
                    "success": True,
                    "summary": summary,
                    "generated_sql": planned_sql,
                    "count": len(records),
                    "result": records,
                    "plan": plan,
                    "interpretation": {
                        "metric_name": plan["metric_name"],
                        "expression": plan["metric_expression"],
                        "aggregation": plan["metric_aggregation"],
                        "dimensions": plan["grouping_dimensions"],
                        "filters": plan["filters"],
                        "explanation": plan["explanation"]
                    }
                }
        except Exception as plan_err:
            print("\n[Ask Router] Structured planner skipped or fell back to generative SQL:", plan_err)

        # -----------------------------------------
        # 2. Generative SQL Pipeline (Fallback for complex/custom shapes)
        # -----------------------------------------
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

                table_matched = (
                    friendly_tbl in question_lower or 
                    friendly_tbl.replace("_", " ") in question_lower or
                    (len(friendly_clean) > 3 and friendly_clean in question_lower) or
                    any(word in friendly_tbl for word in question_lower.split() if len(word) > 3)
                )

                column_matched = False
                if not table_matched:
                    try:
                        for col in inspector.get_columns(t):
                            col_name = col["name"].lower()
                            if col_name in ["id", "_row_id", "key", "date", "name", "city", "email", "status", "type"]:
                                continue
                            if any(word in col_name for word in question_lower.split() if len(word) > 3):
                                column_matched = True
                                break
                    except Exception:
                        pass

                if table_matched or column_matched:
                    user_tables.append(t)

        sql_query = generate_sql(
            payload.question,
            table_name,
            user_id
        )

        for _ in range(MAX_RETRIES):
            physical_sql = sql_query
            for t in user_tables:
                friendly_tbl = t.split("_usr_")[0]
                physical_sql = re.sub(rf"(?<!\w)\`?{re.escape(friendly_tbl)}\`?(?!\w)", f"`{t}`", physical_sql)

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
        else:
            return {
                "success": False,
                "error": message
            }

        physical_sql = sql_query
        for t in user_tables:
            friendly_tbl = t.split("_usr_")[0]
            physical_sql = re.sub(rf"(?<!\w)\`?{re.escape(friendly_tbl)}\`?(?!\w)", f"`{t}`", physical_sql)

        records = execute_sql(physical_sql)

        result_type = interpret_result(sql_query, records)
        if result_type in ["AGGREGATE", "GROUP_AGGREGATE"]:
            summary = generate_aggregate_summary(payload.question, sql_query, records)
        else:
            summary = generate_summary(payload.question, records)

        try:
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

        return {
            "success": True,
            "summary": summary,
            "generated_sql": sql_query,
            "count": len(records),
            "result": records
        }

    except Exception as e:
        print("\nException:", str(e))
        return {
            "success": False,
            "error": str(e)
        }
