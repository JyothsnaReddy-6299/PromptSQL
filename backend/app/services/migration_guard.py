import logging
import re
from typing import Any, Dict, Optional
from sqlalchemy import inspect, text, String, DateTime
from sqlalchemy.types import TypeEngine
from app.utils.error_sanitizer import sanitize_error_message

logger = logging.getLogger(__name__)

MIGRATION_LOCK_NAME = "promptsql_migration_lock"
DEFAULT_LOCK_TIMEOUT = 15
USER_ACTIVE_DATASETS_TABLE = "user_active_datasets"


def acquire_advisory_lock(conn, lock_name: str = MIGRATION_LOCK_NAME, timeout_seconds: int = DEFAULT_LOCK_TIMEOUT) -> bool:
    """
    Acquires a named MySQL advisory lock across all workers/containers.
    For non-MySQL dialects (e.g. SQLite test runners), acts as a no-op returning True.
    """
    dialect = getattr(conn.dialect, "name", "").lower()
    if dialect != "mysql":
        return True

    try:
        res = conn.execute(
            text("SELECT GET_LOCK(:lock_name, :timeout)"),
            {"lock_name": lock_name, "timeout": int(timeout_seconds)}
        ).scalar()
        return res == 1
    except Exception as e:
        logger.warning(f"Failed to acquire MySQL advisory lock '{lock_name}': {sanitize_error_message(str(e))}")
        return False


def release_advisory_lock(conn, lock_name: str = MIGRATION_LOCK_NAME) -> bool:
    """
    Releases a named MySQL advisory lock.
    """
    dialect = getattr(conn.dialect, "name", "").lower()
    if dialect != "mysql":
        return True

    try:
        res = conn.execute(
            text("SELECT RELEASE_LOCK(:lock_name)"),
            {"lock_name": lock_name}
        ).scalar()
        return res == 1
    except Exception as e:
        logger.warning(f"Failed to release MySQL advisory lock '{lock_name}': {sanitize_error_message(str(e))}")
        return False


def verify_user_active_datasets_schema(engine_or_conn, table_name: str = USER_ACTIVE_DATASETS_TABLE) -> Dict[str, Any]:
    """
    Verifies that the target active-datasets table exists and strictly matches the ORM model:
    - user_id: String/VARCHAR(>=50), NOT NULL, Primary Key
    - table_name: String/VARCHAR(>=64), NOT NULL
    - updated_at: DateTime/TIMESTAMP
    
    Raises RuntimeError with sanitized description if table is missing or incompatible.
    Never alters, drops, or destroys existing tables or data.
    """
    inspector = inspect(engine_or_conn)
    tables = inspector.get_table_names()
    if table_name not in tables:
        raise RuntimeError(f"Required table '{table_name}' does not exist.")

    columns = inspector.get_columns(table_name)
    col_map = {c["name"]: c for c in columns}

    # 1. Verify user_id column
    if "user_id" not in col_map:
        raise RuntimeError(f"Table '{table_name}' is missing required column 'user_id'.")
    uid_col = col_map["user_id"]
    uid_type = uid_col["type"]
    uid_type_str = str(uid_type).upper()
    if not (isinstance(uid_type, String) or "VARCHAR" in uid_type_str or "CHAR" in uid_type_str or "TEXT" in uid_type_str):
        raise RuntimeError(
            f"Table '{table_name}' column 'user_id' has incompatible type: expected VARCHAR/String, got {uid_type}."
        )
    uid_len = getattr(uid_type, "length", None)
    if uid_len is not None and uid_len < 50:
        raise RuntimeError(
            f"Table '{table_name}' column 'user_id' length is too short: expected >= 50, got {uid_len}."
        )
    if uid_col.get("nullable") is True:
        raise RuntimeError(f"Table '{table_name}' column 'user_id' must be NOT NULL.")

    # 2. Verify primary key
    pk_info = inspector.get_pk_constraint(table_name)
    pk_cols = pk_info.get("constrained_columns") or []
    if pk_cols != ["user_id"]:
        raise RuntimeError(
            f"Table '{table_name}' has invalid primary key: expected ['user_id'], got {pk_cols}."
        )

    # 3. Verify table_name column
    if "table_name" not in col_map:
        raise RuntimeError(f"Table '{table_name}' is missing required column 'table_name'.")
    tname_col = col_map["table_name"]
    tname_type = tname_col["type"]
    tname_type_str = str(tname_type).upper()
    if not (isinstance(tname_type, String) or "VARCHAR" in tname_type_str or "CHAR" in tname_type_str or "TEXT" in tname_type_str):
        raise RuntimeError(
            f"Table '{table_name}' column 'table_name' has incompatible type: expected VARCHAR/String, got {tname_type}."
        )
    tname_len = getattr(tname_type, "length", None)
    if tname_len is not None and tname_len < 64:
        raise RuntimeError(
            f"Table '{table_name}' column 'table_name' length is too short: expected >= 64, got {tname_len}."
        )
    if tname_col.get("nullable") is True:
        raise RuntimeError(f"Table '{table_name}' column 'table_name' must be NOT NULL.")

    # 4. Verify updated_at column
    if "updated_at" not in col_map:
        raise RuntimeError(f"Table '{table_name}' is missing required column 'updated_at'.")
    upd_col = col_map["updated_at"]
    upd_type = upd_col["type"]
    upd_type_str = str(upd_type).upper()
    if not (isinstance(upd_type, DateTime) or "DATETIME" in upd_type_str or "TIMESTAMP" in upd_type_str):
        raise RuntimeError(
            f"Table '{table_name}' column 'updated_at' has incompatible type: expected DATETIME/TIMESTAMP, got {upd_type}."
        )

    return {
        "valid": True,
        "table_name": table_name,
        "columns": [c["name"] for c in columns],
        "primary_key": pk_cols
    }


def ensure_user_active_datasets_table(
    engine,
    table_name: str = USER_ACTIVE_DATASETS_TABLE,
    lock_name: str = MIGRATION_LOCK_NAME,
    lock_timeout: int = DEFAULT_LOCK_TIMEOUT
) -> None:
    """
    Ensures that the user_active_datasets table exists and is fully verified.
    Acquires a cross-worker advisory lock during creation and schema verification.
    Aborts with a sanitized RuntimeError if initialization or verification fails.
    """
    try:
        with engine.connect() as conn:
            lock_acquired = acquire_advisory_lock(conn, lock_name=lock_name, timeout_seconds=lock_timeout)
            if not lock_acquired:
                raise RuntimeError(
                    f"Failed to acquire advisory migration lock '{lock_name}' within {lock_timeout}s timeout."
                )

            try:
                inspector = inspect(conn)
                if table_name not in inspector.get_table_names():
                    logger.info(f"[STARTUP] Creating '{table_name}' table for authoritative active-dataset state...")
                    create_sql = f"""
                        CREATE TABLE IF NOT EXISTS `{table_name}` (
                            `user_id` VARCHAR(50) NOT NULL PRIMARY KEY,
                            `table_name` VARCHAR(100) NOT NULL,
                            `updated_at` DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                    """
                    conn.execute(text(create_sql))
                    conn.commit()
                    logger.info(f"[STARTUP] Table '{table_name}' created successfully.")

                # Verify schema strictly
                verify_user_active_datasets_schema(conn, table_name=table_name)
            finally:
                release_advisory_lock(conn, lock_name=lock_name)
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        logger.error(f"[STARTUP FATAL] Failed initializing '{table_name}' schema: {safe_msg}")
        raise RuntimeError(f"Active dataset table initialization failed: {safe_msg}") from None
