import os
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.database.connection import engine, Base
from app.utils.error_sanitizer import get_safe_exception_message

# Import models to ensure they are registered with Base before metadata.create_all
from app.models.history import QueryHistory
from app.models.report import SavedReport
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.pending_modification import PendingModification
from app.models.user_active_dataset import UserActiveDataset

from app.routes.upload import router as upload_router
from app.routes.ask import router as ask_router
from app.routes.export import router as export_router
from app.routes.history import router as history_router
from app.routes.report import router as report_router
from app.routes.modification import router as modification_router
from app.routes.audit import router as audit_router
from app.routes.cleaner import router as cleaner_router
from app.routes.auth import router as auth_router

settings = get_settings()

# Auto-initialize database tables in MySQL with startup fault tolerance
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"[STARTUP WARNING] Failed creating database tables: {e}")


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
        print("[STARTUP WARNING] Database schema check for undo_sql column:", e)


try:
    check_and_add_undo_column()
except Exception as e:
    print(f"[STARTUP WARNING] Failed running startup schema checks: {e}")

app = FastAPI(
    title="PromptSQL API",
    debug=settings.DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global sanitized exception handlers to protect against internal secret exposure
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    safe_detail = get_safe_exception_message(exc, is_production=settings.is_production)
    content = {"detail": safe_detail, "error": safe_detail, "success": False} if exc.status_code >= 400 else {"detail": safe_detail}
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=exc.headers
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    safe_detail = get_safe_exception_message(exc, is_production=settings.is_production, context="database operation")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "error": safe_detail, "detail": safe_detail}
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    safe_detail = get_safe_exception_message(exc, is_production=settings.is_production, context="request")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"success": False, "error": safe_detail, "detail": safe_detail}
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
    return {
        "status": "ok",
        "message": "Backend is running",
        "environment": settings.APP_ENV
    }


# Serve static files from frontend build
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
