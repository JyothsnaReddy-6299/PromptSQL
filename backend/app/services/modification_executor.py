import time
from sqlalchemy import text
from app.database.connection import engine
# Groq imports removed to simplify query confirmations without API calls


def extract_first_insert_identity(sql: str) -> tuple:
    import re
    # Match: INSERT INTO `table` (`col1`, `col2`, ...) VALUES ('val1', 'val2', ...)
    match = re.search(r"insert\s+into\s+\S+\s*\((.*?)\)\s*values\s*\((.*?)\)", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return None, None
        
    cols_str, vals_str = match.groups()
    
    # Split columns by comma and strip spaces/backticks
    cols = [c.strip().replace("`", "").replace("'", "").replace('"', '') for c in cols_str.split(",")]
    
    # Split values by comma respecting single/double quotes
    vals = []
    current_val = []
    in_single_quote = False
    in_double_quote = False
    escape = False
    
    for char in vals_str:
        if escape:
            current_val.append(char)
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue
        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue
        if char == ',' and not in_single_quote and not in_double_quote:
            vals.append("".join(current_val).strip())
            current_val = []
            continue
        current_val.append(char)
    vals.append("".join(current_val).strip())
    
    if cols and vals:
        return cols[0], vals[0]
    return None, None


def execute_modification(sql: str, table_name: str, intent: str) -> dict:
    """
    Executes a DML or DDL query inside a transaction, rolling back automatically
    on exception, and returns rows affected, execution time, and records affected.
    """
    start_time = time.time()
    records = []
    
    try:
        # Pre-fetch records if it is a DELETE operation (to know what was deleted)
        if intent == "DELETE":
            try:
                sql_lower = sql.lower()
                where_idx = sql_lower.find("where")
                if where_idx != -1:
                    where_clause = sql[where_idx:]
                    select_sql = f"SELECT * FROM `{table_name}` {where_clause}"
                else:
                    select_sql = f"SELECT * FROM `{table_name}`"
                if select_sql.endswith(";"):
                    select_sql = select_sql[:-1]
                with engine.connect() as conn:
                    res = conn.execute(text(select_sql))
                    records = [dict(row._mapping) for row in res]
            except Exception as select_err:
                print("Failed pre-fetching deleted records:", select_err)

        # Execute query transactionally
        with engine.begin() as connection:
            result = connection.execute(text(sql))
            rows_affected = result.rowcount
            
        elapsed_time_ms = (time.time() - start_time) * 1000
        
        if rows_affected is None or rows_affected < 0:
            rows_affected = 0
            
        # Post-fetch records for INSERT or UPDATE (to know what was changed)
        if intent == "INSERT":
            try:
                col_name, col_val = extract_first_insert_identity(sql)
                if col_name and col_val:
                    select_sql = f"SELECT * FROM `{table_name}` WHERE `{col_name}` = :col_val LIMIT 1"
                    with engine.connect() as conn:
                        res = conn.execute(text(select_sql), {"col_val": col_val})
                        records = [dict(row._mapping) for row in res]
                else:
                    # Fallback to previous sorting logic
                    from sqlalchemy import inspect
                    inspector = inspect(engine)
                    cols = [c["name"] for c in inspector.get_columns(table_name)]
                    pk_cols = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
                    sort_col = pk_cols[0] if pk_cols else (cols[0] if cols else None)
                    
                    if sort_col:
                        select_sql = f"SELECT * FROM `{table_name}` ORDER BY `{sort_col}` DESC LIMIT 1"
                    else:
                        select_sql = f"SELECT * FROM `{table_name}` LIMIT 1"
                        
                    with engine.connect() as conn:
                        res = conn.execute(text(select_sql))
                        records = [dict(row._mapping) for row in res]
            except Exception as insert_err:
                print("Failed post-fetching inserted records:", insert_err)
                
        elif intent == "UPDATE":
            try:
                sql_lower = sql.lower()
                where_idx = sql_lower.find("where")
                if where_idx != -1:
                    where_clause = sql[where_idx:]
                    select_sql = f"SELECT * FROM `{table_name}` {where_clause}"
                else:
                    select_sql = f"SELECT * FROM `{table_name}`"
                if select_sql.endswith(";"):
                    select_sql = select_sql[:-1]
                with engine.connect() as conn:
                    res = conn.execute(text(select_sql))
                    records = [dict(row._mapping) for row in res]
            except Exception as update_err:
                print("Failed post-fetching updated records:", update_err)

        ai_message = generate_confirmation_message(intent, table_name, rows_affected, sql)
        
        return {
            "success": True,
            "rows_affected": rows_affected,
            "execution_time_ms": round(elapsed_time_ms, 2),
            "sql": sql,
            "message": ai_message,
            "records": records,
            "error": None
        }
    except Exception as e:
        elapsed_time_ms = (time.time() - start_time) * 1000
        return {
            "success": False,
            "rows_affected": 0,
            "execution_time_ms": round(elapsed_time_ms, 2),
            "sql": sql,
            "message": "Database execution failed. Transaction rolled back successfully.",
            "records": [],
            "error": str(e)
        }


def generate_confirmation_message(intent: str, table_name: str, rows_affected: int, sql: str) -> str:
    """
    Generates a professional confirmation message based on result without LLM calls.
    """
    if rows_affected == 0 and intent in ["UPDATE", "DELETE"]:
        sql_lower = sql.lower()
        where_idx = sql_lower.find("where")
        if where_idx != -1:
            where_clause = sql[where_idx + 5:].strip()
            if where_clause.endswith(";"):
                where_clause = where_clause[:-1].strip()
            return f"No records matching '{where_clause}' exist in the database."
        return "0 records affected. No matching records found."
        
    if intent == "INSERT":
        return f"1 record inserted into {table_name} successfully."
    if intent == "UPDATE":
        return f"{rows_affected} records updated in {table_name} successfully."
    if intent == "DELETE":
        return f"{rows_affected} records deleted from {table_name} successfully."
    if intent == "TRUNCATE":
        return f"Table {table_name} truncated successfully."
    if intent == "DROP":
        return f"Table {table_name} dropped successfully."
    return f"Database operation {intent} executed successfully on {table_name}."
