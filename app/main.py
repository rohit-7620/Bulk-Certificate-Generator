"""FastAPI application entry point.

On startup:
1. Initialize database (create tables)
2. Recover stale PROCESSING jobs (mark as FAILED)
3. Register routes
"""
import os
from fastapi import FastAPI
from app.database import init_db, get_db
from app.routes import jobs
from app.services.processor import recover_stale_jobs

app = FastAPI(
    title="Bulk Certificate Generator API",
    description="Generate PDF certificates in bulk with background processing",
    version="1.0.0",
)


# Only run startup tasks if not in test mode
if not os.getenv("TESTING"):
    @app.on_event("startup")
    def startup_event():
        """Initialize database and recover stale jobs on startup."""
        init_db()
        
        # Recover any jobs that were PROCESSING when server crashed
        db = next(get_db())
        try:
            recover_stale_jobs(db)
        finally:
            db.close()


# Register routes
app.include_router(jobs.router)


@app.get("/")
def root():
    """Health check / API info."""
    return {
        "service": "Bulk Certificate Generator API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }
