from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.connection import engine, Base
# Import models to ensure they are registered with Base before metadata.create_all
from app.models.history import QueryHistory
from app.models.report import SavedReport
from app.models.audit_log import AuditLog

from app.routes.upload import router as upload_router
from app.routes.ask import router as ask_router
from app.routes.export import router as export_router
from app.routes.history import router as history_router
from app.routes.report import router as report_router
from app.routes.modification import router as modification_router
from app.routes.audit import router as audit_router

# Auto-initialize database tables in MySQL
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(ask_router)
app.include_router(export_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(report_router, prefix="/api")
app.include_router(modification_router, prefix="/api")
app.include_router(audit_router, prefix="/api")

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