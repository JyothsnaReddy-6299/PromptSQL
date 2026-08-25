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


def validate_sql(sql_query, user_tables):
    """
    Validates AI-generated SQL before execution against a list of user-owned tables.
    """

    sql = sql_query.strip()

    # ----------------------------
    # Only SELECT queries allowed
    # ----------------------------

    if not sql.lower().startswith("select") and not sql.lower().startswith("with"):
        return False, "The requested query is invalid and cannot be executed."

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
    all_db_tables = inspector.get_table_names()

    # ----------------------------
    # Check table permissions (Security)
    # ----------------------------
    # Verify that the query does NOT access any database tables that are NOT in user_tables
    for tbl in all_db_tables:
        if tbl not in user_tables:
            if re.search(rf"\b{re.escape(tbl)}\b", sql, re.IGNORECASE):
                return False, f"Access to table '{tbl}' is forbidden."

    # ----------------------------
    # Check all backticked columns
    # ----------------------------

    valid_columns = set()
    known_tables = set()
    for tbl in user_tables:
        known_tables.add(tbl.lower())
        friendly = tbl.split("_usr_")[0].lower()
        known_tables.add(friendly)
        for col in inspector.get_columns(tbl):
            valid_columns.add(col["name"].lower())

    used_columns = re.findall(
        r"`([^`]+)`",
        sql
    )

    for column in used_columns:
        col_lower = column.lower()
        
        # Skip table names or aliases that match known tables
        if col_lower in known_tables:
            continue

        if col_lower not in valid_columns:
            return (
                False,
                f"Unknown column '{column}'."
            )

    return (
        True,
        "SQL is valid."
    )   