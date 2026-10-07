"""Pydantic v2 schemas for request/response validation.

Design decisions:
- EmailStr for email validation
- Field constraints (max length, min items) for safety
- Separate response schemas for different levels of detail
"""
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# Request schemas
class RecipientInput(BaseModel):
    name: str = Field(..., max_length=100, description="Recipient full name")  # Removed min_length
    email: EmailStr = Field(..., description="Recipient email address")
    achievement: Optional[str] = Field(None, max_length=200, description="Optional achievement text")


class CreateJobRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Certificate title")
    issuer: str = Field(..., min_length=1, max_length=200, description="Issuing organization")
    issue_date: Optional[date] = Field(None, description="Issue date (defaults to today)")
    recipients: List[RecipientInput] = Field(..., min_length=1, max_length=1000, description="List of recipients")
    
    @field_validator("recipients")
    @classmethod
    def check_duplicate_emails(cls, v):
        """Flag duplicate emails within the same job.
        
        We don't reject the request here; instead, we'll mark duplicates as FAILED during processing.
        This validator just ensures we have the data we need.
        """
        emails = [r.email.lower() for r in v]
        if len(emails) != len(set(emails)):
            # Find duplicates for the error message
            seen = set()
            duplicates = set()
            for email in emails:
                if email in seen:
                    duplicates.add(email)
                seen.add(email)
            # Note: We'll handle this in the service layer, not here
            # This is just for documentation; actual duplicate handling is in processor
        return v


# Response schemas
class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    total_count: int
    message: str


class JobItemResponse(BaseModel):
    id: int
    name: str
    email: str
    achievement: Optional[str]
    status: str
    error_message: Optional[str]
    download_url: Optional[str]  # Present only if status=SUCCESS
    
    class Config:
        from_attributes = True


class JobStatusResponse(BaseModel):
    job_id: str
    title: str
    status: str
    total: int
    succeeded: int
    failed: int
    pending: int
    created_at: datetime
    completed_at: Optional[datetime]
    items: List[JobItemResponse]
    
    class Config:
        from_attributes = True
