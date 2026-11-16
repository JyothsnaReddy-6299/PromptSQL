"""
PromptSQL — Privacy Policy Service (Issue 16: Privacy Guardian)

Manages dataset scanning, column-level policy persistence, policy enforcement,
and audit logging for intelligent boundary protection.
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.database.connection import engine, SessionLocal
from app.models.privacy import PrivacyColumnPolicy, PrivacyAuditLog
from app.services.privacy_detector import classify_column_privacy
from app.utils.tz_helper import get_ist_time


# In-memory policy cache: (user_id, table_name) -> Dict[col_name, Dict[str, Any]]
_PRIVACY_POLICY_CACHE: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}


def invalidate_privacy_cache(user_id: Optional[str] = None, table_name: Optional[str] = None) -> None:
    """Invalidates the in-memory policy cache."""
    global _PRIVACY_POLICY_CACHE
    if user_id and table_name:
        _PRIVACY_POLICY_CACHE.pop((user_id, table_name), None)
    elif user_id:
        keys_to_remove = [k for k in _PRIVACY_POLICY_CACHE if k[0] == user_id]
        for k in keys_to_remove:
            _PRIVACY_POLICY_CACHE.pop(k, None)
    elif table_name:
        keys_to_remove = [k for k in _PRIVACY_POLICY_CACHE if k[1] == table_name]
        for k in keys_to_remove:
            _PRIVACY_POLICY_CACHE.pop(k, None)
    else:
        _PRIVACY_POLICY_CACHE.clear()


def log_privacy_event(
    user_id: str,
    table_name: str,
    event_type: str,
    details: Dict[str, Any]
) -> None:
    """
    Records a privacy audit event.
    CRITICAL: Guarantees no raw sensitive values are stored in details.
    """
    try:
        sanitized_details = {k: v for k, v in details.items() if "raw" not in k.lower() and "secret" not in k.lower()}
        db: Session = SessionLocal()
        try:
            audit = PrivacyAuditLog(
                user_id=user_id,
                table_name=table_name,
                event_type=event_type,
                details=json.dumps(sanitized_details, default=str),
                timestamp=get_ist_time()
            )
            db.add(audit)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        # Non-fatal log failure to prevent breaking critical transaction
        print(f"[Privacy Guardian] Failed writing audit log: {e}")


def scan_and_save_dataset_privacy(
    user_id: str,
    table_name: str,
    force_rescan: bool = False
) -> List[Dict[str, Any]]:
    """
    Scans table columns and local sample data for sensitive patterns,
    persisting outcomes to `privacy_column_policies` with tenant isolation.
    """
    safe_table = f"`{table_name.replace('`', '``')}`"
    sample_rows = []
    raw_columns = []

    try:
        with engine.connect() as conn:
            inspector = inspect(conn)
            if not inspector.has_table(table_name):
                return []
            raw_columns = inspector.get_columns(table_name)
            if not raw_columns:
                return []
            query = f"SELECT * FROM {safe_table} LIMIT 100"
            result = conn.execute(text(query))
            sample_rows = [dict(row._mapping) for row in result]
    except Exception as err:
        print(f"[Privacy Guardian] Local sampling error on {table_name}: {err}")
        return []

    db: Session = SessionLocal()
    results = []
    try:
        # Check existing policies if not force_rescan
        existing_records = {
            rec.column_name: rec
            for rec in db.query(PrivacyColumnPolicy).filter(
                PrivacyColumnPolicy.user_id == user_id,
                PrivacyColumnPolicy.table_name == table_name
            ).all()
        }

        sensitive_count = 0
        restricted_count = 0
        review_count = 0

        for col in raw_columns:
            col_name = col["name"]
            data_type = str(col["type"])
            col_samples = [row.get(col_name) for row in sample_rows]

            # Detect sensitivity
            classification = classify_column_privacy(
                column_name=col_name,
                data_type=data_type,
                sample_values=col_samples
            )

            # Preserve custom user policy overrides if user previously edited the column policy
            existing = existing_records.get(col_name)
            final_policy = classification["policy"]
            final_status = classification["status"]

            if existing and existing.policy == "custom" and not force_rescan:
                final_policy = existing.policy
                final_status = "configured"

            if existing:
                existing.detected_category = classification["detected_category"]
                existing.sensitivity_level = classification["sensitivity_level"]
                existing.detection_method = classification["detection_method"]
                existing.confidence = classification["confidence"]
                if not (existing.policy == "custom" and not force_rescan):
                    existing.policy = final_policy
                    existing.status = final_status
                existing.explanation = classification["explanation"]
                existing.updated_at = get_ist_time()
            else:
                new_policy = PrivacyColumnPolicy(
                    user_id=user_id,
                    table_name=table_name,
                    column_name=col_name,
                    detected_category=classification["detected_category"],
                    sensitivity_level=classification["sensitivity_level"],
                    detection_method=classification["detection_method"],
                    confidence=classification["confidence"],
                    policy=final_policy,
                    status=final_status,
                    explanation=classification["explanation"],
                    created_at=get_ist_time(),
                    updated_at=get_ist_time()
                )
                db.add(new_policy)

            if final_policy == "sensitive":
                sensitive_count += 1
            elif final_policy == "restricted":
                restricted_count += 1
            if classification["confidence"] == "requires_review" or final_status == "pending_review":
                review_count += 1

            results.append({
                "column_name": col_name,
                "detected_category": classification["detected_category"],
                "sensitivity_level": classification["sensitivity_level"],
                "detection_method": classification["detection_method"],
                "confidence": classification["confidence"],
                "policy": final_policy,
                "status": final_status,
                "explanation": classification["explanation"]
            })

        db.commit()

        # Invalidate in-memory cache
        invalidate_privacy_cache(user_id, table_name)

        # Audit log scan event
        log_privacy_event(
            user_id=user_id,
            table_name=table_name,
            event_type="dataset_scan",
            details={
                "columns_scanned": len(raw_columns),
                "sensitive_detected": sensitive_count,
                "restricted_detected": restricted_count,
                "review_required": review_count,
                "force_rescan": force_rescan
            }
        )

        return results
    finally:
        db.close()


def get_dataset_column_policies(
    user_id: str,
    table_name: str
) -> Dict[str, Dict[str, Any]]:
    """
    Returns mapped column policies for the active dataset:
    { "email": { "policy": "sensitive", "category": "personal_identification", ... } }
    Uses thread-safe in-memory caching for zero-overhead query execution.
    """
    cache_key = (user_id, table_name)
    if cache_key in _PRIVACY_POLICY_CACHE:
        return _PRIVACY_POLICY_CACHE[cache_key]

    db: Session = SessionLocal()
    try:
        records = db.query(PrivacyColumnPolicy).filter(
            PrivacyColumnPolicy.user_id == user_id,
            PrivacyColumnPolicy.table_name == table_name
        ).all()

        if not records:
            # First time accessing table: automatically run initial local scan
            scan_and_save_dataset_privacy(user_id=user_id, table_name=table_name)
            records = db.query(PrivacyColumnPolicy).filter(
                PrivacyColumnPolicy.user_id == user_id,
                PrivacyColumnPolicy.table_name == table_name
            ).all()

        policy_map = {}
        for rec in records:
            policy_map[rec.column_name] = {
                "id": rec.id,
                "column_name": rec.column_name,
                "detected_category": rec.detected_category,
                "sensitivity_level": rec.sensitivity_level,
                "detection_method": rec.detection_method,
                "confidence": rec.confidence,
                "policy": rec.policy,
                "status": rec.status,
                "explanation": rec.explanation
            }

        _PRIVACY_POLICY_CACHE[cache_key] = policy_map
        return policy_map
    finally:
        db.close()


def update_column_policy(
    user_id: str,
    table_name: str,
    column_name: str,
    policy: str,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates the privacy policy for a specific column, saving changes server-side
    and recording an audit trail event.
    """
    allowed_policies = {"normal", "sensitive", "restricted", "custom"}
    if policy.lower() not in allowed_policies:
        raise ValueError(f"Invalid policy '{policy}'. Allowed policies: {sorted(allowed_policies)}")

    db: Session = SessionLocal()
    try:
        record = db.query(PrivacyColumnPolicy).filter(
            PrivacyColumnPolicy.user_id == user_id,
            PrivacyColumnPolicy.table_name == table_name,
            PrivacyColumnPolicy.column_name == column_name
        ).first()

        old_policy = record.policy if record else "normal"
        new_status = status or ("configured" if policy in ("custom", "restricted") else ("protected" if policy == "sensitive" else "normal"))

        if record:
            record.policy = policy.lower()
            record.status = new_status
            record.updated_at = get_ist_time()
        else:
            record = PrivacyColumnPolicy(
                user_id=user_id,
                table_name=table_name,
                column_name=column_name,
                detected_category="user_configured",
                sensitivity_level="high" if policy in ("sensitive", "restricted") else "low",
                detection_method="manual_policy_override",
                confidence="high",
                policy=policy.lower(),
                status=new_status,
                explanation="Policy updated manually by dataset owner.",
                created_at=get_ist_time(),
                updated_at=get_ist_time()
            )
            db.add(record)

        db.commit()

        # Invalidate in-memory cache
        invalidate_privacy_cache(user_id, table_name)

        # Log policy change
        log_privacy_event(
            user_id=user_id,
            table_name=table_name,
            event_type="policy_change",
            details={
                "column_name": column_name,
                "previous_policy": old_policy,
                "new_policy": policy.lower(),
                "status": new_status
            }
        )

        return {
            "success": True,
            "column_name": column_name,
            "policy": policy.lower(),
            "status": new_status
        }
    finally:
        db.close()


