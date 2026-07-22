from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from app.utils.tz_helper import get_ist_time

from app.database.connection import Base


class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), default="default_user", nullable=False)
    table_name = Column(String(100), nullable=False)
    question = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    result_count = Column(Integer, default=0, nullable=False)
    result_json = Column(Text(16777215), nullable=True)  # Store query output records for offline reopenings
    timestamp = Column(DateTime, default=get_ist_time, nullable=False)
