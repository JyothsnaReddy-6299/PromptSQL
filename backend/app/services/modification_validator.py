import re
from typing import Optional, Collection
from sqlalchemy import inspect
import sqlglot
from sqlglot import exp

from app.database.connection import engine
from app.services.schema_service import get_column_names
from app.services.dataset_guard import (
    is_system_table,
    PROTECTED_SYSTEM_TABLES,
    PROTECTED_SCHEMA_PREFIXES,
    SAFE_IDENTIFIER_REGEX
)


def validate_modification_sql(
    sql: str,
    table_name: str,
    intent: str,
    authorized_tables: Optional[Collection[str]] = None
) -> dict:
    """
    Validates a generated modification query using AST parsing via SQLGlot,
    strictly enforcing:
    1. Exactly one SQL statement (no chaining or multiple statements).
    2. Intent and statement type consistency (no disguised administrative commands).
    3. No access to protected system tables or internal MySQL schemas.
    4. Target table ownership and rejection of joined cross-table modifications.
    5. Strict DDL policies (rejection of multi-table or database-level DROP/TRUNCATE).
    6. Safety warnings for unbounded UPDATE/DELETE and irreversible DDL operations.
    """
    if not sql or not sql.strip():
        return {"valid": False, "error": "SQL statement cannot be empty."}

    sql_clean = sql.strip()

    # 0. Global system table guard
    if is_system_table(table_name):
        return {
            "valid": False,
            "error": "Operation on protected system table is not permitted."
        }

    # 1. AST Parsing with SQLGlot
    try:
        parsed_statements = sqlglot.parse(sql_clean, read="mysql")
    except Exception as parse_err:
        return {
            "valid": False,
            "error": f"SQL syntax error: {str(parse_err)}"
        }

    if not parsed_statements:
        return {"valid": False, "error": "No valid SQL statement detected."}

    # Strict rule: exactly one statement
    if len(parsed_statements) != 1:
        return {
            "valid": False,
            "error": "Multiple or chained SQL statements are not permitted."
        }

    stmt = parsed_statements[0]

    # Reject administrative commands, stored procedure calls, or unknown commands
    if isinstance(stmt, exp.Command):
        return {
            "valid": False,
            "error": "Administrative commands and stored procedure calls are strictly prohibited."
        }

    # 2. Intent and Statement Type Mapping
    intent_ast_map = {
        "UPDATE": (exp.Update,),
        "INSERT": (exp.Insert,),
        "DELETE": (exp.Delete,),
        "MERGE": (exp.Insert,),  # MySQL INSERT ... ON DUPLICATE KEY UPDATE parses as exp.Insert
        "ALTER": (exp.Alter,),
        "DROP": (exp.Drop,),
        "TRUNCATE": (exp.TruncateTable,),
        "CREATE": (exp.Create,)
    }

    expected_types = intent_ast_map.get(intent)
    if not expected_types or not isinstance(stmt, expected_types):
        return {
            "valid": False,
            "error": f"SQL statement type '{type(stmt).__name__}' does not match detected intent '{intent}'."
        }

    # Reject joined modifications for UPDATE and DELETE
    if intent in ["UPDATE", "DELETE"]:
        joins = list(stmt.find_all(exp.Join))
        if joins:
            return {
                "valid": False,
                "error": "Joined modifications are not supported for safety and tenant isolation."
            }

    # Strict DDL scope checks before individual table matching
    if intent == "DROP":
        kind = (stmt.args.get("kind") or "").upper()
        if kind and kind not in ["TABLE", ""]:
            return {
                "valid": False,
                "error": "Database or schema-level DROP operations are strictly prohibited."
            }
        drop_tables = list(stmt.find_all(exp.Table))
        if len(drop_tables) != 1:
            return {
                "valid": False,
                "error": "Multi-table DROP operations are strictly prohibited."
            }

    if intent == "TRUNCATE":
        trunc_tables = list(stmt.find_all(exp.Table))
        if len(trunc_tables) != 1:
            return {
                "valid": False,
                "error": "Multi-table TRUNCATE operations are strictly prohibited."
            }

    # 3. Referenced Tables and System Table / Schema Protection
    referenced_tables = list(stmt.find_all(exp.Table))
    if not referenced_tables and intent not in ["CREATE"]:
        return {
            "valid": False,
            "error": "No target table referenced in SQL statement."
        }

    target_table_clean = table_name.lower().strip("`")

    for t in referenced_tables:
        t_name = t.name.lower().strip("`")
        t_schema = (t.db or "").lower().strip("`")

        # Check for system table access
        if is_system_table(t_name):
            return {
                "valid": False,
                "error": f"Query references a protected system table '{t_name}'."
            }

        # Check for schema qualification (information_schema, mysql, etc.)
        if t_schema:
            if is_system_table(t_schema) or any(t_schema == pfx for pfx in PROTECTED_SCHEMA_PREFIXES):
                return {
                    "valid": False,
                    "error": "Query references a protected system schema."
                }

        # Verify against authorized tables if provided
        if authorized_tables is not None:
            authorized_clean = {tbl.lower().strip("`") for tbl in authorized_tables}
            if t_name not in authorized_clean:
                return {
                    "valid": False,
                    "error": "Access denied. One or more referenced tables are unauthorized."
                }

    # Verify that the primary modified table is the active target table
    if intent in ["UPDATE", "INSERT", "DELETE", "MERGE", "ALTER", "TRUNCATE", "DROP"]:
        primary_table_found = any(t.name.lower().strip("`") == target_table_clean for t in referenced_tables)
        if not primary_table_found:
            return {
                "valid": False,
                "error": f"Query does not target the active table '{table_name}'."
            }

    # 4. Specific DDL Safety Checks
    warning = None

    if intent == "DROP":
        # Disallow dropping database or schema
        kind = (stmt.args.get("kind") or "").upper()
        if kind and kind not in ["TABLE", ""]:
            return {
                "valid": False,
                "error": "Database or schema-level DROP operations are strictly prohibited."
            }

        # Disallow multi-table DROP
        if len(referenced_tables) != 1:
            return {
                "valid": False,
                "error": "Multi-table DROP operations are strictly prohibited."
            }

        if is_system_table(table_name):
            return {"valid": False, "error": "Dropping system tables is strictly prohibited."}

        warning = f"CRITICAL: Irreversible DDL operation. Dropping table '{table_name}' will permanently destroy all records and table structure. MySQL DDL commits immediately and cannot be rolled back."

    elif intent == "TRUNCATE":
        if len(referenced_tables) != 1:
            return {
                "valid": False,
                "error": "Multi-table TRUNCATE operations are strictly prohibited."
            }

        if is_system_table(table_name):
            return {"valid": False, "error": "Truncating system tables is strictly prohibited."}

        warning = f"CRITICAL: Irreversible DDL operation. Truncating table '{table_name}' will permanently delete all records. MySQL DDL commits immediately and cannot be rolled back."

    elif intent == "ALTER":
        warning = f"Notice: MySQL DDL operation. Altering table structure of '{table_name}' commits immediately and cannot be rolled back."

    elif intent == "CREATE":
        match = re.search(r"create\s+table\s+(?:if\s+not\s+exists\s+)?`?([a-zA-Z0-9_\s-]+)`?", sql_clean, re.IGNORECASE)
        if match:
            created_table = match.group(1).strip()
            if is_system_table(created_table):
                return {
                    "valid": False,
                    "error": "Creating a table with a protected system table name is forbidden."
                }
            inspector = inspect(engine)
            if created_table in inspector.get_table_names():
                return {
                    "valid": False,
                    "error": f"Table '{created_table}' already exists. Duplicate table creation is rejected."
                }

    # 5. Column validation for DML operations on existing tables
    if intent in ["INSERT", "UPDATE", "DELETE", "MERGE"]:
        try:
            columns = get_column_names(table_name)
            col_set = {c.lower() for c in columns}
            for col in stmt.find_all(exp.Column):
                col_name = col.name.lower().strip("`")
                # Exclude wildcard or pseudo-columns
                if col_name == "*":
                    continue
                if col_name not in col_set:
                    return {
                        "valid": False,
                        "error": f"Column `{col.name}` does not exist in schema of table '{table_name}'."
                    }
        except Exception:
            pass

    # 6. Safety Warning: UPDATE or DELETE without WHERE clause
    if intent in ["UPDATE", "DELETE"]:
        where_node = stmt.args.get("where")
        if not where_node:
            warning = f"Warning: This {intent} query has no WHERE clause and will affect ALL records in the table!"

    return {
        "valid": True,
        "warning": warning,
        "error": None
    }