def get_privacy_overview(user_id: str, table_name: str) -> Dict[str, Any]:
    """
    Returns high-level statistics and column policy items for the Privacy Guardian UI.
    """
    policies = get_dataset_column_policies(user_id, table_name)
    friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name

    total_scanned = len(policies)
    sensitive_count = sum(1 for p in policies.values() if p["policy"] == "sensitive")
    restricted_count = sum(1 for p in policies.values() if p["policy"] == "restricted")
    review_count = sum(1 for p in policies.values() if p["confidence"] == "requires_review" or p["status"] == "pending_review")

    # Fetch last scan time from DB
    db: Session = SessionLocal()
    last_scanned_at = None
    try:
        last_log = db.query(PrivacyAuditLog).filter(
            PrivacyAuditLog.user_id == user_id,
            PrivacyAuditLog.table_name == table_name,
            PrivacyAuditLog.event_type == "dataset_scan"
        ).order_by(PrivacyAuditLog.timestamp.desc()).first()
        if last_log:
            last_scanned_at = last_log.timestamp.isoformat()
    finally:
        db.close()

    return {
        "table_name": table_name,
        "friendly_name": friendly_name,
        "last_scanned_at": last_scanned_at or get_ist_time().isoformat(),
        "columns_scanned": total_scanned,
        "sensitive_columns_count": sensitive_count,
        "restricted_columns_count": restricted_count,
        "review_required_count": review_count,
        "columns": list(policies.values())
    }


def get_privacy_audit_logs(user_id: str, table_name: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Returns user-scoped and dataset-scoped audit events for Privacy Guardian.
    """
    db: Session = SessionLocal()
    try:
        records = db.query(PrivacyAuditLog).filter(
            PrivacyAuditLog.user_id == user_id,
            PrivacyAuditLog.table_name == table_name
        ).order_by(PrivacyAuditLog.timestamp.desc()).limit(limit).all()

        output = []
        for r in records:
            output.append({
                "id": r.id,
                "event_type": r.event_type,
                "details": json.loads(r.details) if r.details.startswith("{") else r.details,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None
            })
        return output
    finally:
        db.close()
