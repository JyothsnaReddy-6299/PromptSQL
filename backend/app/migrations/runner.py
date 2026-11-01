"""Additive, versioned migrations. No uploaded data is rewritten."""
from sqlalchemy import MetaData, Table, Column, String, DateTime, select
from app.utils.tz_helper import get_ist_time
from app.models.relationship import DatasetReference, DatasetRelationship

VERSION = '001_relationship_manager'

def migrate(engine):
    metadata = MetaData()
    versions = Table('promptsql_migrations', metadata,
        Column('version', String(80), primary_key=True), Column('applied_at', DateTime, nullable=False))
    metadata.create_all(engine)
    with engine.begin() as conn:
        if conn.execute(select(versions.c.version).where(versions.c.version == VERSION)).first():
            return
        DatasetReference.__table__.create(conn, checkfirst=True)
        DatasetRelationship.__table__.create(conn, checkfirst=True)
        conn.execute(versions.insert().values(version=VERSION, applied_at=get_ist_time()))

if __name__ == '__main__':
    from app.database.connection import engine
    migrate(engine)
