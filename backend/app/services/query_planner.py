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
    get_default_metric,
    set_default_metric,
    reset_default_metric
)
from app.utils.tz_helper import get_ist_time


class PlanCompilationError(Exception):
    pass


class QueryShapeUnsupportedError(Exception):
    pass


class UnsupportedMetricError(Exception):
    pass


def detect_profit_inquiry(question: str, columns: List[str], user_metrics: List[Dict[str, Any]]) -> Optional[str]:
    """
    Detects if a user is asking for Profit when neither
    a registered Profit metric nor relevant columns exist in the dataset.
    Never substitute revenue for profit.
    """
    q_lower = question.lower()
    profit_words = ["profit", "net profit", "gross profit", "profitability"]
    asks_profit = any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in profit_words)
    if not asks_profit:
        return None

    # Check if a user metric specifically for profit exists
    has_profit_metric = any(
        any(
            re.search(rf"\b{re.escape(pw)}\b", m["name"].lower()) or
            any(re.search(rf"\b{re.escape(pw)}\b", a.lower()) for a in m.get("approved_aliases", []))
            for pw in profit_words
        )
        for m in user_metrics
    )
    if has_profit_metric:
        return None

    # Check if a profit or cost column exists in dataset schema
    cols_lower = [c.lower() for c in columns]
    has_profit_col = any("profit" in c for c in cols_lower)
    has_cost_col = any("cost" in c or "cogs" in c or "expense" in c for c in cols_lower)

    if not has_profit_col and not has_cost_col:
        return (
            "Profit cannot be calculated because neither a 'Profit' metric definition nor the necessary "
            "cost data (e.g., Cost, Expense, COGS) exists in this dataset. "
            "Please register a Profit metric in the Business Metric Registry if data becomes available."
        )

    return None


def detect_sales_ambiguity(
    question: str,
    columns: List[str],
    user_metrics: List[Dict[str, Any]],
    user_id: str,
    table_name: str
) -> Optional[Dict[str, Any]]:
    """
    Checks if a question asking for 'sales' is ambiguous between
    Revenue (monetary) and Quantity (volume), when the dataset contains both.
    Respects saved default metrics unless an explicit override is requested.
    """
    q_lower = question.lower()

    # Explicit revenue terms
    explicit_revenue_terms = [
        "revenue", "dollar", "amount", "income", "turnover", "in usd", "in $", "monetary", "sales amount", "gross sales"
    ]
    # Explicit quantity terms
    explicit_quantity_terms = [
        "quantity", "units", "volume", "pieces", "count of items", "items sold", "number of items", "qty", "units sold"
    ]

    has_explicit_rev = any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in explicit_revenue_terms)
    has_explicit_qty = any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in explicit_quantity_terms)

    # If the user explicitly asks for revenue or quantity, it is not ambiguous
    if has_explicit_rev or has_explicit_qty:
        return None

    # Check if question asks for "sales"
    sales_patterns = [r"\bsales?\b", r"\bselling\b", r"\bbest[-\s]?seller\b"]
    matches_sales = any(re.search(pat, q_lower) for pat in sales_patterns)
    if not matches_sales:
        return None

    # Check if user has a saved default metric for "sales"
    saved_default = get_default_metric(user_id, table_name, concept="sales")
    if saved_default:
        # Default exists and no explicit override requested -> Use default metric!
        return None

    # Check if dataset has plausible revenue column and plausible quantity column
    cols_map = {c.lower(): c for c in columns}

    rev_col_candidates = [c for c in cols_map if any(k in c for k in ["total_sales", "total sales", "revenue", "sales_amount"])]
    qty_col_candidates = [c for c in cols_map if any(k in c for k in ["quantity_ordered", "quantity", "qty", "units_sold", "units"])]

    # Also check if Unit_Price and Quantity exist to derive revenue
    has_derived_rev = ("unit_price" in cols_map or "unit price" in cols_map) and len(qty_col_candidates) > 0

    if (rev_col_candidates or has_derived_rev) and qty_col_candidates:
        if rev_col_candidates:
            rev_canonical = cols_map[rev_col_candidates[0]]
            rev_expr = rev_canonical
        else:
            up_col = cols_map.get("unit_price") or cols_map.get("unit price")
            qty_col = cols_map[qty_col_candidates[0]]
            rev_canonical = f"{up_col} * {qty_col}"
            rev_expr = rev_canonical

        qty_canonical = cols_map[qty_col_candidates[0]]

        return {
            "ambiguous_term": "sales",
            "prompt": "How would you like to measure 'sales' for this query?",
            "options": [
                {
                    "id": "revenue",
                    "label": "Total Revenue (Monetary Sales)",
                    "description": f"Calculate sum of monetary revenue using `{rev_expr}`",
                    "metric_name": "Revenue",
                    "expression": rev_expr,
                    "aggregation": "SUM",
                    "currency_unit": "USD",
                },
                {
                    "id": "quantity",
                    "label": "Units Sold (Volume)",
                    "description": f"Calculate total unit volume using `{qty_canonical}`",
                    "metric_name": "Units Sold",
                    "expression": qty_canonical,
                    "aggregation": "SUM",
                    "currency_unit": "units",
                }
            ]
        }

    return None


