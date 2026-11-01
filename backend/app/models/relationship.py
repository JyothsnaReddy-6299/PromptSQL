"""Logical dataset catalog and user-approved analytical relationships."""
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime
from app.database.connection import Base
from app.utils.tz_helper import get_ist_time

class DatasetReference(Base):
    __tablename__ = 'dataset_references'
    id = Column(String(64), primary_key=True)
    owner_id = Column(String(50), nullable=False, index=True)
    physical_name = Column(String(100), nullable=False, unique=True)
    label = Column(String(100), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    schema_fingerprint = Column(String(64), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=get_ist_time)

class DatasetRelationship(Base):
    __tablename__ = 'dataset_relationships'
    id = Column(String(64), primary_key=True)
    owner_id = Column(String(50), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    left_dataset_id = Column(String(64), nullable=False, index=True)
    right_dataset_id = Column(String(64), nullable=False, index=True)
    keys_json = Column(Text, nullable=False)
    join_type = Column(String(10), nullable=False)
    profile_json = Column(Text, nullable=False)
    versions_json = Column(Text, nullable=False)
    approved = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    needs_revalidation = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=get_ist_time)
    updated_at = Column(DateTime, nullable=False, default=get_ist_time)
