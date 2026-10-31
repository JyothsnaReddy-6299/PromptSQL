from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from app.database.connection import SessionLocal, engine
from app.services.auth_service import get_current_user_id
from app.services.table_manager import get_current_table
from app.services.metric_service import (
    create_or_update_metric,
    list_metrics,
    get_metric,
    delete_metric,
    get_authorized_dataset_columns
)
from app.services.metric_parser import validate_and_compile_expression
from app.models.clarification import ClarificationSession
from app.services.query_planner import (
    resolve_or_create_plan,
    compile_plan_to_sql
)
from app.services.sql_executor import execute_sql
from app.services.summary_generator import generate_summary
from app.services.aggregate_summary import generate_aggregate_summary
from app.services.result_interpreter import interpret_result
from app.utils.tz_helper import get_ist_time

router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


class MetricCreateRequest(BaseModel):
    name: str
    source_dataset: str
    expression: str
    supported_aggregation: str = "SUM"
    description: Optional[str] = ""
    approved_aliases: Optional[List[str]] = []
    optional_filters: Optional[List[Dict[str, Any]]] = []
    currency_unit: Optional[str] = ""


class MetricTestRequest(BaseModel):
    source_dataset: str
    expression: str
    supported_aggregation: str = "SUM"


class ClarificationResolveRequest(BaseModel):
    clarification_id: str
    selected_option_id: str
    save_as_default_metric: Optional[bool] = False


@router.get("")
def get_user_metrics(
    dataset: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    try:
        metrics = list_metrics(user_id=user_id, source_dataset=dataset)
        return {"success": True, "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
def create_metric_endpoint(
    req: MetricCreateRequest,
    user_id: str = Depends(get_current_user_id)
):
    try:
        metric = create_or_update_metric(
            user_id=user_id,
            name=req.name,
            source_dataset=req.source_dataset,
            expression=req.expression,
            supported_aggregation=req.supported_aggregation,
            description=req.description or "",
            approved_aliases=req.approved_aliases,
            optional_filters=req.optional_filters,
            currency_unit=req.currency_unit or ""
        )
        return {"success": True, "metric": metric}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{metric_id}")
def get_metric_endpoint(
    metric_id: int,
    user_id: str = Depends(get_current_user_id)
):
    metric = get_metric(metric_id=metric_id, user_id=user_id)
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")
    return {"success": True, "metric": metric}


@router.put("/{metric_id}")
def update_metric_endpoint(
    metric_id: int,
    req: MetricCreateRequest,
    user_id: str = Depends(get_current_user_id)
):
    try:
        metric = create_or_update_metric(
            user_id=user_id,
            name=req.name,
            source_dataset=req.source_dataset,
            expression=req.expression,
            supported_aggregation=req.supported_aggregation,
            description=req.description or "",
            approved_aliases=req.approved_aliases,
            optional_filters=req.optional_filters,
            currency_unit=req.currency_unit or "",
            metric_id=metric_id
        )
        return {"success": True, "metric": metric}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{metric_id}")
def delete_metric_endpoint(
    metric_id: int,
    user_id: str = Depends(get_current_user_id)
):
    deleted = delete_metric(metric_id=metric_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Metric not found or access denied")
    return {"success": True, "message": "Metric deleted successfully"}


@router.post("/test")
def test_metric_endpoint(
    req: MetricTestRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Dry-runs a metric expression against the authorized dataset table.
    """
    try:
        allowed_cols = get_authorized_dataset_columns(req.source_dataset, user_id)
        compiled_sql, referenced_cols = validate_and_compile_expression(
            req.expression,
            allowed_cols,
            req.supported_aggregation
        )

        # Run safe preview query
        test_query = f"SELECT {compiled_sql} AS `test_metric_val` FROM `{req.source_dataset}`"
        records = execute_sql(test_query)
        sample_value = records[0]["test_metric_val"] if records else None

        return {
            "success": True,
            "compiled_sql": compiled_sql,
            "referenced_columns": referenced_cols,
            "sample_value": sample_value
        }
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# CLARIFICATION RESOLVER ENDPOINT
# -------------------------------------------------------------
clarification_router = APIRouter(prefix="/api/clarification", tags=["Clarification"])


@clarification_router.post("/resolve")
def resolve_clarification(
    req: ClarificationResolveRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Resumes the original question after the user selects an option.
    Validates ownership, applies the selected metric definition, compiles SQL,
    and executes the query.
    """
    db: Session = SessionLocal()
    try:
        session = db.query(ClarificationSession).filter(
            ClarificationSession.id == req.clarification_id,
            ClarificationSession.user_id == user_id
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="Clarification session not found or access denied.")

        if session.expires_at < get_ist_time():
            raise HTTPException(status_code=400, detail="Clarification session has expired. Please ask again.")

        import json
        options = json.loads(session.options_json)
        selected_option = next((opt for opt in options if opt["id"] == req.selected_option_id), None)

        if not selected_option:
            raise HTTPException(status_code=400, detail=f"Option '{req.selected_option_id}' is invalid.")

        table_name = session.table_name
        original_question = session.original_question

        # Save as approved metric definition if requested or if it has a definition
        if req.save_as_default_metric or selected_option.get("metric_name"):
            try:
                friendly_table = table_name.split("_usr_")[0]
                create_or_update_metric(
                    user_id=user_id,
                    name=selected_option.get("metric_name", selected_option["label"]),
                    source_dataset=table_name,
                    expression=selected_option["expression"],
                    supported_aggregation=selected_option.get("aggregation", "SUM"),
                    description=selected_option.get("description", ""),
                    approved_aliases=[selected_option["id"], "sales", selected_option.get("metric_name", "").lower()],
                    currency_unit=selected_option.get("currency_unit", "")
                )
            except Exception as e:
                print("Note: Could not auto-save metric from clarification:", e)

        # Build resolved plan with the chosen metric override
        allowed_cols = get_authorized_dataset_columns(table_name, user_id)
        plan_result = resolve_or_create_plan(
            question=original_question,
            table_name=table_name,
            user_id=user_id,
            override_metric=selected_option
        )

        plan = plan_result["plan"]
        sql_query, sql_params = compile_plan_to_sql(plan, table_name, allowed_cols)

        # Execute SQL
        from sqlalchemy import text
        with engine.connect() as conn:
            res = conn.execute(text(sql_query), sql_params)
            records = [dict(row._mapping) for row in res]

        # Generate summary
        result_type = interpret_result(sql_query, records)
        if result_type in ["AGGREGATE", "GROUP_AGGREGATE"]:
            summary = generate_aggregate_summary(original_question, sql_query, records)
        else:
            summary = generate_summary(original_question, records)

        # Log to query history
        try:
            from app.models.history import QueryHistory
            from app.utils.json_helper import sanitize_for_json
            db_history = QueryHistory(
                user_id=user_id,
                table_name=table_name,
                question=original_question,
                generated_sql=sql_query,
                summary=summary,
                result_count=len(records),
                result_json=json.dumps(sanitize_for_json(records))
            )
            db.add(db_history)
            db.commit()
        except Exception as he:
            print("History logging error on clarification resolve:", he)

        # Clean up clarification session
        db.delete(session)
        db.commit()

        return {
            "success": True,
            "summary": summary,
            "generated_sql": sql_query,
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
    finally:
        db.close()
