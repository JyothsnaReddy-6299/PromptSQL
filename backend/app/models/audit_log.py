from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime

from app.database.connection import Base
from app.utils.tz_helper import get_ist_time


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="default_user", nullable=False)
    timestamp = Column(DateTime, default=get_ist_time, nullable=False)#nullable=False means it cannot be empty
    operation = Column(String(50), nullable=False)  # INSERT, UPDATE, DELETE, etc.
    table_name = Column(String(100), nullable=False)
    generated_sql = Column(Text, nullable=False)
    rows_affected = Column(Integer, default=0, nullable=False)
    status = Column(String(20), nullable=False)  # SUCCESS, FAILURE
    error_message = Column(Text, nullable=True)
