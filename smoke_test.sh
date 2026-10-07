#!/bin/bash
# Smoke test for Bulk Certificate Generator API
# Run this after starting the server with: uvicorn app.main:app

echo "🧪 Testing Bulk Certificate Generator API..."
echo ""

# Create a job with mixed valid/invalid recipients
echo "1. Creating job with mixed valid/invalid recipients..."
RESPONSE=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Python Workshop 2024",
    "issuer": "Tech Academy",
    "recipients": [
      {"name": "Alice Smith", "email": "alice@example.com", "achievement": "Excellence"},
      {"name": "", "email": "empty@example.com"},
      {"name": "Bob Jones", "email": "bob@example.com"},
      {"name": "Duplicate", "email": "alice@example.com"}
    ]
  }')

JOB_ID=$(echo $RESPONSE | grep -o '"job_id":"[^"]*"' | cut -d'"' -f4)
echo "✅ Job created: $JOB_ID"
echo ""

# Wait for processing
echo "2. Waiting for processing (1 second)..."
sleep 1
echo ""

# Check status
echo "3. Checking job status..."
curl -s http://localhost:8000/jobs/$JOB_ID | python -m json.tool | grep -E '"status"|"succeeded"|"failed"|"error_message"'
echo ""

# Download a certificate
echo "4. Downloading certificate..."
curl -s http://localhost:8000/jobs/$JOB_ID/certificates/1 -o test_cert.pdf
if [ -f test_cert.pdf ]; then
    SIZE=$(wc -c < test_cert.pdf)
    echo "✅ Certificate downloaded: $SIZE bytes"
else
    echo "❌ Certificate download failed"
fi
echo ""

echo "✨ Smoke test complete!"
echo "Expected results:"
echo "- Job status: COMPLETED_WITH_ERRORS"
echo "- Succeeded: 2 (Alice, Bob)"
echo "- Failed: 2 (empty name, duplicate email)"
echo "- test_cert.pdf should exist and be ~2KB"
