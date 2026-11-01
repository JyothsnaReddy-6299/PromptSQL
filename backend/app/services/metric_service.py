import json
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from app.database.connection import SessionLocal, engine
from app.models.metric import BusinessMetric
from app.services.metric_parser import validate_and_compile_expression


def normalize_aliases(aliases: Optional[List[str]], name: str) -> List[str]:
    """
    Normalizes and deduplicates aliases:
    - Lowercases, strips punctuation/whitespace.
    - Preserves order while removing duplicates.
    - Always ensures the metric name itself is included.
    """
    seen = set()
    deduped = []

    clean_name = name.strip().lower()
    if clean_name:
        seen.add(clean_name)
        deduped.append(clean_name)

    for a in aliases or []:
        if not a:
            continue
        clean = a.strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            deduped.append(clean)

    return deduped


def get_authorized_dataset_columns(table_name: str, user_id: str) -> List[str]:
    """
    Returns list of authorized column names for a dataset table owned by user.
    Hides internal surrogate keys like '_row_id'.
    """
    if not table_name.endswith(f"_{user_id}"):
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
    is_default: bool = False,
    default_concept: Optional[str] = None,
    metric_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Creates or updates a business metric in the registry after validating
    ownership, dataset authorization, and safe expression compilation.
    """
    db: Session = SessionLocal()
    try:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Metric name cannot be empty.")

        clean_aliases = normalize_aliases(approved_aliases, clean_name)

        # Verify authorized dataset columns
        allowed_cols = get_authorized_dataset_columns(source_dataset, user_id)

        # Validate expression & compilation
        compiled_sql, relevant_cols = validate_and_compile_expression(
            expression=expression,
            allowed_columns=allowed_cols,
            aggregation=supported_aggregation
        )

        # Validate optional filters
        validated_filters = validate_filter_definition(optional_filters or [], allowed_cols)

        # Normalize dataset reference
        clean_dataset = source_dataset.strip()

        if is_default and default_concept:
            # Clear any other defaults for this dataset and concept
            friendly_ds = clean_dataset.split("_usr_")[0]
            existing_defaults = db.query(BusinessMetric).filter(
                BusinessMetric.user_id == user_id,
                (BusinessMetric.source_dataset == clean_dataset) | (BusinessMetric.source_dataset == friendly_ds),
                BusinessMetric.default_concept == default_concept
            ).all()
            for ed in existing_defaults:
                if not metric_id or ed.id != metric_id:
                    ed.is_default = False

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
            metric.source_dataset = clean_dataset
            metric.supported_aggregation = supported_aggregation.upper()
            metric.relevant_columns = json.dumps(relevant_cols)
            metric.expression = expression.strip()
            metric.optional_filters = json.dumps(validated_filters)
            metric.currency_unit = currency_unit.strip()
            if is_default:
                metric.is_default = True
                metric.default_concept = default_concept or "sales"
            metric.version += 1
        else:
            friendly_ds = clean_dataset.split("_usr_")[0]
            existing = db.query(BusinessMetric).filter(
                BusinessMetric.user_id == user_id,
                BusinessMetric.name == clean_name,
                (BusinessMetric.source_dataset == clean_dataset) | (BusinessMetric.source_dataset == friendly_ds)
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
                if is_default:
                    metric.is_default = True
                    metric.default_concept = default_concept or "sales"
                metric.version += 1
            else:
                metric = BusinessMetric(
                    user_id=user_id,
                    name=clean_name,
                    description=description,
                    approved_aliases=json.dumps(clean_aliases),
                    source_dataset=clean_dataset,
                    supported_aggregation=supported_aggregation.upper(),
                    relevant_columns=json.dumps(relevant_cols),
                    expression=expression.strip(),
                    optional_filters=json.dumps(validated_filters),
                    currency_unit=currency_unit.strip(),
                    is_default=is_default,
                    default_concept=default_concept if is_default else None,
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
    Lists all metrics owned by the user, matching either physical or friendly dataset name.
    """
    db: Session = SessionLocal()
    try:
        query = db.query(BusinessMetric).filter(BusinessMetric.user_id == user_id)
        if source_dataset:
            friendly_ds = source_dataset.split("_usr_")[0] if "_usr_" in source_dataset else source_dataset
            query = query.filter(
                (BusinessMetric.source_dataset == source_dataset) |
                (BusinessMetric.source_dataset == friendly_ds) |
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


def set_default_metric(user_id: str, metric_id: int, concept: str = "sales") -> Dict[str, Any]:
    """
    Sets a metric as the default resolution for a concept (e.g. 'sales') on its dataset.
    """
    db: Session = SessionLocal()
    try:
        metric = db.query(BusinessMetric).filter(
            BusinessMetric.id == metric_id,
            BusinessMetric.user_id == user_id
        ).first()
        if not metric:
            raise ValueError(f"Metric with ID {metric_id} not found or access denied.")

        friendly_ds = metric.source_dataset.split("_usr_")[0]
        # Clear existing defaults for this dataset & concept
        existing = db.query(BusinessMetric).filter(
            BusinessMetric.user_id == user_id,
            (BusinessMetric.source_dataset == metric.source_dataset) | (BusinessMetric.source_dataset == friendly_ds),
            BusinessMetric.default_concept == concept
        ).all()
        for e in existing:
            e.is_default = False

        metric.is_default = True
        metric.default_concept = concept
        db.commit()
        db.refresh(metric)
        return metric.to_dict()
    finally:
        db.close()


def reset_default_metric(user_id: str, source_dataset: str, concept: Optional[str] = None) -> bool:
    """
    Resets/clears the default metric for a dataset.
    """
    db: Session = SessionLocal()
    try:
        friendly_ds = source_dataset.split("_usr_")[0] if "_usr_" in source_dataset else source_dataset
        query = db.query(BusinessMetric).filter(
            BusinessMetric.user_id == user_id,
            (BusinessMetric.source_dataset == source_dataset) | (BusinessMetric.source_dataset == friendly_ds)
        )
        if concept:
            query = query.filter(BusinessMetric.default_concept == concept)
        metrics = query.all()
        for m in metrics:
            m.is_default = False
            m.default_concept = None
        db.commit()
        return True
    finally:
        db.close()


def get_default_metric(user_id: str, source_dataset: str, concept: str = "sales") -> Optional[Dict[str, Any]]:
    """
    Retrieves the saved default metric for a dataset and concept, if one exists.
    """
    db: Session = SessionLocal()
    try:
        friendly_ds = source_dataset.split("_usr_")[0] if "_usr_" in source_dataset else source_dataset
        metric = db.query(BusinessMetric).filter(
            BusinessMetric.user_id == user_id,
            (BusinessMetric.source_dataset == source_dataset) | (BusinessMetric.source_dataset == friendly_ds),
            BusinessMetric.is_default == True,
            BusinessMetric.default_concept == concept
        ).first()
        return metric.to_dict() if metric else None
    finally:
        db.close()


def resolve_metrics_for_phrase(
    phrase: str,
    user_id: str,
    source_dataset: str
) -> List[Dict[str, Any]]:
    """
    Matches a natural language term or question against approved metric names and aliases.
    Detects if multiple distinct metrics share conflicting aliases.
    """
    metrics = list_metrics(user_id, source_dataset)
    phrase_lower = phrase.lower().strip()
    matches = []

    for m in metrics:
        name_lower = m["name"].lower()
        aliases = [a.lower() for a in m.get("approved_aliases", [])]

        # Exact match or word boundary match on name
        if phrase_lower == name_lower or re.search(rf"\b{re.escape(name_lower)}\b", phrase_lower):
            if m not in matches:
                matches.append(m)
            continue

        # Match on aliases
        for alias in aliases:
            if phrase_lower == alias or re.search(rf"\b{re.escape(alias)}\b", phrase_lower):
                if m not in matches:
                    matches.append(m)
                break

    return matches
