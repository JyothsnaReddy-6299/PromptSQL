from fastapi import APIRouter, Header, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import re
import json

from app.services.table_manager import get_current_table
from app.services.sql_generator import generate_sql
from app.services.sql_validator import prepare_sql
from app.services.sql_regenerator import regenerate_sql
from app.services.sql_executor import execute_sql

from app.services.result_interpreter import interpret_result
from app.services.aggregate_summary import generate_aggregate_summary
from app.services.summary_generator import generate_summary
from app.services.auth_service import get_current_user_id
from app.services.query_planner import resolve_or_create_plan, compile_plan_to_sql, PlanCompilationError
from app.services.metric_service import get_authorized_dataset_columns
from app.database.connection import engine, SessionLocal
from app.models.history import QueryHistory
from app.utils.json_helper import sanitize_for_json
from sqlalchemy import text

router = APIRouter()


class AskRequest(BaseModel):
    question: str


MAX_RETRIES = 2  # Additional repair attempts after the initial query


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

        # Authorization must also reject system tables and unscoped names.
        if not table_name.endswith(f"_{user_id}"):
            raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")

        # -----------------------------------------
        # 1. Structured Metrics & Ambiguity / Clarification Engine
        # -----------------------------------------
        from app.services.query_planner import UnsupportedMetricError
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
            if plan:
                allowed_cols = get_authorized_dataset_columns(table_name, user_id)
                planned_sql, planned_params = compile_plan_to_sql(plan, table_name, allowed_cols)

                # Execute deterministic SQL
                with engine.connect() as conn:
                    res = conn.execute(text(planned_sql), planned_params)
                    records = [dict(row._mapping) for row in res]

                summary = generate_aggregate_summary(payload.question, planned_sql, records, plan=plan)

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
                        "date_range": plan.get("date_range"),
                        "limit": plan.get("limit"),
                        "ordering": plan.get("ordering"),
                        "tie_handling": plan.get("tie_handling"),
                        "explanation": plan["explanation"]
                    }
                }
        except UnsupportedMetricError as ume:
            return {
                "success": False,
                "error": str(ume),
                "unsupported_metric": True
            }
        except PlanCompilationError as plan_err:
            print("\n[Ask Router] Structured planner skipped or fell back to generative SQL:", plan_err)

        # -----------------------------------------
        # 2. Generative SQL Pipeline (Fallback for complex/custom shapes)
        # -----------------------------------------
        from sqlalchemy import inspect
        inspector = inspect(engine)
        all_tables = inspector.get_table_names()
        suffix = f"_{user_id}"
        all_user_tables = [t for t in all_tables if t.endswith(suffix) and t not in ["query_history", "audit_logs", "users"]]

        user_tables = list(dict.fromkeys([table_name] + all_user_tables))
        sql_query = generate_sql(
            payload.question,
            table_name,
            user_id
        )

        # Validation and execution share one bounded repair loop. Every repair is
        # parsed and authorized again before any query reaches the database.
        records = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                physical_sql = prepare_sql(sql_query, user_tables)
                records = execute_sql(physical_sql)
                sql_query = physical_sql
                break
            except Exception as query_err:
                message = str(query_err)
                for table in user_tables:
                    message = message.replace(table, table.split("_usr_")[0])
                if attempt == MAX_RETRIES:
                    return {"success": False, "error": message}
                sql_query = regenerate_sql(
                    payload.question, table_name, sql_query, message, user_id
                )

        result_type = interpret_result(sql_query, records)
        if result_type in ["AGGREGATE", "GROUP_AGGREGATE"]:
            summary = generate_aggregate_summary(payload.question, sql_query, records)
        else:
            try:
                summary = generate_summary(payload.question, records)
            except Exception:
                summary = f"Retrieved {len(records):,} matching records."

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

    except HTTPException:
        raise
    except Exception as e:
        print("\nException:", str(e))
        return {
            "success": False,
            "error": str(e)
        }
