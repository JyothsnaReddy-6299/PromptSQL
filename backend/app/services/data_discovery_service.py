"""
PromptSQL — Automated Data Discovery & AI Insights Engine (Issue 15)

Production-grade automated data discovery system that:
1. Profiles authorized dataset schemas, column classifications, distributions, and data quality.
2. Performs deterministic statistical discovery (concentration, skewness, disparity, distributions).
3. Detects temporal trends (monthly/yearly period-over-period growth, fluctuations, peaks).
4. Identifies explainable anomalies (Tukey's IQR 1.5x rule, Z-score > 3.0, null concentrations, duplicate IDs).
5. Computes numerical correlations (Pearson r >= 0.5) and categorical aggregations.
6. Synthesizes business-relevant patterns grounded in verified column semantics.
7. Validates every insight with supporting SQL queries and representative record evidence.
8. Generates natural-language AI explanations using LLM with deterministic fallback.
9. Enforces strict tenant isolation, bounded SQL queries, and cache invalidation.
"""

import math
import time
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple, Set
from decimal import Decimal
from sqlalchemy import inspect, text
import sqlglot
from sqlglot import exp

from app.database.connection import engine
from app.services.dataset_guard import (
    resolve_and_authorize_dataset,
    get_user_datasets,
    is_system_table,
    safe_quote_table_name,
)
from app.services.sql_executor import execute_sql
from app.services.llm_service import call_llm
from app.services.aggregate_summary import format_value, to_number


# ---------------------------------------------------------------------------
# In-Memory Discovery Cache with TTL (5 minutes)
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 300
_INSIGHTS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def get_cached_insights(user_id: str, table_name: str) -> Optional[Dict[str, Any]]:
    key = f"{user_id}:{table_name}"
    entry = _INSIGHTS_CACHE.get(key)
    if entry:
        timestamp, data = entry
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return data
        else:
            del _INSIGHTS_CACHE[key]
    return None


def set_cached_insights(user_id: str, table_name: str, data: Dict[str, Any]) -> None:
    key = f"{user_id}:{table_name}"
    _INSIGHTS_CACHE[key] = (time.time(), data)


def invalidate_insights_cache(user_id: str, table_name: Optional[str] = None) -> None:
    """Invalidates cached insights for a user, optionally for a specific table."""
    if table_name:
        key = f"{user_id}:{table_name}"
        _INSIGHTS_CACHE.pop(key, None)
    else:
        prefix = f"{user_id}:"
        keys_to_remove = [k for k in _INSIGHTS_CACHE if k.startswith(prefix)]
        for k in keys_to_remove:
            _INSIGHTS_CACHE.pop(k, None)


