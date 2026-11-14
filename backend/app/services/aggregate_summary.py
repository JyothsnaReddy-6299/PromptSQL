import re
from decimal import Decimal
from typing import Optional, Tuple, Any, List, Dict


def to_number(val: Any) -> Optional[float]:
    """Safely converts an arbitrary value into a float, or None if non-numeric."""
    if val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        return float(val)
    try:
        cleaned = str(val).replace(",", "").strip()
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def clean_label(col: str) -> str:
    """Produces a clean, human-readable column/metric label."""
    if not col:
        return ""
    cleaned = col.replace("_", " ").strip()
    return cleaned


def is_rate_or_percentage(col_name: str, sql: str = "") -> Tuple[bool, bool]:
    """
    Returns (is_rate, is_already_scaled_percentage).
    - is_rate: True if the metric represents a rate, ratio, margin, growth, or percentage.
    - is_already_scaled_percentage: True if the value is already on a 0-100 scale.
    """
    name_lower = col_name.lower().replace("_", " ")

    # Explicit percentage naming
    is_pct_scale = (
        any(k in name_lower for k in ["percentage", "percent", "pct", "growth percentage"])
    )

    # General rate/ratio indicators on column name
    is_rate = (
        is_pct_scale
        or any(k in name_lower for k in ["rate", "ratio", "margin", "proportion", "share", "growth"])
    )

    # If column name is generic but SQL expression is a division of counts/sums
    if not is_rate and "/" in sql.lower() and ("count(" in sql.lower() or "sum(" in sql.lower()):
        # Check if the alias is not an ordinary count/sum
        if not any(k in name_lower for k in ["count", "sum", "total", "amount", "cost", "salary"]):
            is_rate = True

    return is_rate, is_pct_scale


def format_value(value: Any, col_name: str = "", sql: str = "") -> str:
    """
    Nicely formats numeric values, respecting currency/counts vs. rates/percentages.
    Only formats as percentage when its meaning is established.
    """
    if value is None:
        return "N/A"

    num = to_number(value)
    if num is None:
        return str(value)

    is_rate, is_pct_scale = is_rate_or_percentage(col_name, sql)
    if is_rate:
        if is_pct_scale:
            return f"{num:,.2f}%"
        elif abs(num) <= 1.0:
            return f"{(num * 100):,.2f}%"
        else:
            return f"{num:,.2f}%"

    # Ordinary count or integer (when type is int and not float/Decimal from database)
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"

    # Ordinary decimal aggregate (currency, salary, averages, totals)
    return f"{num:,.2f}"


