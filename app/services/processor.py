"""Background job processor with per-item error isolation.

Design decisions:
- Each certificate generation is wrapped in try/except to isolate failures
- Progress is committed per-item so status is visible during processing
- Duplicate emails are detected and marked as FAILED
- Function is sync and plain (no async/Celery) so tests can call it directly

Trade-off: BackgroundTasks loses work on restart. For production, use Celery/RQ with Redis.
On startup, we mark stale PROCESSING jobs as FAILED (simple approach).
"""
import os
import traceback
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Job, JobItem
from app.services.certificate import generate_certificate_pdf
from app.config import settings


def process_job(job_id: str, db_session_maker):
    """
    Process a certificate generation job.
    
    This function:
    1. Marks job as PROCESSING
    2. Detects duplicate emails and marks them as FAILED
    3. For each valid recipient, generates a PDF (wrapped in try/except)
    4. Updates item status and job progress after each certificate
    5. Marks job as COMPLETED / COMPLETED_WITH_ERRORS / FAILED
    
    Args:
        job_id: UUID of the job to process
        db_session_maker: SQLAlchemy sessionmaker (not a session, so we control commits)
    """
    # Create a fresh session for this background task
    db = db_session_maker()
    
    try:
        # Load job and items
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return  # Job deleted or not found
        
        # Mark job as processing
        job.status = "PROCESSING"
        db.commit()
        
        # Load all items for this job
        items = db.query(JobItem).filter(JobItem.job_id == job_id).all()
        
        # Check for duplicate emails and mark them as FAILED
        # Strategy: first occurrence is valid, subsequent duplicates are marked failed
        seen_emails = {}
        for item in items:
            email_lower = item.email.lower()
            if email_lower in seen_emails:
                item.status = "FAILED"
                item.error_message = f"Duplicate email address (first occurrence: item {seen_emails[email_lower]})"
                db.commit()
            else:
                seen_emails[email_lower] = item.id
        
        # Process each item that's still PENDING
        for item in items:
            if item.status != "PENDING":
                continue  # Already marked as FAILED (duplicate) or previously processed
            
            try:
                # Generate PDF
                cert_id = f"cert_{job_id}_{item.id}"
                file_name = f"{cert_id}.pdf"
                relative_path = os.path.join(job_id, file_name)
                full_path = os.path.join(settings.storage_dir, relative_path)
                
                generate_certificate_pdf(
                    output_path=full_path,
                    title=job.title,
                    recipient_name=item.name,
                    issuer=job.issuer,
                    issue_date=job.issue_date,
                    achievement=item.achievement,
                )
                
                # Mark as success
                item.status = "SUCCESS"
                item.file_path = relative_path
                db.commit()
                
            except Exception as e:
                # Isolate failure: record error and continue with other items
                item.status = "FAILED"
                item.error_message = f"{type(e).__name__}: {str(e)}"
                db.commit()
                
                # Log for debugging (in production, use proper logging)
                print(f"Failed to generate certificate for item {item.id}: {e}")
                traceback.print_exc()
        
        # Update final job status
        db.refresh(job)  # Reload to get fresh item relationships
        items = db.query(JobItem).filter(JobItem.job_id == job_id).all()
        
        succeeded = sum(1 for item in items if item.status == "SUCCESS")
        failed = sum(1 for item in items if item.status == "FAILED")
        pending = sum(1 for item in items if item.status == "PENDING")
        
        if pending > 0:
            # Should not happen, but handle gracefully
            job.status = "FAILED"
        elif failed > 0 and succeeded > 0:
            job.status = "COMPLETED_WITH_ERRORS"
        elif failed == len(items):
            job.status = "FAILED"
        else:
            job.status = "COMPLETED"
        
        job.completed_at = datetime.utcnow()
        db.commit()
        
    except Exception as e:
        # Unexpected error in the processor itself
        print(f"Fatal error processing job {job_id}: {e}")
        traceback.print_exc()
        
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "FAILED"
                job.completed_at = datetime.utcnow()
                db.commit()
        except:
            pass  # Best effort
    
    finally:
        db.close()


def recover_stale_jobs(db: Session):
    """
    On startup, mark any PROCESSING jobs as FAILED.
    
    This handles the case where the server crashed mid-processing.
    Alternative: resume processing (more complex, needs job queue persistence).
    
    Called from main.py on startup.
    """
    stale_jobs = db.query(Job).filter(Job.status == "PROCESSING").all()
    for job in stale_jobs:
        job.status = "FAILED"
        job.completed_at = datetime.utcnow()
    
    if stale_jobs:
        db.commit()
        print(f"Recovered {len(stale_jobs)} stale PROCESSING jobs (marked as FAILED)")
