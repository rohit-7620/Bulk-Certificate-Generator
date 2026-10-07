"""SQLAlchemy models for jobs and job items.

Design decisions:
- UUIDs for job IDs (more opaque, RESTful)
- Integer IDs for items (simpler, scoped within a job)
- Index on job_id for fast item lookups
- Status enums as strings for readability in DB browser
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False)
    issuer = Column(String(200), nullable=False)
    issue_date = Column(String(10), nullable=False)  # YYYY-MM-DD format
    
    # Status: PENDING -> PROCESSING -> COMPLETED / COMPLETED_WITH_ERRORS / FAILED
    status = Column(String(50), nullable=False, default="PENDING")
    
    total_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationship to items
    items = relationship("JobItem", back_populates="job", cascade="all, delete-orphan")


class JobItem(Base):
    __tablename__ = "job_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False)
    achievement = Column(String(200), nullable=True)  # Optional extra field
    
    # Status: PENDING -> SUCCESS / FAILED
    status = Column(String(50), nullable=False, default="PENDING")
    error_message = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)  # Relative path under storage/
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship back to job
    job = relationship("Job", back_populates="items")


# Explicit index for faster job_id queries (already created by index=True above, but explicit is clear)
Index("idx_job_items_job_id", JobItem.job_id)
