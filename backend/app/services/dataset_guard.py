"""
PromptSQL — Centralized Database Tenant Isolation & Dataset Guard

This module provides the single source of truth for:
1. Classifying and protecting internal system tables.
2. Validating dataset identifier formats.
3. Resolving and authorizing tenant dataset access based strictly on authenticated user identity.
4. Verifying multi-table SQL query references (e.g. JOIN queries).
5. Safe identifier quoting.
"""

import re
from typing import Collection, List, Optional, Set
from fastapi import HTTPException, Header, Depends, status
from sqlalchemy import inspect

from app.database.connection import engine
from app.services.auth_service import get_current_user_id
from app.services.table_manager import get_current_table, set_current_table

# ---------------------------------------------------------------------------
# 1. Centralized Explicit Denylist of Protected System Tables
# ---------------------------------------------------------------------------
PROTECTED_SYSTEM_TABLES: Set[str] = frozenset({
    "users",
    "query_history",
    "audit_logs",
    "saved_reports",
    "promptsql_migrations",
    "business_metrics",
    "clarification_sessions",
    "dataset_references",
    "dataset_relationships",
    "alembic_version",
    "pending_modifications",
})

# System schema prefixes (MySQL / MariaDB internal schemas)
PROTECTED_SCHEMA_PREFIXES = (
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
)

# Safe identifier pattern (alphanumeric, underscores, hyphens, parentheses from filenames)
SAFE_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_\(\)-]+$")


def is_system_table(table_name: Optional[str]) -> bool:
    """
    Returns True if table_name matches any known application system table
    or an internal database system schema/table.
    """
    if not table_name or not isinstance(table_name, str):
        return False
    clean = table_name.strip().strip("`").strip("'").strip('"').lower()
    if clean in PROTECTED_SYSTEM_TABLES:
        return True
    for pfx in PROTECTED_SCHEMA_PREFIXES:
        if clean == pfx or clean.startswith(f"{pfx}."):
            return True
    return False


def validate_table_identifier_format(table_name: str) -> None:
    """
    Ensures table identifier conforms to safe naming standards.
    Rejects SQL injection, path traversal, control characters, or malformed strings.
    """
    if not isinstance(table_name, str) or not table_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid dataset identifier: table name cannot be empty."
        )

    clean = table_name.strip().strip("`")
    if len(clean) > 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid dataset identifier: length exceeds maximum allowed (64 characters)."
        )

    if not SAFE_IDENTIFIER_REGEX.match(clean):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid dataset identifier: prohibited characters detected."
        )

    # Explicit defense against embedded SQL tokens
    lower = clean.lower()
    dangerous_tokens = (";", "--", "/*", "*/", "@@", "char(", "concat(", "select ", "drop ", "insert ", "update ", "delete ")
    for tok in dangerous_tokens:
        if tok in lower:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid dataset identifier: prohibited token."
            )


def get_user_datasets(user_id: str) -> List[str]:
    """
    Returns all verified physical table names in the database owned by user_id.
    Strictly excludes system tables and other tenants' datasets.
    """
    if not user_id:
        return []
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    suffix = f"_{user_id}"
    return [
        t for t in all_tables
        if t.endswith(suffix) and not is_system_table(t)
    ]


def resolve_and_authorize_dataset(
    user_id: str,
    requested_table_name: Optional[str] = None
) -> str:
    """
    Centralized server-side resolution and authorization function.
    
    1. Validates authenticated user ID.
    2. Resolves requested_table_name (or user's active table if omitted).
    3. Validates identifier format and length.
    4. Rejects protected system tables (403).
    5. Verifies database existence and tenant ownership:
       - If table belongs to another user -> 403 Forbidden.
       - If table does not exist -> 404 Not Found.
    6. Returns safe, verified physical table identifier.
    """
    if not user_id or not user_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required."
        )

    # 1. Resolve candidate table name
    target = (requested_table_name or "").strip()
    if not target:
        # Fall back to user-scoped active table
        active = get_current_table(user_id=user_id)
        if not active:
            user_tables = get_user_datasets(user_id)
            if user_tables:
                active = user_tables[0]
                set_current_table(active, user_id=user_id)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No dataset uploaded yet. Please upload a dataset first."
                )
        target = active

    # Strip enclosing backticks/quotes if present
    target = target.strip("`").strip("'").strip('"').strip()

    # 2. Check identifier format
    validate_table_identifier_format(target)

    # 3. Reject system tables immediately
    if is_system_table(target):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to access this dataset."
        )

    # 4. Check against live database
    inspector = inspect(engine)
    all_db_tables = inspector.get_table_names()

    suffix = f"_{user_id}"

    # Direct match: physical table name belonging to this user
    if target.endswith(suffix) and target in all_db_tables and not is_system_table(target):
        return target

    # Friendly name resolution: e.g. "customers" -> "customers_usr_1"
    friendly_physical = f"{target}_{user_id}"
    if friendly_physical in all_db_tables and not is_system_table(friendly_physical):
        return friendly_physical

    # Target is not authorized for this user. Determine precise error:
    # If the table exists in the database (system table, other user's table, unowned table):
    if target in all_db_tables or is_system_table(target) or "_usr_" in target:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to access this dataset."
        )

    # Does not exist in the database
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Dataset not found."
    )


def safe_quote_table_name(table_name: str, authorized_tables: Collection[str]) -> str:
    """
    Safely quotes a table name for SQL statements after verifying it is
    in the caller's authorized dataset collection.
    """
    if table_name not in authorized_tables:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Unauthorized table identifier."
        )
    clean = table_name.replace("`", "``")
    return f"`{clean}`"


def verify_all_referenced_tables(
    sql_query: str,
    user_id: str,
    authorized_tables: Collection[str]
) -> None:
    """
    Ensures that every database table referenced in an SQL query belongs to
    the authenticated user. Rejects system tables or other tenants' tables.
    """
    if not sql_query:
        return

    # Check for direct system table references
    for sys_tbl in PROTECTED_SYSTEM_TABLES:
        pattern = rf"(?<![a-zA-Z0-9_])`?{re.escape(sys_tbl)}`?(?![a-zA-Z0-9_])"
        if re.search(pattern, sql_query, re.IGNORECASE):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. One or more referenced tables are unauthorized."
            )

    # Check for schema qualification (information_schema., mysql., etc.)
    for pfx in PROTECTED_SCHEMA_PREFIXES:
        pattern = rf"(?<![a-zA-Z0-9_])`?{re.escape(pfx)}`?(?![a-zA-Z0-9_])"
        if re.search(pattern, sql_query, re.IGNORECASE):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. One or more referenced tables are unauthorized."
            )

    # Check all existing database tables
    inspector = inspect(engine)
    all_db_tables = inspector.get_table_names()
    for tbl in all_db_tables:
        if tbl not in authorized_tables:
            pattern = rf"(?<![a-zA-Z0-9_])`?{re.escape(tbl)}`?(?![a-zA-Z0-9_])"
            if re.search(pattern, sql_query, re.IGNORECASE):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied. One or more referenced tables are unauthorized."
                )


def get_authorized_dataset(
    x_table_name: Optional[str] = Header(None),
    user_id: str = Depends(get_current_user_id)
) -> str:
    """
    FastAPI dependency that resolves and authorizes dataset access.
    """
    return resolve_and_authorize_dataset(user_id=user_id, requested_table_name=x_table_name)
