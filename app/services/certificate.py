"""PDF certificate generation using ReportLab.

Single hardcoded template with professional layout.
ReportLab is pure Python (no system dependencies like wkhtmltopdf or LaTeX).

Design decisions:
- Unique certificate ID per recipient (UUID) for verification/audit trail
- Simple centered layout that's easy to modify in an interview
- Uses built-in fonts (Helvetica) to avoid font file dependencies
"""
import os
import uuid
from datetime import datetime
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors


def generate_certificate_pdf(
    output_path: str,
    title: str,
    recipient_name: str,
    issuer: str,
    issue_date: str,
    achievement: str = None,
) -> str:
    """
    Generate a single certificate PDF.
    
    Args:
        output_path: Full file path where PDF will be saved
        title: Certificate title (e.g., "Python Workshop")
        recipient_name: Recipient's full name
        issuer: Issuing organization
        issue_date: Date string (YYYY-MM-DD)
        achievement: Optional achievement text
    
    Returns:
        Unique certificate ID (UUID)
    
    Raises:
        Any exception from ReportLab or filesystem
    """
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Generate unique certificate ID for this specific certificate
    cert_id = str(uuid.uuid4())
    
    # Create PDF in landscape mode (more traditional for certificates)
    c = canvas.Canvas(output_path, pagesize=landscape(letter))
    width, height = landscape(letter)
    
    # Certificate border
    c.setStrokeColor(colors.HexColor("#1e3a8a"))  # Dark blue
    c.setLineWidth(3)
    c.rect(0.5 * inch, 0.5 * inch, width - inch, height - inch)
    
    # Inner border for decoration
    c.setStrokeColor(colors.HexColor("#3b82f6"))  # Lighter blue
    c.setLineWidth(1)
    c.rect(0.6 * inch, 0.6 * inch, width - 1.2 * inch, height - 1.2 * inch)
    
    # Title section
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(colors.HexColor("#1e3a8a"))
    c.drawCentredString(width / 2, height - 1.5 * inch, "CERTIFICATE OF COMPLETION")
    
    # Certificate title (e.g., workshop name)
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(colors.black)
    c.drawCentredString(width / 2, height - 2.2 * inch, title)
    
    # "Presented to" text
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.HexColor("#6b7280"))  # Gray
    c.drawCentredString(width / 2, height - 3 * inch, "This certificate is proudly presented to")
    
    # Recipient name (the star of the show)
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(colors.black)
    c.drawCentredString(width / 2, height - 3.7 * inch, recipient_name)
    
    # Achievement text if provided
    if achievement:
        c.setFont("Helvetica-Oblique", 12)
        c.setFillColor(colors.HexColor("#6b7280"))
        c.drawCentredString(width / 2, height - 4.3 * inch, f"for {achievement}")
    
    # Issuer and date
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.black)
    
    # Issuer on the left
    c.drawString(1.5 * inch, 1.3 * inch, f"Issued by: {issuer}")
    
    # Date on the right
    date_obj = datetime.strptime(issue_date, "%Y-%m-%d")
    formatted_date = date_obj.strftime("%B %d, %Y")
    c.drawRightString(width - 1.5 * inch, 1.3 * inch, f"Date: {formatted_date}")
    
    # Certificate ID at the bottom (small, for verification)
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#9ca3af"))
    c.drawCentredString(width / 2, 0.8 * inch, f"Certificate ID: {cert_id}")
    
    # Save the PDF
    c.save()
    
    return cert_id