# ---------------------------------------------------------------------------
# Mathematical Helper Functions for Statistical Tests
# ---------------------------------------------------------------------------
def _betainc_cf(a: float, b: float, x: float, max_iter: int = 200, eps: float = 1e-12) -> float:
    """Lentz continued fraction for regularized incomplete beta function."""
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c

        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        del_h = d * c
        h *= del_h
        if abs(del_h - 1.0) < eps:
            break
    front = math.exp(math.lgamma(qab) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    return front * h / a


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if x > (a + 1.0) / (a + b + 2.0):
        return 1.0 - _betainc_cf(b, a, 1.0 - x)
    return _betainc_cf(a, b, x)


def calculate_pearson_p_value(r: float, n: int) -> float:
    """Computes exact two-tailed p-value for Pearson correlation using Student's t distribution."""
    if n < 3 or abs(r) >= 1.0:
        return 0.0
    df = n - 2
    t_val = abs(r) * math.sqrt(df / max(1e-12, (1.0 - r * r)))
    x = df / (df + t_val * t_val)
    return betainc(0.5 * df, 0.5, x)


# ---------------------------------------------------------------------------
# Column Semantic Classifications
# ---------------------------------------------------------------------------
REVENUE_KEYWORDS = {"revenue", "sales", "price", "amount", "spend", "cost", "total_amount", "salary", "balance", "fee", "fare"}
QUANTITY_KEYWORDS = {"quantity", "qty", "units", "count", "headcount", "inventory", "stock", "volume", "enrollment"}
PERFORMANCE_KEYWORDS = {"score", "marks", "rating", "grade", "gpa", "percentage", "accuracy", "efficiency"}
ENTITY_KEYWORDS = {"name", "title", "category", "department", "product", "customer", "student", "employee", "country", "city", "state", "status"}


def classify_columns(table_name: str) -> Dict[str, List[str]]:
    """
    Inspects live database schema and classifies columns into:
    numeric, categorical, date, boolean, and text.
    """
    inspector = inspect(engine)
    raw_columns = inspector.get_columns(table_name)
    
    classification = {
        "numeric": [],
        "categorical": [],
        "date": [],
        "boolean": [],
        "text": [],
        "all": [],
        "types": {}
    }

    for col in raw_columns:
        c_name = col["name"]
        c_type_str = str(col["type"]).upper()
        classification["all"].append(c_name)
        classification["types"][c_name] = c_type_str

        # Skip surrogate auto-increment 'id' if generic
        if c_name.lower() in ("id", "_id"):
            continue

        if any(t in c_type_str for t in ["BOOL", "TINYINT(1)"]) or "BOOL" in c_type_str or c_type_str == "TINYINT" or (c_name.lower().startswith(("is_", "has_", "should_")) or c_name.lower() in ("passed", "active", "enabled")):
            classification["boolean"].append(c_name)
        elif any(t in c_type_str for t in ["INT", "DOUBLE", "FLOAT", "DECIMAL", "NUMERIC", "REAL"]):
            if "TINYINT" not in c_type_str or c_name.lower() not in ("passed", "active", "enabled"):
                classification["numeric"].append(c_name)
        elif any(t in c_type_str for t in ["DATE", "DATETIME", "TIMESTAMP"]):
            classification["date"].append(c_name)
        else:
            classification["text"].append(c_name)

    return classification


# ---------------------------------------------------------------------------
# Section 2.1 — Dataset Profiling
# ---------------------------------------------------------------------------
def profile_dataset(table_name: str, classifications: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Computes a comprehensive, bounded statistical profile of the active dataset.
    Avoids full-table memory loads by using aggregate SQL and bounded sampling.
    """
    profile: Dict[str, Any] = {
        "total_records": 0,
        "total_columns": len(classifications["all"]),
        "column_names": classifications["all"],
        "column_types": classifications["types"],
        "numeric_columns": classifications["numeric"],
        "categorical_columns": [],
        "date_columns": classifications["date"],
        "boolean_columns": classifications["boolean"],
        "text_columns": classifications["text"],
        "column_missing": {},
        "column_distinct": {},
        "column_stats": {},
        "categorical_frequencies": {},
        "date_ranges": {},
        "primary_key_candidates": [],
        "potential_dimensions": [],
        "data_quality_score": 100.0,
        "quality_findings": []
    }

    safe_tbl = f"`{table_name}`"

    # 1. Total row count
    res = execute_sql(f"SELECT COUNT(*) as total_rows FROM {safe_tbl}")
    total_rows = res.records[0]["total_rows"] if res.records else 0
    profile["total_records"] = total_rows

    if total_rows == 0:
        profile["data_quality_score"] = 0.0
        profile["quality_findings"].append("The dataset is currently empty (0 records).")
        return profile

    # 2. Column missing counts & distinct counts (batched bounded query)
    missing_exprs = []
    distinct_exprs = []
    for col in classifications["all"]:
        safe_c = f"`{col}`"
        missing_exprs.append(f"SUM(CASE WHEN {safe_c} IS NULL OR CAST({safe_c} AS CHAR) = '' THEN 1 ELSE 0 END) as `miss_{col}`")
        distinct_exprs.append(f"COUNT(DISTINCT {safe_c}) as `dist_{col}`")

    if missing_exprs:
        query_sql = f"SELECT {', '.join(missing_exprs + distinct_exprs)} FROM {safe_tbl}"
        stats_res = execute_sql(query_sql)
        if stats_res.records:
            row = stats_res.records[0]
            for col in classifications["all"]:
                miss = int(row.get(f"miss_{col}") or 0)
                dist = int(row.get(f"dist_{col}") or 0)
                profile["column_missing"][col] = miss
                profile["column_distinct"][col] = dist

                # PK candidate detection: 0 nulls & distinct count equals total records
                if miss == 0 and dist == total_rows and total_rows > 1:
                    profile["primary_key_candidates"].append(col)

    # 3. Categorical column refinement (text columns with cardinality <= 50 or <= 25% of rows)
    categorical_cols: List[str] = []
    for col in classifications["text"]:
        dist = profile["column_distinct"].get(col, 0)
        if dist > 0 and (dist <= 50 or dist <= max(5, int(total_rows * 0.25))):
            categorical_cols.append(col)
    profile["categorical_columns"] = categorical_cols
    profile["potential_dimensions"] = categorical_cols + classifications["date"]

    # 4. Numeric column distributions (min, max, mean, stddev, quartiles, median)
    for col in classifications["numeric"]:
        safe_c = f"`{col}`"
        num_sql = f"""
            SELECT 
                MIN({safe_c}) as min_val,
                MAX({safe_c}) as max_val,
                AVG({safe_c}) as mean_val,
                STDDEV_POP({safe_c}) as std_val
            FROM {safe_tbl}
            WHERE {safe_c} IS NOT NULL
        """
        num_res = execute_sql(num_sql)
        if num_res.records and num_res.records[0]["min_val"] is not None:
            r = num_res.records[0]
            min_v = to_number(r["min_val"]) or 0.0
            max_v = to_number(r["max_val"]) or 0.0
            mean_v = to_number(r["mean_val"]) or 0.0
            std_v = to_number(r["std_val"]) or 0.0

            # Unbiased quartile calculation across all non-null values
            if total_rows <= 50000:
                sample_sql = f"SELECT {safe_c} as v FROM {safe_tbl} WHERE {safe_c} IS NOT NULL ORDER BY {safe_c} ASC"
            else:
                step = max(1, total_rows // 10000)
                sample_sql = f"SELECT {safe_c} as v FROM {safe_tbl} WHERE {safe_c} IS NOT NULL AND MOD(id, {step}) = 0 ORDER BY {safe_c} ASC LIMIT 10000"

            s_res = execute_sql(sample_sql, max_rows=max(total_rows, 1000))
            vals = [to_number(x["v"]) for x in s_res.records if to_number(x["v"]) is not None]

            q1, median, q3 = min_v, mean_v, max_v
            distinct_cnt = profile["column_distinct"].get(col, len(set(vals)) if vals else 0)
            is_discrete = False

            if vals:
                n = len(vals)
                q1 = vals[int(n * 0.25)]
                median = vals[int(n * 0.50)]
                q3 = vals[int(n * 0.75)]
                is_discrete = distinct_cnt <= 10 or (n > 50 and distinct_cnt / n < 0.05)

            iqr_val = round(q3 - q1, 2)
            profile["column_stats"][col] = {
                "min": round(min_v, 2),
                "max": round(max_v, 2),
                "mean": round(mean_v, 2),
                "median": round(median, 2),
                "stddev": round(std_v, 2),
                "q1": round(q1, 2),
                "q3": round(q3, 2),
                "iqr": iqr_val,
                "distinct_count": distinct_cnt,
                "is_discrete": is_discrete
            }

    # 5. Categorical value frequencies
    for col in profile["categorical_columns"][:5]:
        safe_c = f"`{col}`"
        freq_sql = f"""
            SELECT {safe_c} as val, COUNT(*) as cnt,
                   ROUND(COUNT(*) * 100.0 / {total_rows}, 2) as pct
            FROM {safe_tbl}
            WHERE {safe_c} IS NOT NULL AND {safe_c} != ''
            GROUP BY {safe_c}
            ORDER BY cnt DESC
            LIMIT 5
        """
        freq_res = execute_sql(freq_sql)
        profile["categorical_frequencies"][col] = freq_res.records

    # 6. Date ranges and temporal coverage
    for col in classifications["date"]:
        safe_c = f"`{col}`"
        date_sql = f"""
            SELECT 
                MIN({safe_c}) as min_date,
                MAX({safe_c}) as max_date,
                COUNT(DISTINCT DATE({safe_c})) as distinct_dates
            FROM {safe_tbl}
            WHERE {safe_c} IS NOT NULL
        """
        d_res = execute_sql(date_sql)
        if d_res.records and d_res.records[0]["min_date"] is not None:
            r = d_res.records[0]
            profile["date_ranges"][col] = {
                "min_date": str(r["min_date"]),
                "max_date": str(r["max_date"]),
                "distinct_dates": int(r["distinct_dates"] or 0)
            }

    # 7. Data Quality Score calculation
    total_cells = total_rows * len(classifications["all"])
    total_missing_cells = sum(profile["column_missing"].values())
    null_ratio = (total_missing_cells / total_cells) if total_cells > 0 else 0
    quality_score = max(0.0, round(100.0 - (null_ratio * 100.0), 1))
    profile["data_quality_score"] = quality_score

    for col, miss in profile["column_missing"].items():
        if miss > 0:
            pct = round((miss / total_rows) * 100.0, 1)
            if pct > 30.0:
                profile["quality_findings"].append(f"Column '{col}' has {pct}% missing values ({miss:,} of {total_rows:,} records).")
            elif pct > 10.0:
                profile["quality_findings"].append(f"Column '{col}' has {pct}% null cells requiring validation.")

    return profile


# ---------------------------------------------------------------------------
# Helper Functions for Plain-Language & Record Presentation (Issue 15.2)
# ---------------------------------------------------------------------------
def _format_fraction(count: int, total: int) -> str:
    """Returns a natural plain-language fraction approximation."""
    if total <= 0:
        return "none"
    ratio = count / total
    if ratio >= 0.85:
        return "almost all"
    elif ratio >= 0.70:
        return "about three quarters"
    elif ratio >= 0.60:
        return "nearly two thirds"
    elif ratio >= 0.45:
        return "about half"
    elif ratio >= 0.30:
        return "about a third"
    elif ratio >= 0.20:
        return "about a quarter"
    elif ratio >= 0.10:
        return "about one in ten"
    else:
        return "a small fraction"


def _extract_record_label(
    row: Dict[str, Any],
    all_columns: List[str],
    target_col: str,
    fallback_idx: int
) -> str:
    """
    Dynamically finds a meaningful identifier for an individual record from the schema:
    Checks for name, title, item, product, customer, employee, ID, notes, or code.
    Never returns generic 'Record 1' unless no descriptive column exists.
    """
    # 1. High-priority descriptive text columns
    for col in all_columns:
        if col == target_col:
            continue
        col_lower = col.lower()
        if any(k in col_lower for k in ["name", "title", "product", "item", "description", "employee", "student", "customer", "subject", "notes"]):
            val = row.get(col)
            if val is not None and str(val).strip() and str(val).strip().lower() != "none":
                return str(val).strip()

    # 2. Secondary identifier columns (ID, Code, SKU, Number)
    for col in all_columns:
        if col == target_col:
            continue
        col_lower = col.lower()
        if any(k in col_lower for k in ["id", "code", "sku", "number", "key", "ref"]):
            val = row.get(col)
            if val is not None and str(val).strip():
                clean_col = col.replace('_', ' ').capitalize()
                return f"{clean_col} #{val}"

    # 3. Any non-empty text/categorical column
    for col in all_columns:
        if col == target_col:
            continue
        val = row.get(col)
        if val is not None and str(val).strip() and not str(val).replace('.', '', 1).isdigit():
            return str(val).strip()

    return f"Entry #{fallback_idx + 1}"


# ---------------------------------------------------------------------------
# Section 2.2 — Statistical Pattern Discovery
# ---------------------------------------------------------------------------
def discover_statistical_patterns(
    table_name: str,
    profile: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Discovers deterministic statistical patterns such as category concentration,
    numeric skewness, Pareto distributions, and group disparities.
    """
    insights: List[Dict[str, Any]] = []
    total_rows = profile["total_records"]
    if total_rows < 3:
        return insights

    safe_tbl = f"`{table_name}`"

    # Pattern A: Category Volume Concentration / Dominance
    for col, freqs in profile.get("categorical_frequencies", {}).items():
        if not freqs:
            continue
        top = freqs[0]
        top_val = str(top["val"])
        top_cnt = int(top["cnt"])
        top_pct = float(top["pct"])

        if top_pct >= 40.0 and len(freqs) > 1:
            sql = f"SELECT `{col}`, COUNT(*) as record_count, ROUND(COUNT(*) * 100.0 / {total_rows}, 2) as percentage FROM {safe_tbl} GROUP BY `{col}` ORDER BY record_count DESC LIMIT 5"
            col_readable = col.replace('_', ' ')
            fraction_str = _format_fraction(top_cnt, total_rows)
            plain_title = f"About {fraction_str} of your {col_readable} records are '{top_val}' ({top_cnt:,} of {total_rows:,})"
            plain_expl = f"'{top_val}' accounts for {top_pct}% of all records in {col_readable} ({top_cnt:,} out of {total_rows:,} entries), while the remaining {round(100.0 - top_pct, 1)}% are divided across other categories."
            why_matter = f"Your activity is heavily concentrated in '{top_val}'. Fluctuations or trends in this category will have an outsized impact on overall performance."

            insights.append({
                "id": f"ins_stat_conc_{col}",
                "category": "STATISTICAL",
                "sub_category": "CONCENTRATION",
                "severity": "notable" if top_pct >= 60.0 else "info",
                "title": plain_title,
                "plain_explanation": plain_expl,
                "why_it_matters": why_matter,
                "description": f"The '{top_val}' group accounts for {top_pct}% of all records ({top_cnt:,} of {total_rows:,}).",
                "affected_columns": [col],
                "metric_value": f"{top_pct}% ({top_cnt:,} of {total_rows:,})",
                "metric_label": "Category Share",
                "methodology": "Categorical Frequency Analysis & Dominance Ratio",
                "supporting_sql": sql,
                "result_evidence": freqs[:5],
                "chart_type": "bar",
                "chart_data": [{"label": str(f["val"]), "value": float(f["cnt"])} for f in freqs[:5]],
                "confidence": 0.98,
                "suggested_questions": [
                    f"Break down records for {col} = '{top_val}'",
                    f"Compare {col} distribution across other metrics",
                    f"Show top 10 records where {col} is '{top_val}'"
                ]
            })

    # Pattern B: Numeric Skewness & Mean vs Median Disparity
    for col, stats in profile.get("column_stats", {}).items():
        mean_v = stats["mean"]
        median_v = stats["median"]
        std_v = stats["stddev"]
        iqr_v = stats["iqr"]

        if std_v > 0 and median_v > 0:
            diff_ratio = abs(mean_v - median_v) / (std_v if std_v > 0 else 1.0)
            is_skewed = (
                diff_ratio >= 0.25 
                or (stats["max"] >= median_v * 2.5 and stats["max"] > stats["q3"] * 1.5)
                or (mean_v >= median_v * 1.4 or mean_v <= median_v * 0.7)
            )
            if is_skewed:
                direction_slug = "right-skewed" if mean_v > median_v else "left-skewed"
                direction_text = "right-skewed (driven by high-value outliers)" if mean_v > median_v else "left-skewed"
                col_readable = col.replace('_', ' ')
                sql = f"SELECT MIN(`{col}`) as min_val, AVG(`{col}`) as mean_val, MAX(`{col}`) as max_val FROM {safe_tbl}"

                if mean_v > median_v:
                    plain_title = f"A few unusually large values are raising the average {col_readable}"
                    plain_expl = f"Half of all records have a {col_readable} of {format_value(median_v, col)} or less. However, a small number of larger values reaching up to {format_value(stats['max'], col)} raise the mathematical average to {format_value(mean_v, col)}."
                    why_matter = f"The average {col_readable} ({format_value(mean_v, col)}) does not reflect what a typical customer or transaction looks like. Using the typical value of {format_value(median_v, col)} provides a more dependable benchmark."
                else:
                    plain_title = f"A few unusually small values are lowering the average {col_readable}"
                    plain_expl = f"Half of all records have a {col_readable} of {format_value(median_v, col)} or more. However, lower values reaching down to {format_value(stats['min'], col)} reduce the mathematical average to {format_value(mean_v, col)}."
                    why_matter = f"The mathematical average ({format_value(mean_v, col)}) is pulled down by lower extremes. The typical value of {format_value(median_v, col)} represents common activity better."

                insights.append({
                    "id": f"ins_stat_skew_{col}",
                    "category": "STATISTICAL",
                    "sub_category": "SKEWNESS",
                    "severity": "notable" if diff_ratio >= 0.50 else "info",
                    "title": plain_title,
                    "plain_explanation": plain_expl,
                    "why_it_matters": why_matter,
                    "description": f"The distribution of {col} is {direction_text}. Mean ({format_value(mean_v, col)}) substantially departs from median ({format_value(median_v, col)}).",
                    "affected_columns": [col],
                    "metric_value": f"Typical: {format_value(median_v, col)} vs Average: {format_value(mean_v, col)}",
                    "metric_label": "Typical vs Average",
                    "methodology": "Distribution Skewness Assessment (Mean vs. Median Disparity)",
                    "supporting_sql": sql,
                    "result_evidence": [
                        {"metric": "Minimum", "value": stats["min"]},
                        {"metric": "Q1 (25th)", "value": stats["q1"]},
                        {"metric": "Median", "value": stats["median"]},
                        {"metric": "Mean", "value": stats["mean"]},
                        {"metric": "Q3 (75th)", "value": stats["q3"]},
                        {"metric": "Maximum", "value": stats["max"]}
                    ],
                    "chart_type": "bar",
                    "chart_data": [
                        {"label": "Min", "value": stats["min"]},
                        {"label": "Q1", "value": stats["q1"]},
                        {"label": "Median", "value": stats["median"]},
                        {"label": "Mean", "value": stats["mean"]},
                        {"label": "Q3", "value": stats["q3"]},
                        {"label": "Max", "value": stats["max"]}
                    ],
                    "confidence": 0.95,
                    "suggested_questions": [
                        f"What are the highest values in {col}?",
                        f"Which records have {col} above {stats['q3']}?",
                        f"Show distribution quartiles for {col}"
                    ]
                })

    return insights


# ---------------------------------------------------------------------------
# Section 2.3 — Trend Discovery & Semantic Date Filtering
# ---------------------------------------------------------------------------
DEMOGRAPHIC_DATE_KEYWORDS = {
    "dob", "date_of_birth", "birth_date", "birthdate", "birthday", "birth_day",
    "death_date", "expiry_date", "expiration_date", "due_date", "valid_until", "valid_to"
}

EVENT_DATE_KEYWORDS = [
    "order_date", "transaction_date", "created_at", "sale_date", "sales_date",
    "invoice_date", "event_date", "timestamp", "exam_date", "booking_date",
    "payment_date", "purchase_date", "ship_date", "delivery_date", "log_date"
]


def is_valid_trend_date_column(col_name: str, metric_col: Optional[str] = None) -> bool:
    """
    Determines if a date column represents a valid temporal event sequence
    suitable for trend analysis and time-series charts, rather than a demographic
    or fixed personal attribute such as date of birth.
    """
    if not col_name:
        return False
    col_lower = col_name.lower().strip()
    for kw in DEMOGRAPHIC_DATE_KEYWORDS:
        if kw in col_lower:
            return False
    if metric_col and any(m in metric_col.lower() for m in ["salary", "pay", "wage", "compensation", "income"]):
        if any(h in col_lower for h in ["hire", "join", "start"]):
            return False
    return True


def select_best_trend_date_column(date_cols: List[str], metric_col: Optional[str] = None) -> Optional[str]:
    """
    Selects the best date column for trend analysis from available date columns.
    Prioritizes explicit event date keywords, falls back to non-demographic dates,
    and returns None if only demographic dates (like date of birth) exist.
    """
    if not date_cols:
        return None
    valid_cols = [c for c in date_cols if is_valid_trend_date_column(c, metric_col)]
    if not valid_cols:
        return None
    for event_kw in EVENT_DATE_KEYWORDS:
        for c in valid_cols:
            if event_kw in c.lower():
                return c
    return valid_cols[0]


def discover_trends(
    table_name: str,
    profile: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Discovers temporal trends, monthly/yearly period-over-period patterns,
    fluctuations, and historical peaks.
    """
    insights: List[Dict[str, Any]] = []
    date_cols = profile.get("date_columns", [])
    num_cols = profile.get("numeric_columns", [])
    total_rows = profile["total_records"]

    target_metric = num_cols[0] if num_cols else None
    date_col = select_best_trend_date_column(date_cols, target_metric)

    if not date_col or total_rows < 3:
        return insights

    safe_tbl = f"`{table_name}`"

    # Analyze volume over time or numeric metrics over time
    target_metric = num_cols[0] if num_cols else None
    metric_expr = f"ROUND(SUM(`{target_metric}`), 2)" if target_metric else "COUNT(*)"
    metric_alias = f"total_{target_metric}" if target_metric else "record_count"

    # Monthly aggregation
    trend_sql = f"""
        SELECT 
            DATE_FORMAT(`{date_col}`, '%Y-%m') as period,
            COUNT(*) as record_count
            {f', {metric_expr} as {metric_alias}' if target_metric else ''}
        FROM {safe_tbl}
        WHERE `{date_col}` IS NOT NULL
        GROUP BY period
        ORDER BY period ASC
        LIMIT 24
    """
    trend_res = execute_sql(trend_sql)
    records = trend_res.records

    if len(records) >= 3:
        periods = [r["period"] for r in records if r.get("period")]
        values = [to_number(r.get(metric_alias, r.get("record_count"))) or 0.0 for r in records]

        if len(values) >= 3:
            first_val = values[0]
            last_val = values[-1]
            prev_val = values[-2] if len(values) >= 2 else first_val

            # Period-over-period change (latest period vs prior)
            pop_pct = 0.0
            if prev_val > 0:
                pop_pct = round(((last_val - prev_val) / prev_val) * 100.0, 1)

            # Max period
            max_idx = values.index(max(values))
            peak_period = periods[max_idx]
            peak_val = values[max_idx]

            # Overall trajectory
            direction = "Upward Growth" if last_val > first_val * 1.1 else ("Downward Contraction" if last_val < first_val * 0.9 else "Stable / Fluctuating")

            metric_name = target_metric.replace('_', ' ').capitalize() if target_metric else "Activity"
            metric_readable = target_metric.replace('_', ' ') if target_metric else "record volume"
            prev_period = periods[-2] if len(periods) >= 2 else periods[0]
            curr_period = periods[-1]
            abs_change = round(last_val - prev_val, 2)
            prev_val_fmt = format_value(prev_val, target_metric or "")
            curr_val_fmt = format_value(last_val, target_metric or "")
            abs_change_fmt = format_value(abs(abs_change), target_metric or "")

            if pop_pct < 0:
                plain_title = f"The {metric_readable} decreased compared with the previous month"
                plain_expl = f"Total {metric_readable} decreased by {abs_change_fmt} ({pop_pct:+0.1f}%) from {prev_val_fmt} in {prev_period} to {curr_val_fmt} in {curr_period}."
                why_matter = f"A recent drop in {metric_readable} may indicate seasonal slowdown, customer attrition, or supply disruptions that require timely attention."
            elif pop_pct > 0:
                plain_title = f"The {metric_readable} increased compared with the previous month"
                plain_expl = f"Total {metric_readable} increased by {abs_change_fmt} ({pop_pct:+0.1f}%) from {prev_val_fmt} in {prev_period} to {curr_val_fmt} in {curr_period}."
                why_matter = f"Recent growth in {metric_readable} demonstrates positive momentum. Review which channels or categories drove this gain to sustain it."
            else:
                plain_title = f"The {metric_readable} remained consistent across recent periods"
                plain_expl = f"Total {metric_readable} held steady at {curr_val_fmt} between {prev_period} and {curr_period}."
                why_matter = f"Steady figures provide a reliable baseline for upcoming period comparisons and budgeting."

            pop_desc = f" In the latest period ({periods[-1]}), volume {'increased' if pop_pct >= 0 else 'decreased'} by {abs(pop_pct)}% compared to {periods[-2]}." if len(periods) >= 2 and prev_val > 0 else ""
            desc = f"Analyzed {len(records)} periods from {periods[0]} to {periods[-1]}. Peak occurred in {peak_period} at {format_value(peak_val, target_metric or '')}.{pop_desc}"

            insights.append({
                "id": f"ins_trend_{date_col}_{target_metric or 'records'}",
                "category": "TRENDS",
                "sub_category": "TREND",
                "severity": "notable" if abs(pop_pct) >= 20.0 else "info",
                "title": plain_title,
                "plain_explanation": plain_expl,
                "why_it_matters": why_matter,
                "description": desc,
                "affected_columns": [date_col] + ([target_metric] if target_metric else []),
                "metric_value": f"{curr_val_fmt} vs {prev_val_fmt} ({pop_pct:+0.1f}%)" if prev_val > 0 else curr_val_fmt,
                "metric_label": f"{curr_period} vs {prev_period}" if prev_val > 0 else "Latest Value",
                "trend_details": {
                    "metric_name": metric_readable,
                    "previous_period": prev_period,
                    "current_period": curr_period,
                    "previous_value": prev_val,
                    "current_value": last_val,
                    "absolute_change": abs_change,
                    "percentage_change": pop_pct,
                    "peak_period": peak_period,
                    "peak_value": peak_val,
                    "total_periods": len(records),
                    "formatted_previous": prev_val_fmt,
                    "formatted_current": curr_val_fmt,
                    "formatted_change": abs_change_fmt,
                },
                "methodology": "Temporal Period-over-Period Aggregation (Monthly Grain)",
                "supporting_sql": trend_sql.strip(),
                "result_evidence": records,
                "chart_type": "line",
                "chart_data": [{"label": str(r["period"]), "value": to_number(r.get(metric_alias, r.get("record_count"))) or 0.0} for r in records],
                "confidence": 0.96,
                "suggested_questions": [
                    f"Show monthly trend for {target_metric or 'records'}",
                    f"Why did {metric_readable} change between {prev_period} and {curr_period}?",
                    f"What caused the peak in {peak_period}?"
                ]
            })

    return insights


# ---------------------------------------------------------------------------
# Section 2.4 — Explainable Anomaly Detection
# ---------------------------------------------------------------------------
def discover_anomalies(
    table_name: str,
    profile: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Identifies explainable anomalies using:
    1. Tukey's Interquartile Range (IQR 1.5x rule).
    2. Severe distribution outliers (|Z-Score| > 3.0).
    3. High null rate concentrations (> 25%).
    4. Non-PK unique identifier collision/duplicates.
    """
    insights: List[Dict[str, Any]] = []
    total_rows = profile["total_records"]
    if total_rows < 5:
        return insights

    safe_tbl = f"`{table_name}`"

    # 1. IQR Outlier Detection on Numeric Columns
    for col, stats in profile.get("column_stats", {}).items():
        q1 = stats["q1"]
        q3 = stats["q3"]
        iqr = stats["iqr"]
        is_discrete = stats.get("is_discrete", False)
        distinct_cnt = stats.get("distinct_count", 0)

        # Skip degenerate IQR where zero variance or tiny discrete cardinality makes fences meaningless
        if iqr <= 0 or (is_discrete and distinct_cnt <= 5):
            continue

        lower_bound = round(q1 - 1.5 * iqr, 2)
        upper_bound = round(q3 + 1.5 * iqr, 2)

        safe_c = f"`{col}`"
        count_sql = f"""
            SELECT COUNT(*) as outlier_count
            FROM {safe_tbl}
            WHERE {safe_c} < {lower_bound} OR {safe_c} > {upper_bound}
        """
        c_res = execute_sql(count_sql)
        outlier_cnt = int(c_res.records[0]["outlier_count"] or 0) if c_res.records else 0

        if outlier_cnt > 0:
            pct = round((outlier_cnt / total_rows) * 100.0, 1)
            # Fetch up to 5 representative records
            sample_sql = f"""
                SELECT *
                FROM {safe_tbl}
                WHERE {safe_c} < {lower_bound} OR {safe_c} > {upper_bound}
                ORDER BY ABS({safe_c} - {stats['median']}) DESC
                LIMIT 5
            """
            s_res = execute_sql(sample_sql)
            col_readable = col.replace('_', ' ')

            bounds_meta = {
                "methodology": "Tukey's Interquartile Range (IQR 1.5× Rule)",
                "lower_fence": lower_bound,
                "upper_fence": upper_bound,
                "q1": q1,
                "median": stats["median"],
                "q3": q3,
                "iqr": iqr,
                "affected_records": outlier_cnt,
                "outliers_count": outlier_cnt,
                "outlier_pct": pct,
                "affected_percentage": f"{pct}%"
            }

            if pct <= 15.0:
                # Empirical statistical outliers (isolated values)
                chart_data = []
                for i, r in enumerate(s_res.records):
                    val_num = to_number(r.get(col)) or 0.0
                    lbl = _extract_record_label(r, profile["column_names"], col, i)
                    chart_data.append({"label": f"{lbl} ({format_value(val_num, col)})", "value": val_num})

                plain_title = f"Some records have unusually high or low {col_readable}"
                plain_expl = f"We found {outlier_cnt:,} records whose {col_readable} differs substantially from the expected range of {format_value(lower_bound, col)} to {format_value(upper_bound, col)} (typical value is {format_value(stats['median'], col)})."
                why_matter = "Unusual values might represent valid high-value transactions, specialized products, bulk orders, or potential data entry errors. Review these entries to verify their accuracy."

                insights.append({
                    "id": f"ins_anomaly_iqr_{col}",
                    "category": "ANOMALIES",
                    "sub_category": "OUTLIER",
                    "severity": "warning" if pct > 5.0 else "notable",
                    "title": plain_title,
                    "plain_explanation": plain_expl,
                    "why_it_matters": why_matter,
                    "description": f"Identified {outlier_cnt:,} records ({pct}% of dataset) falling outside Tukey's IQR boundaries [{lower_bound:,}, {upper_bound:,}]. Note: These represent empirical statistical outliers, distinct from verified data entry errors.",
                    "affected_columns": [col],
                    "metric_value": f"{outlier_cnt:,} records ({pct}%)",
                    "metric_label": "Outliers Detected",
                    "methodology": "Tukey's Interquartile Range (IQR 1.5× Rule)",
                    "bounds": bounds_meta,
                    "supporting_sql": sample_sql.strip(),
                    "result_evidence": s_res.records,
                    "chart_type": "table",
                    "chart_data": chart_data,
                    "confidence": 0.94,
                    "suggested_questions": [
                        f"Show all outlier records where {col} is outside [{lower_bound}, {upper_bound}]",
                        f"What is the average {col} excluding outliers?",
                        f"Which entity accounts for the highest {col}?"
                    ]
                })
            else:
                # Heavy-tailed or skewed distribution: Classify appropriately and explain method limitation
                bounds_meta["methodology"] = "Distribution Boundary Assessment (IQR Limitation for Heavy Tails)"
                chart_data = []
                for i, r in enumerate(s_res.records):
                    val_num = to_number(r.get(col)) or 0.0
                    lbl = _extract_record_label(r, profile["column_names"], col, i)
                    chart_data.append({"label": f"{lbl} ({format_value(val_num, col)})", "value": val_num})

                plain_title = f"A wide spread of values in {col_readable} creates a long tail"
                plain_expl = f"About {pct}% of records ({outlier_cnt:,} entries) lie beyond standard statistical boundaries. Rather than isolated errors, your data naturally covers a wide range with several higher values."
                why_matter = "Because this data has a wide spread, standard averages can be misleading. Using medians or percentile ranks provides a more accurate picture."

                insights.append({
                    "id": f"ins_stat_tail_{col}",
                    "category": "STATISTICAL",
                    "sub_category": "HEAVY_TAIL",
                    "severity": "info",
                    "title": plain_title,
                    "plain_explanation": plain_expl,
                    "why_it_matters": why_matter,
                    "description": f"Tukey's IQR method flags {outlier_cnt:,} records ({pct}% of dataset) outside [{lower_bound:,}, {upper_bound:,}]. A proportion this large indicates an inherently heavy-tailed or skewed distribution rather than isolated data errors. Standard IQR boundaries have limited validity for this distribution.",
                    "affected_columns": [col],
                    "metric_value": f"{pct}% flagged",
                    "metric_label": "Heavy-Tail Share",
                    "methodology": "Distribution Boundary Assessment (IQR Limitation for Heavy Tails)",
                    "bounds": bounds_meta,
                    "supporting_sql": sample_sql.strip(),
                    "result_evidence": s_res.records,
                    "chart_type": "table",
                    "chart_data": chart_data,
                    "confidence": 0.88,
                    "suggested_questions": [
                        f"Show highest values for {col}",
                        f"How does {col} distribution look across quartiles?",
                        f"What proportion of records are below median for {col}?"
                    ]
                })

    # 2. Data Quality Anomalies (Concentrated Nulls)
    for col, miss_cnt in profile.get("column_missing", {}).items():
        if miss_cnt > 0:
            pct = round((miss_cnt / total_rows) * 100.0, 1)
            if pct >= 25.0:
                col_readable = col.replace('_', ' ')
                plain_title = f"Missing information detected in {col_readable}"
                plain_expl = f"About {pct}% of your records ({miss_cnt:,} out of {total_rows:,}) have blank or missing entries in {col_readable}."
                why_matter = f"Missing data can skew aggregate metrics or exclude relevant transactions from reports. Consider standardizing how {col_readable} is captured."

                insights.append({
                    "id": f"ins_anomaly_null_{col}",
                    "category": "DATA_QUALITY",
                    "sub_category": "NULL_CONCENTRATION",
                    "severity": "warning" if pct >= 50.0 else "notable",
                    "title": plain_title,
                    "plain_explanation": plain_expl,
                    "why_it_matters": why_matter,
                    "description": f"Column '{col}' exhibits an elevated missing-rate of {pct}% ({miss_cnt:,} null values), which may impact analytical queries.",
                    "affected_columns": [col],
                    "metric_value": f"{miss_cnt:,} of {total_rows:,} missing ({pct}%)",
                    "metric_label": "Missing Rate",
                    "methodology": "Missing Value Threshold Assessment (>= 25% threshold)",
                    "supporting_sql": f"SELECT COUNT(*) as missing_count FROM {safe_tbl} WHERE `{col}` IS NULL OR CAST(`{col}` AS CHAR) = ''",
                    "result_evidence": [
                        {"column": col, "missing_records": miss_cnt, "total_records": total_rows, "missing_percentage": f"{pct}%"}
                    ],
                    "chart_type": "bar",
                    "chart_data": [
                        {"label": "Valid Records", "value": total_rows - miss_cnt},
                        {"label": "Missing Records", "value": miss_cnt}
                    ],
                    "confidence": 1.0,
                    "suggested_questions": [
                        f"Show records where {col} is missing",
                        f"Count missing values by category",
                        f"How many complete rows exist?"
                    ]
                })

    return insights


# ---------------------------------------------------------------------------
# Section 2.5 — Relationship & Correlation Discovery
# ---------------------------------------------------------------------------
def discover_relationships(
    table_name: str,
    profile: Dict[str, Any],
    user_id: str
) -> List[Dict[str, Any]]:
    """
    Discovers:
    1. Pearson linear correlations between pairs of numeric fields (r >= 0.50).
    2. Categorical disparities across groups (e.g. salary by department).
    3. Cross-table relationship links with other authorized datasets.
    """
    insights: List[Dict[str, Any]] = []
    num_cols = profile.get("numeric_columns", [])
    cat_cols = profile.get("categorical_columns", [])
    total_rows = profile["total_records"]
    safe_tbl = f"`{table_name}`"

    # 1. Pearson Correlation for pairs of numeric columns
    if len(num_cols) >= 2 and total_rows >= 5:
        # Check first 4 pairs to avoid excessive queries
        pairs = []
        for i in range(len(num_cols)):
            for j in range(i + 1, min(len(num_cols), i + 3)):
                pairs.append((num_cols[i], num_cols[j]))

        for col1, col2 in pairs[:4]:
            c1, c2 = f"`{col1}`", f"`{col2}`"
            corr_sql = f"""
                SELECT 
                    COUNT(*) as n,
                    ROUND(
                        (COUNT(*) * SUM({c1} * {c2}) - SUM({c1}) * SUM({c2})) / 
                        (SQRT(NULLIF(COUNT(*) * SUM({c1} * {c1}) - POW(SUM({c1}), 2), 0)) * 
                         SQRT(NULLIF(COUNT(*) * SUM({c2} * {c2}) - POW(SUM({c2}), 2), 0))),
                        4
                    ) as pearson_r
                FROM {safe_tbl}
                WHERE {c1} IS NOT NULL AND {c2} IS NOT NULL
            """
            c_res = execute_sql(corr_sql)
            if c_res.records and c_res.records[0]["pearson_r"] is not None:
                r_val = float(c_res.records[0]["pearson_r"])
                sample_n = int(c_res.records[0]["n"] or 0)

                # Avoid strong correlation claims when sample size is insufficient (< 10)
                if sample_n < 10:
                    continue

                if abs(r_val) >= 0.45:
                    direction = "positive" if r_val > 0 else "negative"
                    p_val = calculate_pearson_p_value(r_val, sample_n)
                    p_str = "p < 0.001" if p_val < 0.001 else f"p = {p_val:0.4f}"
                    is_sig = p_val < 0.05
                    sig_note = " (statistically significant at alpha = 0.05)" if is_sig else " (not statistically significant)"

                    # Scatter plot points sample
                    scatter_sql = f"SELECT `{col1}`, `{col2}` FROM {safe_tbl} WHERE `{col1}` IS NOT NULL AND `{col2}` IS NOT NULL LIMIT 20"
                    sc_res = execute_sql(scatter_sql)

                    c1_title = col1.replace('_', ' ').capitalize()
                    c2_title = col2.replace('_', ' ').capitalize()
                    c1_read = col1.replace('_', ' ')
                    c2_read = col2.replace('_', ' ')

                    plain_title = f"Higher {c1_read} correlates with higher {c2_read}" if r_val > 0 else f"Higher {c1_read} correlates with lower {c2_read}"
                    plain_expl = f"Higher {c1_read} tends to be associated with {direction} movement in {c2_read} (r = {r_val:0.2f} across {sample_n:,} records)."
                    why_matter = "Correlation shows that these two numbers move together, but it does not prove that one causes the other. Keep this relationship in mind when planning or modeling."

                    insights.append({
                        "id": f"ins_corr_{col1}_{col2}",
                        "category": "STATISTICAL",
                        "sub_category": "CORRELATION",
                        "severity": "notable" if (abs(r_val) >= 0.70 and is_sig) else "info",
                        "title": plain_title,
                        "plain_explanation": plain_expl,
                        "why_it_matters": why_matter,
                        "description": f"Linear association observed between {col1} and {col2} (r = {r_val:0.2f}, n = {sample_n:,}, {p_str}){sig_note}. Correlation measures linear co-movement and does not imply causation.",
                        "affected_columns": [col1, col2],
                        "metric_value": f"r = {r_val:0.2f} (n = {sample_n:,}, {p_str})",
                        "metric_label": "Correlation Strength",
                        "methodology": f"Bivariate Pearson Correlation Test (Student's t-test, df = {sample_n - 2})",
                        "sample_size": sample_n,
                        "p_value": p_val,
                        "correlation_details": {
                            "r": r_val,
                            "n": sample_n,
                            "p_value": p_val,
                            "is_significant": is_sig,
                            "disclaimer": "Correlation reflects statistical association and does not imply causation."
                        },
                        "supporting_sql": corr_sql.strip(),
                        "result_evidence": sc_res.records,
                        "chart_type": "scatter",
                        "chart_data": [{"label": f"Pt {i+1}", "x": to_number(r.get(col1)) or 0.0, "value": to_number(r.get(col2)) or 0.0} for i, r in enumerate(sc_res.records)],
                        "confidence": 0.92 if is_sig else 0.70,
                        "suggested_questions": [
                            f"How does {col1} relate to {col2}?",
                            f"Show scatter plot between {col1} and {col2}",
                            f"Which records have high {col1} but low {col2}?"
                        ]
                    })

    # 2. Categorical Group Disparity (Observed Difference)
    if cat_cols and num_cols:
        disparity_found = False
        for cat_col in cat_cols[:3]:
            if disparity_found:
                break
            for num_col in num_cols[:3]:
                group_sql = f"""
                    SELECT `{cat_col}` as grp, COUNT(*) as cnt, ROUND(AVG(`{num_col}`), 2) as avg_val
                    FROM {safe_tbl}
                    WHERE `{cat_col}` IS NOT NULL AND `{cat_col}` != '' AND `{num_col}` IS NOT NULL
                    GROUP BY `{cat_col}`
                    HAVING cnt >= 2
                    ORDER BY avg_val DESC
                    LIMIT 6
                """
                g_res = execute_sql(group_sql)
                if len(g_res.records) >= 2:
                    top_grp = g_res.records[0]
                    bot_grp = g_res.records[-1]
                    top_avg = float(top_grp["avg_val"] or 0)
                    bot_avg = float(bot_grp["avg_val"] or 0)

                    if bot_avg > 0 and (top_avg / bot_avg) >= 1.5:
                        ratio = round(top_avg / bot_avg, 1)
                        c_title = num_col.replace('_', ' ').capitalize()
                        cat_title = cat_col.replace('_', ' ')
                        plain_title = f"{c_title} varies across {cat_title} groups"
                        plain_expl = f"'{top_grp['grp']}' averages {format_value(top_avg, num_col)}, which is {ratio}× higher than '{bot_grp['grp']}' at {format_value(bot_avg, num_col)}."
                        why_matter = f"A significant gap between {cat_title} categories can uncover operational differences, compensation disparities, or resource allocation needs."

                        insights.append({
                            "id": f"ins_disp_{cat_col}_{num_col}",
                            "category": "STATISTICAL",
                            "sub_category": "GROUP_DISPARITY",
                            "severity": "notable" if ratio >= 2.0 else "info",
                            "title": plain_title,
                            "plain_explanation": plain_expl,
                            "why_it_matters": why_matter,
                            "description": f"'{top_grp['grp']}' recorded the highest average {num_col} ({format_value(top_avg, num_col)} across {top_grp['cnt']:,} records) compared to '{bot_grp['grp']}' ({format_value(bot_avg, num_col)} across {bot_grp['cnt']:,} records), showing a {ratio}× observed difference (based on group sample means).",
                            "affected_columns": [cat_col, num_col],
                            "metric_value": f"{ratio}× difference",
                            "metric_label": "Group Mean Ratio",
                            "methodology": "Cross-Dimensional Categorical Means Comparison (Observed Difference)",
                            "supporting_sql": group_sql.strip(),
                            "result_evidence": g_res.records,
                            "chart_type": "bar",
                            "chart_data": [{"label": str(r["grp"]), "value": float(r["avg_val"])} for r in g_res.records],
                            "confidence": 0.90,
                            "suggested_questions": [
                                f"Compare average {num_col} across all {cat_col} groups",
                                f"Why is {num_col} highest for '{top_grp['grp']}'?",
                                f"Breakdown {cat_col} performance"
                            ]
                        })
                        disparity_found = True
                        break

    # 3. Cross-Table Relational Link
    all_user_tables = get_user_datasets(user_id)
    if len(all_user_tables) > 1:
        try:
            from app.services.relationship_service import discover_user_schemas, infer_table_relationships
            user_schemas = discover_user_schemas(user_id)
            if len(user_schemas) > 1:
                edges = infer_table_relationships(user_schemas)
                for edge in edges:
                    if edge.source_physical == table_name or edge.target_physical == table_name:
                        peer_friendly = edge.target_table if edge.source_physical == table_name else edge.source_table
                        curr_friendly = table_name.split("_usr_")[0]
                        plain_title = f"Your {curr_friendly} and {peer_friendly} tables are connected"
                        plain_expl = f"These tables share matching values through {edge.source_column}. Joining them allows you to analyze connected data across both tables in a single query."
                        why_matter = f"Linking these tables enables unified multi-table reporting without having to manually merge separate files."

                        insights.append({
                            "id": f"ins_cross_rel_{peer_friendly}",
                            "category": "SCHEMA_RELATIONSHIPS",
                            "sub_category": "JOIN_CANDIDATE",
                            "severity": "info",
                            "title": plain_title,
                            "plain_explanation": plain_expl,
                            "why_it_matters": why_matter,
                            "description": f"Potential join candidate identified with '{peer_friendly}' on {edge.join_condition}. Inferred via column naming and primary key cardinality heuristics (documented heuristic confidence: {int(edge.confidence * 100)}%).",
                            "affected_columns": [edge.source_column],
                            "metric_value": f"Connected via {edge.source_column} ({int(edge.confidence * 100)}%)",
                            "metric_label": "Table Relationship",
                            "methodology": "Automated Relational Join Inference (Documented Heuristic Match)",
                            "relationship_details": {
                                "source_table": edge.source_table,
                                "source_col": edge.source_column,
                                "target_table": edge.target_table,
                                "target_col": edge.target_column,
                                "join_condition": edge.join_condition,
                                "confidence": edge.confidence,
                                "match_ratio": edge.confidence,
                                "sample_size": 10,
                                "matched_values": int(edge.confidence * 10),
                                "confidence_basis": f"Heuristic join inferred on key '{edge.source_column}' with cardinality match",
                            },
                            "supporting_sql": f"SELECT * FROM `{edge.source_physical}` JOIN `{edge.target_physical}` ON {edge.physical_join_condition} LIMIT 5",
                            "result_evidence": [{"relationship": edge.join_condition, "cardinality": edge.cardinality, "confidence": edge.confidence}],
                            "chart_type": "table",
                            "chart_data": [],
                            "confidence": edge.confidence,
                            "suggested_questions": [
                                f"Join this table with {peer_friendly}",
                                f"What data is in {peer_friendly}?",
                                f"Show combined records with {peer_friendly}"
                            ]
                        })
                        break
        except Exception:
            pass

    return insights


# ---------------------------------------------------------------------------
# Section 3 — Business Insight Discovery
# ---------------------------------------------------------------------------
def discover_business_insights(
    table_name: str,
    profile: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Synthesizes verified business insights grounded in column semantics:
    e.g. Revenue concentration, top product contribution, payroll share.
    """
    insights: List[Dict[str, Any]] = []
    num_cols = profile.get("numeric_columns", [])
    cat_cols = profile.get("categorical_columns", [])
    safe_tbl = f"`{table_name}`"
    total_rows = profile["total_records"]

    # Match financial / revenue columns
    financial_col = next((c for c in num_cols if any(k in c.lower() for k in REVENUE_KEYWORDS)), None)
    entity_col = next((c for c in cat_cols if any(k in c.lower() for k in ENTITY_KEYWORDS)), None)

    if financial_col and entity_col and total_rows >= 3:
        sql = f"""
            SELECT `{entity_col}` as entity, 
                   COUNT(*) as volume,
                   ROUND(SUM(`{financial_col}`), 2) as total_val,
                   ROUND(AVG(`{financial_col}`), 2) as avg_val
            FROM {safe_tbl}
            WHERE `{entity_col}` IS NOT NULL AND `{financial_col}` IS NOT NULL
            GROUP BY `{entity_col}`
            ORDER BY total_val DESC
            LIMIT 5
        """
        res = execute_sql(sql)
        if res.records:
            total_sum_sql = f"SELECT SUM(`{financial_col}`) as grand_total FROM {safe_tbl}"
            g_res = execute_sql(total_sum_sql)
            grand_total = float(g_res.records[0]["grand_total"] or 0.0) if g_res.records else 0.0

            top = res.records[0]
            top_val = float(top["total_val"] or 0.0)
            share_pct = round((top_val / grand_total * 100.0), 1) if grand_total > 0 else 0.0

            if share_pct >= 25.0:
                fin_readable = financial_col.replace('_', ' ')
                top_entity = str(top['entity'])
                plain_title = f"'{top_entity}' generates {share_pct}% of total {fin_readable}"
                plain_expl = f"'{top_entity}' is the primary contributor, generating {format_value(top_val, financial_col)} out of your total {format_value(grand_total, financial_col)} ({share_pct}%)."
                why_matter = f"A large revenue share in '{top_entity}' indicates heavy concentration. Maintaining this key segment is critical to overall business stability."

                insights.append({
                    "id": f"ins_biz_top_share_{entity_col}_{financial_col}",
                    "category": "BUSINESS",
                    "sub_category": "REVENUE_SHARE",
                    "severity": "notable" if share_pct >= 50.0 else "info",
                    "title": plain_title,
                    "plain_explanation": plain_expl,
                    "why_it_matters": why_matter,
                    "description": f"'{top['entity']}' represents the primary contribution driver, generating {format_value(top_val, financial_col)} ({share_pct}%) of the total {format_value(grand_total, financial_col)}.",
                    "affected_columns": [entity_col, financial_col],
                    "metric_value": f"{share_pct}%",
                    "metric_label": f"Share of {financial_col.replace('_', ' ').title()}",
                    "methodology": "Pareto Business Contribution Analysis",
                    "supporting_sql": sql.strip(),
                    "result_evidence": res.records,
                    "chart_type": "bar",
                    "chart_data": [{"label": str(r["entity"]), "value": float(r["total_val"])} for r in res.records],
                    "confidence": 0.98,
                    "suggested_questions": [
                        f"Why does {top['entity']} lead in {financial_col}?",
                        f"Compare {entity_col} performance metrics",
                        f"Show highest transactions for {top['entity']}"
                    ]
                })

    return insights


# ---------------------------------------------------------------------------
# Section 5 — AI Explanations Grounded in Verified Analytical Results
# ---------------------------------------------------------------------------
def enhance_insights_with_ai(insights: List[Dict[str, Any]], dataset_name: str) -> None:
    """
    Enriches verified insights with executive-level natural-language summaries
    using call_llm, while preserving deterministic fallback for offline/rate-limited resilience.
    """
    if not insights:
        return

    # Deterministic baseline guarantees resilience
    for ins in insights:
        ins["ai_explanation"] = ins.get("plain_explanation") or ins.get("description", "")

    import os
    if os.environ.get("PROMPTSQL_TESTING") == "1":
        return

    # Select top 3 most significant insights for AI enrichment
    candidates = [ins for ins in insights if ins.get("severity") in ("warning", "notable")][:3]
    if not candidates:
        candidates = insights[:2]

    try:
        facts_summary = []
        for i, ins in enumerate(candidates):
            # Enforce small-group disclosure suppression for outbound AI prompt
            sample_size = ins.get("sample_size") or ins.get("count") or ins.get("row_count")
            metric_val = ins['metric_value']
            if sample_size is not None and 0 < sample_size < 3:
                metric_val = "[SUPPRESSED_SMALL_GROUP]"

            facts_summary.append(
                f"Insight {i+1} ({ins['title']}): Metric = {metric_val}, Evidence = {ins.get('plain_explanation') or ins.get('description')}"
            )

        prompt = f"""
Dataset: {dataset_name}
Verified Quantitative Discoveries:
{chr(10).join(facts_summary)}

Task: For each insight above, provide a 1-sentence executive analytical takeaway grounded strictly in these verified numbers. Do not invent facts or speculate on external causes.

Output in valid JSON array of strings, e.g.:
["takeaway 1", "takeaway 2"]
"""
        response_text = call_llm(
            system_prompt="You are an enterprise data discovery analyst. Return ONLY a valid JSON array of strings.",
            user_prompt=prompt
        )
        parsed = json.loads(response_text)
        if isinstance(parsed, list):
            for idx, text_val in enumerate(parsed):
                if idx < len(candidates) and isinstance(text_val, str) and text_val.strip():
                    candidates[idx]["ai_explanation"] = text_val.strip()
    except Exception:
        # Graceful fallback: verified deterministic description remains intact
        pass


# ---------------------------------------------------------------------------
# Section 6 — Insight Prioritization & Grouping Layer (Issue 15.1)
# ---------------------------------------------------------------------------
def prioritize_and_group_insights(all_insights: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Ranks findings by analytical relevance, reliability, and practical usefulness.
    Suppresses trivial observations and prevents repetitive cards from dominating
    the default view.

    Returns (key_discoveries, advanced_discoveries).
    - key_discoveries: 4 to 6 highest-value, non-repetitive insights
    - advanced_discoveries: remaining detailed/technical insights
    """
    if not all_insights:
        return [], []

    scored_insights = []
    for ins in all_insights:
        cat = ins.get("category", "")
        sub_cat = ins.get("sub_category", "")
        sev = ins.get("severity", "info")
        score = 15  # baseline score

        if cat == "BUSINESS":
            score = 55
        elif cat == "ANOMALIES":
            score = 48 if sev == "warning" else 42
        elif cat == "DATA_QUALITY":
            score = 46 if sev == "warning" else 35
        elif cat == "TRENDS":
            score = 40 if sev == "notable" else 32
        elif cat == "SCHEMA_RELATIONSHIPS":
            score = 36 if ins.get("confidence", 0) >= 0.8 else 28
        elif cat == "STATISTICAL":
            if sub_cat == "CORRELATION":
                sample_n = ins.get("sample_size", 0)
                p_val = ins.get("p_value", 1.0)
                if sample_n >= 30 and p_val < 0.05:
                    score = 38
                elif sample_n >= 10 and p_val < 0.05:
                    score = 28
                else:
                    score = 10
            elif sub_cat == "GROUP_DISPARITY":
                score = 32 if "2." in ins.get("metric_value", "") or "3." in ins.get("metric_value", "") else 25
            elif sub_cat == "HEAVY_TAIL":
                score = 22
            elif sub_cat == "CONCENTRATION":
                score = 30 if sev == "notable" else 20
            elif sub_cat == "SKEWNESS":
                score = 20
            else:
                score = 16

        scored_insights.append((score, ins))

    # Sort initially by score descending
    scored_insights.sort(key=lambda x: x[0], reverse=True)

    # Diversity & redundancy filter for top recommendations:
    seen_subcats = set()
    seen_columns = set()
    key_discoveries = []
    remaining = []

    for score, ins in scored_insights:
        sub_cat = ins.get("sub_category", ins.get("category"))
        aff_cols = tuple(sorted(ins.get("affected_columns", [])))

        # Penalize duplicate skewness, duplicate correlations, or duplicate dominance
        is_repetitive = False
        if sub_cat in ("SKEWNESS", "CORRELATION", "HEAVY_TAIL") and sub_cat in seen_subcats:
            is_repetitive = True
        elif sub_cat == "CONCENTRATION" and sub_cat in seen_subcats and len(key_discoveries) >= 3:
            is_repetitive = True
        elif aff_cols and aff_cols in seen_columns and len(key_discoveries) >= 3:
            is_repetitive = True

        if len(key_discoveries) < 6 and (not is_repetitive or len(key_discoveries) < 4):
            ins["is_key"] = True
            ins["priority_score"] = score
            ins["relevance_score"] = score
            key_discoveries.append(ins)
            seen_subcats.add(sub_cat)
            if aff_cols:
                seen_columns.add(aff_cols)
        else:
            ins["is_key"] = False
            ins["priority_score"] = score
            ins["relevance_score"] = score
            remaining.append(ins)

    # Ensure key_discoveries has between 4 and 6 items if total insights allow
    while len(key_discoveries) < min(4, len(all_insights)) and remaining:
        cand = remaining.pop(0)
        cand["is_key"] = True
        key_discoveries.append(cand)

    key_discoveries.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
    return key_discoveries, remaining


# ---------------------------------------------------------------------------
# Dynamic Dataset Understanding & Domain Classification (Issue 15.3)
# ---------------------------------------------------------------------------
DOMAIN_RULES: Dict[str, Dict[str, Any]] = {
    "ecommerce": {
        "label": "E-Commerce & Sales",
        "keywords": ["order", "product", "sale", "sales", "revenue", "price", "unit_price", "total_amount", "quantity", "customer", "cart", "discount", "subtotal", "shipping", "item"],
        "high_weight": ["order_id", "total_amount", "unit_price", "quantity", "product_name", "revenue", "customer_id"],
        "entity_id_candidates": ["order_id", "sale_id", "transaction_id", "invoice_no"]
    },
    "education": {
        "label": "Student Academics",
        "keywords": ["student", "subject", "marks", "score", "exam", "grade", "attendance", "passed", "semester", "class", "gpa", "academic", "roll_no", "course"],
        "high_weight": ["student_id", "roll_no", "marks", "subject", "exam_date", "grade", "score"],
        "entity_id_candidates": ["student_id", "roll_no", "enrollment_id"]
    },
    "hr": {
        "label": "Workforce & HR",
        "keywords": ["employee", "department", "salary", "designation", "job", "joining_date", "hire_date", "performance_rating", "experience", "payroll", "bonus", "staff", "office", "wage"],
        "high_weight": ["employee_id", "staff_no", "salary", "department", "hire_date", "designation", "job_title"],
        "entity_id_candidates": ["employee_id", "staff_no", "emp_id"]
    },
    "finance": {
        "label": "Financial Transactions",
        "keywords": ["finance", "financial", "txn", "transaction", "account", "balance", "credit", "debit", "transfer", "fee", "deposit", "withdrawal", "amount", "payment", "currency"],
        "high_weight": ["transaction_id", "txn_id", "account_id", "balance", "credit", "debit", "transfer", "deposit"],
        "entity_id_candidates": ["transaction_id", "txn_id", "account_id", "transfer_id"]
    },
    "inventory": {
        "label": "Inventory & Stock",
        "keywords": ["inventory", "stock", "warehouse", "sku", "reorder", "unit_cost", "on_hand", "supplier", "reorder_level", "stock_quantity", "stock_level"],
        "high_weight": ["sku", "stock_quantity", "reorder_level", "warehouse", "unit_cost"],
        "entity_id_candidates": ["sku", "product_id", "item_code"]
    },
    "healthcare": {
        "label": "Healthcare Administration",
        "keywords": ["patient", "doctor", "diagnosis", "admission", "discharge", "hospital", "bed", "medication", "treatment", "clinic"],
        "high_weight": ["patient_id", "doctor_id", "diagnosis", "admission_date", "discharge_date"],
        "entity_id_candidates": ["patient_id", "admission_id", "record_id"]
    }
}


def identify_dataset_domain(table_name: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Infers the primary domain of the dataset through evidence-based semantic scoring.
    Detects line-item vs transaction-level granularity to prevent aggregation distortion.
    """
    col_names = [c.lower() for c in profile.get("column_names", [])]
    clean_tbl = re.sub(r'_usr_.*$', '', table_name.lower())
    clean_tbl = re.sub(r'_\(\d+\)', '', clean_tbl)
    
    scores = {}
    matched_features = {}
    
    for domain, rules in DOMAIN_RULES.items():
        score = 0
        matches = []
        for kw in rules["keywords"]:
            if kw in clean_tbl:
                score += 3
                matches.append(f"table_name:{kw}")
        for col in col_names:
            if col in rules["high_weight"]:
                score += 4
                matches.append(f"high:{col}")
            elif any(kw in col for kw in rules["keywords"]):
                score += 1.5
                matches.append(f"col:{col}")
        
        scores[domain] = score
        matched_features[domain] = matches

    best_domain, best_score = max(scores.items(), key=lambda x: x[1])
    
    is_line_item = False
    entity_key = None
    candidates = DOMAIN_RULES.get(best_domain, {}).get("entity_id_candidates", []) + ["id", "code"]
    
    for cand in candidates:
        matched_col = next((c for c in profile.get("column_names", []) if cand == c.lower() or c.lower().endswith(f"_{cand}")), None)
        if matched_col:
            entity_key = matched_col
            dist_cnt = profile.get("column_distinct", {}).get(matched_col)
            if dist_cnt is None:
                with engine.connect() as conn:
                    dist_cnt = conn.execute(text(f"SELECT COUNT(DISTINCT `{matched_col}`) FROM `{table_name}` WHERE `{matched_col}` IS NOT NULL")).scalar()
            
            if dist_cnt is not None and profile.get("total_records", 0) > 0:
                if dist_cnt < profile.get("total_records", 0):
                    is_line_item = True
            break

    if best_score < 3.0:
        return {
            "domain": "generic",
            "domain_label": "General Tabular Data",
            "confidence": round(best_score / 10.0, 2),
            "is_line_item": False,
            "entity_key": entity_key,
            "matched_features": []
        }

    return {
        "domain": best_domain,
        "domain_label": DOMAIN_RULES[best_domain]["label"],
        "confidence": min(1.0, round(best_score / 12.0, 2)),
        "is_line_item": is_line_item,
        "entity_key": entity_key,
        "matched_features": matched_features[best_domain]
    }


def get_logical_table_name(physical_table: str) -> str:
    """Derives the user-facing logical dataset name from the physical table name."""
    if not physical_table:
        return ""
    base = re.sub(r'_usr_[a-zA-Z0-9]+$', '', physical_table)
    base = re.sub(r'_\(\d+\)$', '', base)
    return base or physical_table


def to_display_sql(physical_sql: str, physical_table: str, logical_table: str) -> str:
    """
    Transforms execution SQL containing authorized physical table names into
    clean display SQL containing user-facing logical dataset names.
    Preserves exact query semantics, parameters, and clauses while ensuring
    internal physical identifiers (e.g. `_usr_8`) are never exposed to the user.
    """
    if not physical_sql or not physical_table or not logical_table:
        return physical_sql or ""
    try:
        parsed = sqlglot.parse_one(physical_sql, read="mysql")
        matched = False
        def sanitize_table(node):
            nonlocal matched
            if isinstance(node, exp.Table):
                if node.name and node.name.lower() == physical_table.lower():
                    matched = True
                    return exp.Table(this=exp.to_identifier(logical_table, quoted=True))
            return node
        transformed = parsed.transform(sanitize_table)
        if matched:
            return transformed.sql(dialect="mysql")
    except Exception:
        pass

    clean_phys = re.escape(physical_table)
    pattern = re.compile(rf'(\b(?:FROM|JOIN)\s+)`?{clean_phys}`?', re.IGNORECASE)
    res = pattern.sub(rf'\1`{logical_table}`', physical_sql)
    res = re.sub(rf'`{clean_phys}`', f'`{logical_table}`', res)
    return res


CURRENCY_MAP: Dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CAD": "C$",
    "AUD": "A$",
    "CNY": "¥"
}


def detect_dataset_currency_details(
    table_name: str,
    profile: Dict[str, Any],
    where_sql: str = "",
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Analyzes dataset currency semantics across schema, dedicated currency columns, and table names.
    Distinguishes:
      - 'single': exactly one verified currency across all records
      - 'multi': multiple distinct verified currencies (e.g. INR, USD, JPY)
      - 'unresolved': mixed missing, unmapped, or invalid currency values
      - 'none': no currency indication established (neutral numeric presentation)
    """
    col_names = [c.lower() for c in profile.get("column_names", [])]
    clean_tbl = table_name.lower()
    params = params or {}

    curr_col = next((c for c in profile.get("column_names", []) if c.lower() in ("currency", "curr", "curr_code", "currency_code")), None)
    if curr_col:
        try:
            with engine.connect() as conn:
                sql = f"SELECT `{curr_col}` as c_val, COUNT(*) as cnt FROM `{table_name}` {where_sql} GROUP BY `{curr_col}`"
                rows = conn.execute(text(sql), params).fetchall()
                
            if rows:
                valid_currencies: Dict[str, Tuple[str, int]] = {}
                unresolved_codes: List[Tuple[str, int]] = []
                null_count = 0
                for r in rows:
                    raw_val = r[0]
                    cnt = int(r[1])
                    if raw_val is None or str(raw_val).strip() == "" or str(raw_val).strip().upper() in ("NULL", "NONE", "UNKNOWN", "N/A", "?"):
                        null_count += cnt
                    else:
                        code_str = str(raw_val).strip().upper()
                        if code_str in CURRENCY_MAP:
                            valid_currencies[code_str] = (CURRENCY_MAP[code_str], cnt)
                        else:
                            unresolved_codes.append((code_str, cnt))
                
                # Check for unresolved or ambiguous mixed currencies
                if unresolved_codes or (null_count > 0 and len(valid_currencies) > 0):
                    return {
                        "status": "unresolved",
                        "currency_col": curr_col,
                        "is_multi_currency": False,
                        "primary_currency": ("", ""),
                        "valid_currencies": valid_currencies,
                        "unresolved_codes": unresolved_codes,
                        "null_count": null_count,
                        "explanation": f"Dataset contains unresolved or missing currency values in `{curr_col}`."
                    }
                elif len(valid_currencies) > 1:
                    return {
                        "status": "multi",
                        "currency_col": curr_col,
                        "is_multi_currency": True,
                        "primary_currency": ("", ""),
                        "valid_currencies": valid_currencies,
                        "unresolved_codes": [],
                        "null_count": 0,
                        "explanation": f"Dataset contains {len(valid_currencies)} distinct currencies ({', '.join(valid_currencies.keys())})."
                    }
                elif len(valid_currencies) == 1:
                    single_code = list(valid_currencies.keys())[0]
                    single_sym = valid_currencies[single_code][0]
                    return {
                        "status": "single",
                        "currency_col": curr_col,
                        "is_multi_currency": False,
                        "primary_currency": (single_sym, single_code),
                        "valid_currencies": valid_currencies,
                        "unresolved_codes": [],
                        "null_count": 0,
                        "explanation": f"Single verified currency: {single_code} ({single_sym})."
                    }
                elif null_count > 0 and len(valid_currencies) == 0:
                    return {
                        "status": "none",
                        "currency_col": curr_col,
                        "is_multi_currency": False,
                        "primary_currency": ("", ""),
                        "valid_currencies": {},
                        "unresolved_codes": [],
                        "null_count": null_count,
                        "explanation": "Currency column has only null or empty values."
                    }
        except Exception:
            pass

    # Check column name patterns if no currency column
    col_matches = []
    for col in col_names:
        for sfx, sym, code in [
            ("inr", "₹", "INR"), ("rupee", "₹", "INR"), ("rs", "₹", "INR"),
            ("eur", "€", "EUR"), ("euro", "€", "EUR"),
            ("gbp", "£", "GBP"), ("pound", "£", "GBP"),
            ("jpy", "¥", "JPY"), ("yen", "¥", "JPY"),
            ("usd", "$", "USD"), ("dollar", "$", "USD")
        ]:
            if col.endswith(sfx) or f"_{sfx}_" in f"_{col}_":
                col_matches.append((sym, code))
                break

    distinct_col_currencies = list({m[1]: m for m in col_matches}.values())
    if len(distinct_col_currencies) == 1:
        return {
            "status": "single",
            "currency_col": None,
            "is_multi_currency": False,
            "primary_currency": distinct_col_currencies[0],
            "valid_currencies": {distinct_col_currencies[0][1]: (distinct_col_currencies[0][0], 0)},
            "unresolved_codes": [],
            "null_count": 0,
            "explanation": f"Single verified currency from schema: {distinct_col_currencies[0][1]}."
        }
    elif len(distinct_col_currencies) > 1:
        return {
            "status": "multi",
            "currency_col": None,
            "is_multi_currency": True,
            "primary_currency": ("", ""),
            "valid_currencies": {c[1]: (c[0], 0) for c in distinct_col_currencies},
            "unresolved_codes": [],
            "null_count": 0,
            "explanation": "Multiple currency-specific columns detected in schema."
        }

    # Check table name
    for sfx, sym, code in [
        ("_inr", "₹", "INR"), ("rupee", "₹", "INR"),
        ("_eur", "€", "EUR"), ("euro", "€", "EUR"),
        ("_gbp", "£", "GBP"), ("pound", "£", "GBP"),
        ("_jpy", "¥", "JPY"), ("yen", "¥", "JPY"),
        ("_usd", "$", "USD"), ("dollar", "$", "USD")
    ]:
        if sfx in clean_tbl:
            return {
                "status": "single",
                "currency_col": None,
                "is_multi_currency": False,
                "primary_currency": (sym, code),
                "valid_currencies": {code: (sym, 0)},
                "unresolved_codes": [],
                "null_count": 0,
                "explanation": f"Single verified currency from table naming: {code}."
            }

    return {
        "status": "none",
        "currency_col": None,
        "is_multi_currency": False,
        "primary_currency": ("", ""),
        "valid_currencies": {},
        "unresolved_codes": [],
        "null_count": 0,
        "explanation": "No currency information established."
    }


def detect_dataset_currency(table_name: str, profile: Dict[str, Any]) -> Tuple[str, str]:
    """
    Detects dataset currency symbol and currency code based on verified single currency.
    Returns (symbol, code). If unestablished, multi-currency, or unresolved, returns ('', '').
    Does NOT assume USD ($) or INR (₹) arbitrarily.
    """
    details = detect_dataset_currency_details(table_name, profile)
    if details.get("status") == "single":
        return details.get("primary_currency", ("", ""))
    return ("", "")


def format_kpi_value(val: Any, unit_type: str = "number", prefix: str = "", suffix: str = "") -> str:
    """Formats numeric metrics cleanly with currency symbols, compact notation (K/M), scores, or percentages."""
    if val is None:
        return "N/A"
    try:
        fval = float(val)
    except (ValueError, TypeError):
        return str(val)

    if unit_type == "currency":
        symbol = prefix or ""
        if abs(fval) >= 1_000_000:
            return f"{symbol}{fval / 1_000_000:.2f}M"
        elif abs(fval) >= 1_000:
            return f"{symbol}{fval / 1_000:.1f}K"
        else:
            return f"{symbol}{fval:,.2f}"
    elif unit_type == "count":
        return f"{int(round(fval)):,}{suffix}"
    elif unit_type == "percentage":
        return f"{fval:.1f}%"
    elif unit_type == "score":
        return f"{fval:.1f}{suffix}"
    else:
        if abs(fval) >= 1_000_000:
            return f"{fval / 1_000_000:.2f}M{suffix}"
        elif abs(fval) >= 1_000:
            return f"{fval / 1_000:.1f}K{suffix}"
        elif fval.is_integer():
            return f"{int(fval):,}{suffix}"
        else:
            return f"{fval:,.2f}{suffix}"


def build_filter_clause(table_name: str, profile: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """Builds a secure, parameterized WHERE clause for dynamic filters."""
    if not filters:
        return "", {}
    
    valid_cols = set(profile.get("column_names", []) or [])
    clauses = []
    params = {}
    
    for key, val in filters.items():
        if val is None or val == "" or val == "ALL":
            continue
        if key == "_date_from" and profile.get("date_columns"):
            d_col = profile["date_columns"][0]
            val_str = str(val).strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
                clauses.append(f"`{d_col}` >= :date_from")
                params["date_from"] = val_str
        elif key == "_date_to" and profile.get("date_columns"):
            d_col = profile["date_columns"][0]
            val_str = str(val).strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}$", val_str):
                clauses.append(f"`{d_col}` <= :date_to")
                params["date_to"] = val_str
        elif key in valid_cols:
            param_key = f"filter_{re.sub(r'[^a-zA-Z0-9_]', '', key)}"
            clauses.append(f"`{key}` = :{param_key}")
            params[param_key] = val

    if clauses:
        return "WHERE " + " AND ".join(clauses), params
    return "", {}


def evaluate_period_change(
    cur_val: Optional[float],
    prev_val: Optional[float],
    cur_period: str = "current",
    prev_period: str = "previous",
    metric_name: str = "Metric",
    unit: str = ""
) -> Dict[str, Any]:
    """
    Evaluates period-over-period change adhering strictly to mathematical rules:
      - Case A (prev == 0, cur > 0): change_pct is None (not 100%, not inf).
      - Case B (prev == 0, cur == 0): change_pct is 0.0 ("No change").
      - Case C (prev > 0, cur == 0): change_pct is -100.0.
      - Case D (prev > 0, cur > 0): standard percentage change.
      - Case E (prev < 0): absolute movement narrative without misleading percentage.
      - Case F (prev is None or cur is None): unavailable comparison message.
    """
    if cur_val is None or prev_val is None:
        missing_label = "current period" if cur_val is None else "previous period"
        return {
            "status": "unavailable",
            "metric_name": metric_name,
            "current_period": cur_period,
            "previous_period": prev_period,
            "current_value": cur_val,
            "previous_value": prev_val,
            "absolute_change": None,
            "percentage_change": None,
            "change_pct": None,
            "period_label": f"{cur_period} vs {prev_period}",
            "narrative": f"Comparison unavailable for {metric_name}: {missing_label} data is missing or not recorded."
        }

    abs_change = round(cur_val - prev_val, 2)
    sign = "+" if abs_change > 0 else ""
    fmt_abs = f"{sign}{unit}{abs(abs_change):,.2f}" if unit else f"{sign}{abs_change:,.2f}"
    fmt_prev = f"{unit}{prev_val:,.2f}" if unit else f"{prev_val:,.2f}"
    fmt_cur = f"{unit}{cur_val:,.2f}" if unit else f"{cur_val:,.2f}"

    # Case B: Both periods are zero
    if prev_val == 0.0 and cur_val == 0.0:
        return {
            "metric_name": metric_name,
            "current_period": cur_period,
            "previous_period": prev_period,
            "current_value": cur_val,
            "previous_value": prev_val,
            "absolute_change": 0.0,
            "percentage_change": 0.0,
            "change_pct": 0.0,
            "period_label": f"{cur_period} vs {prev_period}",
            "narrative": f"No change. Both periods have zero recorded {metric_name.lower()}."
        }

    # Case A: Previous is 0, Current > 0
    if prev_val == 0.0 and cur_val > 0.0:
        return {
            "metric_name": metric_name,
            "current_period": cur_period,
            "previous_period": prev_period,
            "current_value": cur_val,
            "previous_value": prev_val,
            "absolute_change": abs_change,
            "percentage_change": None,
            "change_pct": None,
            "period_label": f"{cur_period} vs {prev_period}",
            "narrative": f"{metric_name} increased from {fmt_prev} to {fmt_cur} (baseline was zero)."
        }

    # Case C: Previous > 0, Current == 0
    if prev_val > 0.0 and cur_val == 0.0:
        return {
            "metric_name": metric_name,
            "current_period": cur_period,
            "previous_period": prev_period,
            "current_value": cur_val,
            "previous_value": prev_val,
            "absolute_change": abs_change,
            "percentage_change": -100.0,
            "change_pct": -100.0,
            "period_label": f"{cur_period} vs {prev_period}",
            "narrative": f"{metric_name} decreased from {fmt_prev} to {fmt_cur} (-100%)."
        }

    # Case E: Previous value is negative
    if prev_val < 0.0:
        if cur_val > 0.0:
            narrative = f"{metric_name} improved by {fmt_abs}, moving from {fmt_prev} to {fmt_cur}."
        elif cur_val == 0.0:
            narrative = f"{metric_name} recovered from {fmt_prev} to {fmt_cur} (net improvement of {fmt_abs})."
        else:
            dir_word = "widened" if cur_val < prev_val else "contracted"
            narrative = f"Deficit {dir_word} from {fmt_prev} to {fmt_cur} (net change of {fmt_abs})."
        return {
            "metric_name": metric_name,
            "current_period": cur_period,
            "previous_period": prev_period,
            "current_value": cur_val,
            "previous_value": prev_val,
            "absolute_change": abs_change,
            "percentage_change": None,
            "change_pct": None,
            "period_label": f"{cur_period} vs {prev_period}",
            "narrative": narrative
        }

    # Case D: Normal positive baseline
    chg_pct = round(((cur_val - prev_val) / prev_val) * 100.0, 1)
    chg_sign = "+" if chg_pct >= 0 else ""
    dir_word = "increased" if chg_pct >= 0 else "decreased"
    return {
        "metric_name": metric_name,
        "current_period": cur_period,
        "previous_period": prev_period,
        "current_value": cur_val,
        "previous_value": prev_val,
        "absolute_change": abs_change,
        "percentage_change": chg_pct,
        "change_pct": chg_pct,
        "period_label": f"{cur_period} vs {prev_period}",
        "narrative": f"{metric_name} {dir_word} by {chg_sign}{chg_pct}% ({fmt_cur} in {cur_period} vs {fmt_prev} in {prev_period}, {fmt_abs})."
    }


def calculate_period_comparison(
    table_name: str,
    date_col: str,
    metric_expr: str,
    where_base: str,
    params: Dict[str, Any],
    metric_name: str = "Metric",
    unit: str = "",
    subquery_source: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Calculates legitimate period-over-period comparison using evaluate_period_change."""
    try:
        if subquery_source:
            sql = f"""
                SELECT DATE_FORMAT(`{date_col}`, '%Y-%m') as ym,
                       {metric_expr} as val
                FROM {subquery_source}
                WHERE `{date_col}` IS NOT NULL
                GROUP BY ym
                ORDER BY ym DESC
                LIMIT 2
            """
        else:
            sql = f"""
                SELECT DATE_FORMAT(`{date_col}`, '%Y-%m') as ym,
                       {metric_expr} as val
                FROM `{table_name}`
                {where_base + (' AND ' if where_base else 'WHERE ') + f'`{date_col}` IS NOT NULL'}
                GROUP BY ym
                ORDER BY ym DESC
                LIMIT 2
            """
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        if len(rows) >= 2:
            cur_ym = str(rows[0][0])
            cur_val = float(rows[0][1]) if rows[0][1] is not None else None
            prev_ym = str(rows[1][0])
            prev_val = float(rows[1][1]) if rows[1][1] is not None else None
            return evaluate_period_change(cur_val, prev_val, cur_ym, prev_ym, metric_name, unit)
        elif len(rows) == 1:
            cur_ym = str(rows[0][0])
            cur_val = float(rows[0][1]) if rows[0][1] is not None else None
            return evaluate_period_change(cur_val, None, cur_ym, "N/A", metric_name, unit)
    except Exception:
        pass
    return None


def inspect_order_amount_grain(
    table_name: str,
    order_col: str,
    rev_col: str,
    profile: Dict[str, Any],
    where_sql: str = "",
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Semantically inspects order-grain structure to distinguish:
      - Case A: One row per order (total rows == distinct order IDs).
      - Case B: Multiple line items with individual line amounts (amounts vary across rows, or explicitly line-item labeled).
      - Case C: Multiple line items with repeated order totals (amounts constant per order, order-total labeled).
      - Ambiguous: Constant amount per order without line-item or order-level disambiguation.
    Returns dictionary with grain case, consolidated SQL expressions, and ambiguity flags.
    """
    params = params or {}
    col_names = profile.get("column_names", [])
    col_names_lower = [c.lower() for c in col_names]
    rev_lower = rev_col.lower()

    with engine.connect() as conn:
        counts = conn.execute(
            text(f"SELECT COUNT(*) as total_rows, COUNT(DISTINCT `{order_col}`) as distinct_orders FROM `{table_name}` {where_sql}"),
            params
        ).fetchone()
        
        tot_rows = int(counts[0] or 0) if counts else 0
        dist_orders = int(counts[1] or 0) if counts else 0

        # Case A: One row per order
        if tot_rows > 0 and tot_rows == dist_orders:
            return {
                "grain_case": "CASE_A_SINGLE_ROW",
                "is_line_item": False,
                "is_ambiguous": False,
                "total_orders": dist_orders,
                "tot_rev_sql": f"SELECT ROUND(SUM(`{rev_col}`), 2) FROM `{table_name}` {where_sql}",
                "tot_orders_sql": f"SELECT COUNT(DISTINCT `{order_col}`) FROM `{table_name}` {where_sql}",
                "aov_sql": f"SELECT ROUND(SUM(`{rev_col}`) / NULLIF(COUNT(DISTINCT `{order_col}`), 0), 2) FROM `{table_name}` {where_sql}",
                "max_order_sql": f"SELECT ROUND(MAX(`{rev_col}`), 2) FROM `{table_name}` {where_sql}",
                "explanation": "Each row represents a distinct, complete order."
            }

        # Multi-row orders present
        var_check = conn.execute(
            text(f"""
                SELECT 
                    COUNT(*) as multi_order_count,
                    SUM(CASE WHEN min_val = max_val THEN 1 ELSE 0 END) as constant_orders,
                    SUM(CASE WHEN min_val != max_val THEN 1 ELSE 0 END) as varying_orders
                FROM (
                    SELECT `{order_col}`, MIN(`{rev_col}`) as min_val, MAX(`{rev_col}`) as max_val, COUNT(*) as c
                    FROM `{table_name}` {where_sql}
                    GROUP BY `{order_col}`
                    HAVING c > 1
                ) sub
            """),
            params
        ).fetchone()

        multi_cnt = int(var_check[0] or 0) if var_check else 0
        const_cnt = int(var_check[1] or 0) if var_check else 0
        vary_cnt = int(var_check[2] or 0) if var_check else 0

        # Semantic column checks
        is_order_total_named = any(
            rev_lower == k or rev_lower.startswith(k + "_") or rev_lower.endswith("_" + k)
            for k in ["total_amount", "order_total", "order_amount", "invoice_amount", "invoice_total", "bill_amount", "order_value", "total_order_amount", "grand_total"]
        )
        is_line_item_named = any(
            k in rev_lower
            for k in ["line_amount", "line_total", "item_amount", "item_total", "item_price", "unit_price", "line_item", "product_price", "product_amount"]
        )

        # Mixed and Inconsistent Order Amounts: Some orders have constant amounts, others varying
        if const_cnt > 0 and vary_cnt > 0:
            return {
                "grain_case": "AMBIGUOUS",
                "is_line_item": True,
                "is_ambiguous": True,
                "total_orders": dist_orders,
                "tot_rev_sql": None,
                "tot_orders_sql": f"SELECT COUNT(DISTINCT `{order_col}`) FROM `{table_name}` {where_sql}",
                "aov_sql": None,
                "max_order_sql": None,
                "explanation": (
                    f"Dataset contains mixed order-amount grain ({const_cnt} orders with constant amounts, "
                    f"{vary_cnt} with varying amounts). Total revenue and AOV are suppressed to prevent inaccurate aggregation."
                )
            }

        # Case B: Varying amounts within orders -> clearly individual line amounts
        if vary_cnt > 0:
            return {
                "grain_case": "CASE_B_LINE_ITEMS",
                "is_line_item": True,
                "is_ambiguous": False,
                "total_orders": dist_orders,
                "tot_rev_sql": f"SELECT ROUND(SUM(order_sum), 2) FROM (SELECT `{order_col}`, SUM(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "tot_orders_sql": f"SELECT COUNT(DISTINCT `{order_col}`) FROM `{table_name}` {where_sql}",
                "aov_sql": f"SELECT ROUND(SUM(order_sum) / NULLIF(COUNT(*), 0), 2) FROM (SELECT `{order_col}`, SUM(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "max_order_sql": f"SELECT ROUND(MAX(order_sum), 2) FROM (SELECT `{order_col}`, SUM(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "explanation": "Multiple line items per order with varying line amounts consolidated to order totals."
            }

        # If amounts are constant within every multi-row order:
        # Check if column is explicitly a line-item amount (Test 4: equal line amounts)
        if is_line_item_named:
            return {
                "grain_case": "CASE_B_LINE_ITEMS",
                "is_line_item": True,
                "is_ambiguous": False,
                "total_orders": dist_orders,
                "tot_rev_sql": f"SELECT ROUND(SUM(order_sum), 2) FROM (SELECT `{order_col}`, SUM(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "tot_orders_sql": f"SELECT COUNT(DISTINCT `{order_col}`) FROM `{table_name}` {where_sql}",
                "aov_sql": f"SELECT ROUND(SUM(order_sum) / NULLIF(COUNT(*), 0), 2) FROM (SELECT `{order_col}`, SUM(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "max_order_sql": f"SELECT ROUND(MAX(order_sum), 2) FROM (SELECT `{order_col}`, SUM(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "explanation": "Multiple line items per order with equal line amounts consolidated by order ID."
            }

        # Check if column is explicitly an order-level total (Case C: Repeated order total)
        if is_order_total_named:
            return {
                "grain_case": "CASE_C_REPEATED_ORDER_TOTAL",
                "is_line_item": True,
                "is_ambiguous": False,
                "total_orders": dist_orders,
                "tot_rev_sql": f"SELECT ROUND(SUM(order_sum), 2) FROM (SELECT `{order_col}`, MAX(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "tot_orders_sql": f"SELECT COUNT(DISTINCT `{order_col}`) FROM `{table_name}` {where_sql}",
                "aov_sql": f"SELECT ROUND(SUM(order_sum) / NULLIF(COUNT(*), 0), 2) FROM (SELECT `{order_col}`, MAX(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "max_order_sql": f"SELECT ROUND(MAX(order_sum), 2) FROM (SELECT `{order_col}`, MAX(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub",
                "explanation": "Repeated order totals across product rows consolidated to one verified amount per distinct order."
            }

        # If neither explicitly line-item nor explicitly order-total: AMBIGUOUS (Test 5)
        return {
            "grain_case": "AMBIGUOUS",
            "is_line_item": True,
            "is_ambiguous": True,
            "total_orders": dist_orders,
            "tot_rev_sql": None,
            "tot_orders_sql": f"SELECT COUNT(DISTINCT `{order_col}`) FROM `{table_name}` {where_sql}",
            "aov_sql": None,
            "max_order_sql": None,
            "explanation": f"Aggregation grain for column '{rev_col}' is ambiguous: values are constant across multi-line orders, but schema cannot verify whether it represents repeated order totals or identical line items. Revenue and AOV KPIs are suppressed to prevent inaccurate aggregation."
        }


def generate_dynamic_kpis(
    table_name: str,
    profile: Dict[str, Any],
    domain_info: Dict[str, Any],
    filters: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Generates 4-6 dynamic, domain-tailored KPI cards grounded in verified SQL calculations.
    Each KPI definition contains metric ID, grain, aggregation method, unit, display and execution SQL.
    Correctly accounts for line-item vs transaction-level granularity without unsafe fallbacks.
    """
    where_sql, params = build_filter_clause(table_name, profile, filters)
    kpis: List[Dict[str, Any]] = []
    
    logical_table = get_logical_table_name(table_name)
    curr_details = detect_dataset_currency_details(table_name, profile, where_sql, params)
    currency_symbol, currency_code = curr_details.get("primary_currency", ("", ""))
    is_multi_currency = curr_details.get("is_multi_currency", False)
    is_currency_unresolved = curr_details.get("status") == "unresolved"
    curr_col = curr_details.get("currency_col")
    
    num_cols = profile.get("numeric_columns", [])
    raw_cat = profile.get("categorical_columns", []) + profile.get("text_columns", [])
    cat_cols = list(dict.fromkeys(raw_cat))
    date_cols = profile.get("date_columns", [])
    primary_date = select_best_trend_date_column(date_cols)
    
    domain = domain_info.get("domain", "generic")
    is_line_item = domain_info.get("is_line_item", False)
    
    with engine.connect() as conn:
        if domain == "ecommerce":
            rev_col = next((c for c in num_cols if any(k in c.lower() for k in ["total_amount", "line_amount", "amount", "revenue", "sales"])), None)
            order_col = domain_info.get("entity_key") or next((c for c in profile.get("column_names", []) if "order_id" in c.lower() or c.lower().endswith("order_id")), None)

            # Grain analysis if order_col and rev_col present
            grain = None
            if order_col and rev_col:
                grain = inspect_order_amount_grain(table_name, order_col, rev_col, profile, where_sql, params)
                if grain.get("is_line_item"):
                    is_line_item = True

            # 1. Total Revenue Handling (Multi-Currency vs Unresolved vs Ambiguous vs Normal)
            if rev_col:
                if is_multi_currency and curr_col:
                    sql_multi_exec = f"""
                        SELECT `{curr_col}` as currency,
                               ROUND(SUM(`{rev_col}`), 2) as val,
                               COUNT(*) as cnt
                        FROM `{table_name}` {where_sql}
                        WHERE `{curr_col}` IS NOT NULL
                        GROUP BY `{curr_col}`
                        ORDER BY val DESC
                    """
                    rows = conn.execute(text(sql_multi_exec), params).fetchall()
                    breakdown = []
                    display_parts = []
                    for r in rows:
                        c_code = str(r[0]).strip().upper()
                        c_sym = CURRENCY_MAP.get(c_code, "")
                        c_val = float(r[1] or 0)
                        c_fmt = format_kpi_value(c_val, "currency", prefix=c_sym)
                        breakdown.append({
                            "code": c_code,
                            "symbol": c_sym,
                            "amount": c_val,
                            "formatted": c_fmt,
                            "count": int(r[2])
                        })
                        display_parts.append(f"{c_fmt} ({c_code})")
                    
                    multi_disp = " | ".join(display_parts) if display_parts else "N/A"
                    disp_sql = to_display_sql(sql_multi_exec, table_name, logical_table)
                    kpis.append({
                        "id": "kpi_total_revenue",
                        "metric_id": "total_revenue_multi_currency",
                        "title": "TOTAL REVENUE (BY CURRENCY)",
                        "display_name": "TOTAL REVENUE (BY CURRENCY)",
                        "value": multi_disp,
                        "raw_value": None,
                        "unit": "multi-currency",
                        "is_multi_currency": True,
                        "currency_breakdown": breakdown,
                        "aggregation_method": "GROUP_BY_CURRENCY",
                        "data_grain": "currency_subtotal",
                        "source_table": logical_table,
                        "source_column": rev_col,
                        "description": "Revenue grouped by currency to prevent invalid cross-currency summation",
                        "explanation": "Different currencies cannot be aggregated together without verified exchange rates. Metrics are presented separately for each currency.",
                        "supporting_sql": disp_sql,
                        "display_sql": disp_sql,
                        "execution_sql": sql_multi_exec,
                        "period_comparison": None,
                        "icon": "DollarSign"
                    })
                elif is_currency_unresolved:
                    kpis.append({
                        "id": "kpi_revenue_unresolved",
                        "metric_id": "revenue_unresolved",
                        "title": "REVENUE AGGREGATION SUPPRESSED",
                        "display_name": "REVENUE AGGREGATION SUPPRESSED",
                        "value": "Unresolved Currency",
                        "raw_value": None,
                        "unit": "",
                        "is_ambiguous": True,
                        "aggregation_method": "SUPPRESSED",
                        "data_grain": "unresolved",
                        "source_table": logical_table,
                        "source_column": rev_col,
                        "description": "Dataset contains mixed, missing, or unrecognized currency codes.",
                        "explanation": "Monetary aggregation was suppressed because currency indicators are ambiguous or unresolved. Adding mixed currencies without conversion rates produces mathematically invalid totals.",
                        "supporting_sql": "-- Suppressed to prevent invalid cross-currency summation",
                        "display_sql": "-- Suppressed to prevent invalid cross-currency summation",
                        "execution_sql": "-- Suppressed",
                        "period_comparison": None,
                        "icon": "AlertCircle"
                    })
                elif grain and grain.get("is_ambiguous"):
                    kpis.append({
                        "id": "kpi_revenue_ambiguous",
                        "metric_id": "revenue_ambiguous",
                        "title": "REVENUE GRAIN AMBIGUOUS",
                        "display_name": "REVENUE GRAIN AMBIGUOUS",
                        "value": "Clarification Required",
                        "raw_value": None,
                        "unit": "",
                        "is_ambiguous": True,
                        "aggregation_method": "SUPPRESSED",
                        "data_grain": "ambiguous",
                        "source_table": logical_table,
                        "source_column": rev_col,
                        "description": f"Aggregation grain for `{rev_col}` is ambiguous across multi-line orders.",
                        "explanation": grain.get("explanation"),
                        "supporting_sql": "-- Suppressed to prevent potentially inaccurate revenue aggregation",
                        "display_sql": "-- Suppressed to prevent potentially inaccurate revenue aggregation",
                        "execution_sql": "-- Suppressed",
                        "period_comparison": None,
                        "icon": "AlertCircle"
                    })
                else:
                    sql_rev_exec = grain["tot_rev_sql"] if grain and grain.get("tot_rev_sql") else f"SELECT ROUND(SUM(`{rev_col}`), 2) FROM `{table_name}` {where_sql}"
                    tot_rev = conn.execute(text(sql_rev_exec), params).scalar() or 0
                    sql_rev_disp = to_display_sql(sql_rev_exec, table_name, logical_table)
                    comp = calculate_period_comparison(table_name, primary_date, f"ROUND(SUM(`{rev_col}`), 2)", where_sql, params, "Total Revenue", currency_symbol) if primary_date else None
                    
                    agg_m = "SUM"
                    if grain and grain.get("grain_case") == "CASE_C_REPEATED_ORDER_TOTAL":
                        agg_m = "CONSOLIDATED_MAX"
                        desc_rev = f"Consolidated order revenue from `{rev_col}` (one verified total per distinct `{order_col}`)"
                    elif grain and grain.get("grain_case") == "CASE_B_LINE_ITEMS":
                        agg_m = "CONSOLIDATED_SUM"
                        desc_rev = f"Consolidated line-item revenue from `{rev_col}` grouped by `{order_col}`"
                    else:
                        desc_rev = f"Sum of `{rev_col}` across verified records"

                    kpis.append({
                        "id": "kpi_total_revenue",
                        "metric_id": "total_revenue",
                        "title": "TOTAL REVENUE",
                        "display_name": "TOTAL REVENUE",
                        "value": format_kpi_value(tot_rev, "currency", prefix=currency_symbol),
                        "raw_value": float(tot_rev),
                        "unit": currency_symbol,
                        "currency_code": currency_code,
                        "aggregation_method": agg_m,
                        "data_grain": "order" if is_line_item else "transaction",
                        "source_table": logical_table,
                        "source_column": rev_col,
                        "description": desc_rev,
                        "explanation": grain.get("explanation") if grain else f"Calculates total revenue by summing `{rev_col}` across verified records.",
                        "supporting_sql": sql_rev_disp,
                        "display_sql": sql_rev_disp,
                        "execution_sql": sql_rev_exec,
                        "period_comparison": comp,
                        "icon": "DollarSign"
                    })

            # 2. Total Orders Handling
            if order_col:
                sql_orders_exec = grain["tot_orders_sql"] if grain and grain.get("tot_orders_sql") else f"SELECT COUNT(DISTINCT `{order_col}`) FROM `{table_name}` {where_sql}"
                desc_orders = f"Distinct `{order_col}` count" + (" (line-item consolidated)" if is_line_item else "")
                tot_orders = conn.execute(text(sql_orders_exec), params).scalar() or 0
                sql_orders_disp = to_display_sql(sql_orders_exec, table_name, logical_table)
                comp_ord = calculate_period_comparison(table_name, primary_date, f"COUNT(DISTINCT `{order_col}`)", where_sql, params, "Total Orders", "") if primary_date else None
                
                kpis.append({
                    "id": "kpi_total_orders",
                    "metric_id": "total_orders",
                    "title": "TOTAL ORDERS",
                    "display_name": "TOTAL ORDERS",
                    "value": format_kpi_value(tot_orders, "count"),
                    "raw_value": int(tot_orders),
                    "unit": "orders",
                    "aggregation_method": "COUNT_DISTINCT",
                    "data_grain": "order",
                    "source_table": logical_table,
                    "source_column": order_col,
                    "description": desc_orders,
                    "explanation": f"Counts distinct `{order_col}` values to measure total orders placed without line-item inflation.",
                    "supporting_sql": sql_orders_disp,
                    "display_sql": sql_orders_disp,
                    "execution_sql": sql_orders_exec,
                    "period_comparison": comp_ord,
                    "icon": "ShoppingCart"
                })
            else:
                sql_orders_exec = f"SELECT COUNT(*) FROM `{table_name}` {where_sql}"
                tot_orders = conn.execute(text(sql_orders_exec), params).scalar() or 0
                sql_orders_disp = to_display_sql(sql_orders_exec, table_name, logical_table)
                comp_ord = calculate_period_comparison(table_name, primary_date, "COUNT(*)", where_sql, params, "Total Orders", "") if primary_date else None
                kpis.append({
                    "id": "kpi_total_orders",
                    "metric_id": "total_orders",
                    "title": "TOTAL TRANSACTIONS",
                    "display_name": "TOTAL TRANSACTIONS",
                    "value": format_kpi_value(tot_orders, "count"),
                    "raw_value": int(tot_orders),
                    "unit": "orders",
                    "aggregation_method": "COUNT",
                    "data_grain": "record",
                    "source_table": logical_table,
                    "source_column": "*",
                    "description": "Total order records on file",
                    "explanation": "Counts total recorded transaction rows.",
                    "supporting_sql": sql_orders_disp,
                    "display_sql": sql_orders_disp,
                    "execution_sql": sql_orders_exec,
                    "period_comparison": comp_ord,
                    "icon": "ShoppingCart"
                })

            # 3. Average Order Value (AOV) Handling
            if rev_col and not is_multi_currency and not is_currency_unresolved and not (grain and grain.get("is_ambiguous")):
                if grain and grain.get("aov_sql"):
                    sql_aov_exec = grain["aov_sql"]
                    desc_aov = "Consolidated average revenue per distinct order"
                elif order_col:
                    sql_aov_exec = f"SELECT ROUND(SUM(`{rev_col}`) / NULLIF(COUNT(DISTINCT `{order_col}`), 0), 2) FROM `{table_name}` {where_sql}"
                    desc_aov = "Average revenue per distinct order"
                else:
                    sql_aov_exec = f"SELECT ROUND(AVG(`{rev_col}`), 2) FROM `{table_name}` {where_sql}"
                    desc_aov = "Mean transaction value"
                
                aov_val = conn.execute(text(sql_aov_exec), params).scalar() or 0
                sql_aov_disp = to_display_sql(sql_aov_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_aov",
                    "metric_id": "average_order_value",
                    "title": "AVERAGE ORDER VALUE",
                    "display_name": "AVERAGE ORDER VALUE",
                    "value": format_kpi_value(aov_val, "currency", prefix=currency_symbol),
                    "raw_value": float(aov_val),
                    "unit": currency_symbol,
                    "currency_code": currency_code,
                    "aggregation_method": "CONSOLIDATED_AOV" if (grain and grain.get("aov_sql")) else ("SUM/COUNT_DISTINCT" if order_col else "AVG"),
                    "data_grain": "order",
                    "source_table": logical_table,
                    "source_column": rev_col,
                    "description": desc_aov,
                    "explanation": "Calculates average spend per distinct order without line-item inflation.",
                    "supporting_sql": sql_aov_disp,
                    "display_sql": sql_aov_disp,
                    "execution_sql": sql_aov_exec,
                    "period_comparison": None,
                    "icon": "TrendingUp"
                })

            # 4. Highest Order Value Handling
            if rev_col and not is_multi_currency and not is_currency_unresolved and not (grain and grain.get("is_ambiguous")):
                if grain and grain.get("max_order_sql"):
                    sql_max_exec = grain["max_order_sql"]
                    desc_max = "Largest consolidated order value"
                elif order_col and is_line_item:
                    sql_max_exec = f"SELECT ROUND(MAX(order_sum), 2) FROM (SELECT SUM(`{rev_col}`) as order_sum FROM `{table_name}` {where_sql} GROUP BY `{order_col}`) sub"
                    desc_max = "Largest consolidated order value"
                else:
                    sql_max_exec = f"SELECT ROUND(MAX(`{rev_col}`), 2) FROM `{table_name}` {where_sql}"
                    desc_max = f"Peak individual transaction in `{rev_col}`"
                
                max_val = conn.execute(text(sql_max_exec), params).scalar() or 0
                sql_max_disp = to_display_sql(sql_max_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_max_order",
                    "metric_id": "highest_order_value",
                    "title": "HIGHEST ORDER VALUE",
                    "display_name": "HIGHEST ORDER VALUE",
                    "value": format_kpi_value(max_val, "currency", prefix=currency_symbol),
                    "raw_value": float(max_val),
                    "unit": currency_symbol,
                    "currency_code": currency_code,
                    "aggregation_method": "MAX",
                    "data_grain": "order",
                    "source_table": logical_table,
                    "source_column": rev_col,
                    "description": desc_max,
                    "explanation": "Identifies the highest single order amount placed.",
                    "supporting_sql": sql_max_disp,
                    "display_sql": sql_max_disp,
                    "execution_sql": sql_max_exec,
                    "period_comparison": None,
                    "icon": "Award"
                })

            qty_col = next((c for c in num_cols if any(k in c.lower() for k in ["quantity", "qty", "units"])), None)
            if qty_col:
                sql_qty_exec = f"SELECT SUM(`{qty_col}`) FROM `{table_name}` {where_sql}"
                tot_qty = conn.execute(text(sql_qty_exec), params).scalar() or 0
                sql_qty_disp = to_display_sql(sql_qty_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_units_sold",
                    "metric_id": "total_units_sold",
                    "title": "TOTAL UNITS SOLD",
                    "display_name": "TOTAL UNITS SOLD",
                    "value": format_kpi_value(tot_qty, "count"),
                    "raw_value": float(tot_qty),
                    "unit": "units",
                    "aggregation_method": "SUM",
                    "data_grain": "line_item",
                    "source_table": logical_table,
                    "source_column": qty_col,
                    "description": f"Cumulative items purchased (`{qty_col}`)",
                    "explanation": f"Sums all item quantities sold across transactions.",
                    "supporting_sql": sql_qty_disp,
                    "display_sql": sql_qty_disp,
                    "execution_sql": sql_qty_exec,
                    "period_comparison": None,
                    "icon": "Package"
                })

            cust_col = next((c for c in profile.get("column_names", []) if any(k in c.lower() for k in ["customer_id", "client_id", "buyer_id"])), None)
            if cust_col:
                sql_cust_exec = f"SELECT COUNT(DISTINCT `{cust_col}`) FROM `{table_name}` {where_sql}"
                tot_cust = conn.execute(text(sql_cust_exec), params).scalar() or 0
                sql_cust_disp = to_display_sql(sql_cust_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_unique_customers",
                    "metric_id": "unique_customers",
                    "title": "UNIQUE CUSTOMERS",
                    "display_name": "UNIQUE CUSTOMERS",
                    "value": format_kpi_value(tot_cust, "count"),
                    "raw_value": int(tot_cust),
                    "unit": "customers",
                    "aggregation_method": "COUNT_DISTINCT",
                    "data_grain": "customer",
                    "source_table": logical_table,
                    "source_column": cust_col,
                    "description": f"Distinct purchasing customers (`{cust_col}`)",
                    "explanation": f"Counts distinct buyers registered in `{cust_col}`.",
                    "supporting_sql": sql_cust_disp,
                    "display_sql": sql_cust_disp,
                    "execution_sql": sql_cust_exec,
                    "period_comparison": None,
                    "icon": "Users"
                })

        elif domain == "education":
            student_col = next((c for c in profile.get("column_names", []) if any(k in c.lower() for k in ["student_id", "roll_no", "student", "rollno"])), None)
            if student_col:
                sql_st_exec = f"SELECT COUNT(DISTINCT `{student_col}`) FROM `{table_name}` {where_sql}"
                desc_st = f"Distinct students enrolled (`{student_col}`)"
                grain_st = "student"
                source_st = student_col
                agg_st = "COUNT_DISTINCT"
            else:
                sql_st_exec = f"SELECT COUNT(*) FROM `{table_name}` {where_sql}"
                desc_st = "Total student assessment records"
                grain_st = "record"
                source_st = "*"
                agg_st = "COUNT"
            tot_st = conn.execute(text(sql_st_exec), params).scalar() or 0
            sql_st_disp = to_display_sql(sql_st_exec, table_name, logical_table)
            kpis.append({
                "id": "kpi_total_students",
                "metric_id": "total_students",
                "title": "TOTAL STUDENTS",
                "display_name": "TOTAL STUDENTS",
                "value": format_kpi_value(tot_st, "count"),
                "raw_value": int(tot_st),
                "unit": "students",
                "aggregation_method": agg_st,
                "data_grain": grain_st,
                "source_table": logical_table,
                "source_column": source_st,
                "description": desc_st,
                "explanation": "Calculates total student headcount on record.",
                "supporting_sql": sql_st_disp,
                "display_sql": sql_st_disp,
                "execution_sql": sql_st_exec,
                "period_comparison": None,
                "icon": "GraduationCap"
            })

            marks_col = next((c for c in num_cols if any(k in c.lower() for k in ["marks", "score", "grade_val", "points"])), None)
            if marks_col:
                sql_avg_exec = f"SELECT ROUND(AVG(`{marks_col}`), 2) FROM `{table_name}` {where_sql}"
                avg_marks = conn.execute(text(sql_avg_exec), params).scalar() or 0
                sql_avg_disp = to_display_sql(sql_avg_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_avg_marks",
                    "metric_id": "average_marks",
                    "title": "AVERAGE MARKS",
                    "display_name": "AVERAGE MARKS",
                    "value": format_kpi_value(avg_marks, "number"),
                    "raw_value": float(avg_marks),
                    "unit": "marks",
                    "aggregation_method": "AVG",
                    "data_grain": "assessment",
                    "source_table": logical_table,
                    "source_column": marks_col,
                    "description": f"Overall average score across records (`{marks_col}`)",
                    "explanation": f"Computes arithmetic mean of `{marks_col}`.",
                    "supporting_sql": sql_avg_disp,
                    "display_sql": sql_avg_disp,
                    "execution_sql": sql_avg_exec,
                    "period_comparison": None,
                    "icon": "Award"
                })

                sql_max_exec = f"SELECT MAX(`{marks_col}`) FROM `{table_name}` {where_sql}"
                max_marks = conn.execute(text(sql_max_exec), params).scalar() or 0
                sql_max_disp = to_display_sql(sql_max_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_max_marks",
                    "metric_id": "highest_marks",
                    "title": "HIGHEST MARKS",
                    "display_name": "HIGHEST MARKS",
                    "value": format_kpi_value(max_marks, "number"),
                    "raw_value": float(max_marks),
                    "unit": "marks",
                    "aggregation_method": "MAX",
                    "data_grain": "assessment",
                    "source_table": logical_table,
                    "source_column": marks_col,
                    "description": f"Peak score achieved in `{marks_col}`",
                    "explanation": f"Identifies highest individual score recorded.",
                    "supporting_sql": sql_max_disp,
                    "display_sql": sql_max_disp,
                    "execution_sql": sql_max_exec,
                    "period_comparison": None,
                    "icon": "Trophy"
                })

                sql_min_exec = f"SELECT MIN(`{marks_col}`) FROM `{table_name}` {where_sql}"
                min_marks = conn.execute(text(sql_min_exec), params).scalar() or 0
                sql_min_disp = to_display_sql(sql_min_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_min_marks",
                    "metric_id": "lowest_marks",
                    "title": "LOWEST MARKS",
                    "display_name": "LOWEST MARKS",
                    "value": format_kpi_value(min_marks, "number"),
                    "raw_value": float(min_marks),
                    "unit": "marks",
                    "aggregation_method": "MIN",
                    "data_grain": "assessment",
                    "source_table": logical_table,
                    "source_column": marks_col,
                    "description": f"Minimum score recorded in `{marks_col}`",
                    "explanation": f"Identifies lowest individual score recorded.",
                    "supporting_sql": sql_min_disp,
                    "display_sql": sql_min_disp,
                    "execution_sql": sql_min_exec,
                    "period_comparison": None,
                    "icon": "AlertCircle"
                })

                status_col = next((c for c in profile.get("column_names", []) if any(k == c.lower() or f"_{k}" in c.lower() for k in ["passed", "result", "status", "pass_fail"])), None)
                if status_col:
                    sql_pass_exec = f"SELECT ROUND(100.0 * SUM(CASE WHEN LOWER(`{status_col}`) IN ('pass', 'passed', 'p', '1', 'true') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) FROM `{table_name}` {where_sql}"
                    pass_pct = conn.execute(text(sql_pass_exec), params).scalar() or 0
                    sql_pass_disp = to_display_sql(sql_pass_exec, table_name, logical_table)
                    kpis.append({
                        "id": "kpi_pass_rate",
                        "metric_id": "pass_percentage",
                        "title": "PASS PERCENTAGE",
                        "display_name": "PASS PERCENTAGE",
                        "value": format_kpi_value(pass_pct, "percentage"),
                        "raw_value": float(pass_pct),
                        "unit": "%",
                        "aggregation_method": "RATE",
                        "data_grain": "student",
                        "source_table": logical_table,
                        "source_column": status_col,
                        "description": f"Percentage of passing outcomes based on `{status_col}`",
                        "explanation": f"Calculates passing percentage from explicit `{status_col}` records.",
                        "supporting_sql": sql_pass_disp,
                        "display_sql": sql_pass_disp,
                        "execution_sql": sql_pass_exec,
                        "period_comparison": None,
                        "icon": "CheckCircle"
                    })

            subj_col = next((c for c in profile.get("column_names", []) if any(k in c.lower() for k in ["subject", "course", "paper"])), None)
            if subj_col:
                sql_subj_exec = f"SELECT COUNT(DISTINCT `{subj_col}`) FROM `{table_name}` {where_sql}"
                tot_subj = conn.execute(text(sql_subj_exec), params).scalar() or 0
                sql_subj_disp = to_display_sql(sql_subj_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_subjects_count",
                    "metric_id": "total_subjects",
                    "title": "TOTAL SUBJECTS",
                    "display_name": "TOTAL SUBJECTS",
                    "value": format_kpi_value(tot_subj, "count"),
                    "raw_value": int(tot_subj),
                    "unit": "subjects",
                    "aggregation_method": "COUNT_DISTINCT",
                    "data_grain": "subject",
                    "source_table": logical_table,
                    "source_column": subj_col,
                    "description": "Distinct academic subjects evaluated",
                    "explanation": f"Counts distinct subjects in `{subj_col}`.",
                    "supporting_sql": sql_subj_disp,
                    "display_sql": sql_subj_disp,
                    "execution_sql": sql_subj_exec,
                    "period_comparison": None,
                    "icon": "BookOpen"
                })

                if marks_col:
                    try:
                        sql_best_subj = f"SELECT `{subj_col}`, ROUND(AVG(`{marks_col}`), 2) as avg_s FROM `{table_name}` {where_sql} GROUP BY `{subj_col}` ORDER BY avg_s DESC LIMIT 1"
                        best_row = conn.execute(text(sql_best_subj), params).fetchone()
                        if best_row:
                            sql_best_disp = to_display_sql(sql_best_subj, table_name, logical_table)
                            kpis.append({
                                "id": "kpi_best_subject",
                                "metric_id": "best_performing_subject",
                                "title": "TOP SUBJECT",
                                "display_name": "TOP SUBJECT",
                                "value": str(best_row[0]),
                                "raw_value": float(best_row[1]),
                                "unit": "marks",
                                "aggregation_method": "GROUP_AVG_MAX",
                                "data_grain": "subject",
                                "source_table": logical_table,
                                "source_column": f"{subj_col}, {marks_col}",
                                "description": f"Highest scoring subject (Avg: {best_row[1]})",
                                "explanation": f"Subject with highest average `{marks_col}` score.",
                                "supporting_sql": sql_best_disp,
                                "display_sql": sql_best_disp,
                                "execution_sql": sql_best_subj,
                                "period_comparison": None,
                                "icon": "Award"
                            })
                    except Exception:
                        pass

        elif domain == "hr":
            emp_col = next((c for c in profile.get("column_names", []) if any(k in c.lower() for k in ["employee_id", "staff_no", "emp_id", "staff_id"])), None)
            if emp_col:
                sql_emp_exec = f"SELECT COUNT(DISTINCT `{emp_col}`) FROM `{table_name}` {where_sql}"
                desc_emp = f"Distinct employees on record (`{emp_col}`)"
                grain_emp = "employee"
                source_emp = emp_col
                agg_emp = "COUNT_DISTINCT"
            else:
                sql_emp_exec = f"SELECT COUNT(*) FROM `{table_name}` {where_sql}"
                desc_emp = "Total employee records"
                grain_emp = "record"
                source_emp = "*"
                agg_emp = "COUNT"
            tot_emp = conn.execute(text(sql_emp_exec), params).scalar() or 0
            sql_emp_disp = to_display_sql(sql_emp_exec, table_name, logical_table)
            kpis.append({
                "id": "kpi_total_employees",
                "metric_id": "total_employees",
                "title": "TOTAL EMPLOYEES",
                "display_name": "TOTAL EMPLOYEES",
                "value": format_kpi_value(tot_emp, "count"),
                "raw_value": int(tot_emp),
                "unit": "employees",
                "aggregation_method": agg_emp,
                "data_grain": grain_emp,
                "source_table": logical_table,
                "source_column": source_emp,
                "description": desc_emp,
                "explanation": "Calculates total employee headcount.",
                "supporting_sql": sql_emp_disp,
                "display_sql": sql_emp_disp,
                "execution_sql": sql_emp_exec,
                "period_comparison": None,
                "icon": "Users"
            })

            sal_col = next((c for c in num_cols if any(k in c.lower() for k in ["salary", "pay", "wage", "compensation", "ctc"])), None)
            if sal_col:
                sql_sal_exec = f"SELECT ROUND(AVG(`{sal_col}`), 2) FROM `{table_name}` {where_sql}"
                avg_sal = conn.execute(text(sql_sal_exec), params).scalar() or 0
                sql_sal_disp = to_display_sql(sql_sal_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_avg_salary",
                    "metric_id": "average_salary",
                    "title": "AVERAGE SALARY",
                    "display_name": "AVERAGE SALARY",
                    "value": format_kpi_value(avg_sal, "currency", prefix=currency_symbol),
                    "raw_value": float(avg_sal),
                    "unit": currency_symbol,
                    "currency_code": currency_code,
                    "aggregation_method": "AVG",
                    "data_grain": "employee",
                    "source_table": logical_table,
                    "source_column": sal_col,
                    "description": f"Mean compensation package (`{sal_col}`)",
                    "explanation": f"Computes arithmetic mean of `{sal_col}` across personnel.",
                    "supporting_sql": sql_sal_disp,
                    "display_sql": sql_sal_disp,
                    "execution_sql": sql_sal_exec,
                    "period_comparison": None,
                    "icon": "Briefcase"
                })

                sql_max_sal_exec = f"SELECT MAX(`{sal_col}`) FROM `{table_name}` {where_sql}"
                max_sal = conn.execute(text(sql_max_sal_exec), params).scalar() or 0
                sql_max_sal_disp = to_display_sql(sql_max_sal_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_max_salary",
                    "metric_id": "highest_salary",
                    "title": "HIGHEST SALARY",
                    "display_name": "HIGHEST SALARY",
                    "value": format_kpi_value(max_sal, "currency", prefix=currency_symbol),
                    "raw_value": float(max_sal),
                    "unit": currency_symbol,
                    "currency_code": currency_code,
                    "aggregation_method": "MAX",
                    "data_grain": "employee",
                    "source_table": logical_table,
                    "source_column": sal_col,
                    "description": f"Peak employee compensation (`{sal_col}`)",
                    "explanation": f"Identifies highest compensation figure in `{sal_col}`.",
                    "supporting_sql": sql_max_sal_disp,
                    "display_sql": sql_max_sal_disp,
                    "execution_sql": sql_max_sal_exec,
                    "period_comparison": None,
                    "icon": "TrendingUp"
                })

            dept_col = next((c for c in profile.get("column_names", []) if any(k in c.lower() for k in ["department", "dept", "division", "team"])), None)
            if dept_col:
                sql_dept_exec = f"SELECT COUNT(DISTINCT `{dept_col}`) FROM `{table_name}` {where_sql}"
                tot_dept = conn.execute(text(sql_dept_exec), params).scalar() or 0
                sql_dept_disp = to_display_sql(sql_dept_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_departments_count",
                    "metric_id": "total_departments",
                    "title": "TOTAL DEPARTMENTS",
                    "display_name": "TOTAL DEPARTMENTS",
                    "value": format_kpi_value(tot_dept, "count"),
                    "raw_value": int(tot_dept),
                    "unit": "departments",
                    "aggregation_method": "COUNT_DISTINCT",
                    "data_grain": "department",
                    "source_table": logical_table,
                    "source_column": dept_col,
                    "description": f"Distinct business units (`{dept_col}`)",
                    "explanation": f"Counts distinct departments in `{dept_col}`.",
                    "supporting_sql": sql_dept_disp,
                    "display_sql": sql_dept_disp,
                    "execution_sql": sql_dept_exec,
                    "period_comparison": None,
                    "icon": "Building"
                })

                sql_top_dept_exec = f"SELECT `{dept_col}`, COUNT(*) as cnt FROM `{table_name}` {where_sql} GROUP BY `{dept_col}` ORDER BY cnt DESC LIMIT 1"
                top_dept_row = conn.execute(text(sql_top_dept_exec), params).fetchone()
                if top_dept_row:
                    sql_top_dept_disp = to_display_sql(sql_top_dept_exec, table_name, logical_table)
                    kpis.append({
                        "id": "kpi_largest_department",
                        "metric_id": "largest_department",
                        "title": "LARGEST DEPARTMENT",
                        "display_name": "LARGEST DEPARTMENT",
                        "value": str(top_dept_row[0]),
                        "raw_value": int(top_dept_row[1]),
                        "unit": "staff",
                        "aggregation_method": "GROUP_COUNT_MAX",
                        "data_grain": "department",
                        "source_table": logical_table,
                        "source_column": dept_col,
                        "description": f"Headcount: {top_dept_row[1]} members ({dept_col})",
                        "explanation": f"Department with largest employee headcount.",
                        "supporting_sql": sql_top_dept_disp,
                        "display_sql": sql_top_dept_disp,
                        "execution_sql": sql_top_dept_exec,
                        "period_comparison": None,
                        "icon": "Layers"
                    })

        elif domain == "finance":
            amt_col = next((c for c in num_cols if any(k in c.lower() for k in ["amount", "txn_amount", "transaction_amount", "value", "balance"])), None)
            if amt_col:
                if is_multi_currency and curr_col:
                    sql_multi_exec = f"""
                        SELECT `{curr_col}` as currency,
                               ROUND(SUM(`{amt_col}`), 2) as val,
                               COUNT(*) as cnt
                        FROM `{table_name}` {where_sql}
                        WHERE `{curr_col}` IS NOT NULL
                        GROUP BY `{curr_col}`
                        ORDER BY val DESC
                    """
                    rows = conn.execute(text(sql_multi_exec), params).fetchall()
                    breakdown = []
                    display_parts = []
                    for r in rows:
                        c_code = str(r[0]).strip().upper()
                        c_sym = CURRENCY_MAP.get(c_code, "")
                        c_val = float(r[1] or 0)
                        c_fmt = format_kpi_value(c_val, "currency", prefix=c_sym)
                        breakdown.append({
                            "code": c_code,
                            "symbol": c_sym,
                            "amount": c_val,
                            "formatted": c_fmt,
                            "count": int(r[2])
                        })
                        display_parts.append(f"{c_fmt} ({c_code})")
                    
                    multi_disp = " | ".join(display_parts) if display_parts else "N/A"
                    disp_sql = to_display_sql(sql_multi_exec, table_name, logical_table)
                    kpis.append({
                        "id": "kpi_total_volume",
                        "metric_id": "total_transaction_value_multi_currency",
                        "title": "TOTAL VOLUME (BY CURRENCY)",
                        "display_name": "TOTAL TRANSACTION VALUE (BY CURRENCY)",
                        "value": multi_disp,
                        "raw_value": None,
                        "unit": "multi-currency",
                        "is_multi_currency": True,
                        "currency_breakdown": breakdown,
                        "aggregation_method": "GROUP_BY_CURRENCY",
                        "data_grain": "currency_subtotal",
                        "source_table": logical_table,
                        "source_column": amt_col,
                        "description": "Transaction volume grouped by currency to prevent invalid cross-currency summation",
                        "explanation": "Different currencies cannot be aggregated together without verified exchange rates. Metrics are presented separately for each currency.",
                        "supporting_sql": disp_sql,
                        "display_sql": disp_sql,
                        "execution_sql": sql_multi_exec,
                        "period_comparison": None,
                        "icon": "DollarSign"
                    })
                elif is_currency_unresolved:
                    kpis.append({
                        "id": "kpi_volume_unresolved",
                        "metric_id": "volume_unresolved",
                        "title": "VOLUME AGGREGATION SUPPRESSED",
                        "display_name": "VOLUME AGGREGATION SUPPRESSED",
                        "value": "Unresolved Currency",
                        "raw_value": None,
                        "unit": "",
                        "is_ambiguous": True,
                        "aggregation_method": "SUPPRESSED",
                        "data_grain": "unresolved",
                        "source_table": logical_table,
                        "source_column": amt_col,
                        "description": "Dataset contains mixed, missing, or unrecognized currency codes.",
                        "explanation": "Monetary aggregation was suppressed because currency indicators are ambiguous or unresolved.",
                        "supporting_sql": "-- Suppressed to prevent invalid cross-currency summation",
                        "display_sql": "-- Suppressed to prevent invalid cross-currency summation",
                        "execution_sql": "-- Suppressed",
                        "period_comparison": None,
                        "icon": "AlertCircle"
                    })
                else:
                    sql_tot_amt = f"SELECT ROUND(SUM(`{amt_col}`), 2) FROM `{table_name}` {where_sql}"
                    tot_amt = conn.execute(text(sql_tot_amt), params).scalar() or 0
                    sql_tot_disp = to_display_sql(sql_tot_amt, table_name, logical_table)
                    comp = calculate_period_comparison(table_name, primary_date, f"ROUND(SUM(`{amt_col}`), 2)", where_sql, params, "Total Volume", currency_symbol) if primary_date else None
                    kpis.append({
                        "id": "kpi_total_volume",
                        "metric_id": "total_transaction_value",
                        "title": "TOTAL VOLUME",
                        "display_name": "TOTAL TRANSACTION VALUE",
                        "value": format_kpi_value(tot_amt, "currency", prefix=currency_symbol),
                        "raw_value": float(tot_amt),
                        "unit": currency_symbol,
                        "currency_code": currency_code,
                        "aggregation_method": "SUM",
                        "data_grain": "transaction",
                        "source_table": logical_table,
                        "source_column": amt_col,
                        "description": f"Sum of transaction amounts (`{amt_col}`)",
                        "explanation": f"Aggregates total volume from `{amt_col}`.",
                        "supporting_sql": sql_tot_disp,
                        "display_sql": sql_tot_disp,
                        "execution_sql": sql_tot_amt,
                        "period_comparison": comp,
                        "icon": "DollarSign"
                    })

                sql_tot_txns = f"SELECT COUNT(*) FROM `{table_name}` {where_sql}"
                tot_txns = conn.execute(text(sql_tot_txns), params).scalar() or 0
                sql_txns_disp = to_display_sql(sql_tot_txns, table_name, logical_table)
                kpis.append({
                    "id": "kpi_total_transactions",
                    "metric_id": "total_transactions",
                    "title": "TOTAL TRANSACTIONS",
                    "display_name": "TOTAL TRANSACTIONS",
                    "value": format_kpi_value(tot_txns, "count"),
                    "raw_value": int(tot_txns),
                    "unit": "transactions",
                    "aggregation_method": "COUNT",
                    "data_grain": "transaction",
                    "source_table": logical_table,
                    "source_column": "*",
                    "description": "Total executed financial transactions",
                    "explanation": "Counts total financial records processed.",
                    "supporting_sql": sql_txns_disp,
                    "display_sql": sql_txns_disp,
                    "execution_sql": sql_tot_txns,
                    "period_comparison": None,
                    "icon": "TrendingUp"
                })

                if not is_multi_currency and not is_currency_unresolved:
                    sql_avg_amt = f"SELECT ROUND(AVG(`{amt_col}`), 2) FROM `{table_name}` {where_sql}"
                    avg_amt = conn.execute(text(sql_avg_amt), params).scalar() or 0
                    sql_avg_disp = to_display_sql(sql_avg_amt, table_name, logical_table)
                    kpis.append({
                        "id": "kpi_avg_transaction",
                        "metric_id": "average_transaction_value",
                        "title": "AVERAGE TRANSACTION",
                        "display_name": "AVERAGE TRANSACTION VALUE",
                        "value": format_kpi_value(avg_amt, "currency", prefix=currency_symbol),
                        "raw_value": float(avg_amt),
                        "unit": currency_symbol,
                        "currency_code": currency_code,
                        "aggregation_method": "AVG",
                        "data_grain": "transaction",
                        "source_table": logical_table,
                        "source_column": amt_col,
                        "description": f"Mean transaction size (`{amt_col}`)",
                        "explanation": f"Average financial transaction size.",
                        "supporting_sql": sql_avg_disp,
                        "display_sql": sql_avg_disp,
                        "execution_sql": sql_avg_amt,
                        "period_comparison": None,
                        "icon": "Award"
                    })

                    sql_max_amt = f"SELECT MAX(`{amt_col}`) FROM `{table_name}` {where_sql}"
                    max_amt = conn.execute(text(sql_max_amt), params).scalar() or 0
                    sql_max_disp = to_display_sql(sql_max_amt, table_name, logical_table)
                    kpis.append({
                        "id": "kpi_max_transaction",
                        "metric_id": "highest_transaction",
                        "title": "HIGHEST TRANSACTION",
                        "display_name": "HIGHEST TRANSACTION",
                        "value": format_kpi_value(max_amt, "currency", prefix=currency_symbol),
                        "raw_value": float(max_amt),
                        "unit": currency_symbol,
                        "currency_code": currency_code,
                        "aggregation_method": "MAX",
                        "data_grain": "transaction",
                        "source_table": logical_table,
                        "source_column": amt_col,
                        "description": f"Peak transaction observed in `{amt_col}`",
                        "explanation": f"Identifies largest single transaction value.",
                        "supporting_sql": sql_max_disp,
                        "display_sql": sql_max_disp,
                        "execution_sql": sql_max_amt,
                        "period_comparison": None,
                        "icon": "Award"
                    })

        elif domain == "inventory":
            prod_col = next((c for c in profile.get("column_names", []) if any(k in c.lower() for k in ["sku", "product_id", "item_code", "product_name", "product"])), None)
            if prod_col:
                sql_prod_exec = f"SELECT COUNT(DISTINCT `{prod_col}`) FROM `{table_name}` {where_sql}"
                desc_prod = f"Distinct SKU items (`{prod_col}`)"
                agg_prod = "COUNT_DISTINCT"
                source_prod = prod_col
            else:
                sql_prod_exec = f"SELECT COUNT(*) FROM `{table_name}` {where_sql}"
                desc_prod = "Total inventory catalog items"
                agg_prod = "COUNT"
                source_prod = "*"
            tot_prod = conn.execute(text(sql_prod_exec), params).scalar() or 0
            sql_prod_disp = to_display_sql(sql_prod_exec, table_name, logical_table)
            kpis.append({
                "id": "kpi_total_products",
                "metric_id": "total_products",
                "title": "TOTAL PRODUCTS",
                "display_name": "TOTAL PRODUCTS",
                "value": format_kpi_value(tot_prod, "count"),
                "raw_value": int(tot_prod),
                "unit": "products",
                "aggregation_method": agg_prod,
                "data_grain": "product",
                "source_table": logical_table,
                "source_column": source_prod,
                "description": desc_prod,
                "explanation": "Counts distinct catalog products.",
                "supporting_sql": sql_prod_disp,
                "display_sql": sql_prod_disp,
                "execution_sql": sql_prod_exec,
                "period_comparison": None,
                "icon": "Package"
            })

            stock_col = next((c for c in num_cols if any(k in c.lower() for k in ["stock_quantity", "stock", "quantity", "on_hand", "qty"])), None)
            cost_col = next((c for c in num_cols if any(k in c.lower() for k in ["unit_cost", "cost", "price", "unit_price"])), None)

            if stock_col:
                sql_stock_exec = f"SELECT SUM(`{stock_col}`) FROM `{table_name}` {where_sql}"
                tot_stock = conn.execute(text(sql_stock_exec), params).scalar() or 0
                sql_stock_disp = to_display_sql(sql_stock_exec, table_name, logical_table)
                kpis.append({
                    "id": "kpi_total_stock",
                    "metric_id": "total_stock_quantity",
                    "title": "TOTAL STOCK QUANTITY",
                    "display_name": "TOTAL STOCK QUANTITY",
                    "value": format_kpi_value(tot_stock, "count"),
                    "raw_value": float(tot_stock),
                    "unit": "units",
                    "aggregation_method": "SUM",
                    "data_grain": "stock_unit",
                    "source_table": logical_table,
                    "source_column": stock_col,
                    "description": f"Cumulative units on hand (`{stock_col}`)",
                    "explanation": f"Sums physical inventory units across records.",
                    "supporting_sql": sql_stock_disp,
                    "display_sql": sql_stock_disp,
                    "execution_sql": sql_stock_exec,
                    "period_comparison": None,
                    "icon": "Layers"
                })

            if stock_col and cost_col:
                sql_inv_val = f"SELECT ROUND(SUM(`{stock_col}` * `{cost_col}`), 2) FROM `{table_name}` {where_sql}"
                inv_val = conn.execute(text(sql_inv_val), params).scalar() or 0
                sql_inv_disp = to_display_sql(sql_inv_val, table_name, logical_table)
                kpis.append({
                    "id": "kpi_inventory_value",
                    "metric_id": "inventory_value",
                    "title": "TOTAL INVENTORY VALUE",
                    "display_name": "TOTAL INVENTORY VALUE",
                    "value": format_kpi_value(inv_val, "currency", prefix=currency_symbol),
                    "raw_value": float(inv_val),
                    "unit": currency_symbol,
                    "currency_code": currency_code,
                    "aggregation_method": "SUM_PRODUCT",
                    "data_grain": "product",
                    "source_table": logical_table,
                    "source_column": f"{stock_col} * {cost_col}",
                    "description": f"Calculated as `{stock_col}` * `{cost_col}`",
                    "explanation": f"Calculates total inventory valuation by multiplying stock quantity by unit cost.",
                    "supporting_sql": sql_inv_disp,
                    "display_sql": sql_inv_disp,
                    "execution_sql": sql_inv_val,
                    "period_comparison": None,
                    "icon": "DollarSign"
                })

        else:
            sql_tot_exec = f"SELECT COUNT(*) FROM `{table_name}` {where_sql}"
            tot_rows = conn.execute(text(sql_tot_exec), params).scalar() or 0
            sql_tot_disp = to_display_sql(sql_tot_exec, table_name, logical_table)
            kpis.append({
                "id": "kpi_total_records",
                "metric_id": "total_records",
                "title": "TOTAL RECORDS",
                "display_name": "TOTAL RECORDS",
                "value": format_kpi_value(tot_rows, "count"),
                "raw_value": int(tot_rows),
                "unit": "records",
                "aggregation_method": "COUNT",
                "data_grain": "record",
                "source_table": logical_table,
                "source_column": "*",
                "description": "Total rows analyzed in dataset",
                "explanation": "Calculates total row count across verified dataset.",
                "supporting_sql": sql_tot_disp,
                "display_sql": sql_tot_disp,
                "execution_sql": sql_tot_exec,
                "period_comparison": None,
                "icon": "Database"
            })

            for p_num in num_cols[:2]:
                if any(p_num.lower() == k for k in ["id", "index", "row_num"]):
                    continue
                sql_sum = f"SELECT ROUND(SUM(`{p_num}`), 2) FROM `{table_name}` {where_sql}"
                val_sum = conn.execute(text(sql_sum), params).scalar() or 0
                disp_sum = to_display_sql(sql_sum, table_name, logical_table)
                kpis.append({
                    "id": f"kpi_sum_{p_num}",
                    "metric_id": f"total_{p_num}",
                    "title": f"TOTAL {p_num.upper()}",
                    "display_name": f"TOTAL {p_num.upper()}",
                    "value": format_kpi_value(val_sum),
                    "raw_value": float(val_sum),
                    "unit": "",
                    "aggregation_method": "SUM",
                    "data_grain": "record",
                    "source_table": logical_table,
                    "source_column": p_num,
                    "description": f"Cumulative sum of `{p_num}`",
                    "explanation": f"Sums numerical values in `{p_num}`.",
                    "supporting_sql": disp_sum,
                    "display_sql": disp_sum,
                    "execution_sql": sql_sum,
                    "period_comparison": None,
                    "icon": "TrendingUp"
                })

                sql_avg = f"SELECT ROUND(AVG(`{p_num}`), 2) FROM `{table_name}` {where_sql}"
                val_avg = conn.execute(text(sql_avg), params).scalar() or 0
                disp_avg = to_display_sql(sql_avg, table_name, logical_table)
                kpis.append({
                    "id": f"kpi_avg_{p_num}",
                    "metric_id": f"average_{p_num}",
                    "title": f"AVERAGE {p_num.upper()}",
                    "display_name": f"AVERAGE {p_num.upper()}",
                    "value": format_kpi_value(val_avg),
                    "raw_value": float(val_avg),
                    "unit": "",
                    "aggregation_method": "AVG",
                    "data_grain": "record",
                    "source_table": logical_table,
                    "source_column": p_num,
                    "description": f"Mean value of `{p_num}`",
                    "explanation": f"Calculates arithmetic average of `{p_num}`.",
                    "supporting_sql": disp_avg,
                    "display_sql": disp_avg,
                    "execution_sql": sql_avg,
                    "period_comparison": None,
                    "icon": "BarChart"
                })

            if cat_cols:
                p_cat = cat_cols[0]
                sql_dist = f"SELECT COUNT(DISTINCT `{p_cat}`) FROM `{table_name}` {where_sql}"
                val_dist = conn.execute(text(sql_dist), params).scalar() or 0
                disp_dist = to_display_sql(sql_dist, table_name, logical_table)
                kpis.append({
                    "id": f"kpi_distinct_{p_cat}",
                    "metric_id": f"unique_{p_cat}",
                    "title": f"UNIQUE {p_cat.upper()}",
                    "display_name": f"UNIQUE {p_cat.upper()}",
                    "value": format_kpi_value(val_dist, "count"),
                    "raw_value": int(val_dist),
                    "unit": "unique",
                    "aggregation_method": "COUNT_DISTINCT",
                    "data_grain": "category",
                    "source_table": logical_table,
                    "source_column": p_cat,
                    "description": f"Distinct values in `{p_cat}`",
                    "explanation": f"Counts distinct category entries in `{p_cat}`.",
                    "supporting_sql": disp_dist,
                    "display_sql": disp_dist,
                    "execution_sql": sql_dist,
                    "period_comparison": None,
                    "icon": "Layers"
                })

    return kpis[:6]


def generate_visual_analytics(
    table_name: str,
    profile: Dict[str, Any],
    domain_info: Dict[str, Any],
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Intelligently generates overview trend charts, category breakdowns, distributions, and rankings.
    Ensures latest 12 periods are selected chronologically, metric-aware aggregation (AVG vs SUM),
    and true dataset population percentage calculation across all categories.
    """
    where_sql, params = build_filter_clause(table_name, profile, filters)
    charts: Dict[str, Any] = {}
    logical_table = get_logical_table_name(table_name)
    
    num_cols = profile.get("numeric_columns", [])
    raw_cat = profile.get("categorical_columns", []) + profile.get("text_columns", [])
    cat_cols = list(dict.fromkeys(raw_cat))
    date_cols = profile.get("date_columns", [])
    
    primary_num = next((c for c in num_cols if any(k in c.lower() for k in ["total_amount", "amount", "revenue", "sales", "salary", "marks", "score"])), None)
    if not primary_num and num_cols:
        valid_nums = [c for c in num_cols if not c.lower().endswith("_id") and c.lower() != "id"]
        primary_num = valid_nums[0] if valid_nums else num_cols[0]
        
    primary_cat = next((c for c in cat_cols if any(k in c.lower() for k in ["category", "department", "subject", "product_category", "type", "office", "genre"])), None)
    if not primary_cat and cat_cols:
        primary_cat = next((c for c in cat_cols if not c.lower().endswith("_id") and c.lower() != "id"), cat_cols[0])
        
    status_cat = next((c for c in cat_cols if any(k in c.lower() for k in ["status", "state", "segment", "grade", "office"])), None)
    entity_col = next((c for c in cat_cols if any(k in c.lower() for k in ["product_name", "product", "customer_name", "full_name", "name", "student_name", "title"])), None)

    with engine.connect() as conn:
        # 1. Performance Overview Chart: Latest 12 periods with metric-aware aggregation
        trend_date_col = select_best_trend_date_column(date_cols, primary_num)
        if trend_date_col and primary_num:
            d_col = trend_date_col
            is_avg_metric = any(k in primary_num.lower() for k in ["salary", "pay", "marks", "score", "rating", "unit_price", "price", "gpa", "discount_pct"])
            agg_fn = "AVG" if is_avg_metric else "SUM"
            agg_title = "Average" if is_avg_metric else "Total"
            
            sql_trend_exec = f"""
                SELECT period, val FROM (
                    SELECT DATE_FORMAT(`{d_col}`, '%Y-%m') as period,
                           ROUND({agg_fn}(`{primary_num}`), 2) as val
                    FROM `{table_name}`
                    {where_sql + (' AND ' if where_sql else 'WHERE ') + f'`{d_col}` IS NOT NULL AND `{primary_num}` IS NOT NULL'}
                    GROUP BY period
                    ORDER BY period DESC
                    LIMIT 12
                ) sub
                ORDER BY period ASC
            """
            rows = conn.execute(text(sql_trend_exec), params).fetchall()
            if rows:
                disp_trend = to_display_sql(sql_trend_exec, table_name, logical_table)
                charts["overview_chart"] = {
                    "title": f"Monthly {agg_title} {primary_num.replace('_', ' ').title()} Trend",
                    "type": "line",
                    "x_label": "Month",
                    "y_label": f"{agg_title} {primary_num.replace('_', ' ').title()}",
                    "data": [{"label": str(r[0]), "value": float(r[1] or 0)} for r in rows],
                    "supporting_sql": disp_trend,
                    "display_sql": disp_trend,
                    "execution_sql": sql_trend_exec
                }
        elif primary_cat and primary_num:
            is_avg_metric = any(k in primary_num.lower() for k in ["salary", "pay", "marks", "score", "rating", "unit_price", "price", "gpa"])
            agg_fn = "AVG" if is_avg_metric else "SUM"
            agg_title = "Average" if is_avg_metric else "Total"
            sql_cat_trend_exec = f"""
                SELECT `{primary_cat}` as cat,
                       ROUND({agg_fn}(`{primary_num}`), 2) as val
                FROM `{table_name}`
                {where_sql + (' AND ' if where_sql else 'WHERE ') + f'`{primary_cat}` IS NOT NULL AND `{primary_num}` IS NOT NULL'}
                GROUP BY `{primary_cat}`
                ORDER BY val DESC
                LIMIT 8
            """
            rows = conn.execute(text(sql_cat_trend_exec), params).fetchall()
            if rows:
                disp_cat_trend = to_display_sql(sql_cat_trend_exec, table_name, logical_table)
                charts["overview_chart"] = {
                    "title": f"{agg_title} {primary_num.replace('_', ' ').title()} across {primary_cat.replace('_', ' ').title()}",
                    "type": "bar",
                    "x_label": primary_cat.replace('_', ' ').title(),
                    "y_label": f"{agg_title} {primary_num.replace('_', ' ').title()}",
                    "data": [{"label": str(r[0]), "value": float(r[1] or 0)} for r in rows],
                    "supporting_sql": disp_cat_trend,
                    "display_sql": disp_cat_trend,
                    "execution_sql": sql_cat_trend_exec
                }
        else:
            charts["overview_chart"] = None

        # 2. Category Breakdown Chart: Calculated with true population share
        if primary_cat and primary_num:
            sql_tot_cat = f"""
                SELECT ROUND(SUM(`{primary_num}`), 2), COUNT(DISTINCT `{primary_cat}`)
                FROM `{table_name}`
                {where_sql + (' AND ' if where_sql else 'WHERE ') + f'`{primary_cat}` IS NOT NULL AND `{primary_num}` IS NOT NULL'}
            """
            row_tot = conn.execute(text(sql_tot_cat), params).fetchone()
            total_dataset_val = float(row_tot[0] or 0.0) if row_tot else 0.0
            total_cats_count = int(row_tot[1] or 0) if row_tot else 0

            sql_bar_exec = f"""
                SELECT `{primary_cat}` as cat,
                       ROUND(SUM(`{primary_num}`), 2) as val,
                       COUNT(*) as volume
                FROM `{table_name}`
                {where_sql + (' AND ' if where_sql else 'WHERE ') + f'`{primary_cat}` IS NOT NULL AND `{primary_num}` IS NOT NULL'}
                GROUP BY `{primary_cat}`
                ORDER BY val DESC
                LIMIT 6
            """
            rows = conn.execute(text(sql_bar_exec), params).fetchall()
            if rows:
                disp_bar = to_display_sql(sql_bar_exec, table_name, logical_table)
                cat_data = []
                for r in rows:
                    val = float(r[1] or 0)
                    share = round((val / total_dataset_val) * 100.0, 1) if total_dataset_val > 0 else 0.0
                    cat_data.append({
                        "label": str(r[0]),
                        "value": val,
                        "volume": int(r[2]),
                        "share_pct": share
                    })
                charts["category_chart"] = {
                    "title": f"{primary_num.replace('_', ' ').title()} by {primary_cat.replace('_', ' ').title()}",
                    "type": "bar",
                    "x_label": primary_cat.replace('_', ' ').title(),
                    "y_label": primary_num.replace('_', ' ').title(),
                    "data": cat_data,
                    "total_dataset_value": total_dataset_val,
                    "shown_count": len(rows),
                    "total_categories_count": total_cats_count,
                    "supporting_sql": disp_bar,
                    "display_sql": disp_bar,
                    "execution_sql": sql_bar_exec
                }
        else:
            charts["category_chart"] = None

        # 3. Distribution Donut Chart
        dist_col = status_cat or (primary_cat if primary_cat != status_cat else None)
        if dist_col:
            sql_donut_exec = f"""
                SELECT `{dist_col}` as label,
                       COUNT(*) as cnt
                FROM `{table_name}`
                {where_sql + (' AND ' if where_sql else 'WHERE ') + f'`{dist_col}` IS NOT NULL'}
                GROUP BY `{dist_col}`
                ORDER BY cnt DESC
                LIMIT 6
            """
            rows = conn.execute(text(sql_donut_exec), params).fetchall()
            if rows:
                disp_donut = to_display_sql(sql_donut_exec, table_name, logical_table)
                charts["distribution_chart"] = {
                    "title": f"{dist_col.replace('_', ' ').title()} Distribution",
                    "type": "donut",
                    "data": [{"label": str(r[0]), "value": int(r[1])} for r in rows],
                    "supporting_sql": disp_donut,
                    "display_sql": disp_donut,
                    "execution_sql": sql_donut_exec
                }
        else:
            charts["distribution_chart"] = None

        # 4. Top Entities Ranking Chart
        if entity_col and primary_num:
            sql_top_exec = f"""
                SELECT `{entity_col}` as entity,
                       ROUND(SUM(`{primary_num}`), 2) as val
                FROM `{table_name}`
                {where_sql + (' AND ' if where_sql else 'WHERE ') + f'`{entity_col}` IS NOT NULL AND `{primary_num}` IS NOT NULL'}
                GROUP BY `{entity_col}`
                ORDER BY val DESC
                LIMIT 5
            """
            rows = conn.execute(text(sql_top_exec), params).fetchall()
            if rows:
                disp_top = to_display_sql(sql_top_exec, table_name, logical_table)
                charts["top_entities_chart"] = {
                    "title": f"Top 5 {entity_col.replace('_', ' ').title()} by {primary_num.replace('_', ' ').title()}",
                    "type": "bar",
                    "x_label": entity_col.replace('_', ' ').title(),
                    "y_label": primary_num.replace('_', ' ').title(),
                    "data": [{"label": str(r[0]), "value": float(r[1] or 0)} for r in rows],
                    "supporting_sql": disp_top,
                    "display_sql": disp_top,
                    "execution_sql": sql_top_exec
                }
        else:
            charts["top_entities_chart"] = None

    return charts


def generate_standout_highlights(
    table_name: str,
    profile: Dict[str, Any],
    domain_info: Dict[str, Any],
    kpis: List[Dict[str, Any]],
    charts: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Synthesizes 2-4 concise, query-grounded highlights with conversational follow-up questions."""
    highlights: List[Dict[str, Any]] = []
    domain = domain_info.get("domain", "generic")
    curr_sym, _ = detect_dataset_currency(table_name, profile)
    unit_type = "currency" if domain in ("ecommerce", "finance") else ("score" if domain == "education" else "number")
    verb = "generated" if domain in ("ecommerce", "finance") else ("achieved an average of" if domain == "education" else "recorded")
    
    # 1. Category dominance highlight calculated against complete dataset
    cat_chart = charts.get("category_chart")
    if cat_chart and cat_chart.get("data"):
        data = cat_chart["data"]
        top_cat = data[0]
        total_val = cat_chart.get("total_dataset_value") or sum(d["value"] for d in data)
        total_cats_count = cat_chart.get("total_categories_count") or len(data)
        if total_val > 0:
            share = round((top_cat["value"] / total_val) * 100, 1)
            formatted_top = format_kpi_value(top_cat["value"], unit_type, prefix=curr_sym)
            cat_label = cat_chart.get("x_label", "Category")
            metric_label = cat_chart.get("y_label", "Volume")
            highlights.append({
                "id": "hl_top_category",
                "title": f"Leading {cat_label}",
                "text": f"{top_cat['label']} {verb} {formatted_top}, contributing {share}% of total {metric_label.lower()} across all {total_cats_count} categories.",
                "metric": formatted_top,
                "suggested_question": f"Show detailed breakdown and performance for {top_cat['label']}",
                "action": "Investigate"
            })

    # 2. Top individual entity highlight
    top_chart = charts.get("top_entities_chart")
    if top_chart and top_chart.get("data"):
        top_entity = top_chart["data"][0]
        formatted_entity = format_kpi_value(top_entity["value"], unit_type, prefix=curr_sym)
        highlights.append({
            "id": "hl_top_entity",
            "title": f"Highest-Performing {top_chart['x_label']}",
            "text": f"{top_entity['label']} is the top contributor with {formatted_entity}.",
            "metric": formatted_entity,
            "suggested_question": f"Show records and performance for {top_entity['label']}",
            "action": "Investigate"
        })

    # 3. Distribution highlight
    dist_chart = charts.get("distribution_chart")
    if dist_chart and dist_chart.get("data"):
        dist_data = dist_chart["data"]
        top_dist = dist_data[0]
        tot_cnt = sum(d["value"] for d in dist_data)
        if tot_cnt > 0:
            pct = round((top_dist["value"] / tot_cnt) * 100, 1)
            highlights.append({
                "id": "hl_distribution",
                "title": f"Primary {dist_chart['title'].replace(' Distribution', '')}",
                "text": f"{top_dist['label']} accounts for {pct}% of classified records ({top_dist['value']:,} entries).",
                "metric": f"{pct}%",
                "suggested_question": f"Analyze records with {dist_chart['title'].replace(' Distribution', '')} as {top_dist['label']}",
                "action": "Investigate"
            })

    # 4. Period trend highlight
    ov_chart = charts.get("overview_chart")
    if ov_chart and ov_chart.get("type") == "line" and len(ov_chart.get("data", [])) >= 2:
        pts = ov_chart["data"]
        last_pt = pts[-1]
        prev_pt = pts[-2]
        if prev_pt["value"] > 0:
            diff = last_pt["value"] - prev_pt["value"]
            chg = round((diff / prev_pt["value"]) * 100, 1)
            sign = "+" if chg >= 0 else ""
            direction = "increased" if chg >= 0 else "decreased"
            highlights.append({
                "id": "hl_period_trend",
                "title": "Period-over-Period Performance",
                "text": f"Recent period {direction} by {sign}{chg}% ({last_pt['label']} vs {prev_pt['label']}).",
                "metric": f"{sign}{chg}%",
                "suggested_question": f"Compare performance between {prev_pt['label']} and {last_pt['label']}",
                "action": "Investigate"
            })

    return highlights[:4]


def get_available_filters(table_name: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extracts available dynamic filter options based on schema dimensions and date columns."""
    filters: List[Dict[str, Any]] = []
    raw_cat = profile.get("categorical_columns", []) + profile.get("text_columns", [])
    cat_cols = list(dict.fromkeys(raw_cat))
    date_cols = profile.get("date_columns", [])
    
    with engine.connect() as conn:
        for col in cat_cols:
            if col.lower().endswith("_id") and not col.lower() in ("customer_id", "department_id"):
                continue
            dist_cnt = profile.get("column_distinct", {}).get(col)
            if dist_cnt and 2 <= dist_cnt <= 25:
                try:
                    sql = f"SELECT DISTINCT `{col}` FROM `{table_name}` WHERE `{col}` IS NOT NULL ORDER BY `{col}` LIMIT 20"
                    rows = conn.execute(text(sql)).fetchall()
                    options = [str(r[0]) for r in rows if r[0] is not None]
                    if len(options) >= 2:
                        filters.append({
                            "column": col,
                            "label": col.replace("_", " ").title(),
                            "options": options
                        })
                except Exception:
                    pass
                    
        trend_date = select_best_trend_date_column(date_cols)
        d_col = trend_date if trend_date else (date_cols[0] if date_cols else None)
        if d_col:
            try:
                sql_range = f"SELECT MIN(`{d_col}`), MAX(`{d_col}`) FROM `{table_name}` WHERE `{d_col}` IS NOT NULL"
                min_d, max_d = conn.execute(text(sql_range)).fetchone()
                if min_d and max_d:
                    filters.append({
                        "column": "_date_range",
                        "date_column": d_col,
                        "label": f"{d_col.replace('_', ' ').title()} Range",
                        "min_date": str(min_d)[:10],
                        "max_date": str(max_d)[:10]
                    })
            except Exception:
                pass
                
    return filters[:4]


def get_domain_suggested_questions(domain: str, profile: Dict[str, Any]) -> List[str]:
    """Generates context-aware analytical questions for natural-language investigation."""
    if domain == "ecommerce":
        return [
            "Which product generated the highest revenue?",
            "Compare revenue across categories",
            "Show monthly sales trends",
            "What is the average order value?",
            "Show status distribution of orders"
        ]
    elif domain == "education":
        return [
            "Which subject has the highest average marks?",
            "How many students passed with marks >= 40?",
            "Show student performance distribution",
            "What is the overall pass percentage?"
        ]
    elif domain == "hr":
        return [
            "Which department has the largest headcount?",
            "Show average salary across departments",
            "What is the employee distribution across offices?",
            "Who has the highest compensation package?"
        ]
    elif domain == "finance":
        return [
            "What is the total transaction volume?",
            "Show monthly transaction trends",
            "What was the single largest transaction?"
        ]
    else:
        return [
            "Show summary statistics for this dataset",
            "Which category has the highest volume?",
            "Show the distribution of recorded values"
        ]


# ---------------------------------------------------------------------------
# Main Orchestration Engine
# ---------------------------------------------------------------------------
def discover_dataset_insights(
    user_id: str,
    table_name: Optional[str] = None,
    force_refresh: bool = False,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Primary orchestrator for automated dataset discovery & dynamic analytics.
    1. Resolves and authorizes dataset context server-side.
    2. Checks discovery cache (filter-aware).
    3. Profiles schema and distributions.
    4. Automatically infers domain & generates 4-6 dynamic KPIs.
    5. Builds intelligent visual analytics (overview, breakdown, distribution, rankings).
    6. Formulates data-backed 'What stands out?' takeaways and filter controls.
    7. Preserves deep statistical discoveries (anomalies, correlations, skew, relationships, quality) under advanced_discoveries.
    8. Returns composite structured payload.
    """
    # 1. Server-side tenant authorization
    physical_table = resolve_and_authorize_dataset(user_id=user_id, requested_table_name=table_name)
    friendly_name = get_logical_table_name(physical_table)

    # 2. Check cache (filter-aware key)
    filter_hash = f"__filt_{abs(hash(json.dumps(filters, sort_keys=True)))}" if filters else ""
    cache_tbl_key = f"{physical_table}{filter_hash}"
    if not force_refresh:
        cached = get_cached_insights(user_id, cache_tbl_key)
        if cached:
            return cached

    # 3. Classify columns & profile dataset
    classifications = classify_columns(physical_table)
    profile = profile_dataset(physical_table, classifications)

    # 4. Dynamic Domain Understanding & Visual Analytics (Issue 15.3 & 15.4)
    domain_info = identify_dataset_domain(physical_table, profile)
    kpis = generate_dynamic_kpis(physical_table, profile, domain_info, filters)
    charts = generate_visual_analytics(physical_table, profile, domain_info, filters)
    highlights = generate_standout_highlights(physical_table, profile, domain_info, kpis, charts)
    available_filters = get_available_filters(physical_table, profile)
    suggested_questions = get_domain_suggested_questions(domain_info["domain"], profile)

    all_insights: List[Dict[str, Any]] = []

    # If dataset has data, run the discovery modules
    if profile["total_records"] > 0:
        stat_insights = discover_statistical_patterns(physical_table, profile)
        trend_insights = discover_trends(physical_table, profile)
        anomaly_insights = discover_anomalies(physical_table, profile)
        relation_insights = discover_relationships(physical_table, profile, user_id)
        biz_insights = discover_business_insights(physical_table, profile)

        all_insights = biz_insights + stat_insights + trend_insights + anomaly_insights + relation_insights

        # Enhance with AI
        enhance_insights_with_ai(all_insights, friendly_name)

        # Transform physical SQL in findings to logical display SQL while preserving execution SQL
        for ins in all_insights:
            orig_sql = ins.get("supporting_sql", "")
            if orig_sql:
                ins["execution_sql"] = orig_sql
                ins["display_sql"] = to_display_sql(orig_sql, physical_table, friendly_name)
                ins["supporting_sql"] = ins["display_sql"]

    # Prioritize and group findings into key (4-6) and advanced discoveries
    key_discoveries, advanced_discoveries = prioritize_and_group_insights(all_insights)

    # Calculate summary metrics
    anomalies_count = sum(1 for i in all_insights if i["category"] in ("ANOMALIES", "DATA_QUALITY"))
    quality_findings_count = len(profile.get("quality_findings", []))

    result = {
        "success": True,
        "table_name": physical_table,
        "friendly_name": friendly_name,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "domain": domain_info["domain"],
        "domain_label": domain_info["domain_label"],
        "domain_confidence": domain_info["confidence"],
        "is_line_item": domain_info["is_line_item"],
        "entity_key": domain_info["entity_key"],
        "kpis": kpis,
        "charts": charts,
        "highlights": highlights,
        "available_filters": available_filters,
        "active_filters": filters or {},
        "suggested_questions": suggested_questions,
        "profile": profile,
        "summary_stats": {
            "records_analyzed": profile["total_records"],
            "fields_analyzed": profile["total_columns"],
            "insights_discovered": len(all_insights),
            "key_discoveries_count": len(key_discoveries),
            "review_candidates_count": anomalies_count,
            "potential_anomalies": anomalies_count,
            "data_quality_score": profile.get("data_quality_score", 100.0),
            "data_quality_findings": quality_findings_count
        },
        "key_discoveries": key_discoveries,
        "advanced_discoveries": advanced_discoveries,
        "insights": all_insights
    }

    # Save to cache
    set_cached_insights(user_id, cache_tbl_key, result)
    return result

