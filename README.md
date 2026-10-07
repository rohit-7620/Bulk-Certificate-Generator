# Bulk Certificate Generator API

A FastAPI-based backend service for generating PDF certificates in bulk. Accepts a list of recipients, generates personalized certificates asynchronously, and provides download endpoints for individual certificates or bulk ZIP downloads.

## Features

- **Bulk processing**: Submit up to 1000 recipients in a single request
- **Background processing**: Returns immediately (202 Accepted) and processes certificates asynchronously
- **Error isolation**: One failed certificate doesn't stop others; failures are tracked per-recipient
- **Validation**: Invalid recipients become FAILED items with clear error messages (no 400/422 rejection)
- **Progress tracking**: Real-time status endpoint shows succeeded/failed/pending counts
- **Flexible downloads**: Download individual PDFs or all successful certificates as a ZIP
- **Filtering & pagination**: Query job items by status, paginate large result sets

## Quick Start

### Prerequisites

- Python 3.11 or higher
- pip (Python package manager)

### Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

### Run the Server

```bash
# Start with uvicorn (default: http://localhost:8000)
uvicorn app.main:app --reload

# Or specify host and port
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

### Run Tests

```bash
# Run all tests with pytest
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app --cov-report=html
```

## API Usage Examples

### 1. Create a Certificate Job

Submit a bulk certificate generation job:

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Python Workshop 2024",
    "issuer": "Tech Academy",
    "issue_date": "2024-01-15",
    "recipients": [
      {
        "name": "Alice Smith",
        "email": "alice@example.com",
        "achievement": "Excellence in Python Programming"
      },
      {
        "name": "Bob Jones",
        "email": "bob@example.com",
        "achievement": "Outstanding Participation"
      }
    ]
  }'
```

**Response (202 Accepted):**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "PENDING",
  "total_count": 2,
  "message": "Job created with 2 recipients. Processing started."
}
```

### 2. Check Job Status

Get job progress and item details:

```bash
# Basic status
curl http://localhost:8000/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890

# Filter by status (e.g., see only failures)
curl "http://localhost:8000/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890?status=FAILED"

# Paginate results
curl "http://localhost:8000/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890?limit=10&offset=0"
```

**Response:**
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Python Workshop 2024",
  "status": "COMPLETED",
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "pending": 0,
  "created_at": "2024-01-15T10:00:00",
  "completed_at": "2024-01-15T10:00:05",
  "items": [
    {
      "id": 1,
      "name": "Alice Smith",
      "email": "alice@example.com",
      "achievement": "Excellence in Python Programming",
      "status": "SUCCESS",
      "error_message": null,
      "download_url": "/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/certificates/1"
    },
    {
      "id": 2,
      "name": "Bob Jones",
      "email": "bob@example.com",
      "achievement": "Outstanding Participation",
      "status": "SUCCESS",
      "error_message": null,
      "download_url": "/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/certificates/2"
    }
  ]
}
```

### 3. Download a Single Certificate

```bash
curl -O -J http://localhost:8000/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/certificates/1
```

This downloads `certificate_Alice_Smith.pdf`.

### 4. Download All Certificates as ZIP

```bash
curl -O -J http://localhost:8000/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/download
```

This downloads `Python_Workshop_2024_certificates.zip` containing all successful certificates.

### 5. Test with Mixed Valid/Invalid Recipients

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Python Workshop 2024",
    "issuer": "Tech Academy",
    "recipients": [
      {
        "name": "Alice Smith",
        "email": "alice@example.com"
      },
      {
        "name": "",
        "email": "empty@example.com"
      },
      {
        "name": "Charlie Brown",
        "email": "charlie@example.com"
      },
      {
        "name": "Duplicate",
        "email": "alice@example.com"
      }
    ]
  }'
```

The job will succeed (202), but:
- Empty name → FAILED with error "Name is empty or whitespace only"
- Duplicate email → FAILED with error "Duplicate email address (first occurrence: item X)"
- Valid recipients → SUCCESS with generated PDFs

## Design Decisions

### 1. Background Processing with BackgroundTasks

**Why:** Generating hundreds of certificates synchronously would block the HTTP request and cause timeouts.

**Trade-off:** FastAPI's `BackgroundTasks` is simple but in-memory only. If the server crashes or restarts, in-progress jobs are lost.

**Production alternative:** Use Celery or RQ with Redis/RabbitMQ for persistent task queues. The `process_job` function is designed as a plain sync function, making it easy to wrap in a Celery task.

**Startup recovery:** On server startup, any jobs stuck in PROCESSING status are marked as FAILED (see `recover_stale_jobs` in `app/services/processor.py`).

### 2. Per-Item Failure Isolation

**Why:** One bad email or PDF generation error shouldn't fail the entire batch of 1000 recipients.

**Implementation:** Each certificate generation is wrapped in a try/except block. Failures are recorded on the specific `JobItem` with status=FAILED and a descriptive error message. Other items continue processing.

**Result:** Jobs end in `COMPLETED_WITH_ERRORS` if some items succeed and some fail, making it easy to retry just the failures (future feature).

### 3. Invalid Recipients Become FAILED Items

**Why:** A request with 1000 recipients shouldn't be rejected entirely because one email is malformed or one name is empty.

**Implementation:** Validation happens at two levels:
- **Pydantic validation** (request level): Rejects with 422 only for structural errors (missing required fields, wrong types, list size violations)
- **Business validation** (processing level): Invalid recipients (empty names, duplicate emails) are stored as FAILED items with clear error messages

**Trade-off:** This approach prioritizes partial success over strict validation. If strict validation is required, move duplicate detection to the Pydantic validator and raise a 422.

### 4. SQLite with Easy Postgres Migration

**Why:** SQLite requires zero setup for local development and take-home assignments.

**Migration path:** The entire database config is in `app/config.py`. To switch to Postgres:

```bash
# Set environment variable
export DATABASE_URL="postgresql://user:password@localhost/certificates"

