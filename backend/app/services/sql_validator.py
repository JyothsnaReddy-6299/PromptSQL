import re
from sqlalchemy import inspect
from app.database.connection import engine


BLOCKED_KEYWORDS = {
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "REPLACE"
}


def validate_sql(sql_query, table_name):
    """
    Validates AI-generated SQL before execution.
    """

    sql = sql_query.strip()

    # ----------------------------
    # Only SELECT queries allowed
    # ----------------------------

    if not sql.lower().startswith("select"):
        return False, "Only SELECT queries are allowed."

    # ----------------------------
    # Dangerous keywords
    # ----------------------------

    upper_sql = sql.upper()

    for keyword in BLOCKED_KEYWORDS:

        if re.search(rf"\b{keyword}\b", upper_sql):

            return (
                False,
                f"{keyword} statements are not allowed."
            )

    inspector = inspect(engine)

    tables = inspector.get_table_names()

    # ----------------------------
    # Check table exists
    # ----------------------------

    if table_name not in tables:

        return (
            False,
            f"Table '{table_name}' does not exist."
        )

    # ----------------------------
    # Verify FROM table
    # ----------------------------

    match = re.search(

        r"FROM\s+`?([^`\s]+)`?",

        sql,

        re.IGNORECASE

    )

    if not match:

        return (
            False,
            "No FROM clause found."
        )

    used_table = match.group(1)

    if used_table != table_name:

        return (
            False,
            "Generated SQL uses the wrong table."
        )

    # ----------------------------
    # Check all backticked columns
    # ----------------------------

    valid_columns = {

        column["name"]

        for column in inspector.get_columns(table_name)

    }

    used_columns = re.findall(

        r"`([^`]+)`",

        sql

    )

    for column in used_columns:

        # Skip table name references
        if column.lower() == table_name.lower():
            continue

        if column not in valid_columns:

            return (
                False,
                f"Unknown column '{column}'."
            )

    return (
        True,
        "SQL is valid."
    )   