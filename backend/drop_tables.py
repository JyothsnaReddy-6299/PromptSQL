from app.database.connection import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS query_history"))
        conn.execute(text("DROP TABLE IF EXISTS saved_reports"))
        conn.execute(text("DROP TABLE IF EXISTS audit_logs"))
        # Commit manually if not in autocommit mode
        conn.execute(text("COMMIT"))
    print("Tables dropped successfully!")
except Exception as e:
    print("Error dropping tables:", e)
