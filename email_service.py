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
        Send an email asynchronously with enhanced Gmail SMTP connection handling
        
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
                logger.error("Email service not configured properly - Missing credentials")
                return False
            
            print(f"📧 ENHANCED GMAIL SMTP - Attempting email to {to_emails}")
            print(f"🔧 Using {self.smtp_server}:{self.smtp_port}")
            
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
            
            # Enhanced Gmail SMTP configuration with retry mechanism
            max_retries = 3
            retry_delay = 2  # seconds
            
            for attempt in range(max_retries):
                try:
                    print(f"🔄 Attempt {attempt + 1}/{max_retries} - Connecting to Gmail SMTP...")
                    
                    # Determine connection settings based on port
                    if self.smtp_port == 465:
                        # Port 465: Use direct TLS/SSL connection
                        print("🔒 Using SSL/TLS on port 465")
                        await aiosmtplib.send(
                            message,
                            hostname=self.smtp_server,
                            port=self.smtp_port,
                            use_tls=True,  # Direct TLS for port 465
                            start_tls=False,  # Don't use STARTTLS for port 465
                            username=self.sender_email,
                            password=self.sender_password,
                            recipients=recipients,
                            timeout=60,  # Increased timeout for production
                            validate_certs=True,
                        )
                    else:
                        # Port 587: Use STARTTLS
                        print("🔐 Using STARTTLS on port 587")
                        await aiosmtplib.send(
                            message,
                            hostname=self.smtp_server,
                            port=self.smtp_port,
                            use_tls=False,  # No direct TLS for port 587
                            start_tls=True,  # Use STARTTLS for port 587
                            username=self.sender_email,
                            password=self.sender_password,
                            recipients=recipients,
                            timeout=60,  # Increased timeout for production
                            validate_certs=True,
                        )
                    
                    print(f"✅ Email sent successfully on attempt {attempt + 1}")
                    logger.info(f"Email sent successfully to {to_emails} on attempt {attempt + 1}")
                    return True
                    
                except (aiosmtplib.SMTPConnectTimeoutError, 
                        aiosmtplib.SMTPServerDisconnected,
                        ConnectionError,
                        OSError) as conn_e:
                    print(f"⚠️ Connection attempt {attempt + 1} failed: {type(conn_e).__name__}: {str(conn_e)}")
                    if attempt < max_retries - 1:
                        print(f"⏳ Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        print(f"❌ All {max_retries} connection attempts failed")
                        logger.error(f"SMTP Connection failed after {max_retries} attempts: {str(conn_e)}")
                        return False
                        
                except aiosmtplib.SMTPException as smtp_e:
                    print(f"❌ SMTP Error on attempt {attempt + 1}: {type(smtp_e).__name__}: {str(smtp_e)}")
                    logger.error(f"SMTP Error: {type(smtp_e).__name__}: {str(smtp_e)}")
                    return False
                    
                except Exception as send_e:
                    print(f"❌ Send Error on attempt {attempt + 1}: {type(send_e).__name__}: {str(send_e)}")
                    logger.error(f"Send Error: {type(send_e).__name__}: {str(send_e)}")
                    return False
            
            return False  # Should not reach here
            
        except Exception as e:
            print(f"💥 General email error: {type(e).__name__}: {str(e)}")
            logger.error(f"General email error: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
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
            
            # CRITICAL DEBUGGING: Log all email configuration
            print(f"🔍 EMAIL DEBUG - Order {order_id}")
            print(f"📧 Admin Email: {self.admin_email}")
            print(f"📧 Sender Email: {self.sender_email}")
            print(f"🌐 SMTP Server: {self.smtp_server}:{self.smtp_port}")
            print(f"🔑 Has Password: {'Yes' if self.sender_password else 'No'}")
            print(f"📝 Subject: {subject}")
            
            # Send email to admin
            success = await self.send_email(
                to_emails=[self.admin_email],
                subject=subject,
                body_text=text_body,
                body_html=html_body
            )
            
            if success:
                print(f"📬 EMAIL SERVICE REPORTS SUCCESS for order {order_id}")
                logger.info(f"Order notification sent successfully for order {order_id}")
            else:
                print(f"📭 EMAIL SERVICE REPORTS FAILURE for order {order_id}")
                logger.error(f"Failed to send order notification for order {order_id}")
            
            return success
            
        except Exception as e:
            print(f"💥 EXCEPTION in send_order_notification for order {order_id}: {str(e)}")
            logger.error(f"Error sending order notification: {str(e)}")
            return False

# Create global email service instance
email_service = EmailService()