# Or create a .env file
echo 'DATABASE_URL="postgresql://user:password@localhost/certificates"' > .env

# Run (SQLAlchemy handles the rest)
uvicorn app.main:app
```

The code is database-agnostic; only the connection string changes.

### 5. ReportLab for PDF Generation

**Why:** Pure Python library with no system dependencies (unlike wkhtmltopdf, Puppeteer, or LaTeX).

**Trade-off:** Lower-level API compared to HTML-to-PDF tools, but full control over layout and no external process overhead.

**Template:** Single hardcoded template in `app/services/certificate.py` (`generate_certificate_pdf` function). To add more templates, add a `template` parameter and a switch statement (or template registry).

### 6. Job Status Transitions

```
PENDING → PROCESSING → COMPLETED (all succeeded)
                     → COMPLETED_WITH_ERRORS (mixed results)
                     → FAILED (all failed or fatal error)
```

Status is computed after processing all items based on counts:
- `COMPLETED`: succeeded > 0, failed = 0
- `COMPLETED_WITH_ERRORS`: succeeded > 0, failed > 0
- `FAILED`: succeeded = 0 (or processor crashed)

## Project Structure

```
.
├── app/
│   ├── main.py                 # FastAPI app entry point, startup logic
│   ├── config.py               # Settings (DATABASE_URL, storage path)
│   ├── database.py             # SQLAlchemy engine, session, Base
│   ├── models.py               # Job and JobItem ORM models
│   ├── schemas.py              # Pydantic request/response schemas
│   ├── routes/
│   │   └── jobs.py             # API endpoints (POST /jobs, GET /jobs/{id}, etc.)
│   └── services/
│       ├── certificate.py      # PDF generation with ReportLab
│       └── processor.py        # Background job processing logic
├── tests/
│   ├── conftest.py             # Pytest fixtures (isolated DB, temp storage)
│   └── test_api.py             # API endpoint tests
├── requirements.txt            # Python dependencies
├── README.md                   # This file
└── .gitignore                  # Ignore storage/, *.db, __pycache__, etc.
```

## What I Would Do With More Time

### 1. Add a New Template Field (e.g., instructor name)

**Where:** 
- Add `instructor: Optional[str]` to `CreateJobRequest` and `RecipientInput` in `app/schemas.py`
- Add `instructor` column to `JobItem` model in `app/models.py`
- Update `generate_certificate_pdf()` in `app/services/certificate.py` to render the instructor name

**Estimate:** 15 minutes

### 2. Switch to Celery for Production

**Where:**
- Create `app/celery_app.py` with Celery configuration (Redis broker)
- Change `process_job()` in `app/services/processor.py` to a Celery task: `@celery_app.task`
- In `app/routes/jobs.py`, replace `background_tasks.add_task(...)` with `process_job.delay(job_id)`
- Add `celery -A app.celery_app worker` to deployment instructions

**Estimate:** 1-2 hours (including testing and deployment config)

### 3. Add Retry for Failed Items

**Where:**
- Add `POST /jobs/{job_id}/retry` endpoint in `app/routes/jobs.py`
- Query all `JobItem`s with status=FAILED, reset them to PENDING
- Call `process_job(job_id, SessionLocal)` via BackgroundTasks (or Celery)
- Processor already handles PENDING items, so no changes needed there

**Estimate:** 30 minutes

### 4. Add Email Delivery

**Where:**
- Create `app/services/email.py` with an SMTP sender function
- In `app/services/processor.py`, after successful PDF generation, call `send_certificate_email(recipient.email, file_path)`
- Add email credentials to `app/config.py` (SMTP_HOST, SMTP_USER, SMTP_PASSWORD)
- Add `email_sent` boolean field to `JobItem` to track delivery status

**Estimate:** 1 hour

### 5. Add Webhook Notifications

**Where:**
- Add `webhook_url: Optional[str]` to `CreateJobRequest` in `app/schemas.py`
- Store it on the `Job` model
- In `app/services/processor.py`, after job completion, POST job status to `webhook_url` using `httpx`

**Estimate:** 30 minutes

## License

MIT (for take-home assignment purposes)
