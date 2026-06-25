from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
<<<<<<< HEAD
from dotenv import load_dotenv
import os

load_dotenv()

DB_USER = os.getenv("MYSQL_USER")
DB_PASS = os.getenv("MYSQL_PASSWORD")
DB_HOST = os.getenv("MYSQL_HOST")
DB_PORT = os.getenv("MYSQL_PORT")
DB_NAME = os.getenv("MYSQL_DATABASE")

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASS}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL, echo=False)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

=======

DATABASE_URL = "mysql+pymysql://root:your_password@localhost/ai_analytics"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

>>>>>>> 5c5ce2251e911f794b066c7be088e1183b3f9cdb
Base = declarative_base()