# Bulk Certificate Generator API - Summary

## Project Complete ✅

A production-ready FastAPI backend for bulk PDF certificate generation, designed for take-home interview presentation.

## How to Run

### Setup
```bash
pip install -r requirements.txt
```

### Start Server
```bash
uvicorn app.main:app --reload
# Server runs at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Run Tests
```bash
pytest tests/test_api.py -v
# All 20 tests pass
```

## Quick API Test

```bash
# Create a job
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Python Workshop",
    "issuer": "Tech Academy",
    "recipients": [
      {"name": "Alice Smith", "email": "alice@example.com"},
      {"name": "Bob Jones", "email": "bob@example.com"}
    ]
  }'

# Response: {"job_id": "...", "status": "PENDING", ...}

# Check status (use the job_id from response)
curl http://localhost:8000/jobs/{job_id}

# Download single certificate
curl http://localhost:8000/jobs/{job_id}/certificates/{item_id} -O

# Download all as ZIP
curl http://localhost:8000/jobs/{job_id}/download -O
```

## Key Design Decisions

### 1. Background Processing with BackgroundTasks
**Why:** Generating hundreds of certificates synchronously would block HTTP requests and cause timeouts.

**Trade-off:** FastAPI's BackgroundTasks runs in-memory. If the server restarts, in-progress jobs are marked as FAILED on next startup (see `recover_stale_jobs`).

**Production alternative:** Use Celery/RQ with Redis for persistent task queues. The `process_job` function is a plain sync function, making it trivial to wrap as a Celery task.

### 2. Per-Item Error Isolation
**Why:** One malformed email or PDF generation error shouldn't fail all 1000 recipients.

**Implementation:** Each certificate generation is wrapped in try/except. Failures are recorded on that specific `JobItem` (status=FAILED, error message saved). Other items continue processing.

**Result:** Jobs end in `COMPLETED_WITH_ERRORS` status when some succeed and some fail.

### 3. Invalid Recipients Become FAILED Items (Not 422 Rejection)
**Why:** A request with 1000 recipients shouldn't be rejected because one email is invalid or one name is empty.

**Implementation:** 
- Pydantic validates request structure (missing fields, wrong types → 422)
- Business validation (duplicate emails, empty names) happens during processing → FAILED items with error messages

**Trade-off:** Prioritizes partial success over strict validation. For stricter validation, move checks to Pydantic and return 422.

### 4. SQLite with Easy Postgres Migration
**Why:** SQLite needs zero setup for local development and take-home assignments.

**Migration:** Change one environment variable:
```bash
export DATABASE_URL="postgresql://user:password@localhost/certificates"
uvicorn app.main:app
```
SQLAlchemy handles the rest. No code changes needed.

### 5. ReportLab for PDF Generation
**Why:** Pure Python library with no system dependencies (no wkhtmltopdf, Puppeteer, or LaTeX).

**Trade-off:** Lower-level API than HTML-to-PDF tools, but full layout control and no subprocess overhead.

**Template:** Single hardcoded template in `app/services/certificate.py`. To add templates, add a `template` parameter and switch logic.

## Test Coverage

All 20 tests pass, covering:
- ✅ Job creation (202 response, correct counts)
- ✅ Input validation (bad email, empty name, empty list, oversized list, duplicate emails)
- ✅ Certificate generation (PDF file created, valid format, reasonable size)
- ✅ Job status transitions (PENDING → PROCESSING → COMPLETED/COMPLETED_WITH_ERRORS/FAILED)
- ✅ Filtering by status (e.g., ?status=FAILED to see only failures)
- ✅ Pagination (limit/offset parameters)
- ✅ Individual certificate failure isolation (one failure doesn't stop others)
- ✅ Download endpoints (single PDF, bulk ZIP, 404/409 error cases)

## Code Characteristics

- **Simple, readable code:** No clever abstractions; every line is explainable in an interview
- **Short comments on non-obvious decisions:** e.g., why BackgroundTasks, why StaticPool for tests, why empty names don't reject requests
- **Production-ready patterns:** Proper error handling, status tracking, foreign key constraints, pagination

## 3 Likely Interview Follow-Ups

### 1. Add a new template field (e.g., instructor name)
**Where:** 
- Add `instructor: Optional[str]` to `CreateJobRequest` and `JobItem` model (app/schemas.py, app/models.py)
- Update `generate_certificate_pdf()` to render the instructor name (app/services/certificate.py)

### 2. Switch to Celery for production
**Where:**
- Create `app/celery_app.py` with Celery config (Redis broker)
- Convert `process_job()` in `app/services/processor.py` to a Celery task: `@celery_app.task`
- In `app/routes/jobs.py`, replace `background_tasks.add_task(...)` with `process_job.delay(job_id)`

### 3. Add retry for failed items
**Where:**
- Add `POST /jobs/{job_id}/retry` endpoint in `app/routes/jobs.py`
- Query all `JobItem`s with status=FAILED, reset to PENDING
- Call `process_job(job_id, SessionLocal)` (processor already handles PENDING items)

## Project Structure

```
app/
├── main.py              # FastAPI entry point, startup logic
├── config.py            # Settings (DATABASE_URL, storage path)
├── database.py          # SQLAlchemy engine, session, Base
├── models.py            # Job and JobItem ORM models
├── schemas.py           # Pydantic request/response schemas
├── routes/
│   └── jobs.py          # API endpoints
└── services/
    ├── certificate.py   # PDF generation (ReportLab)
    └── processor.py     # Background job processing
tests/
├── conftest.py          # Pytest fixtures (isolated DB, temp storage)
└── test_api.py          # Comprehensive API tests (20 tests)
requirements.txt         # Python dependencies
README.md                # Full documentation with design decisions
```

## What Makes This Interview-Ready

1. **Every line is explainable:** No magic, no complex abstractions
2. **Comments on trade-offs:** e.g., "BackgroundTasks loses work on restart; Celery would fix this"
3. **Production patterns:** Error isolation, status tracking, pagination, foreign keys
4. **Comprehensive tests:** 20 tests, all passing, isolated fixtures
5. **Clear documentation:** README explains every design decision and migration path
6. **Easy to modify:** Follow-up questions have clear answers pointing to specific files/functions