def extract_dimensions_and_grouping(
    question: str,
    columns: List[str],
    measure_columns: Optional[List[str]] = None
) -> List[str]:
    """
    Extracts grouping dimensions from the question:
    1. Group clauses: 'by <dim>', 'per <dim>', 'for each <dim>', 'across <dim>'
    2. Subject patterns: 'which <dim> has...', 'what <dim> has...', 'top <dim> by...'
    3. Strict separation: Measure columns (e.g. Total Sales Amount, Unit Price) are NEVER
       added as dimensions unless explicitly requested as a dimension.
    """
    q_lower = re.sub(r"\bacross\s+(?:all\s+)?(?:orders|records|rows)\b", "", question.lower()).rstrip(" ?.!;")
    dimensions = []
    measure_cols_lower = [m.lower() for m in (measure_columns or [])]

    # Map column names
    col_map = {c.lower(): c for c in columns}
    col_clean_map = {c.lower().replace("_", " "): c for c in columns}

    # 1. Subject extraction: "Which <dim> has/had/is/with...", "What <dim> has...", "Who is the top <dim>..."
    subject_match = re.search(r"\b(?:which|what|who is the top|find the top|best)\s+([a-zA-Z_\s]+?)\s+(?:has|had|is|are|with|in|for|by|sold|generated)\b", q_lower)
    if subject_match:
        subject = subject_match.group(1).strip()
        # Exclude metric words from subject
        if subject not in ["sales", "revenue", "orders", "records", "items", "amount", "unit", "units"]:
            # Check if subject matches a column
            for col in columns:
                if col.lower() in measure_cols_lower:
                    continue
                col_clean = col.lower().replace("_", " ")
                col_tokens = [t for t in col_clean.split() if len(t) > 2]
                if subject == col_clean or subject in col_tokens:
                    if col not in dimensions:
                        dimensions.append(col)
                    break

    # 2. Group clauses: "by <phrase>", "per <phrase>", "across <phrase>", "for each <phrase>"
    group_matches = re.findall(r"\b(?:by|per|across|for each|each|grouped by|group by)\s+([a-zA-Z0-9_\s]+?)(?=\s+(?:for|in|where|with|having|order|limit|sort|having)|$)", q_lower)
    group_matches = [part.strip() for phrase in group_matches for part in re.split(r"\s+and\s+|,|&", phrase)]
    for gm in group_matches:
        phrase = gm.strip()
        # Find exact or best matching column for this specific group phrase
        matched_for_phrase = None

        # Check full phrase match
        for col in columns:
            if col.lower() in measure_cols_lower:
                continue
            col_clean = col.lower().replace("_", " ")
            if phrase == col_clean or phrase == col.lower():
                matched_for_phrase = col
                break

        # Check token matching if no full match
        if not matched_for_phrase:
            phrase_tokens = [w for w in phrase.split() if len(w) > 2 and w not in ["the", "all", "each"]]
            for col in columns:
                if col.lower() in measure_cols_lower:
                    continue
                col_clean = col.lower().replace("_", " ")
                col_tokens = [t for t in col_clean.split() if len(t) > 2]
                if phrase_tokens and all(pt in col_tokens for pt in phrase_tokens):
                    matched_for_phrase = col
                    break

        if matched_for_phrase and matched_for_phrase not in dimensions:
            dimensions.append(matched_for_phrase)

    # A column mentioned as a filter or measure is not a grouping dimension.
    # Only the explicit grouping and subject clauses above establish dimensions.
    return dimensions


