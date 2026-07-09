from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database.connection import SessionLocal
from app.models.audit_log import AuditLog
from app.services.table_manager import get_current_table
from app.services.intent_detector import detect_intent
from app.services.modification_sql_generator import generate_modification_sql
from app.services.modification_validator import validate_modification_sql
from app.services.impact_estimator import estimate_affected_rows
from app.services.impact_explainer import explain_impact
from app.services.modification_executor import execute_modification

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


@router.post("/ask")
def ask_modification(payload: ModificationAskRequest):
    """
    Checks intent, generates SQL, validates safety checks, and returns a preview impact description.
    """
    table_name = get_current_table()
    if not table_name:
        raise HTTPException(status_code=400, detail="Please upload a dataset first.")

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

    # 4. Validate SQL safety rules
    validation = validate_modification_sql(sql, table_name, intent)
    if not validation["valid"]:
        return {
            "success": False,
            "error": validation["error"]
        }

    # 5. Estimate count of rows to be affected
    est_rows = estimate_affected_rows(sql, table_name, intent)

    # 6. Generate natural language impact explanation
    impact_text = explain_impact(sql, table_name, intent, est_rows)

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
def execute_modification_query(payload: ModificationExecuteRequest, db: Session = Depends(get_db)):
    """
    Executes a validated query transactionally and saves audit log entry in database.
    """
    # Execute query inside transaction
    result = execute_modification(payload.sql, payload.table_name, payload.intent)

    # Save to Audit Log
    try:
        db_log = AuditLog(
            user_id="default_user",
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

    return result
