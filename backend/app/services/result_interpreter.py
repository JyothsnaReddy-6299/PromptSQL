import re


AGGREGATE_FUNCTIONS = [
    "count(",
    "sum(",
    "avg(",
    "min(",
    "max("
]


def is_aggregate_query(sql: str) -> bool:
    """
    Returns True if the SQL uses aggregate functions.
    """

    sql = sql.lower()

    return any(
        func in sql
        for func in AGGREGATE_FUNCTIONS
    )


def has_group_by(sql: str) -> bool:
    """
    Checks if GROUP BY exists.
    """

    return "group by" in sql.lower()


def interpret_result(sql: str, records: list):
    """
    Determines what kind of result the SQL produced.
    """

    if not records:
        return "EMPTY"

    if is_aggregate_query(sql):

        if has_group_by(sql):
            return "GROUP_AGGREGATE"

        return "AGGREGATE"

    return "ROWS"