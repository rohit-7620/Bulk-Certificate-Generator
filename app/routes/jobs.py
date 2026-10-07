"""API routes for certificate job management.

Endpoints:
- POST /jobs: Create a new bulk certificate job
- GET /jobs/{job_id}: Get job status and items (with filtering and pagination)
- GET /jobs/{job_id}/certificates/{item_id}: Download single certificate PDF
- GET /jobs/{job_id}/download: Download all successful certificates as ZIP
"""
import os
import zipfile
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.models import Job, JobItem
from app.schemas import CreateJobRequest, CreateJobResponse, JobStatusResponse, JobItemResponse
from app.services.processor import process_job
from app.config import settings

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=CreateJobResponse, status_code=202)
def create_job(
    request: CreateJobRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Create a bulk certificate generation job.
    
    Returns 202 Accepted immediately and processes certificates in the background.
    Invalid recipients (empty names, malformed emails) are marked as FAILED items.
    Only rejects with 422 if the request itself is malformed (missing required fields, etc.).
    """
    # Use today's date if not provided
    issue_date_str = request.issue_date.isoformat() if request.issue_date else date.today().isoformat()
    
    # Create job record
    job = Job(
        title=request.title,
        issuer=request.issuer,
        issue_date=issue_date_str,
        status="PENDING",
        total_count=len(request.recipients),
    )
    db.add(job)
    db.flush()  # Get job.id before creating items
    
    # Create items for all recipients (even if some are invalid)
    # Validation errors are stored as FAILED items rather than rejecting the request
    for recipient in request.recipients:
        # Basic validation already done by Pydantic, but double-check name
        if not recipient.name or not recipient.name.strip():
            # Mark as failed immediately
            item = JobItem(
                job_id=job.id,
                name="[Invalid]",
                email=recipient.email,
                achievement=recipient.achievement,
                status="FAILED",
                error_message="Name is empty or whitespace only",
            )
        else:
            item = JobItem(
                job_id=job.id,
                name=recipient.name.strip(),
                email=recipient.email,
                achievement=recipient.achievement,
                status="PENDING",
            )
        db.add(item)
    
    db.commit()
    
    # Schedule background processing
    # Pass SessionLocal (the maker) not the session, so processor creates its own
    background_tasks.add_task(process_job, job.id, SessionLocal)
    
    return CreateJobResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        message=f"Job created with {job.total_count} recipients. Processing started.",
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    status: Optional[str] = Query(None, description="Filter items by status (SUCCESS, FAILED, PENDING)"),
    limit: int = Query(100, ge=1, le=1000, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Items to skip"),
    db: Session = Depends(get_db),
):
    """
    Get job status, progress, and list of items.
    
    Supports:
    - Filtering by status (e.g., ?status=FAILED to see only failures)
    - Pagination via limit/offset
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Build item query with optional status filter
    items_query = db.query(JobItem).filter(JobItem.job_id == job_id)
    if status:
        items_query = items_query.filter(JobItem.status == status.upper())
    
    # Apply pagination
    items = items_query.offset(offset).limit(limit).all()
    
    # Calculate counts from all items (not just the paginated subset)
    all_items = db.query(JobItem).filter(JobItem.job_id == job_id).all()
    succeeded = sum(1 for item in all_items if item.status == "SUCCESS")
    failed = sum(1 for item in all_items if item.status == "FAILED")
    pending = sum(1 for item in all_items if item.status == "PENDING")
    
    # Build response items with download URLs
    response_items = []
    for item in items:
        download_url = None
        if item.status == "SUCCESS" and item.file_path:
            download_url = f"/jobs/{job_id}/certificates/{item.id}"
        
        response_items.append(JobItemResponse(
            id=item.id,
            name=item.name,
            email=item.email,
            achievement=item.achievement,
            status=item.status,
            error_message=item.error_message,
            download_url=download_url,
        ))
    
    return JobStatusResponse(
        job_id=job.id,
        title=job.title,
        status=job.status,
        total=job.total_count,
        succeeded=succeeded,
        failed=failed,
        pending=pending,
        created_at=job.created_at,
        completed_at=job.completed_at,
        items=response_items,
    )


@router.get("/{job_id}/certificates/{item_id}")
def download_certificate(
    job_id: str,
    item_id: int,
    db: Session = Depends(get_db),
):
    """
    Download a single certificate PDF.
    
    Returns 404 if item not found, not yet generated, or file missing.
    """
    item = db.query(JobItem).filter(
        JobItem.id == item_id,
        JobItem.job_id == job_id,
    ).first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Certificate not found")
    
    if item.status != "SUCCESS" or not item.file_path:
        raise HTTPException(
            status_code=404,
            detail=f"Certificate not available (status: {item.status})",
        )
    
    full_path = os.path.join(settings.storage_dir, item.file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Certificate file not found on disk")
    
    return FileResponse(
        full_path,
        media_type="application/pdf",
        filename=f"certificate_{item.name.replace(' ', '_')}.pdf",
    )


@router.get("/{job_id}/download")
def download_all_certificates(
    job_id: str,
    db: Session = Depends(get_db),
):
    """
    Download all successful certificates as a ZIP file.
    
    Returns 404 if job not found.
    Returns 409 if job is not yet completed.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Check if job is complete
    if job.status in ["PENDING", "PROCESSING"]:
        raise HTTPException(
            status_code=409,
            detail=f"Job is still {job.status.lower()}. Please wait for completion.",
        )
    
    # Get all successful items
    successful_items = db.query(JobItem).filter(
        JobItem.job_id == job_id,
        JobItem.status == "SUCCESS",
    ).all()
    
    if not successful_items:
        raise HTTPException(
            status_code=404,
            detail="No successful certificates to download",
        )
    
    # Create ZIP file in memory (for simplicity; for large jobs, stream to disk first)
    zip_path = os.path.join(settings.storage_dir, f"{job_id}_all.zip")
    
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for item in successful_items:
                if item.file_path:
                    full_path = os.path.join(settings.storage_dir, item.file_path)
                    if os.path.exists(full_path):
                        # Add with a clean name
                        arcname = f"{item.name.replace(' ', '_')}_{item.id}.pdf"
                        zipf.write(full_path, arcname=arcname)
        
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=f"{job.title.replace(' ', '_')}_certificates.zip",
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating ZIP: {str(e)}")
