import re


def format_value(value):
    """
    Nicely format numeric values.
    """

    if value is None:
        return "0"

    if isinstance(value, float):
        return f"{value:,.2f}"

    if isinstance(value, int):
        return f"{value:,}"

    return str(value)


def generate_aggregate_summary(question, sql, records):
    """
    Generates deterministic summaries for aggregate SQL queries.
    No LLM is used here.
    """

    if not records:
        return "No matching records found."

    row = records[0]

    sql_lower = sql.lower()

    # ---------------------------------
    # COUNT
    # ---------------------------------

    if "count(" in sql_lower:

        value = list(row.values())[0]

        return f"There are {format_value(value)} matching records for your query."

    # ---------------------------------
    # SUM
    # ---------------------------------

    if "sum(" in sql_lower and "group by" not in sql_lower:

        value = list(row.values())[-1]

        column = list(row.keys())[-1]

        return f"The total {column} is {format_value(value)}."

    # ---------------------------------
    # AVG
    # ---------------------------------

    if "avg(" in sql_lower and "group by" not in sql_lower:

        value = list(row.values())[-1]

        column = list(row.keys())[-1]

        return f"The average {column} is {format_value(value)}."

    # ---------------------------------
    # MAX
    # ---------------------------------

    if "max(" in sql_lower and "group by" not in sql_lower:

        value = list(row.values())[-1]

        column = list(row.keys())[-1]

        return f"The maximum {column} is {format_value(value)}."

    # ---------------------------------
    # MIN
    # ---------------------------------

    if "min(" in sql_lower and "group by" not in sql_lower:

        value = list(row.values())[-1]

        column = list(row.keys())[-1]

        return f"The minimum {column} is {format_value(value)}."

    # ---------------------------------
    # GROUP BY Aggregates
    # ---------------------------------

    if "group by" in sql_lower:

        if len(records) == 1:

            values = list(row.values())

            if len(values) >= 2:

                group = values[0]
                aggregate = values[1]

                if "sum(" in sql_lower:
                    return (
                        f"{group} has the highest total value "
                        f"of {format_value(aggregate)}."
                    )

                if "avg(" in sql_lower:
                    return (
                        f"{group} has the highest average value "
                        f"of {format_value(aggregate)}."
                    )

                if "count(" in sql_lower:
                    return (
                        f"{group} has the highest count "
                        f"of {format_value(aggregate)}."
                    )

        return (
            f"The query returned {len(records)} grouped results."
        )

    # ---------------------------------
    # FALLBACK
    # ---------------------------------

    return f"The query returned {len(records)} record(s)."