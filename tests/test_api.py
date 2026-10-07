"""API endpoint tests.

Covers:
- Job creation (202, correct response)
- Input validation (various error cases)
- Certificate generation (PDF file exists and contains expected content)
- Job status and progress (counts, status transitions, filtering, pagination)
- Individual certificate failure (error isolation, COMPLETED_WITH_ERRORS status)
- Certificate downloads (single PDF, ZIP, 404 cases, 409 for incomplete jobs)
"""
import os
import time
import pytest
from unittest.mock import patch
from app.services.processor import process_job
from app.services.certificate import generate_certificate_pdf
from app.config import settings


def test_create_job_success(client, test_db):
    """Test successful job creation returns 202 with job_id."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "Bob Jones", "email": "bob@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 202
    
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "PENDING"
    assert data["total_count"] == 2


def test_create_job_with_issue_date(client, test_db):
    """Test job creation with explicit issue date."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "issue_date": "2024-01-15",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 202


def test_validation_missing_title(client, test_db):
    """Test 422 when title is missing."""
    payload = {
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 422


def test_validation_empty_recipients(client, test_db):
    """Test 422 when recipients list is empty."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [],
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 422


def test_validation_too_many_recipients(client, test_db):
    """Test 422 when recipients exceed limit."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": f"Person {i}", "email": f"person{i}@example.com"}
            for i in range(1001)
        ],
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 422