def extract_limit_and_ordering(question: str) -> Tuple[Optional[int], str]:
    """
    Extracts limit (e.g. 'top 5', 'lowest 10', 'highest', 'lowest', 'bottom 3')
    and sort direction ('DESC' or 'ASC').
    """
    q_lower = question.lower()

    # Sort direction
    direction = "DESC"
    if any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in ["lowest", "bottom", "least", "smallest", "worst", "minimum", "min"]):
        direction = "ASC"

    # Numeric limit
    limit_match = re.search(r"\b(?:top|bottom|highest|lowest|first|best|worst)\s+(\d+)\b", q_lower)
    if limit_match:
        limit = int(limit_match.group(1))
    elif any(re.search(rf"\b{re.escape(w)}\b", q_lower) for w in ["highest", "lowest", "top", "bottom", "best", "worst", "most", "maximum", "max", "lead", "leading"]):
        limit = 1
    else:
        limit = None

    return limit, direction


def extract_filters_and_date_range(question: str, columns: List[str]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Extracts filters and date ranges from the question:
    - Status/category filters (e.g. 'for completed orders' -> Order Status = 'completed')
    - Year filters (e.g. 'in 2023' -> YEAR(`Order Date`) = 2023)
    """
    q_lower = question.lower()
    filters = []
    date_range = None

    # 1. Date / Year extraction
    year_match = re.search(r"\b(?:in|for|during|year)\s+(20\d\d|19\d\d)\b", q_lower)
    if year_match:
        year_val = int(year_match.group(1))
        # Identify date column in dataset
        date_col = next((c for c in columns if any(k in c.lower() for k in ["date", "time", "year", "created"])), None)
        if date_col:
            date_range = {
                "column": date_col,
                "year": year_val,
                "start": f"{year_val}-01-01",
                "end": f"{year_val}-12-31"
            }

    # 2. Status / Value filters
    # Look for status keywords: 'completed', 'cancelled', 'pending', 'delivered', 'shipped', 'active', 'inactive'
    status_keywords = ["completed", "cancelled", "pending", "delivered", "shipped", "active", "inactive", "closed"]
    status_col = next((c for c in columns if any(k in c.lower() for k in ["status", "state"])), None)
    if status_col:
        for kw in status_keywords:
            if re.search(rf"\b{re.escape(kw)}\b", q_lower):
                filters.append({
                    "column": status_col,
                    "operator": "=",
                    "value": kw
                })
                break

    # Look for explicit column = 'value' syntax
    for col in columns:
        if col.lower() in ["id", "_row_id"]:
            continue
        col_clean = col.lower().replace("_", " ")
        match = re.search(rf"\b{re.escape(col_clean)}\s*(?:is|=|equal to)\s*['\"]?([a-zA-Z0-9_\-\s]+)['\"]?", q_lower)
        if match:
            filters.append({
                "column": col,
                "operator": "=",
                "value": match.group(1).strip()
            })

    return filters, date_range


def build_plan_explanation(
    metric_name: str,
    dimensions: List[str],
    limit: Optional[int],
    direction: str,
    filters: List[Dict[str, Any]],
    date_range: Optional[Dict[str, Any]]
) -> str:
    """
    Builds a concise, accurate human-readable interpretation of the query plan.
    Preserves metric names (e.g. 'Revenue', 'Units Sold').
    """
    parts = []
    if limit:
        rank_word = "Highest" if direction == "DESC" else "Lowest"
        parts.append(f"{rank_word} {limit}" if limit > 1 else f"{rank_word}")

    parts.append(metric_name)

    if dimensions:
        parts.append(f"by {', '.join(dimensions)}")

    details = []
    if filters:
        filter_str = " and ".join(f"{f['column']} = '{f['value']}'" for f in filters)
        details.append(filter_str)

    if date_range:
        details.append(f"in {date_range.get('year', '')}")

    if details:
        parts.append(f"({' for '.join(details)})")

    return " ".join(parts)


def resolve_or_create_plan(
    question: str,
    table_name: str,
    user_id: str,
    override_metric: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Constructs, validates, and resolves a TypedQueryPlan for the user's question.
    If ambiguity is detected, saves the partially resolved plan on the server
    and returns a clarification request.
    """
    columns = get_authorized_dataset_columns(table_name, user_id)
    friendly_name = table_name.split("_usr_")[0]
    # This planner implements a deliberately small grammar. Complex questions
    # must reach the schema-aware generative path instead of losing conditions.
    q = question.lower()
    if re.search(r"\b(join|versus|compare|monthly|weekly|daily|quarterly|between|before|after|contains|distinct|having|except|excluding|not|or)\b|[<>]", q):
        raise PlanCompilationError("Question requires the generative query planner.")
    if not re.search(r"\b(total|sum|average|avg|count|how many|number of|highest|lowest|top|bottom|best|worst|most|least|maximum|minimum|by|per|across|each)\b", q):
        raise PlanCompilationError("No supported aggregate request detected.")
    user_metrics = list_metrics(user_id, table_name)

    # Another dataset or a rich filter cannot be represented by this simple
    # planner. Prefer generation over returning a plausible but incomplete total.
    if re.search(r"\b(under|over|above|below|greater|less|more than|last|previous|this month|this year|trend|growth|percentage|percent|median)\b", q):
        raise PlanCompilationError("Question requires richer filters or calculations.")

    # 1. Check for unsupported profit inquiry (Requirement G)
    profit_err = detect_profit_inquiry(question, columns, user_metrics)
    if profit_err:
        raise UnsupportedMetricError(profit_err)

    # 2. Extract common plan components first (to preserve across clarification)
    limit, direction = extract_limit_and_ordering(question)
    filters, date_range = extract_filters_and_date_range(question, columns)

    # Do not silently ignore free-form filters such as "for customers in London".
    residual = q
    if date_range:
        residual = re.sub(r"\b(?:in|for|during|year)\s+(?:20\d\d|19\d\d)\b", "", residual)
    for item in filters:
        if item["column"].lower().replace("_", " ") in residual:
            residual = re.sub(rf"\b{re.escape(item['column'].lower().replace('_', ' '))}\s*(?:is|=|equal to)\s*['\"]?{re.escape(str(item['value']).lower())}['\"]?", "", residual)
        residual = re.sub(rf"\b(?:for|with)\s+{re.escape(str(item['value']).lower())}\s*(?:orders|records)?", "", residual)
    if re.search(r"\b(?:where|with|for|in|during)\s+\S", residual):
        raise PlanCompilationError("Question contains a filter requiring SQL generation.")

    # 3. Check for clarification / ambiguity
    if not override_metric:
        ambiguity = detect_sales_ambiguity(question, columns, user_metrics, user_id, table_name)
        if ambiguity:
            # Extract dimensions before clarification so they are preserved
            preliminary_dims = extract_dimensions_and_grouping(question, columns, measure_columns=[])

            # Partially resolved plan stored in server database with ownership & 30-min expiry
            partially_resolved_plan = {
                "table_name": table_name,
                "question": question,
                "grouping_dimensions": preliminary_dims,
                "filters": filters,
                "date_range": date_range,
                "ordering": {
                    "target": "metric",
                    "direction": direction
                },
                "limit": limit,
                "tie_handling": "standard",
                "unresolved_metric": ambiguity["ambiguous_term"]
            }

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
                    proposed_plan_json=json.dumps(partially_resolved_plan),
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

    # 4. Resolve Metric
    chosen_metric = None

    if override_metric:
        chosen_metric = override_metric
    else:
        # Check if saved default metric applies
        saved_default = get_default_metric(user_id, table_name, concept="sales")
        q_lower = question.lower()

        # Resolve against registered user metrics first
        # Strip aggregation cues like "what is total", "show total", "total"
        clean_q = re.sub(r"^(?:what is|show|get|find|calculate|list)\s+", "", q_lower)
        clean_q = re.sub(r"\b(?:total|sum of|average of|count of)\s+", "", clean_q)

        matched_metrics = []
        for m in user_metrics:
            m_name = m["name"].lower()
            aliases = [a.lower() for a in m.get("approved_aliases", [])]

            if re.search(rf"\b{re.escape(m_name)}\b", clean_q) or re.search(rf"\b{re.escape(m_name)}\b", q_lower):
                matched_metrics.append(m)
            else:
                for alias in aliases:
                    if re.search(rf"\b{re.escape(alias)}\b", clean_q) or re.search(rf"\b{re.escape(alias)}\b", q_lower):
                        matched_metrics.append(m)
                        break

        # Check for conflicting aliases across distinct metrics
        if len(matched_metrics) > 1:
            # Check if definitions materially differ
            unique_exprs = {m["expression"] for m in matched_metrics}
            if len(unique_exprs) > 1:
                # Multiple metrics share conflicting aliases -> return clarification
                db = SessionLocal()
                try:
                    clar_id = f"clar_{uuid.uuid4().hex[:16]}"
                    conflict_options = [
                        {
                            "id": f"metric_{m['id']}",
                            "label": m["name"],
                            "description": m.get("description") or f"Calculate using `{m['expression']}` ({m['supported_aggregation']})",
                            "metric_name": m["name"],
                            "expression": m["expression"],
                            "aggregation": m["supported_aggregation"],
                            "currency_unit": m.get("currency_unit", ""),
                            "metric_id": m["id"]
                        }
                        for m in matched_metrics
                    ]
                    preliminary_dims = extract_dimensions_and_grouping(question, columns, measure_columns=[])
                    partially_resolved_plan = {
                        "table_name": table_name,
                        "question": question,
                        "grouping_dimensions": preliminary_dims,
                        "filters": filters,
                        "date_range": date_range,
                        "ordering": {"target": "metric", "direction": direction},
                        "limit": limit,
                        "tie_handling": "standard"
                    }
                    session = ClarificationSession(
                        id=clar_id,
                        user_id=user_id,
                        original_question=question,
                        table_name=table_name,
                        clarification_prompt="Multiple metrics match your query. Which definition would you like to use?",
                        options_json=json.dumps(conflict_options),
                        proposed_plan_json=json.dumps(partially_resolved_plan),
                        expires_at=get_ist_time() + timedelta(minutes=30)
                    )
                    db.add(session)
                    db.commit()

                    return {
                        "needs_clarification": True,
                        "clarification_id": clar_id,
                        "prompt": "Multiple metrics match your query. Which definition would you like to use?",
                        "options": conflict_options,
                        "original_question": question
                    }
                finally:
                    db.close()
            else:
                chosen_metric = matched_metrics[0]
        elif len(matched_metrics) == 1:
            chosen_metric = matched_metrics[0]
        elif saved_default and any(w in q_lower for w in ["sales", "selling"]) and not re.search(r"\b(revenue|turnover|income|quantity|volume|units|qty)\b", q_lower):
            chosen_metric = saved_default
        else:
            # Infer standard metric from columns
            cols_map = {c.lower().replace(" ", "_"): c for c in columns}
            if any(w in q_lower for w in ["revenue", "turnover", "income", "sales", "total sales"]):
                rev_col = next((cols_map[c] for c in cols_map if any(k in c for k in ["total_sales", "total sales", "revenue", "sales_amount"])), None)
                if not rev_col and "unit_price" in cols_map and "quantity_ordered" in cols_map:
                    chosen_metric = {
                        "name": "Revenue",
                        "expression": f"{cols_map['unit_price']} * {cols_map['quantity_ordered']}",
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
            elif any(w in q_lower for w in ["quantity", "volume", "units", "units sold", "items sold", "qty"]):
                qty_col = next((cols_map[c] for c in cols_map if any(k in c for k in ["quantity", "qty", "units"])), None)
                if qty_col:
                    chosen_metric = {
                        "name": "Units Sold",
                        "expression": qty_col,
                        "aggregation": "SUM",
                        "currency_unit": "units",
                        "description": f"Total volume sum using `{qty_col}`"
                    }
            elif any(w in q_lower for w in ["count", "how many", "number of orders", "number of records", "total orders"]):
                chosen_metric = {
                    "name": "Record Count",
                    "expression": columns[0],
                    "aggregation": "COUNT",
                    "currency_unit": "records",
                    "description": "Total count of records"
                }
            elif any(w in q_lower for w in ["average", "avg"]):
                num_col = next((cols_map[c] for c in cols_map if any(k in c for k in ["unit_price", "price", "amount", "salary"])), None)
                if num_col:
                    chosen_metric = {
                        "name": f"Average {num_col}",
                        "expression": num_col,
                        "aggregation": "AVG",
                        "currency_unit": "",
                        "description": f"Average of `{num_col}`"
                    }

    if not chosen_metric:
        raise PlanCompilationError("Could not resolve a suitable metric for this question against the dataset schema.")

    if not (chosen_metric.get("id") or chosen_metric.get("metric_id")):
        requested_agg = next((agg for pattern, agg in [
            (r"\b(average|avg|mean)\b", "AVG"),
            (r"\b(minimum|min)\b", "MIN"),
            (r"\b(maximum|max)\b", "MAX"),
        ] if re.search(pattern, question, re.IGNORECASE)), None)
        if requested_agg:
            chosen_metric = dict(chosen_metric, aggregation=requested_agg)

    # 5. Extract measure columns to strictly exclude from grouping dimensions (Requirement D)
    _, measure_cols = validate_and_compile_expression(
        chosen_metric["expression"], columns,
        chosen_metric.get("supported_aggregation", chosen_metric.get("aggregation", "SUM"))
    )

    # 6. Extract grouping dimensions strictly separating measures from dimensions
    dimensions = extract_dimensions_and_grouping(question, columns, measure_columns=measure_cols)

    grouping_question = re.sub(r"\bacross\s+(?:all\s+)?(?:orders|records|rows)\b", "", question, flags=re.IGNORECASE)
    if re.search(r"\b(?:by|per|across|for each|grouped by|group by)\s+", grouping_question, re.IGNORECASE) and not dimensions:
        raise PlanCompilationError("Requested grouping could not be resolved reliably.")

    # Metric naming hygiene (NEVER label as generic "Metric")
    resolved_metric_name = chosen_metric.get("metric_name") or chosen_metric.get("name") or "Revenue"

    # 7. Build Canonical Typed Query Plan
    plan = {
        "dataset_table": table_name,
        "metric_name": resolved_metric_name,
        "metric_id": chosen_metric.get("id") or chosen_metric.get("metric_id"),
        "metric_expression": chosen_metric.get("expression", resolved_metric_name),
        "metric_aggregation": chosen_metric.get("supported_aggregation", chosen_metric.get("aggregation", "SUM")),
        "currency_unit": chosen_metric.get("currency_unit", ""),
        "description": chosen_metric.get("description", ""),
        "grouping_dimensions": dimensions,
        "filters": filters,
        "date_range": date_range,
        "ordering": {
            "target": "metric",
            "direction": direction
        },
        "limit": limit,
        "tie_handling": "standard",
        "explanation": build_plan_explanation(resolved_metric_name, dimensions, limit, direction, filters, date_range)
    }

    return {
        "needs_clarification": False,
        "plan": plan
    }


def compile_plan_to_sql(plan: Dict[str, Any], table_name: str, allowed_columns: List[str]) -> Tuple[str, Dict[str, Any]]:
    """
    Deterministically compiles a validated TypedQueryPlan into safe SQL.
    Returns:
        (sql_query, sql_params)
    """
    metric_expr = plan["metric_expression"]
    agg = plan.get("metric_aggregation", "SUM")
    metric_sql, _ = validate_and_compile_expression(metric_expr, allowed_columns, agg)

    metric_name = plan.get("metric_name", "Revenue")
    metric_alias = re.sub(r'[^a-zA-Z0-9_]', '_', metric_name).strip('_') or "Revenue"

    dims = plan.get("grouping_dimensions", [])
    for d in dims:
        if d not in allowed_columns:
            raise PlanCompilationError(f"Dimension '{d}' is not an authorized column in dataset.")

    select_parts = [f"`{d}`" for d in dims]
    select_parts.append(f"{metric_sql} AS `{metric_alias}`")

    where_parts = []
    params = {}
    param_idx = 0

    # 1. Date Range
    date_range = plan.get("date_range")
    if date_range and date_range.get("column") in allowed_columns:
        date_col = date_range["column"]
        year_val = date_range.get("year")
        if year_val:
            param_name = f"param_{param_idx}"
            where_parts.append(f"YEAR(`{date_col}`) = :{param_name}")
            params[param_name] = year_val
            param_idx += 1

    # 2. Filters
    for f in plan.get("filters", []):
        col = f["column"]
        if col not in allowed_columns:
            raise PlanCompilationError(f"Filter column '{col}' is not authorized.")
        op = f.get("operator", "=").upper()
        if op not in {"=", "!=", "<", ">", "<=", ">=", "LIKE", "NOT LIKE"}:
            raise PlanCompilationError("Unsupported filter operator.")
        param_name = f"param_{param_idx}"
        where_parts.append(f"`{col}` {op} :{param_name}")
        params[param_name] = f["value"]
        param_idx += 1

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
        if target != "metric" and target not in allowed_columns:
            raise PlanCompilationError("Unknown ordering column.")
        order_col = f"`{metric_alias}`" if target == "metric" else f"`{target}`"
        sql += f"\nORDER BY {order_col} {dir_sql}"

    limit = plan.get("limit")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0 or limit > 10000:
            raise PlanCompilationError("Limit must be an integer between 1 and 10000.")
        sql += f"\nLIMIT {limit}"

    return sql, params


def refine_and_execute_plan(
    original_plan: Dict[str, Any],
    refinements: Dict[str, Any],
    table_name: str,
    user_id: str
) -> Dict[str, Any]:
    """
    Applies user-selected refinements to an existing TypedQueryPlan and re-compiles it.
    Updates only the intended fields (limit, direction, dimensions, filters).
    """
    allowed_cols = get_authorized_dataset_columns(table_name, user_id)
    new_plan = dict(original_plan)

    if "limit" in refinements:
        new_plan["limit"] = refinements["limit"]

    if "direction" in refinements:
        new_plan["ordering"] = {
            "target": "metric",
            "direction": "DESC" if refinements["direction"].upper() == "DESC" else "ASC"
        }

    if "grouping_dimensions" in refinements:
        new_dims = refinements["grouping_dimensions"]
        for d in new_dims:
            if d not in allowed_cols:
                raise PlanCompilationError(f"Dimension '{d}' does not exist in schema.")
        new_plan["grouping_dimensions"] = new_dims

    if "filters" in refinements:
        new_plan["filters"] = refinements["filters"]

    # Re-build explanation
    new_plan["explanation"] = build_plan_explanation(
        new_plan["metric_name"],
        new_plan.get("grouping_dimensions", []),
        new_plan.get("limit"),
        new_plan.get("ordering", {}).get("direction", "DESC"),
        new_plan.get("filters", []),
        new_plan.get("date_range")
    )

    sql, params = compile_plan_to_sql(new_plan, table_name, allowed_cols)
    return {
        "plan": new_plan,
        "sql": sql,
        "params": params
    }
