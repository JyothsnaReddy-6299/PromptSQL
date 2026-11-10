from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env_path = os.path.join(base_dir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
load_dotenv()

# Support both unified DATABASE_URL (standard on Render/Railway/Heroku) and individual MySQL variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    MYSQL_USER = os.getenv("MYSQL_USER")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
    MYSQL_HOST = os.getenv("MYSQL_HOST")
    MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")
    if MYSQL_USER and MYSQL_HOST and MYSQL_DATABASE:
        DATABASE_URL = (
            f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
            f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
        )
    else:
        # Fallback to local default if no environment variables are provided
        DATABASE_URL = "mysql+pymysql://root:@localhost:3306/promptsql"

# Normalize mysql:// schema to mysql+pymysql:// for PyMySQL adapter compatibility
if DATABASE_URL.startswith("mysql://"):
    DATABASE_URL = DATABASE_URL.replace("mysql://", "mysql+pymysql://", 1)

# Configure SSL for remote managed databases (Aiven, AWS RDS, PlanetScale, etc.)
connect_args = {}
is_remote = (
    ("localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL)
    or "aivencloud" in DATABASE_URL
    or "amazonaws" in DATABASE_URL
    or "ssl" in DATABASE_URL
)
if is_remote:
    connect_args = {
        "ssl": {
            "check_hostname": False
        }
    }

engine = create_engine(
    DATABASE_URL, 
    echo=False, 
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()
