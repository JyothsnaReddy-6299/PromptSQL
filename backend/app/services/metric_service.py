import json
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from app.database.connection import SessionLocal, engine
from app.models.metric import BusinessMetric
from app.services.metric_parser import validate_and_compile_expression


def get_authorized_dataset_columns(table_name: str, user_id: str) -> List[str]:
    """
    Returns list of authorized column names for a dataset table owned by user.
    Hides internal surrogate keys like '_row_id'.
    """
    if "_usr_" in table_name:
        owner_id = "usr_" + table_name.split("_usr_")[-1]
        if owner_id != user_id:
            raise PermissionError(f"Access denied. You do not own dataset '{table_name}'.")

    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        raise ValueError(f"Dataset table '{table_name}' does not exist.")

    cols = [c["name"] for c in inspector.get_columns(table_name) if c["name"] != "_row_id"]
    return cols


def validate_filter_definition(filters: List[Dict[str, Any]], allowed_columns: List[str]) -> List[Dict[str, Any]]:
    """
    Validates optional metric filters:
    - column must exist in allowed_columns
    - operator must be in whitelist
    """
    allowed_cols_map = {c.lower(): c for c in allowed_columns}
    valid_operators = {"=", "!=", "<", ">", "<=", ">=", "LIKE", "NOT LIKE", "IN"}
    validated = []

    for f in filters:
        if not isinstance(f, dict):
            continue
        col = f.get("column", "").strip()
        op = f.get("operator", "=").strip().upper()
        val = f.get("value")

        if not col or col.lower() not in allowed_cols_map:
            raise ValueError(f"Filter column '{col}' does not exist in dataset.")
        if op not in valid_operators:
            raise ValueError(f"Unsupported filter operator '{op}'. Allowed: {', '.join(sorted(valid_operators))}")

        validated.append({
            "column": allowed_cols_map[col.lower()],
            "operator": op,
            "value": val
        })
    return validated


def create_or_update_metric(
    user_id: str,
    name: str,
    source_dataset: str,
    expression: str,
    supported_aggregation: str = "SUM",
    description: str = "",
    approved_aliases: Optional[List[str]] = None,
    optional_filters: Optional[List[Dict[str, Any]]] = None,
    currency_unit: str = "",
    metric_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Creates or updates a business metric in the registry after validating
    ownership, dataset authorization, and safe expression compilation.
    """
    db: Session = SessionLocal()
    try:
        # 1. Clean inputs
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Metric name cannot be empty.")

        clean_aliases = [a.strip().lower() for a in (approved_aliases or []) if a and a.strip()]
        # Always include the name itself as a normalized alias
        if clean_name.lower() not in clean_aliases:
            clean_aliases.insert(0, clean_name.lower())

        # 2. Verify authorized dataset columns
        allowed_cols = get_authorized_dataset_columns(source_dataset, user_id)

        # 3. Validate expression & compilation
        compiled_sql, relevant_cols = validate_and_compile_expression(
            expression=expression,
            allowed_columns=allowed_cols,
            aggregation=supported_aggregation
        )

        # 4. Validate optional filters
        validated_filters = validate_filter_definition(optional_filters or [], allowed_cols)

        # 5. Save to database
        if metric_id:
            metric = db.query(BusinessMetric).filter(
                BusinessMetric.id == metric_id,
                BusinessMetric.user_id == user_id
            ).first()
            if not metric:
                raise ValueError(f"Metric with ID {metric_id} not found or access denied.")
            metric.name = clean_name
            metric.description = description
            metric.approved_aliases = json.dumps(clean_aliases)
            metric.source_dataset = source_dataset
            metric.supported_aggregation = supported_aggregation.upper()
            metric.relevant_columns = json.dumps(relevant_cols)
            metric.expression = expression.strip()
            metric.optional_filters = json.dumps(validated_filters)
            metric.currency_unit = currency_unit.strip()
            metric.version += 1
        else:
            # Check for duplicate metric name within user workspace
            existing = db.query(BusinessMetric).filter(
                BusinessMetric.user_id == user_id,
                BusinessMetric.name == clean_name,
                BusinessMetric.source_dataset == source_dataset
            ).first()
            if existing:
                metric = existing
                metric.description = description
                metric.approved_aliases = json.dumps(clean_aliases)
                metric.supported_aggregation = supported_aggregation.upper()
                metric.relevant_columns = json.dumps(relevant_cols)
                metric.expression = expression.strip()
                metric.optional_filters = json.dumps(validated_filters)
                metric.currency_unit = currency_unit.strip()
                metric.version += 1
            else:
                metric = BusinessMetric(
                    user_id=user_id,
                    name=clean_name,
                    description=description,
                    approved_aliases=json.dumps(clean_aliases),
                    source_dataset=source_dataset,
                    supported_aggregation=supported_aggregation.upper(),
                    relevant_columns=json.dumps(relevant_cols),
                    expression=expression.strip(),
                    optional_filters=json.dumps(validated_filters),
                    currency_unit=currency_unit.strip(),
                    version=1
                )
                db.add(metric)

        db.commit()
        db.refresh(metric)
        return metric.to_dict()
    finally:
        db.close()


def list_metrics(user_id: str, source_dataset: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lists all metrics owned by the user, optionally filtered by dataset.
    """
    db: Session = SessionLocal()
    try:
        query = db.query(BusinessMetric).filter(BusinessMetric.user_id == user_id)
        if source_dataset:
            query = query.filter(
                (BusinessMetric.source_dataset == source_dataset) |
                (BusinessMetric.source_dataset == "*")
            )
        metrics = query.order_by(BusinessMetric.name.asc()).all()
        return [m.to_dict() for m in metrics]
    finally:
        db.close()


def get_metric(metric_id: int, user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single metric by ID with ownership check.
    """
    db: Session = SessionLocal()
    try:
        metric = db.query(BusinessMetric).filter(
            BusinessMetric.id == metric_id,
            BusinessMetric.user_id == user_id
        ).first()
        return metric.to_dict() if metric else None
    finally:
        db.close()


def delete_metric(metric_id: int, user_id: str) -> bool:
    """
    Deletes a metric with strict user authorization.
    """
    db: Session = SessionLocal()
    try:
        metric = db.query(BusinessMetric).filter(
            BusinessMetric.id == metric_id,
            BusinessMetric.user_id == user_id
        ).first()
        if not metric:
            return False
        db.delete(metric)
        db.commit()
        return True
    finally:
        db.close()


def resolve_metrics_for_phrase(
    phrase: str,
    user_id: str,
    source_dataset: str
) -> List[Dict[str, Any]]:
    """
    Matches a natural language term or question against approved metric names and aliases.
    Returns list of matched registered metrics.
    """
    metrics = list_metrics(user_id, source_dataset)
    phrase_lower = phrase.lower().strip()
    matches = []

    for m in metrics:
        name_lower = m["name"].lower()
        aliases = [a.lower() for a in m.get("approved_aliases", [])]

        # Exact match on name
        if phrase_lower == name_lower or name_lower in phrase_lower:
            matches.append(m)
            continue

        # Match on aliases
        matched_alias = False
        for alias in aliases:
            if alias == phrase_lower or alias in phrase_lower:
                matches.append(m)
                matched_alias = True
                break

    return matches
