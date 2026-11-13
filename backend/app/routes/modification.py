import re
import secrets
import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from app.database.connection import SessionLocal, engine
from app.models.audit_log import AuditLog
from app.models.history import QueryHistory
from app.models.pending_modification import PendingModification
from app.services.intent_detector import detect_intent
from app.services.modification_sql_generator import generate_modification_sql
from app.services.modification_validator import validate_modification_sql
from app.services.impact_estimator import estimate_affected_rows
from app.services.impact_explainer import explain_impact
from app.services.modification_executor import execute_modification
from app.services.auth_service import get_current_user_id
from app.services.dataset_guard import (
    resolve_and_authorize_dataset,
    get_user_datasets,
    verify_all_referenced_tables,
    safe_quote_table_name,
    is_system_table
)
from app.utils.tz_helper import get_ist_time
from app.utils.json_helper import sanitize_for_json
from app.utils.error_sanitizer import sanitize_error_message
import json

router = APIRouter(prefix="/modification", tags=["Modification"])

MODIFICATION_TTL_MINUTES = 15
DEFAULT_STALE_EXECUTION_TIMEOUT_SECONDS = 60


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ModificationAskRequest(BaseModel):
    question: str


class ModificationExecuteRequest(BaseModel):
    confirmation_token: Optional[str] = None
    # Legacy fields accepted for API compatibility but NEVER trusted for execution
    sql: Optional[str] = None
    intent: Optional[str] = None
    table_name: Optional[str] = None
    question: Optional[str] = None


class ReconcileRequest(BaseModel):
    token: Optional[str] = None
    stale_timeout_seconds: Optional[int] = DEFAULT_STALE_EXECUTION_TIMEOUT_SECONDS


def is_query_still_running_in_db(sql_to_execute: str, table_name: str) -> bool:
    """
    Inspects MySQL processlist to determine if the SQL or target table is currently
    actively executing in the database engine.
    Ensures legitimate long-running DDL operations are not mistakenly declared as crashed.
    """
    try:
        with engine.connect() as conn:
            res = conn.execute(text(
                "SELECT ID, COMMAND, TIME, STATE, INFO FROM information_schema.processlist "
                "WHERE COMMAND != 'Sleep' AND INFO IS NOT NULL"
            )).fetchall()
            clean_target = table_name.lower().strip("`")
            for row in res:
                info = (row.INFO or "").lower()
                if clean_target in info and any(k in info for k in ["alter", "drop", "truncate", "update", "insert", "delete"]):
                    return True
        return False
    except Exception as e:
        print("Processlist inspection error:", e)
        return False


