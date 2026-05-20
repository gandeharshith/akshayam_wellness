"""
DEPRECATED: SendGrid has been replaced with Gmail SMTP.
This file is kept for backward compatibility only.
All email sending is now handled by smtp_email_service.py
"""
from smtp_email_service import smtp_email_service

# Alias so any old imports still work without errors
sendgrid_email_service = smtp_email_service
