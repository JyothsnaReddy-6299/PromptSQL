from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from app.database.connection import Base


class UserActiveDataset(Base):
    """
    Persists per-user active dataset selection in the database.
    Guarantees atomic consistency across multiple worker processes and containers.
    """
    __tablename__ = "user_active_datasets"

    user_id = Column(String(50), primary_key=True, index=True)
    table_name = Column(String(100), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
