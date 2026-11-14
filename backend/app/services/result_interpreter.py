import re


AGGREGATE_FUNCTIONS = [
    "count(",
    "sum(",
    "avg(",
    "min(",
    "max(",
    "lag(",
    "lead(",
    "stddev(",
    "variance("
]


def is_aggregate_query(sql: str) -> bool:
    """
    Returns True if the SQL uses aggregate functions, window functions,
    or arithmetic expressions computing derived rates/percentages.
    """
    sql_lower = sql.lower()

    if any(func in sql_lower for func in AGGREGATE_FUNCTIONS):
        return True

    # Check for derived ratios or arithmetic operations between fields
    if "/" in sql_lower or "*" in sql_lower:
        # If calculating ratios or percentage metrics
        ratio_keywords = ["rate", "ratio", "margin", "percentage", "pct", "growth"]
        if any(kw in sql_lower for kw in ratio_keywords):
            return True

    return False


def has_group_by(sql: str) -> bool:
    """
    Checks if query groups by dimensions or window partitions.
    """
    sql_lower = sql.lower()
    return "group by" in sql_lower or "over (" in sql_lower or "over(" in sql_lower


def interpret_result(sql: str, records: list):
    """
    Determines what kind of result the SQL produced.
    """
    if not records:
        return "EMPTY"

    if is_aggregate_query(sql):
        if has_group_by(sql) or len(records) > 1:
            return "GROUP_AGGREGATE"
        return "AGGREGATE"

    return "ROWS"
