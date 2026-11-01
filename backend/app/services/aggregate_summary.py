import re
from typing import Optional, Dict, Any, List
from decimal import Decimal


def format_value(value, currency_unit: str = "") -> str:
    """
    Nicely format numeric values with precision protection,
    avoiding floating-point artifacts.
    """
    if value is None:
        return "not available"

    prefix = "$" if currency_unit.upper() in ["USD", "$"] else ""
    suffix = f" {currency_unit}" if currency_unit and currency_unit.upper() not in ["USD", "$"] else ""

    if isinstance(value, (float, Decimal)):
        rounded = round(float(value), 2)
        # Format with 2 decimal places if it has fractional part
        if rounded.is_integer():
            val_str = f"{int(rounded):,}"
        else:
            val_str = f"{rounded:,.2f}"
        return f"{prefix}{val_str}{suffix}"

    if isinstance(value, int):
        return f"{prefix}{value:,}{suffix}"

    return f"{prefix}{value}{suffix}"


def generate_aggregate_summary(
    question: str,
    sql: str,
    records: List[Dict[str, Any]],
    plan: Optional[Dict[str, Any]] = None
) -> str:
    """
    Generates deterministic, accurate summaries for aggregate SQL queries.
    Uses structured plan fields when available, avoiding brittle SQL substring parsing.
    """
    if not records:
        return "No matching records found."

    row = records[0]

    # If structured plan is provided, use its verified metadata
    if plan:
        metric_name = plan.get("metric_name", "Metric")
        unit = plan.get("currency_unit", "")
        dimensions = plan.get("grouping_dimensions", [])
        direction = plan.get("ordering", {}).get("direction", "DESC")
        limit = plan.get("limit")

        # Metric column in the result records
        # Either exact name or sanitised identifier
        metric_key = next((k for k in row.keys() if k.lower() in [metric_name.lower(), metric_name.lower().replace(" ", "_")]), list(row.keys())[-1])
        metric_val = row.get(metric_key)

        if dimensions:
            dim_key = dimensions[0]
            dim_val = row.get(dim_key, list(row.values())[0])

            if len(records) == 1:
                rank_word = "lowest" if direction == "ASC" else "highest"
                return f"{dim_val} has the {rank_word} {metric_name} of {format_value(metric_val, unit)}."
            else:
                return f"Retrieved {metric_name} across {len(records)} {dim_key} groups."
        else:
            # Pure aggregate (no grouping dimensions)
            agg = plan.get("metric_aggregation", "SUM")
            agg_word = {"AVG": "average", "MIN": "minimum", "MAX": "maximum", "COUNT": "count of", "COUNT_DISTINCT": "distinct count of"}.get(agg, "total")
            return f"The {agg_word} {metric_name} is {format_value(metric_val, unit)}."

    # Fallback to deterministic SQL inspection when no structured plan is present
    sql_lower = sql.lower()

    if "count(" in sql_lower and "group by" not in sql_lower:
        value = list(row.values())[0]
        return f"There are {format_value(value)} matching records for your query."

    if "group by" in sql_lower:
        if len(records) == 1:
            values = list(row.values())
            if len(values) >= 2:
                group = values[0]
                aggregate = values[1]
                rank_word = "lowest" if " asc" in sql_lower else "highest"
                agg_type = "average" if "avg(" in sql_lower else ("count" if "count(" in sql_lower else "total value")
                return f"{group} has the {rank_word} {agg_type} of {format_value(aggregate)}."

        return f"The query returned {len(records)} grouped results."

    # Single aggregate row
    value = list(row.values())[-1]
    column = list(row.keys())[-1]
    agg_word = "average" if "avg(" in sql_lower else ("maximum" if "max(" in sql_lower else ("minimum" if "min(" in sql_lower else "total"))
    return f"The {agg_word} {column} is {format_value(value)}."