def generate_aggregate_summary(question: str, sql: str, records: list, is_truncated: bool = False) -> str:
    """
    Generates deterministic, informative summaries for aggregate and grouped SQL queries.
    Accurately handles standard aggregates, derived rates/percentages, and grouped distributions.
    """
    if not records:
        return "No matching records found."

    sql_lower = sql.lower()
    row = records[0]
    keys = list(row.keys())
    values = list(row.values())
    has_group = "group by" in sql_lower or "over (" in sql_lower or "over(" in sql_lower

    # -------------------------------------------------------------
    # 1. Single-Row Non-Grouped Query
    # -------------------------------------------------------------
    if not has_group and len(records) == 1:
        col = keys[-1]
        val = values[-1]
        label = clean_label(col)
        is_rate, _ = is_rate_or_percentage(col, sql)

        # Derived Rate / Ratio / Margin / Percentage
        if is_rate:
            formatted_val = format_value(val, col, sql)
            return f"The {label} is {formatted_val}."

        # Ordinary COUNT (not a ratio or rate)
        if "count(" in sql_lower and "/" not in sql_lower:
            count_val = values[0]
            col0 = keys[0]
            return f"There are {format_value(count_val, col0, sql)} matching records for your query."

        # SUM
        if "sum(" in sql_lower:
            formatted_val = format_value(val, col, sql)
            if label.lower().startswith("total") or label.lower().startswith("sum"):
                return f"The {label} is {formatted_val}."
            return f"The total {label} is {formatted_val}."

        # AVG
        if "avg(" in sql_lower:
            formatted_val = format_value(val, col, sql)
            if label.lower().startswith("average") or label.lower().startswith("avg"):
                return f"The {label} is {formatted_val}."
            return f"The average {label} is {formatted_val}."

        # MAX
        if "max(" in sql_lower:
            formatted_val = format_value(val, col, sql)
            if label.lower().startswith("maximum") or label.lower().startswith("max"):
                return f"The {label} is {formatted_val}."
            return f"The maximum {label} is {formatted_val}."

        # MIN
        if "min(" in sql_lower:
            formatted_val = format_value(val, col, sql)
            if label.lower().startswith("minimum") or label.lower().startswith("min"):
                return f"The {label} is {formatted_val}."
            return f"The minimum {label} is {formatted_val}."

        # Generic single-cell aggregate
        formatted_val = format_value(val, col, sql)
        return f"The {label} is {formatted_val}."

    # -------------------------------------------------------------
    # 2. Grouped Query with Exactly 1 Result Row
    # -------------------------------------------------------------
    if len(records) == 1:
        dim_key = keys[0]
        dim_val = values[0]
        metric_key = keys[-1] if len(keys) > 1 else keys[0]
        metric_val = values[-1] if len(values) > 1 else values[0]
        metric_label = clean_label(metric_key)
        formatted_val = format_value(metric_val, metric_key, sql)

        # Check whether query explicitly sorted with LIMIT 1
        is_explicit_highest = "order by" in sql_lower and "desc" in sql_lower and "limit 1" in sql_lower
        is_explicit_lowest = "order by" in sql_lower and "asc" in sql_lower and "limit 1" in sql_lower

        if is_explicit_highest:
            return f"{dim_val} has the highest {metric_label} of {formatted_val}."
        elif is_explicit_lowest:
            return f"{dim_val} has the lowest {metric_label} of {formatted_val}."
        else:
            return f"For {dim_val}, the {metric_label} is {formatted_val}."

    # -------------------------------------------------------------
    # 3. Multi-Row Grouped / Period Results
    # -------------------------------------------------------------
    dim_key = keys[0]
    cap_note = " (sample capped at system limit)" if is_truncated else ""

    # Check for period-over-period growth results
    growth_col = next((k for k in keys if "growth" in k.lower() or "pct" in k.lower() or "percent" in k.lower()), None)
    if growth_col and len(keys) >= 2:
        val_col = next((k for k in keys if k != dim_key and k != growth_col), None)
        period_strs = []
        for r in records:
            d = r.get(dim_key)
            v = format_value(r.get(val_col), val_col, sql) if val_col and r.get(val_col) is not None else ""
            g = r.get(growth_col)
            if g is not None:
                g_str = f" (growth: {format_value(g, growth_col, sql)})"
            else:
                g_str = ""
            period_strs.append(f"{d}: {v}{g_str}" if v else f"{d}{g_str}")

        return f"The query returned {len(records)} grouped results{cap_note}: " + ", ".join(period_strs) + "."

    # Standard multi-row grouped results
    metric_candidates = [k for k in keys if k != dim_key]

    if not metric_candidates:
        metric_key = dim_key
    else:
        # Prefer the last column containing numeric data
        metric_key = metric_candidates[-1]
        for k in reversed(metric_candidates):
            if to_number(records[0].get(k)) is not None:
                metric_key = k
                break

    metric_label = clean_label(metric_key)

    parsed_items = []
    for r in records:
        d_val = r.get(dim_key)
        m_val = r.get(metric_key)
        num = to_number(m_val)
        formatted = format_value(m_val, metric_key, sql)
        parsed_items.append((d_val, m_val, num, formatted))

    valid_numerics = [item for item in parsed_items if item[2] is not None]

    if valid_numerics:
        distinct_nums = {item[2] for item in valid_numerics}
        sorted_by_num = sorted(valid_numerics, key=lambda x: x[2], reverse=True)
        high = sorted_by_num[0]
        low = sorted_by_num[-1]

        if len(distinct_nums) == 1:
            return f"The query returned {len(records)} grouped results{cap_note}, each with {metric_label} of {high[3]}."

        if len(records) == 2:
            return (
                f"The query returned 2 grouped results{cap_note}: "
                f"{high[0]} is highest with {metric_label} of {high[3]}, and "
                f"{low[0]} is lowest with {low[3]}."
            )

        if len(records) == 3:
            mid = sorted_by_num[1]
            return (
                f"The query returned 3 grouped results{cap_note}: "
                f"{high[0]} is highest with {metric_label} of {high[3]}, and "
                f"{low[0]} is lowest with {low[3]} "
                f"({mid[0]}: {mid[3]})."
            )

        if len(records) <= 5:
            details = ", ".join(f"{it[0]}: {it[3]}" for it in parsed_items)
            return (
                f"The query returned {len(records)} grouped results{cap_note} ({details}). "
                f"{high[0]} is highest with {high[3]}, and {low[0]} is lowest with {low[3]}."
            )

        # > 5 records
        return (
            f"The query returned {len(records)} grouped results{cap_note}. "
            f"{high[0]} has the highest {metric_label} at {high[3]}, while "
            f"{low[0]} has the lowest at {low[3]}."
        )

    return f"The query returned {len(records)} grouped results{cap_note}."
