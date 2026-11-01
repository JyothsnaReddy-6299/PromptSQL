from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
import json
from app.utils.tz_helper import get_ist_time
from app.database.connection import Base


class BusinessMetric(Base):
    __tablename__ = "business_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    approved_aliases = Column(Text, nullable=True)  # JSON string: ["sales", "turnover"]
    source_dataset = Column(String(100), nullable=False)  # friendly dataset name or table name
    supported_aggregation = Column(String(30), default="SUM", nullable=False)  # SUM, AVG, COUNT, COUNT_DISTINCT, MIN, MAX
    relevant_columns = Column(Text, nullable=False)  # JSON string: ["Unit_Price", "Quantity_Ordered"]
    expression = Column(String(255), nullable=True)  # Limited arithmetic expression e.g. "Unit_Price * Quantity_Ordered" or column name
    optional_filters = Column(Text, nullable=True)  # JSON string: [{"column": "status", "operator": "!=", "value": "cancelled"}]
    currency_unit = Column(String(50), nullable=True)  # e.g. "USD", "$", "units", "orders"
    version = Column(Integer, default=1, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    default_concept = Column(String(50), nullable=True)  # e.g. "sales"
    created_at = Column(DateTime, default=get_ist_time, nullable=False)
    updated_at = Column(DateTime, default=get_ist_time, onupdate=get_ist_time, nullable=False)

    def to_dict(self):
        def safe_json_load(raw, fallback):
            if not raw:
                return fallback
            try:
                return json.loads(raw)
            except Exception:
                return fallback

        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description or "",
            "approved_aliases": safe_json_load(self.approved_aliases, []),
            "source_dataset": self.source_dataset,
            "supported_aggregation": self.supported_aggregation,
            "relevant_columns": safe_json_load(self.relevant_columns, []),
            "expression": self.expression or "",
            "optional_filters": safe_json_load(self.optional_filters, []),
            "currency_unit": self.currency_unit or "",
            "version": self.version,
            "is_default": bool(self.is_default),
            "default_concept": self.default_concept or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
