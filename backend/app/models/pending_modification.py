import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from app.database.connection import Base
from app.utils.tz_helper import get_ist_time


class PendingModification(Base):
    __tablename__ = "pending_modifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(String(50), index=True, nullable=False)
    table_name = Column(String(100), nullable=False)
    question = Column(Text, nullable=False)
    intent = Column(String(20), nullable=False)
    execution_policy = Column(String(20), default="DML", nullable=False)  # DML or DDL
    sql_to_execute = Column(Text, nullable=False)
    estimated_rows = Column(Integer, nullable=True)  # Null if impact could not be estimated reliably
    actual_rows_affected = Column(Integer, nullable=True)
    impact_explanation = Column(Text, nullable=True)
    warning = Column(Text, nullable=True)
    status = Column(String(30), default="PENDING", nullable=False)
    # Terminal & lifecycle statuses:
    # PENDING -> EXECUTING -> EXECUTED
    #                     -> FAILED
    #                     -> EXPIRED
    #                     -> UNKNOWN
    #                     -> BOOKKEEPING_FAILED
    status_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_ist_time, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    started_executing_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)
