from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.connection import engine, Base
# Import models to ensure they are registered with Base before metadata.create_all
from app.models.history import QueryHistory
from app.models.report import SavedReport
from app.models.audit_log import AuditLog
from app.models.user import User

from app.routes.upload import router as upload_router
from app.routes.ask import router as ask_router
from app.routes.export import router as export_router
from app.routes.history import router as history_router
from app.routes.report import router as report_router
from app.routes.modification import router as modification_router
from app.routes.audit import router as audit_router
from app.routes.cleaner import router as cleaner_router
from app.routes.auth import router as auth_router

# Auto-initialize database tables in MySQL
Base.metadata.create_all(bind=engine)

# Self-healing database check to automatically add undo_sql column to existing query_history table
def check_and_add_undo_column():
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(engine)
        if "query_history" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("query_history")]
            if "undo_sql" not in columns:
                print("[STARTUP] Adding 'undo_sql' column to query_history table...")
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE query_history ADD COLUMN undo_sql TEXT NULL"))
                    conn.execute(text("COMMIT"))
                print("[STARTUP] 'undo_sql' column added successfully!")
    except Exception as e:
        print("[STARTUP] Failed database schema check for undo_sql column:", e)

check_and_add_undo_column()

app = FastAPI(title="AI Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(ask_router)
app.include_router(export_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(report_router, prefix="/api")
app.include_router(modification_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(cleaner_router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok", "message": "Backend is running"}


# Serve static files from frontend build
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "frontend",
        "dist"
    )
)

if os.path.exists(frontend_dist):
    print(f"Serving frontend static files from: {frontend_dist}")

    # Mount /assets directory if it exists
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="static"
        )

    # Route for serving index.html for client-side routing
    @app.get("/{catchall:path}")
    def serve_frontend(catchall: str):
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"error": f"Frontend index.html not found at {index_path}."}
else:
    print(f"Frontend dist directory not found at: {frontend_dist}")

    @app.get("/")
    def home():
        return {
            "message": "Backend is running. Frontend build not found.",
            "build_path": frontend_dist
        }