def test_invalid_email_format(client, test_db):
    """Test that invalid email fails Pydantic validation (422)."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "not-an-email"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 422


def test_empty_name_marked_as_failed(client, test_db):
    """Test that empty name is accepted but marked as FAILED item."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "", "email": "alice@example.com"},
            {"name": "Bob Jones", "email": "bob@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 202
    
    job_id = response.json()["job_id"]
    
    # Process synchronously for testing
    process_job(job_id, test_db)
    
    # Check status
    status_response = client.get(f"/jobs/{job_id}")
    data = status_response.json()
    
    assert data["failed"] == 1
    assert data["succeeded"] == 1
    
    # Check that empty name item has error
    failed_items = [item for item in data["items"] if item["status"] == "FAILED"]
    assert len(failed_items) == 1
    assert "empty" in failed_items[0]["error_message"].lower()


def test_duplicate_emails_marked_as_failed(client, test_db):
    """Test that duplicate emails are detected and marked as FAILED."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "Alice Duplicate", "email": "ALICE@example.com"},  # Case insensitive
            {"name": "Bob Jones", "email": "bob@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    assert response.status_code == 202
    
    job_id = response.json()["job_id"]
    
    # Process synchronously
    process_job(job_id, test_db)
    
    # Check status
    status_response = client.get(f"/jobs/{job_id}")
    data = status_response.json()
    
    assert data["succeeded"] == 2  # Alice (first) and Bob
    assert data["failed"] == 1  # Alice (duplicate)
    
    # Verify error message mentions duplicate
    failed_items = [item for item in data["items"] if item["status"] == "FAILED"]
    assert len(failed_items) == 1
    assert "duplicate" in failed_items[0]["error_message"].lower()


def test_certificate_generation(client, test_db, temp_storage):
    """Test that PDF is generated and contains expected content."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com", "achievement": "Excellence in Python"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    # Process synchronously
    process_job(job_id, test_db)
    
    # Check status
    status_response = client.get(f"/jobs/{job_id}")
    data = status_response.json()
    
    assert data["succeeded"] == 1
    assert data["status"] == "COMPLETED"
    
    # Get the file path
    item = data["items"][0]
    assert item["status"] == "SUCCESS"
    assert item["download_url"] is not None
    
    # Check file exists
    file_path = os.path.join(temp_storage, job_id)
    assert os.path.exists(file_path)
    
    # Check PDF content
    pdf_files = [f for f in os.listdir(file_path) if f.endswith(".pdf")]
    assert len(pdf_files) == 1
    
    pdf_path = os.path.join(file_path, pdf_files[0])
    with open(pdf_path, "rb") as f:
        content = f.read()
    
    # PDF should start with %PDF header
    assert content.startswith(b"%PDF")
    
    # Check that the PDF is non-trivial (has reasonable size)
    assert len(content) > 1000, "PDF should be more than 1KB"


def test_job_status_endpoint(client, test_db):
    """Test job status endpoint returns correct structure."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    # Get status before processing
    status_response = client.get(f"/jobs/{job_id}")
    assert status_response.status_code == 200
    
    data = status_response.json()
    assert data["job_id"] == job_id
    assert data["title"] == "Python Workshop"
    assert data["total"] == 1
    assert data["pending"] == 1
    
    # Process
    process_job(job_id, test_db)
    
    # Get status after processing
    status_response = client.get(f"/jobs/{job_id}")
    data = status_response.json()
    
    assert data["status"] == "COMPLETED"
    assert data["succeeded"] == 1
    assert data["failed"] == 0
    assert data["pending"] == 0


def test_status_filtering(client, test_db):
    """Test filtering items by status."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "", "email": "empty@example.com"},  # Will fail
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    process_job(job_id, test_db)
    
    # Filter by FAILED status
    status_response = client.get(f"/jobs/{job_id}?status=FAILED")
    data = status_response.json()
    
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "FAILED"
    
    # Filter by SUCCESS status
    status_response = client.get(f"/jobs/{job_id}?status=SUCCESS")
    data = status_response.json()
    
    assert len(data["items"]) == 1
    assert data["items"][0]["status"] == "SUCCESS"


def test_pagination(client, test_db):
    """Test pagination of job items."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": f"Person {i}", "email": f"person{i}@example.com"}
            for i in range(5)
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    # Get first 2 items
    status_response = client.get(f"/jobs/{job_id}?limit=2&offset=0")
    data = status_response.json()
    
    assert len(data["items"]) == 2
    assert data["total"] == 5
    
    # Get next 2 items
    status_response = client.get(f"/jobs/{job_id}?limit=2&offset=2")
    data = status_response.json()
    
    assert len(data["items"]) == 2


def test_individual_certificate_failure_isolation(client, test_db, temp_storage):
    """Test that one certificate failure doesn't stop others."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "Bob Jones", "email": "bob@example.com"},
            {"name": "Charlie Brown", "email": "charlie@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    # Monkeypatch the PDF generator to fail for Bob
    original_generate = generate_certificate_pdf
    
    def failing_generate(*args, **kwargs):
        if "Bob Jones" in str(kwargs.get("recipient_name", "")):
            raise RuntimeError("Simulated PDF generation failure")
        return original_generate(*args, **kwargs)
    
    with patch("app.services.processor.generate_certificate_pdf", side_effect=failing_generate):
        process_job(job_id, test_db)
    
    # Check status
    status_response = client.get(f"/jobs/{job_id}")
    data = status_response.json()
    
    assert data["status"] == "COMPLETED_WITH_ERRORS"
    assert data["succeeded"] == 2  # Alice and Charlie
    assert data["failed"] == 1  # Bob
    
    # Check that Bob's item has error recorded
    bob_item = [item for item in data["items"] if "Bob" in item["name"]][0]
    assert bob_item["status"] == "FAILED"
    assert "RuntimeError" in bob_item["error_message"]
    assert "Simulated PDF generation failure" in bob_item["error_message"]
    
    # Check that Alice and Charlie succeeded
    alice_item = [item for item in data["items"] if "Alice" in item["name"]][0]
    charlie_item = [item for item in data["items"] if "Charlie" in item["name"]][0]
    
    assert alice_item["status"] == "SUCCESS"
    assert charlie_item["status"] == "SUCCESS"


def test_download_single_certificate(client, test_db):
    """Test downloading a single certificate PDF."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    process_job(job_id, test_db)
    
    # Get item ID
    status_response = client.get(f"/jobs/{job_id}")
    item_id = status_response.json()["items"][0]["id"]
    
    # Download certificate
    download_response = client.get(f"/jobs/{job_id}/certificates/{item_id}")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/pdf"
    assert download_response.content.startswith(b"%PDF")


def test_download_certificate_404_not_found(client, test_db):
    """Test 404 when downloading non-existent certificate."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    # Try to download without processing
    download_response = client.get(f"/jobs/{job_id}/certificates/999")
    assert download_response.status_code == 404


def test_download_certificate_404_failed_item(client, test_db):
    """Test 404 when trying to download a failed certificate."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "", "email": "alice@example.com"},  # Will fail
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    process_job(job_id, test_db)
    
    # Get item ID
    status_response = client.get(f"/jobs/{job_id}")
    item_id = status_response.json()["items"][0]["id"]
    
    # Try to download failed certificate
    download_response = client.get(f"/jobs/{job_id}/certificates/{item_id}")
    assert download_response.status_code == 404


def test_download_zip_success(client, test_db):
    """Test downloading all certificates as ZIP."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "Bob Jones", "email": "bob@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    process_job(job_id, test_db)
    
    # Download ZIP
    download_response = client.get(f"/jobs/{job_id}/download")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "application/zip"
    
    # ZIP should have content
    assert len(download_response.content) > 0


def test_download_zip_409_not_completed(client, test_db):
    """Test 409 when trying to download ZIP before job completes."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    # Don't process, try to download immediately
    download_response = client.get(f"/jobs/{job_id}/download")
    assert download_response.status_code == 409
    assert "pending" in download_response.json()["detail"].lower()


def test_download_zip_404_no_successful_certs(client, test_db):
    """Test 404 when job has no successful certificates."""
    payload = {
        "title": "Python Workshop",
        "issuer": "Tech Academy",
        "recipients": [
            {"name": "", "email": "alice@example.com"},  # Will fail
        ],
    }
    
    response = client.post("/jobs", json=payload)
    job_id = response.json()["job_id"]
    
    process_job(job_id, test_db)
    
    # Try to download ZIP
    download_response = client.get(f"/jobs/{job_id}/download")
    assert download_response.status_code == 404
    assert "no successful" in download_response.json()["detail"].lower()


def test_job_not_found(client, test_db):
    """Test 404 for non-existent job."""
    response = client.get("/jobs/nonexistent-job-id")
    assert response.status_code == 404
