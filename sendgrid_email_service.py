import os
import logging
from typing import List, Optional
from datetime import datetime, UTC
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

# Set up logging
logger = logging.getLogger(__name__)

class SendGridEmailService:
    def __init__(self):
        # Initialize as None - will be loaded when needed
        self._api_key = None
        self._sg = None
        self._initialized = False
    
    def _initialize_if_needed(self):
        """Lazy initialization of SendGrid client"""
        if self._initialized:
            return
            
        # SendGrid configuration from environment variables
        self._api_key = os.getenv("SENDGRID_API_KEY") or os.getenv("SENDER_PASSWORD", "")
        self._sender_email = os.getenv("SENDER_EMAIL", "akshayamwellnessorders@gmail.com")
        self._admin_email = os.getenv("ADMIN_EMAIL", "akshayamwellness@gmail.com")
        self._admin_email_2 = os.getenv("ADMIN_EMAIL_2", "vivek1995@gmail.com")
        
        print(f"🔧 SendGrid API Key loaded: {self._api_key[:15]}...{self._api_key[-5:] if len(self._api_key) > 20 else 'Invalid'}")
        print(f"🔧 API Key starts with SG.: {self._api_key.startswith('SG.') if self._api_key else False}")
        
        # Initialize SendGrid client
        if self._api_key and self._api_key.startswith("SG."):
            self._sg = SendGridAPIClient(api_key=self._api_key)
            print("✅ SendGrid Web API client initialized successfully")
            logger.info("SendGrid Web API client initialized successfully")
        else:
            self._sg = None
            print(f"❌ SendGrid API key invalid: {self._api_key[:30] if self._api_key else 'None'}")
            logger.error("SendGrid API key not configured properly or invalid format")
            
        self._initialized = True
    
    @property
    def api_key(self):
        self._initialize_if_needed()
        return self._api_key
        
    @property
    def sg(self):
        self._initialize_if_needed()
        return self._sg
    
    @property
    def admin_email(self):
        self._initialize_if_needed()
        return self._admin_email
    
    @property
    def admin_email_2(self):
        self._initialize_if_needed()
        return self._admin_email_2
        
    @property  
    def sender_email(self):
        self._initialize_if_needed()
        return self._sender_email
    
    async def send_email(self, 
                        to_emails: List[str], 
                        subject: str, 
                        body_text: str, 
                        body_html: Optional[str] = None) -> bool:
        """
        Send an email using SendGrid Web API
        
        Args:
            to_emails: List of recipient email addresses
            subject: Email subject line
            body_text: Plain text body
            body_html: HTML body (optional)
            
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            if not self.sg:
                print("❌ SendGrid API client not initialized - check API key")
                logger.error("SendGrid API client not initialized")
                return False
            
            print(f"📧 SENDGRID WEB API - Sending email to {to_emails}")
            print(f"🔧 Using SendGrid Web API v3")
            print(f"🔑 API Key: {self.api_key[:15]}...{self.api_key[-5:] if len(self.api_key) > 20 else 'Invalid'}")
            
            # Create the email
            from_email = Email(self.sender_email)
            to_list = [To(email) for email in to_emails]
            
            # Create Mail object
            if body_html:
                # Use HTML content if provided
                content = Content("text/html", body_html)
            else:
                # Use plain text content
                content = Content("text/plain", body_text)
            
            mail = Mail(from_email, to_list[0], subject, content)
            
            # Add additional recipients if any
            if len(to_list) > 1:
                for to_email in to_list[1:]:
                    mail.add_to(to_email)
            
            # Add plain text version if HTML is provided
            if body_html and body_text:
                mail.add_content(Content("text/plain", body_text))
            
            # Send the email
            print("🚀 Sending email via SendGrid Web API...")
            response = self.sg.send(mail)
            
            # Check response status
            if response.status_code in [200, 201, 202]:
                print(f"✅ SendGrid API Success! Status Code: {response.status_code}")
                print(f"📬 Message ID: {response.headers.get('X-Message-Id', 'N/A')}")
                logger.info(f"Email sent successfully via SendGrid Web API to {to_emails}")
                return True
            else:
                print(f"❌ SendGrid API Error! Status Code: {response.status_code}")
                print(f"🔍 Response Body: {response.body}")
                print(f"🔍 Response Headers: {response.headers}")
                logger.error(f"SendGrid API error: Status {response.status_code}, Body: {response.body}")
                return False
                
        except Exception as e:
            print(f"💥 SendGrid Web API Exception: {type(e).__name__}: {str(e)}")
            logger.error(f"SendGrid Web API error: {type(e).__name__}: {str(e)}")
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
        created_at = order_data.get("created_at", datetime.now(UTC))
        
        # Format creation date
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except:
                created_at = datetime.now(UTC)
        
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
        Send order notification email to admin using SendGrid Web API
        
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
            print(f"🔍 SENDGRID EMAIL DEBUG - Order {order_id}")
            print(f"📧 Admin Email 1: {self.admin_email}")
            print(f"📧 Admin Email 2: {self.admin_email_2}")
            print(f"📧 Sender Email: {self.sender_email}")
            print(f"🌐 SendGrid Web API v3")
            print(f"🔑 API Key Present: {'Yes' if self.api_key and self.api_key.startswith('SG.') else 'No'}")
            print(f"📝 Subject: {subject}")
            
            # Send email to both admin emails
            admin_emails = [self.admin_email, self.admin_email_2]
            print(f"📧 Sending to both admins: {admin_emails}")
            
            success = await self.send_email(
                to_emails=admin_emails,
                subject=subject,
                body_text=text_body,
                body_html=html_body
            )
            
            if success:
                print(f"📬 SENDGRID WEB API REPORTS SUCCESS for order {order_id}")
                logger.info(f"Order notification sent successfully via SendGrid Web API for order {order_id}")
            else:
                print(f"📭 SENDGRID WEB API REPORTS FAILURE for order {order_id}")
                logger.error(f"Failed to send order notification via SendGrid Web API for order {order_id}")
            
            return success
            
        except Exception as e:
            print(f"💥 EXCEPTION in send_order_notification for order {order_id}: {str(e)}")
            logger.error(f"Error sending order notification via SendGrid Web API: {str(e)}")
            return False

# Create global SendGrid email service instance
sendgrid_email_service = SendGridEmailService()
