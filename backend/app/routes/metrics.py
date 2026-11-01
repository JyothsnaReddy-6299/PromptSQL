import json
from decimal import Decimal
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database.connection import SessionLocal, engine
from app.services.auth_service import get_current_user_id
from app.services.table_manager import get_current_table
from app.services.metric_service import (
    create_or_update_metric,
    list_metrics,
    get_metric,
    delete_metric,
    get_authorized_dataset_columns,
    set_default_metric,
    reset_default_metric,
    get_default_metric
)
from app.services.metric_parser import validate_and_compile_expression
from app.models.clarification import ClarificationSession
from app.services.query_planner import (
    resolve_or_create_plan,
    compile_plan_to_sql,
    build_plan_explanation,
    refine_and_execute_plan,
    extract_dimensions_and_grouping
)
from app.services.sql_executor import execute_sql
from app.services.summary_generator import generate_summary
from app.services.aggregate_summary import generate_aggregate_summary, format_value
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
    is_default: Optional[bool] = False
    default_concept: Optional[str] = None


class MetricTestRequest(BaseModel):
    source_dataset: str
    expression: str
    supported_aggregation: str = "SUM"


class ClarificationResolveRequest(BaseModel):
    clarification_id: str
    selected_option_id: str
    save_as_default_metric: Optional[bool] = False


class RefineRequest(BaseModel):
    plan: Dict[str, Any]
    refinements: Dict[str, Any]
    table_name: str


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


@router.get("/columns")
def get_dataset_columns_endpoint(
    dataset: str,
    user_id: str = Depends(get_current_user_id)
):
    try:
        cols = get_authorized_dataset_columns(dataset, user_id)
        return {"success": True, "columns": cols}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
            currency_unit=req.currency_unit or "",
            is_default=req.is_default or False,
            default_concept=req.default_concept
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
            is_default=req.is_default or False,
            default_concept=req.default_concept,
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


@router.post("/{metric_id}/set-default")
def set_default_metric_endpoint(
    metric_id: int,
    concept: str = "sales",
    user_id: str = Depends(get_current_user_id)
):
    try:
        updated = set_default_metric(user_id=user_id, metric_id=metric_id, concept=concept)
        return {"success": True, "metric": updated}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reset-default")
def reset_default_metric_endpoint(
    dataset: str,
    concept: Optional[str] = "sales",
    user_id: str = Depends(get_current_user_id)
):
    try:
        reset_default_metric(user_id=user_id, source_dataset=dataset, concept=concept)
        return {"success": True, "message": "Default metric reset successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/test")
