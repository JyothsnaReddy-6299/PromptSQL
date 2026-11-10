from typing import Optional, Collection
import sqlglot
from sqlglot import exp
from sqlalchemy import text
from app.database.connection import engine
from app.services.dataset_guard import (
    safe_quote_table_name,
    is_system_table,
    verify_all_referenced_tables
)


def estimate_affected_rows(
    sql: str,
    table_name: str,
    intent: str,
    user_id: Optional[str] = None,
    user_datasets: Optional[Collection[str]] = None
) -> dict:
    """
    Accurately estimates the number of rows that will be affected by a
    validated modification statement using AST analysis.

    Returns:
        dict: {
            "estimated_rows": Optional[int],  # integer count, or None if impact is unreliable
            "reliable": bool,                 # True if estimator can faithfully represent semantics
            "message": str                    # Human-readable impact explanation or warning
        }

    Semantics:
    - For UPDATE / DELETE: executes SELECT COUNT(*) using the exact WHERE clause and table alias.
    - For INSERT (multi-tuple): counts row tuples in the VALUES clause.
    - For INSERT ... SELECT: executes SELECT COUNT(*) on the inner source query.
    - For TRUNCATE / DROP: queries current total row count of the table.
    - For ALTER / CREATE: returns 0 data rows (schema structural change).
    - If semantics cannot be represented reliably or count query fails:
      returns estimated_rows=None, reliable=False, message="Impact could not be estimated reliably."
    """
    if is_system_table(table_name):
        return {
            "estimated_rows": None,
            "reliable": False,
            "message": "Impact cannot be estimated on protected system tables."
        }

    safe_tbl = f"`{table_name.replace('`', '``')}`"

    try:
        parsed = sqlglot.parse(sql, read="mysql")
        if not parsed:
            return {
                "estimated_rows": None,
                "reliable": False,
                "message": "Impact could not be estimated reliably."
            }
        stmt = parsed[0]

        # 1. UPDATE & DELETE
        if intent in ["UPDATE", "DELETE"]:
            # Check for table alias
            alias = getattr(stmt.this, "alias", None)
            alias_str = f" AS `{alias}`" if alias else ""

            where_node = stmt.args.get("where")
            where_clause = where_node.sql("mysql") if where_node else ""
            count_query = f"SELECT COUNT(*) FROM {safe_tbl}{alias_str} {where_clause}".strip()

            # Ensure subqueries cannot escape the authorized tenant dataset
            if user_id and user_datasets is not None:
                verify_all_referenced_tables(count_query, user_id, user_datasets)

            with engine.connect() as conn:
                res = conn.execute(text(count_query)).scalar()
                count = int(res) if res is not None else 0
                return {
                    "estimated_rows": count,
                    "reliable": True,
                    "message": f"{count} row(s) estimated to be affected."
                }

        # 2. INSERT (multi-tuple VALUES or INSERT ... SELECT)
        elif intent == "INSERT":
            # Check for INSERT ... SELECT
            select_node = stmt.find(exp.Select)
            if select_node:
                src_sql = select_node.sql("mysql")
                count_query = f"SELECT COUNT(*) FROM ({src_sql}) AS `_ins_sel_src`"

                if user_id and user_datasets is not None:
                    verify_all_referenced_tables(count_query, user_id, user_datasets)

                with engine.connect() as conn:
                    res = conn.execute(text(count_query)).scalar()
                    count = int(res) if res is not None else 0
                    return {
                        "estimated_rows": count,
                        "reliable": True,
                        "message": f"{count} row(s) estimated to be inserted."
                    }

            # Check for multi-row VALUES tuples
            tuples = list(stmt.find_all(exp.Tuple))
            if tuples:
                count = len(tuples)
                return {
                    "estimated_rows": count,
                    "reliable": True,
                    "message": f"{count} row(s) estimated to be inserted."
                }

            values_node = stmt.find(exp.Values)
            if values_node and hasattr(values_node, "expressions") and values_node.expressions:
                count = len(values_node.expressions)
                return {
                    "estimated_rows": count,
                    "reliable": True,
                    "message": f"{count} row(s) estimated to be inserted."
                }

            return {
                "estimated_rows": 1,
                "reliable": True,
                "message": "1 row estimated to be inserted."
            }

        # 3. TRUNCATE & DROP
        elif intent in ["TRUNCATE", "DROP"]:
            count_query = f"SELECT COUNT(*) FROM {safe_tbl}"
            with engine.connect() as conn:
                res = conn.execute(text(count_query)).scalar()
                count = int(res) if res is not None else 0
                action_word = "dropped" if intent == "DROP" else "truncated"
                return {
                    "estimated_rows": count,
                    "reliable": True,
                    "message": f"Table currently contains {count} record(s) that will be permanently {action_word}."
                }

        # 4. ALTER, CREATE, RENAME
        elif intent in ["ALTER", "CREATE", "RENAME"]:
            return {
                "estimated_rows": 0,
                "reliable": True,
                "message": "0 data rows affected. Schema structure will be modified."
            }

        return {
            "estimated_rows": None,
            "reliable": False,
            "message": "Impact could not be estimated reliably."
        }

    except Exception as e:
        print("Safe impact estimation error:", e)
        return {
            "estimated_rows": None,
            "reliable": False,
            "message": "Impact could not be estimated reliably."
        }
