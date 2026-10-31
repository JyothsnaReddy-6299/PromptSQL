import uuid
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from app.database.connection import SessionLocal, engine
from app.models.clarification import ClarificationSession
from app.models.metric import BusinessMetric
from app.services.metric_parser import validate_and_compile_expression
from app.services.metric_service import (
    get_authorized_dataset_columns,
    list_metrics,
    create_or_update_metric
)
from app.utils.tz_helper import get_ist_time


class PlanCompilationError(Exception):
    pass


class QueryShapeUnsupportedError(Exception):
    pass


def detect_sales_ambiguity(
    question: str,
    columns: List[str],
    user_metrics: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Checks if a question asking for 'sales' is ambiguous between
    Revenue (monetary) and Quantity (volume), when the dataset contains both.
    """
    q_lower = question.lower()

    # If question explicitly clarifies revenue or quantity, it is NOT ambiguous:
    explicit_revenue_terms = [
        "revenue", "dollar", "amount", "income", "turnover", "in usd", "in $", "monetary", "sales amount"
    ]
    explicit_quantity_terms = [
        "quantity", "units", "volume", "pieces", "count of items", "items sold", "number of items", "qty"
    ]

    has_explicit_rev = any(w in q_lower for w in explicit_revenue_terms)
    has_explicit_qty = any(w in q_lower for w in explicit_quantity_terms)

    if has_explicit_rev or has_explicit_qty:
        return None

    # Check if the word "sale" or "sales" is in question
    sales_patterns = [r"\bsales?\b", r"\bselling\b", r"\bbest[-\s]?seller\b"]
    matches_sales = any(re.search(pat, q_lower) for pat in sales_patterns)

    if not matches_sales:
        return None

    # Check if dataset has plausible revenue column and plausible quantity column
    cols_lower = {c.lower(): c for c in columns}

    rev_cols = [c for c in cols_lower if any(k in c for k in ["total_sales", "total sales", "revenue", "sales_amount", "unit_price"])]
    qty_cols = [c for c in cols_lower if any(k in c for k in ["quantity_ordered", "quantity", "qty", "units_sold", "units"])]

    if rev_cols and qty_cols:
        # Both monetary sales and quantity sales columns exist!
        rev_canonical = cols_lower[rev_cols[0]]
        qty_canonical = cols_lower[qty_cols[0]]

        return {
            "ambiguous_term": "sales",
            "prompt": "How would you like to measure 'sales' for this query?",
            "options": [
                {
                    "id": "revenue",
                    "label": "Total Revenue (Monetary Sales)",
                    "description": f"Calculate sum of monetary revenue using `{rev_canonical}`",
                    "metric_name": "Revenue",
                    "expression": rev_canonical,
                    "aggregation": "SUM",
                    "currency_unit": "USD",
                },
                {
                    "id": "quantity",
                    "label": "Units Sold (Volume)",
                    "description": f"Calculate total unit volume using `{qty_canonical}`",
                    "metric_name": "Quantity",
                    "expression": qty_canonical,
                    "aggregation": "SUM",
                    "currency_unit": "units",
                }
            ]
        }

    return None


def extract_dimensions_and_grouping(
    question: str,
    columns: List[str]
) -> List[str]:
    """
    Extracts grouping dimensions from the question by matching authorized dataset column names,
    e.g. 'by category', 'per region', 'for each segment', 'by country'.
    """
    q_lower = question.lower()
    dimensions = []

    # First look for "by <words>", "per <words>", "for each <words>", "across <words>"
    group_tokens = re.findall(r"\b(?:by|per|across|for each|each|group by|grouped by)\s+([a-zA-Z0-9_\s]+)", q_lower)

    for col in columns:
        col_lower = col.lower()
        if col_lower in ["id", "_row_id", "quantity_ordered", "unit_price", "total_sales", "total sales", "salary"]:
            continue

        col_clean_words = col_lower.replace("_", " ")
        col_tokens = [t for t in col_lower.split("_") if len(t) > 2]

        # 1. Direct full match: "product category" in question
        if col_clean_words in q_lower:
            if col not in dimensions:
                dimensions.append(col)
            continue

        # 2. Match token in group phrase: e.g. "by category" matches col_tokens ["product", "category"]
        matched = False
        for gt in group_tokens:
            gt_words = [w.strip() for w in gt.split() if len(w.strip()) > 2]
            for w in gt_words:
                if w in col_tokens or (len(w) >= 4 and w in col_lower):
                    if col not in dimensions:
                        dimensions.append(col)
                    matched = True
                    break
            if matched:
                break

    return dimensions


def extract_limit_and_ordering(question: str) -> Tuple[Optional[int], str]:
    """
    Extracts limit (e.g. 'top 5', 'highest 10', 'highest', 'lowest', 'bottom 3')
    and sort direction ('DESC' or 'ASC').
    """
    q_lower = question.lower()

    # Direction
    direction = "DESC"
    if any(w in q_lower for w in ["lowest", "bottom", "least", "smallest", "worst", "minimum", "min"]):
        direction = "ASC"

    # Numeric limit
    limit_match = re.search(r"\b(?:top|bottom|highest|lowest|first|best|worst)\s+(\d+)\b", q_lower)
    if limit_match:
        limit = int(limit_match.group(1))
    elif any(w in q_lower for w in ["highest", "lowest", "top", "bottom", "best", "worst", "most", "maximum", "max"]):
        limit = 1
    else:
        limit = None

    return limit, direction


def resolve_or_create_plan(
    question: str,
    table_name: str,
    user_id: str,
    override_metric: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Constructs, validates, and resolves a TypedQueryPlan for the user's question.
    If ambiguity is detected, returns a pending clarification response instead.
    """
    columns = get_authorized_dataset_columns(table_name, user_id)
    friendly_name = table_name.split("_usr_")[0]
    user_metrics = list_metrics(user_id, friendly_name)

    # 1. If override metric is supplied (e.g. from a resolved clarification), use it directly
    if override_metric:
        chosen_metric = override_metric
    else:
        # Check for ambiguity that materially changes the answer (Acceptance Check 1)
        ambiguity = detect_sales_ambiguity(question, columns, user_metrics)
        if ambiguity:
            # Store pending clarification state on server with ownership & 30-min expiry (Requirement 5 & 6)
            db = SessionLocal()
            try:
                clar_id = f"clar_{uuid.uuid4().hex[:16]}"
                session = ClarificationSession(
                    id=clar_id,
                    user_id=user_id,
                    original_question=question,
                    table_name=table_name,
                    clarification_prompt=ambiguity["prompt"],
                    options_json=json.dumps(ambiguity["options"]),
                    proposed_plan_json=json.dumps({
                        "table_name": table_name,
                        "question": question
                    }),
                    expires_at=get_ist_time() + timedelta(minutes=30)
                )
                db.add(session)
                db.commit()

                return {
                    "needs_clarification": True,
                    "clarification_id": clar_id,
                    "prompt": ambiguity["prompt"],
                    "options": ambiguity["options"],
                    "original_question": question
                }
            finally:
                db.close()

        # Resolve against registered user metrics first
        q_lower = question.lower()
        matched_metrics = []
        for m in user_metrics:
            if m["name"].lower() in q_lower:
                matched_metrics.append(m)
            else:
                for alias in m.get("approved_aliases", []):
                    if alias.lower() in q_lower:
                        matched_metrics.append(m)
                        break

        if matched_metrics:
            chosen_metric = matched_metrics[0]
        else:
            # Infer metric from question and columns
            cols_lower = {c.lower(): c for c in columns}
            if any(w in q_lower for w in ["revenue", "turnover", "income", "sales", "total sales"]):
                rev_col = next((cols_lower[c] for c in cols_lower if "total_sales" in c or "total sales" in c or "revenue" in c), None)
                if not rev_col and "unit_price" in cols_lower and "quantity_ordered" in cols_lower:
                    chosen_metric = {
                        "name": "Revenue",
                        "expression": f"{cols_lower['unit_price']} * {cols_lower['quantity_ordered']}",
                        "aggregation": "SUM",
                        "currency_unit": "USD",
                        "description": "Calculated total revenue (Unit Price * Quantity Ordered)"
                    }
                elif rev_col:
                    chosen_metric = {
                        "name": "Revenue",
                        "expression": rev_col,
                        "aggregation": "SUM",
                        "currency_unit": "USD",
                        "description": f"Total revenue sum using `{rev_col}`"
                    }
                else:
                    chosen_metric = None
            elif any(w in q_lower for w in ["quantity", "volume", "units", "units sold", "items sold", "qty"]):
                qty_col = next((cols_lower[c] for c in cols_lower if "quantity" in c or "qty" in c or "units" in c), None)
                if qty_col:
                    chosen_metric = {
                        "name": "Quantity",
                        "expression": qty_col,
                        "aggregation": "SUM",
                        "currency_unit": "units",
                        "description": f"Total volume sum using `{qty_col}`"
                    }
                else:
                    chosen_metric = None
            elif any(w in q_lower for w in ["count", "how many", "number of orders", "number of records", "total orders"]):
                chosen_metric = {
                    "name": "Record Count",
                    "expression": columns[0],
                    "aggregation": "COUNT",
                    "currency_unit": "records",
                    "description": "Total count of records"
                }
            elif any(w in q_lower for w in ["average", "avg"]):
                num_col = next((cols_lower[c] for c in cols_lower if c in ["unit_price", "total_sales", "salary", "price"]), None)
                if num_col:
                    chosen_metric = {
                        "name": f"Average {num_col}",
                        "expression": num_col,
                        "aggregation": "AVG",
                        "currency_unit": "",
                        "description": f"Average of `{num_col}`"
                    }
                else:
                    chosen_metric = None
            else:
                num_col = next((cols_lower[c] for c in cols_lower if any(k in c for k in ["sales", "price", "amount", "salary", "total"])), None)
                if num_col:
                    chosen_metric = {
                        "name": num_col,
                        "expression": num_col,
                        "aggregation": "SUM",
                        "currency_unit": "",
                        "description": f"Sum of `{num_col}`"
                    }
                else:
                    chosen_metric = {
                        "name": "Count",
                        "expression": columns[0],
                        "aggregation": "COUNT",
                        "currency_unit": "count",
                        "description": "Record count"
                    }

    if not chosen_metric:
        raise PlanCompilationError("Could not resolve a suitable metric for this question against the dataset schema.")

    # 2. Extract dimensions
    dimensions = extract_dimensions_and_grouping(question, columns)

    # 3. Extract limit and ordering
    limit, direction = extract_limit_and_ordering(question)

    # 4. Extract simple filters present in the question
    filters = []
    q_lower = question.lower()
    for col in columns:
        col_lower = col.lower()
        if col_lower in ["id", "_row_id"]:
            continue
        val_match = re.search(rf"\b{re.escape(col_lower.replace('_', ' '))}\s*(?:is|=|equal to)\s*['\"]?([a-zA-Z0-9_\-\s]+)['\"]?", q_lower)
        if val_match:
            filters.append({
                "column": col,
                "operator": "=",
                "value": val_match.group(1).strip()
            })

    # 5. Build Typed Query Plan
    plan = {
        "metric_name": chosen_metric.get("name", "Metric"),
        "metric_id": chosen_metric.get("id"),
        "metric_expression": chosen_metric.get("expression", chosen_metric.get("name")),
        "metric_aggregation": chosen_metric.get("supported_aggregation", chosen_metric.get("aggregation", "SUM")),
        "currency_unit": chosen_metric.get("currency_unit", ""),
        "description": chosen_metric.get("description", ""),
        "grouping_dimensions": dimensions,
        "filters": filters,
        "ordering": {
            "target": "metric",
            "direction": direction
        },
        "limit": limit,
        "tie_handling": "standard",
        "explanation": build_plan_explanation(chosen_metric.get("name", "Metric"), dimensions, limit, direction, filters)
    }

    return {
        "needs_clarification": False,
        "plan": plan
    }


def build_plan_explanation(
    metric_name: str,
    dimensions: List[str],
    limit: Optional[int],
    direction: str,
    filters: List[Dict[str, Any]]
) -> str:
    """
    Builds a concise, human-readable interpretation of the query plan.
    """
    parts = []
    if limit:
        rank_word = "Highest" if direction == "DESC" else "Lowest"
        parts.append(f"{rank_word} {limit}" if limit > 1 else f"{rank_word}")
    parts.append(metric_name)

    if dimensions:
        parts.append(f"by {', '.join(dimensions)}")

    if filters:
        filter_str = " and ".join(f"{f['column']} = '{f['value']}'" for f in filters)
        parts.append(f"(filtered by {filter_str})")

    return " ".join(parts)


def compile_plan_to_sql(plan: Dict[str, Any], table_name: str, allowed_columns: List[str]) -> Tuple[str, Dict[str, Any]]:
    """
    Deterministically compiles a validated TypedQueryPlan into safe MySQL SQL.
    Returns:
        (sql_query, sql_params)
    """
    metric_expr = plan["metric_expression"]
    agg = plan.get("metric_aggregation", "SUM")
    metric_sql, _ = validate_and_compile_expression(metric_expr, allowed_columns, agg)

    metric_alias = re.sub(r'[^a-zA-Z0-9_]', '_', plan["metric_name"]).strip('_') or "metric_val"

    dims = plan.get("grouping_dimensions", [])
    for d in dims:
        if d not in allowed_columns:
            raise PlanCompilationError(f"Dimension '{d}' is not an authorized column in dataset.")

    select_parts = [f"`{d}`" for d in dims]
    select_parts.append(f"{metric_sql} AS `{metric_alias}`")

    where_parts = []
    params = {}
    for idx, f in enumerate(plan.get("filters", [])):
        col = f["column"]
        if col not in allowed_columns:
            raise PlanCompilationError(f"Filter column '{col}' is not authorized.")
        op = f.get("operator", "=")
        param_name = f"param_{idx}"
        where_parts.append(f"`{col}` {op} :{param_name}")
        params[param_name] = f["value"]

    sql = f"SELECT {', '.join(select_parts)}\nFROM `{table_name}`"
    if where_parts:
        sql += f"\nWHERE {' AND '.join(where_parts)}"

    if dims:
        group_parts = [f"`{d}`" for d in dims]
        sql += f"\nGROUP BY {', '.join(group_parts)}"

    ordering = plan.get("ordering")
    if ordering:
        target = ordering.get("target", "metric")
        dir_sql = "DESC" if ordering.get("direction", "DESC").upper() == "DESC" else "ASC"
        order_col = f"`{metric_alias}`" if target == "metric" else f"`{target}`"
        sql += f"\nORDER BY {order_col} {dir_sql}"

    limit = plan.get("limit")
    if limit and isinstance(limit, int) and limit > 0:
        sql += f"\nLIMIT {limit}"

    return sql, params