def reconcile_stale_modification(pending: PendingModification, db: Session) -> dict:
    """
    Safely reconciles a pending modification stuck in EXECUTING state:
    1. Checks if the query is still actively executing in MySQL engine (SHOW PROCESSLIST).
    2. Checks AuditLog for verified completion (SUCCESS or FAILURE).
    3. Inspects database schema/table state for DDL operations:
       - DROP: if table no longer exists -> EXECUTED.
       - ALTER ADD COLUMN: if column exists in table schema -> EXECUTED.
       - ALTER MODIFY COLUMN, ALTER DROP COLUMN, TRUNCATE: if structural evidence is ambiguous or absent -> UNKNOWN.
    4. Concurrency: Uses atomic status transition filter to prevent multi-worker race conditions.
    Never returns to PENDING. Never automatically reruns SQL.
    """
    # 0. Active database execution check: do not declare a currently running query as crashed
    if is_query_still_running_in_db(pending.sql_to_execute, pending.table_name):
        return {
            "token": pending.token,
            "reconciled": False,
            "status": "EXECUTING",
            "evidence": "Query is still actively executing in MySQL engine"
        }

    target_status = "UNKNOWN"
    status_message = "Execution timed out without conclusive evidence of completion or rollback. Manual reconciliation required."
    evidence_desc = "None (uncertain outcome)"
    executed_at = None

    # 1. Audit evidence check
    recent_audit = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == pending.user_id,
            AuditLog.table_name == pending.table_name,
            AuditLog.generated_sql == pending.sql_to_execute
        )
        .order_by(AuditLog.id.desc())
        .first()
    )
    if recent_audit and recent_audit.timestamp >= (pending.started_executing_at or pending.created_at):
        if recent_audit.status == "SUCCESS":
            target_status = "EXECUTED"
            status_message = "Reconciled from verified AuditLog SUCCESS evidence."
            executed_at = recent_audit.timestamp
            evidence_desc = "AuditLog SUCCESS"
        elif recent_audit.status == "FAILURE":
            target_status = "FAILED"
            status_message = "Reconciled from verified AuditLog FAILURE evidence."
            evidence_desc = "AuditLog FAILURE"

    # 2. Structural DDL evidence check (only when audit log is absent)
    elif pending.intent == "DROP":
        try:
            inspector = inspect(engine)
            if pending.table_name not in inspector.get_table_names():
                target_status = "EXECUTED"
                status_message = "Reconciled: Target table no longer exists in database; DROP completed."
                executed_at = get_ist_time()
                evidence_desc = "Target table no longer exists in schema"
        except Exception as insp_err:
            print("Reconciliation inspection error on DROP:", insp_err)

    elif pending.intent == "ALTER":
        try:
            # Check for ALTER ADD COLUMN
            match_add = re.search(r"add\s+(?:column\s+)?`?([a-zA-Z0-9_]+)`?", pending.sql_to_execute, re.IGNORECASE)
            if match_add:
                col_added = match_add.group(1).lower()
                inspector = inspect(engine)
                cols = [c["name"].lower() for c in inspector.get_columns(pending.table_name)]
                if col_added in cols:
                    target_status = "EXECUTED"
                    status_message = f"Reconciled: Column `{col_added}` verified in table schema; ALTER completed."
                    executed_at = get_ist_time()
                    evidence_desc = f"Column {col_added} verified in schema"
            # For ALTER MODIFY COLUMN and ALTER DROP COLUMN, structural evidence alone without baseline
            # is insufficient to guarantee this exact operation ran; falls through to UNKNOWN.
        except Exception as insp_err:
            print("Reconciliation inspection error on ALTER:", insp_err)

    # For TRUNCATE TABLE: rowcount=0 alone cannot prove the table was truncated vs already empty; falls through to UNKNOWN.

    # 3. Atomic transition update to prevent concurrent worker conflicts
    rows_updated = (
        db.query(PendingModification)
        .filter(
            PendingModification.id == pending.id,
            PendingModification.status == "EXECUTING"
        )
        .update({
            "status": target_status,
            "status_message": status_message,
            "executed_at": executed_at
        })
    )
    db.commit()

    if rows_updated == 0:
        db.refresh(pending)
        return {
            "token": pending.token,
            "reconciled": False,
            "status": pending.status,
            "evidence": "Already reconciled by concurrent worker"
        }

    return {
        "token": pending.token,
        "reconciled": True,
        "status": target_status,
        "evidence": evidence_desc
    }


