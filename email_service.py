import smtplib
import ssl
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from typing import List, Optional
from datetime import datetime
import asyncio
import logging

# Set up logging
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        # Email configuration from environment variables
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")
        self.admin_email = os.getenv("ADMIN_EMAIL", "akshayamwellness@gmail.com")
        
        # Validate configuration
        if not self.sender_email or not self.sender_password:
            logger.warning("Email service not configured properly. Missing SENDER_EMAIL or SENDER_PASSWORD.")
    
    async def send_email(self, 
                        to_emails: List[str], 
                        subject: str, 
                        body_text: str, 
                        body_html: Optional[str] = None,
                        cc_emails: Optional[List[str]] = None,
                        bcc_emails: Optional[List[str]] = None) -> bool:
        """
        Send an email asynchronously
        
        Args:
            to_emails: List of recipient email addresses
            subject: Email subject line
            body_text: Plain text body
            body_html: HTML body (optional)
            cc_emails: List of CC recipients (optional)
            bcc_emails: List of BCC recipients (optional)
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            if not self.sender_email or not self.sender_password:
                logger.error("Email service not configured properly")
                return False
            
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = self.sender_email
            message["To"] = ", ".join(to_emails)
            
            if cc_emails:
                message["Cc"] = ", ".join(cc_emails)
            
            # Create the plain-text part
            text_part = MIMEText(body_text, "plain")
            message.attach(text_part)
            
            # Create the HTML part if provided
            if body_html:
                html_part = MIMEText(body_html, "html")
                message.attach(html_part)
            
            # Prepare recipient list
            recipients = to_emails.copy()
            if cc_emails:
                recipients.extend(cc_emails)
            if bcc_emails:
                recipients.extend(bcc_emails)
            
            # Send email using aiosmtplib for async operation
            await aiosmtplib.send(
                message,
                hostname=self.smtp_server,
                port=self.smtp_port,
                start_tls=True,
                username=self.sender_email,
                password=self.sender_password,
                recipients=recipients,
            )
            
            logger.info(f"Email sent successfully to {to_emails}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            return False
    
    def format_order_details(self, order_data: dict) -> tuple[str, str]:
        """
        Format order details for email
        
        Args:
            order_data: Order dictionary containing order information
            
        Returns:
            tuple: (text_body, html_body)
        """
        # Extract order information
        order_id = order_data.get("_id", "N/A")
        user_name = order_data.get("user_name", "")
        user_email = order_data.get("user_email", "")
        user_phone = order_data.get("user_phone", "")
        user_address = order_data.get("user_address", "")
        total_amount = order_data.get("total_amount", 0)
        items = order_data.get("items", [])
        created_at = order_data.get("created_at", datetime.utcnow())
        
        # Format creation date
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except:
                created_at = datetime.utcnow()
        
        formatted_date = created_at.strftime("%B %d, %Y at %I:%M %p")
        
        # Create text version
        text_body = f"""
New Order Received - Akshayam Wellness

Order Details:
==============
Order ID: {order_id}
Date: {formatted_date}

Customer Information:
===================
Name: {user_name}
Email: {user_email}
Phone: {user_phone}
Address: {user_address}

Order Items:
============
"""
        
        for item in items:
            text_body += f"""
Product: {item.get('product_name', 'N/A')}
Quantity: {item.get('quantity', 0)}
Price: ₹{item.get('price', 0):.2f}
Total: ₹{item.get('total', 0):.2f}
"""
        
        text_body += f"""
==============
Total Amount: ₹{total_amount:.2f}

Please process this order as soon as possible.

Best regards,
Akshayam Wellness System
"""
        
        # Create HTML version
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background-color: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
        .section {{ margin-bottom: 20px; }}
        .section h3 {{ color: #4CAF50; border-bottom: 2px solid #4CAF50; padding-bottom: 5px; }}
        .order-item {{ background-color: white; padding: 15px; margin: 10px 0; border-left: 4px solid #4CAF50; }}
        .total {{ background-color: #4CAF50; color: white; padding: 15px; text-align: center; font-size: 18px; font-weight: bold; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px; border-bottom: 1px solid #eee; }}
        .label {{ font-weight: bold; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛒 New Order Received</h1>
            <p>Akshayam Wellness</p>
        </div>
        
        <div class="content">
            <div class="section">
                <h3>📋 Order Details</h3>
                <table>
                    <tr><td class="label">Order ID:</td><td>{order_id}</td></tr>
                    <tr><td class="label">Date:</td><td>{formatted_date}</td></tr>
                </table>
            </div>
            
            <div class="section">
                <h3>👤 Customer Information</h3>
                <table>
                    <tr><td class="label">Name:</td><td>{user_name}</td></tr>
                    <tr><td class="label">Email:</td><td>{user_email}</td></tr>
                    <tr><td class="label">Phone:</td><td>{user_phone}</td></tr>
                    <tr><td class="label">Address:</td><td>{user_address}</td></tr>
                </table>
            </div>
            
            <div class="section">
                <h3>🛍️ Order Items</h3>
"""
        
        for item in items:
            html_body += f"""
                <div class="order-item">
                    <strong>{item.get('product_name', 'N/A')}</strong><br>
                    Quantity: {item.get('quantity', 0)} × ₹{item.get('price', 0):.2f} = <strong>₹{item.get('total', 0):.2f}</strong>
                </div>
"""
        
        html_body += f"""
            </div>
            
            <div class="total">
                💰 Total Amount: ₹{total_amount:.2f}
            </div>
            
            <div style="margin-top: 20px; padding: 15px; background-color: #e7f3ff; border-left: 4px solid #2196F3;">
                <strong>⚡ Action Required:</strong> Please process this order as soon as possible.
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 20px; color: #666; font-size: 12px;">
            This is an automated notification from Akshayam Wellness System
        </div>
    </div>
</body>
</html>
"""
        
        return text_body, html_body
    
    async def send_order_notification(self, order_data: dict) -> bool:
        """
        Send order notification email to admin
        
        Args:
            order_data: Order dictionary containing order information
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            # Format email content
            text_body, html_body = self.format_order_details(order_data)
            
            # Email subject
            order_id = order_data.get("_id", "N/A")
            user_name = order_data.get("user_name", "Customer")
            subject = f"🛒 New Order #{order_id} from {user_name} - Akshayam Wellness"
            
            # Send email to admin
            success = await self.send_email(
                to_emails=[self.admin_email],
                subject=subject,
                body_text=text_body,
                body_html=html_body
            )
            
            if success:
                logger.info(f"Order notification sent successfully for order {order_id}")
            else:
                logger.error(f"Failed to send order notification for order {order_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending order notification: {str(e)}")
            return False

# Create global email service instance
email_service = EmailService()
