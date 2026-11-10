from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

settings = get_settings()

DATABASE_URL = settings.resolved_database_url

# Configure SSL for remote managed databases (Aiven, AWS RDS, PlanetScale, etc.)
connect_args = {}
if settings.is_remote_db:
    connect_args = {
        "ssl": {
            "check_hostname": False
        }
    }

engine = create_engine(
    DATABASE_URL, 
    echo=settings.DEBUG, 
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()
