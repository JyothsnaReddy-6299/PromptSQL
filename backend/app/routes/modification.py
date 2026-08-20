from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
import re

from app.database.connection import SessionLocal
from app.models.audit_log import AuditLog
from app.services.table_manager import get_current_table
from app.services.intent_detector import detect_intent
from app.services.modification_sql_generator import generate_modification_sql
from app.services.modification_validator import validate_modification_sql
from app.services.impact_estimator import estimate_affected_rows
from app.services.impact_explainer import explain_impact
from app.services.modification_executor import execute_modification

from app.services.auth_service import get_current_user_id

router = APIRouter(prefix="/modification", tags=["Modification"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ModificationAskRequest(BaseModel):
    question: str


class ModificationExecuteRequest(BaseModel):
    sql: str
    intent: str
    table_name: str
    question: str


@router.post("/ask")
def ask_modification(
    payload: ModificationAskRequest,
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
):
    """
    Checks intent, generates SQL, validates safety checks, and returns a preview impact description.
    """
    table_name = x_table_name or get_current_table()
    if not table_name:
        raise HTTPException(status_code=400, detail="Please upload a dataset first.")

    # Security check: verify user owns the dataset
    if "_usr_" in table_name:
        owner_id = "usr_" + table_name.split("_usr_")[-1]
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")

    # 1. Detect user query intent (DML / DDL / SELECT)
    intent = detect_intent(payload.question)

    # 2. Separate select queries from modifications to preserve select pipeline
    if intent == "SELECT":
        return {
            "success": True,
            "intent": "SELECT",
            "requires_confirmation": False
        }

    # 3. Generate query modification SQL
    try:
        sql = generate_modification_sql(payload.question, table_name, intent)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL Generation error: {str(e)}")

    # Get base friendly table name
    friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name
    physical_sql = re.sub(rf"(?<!\w)\`?{re.escape(friendly_name)}\`?(?!\w)", f"`{table_name}`", sql)

    # 4. Validate SQL safety rules
    validation = validate_modification_sql(physical_sql, table_name, intent)
    if not validation["valid"]:
        return {
            "success": False,
            "error": validation["error"]
        }

    # 5. Estimate count of rows to be affected
    est_rows = estimate_affected_rows(physical_sql, table_name, intent)

    # 6. Generate natural language impact explanation
    impact_text = explain_impact(physical_sql, table_name, intent, est_rows)

    return {
        "success": True,
        "intent": intent,
        "sql": sql,
        "table_name": table_name,
        "requires_confirmation": True,
        "warning": validation["warning"],
        "impact_explanation": impact_text,
        "estimated_rows": est_rows
    }


@router.post("/execute")
def execute_modification_query(
    payload: ModificationExecuteRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Executes a validated query transactionally and saves audit log entry in database.
    """
    # Security check: verify user owns the dataset
    if "_usr_" in payload.table_name:
        owner_id = "usr_" + payload.table_name.split("_usr_")[-1]
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied. You do not own this dataset.")

    friendly_name = payload.table_name.split("_usr_")[0] if "_usr_" in payload.table_name else payload.table_name
    physical_sql = re.sub(rf"(?<!\w)\`?{re.escape(friendly_name)}\`?(?!\w)", f"`{payload.table_name}`", payload.sql)

    # Execute query inside transaction
    result = execute_modification(physical_sql, payload.table_name, payload.intent)

    # Save to Audit Log
    try:
        db_log = AuditLog(
            user_id=user_id,
            operation=payload.intent,
            table_name=payload.table_name,
            generated_sql=payload.sql,
            rows_affected=result["rows_affected"],
            status="SUCCESS" if result["success"] else "FAILURE",
            error_message=result["error"]
        )
        db.add(db_log)
        db.commit()
    except Exception as audit_err:
        print("Audit logging error:", audit_err)

    # Save to Query History if modification was executed successfully
    if result["success"]:
        try:
            from app.models.history import QueryHistory
            from app.utils.json_helper import sanitize_for_json
            import json
            db_history = QueryHistory(
                user_id=user_id,
                table_name=payload.table_name,
                question=payload.question,
                generated_sql=payload.sql,
                summary=result["message"],
                result_count=result["rows_affected"],
                result_json=json.dumps(sanitize_for_json(result.get("records", []))),
                undo_sql=result.get("undo_sql")
            )
            db.add(db_history)
            db.commit()
            db.refresh(db_history)
            result["history_id"] = db_history.id
        except Exception as history_err:
            print("Failed logging modification query to history:", history_err)

    return result
