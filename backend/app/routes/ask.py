from fastapi import APIRouter, Header, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import re
import json
from app.services import relationship_service
from app.services.join_guard import guard_query

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
    relationship_ids: Optional[list[str]] = None
    dataset_ids: Optional[list[str]] = None


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

        if table_name in {'users','query_history','saved_reports','audit_logs','business_metrics','clarification_sessions','dataset_references','dataset_relationships','promptsql_migrations'}:
            raise HTTPException(status_code=403,detail='System tables are not query datasets.')
        from sqlalchemy import inspect
        from app.services.dataset_resolution import canonical_dataset
        required_tables, approved_path = [table_name], []
        relationships_ready = inspect(engine).has_table('dataset_references')
        if relationships_ready:
            # Resolve/authorize IDs, logical labels and physical names against the
            # same owned catalog used by the relationship workspace and graph.
            try:
                table_name = canonical_dataset(table_name,relationship_service.catalog(user_id))['table_name']
            except relationship_service.RelationshipError as exc:
                raise HTTPException(status_code=403,detail=str(exc)) from exc
            required_tables, approved_path = relationship_service.query_context(
                user_id,payload.question,table_name,payload.relationship_ids,payload.dataset_ids)
            table_name = required_tables[0]
        elif not table_name.endswith(f"_{user_id}"):
            raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")

        # -----------------------------------------
        # 1. Structured Metrics & Ambiguity / Clarification Engine
        # -----------------------------------------
        from app.services.query_planner import UnsupportedMetricError
        try:
            if len(required_tables) > 1:
                raise PlanCompilationError('Use the existing generative planner with approved relationships.')
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
                    "table_name": table_name,
                    "resolved_datasets": required_tables,
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
        # SQL validation and generation receive only the resolved source/path
        # scope, never every uploaded dataset or every approved relationship.
        user_tables = list(dict.fromkeys(required_tables + [
            t for rel in approved_path for t in (rel['left_table'],rel['right_table'])]))
        selected_relationships = [r['id'] for r in approved_path] or payload.relationship_ids
        sql_query = generate_sql(
            payload.question,
            table_name,
            user_id, relationship_ids=selected_relationships, required_tables=user_tables
        )

        # Validation and execution share one bounded repair loop. Every repair is
        # parsed and authorized again before any query reaches the database.
        records = None
        join_explanation = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                physical_sql = prepare_sql(sql_query, user_tables)
                if relationships_ready:
                    physical_sql, join_explanation = guard_query(physical_sql, user_id, selected_relationships, required_tables)
                else:
                    import sqlglot
                    from sqlglot import exp
                    if len({t.name for t in sqlglot.parse_one(physical_sql, read='mysql').find_all(exp.Table)}) > 1:
                        raise relationship_service.RelationshipError('Run the relationship migration before using multi-dataset queries.')
                records = execute_sql(physical_sql)
                sql_query = physical_sql
                break
            except relationship_service.RelationshipError:
                raise
            except Exception as query_err:
                message = str(query_err)
                for table in user_tables:
                    message = message.replace(table, table.split("_usr_")[0])
                if attempt == MAX_RETRIES:
                    return {"success": False, "error": message}
                sql_query = regenerate_sql(
                    payload.question, table_name, sql_query, message, user_id, relationship_ids=selected_relationships, required_tables=user_tables
                )

        result_type = interpret_result(sql_query, records)
        if result_type in ["AGGREGATE", "GROUP_AGGREGATE"]:
            summary = generate_aggregate_summary(payload.question, sql_query, records)
        else:
            try:
                summary = generate_summary(payload.question, records)
            except Exception:
                summary = f"Retrieved {len(records):,} matching records."

        if join_explanation:
            details = ["Datasets: " + ", ".join(join_explanation['datasets'])]
            for rel in join_explanation['relationships']:
                details.append(f"Approved relationship {rel['name']} ({rel['join_type']}): " + ", ".join(k['left'] + ' = ' + k['right'] for k in rel['keys']))
            details += [f"Metric source: {m['source']}; grain: {m['grain']}" for m in join_explanation['metrics']]
            details += [p['dataset'] + ': ' + p['strategy'] for p in join_explanation['preaggregation']]
            details += join_explanation['warnings']
            details.append(join_explanation['verification'])
            summary += "\n\n" + "\n".join(details)

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
            "result": records,
            "join_explanation": join_explanation,
            "table_name": table_name,
            "resolved_datasets": required_tables
        }

    except (relationship_service.RelationshipChoice, relationship_service.DatasetChoice) as choice:
        import uuid
        from datetime import timedelta
        from app.models.clarification import ClarificationSession
        from app.utils.tz_helper import get_ist_time
        is_dataset_choice = isinstance(choice,relationship_service.DatasetChoice)
        clar_id = ('ds_' if is_dataset_choice else 'rel_') + uuid.uuid4().hex
        with SessionLocal() as db:
            db.add(ClarificationSession(id=clar_id, user_id=user_id,
                original_question=payload.question, table_name=table_name,
                clarification_prompt=str(choice), options_json=json.dumps(choice.options),
                proposed_plan_json=json.dumps({'kind': 'dataset' if is_dataset_choice else 'relationship',
                    'dataset_ids': payload.dataset_ids, 'relationship_ids': payload.relationship_ids}),
                expires_at=get_ist_time()+timedelta(minutes=30)))
            db.commit()
        return dict(success=True, needs_clarification=True, clarification_id=clar_id,
                    prompt=str(choice), options=choice.options, original_question=payload.question)
    except relationship_service.RelationshipError as exc:
        return {'success': False, 'error': str(exc), 'relationship_limitation': True,
                'resolved_datasets': getattr(exc,'resolved_datasets',locals().get('required_tables', []))}
    except HTTPException:
        raise
    except Exception as e:
        print("\nException:", str(e))
        return {
            "success": False,
            "error": str(e)
        }
