"""Pytest fixtures for isolated test environment.

Each test gets:
- Fresh in-memory SQLite database
- Isolated temporary storage directory
- TestClient for API calls
"""
import os
import tempfile
import shutil
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.config import settings

# Set testing flag to skip startup events (must be set BEFORE importing app)
os.environ["TESTING"] = "1"

# Now import app
from app.main import app


@pytest.fixture(scope="function")
def temp_storage():
    """Create a temporary storage directory for each test."""
    temp_dir = tempfile.mkdtemp()
    original_storage = settings.storage_dir
    settings.storage_dir = temp_dir
    yield temp_dir
    settings.storage_dir = original_storage
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def test_db_engine(temp_storage):
    """Create a test database engine and session maker."""
    from sqlalchemy import event
    from app.models import Job, JobItem  # Import models BEFORE creating tables
    
    # Create fresh test database with StaticPool to share connections
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # IMPORTANT: Share connections so all see the same DB
    )
    
    # Enable foreign keys for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session maker
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    yield TestingSessionLocal, engine
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_db(test_db_engine):
    """Get the session maker for direct database access."""
    return test_db_engine[0]


@pytest.fixture(scope="function")
def client(test_db_engine):
    """FastAPI TestClient with isolated database and storage."""
    TestingSessionLocal, engine = test_db_engine
    
    # Override the dependency FIRST
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    try:
        # Create client AFTER override is set
        client = TestClient(app)
        yield client
    finally:
        # Cleanup
        app.dependency_overrides.clear()
