from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database.connection import Base
from app.utils.tz_helper import get_ist_time


class PrivacyColumnPolicy(Base):
    """
    Persists detected sensitivity categories, confidence levels, and active privacy policies
    for columns across user datasets.
    """
    __tablename__ = "privacy_column_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    table_name = Column(String(100), nullable=False, index=True)
    column_name = Column(String(100), nullable=False)
    detected_category = Column(String(50), nullable=False)
    sensitivity_level = Column(String(20), nullable=False)  # low, medium, high, critical
    detection_method = Column(String(50), nullable=False)  # pattern_match, checksum_verified, semantic_heuristic, hybrid_sampling
    confidence = Column(String(20), nullable=False)  # high, medium, low, requires_review
    policy = Column(String(20), nullable=False, default="normal")  # normal, sensitive, restricted, custom
    status = Column(String(20), nullable=False, default="normal")  # protected, pending_review, configured, normal
    explanation = Column(Text, nullable=True)
    sample_patterns = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=get_ist_time, nullable=False)
    updated_at = Column(DateTime, default=get_ist_time, onupdate=get_ist_time, nullable=False)


class PrivacyAuditLog(Base):
    """
    Persists privacy-related audit events (scans, policy changes, redaction events, blocked transmissions).
    CRITICAL: Never stores raw sensitive values in the audit details.
    """
    __tablename__ = "privacy_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, index=True)
    table_name = Column(String(100), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # dataset_scan, policy_change, classification_change, ai_boundary_redaction, blocked_transmission
    details = Column(Text, nullable=False)  # Sanitized JSON summary
    timestamp = Column(DateTime, default=get_ist_time, nullable=False)
