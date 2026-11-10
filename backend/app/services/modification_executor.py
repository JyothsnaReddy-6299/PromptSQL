import time
from sqlalchemy import text
from app.database.connection import engine


def extract_first_insert_identity(sql: str) -> tuple:
    import re
    match = re.search(r"insert\s+into\s+\S+\s*\((.*?)\)\s*values\s*\((.*?)\)", sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return None, None

    cols_str, vals_str = match.groups()

    cols = [c.strip().replace("`", "").replace("'", "").replace('"', '') for c in cols_str.split(",")]

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


def generate_undo_sql(intent: str, table_name: str, records_before: list, records_after: list) -> str:
    from sqlalchemy import inspect
    try:
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            return None

        pk_cols = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        if not pk_cols:
            cols = [c["name"] for c in inspector.get_columns(table_name)]
            if cols:
                pk_cols = [cols[0]]

        if not pk_cols:
            return None

        pk_col = pk_cols[0]

        def format_value(val):
            if val is None:
                return "NULL"
            if isinstance(val, (int, float)):
                return str(val)
            escaped = str(val).replace("'", "''")
            return f"'{escaped}'"

        if intent == "INSERT":
            if not records_after:
                return None
            delete_queries = []
            for rec in records_after:
                pk_val = rec.get(pk_col)
                if pk_val is not None:
                    delete_queries.append(f"DELETE FROM `{table_name}` WHERE `{pk_col}` = {format_value(pk_val)}")
            return "; ".join(delete_queries) if delete_queries else None

        elif intent == "DELETE":
            if not records_before:
                return None
            insert_queries = []
            for rec in records_before:
                cols = list(rec.keys())
                vals = [format_value(rec[c]) for c in cols]
                cols_str = ", ".join(f"`{c}`" for c in cols)
                vals_str = ", ".join(vals)
                insert_queries.append(f"INSERT INTO `{table_name}` ({cols_str}) VALUES ({vals_str})")
            return "; ".join(insert_queries) if insert_queries else None

        elif intent == "UPDATE":
            if not records_before:
                return None
            update_queries = []
            for rec in records_before:
                pk_val = rec.get(pk_col)
                if pk_val is None:
                    continue
                set_parts = []
                for col, val in rec.items():
                    if col != pk_col:
                        set_parts.append(f"`{col}` = {format_value(val)}")
                set_str = ", ".join(set_parts)
                update_queries.append(f"UPDATE `{table_name}` SET {set_str} WHERE `{pk_col}` = {format_value(pk_val)}")
            return "; ".join(update_queries) if update_queries else None
    except Exception as undo_err:
        print("Failed to generate undo SQL:", undo_err)
        return None

    return None


def execute_modification(sql: str, table_name: str, intent: str) -> dict:
    """
    Executes a DML or DDL query with strict separation of execution policies:

    1. DML Policy (UPDATE, INSERT, DELETE, MERGE):
       - Executed in a true transactional block.
       - Automatically rolls back on any error.
       - Pre-fetches / post-fetches records for audit and undo generation.

    2. DDL Policy (ALTER, DROP, TRUNCATE, CREATE):
       - Explicitly accounts for MySQL implicit transaction commits.
       - Cannot be rolled back once committed by MySQL.
       - Never reports that DDL was rolled back on failure.
    """
    start_time = time.time()
    records = []
    records_before = []
    is_ddl = intent.upper() in ["ALTER", "DROP", "TRUNCATE", "CREATE"]
    policy = "DDL" if is_ddl else "DML"

    # -------------------------------------------------------------
    # Policy A: DDL Execution (Implicit Commit, No Transactional Rollback)
    # -------------------------------------------------------------
    if is_ddl:
        try:
            with engine.connect() as conn:
                conn.execute(text(sql))
                conn.commit()

            elapsed_time_ms = (time.time() - start_time) * 1000
            ai_message = generate_confirmation_message(intent, table_name, 0, sql)

            return {
                "success": True,
                "policy": "DDL",
                "rolled_back": False,
                "rows_affected": 0,
                "execution_time_ms": round(elapsed_time_ms, 2),
                "sql": sql,
                "message": ai_message,
                "records": [],
                "undo_sql": None,
                "error": None
            }
        except Exception as ddl_err:
            elapsed_time_ms = (time.time() - start_time) * 1000
            err_msg = str(ddl_err)
            return {
                "success": False,
                "policy": "DDL",
                "rolled_back": False,
                "rows_affected": 0,
                "execution_time_ms": round(elapsed_time_ms, 2),
                "sql": sql,
                "message": f"DDL operation failed: {err_msg}. (Note: MySQL DDL operations trigger implicit commits and do not support rollback.)",
                "records": [],
                "undo_sql": None,
                "error": err_msg
            }

    # -------------------------------------------------------------
    # Policy B: DML Execution (Full Transactional Atomicity & Rollback)
    # -------------------------------------------------------------
    try:
        # Pre-fetch records if it is a DELETE or UPDATE operation
        if intent in ["DELETE", "UPDATE"]:
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
                    records_before = [dict(row._mapping) for row in res]
            except Exception as select_err:
                print("Failed pre-fetching records before modification:", select_err)

        # Execute query inside a strict transaction block
        with engine.begin() as connection:
            result = connection.execute(text(sql))
            rows_affected = result.rowcount

        elapsed_time_ms = (time.time() - start_time) * 1000

        if rows_affected is None or rows_affected < 0:
            rows_affected = 0

        # Post-fetch records for INSERT or UPDATE
        if intent == "INSERT":
            try:
                col_name, col_val = extract_first_insert_identity(sql)
                if col_name and col_val:
                    select_sql = f"SELECT * FROM `{table_name}` WHERE `{col_name}` = :col_val LIMIT 1"
                    with engine.connect() as conn:
                        res = conn.execute(text(select_sql), {"col_val": col_val})
                        records = [dict(row._mapping) for row in res]
                else:
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

        # Generate Undo SQL
        undo_sql = None
        if intent in ["INSERT", "UPDATE", "DELETE"] and rows_affected > 0:
            records_after = records if intent == "INSERT" else []
            undo_sql = generate_undo_sql(intent, table_name, records_before, records_after)

        ai_message = generate_confirmation_message(intent, table_name, rows_affected, sql)

        return {
            "success": True,
            "policy": "DML",
            "rolled_back": False,
            "rows_affected": rows_affected,
            "execution_time_ms": round(elapsed_time_ms, 2),
            "sql": sql,
            "message": ai_message,
            "records": records,
            "undo_sql": undo_sql,
            "error": None
        }
    except Exception as dml_err:
        elapsed_time_ms = (time.time() - start_time) * 1000
        err_msg = str(dml_err)
        return {
            "success": False,
            "policy": "DML",
            "rolled_back": True,
            "rows_affected": 0,
            "execution_time_ms": round(elapsed_time_ms, 2),
            "sql": sql,
            "message": "DML database execution failed. Transaction was automatically rolled back.",
            "records": [],
            "undo_sql": None,
            "error": err_msg
        }


def generate_confirmation_message(intent: str, table_name: str, rows_affected: int, sql: str) -> str:
    friendly_name = table_name.split("_usr_")[0] if "_usr_" in table_name else table_name

    if rows_affected == 0 and intent in ["UPDATE", "DELETE"]:
        sql_lower = sql.lower()
        where_idx = sql_lower.find("where")
        if where_idx != -1:
            where_clause = sql[where_idx + 5:].strip()
            if where_clause.endswith(";"):
                where_clause = where_clause[:-1].strip()
            return f"No records matching '{where_clause}' exist in dataset '{friendly_name}'."
        return f"0 records affected in dataset '{friendly_name}'. No matching records found."

    if intent == "INSERT":
        return f"1 record inserted into dataset '{friendly_name}' successfully."
    if intent == "UPDATE":
        return f"{rows_affected} record(s) updated in dataset '{friendly_name}' successfully."
    if intent == "DELETE":
        return f"{rows_affected} record(s) deleted from dataset '{friendly_name}' successfully."
    if intent == "TRUNCATE":
        return f"Dataset '{friendly_name}' truncated successfully. All records permanently erased."
    if intent == "DROP":
        return f"Dataset '{friendly_name}' dropped successfully. Table and all records permanently destroyed."
    if intent == "ALTER":
        return f"Dataset '{friendly_name}' schema altered successfully."
    return f"Database operation {intent} executed successfully on dataset '{friendly_name}'."