@router.post("/ask")
def ask_modification(
    payload: ModificationAskRequest,
    x_table_name: Optional[str] = Header(None),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Step 1 of Modification Flow (Server-Side Preview Generation):
    - Authenticates the user and resolves authorized active dataset.
    - Generates physical SQL statement on backend.
    - Performs AST validation (no statement chaining, no admin commands, no cross-tenant refs).
    - Estimates affected rows and flags unreliable estimates cleanly.
    - Persists an immutable PendingModification record with confirmation token.
    - Returns preview details to client for user approval.
    """
    # 1. Authorize dataset
    table_name = resolve_and_authorize_dataset(
        user_id=user_id,
        requested_table_name=x_table_name
    )
    user_datasets = get_user_datasets(user_id)

    # 2. Detect Intent
    intent = detect_intent(payload.question)
    if intent not in ["UPDATE", "INSERT", "DELETE", "MERGE", "ALTER", "DROP", "TRUNCATE", "CREATE"]:
        return {
            "success": True,
            "is_modification": False,
            "requires_confirmation": False,
            "message": "This request does not appear to be a data or schema modification."
        }

    friendly_name = table_name.split(f"_usr_{user_id.split('_')[-1]}")[0] if f"_usr_{user_id.split('_')[-1]}" in table_name else table_name

    # 3. Generate physical SQL
    try:
        sql = generate_modification_sql(payload.question, table_name, intent)
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed generating SQL for modification: {safe_msg}"
        )

    # Replace friendly name with physical table name in quotes
    pattern = rf"(?<![a-zA-Z0-9_`])`?{re.escape(friendly_name)}`?(?![a-zA-Z0-9_`])"
    physical_sql = re.sub(pattern, safe_quote_table_name(table_name, user_datasets), sql)

    # 4. Strict AST Validation
    verify_all_referenced_tables(physical_sql, user_id, user_datasets)
    validation = validate_modification_sql(physical_sql, table_name, intent, user_datasets)

    if not validation["valid"]:
        return {
            "success": False,
            "error": validation["error"],
            "requires_confirmation": False
        }

    # 5. Estimate affected rows (cleanly distinguish reliable from unreliable)
    est_result = estimate_affected_rows(physical_sql, table_name, intent, user_id, user_datasets)
    est_rows = est_result["estimated_rows"]
    is_reliable = est_result["reliable"]

    # 6. Generate natural language impact explanation
    impact_text = explain_impact(physical_sql, table_name, intent, est_rows)
    if not is_reliable:
        impact_text = "Impact could not be estimated reliably. " + impact_text

    # 7. Execution Policy: separate DML vs DDL
    is_ddl = intent.upper() in ["ALTER", "DROP", "TRUNCATE", "CREATE"]
    policy = "DDL" if is_ddl else "DML"

    # 8. Create server-side PendingModification record
    confirmation_token = secrets.token_hex(32)
    created_at = get_ist_time()
    expires_at = created_at + datetime.timedelta(minutes=MODIFICATION_TTL_MINUTES)

    pending_record = PendingModification(
        token=confirmation_token,
        user_id=user_id,
        table_name=table_name,
        question=payload.question,
        intent=intent,
        execution_policy=policy,
        sql_to_execute=physical_sql,
        estimated_rows=est_rows,
        impact_explanation=impact_text,
        warning=validation["warning"],
        status="PENDING",
        created_at=created_at,
        expires_at=expires_at
    )
    db.add(pending_record)
    db.commit()

    return {
        "success": True,
        "intent": intent,
        "policy": policy,
        "sql": sql,
        "table_name": table_name,
        "target_dataset": friendly_name,
        "requires_confirmation": True,
        "warning": validation["warning"],
        "impact_explanation": impact_text,
        "estimated_rows": est_rows,
        "reliable_estimate": is_reliable,
        "confirmation_token": confirmation_token,
        "expires_at": expires_at.isoformat()
    }


@router.post("/execute")
def execute_modification_query(
    payload: ModificationExecuteRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Step 2 of Modification Flow (Secure Execution via Confirmation Token):
    - Authenticates the user.
    - Retrieves pending modification record via confirmation token.
    - Verifies tenant ownership and ensures token is unexpired and unexecuted.
    - Recovers/reconciles stale EXECUTING records instead of blindly re-running.
    - Completely ignores any client-supplied SQL statements.
    - Re-validates the original server-stored SQL immediately prior to execution.
    - Executes query with distinct DML (transactional rollback) vs DDL (implicit commit) policies.
    - Records audit log and query history with verified status distinction.
    """
    token = payload.confirmation_token

    if not token or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid confirmation token from a server preview is required for execution."
        )

    clean_token = token.strip()

    # 1. Retrieve the pending modification from server-side database storage
    pending = db.query(PendingModification).filter(PendingModification.token == clean_token).first()
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending modification not found. Please generate a new preview."
        )

    # 2. Strict Tenant Authorization: verify the token belongs to the authenticated user
    if pending.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not own this pending modification."
        )

    # 3. Check expiration
    now = get_ist_time()
    if now > pending.expires_at:
        pending.status = "EXPIRED"
        pending.status_message = "Modification expired before execution."
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This modification confirmation has expired. Please request a fresh preview."
        )

    # 4. Check status to prevent duplicate or replayed execution
    if pending.status == "EXECUTED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This modification has already been executed."
        )

    if pending.status in ["FAILED", "EXPIRED", "BOOKKEEPING_FAILED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Modification cannot be executed (current status: {pending.status})."
        )

    if pending.status == "UNKNOWN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Modification outcome is uncertain and cannot be re-executed. Reconciliation or administrative review is required."
        )

    # Check for stale or ongoing EXECUTING status
    if pending.status == "EXECUTING":
        started = pending.started_executing_at or pending.created_at
        elapsed_seconds = (now - started).total_seconds()

        # Check if still running in MySQL database engine regardless of elapsed time
        if is_query_still_running_in_db(pending.sql_to_execute, pending.table_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This modification is currently still executing in the database engine (elapsed: {int(elapsed_seconds)}s). Please wait for completion."
            )

        if elapsed_seconds > DEFAULT_STALE_EXECUTION_TIMEOUT_SECONDS:
            reconcile_result = reconcile_stale_modification(pending, db)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Modification was stuck in EXECUTING and has been reconciled (status: {pending.status}: {pending.status_message}). It cannot be re-executed."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This modification is currently being processed by another worker. Please wait."
            )

    if pending.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Modification cannot be executed (current status: {pending.status})."
        )

    # 5. Atomic state transition to prevent race conditions and concurrent double-execution
    rows_locked = (
        db.query(PendingModification)
        .filter(
            PendingModification.id == pending.id,
            PendingModification.status == "PENDING"
        )
        .update({
            "status": "EXECUTING",
            "started_executing_at": now
        })
    )
    db.commit()

    if rows_locked == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This modification is currently being processed or has already executed."
        )

    # 6. Retrieve original validated SQL from server storage (NEVER trust client-supplied SQL!)
    table_name = pending.table_name
    physical_sql = pending.sql_to_execute
    intent = pending.intent
    user_datasets = get_user_datasets(user_id)

    # 7. Re-verify table ownership and re-validate SQL immediately before execution
    try:
        resolve_and_authorize_dataset(user_id=user_id, requested_table_name=table_name)
        verify_all_referenced_tables(physical_sql, user_id, user_datasets)
        validation = validate_modification_sql(physical_sql, table_name, intent, user_datasets)
        if not validation["valid"]:
            pending.status = "FAILED"
            pending.status_message = validation["error"]
            db.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=validation["error"])
    except HTTPException:
        pending.status = "FAILED"
        pending.status_message = "Re-validation failed prior to execution."
        db.commit()
        raise

    # 8. Execute query with separate DML vs DDL execution policies
    try:
        result = execute_modification(physical_sql, table_name, intent)
    except Exception as unexpected_err:
        # Unexpected infrastructure crash during execution -> outcome UNKNOWN
        pending.status = "UNKNOWN"
        pending.status_message = f"Execution interrupted by unexpected error: {str(unexpected_err)}"
        db.commit()
        try:
            db_log = AuditLog(
                user_id=user_id,
                operation=intent,
                table_name=table_name,
                generated_sql=physical_sql,
                rows_affected=0,
                status="UNKNOWN",
                error_message=str(unexpected_err)
            )
            db.add(db_log)
            db.commit()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Execution was interrupted. Outcome is uncertain and cannot be replayed automatically."
        )

    # 9. Update state & save audit / history records
    if result["success"]:
        # If dataset was permanently dropped, clear active dataset state for this user
        if intent == "DROP":
            try:
                from app.services.table_manager import get_current_table, clear_current_table
                if get_current_table(user_id=user_id) == table_name:
                    clear_current_table(user_id=user_id)
            except Exception:
                pass

        bookkeeping_err = None

        try:
            pending.status = "EXECUTED"
            pending.actual_rows_affected = result["rows_affected"]
            pending.executed_at = get_ist_time()
            pending.status_message = "Executed successfully."
            db.commit()
        except Exception as e:
            bookkeeping_err = f"Failed updating pending status: {e}"

        # Save to Audit Log
        try:
            db_log = AuditLog(
                user_id=user_id,
                operation=intent,
                table_name=table_name,
                generated_sql=physical_sql,
                rows_affected=result["rows_affected"],
                status="SUCCESS",
                error_message=None
            )
            db.add(db_log)
            db.commit()
        except Exception as audit_err:
            print("Audit logging error:", audit_err)
            bookkeeping_err = (bookkeeping_err or "") + f" Audit log error: {audit_err}"

        # Save to Query History
        try:
            db_history = QueryHistory(
                user_id=user_id,
                table_name=table_name,
                question=pending.question,
                generated_sql=physical_sql,
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
            bookkeeping_err = (bookkeeping_err or "") + f" Query history error: {history_err}"

        if bookkeeping_err:
            try:
                db.rollback()
                db.query(PendingModification).filter(PendingModification.id == pending.id).update({
                    "status": "BOOKKEEPING_FAILED",
                    "status_message": bookkeeping_err,
                    "actual_rows_affected": result["rows_affected"],
                    "executed_at": get_ist_time()
                })
                db.commit()
            except Exception as update_err:
                print("Failed updating status to BOOKKEEPING_FAILED:", update_err)
            result["bookkeeping_status"] = "BOOKKEEPING_FAILED"
            result["warning"] = "SQL executed and committed successfully, but post-execution bookkeeping encountered an error: " + bookkeeping_err
        else:
            result["bookkeeping_status"] = "COMPLETED"

        return result
    else:
        pending.status = "FAILED"
        pending.status_message = result.get("error")
        pending.actual_rows_affected = 0
        db.commit()

        # Log failed attempt in Audit Log
        try:
            db_log = AuditLog(
                user_id=user_id,
                operation=intent,
                table_name=table_name,
                generated_sql=physical_sql,
                rows_affected=0,
                status="FAILURE",
                error_message=result.get("error")
            )
            db.add(db_log)
            db.commit()
        except Exception as audit_err:
            print("Audit logging error on failure:", audit_err)

        return result


@router.post("/reconcile")
def reconcile_stale_records(
    payload: ReconcileRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id)
):
    """
    Administrative & user reconciliation mechanism for stuck or stale EXECUTING records:
    - If a specific token is given, verifies ownership and reconciles that record.
    - If no token is given, scans the authenticated user's records stuck in EXECUTING
      beyond the configured timeout and transitions them based on evidence.
    """
    now = get_ist_time()
    timeout = payload.stale_timeout_seconds or DEFAULT_STALE_EXECUTION_TIMEOUT_SECONDS
    cutoff = now - datetime.timedelta(seconds=timeout)

    reconciled_items = []

    if payload.token:
        pending = db.query(PendingModification).filter(PendingModification.token == payload.token.strip()).first()
        if not pending:
            raise HTTPException(status_code=404, detail="Modification record not found.")
        if pending.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied.")
        if pending.status != "EXECUTING":
            return {"message": f"Modification is not in EXECUTING state (current: {pending.status}).", "items": []}

        res = reconcile_stale_modification(pending, db)
        reconciled_items.append(res)
    else:
        stale_records = (
            db.query(PendingModification)
            .filter(
                PendingModification.user_id == user_id,
                PendingModification.status == "EXECUTING",
                (PendingModification.started_executing_at < cutoff) | (PendingModification.started_executing_at == None)
            )
            .all()
        )
        for rec in stale_records:
            res = reconcile_stale_modification(rec, db)
            reconciled_items.append(res)

    return {
        "success": True,
        "reconciled_count": len(reconciled_items),
        "items": reconciled_items
    }
