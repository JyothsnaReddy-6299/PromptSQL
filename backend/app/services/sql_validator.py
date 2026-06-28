import re
from sqlalchemy import inspect
from app.database.connection import engine


def validate_sql(sql_query, table_name):

    sql = sql_query.strip().lower()

    # Allow only SELECT queries
    if not sql.startswith("select"):
        return False, "Only SELECT queries are allowed."

    # Block dangerous SQL keywords
    blocked_keywords = [
        "drop",
        "delete",
        "truncate",
        "update",
        "insert",
        "alter",
        "create",
        "replace"
    ]

    for keyword in blocked_keywords:
        if keyword in sql:
            return False, f"'{keyword.upper()}' queries are not allowed."

    # Check whether the table exists
    inspector = inspect(engine)

    tables = inspector.get_table_names()

    if table_name not in tables:
        return False, f"Table '{table_name}' does not exist."

    # Get all valid columns
    columns = inspector.get_columns(table_name)

    valid_columns = {
        column["name"].lower()
        for column in columns
    }

    # SQL keywords/functions to ignore
    sql_keywords = {
        "select", "from", "where", "and", "or",
        "group", "by", "order", "limit",
        "having", "count", "sum", "avg",
        "min", "max", "distinct", "as",
        "asc", "desc", "between", "like",
        "in", "not", "is", "null",
        "join", "left", "right",
        "inner", "outer", "on"
    }

    # Remove quoted string values
    sql_without_strings = re.sub(r"'[^']*'", "", sql)

    # Extract identifiers
    identifiers = re.findall(
        r"[A-Za-z_][A-Za-z0-9_]*",
        sql_without_strings
    )

    for word in identifiers:

        if word in sql_keywords:
            continue

        if word == table_name.lower():
            continue

        if word in valid_columns:
            continue

        return False, f"Unknown column: {word}"

    return True, "SQL is valid."