def test_metric_endpoint(
    req: MetricTestRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Dry-runs a metric expression against the authorized dataset table.
    Preserves precision and avoids floating point artifacts in previews.
    """
    try:
        allowed_cols = get_authorized_dataset_columns(req.source_dataset, user_id)
        compiled_sql, referenced_cols = validate_and_compile_expression(
            req.expression,
            allowed_cols,
            req.supported_aggregation
        )

        # Run safe preview query with limit 1
        test_query = f"SELECT {compiled_sql} AS `test_metric_val` FROM `{req.source_dataset}`"
        records = execute_sql(test_query)
        sample_value = records[0]["test_metric_val"] if records else None

        # Clean precision formatting
        formatted_val = format_value(sample_value)
        if isinstance(sample_value, (float, Decimal)):
            clean_val = round(float(sample_value), 2)
        else:
            clean_val = sample_value

        return {
            "success": True,
            "compiled_sql": compiled_sql,
            "referenced_columns": referenced_cols,
            "sample_value": clean_val,
            "formatted_sample_value": formatted_val
        }
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refine")
def refine_query_endpoint(
    req: RefineRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Applies user-specified refinements to an existing plan and re-executes.
    """
    try:
        result = refine_and_execute_plan(req.plan, req.refinements, req.table_name, user_id)
        new_plan = result["plan"]
        sql_query = result["sql"]
        sql_params = result["params"]

        with engine.connect() as conn:
            res = conn.execute(text(sql_query), sql_params)
            records = [dict(row._mapping) for row in res]

        summary = generate_aggregate_summary("Refined query", sql_query, records, plan=new_plan)

        return {
            "success": True,
            "summary": summary,
            "generated_sql": sql_query,
            "count": len(records),
            "result": records,
            "plan": new_plan,
            "interpretation": {
                "metric_name": new_plan["metric_name"],
                "expression": new_plan["metric_expression"],
                "aggregation": new_plan["metric_aggregation"],
                "dimensions": new_plan["grouping_dimensions"],
                "filters": new_plan["filters"],
                "date_range": new_plan.get("date_range"),
                "limit": new_plan.get("limit"),
                "ordering": new_plan.get("ordering"),
                "tie_handling": new_plan.get("tie_handling"),
                "explanation": new_plan["explanation"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    Validates ownership, preserves grouping dimensions and filters from the
    original plan, updates only the resolved metric, and executes safely.
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

        options = json.loads(session.options_json)
        selected_option = next((opt for opt in options if opt["id"] == req.selected_option_id), None)

        if not selected_option:
            raise HTTPException(status_code=400, detail=f"Option '{req.selected_option_id}' is invalid.")

        saved_context = json.loads(session.proposed_plan_json or '{}')
        if saved_context.get('kind') in ('relationship','dataset'):
            from app.routes.ask import ask_question, AskRequest
            question, table = session.original_question, session.table_name
            dataset_ids = selected_option.get('dataset_ids',saved_context.get('dataset_ids'))
            relationship_ids = selected_option.get('relationship_ids',saved_context.get('relationship_ids'))
            db.delete(session)
            db.commit()
            return ask_question(AskRequest(question=question,relationship_ids=relationship_ids,dataset_ids=dataset_ids),table,user_id)

        table_name = session.table_name
        original_question = session.original_question

        # Retrieve the partially resolved plan preserved across clarification
        saved_plan = {}
        if session.proposed_plan_json:
            try:
                saved_plan = json.loads(session.proposed_plan_json)
            except Exception:
                saved_plan = {}

        # Save as approved metric definition if requested
        if req.save_as_default_metric:
            try:
                create_or_update_metric(
                    user_id=user_id,
                    name=selected_option.get("metric_name", selected_option["label"]),
                    source_dataset=table_name,
                    expression=selected_option["expression"],
                    supported_aggregation=selected_option.get("aggregation", "SUM"),
                    description=selected_option.get("description", ""),
                    approved_aliases=[selected_option["id"], "sales", selected_option.get("metric_name", "").lower()],
                    currency_unit=selected_option.get("currency_unit", ""),
                    is_default=True,
                    default_concept="sales"
                )
            except Exception as e:
                print("Note: Could not auto-save metric from clarification:", e)

        # Build resolved plan by updating ONLY the unresolved metric
        allowed_cols = get_authorized_dataset_columns(table_name, user_id)
        metric_name = selected_option.get("metric_name") or selected_option.get("label") or "Revenue"
        _, measure_columns = validate_and_compile_expression(
            selected_option["expression"], allowed_cols,
            selected_option.get("aggregation", "SUM")
        )
        grouping_dims = extract_dimensions_and_grouping(
            original_question, allowed_cols, measure_columns
        )
        filters = saved_plan.get("filters", [])
        date_range = saved_plan.get("date_range")
        ordering = saved_plan.get("ordering", {"target": "metric", "direction": "DESC"})
        limit = saved_plan.get("limit")
        tie_handling = saved_plan.get("tie_handling", "standard")

        plan = {
            "dataset_table": table_name,
            "metric_name": metric_name,
            "metric_id": selected_option.get("metric_id"),
            "metric_expression": selected_option["expression"],
            "metric_aggregation": selected_option.get("aggregation", selected_option.get("supported_aggregation", "SUM")),
            "currency_unit": selected_option.get("currency_unit", ""),
            "description": selected_option.get("description", ""),
            "grouping_dimensions": grouping_dims,
            "filters": filters,
            "date_range": date_range,
            "ordering": ordering,
            "limit": limit,
            "tie_handling": tie_handling,
            "explanation": build_plan_explanation(
                metric_name,
                grouping_dims,
                limit,
                ordering.get("direction", "DESC"),
                filters,
                date_range
            )
        }

        sql_query, sql_params = compile_plan_to_sql(plan, table_name, allowed_cols)

        # Execute SQL
        with engine.connect() as conn:
            res = conn.execute(text(sql_query), sql_params)
            records = [dict(row._mapping) for row in res]

        summary = generate_aggregate_summary(original_question, sql_query, records, plan=plan)

        # Clean up clarification session to prevent stale execution
        db.delete(session)
        db.commit()

        # Log to query history in an isolated session
        try:
            from app.models.history import QueryHistory
            from app.utils.json_helper import sanitize_for_json
            db_hist = SessionLocal()
            try:
                db_history = QueryHistory(
                    user_id=user_id,
                    table_name=table_name,
                    question=original_question,
                    generated_sql=sql_query,
                    summary=summary,
                    result_count=len(records),
                    result_json=json.dumps(sanitize_for_json(records))
                )
                db_hist.add(db_history)
                db_hist.commit()
            finally:
                db_hist.close()
        except Exception as he:
            print("History logging error on clarification resolve:", he)

        return {
            "success": True,
            "summary": summary,
            "generated_sql": sql_query,
            "count": len(records),
            "result": records,
            "plan": plan,
            "table_name": table_name,
            "resolved_datasets": [table_name],
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
    finally:
        db.close()
