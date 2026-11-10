"""
PromptSQL — Centralized Active Dataset Table Manager

Authoritative active-dataset state store backed exclusively by MySQL.
Guarantees atomic consistency across multi-worker and multi-container deployments.
Process-local caches and filesystem fallback have been eliminated to prevent
cache desynchronization, stale state overrides, and multi-process race conditions.
"""

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import text

from app.database.connection import engine


def set_current_table(table_name: str, user_id: Optional[str] = None) -> None:
    """
    Stores active table scoped strictly to the specific user.
    Executes a single atomic database upsert (INSERT ... ON DUPLICATE KEY UPDATE)
    directly in the authoritative MySQL database.
    Does not use process-local caching or local filesystem files, ensuring
    100% authoritative consistency across all worker processes and containers.
    """
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        return

    clean_user_id = user_id.strip()
    clean_table = (table_name or "").strip()

    now = datetime.now(timezone.utc)
    try:
        with engine.connect() as conn:
            if clean_table:
                # Single-statement atomic upsert in MySQL engine
                sql = text("""
                    INSERT INTO user_active_datasets (user_id, table_name, updated_at)
                    VALUES (:uid, :tbl, :now)
                    ON DUPLICATE KEY UPDATE
                        table_name = VALUES(table_name),
                        updated_at = VALUES(updated_at)
                """)
                conn.execute(sql, {"uid": clean_user_id, "tbl": clean_table, "now": now})
            else:
                conn.execute(
                    text("DELETE FROM user_active_datasets WHERE user_id = :uid"),
                    {"uid": clean_user_id}
                )
            conn.commit()
    except Exception as e:
        print(f"[TABLE MANAGER ERROR] Atomic database upsert failed for user '{clean_user_id}': {e}")
        raise


def get_current_table(user_id: Optional[str] = None) -> Optional[str]:
    """
    Retrieves active table scoped strictly to user_id directly from authoritative MySQL database.
    Returns None if user_id is missing or if no active table is set in the database.
    If database connectivity fails, raises the database error so the request fails safely
    without falling back to potentially stale process cache or disk files.
    """
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        return None

    clean_user_id = user_id.strip()

    try:
        with engine.connect() as conn:
            sql = text("SELECT table_name FROM user_active_datasets WHERE user_id = :uid LIMIT 1")
            result = conn.execute(sql, {"uid": clean_user_id}).scalar()
            return str(result).strip() if result else None
    except Exception as e:
        print(f"[TABLE MANAGER ERROR] Authoritative database lookup failed for user '{clean_user_id}': {e}")
        raise


def clear_current_table(user_id: Optional[str] = None) -> None:
    """
    Atomically clears active dataset state for the specified user in the authoritative MySQL database.
    """
    set_current_table("", user_id=user_id)
