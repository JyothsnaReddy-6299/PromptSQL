import re
from sqlalchemy import text
from app.database.connection import engine


def estimate_affected_rows(sql: str, table_name: str, intent: str) -> int:
    """
    Runs a SELECT COUNT(*) version of the query to get the number of rows
    that will be affected by UPDATE/DELETE, or reads table size for DROP/TRUNCATE.
    """
    if intent not in ["UPDATE", "DELETE", "TRUNCATE", "DROP"]:
        if intent == "INSERT":
            return 1
        return 0
        
    sql_lower = sql.lower()
    
    if intent in ["UPDATE", "DELETE"]:
        where_idx = sql_lower.find("where")
        if where_idx == -1:
            query = f"SELECT COUNT(*) FROM `{table_name}`"
        else:
            where_clause = sql[where_idx:]
            query = f"SELECT COUNT(*) FROM `{table_name}` {where_clause}"
    elif intent in ["DROP", "TRUNCATE"]:
        query = f"SELECT COUNT(*) FROM `{table_name}`"
    else:
        return 0
        
    # Clean query
    if query.endswith(";"):
        query = query[:-1]
        
    try:
        with engine.connect() as connection:
            res = connection.execute(text(query)).scalar()
            return int(res) if res is not None else 0
    except Exception as e:
        print("Error estimating affected rows:", e)
        return 0
