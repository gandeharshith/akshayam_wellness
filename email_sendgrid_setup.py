"""
SendGrid Email Service Setup for Production

This script demonstrates how to switch from Gmail SMTP to SendGrid
for production email delivery.

SendGrid Setup Instructions:
==========================

1. Sign up for SendGrid account:
   https://sendgrid.com/

2. Create an API Key:
   - Go to Settings > API Keys
   - Create new API Key with "Full Access"
   - Copy the API Key (starts with "SG.")

3. Update your production environment variables:
   SMTP_SERVER=smtp.sendgrid.net
   SMTP_PORT=587
   SENDER_EMAIL=noreply@yourdomain.com  # Use your domain
   SENDER_PASSWORD=your_sendgrid_api_key  # Paste API key here
   ADMIN_EMAIL=akshayamwellness@gmail.com

4. Deploy and test!

Benefits of SendGrid:
====================
✅ Not blocked by hosting providers
✅ High deliverability rates  
✅ Built for production use
✅ Detailed delivery analytics
✅ Free tier: 100 emails/day

Alternative Quick Fix (if SendGrid not available):
================================================
If you can't set up SendGrid immediately, try these SMTP alternatives:

Option 1: Gmail App Password (might still be blocked)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
# Change port to 465 and enable SSL

Option 2: Outlook/Hotmail
SMTP_SERVER=smtp-mail.outlook.com
SMTP_PORT=587

Option 3: AWS SES (if you're on AWS)
SMTP_SERVER=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
"""

# Example SendGrid configuration for your .env file:
SENDGRID_CONFIG = {
    "SMTP_SERVER": "smtp.sendgrid.net",
    "SMTP_PORT": "587", 
    "SENDER_EMAIL": "noreply@yourdomain.com",  # Use your actual domain
    "SENDER_PASSWORD": "SG.your_api_key_here",  # Replace with actual SendGrid API key
    "ADMIN_EMAIL": "akshayamwellness@gmail.com"
}

print("📧 SendGrid Setup Instructions Generated")
print("🔗 Visit: https://sendgrid.com/ to create account")
print("💡 See backend/email_sendgrid_setup.py for detailed instructions")
