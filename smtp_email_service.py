"""
SMTP Email Service for Akshayam Wellness order notifications.
Uses Gmail SMTP with App Password (no third-party API required).
"""
import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
from datetime import datetime, UTC

logger = logging.getLogger(__name__)


class SMTPEmailService:
    def __init__(self):
        self._initialized = False
        self._smtp_host = None
        self._smtp_port = None
        self._sender_email = None
        self._sender_password = None
        self._admin_email = None
        self._admin_email_2 = None
        self._admin_email_3 = None

    def _initialize_if_needed(self):
        """Lazy initialization of SMTP config from environment variables."""
        if self._initialized:
            return

        self._smtp_host = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self._smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self._sender_email = os.getenv("SENDER_EMAIL", "akshayamwellnessorders@gmail.com")
        self._sender_password = os.getenv("SENDER_PASSWORD", "")
        self._admin_email = os.getenv("ADMIN_EMAIL", "akshayamwellness@gmail.com")
        self._admin_email_2 = os.getenv("ADMIN_EMAIL_2") or os.getenv("ADMIN_EMAIL_LOGIN", "vivek1995m@gmail.com")
        self._admin_email_3 = os.getenv("ADMIN_EMAIL_3", "")

        print(f"📧 SMTP Config: host={self._smtp_host}, port={self._smtp_port}")
        print(f"📧 Sender: {self._sender_email}")
        print(f"📧 Admin 1: {self._admin_email}")
        print(f"📧 Admin 2: {self._admin_email_2}")
        print(f"📧 Admin 3: {self._admin_email_3}")
        print(f"🔑 Password set: {'Yes' if self._sender_password else 'No'}")

        self._initialized = True

    @property
    def admin_emails(self) -> List[str]:
        self._initialize_if_needed()
        emails = [self._admin_email, self._admin_email_2]
        if self._admin_email_3:
            emails.append(self._admin_email_3)
        return emails

    def format_order_details(self, order_data: dict):
        """Format order details into plain text and HTML bodies."""
        order_id = order_data.get("_id", "N/A")
        user_name = order_data.get("user_name", "")
        user_email = order_data.get("user_email", "")
        user_phone = order_data.get("user_phone", "")
        user_address = order_data.get("user_address", "")
        total_amount = order_data.get("total_amount", 0)
        items = order_data.get("items", [])
        created_at = order_data.get("created_at", datetime.now(UTC))

        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except Exception:
                created_at = datetime.now(UTC)

        formatted_date = created_at.strftime("%B %d, %Y at %I:%M %p")

        # Plain text body
        text_body = f"""
New Order Received - Akshayam Wellness

Order Details:
==============
Order ID: {order_id}
Date: {formatted_date}

Customer Information:
=====================
Name: {user_name}
Email: {user_email}
Phone: {user_phone}
Address: {user_address}

Order Items:
============
"""
        for item in items:
            text_body += f"- {item.get('product_name', 'N/A')} x{item.get('quantity', 0)} @ ₹{item.get('price', 0):.2f} = ₹{item.get('total', 0):.2f}\n"

        text_body += f"""
==============
Total Amount: ₹{total_amount:.2f}

Please process this order as soon as possible.

Best regards,
Akshayam Wellness System
"""

        # HTML body
        items_html = ""
        for item in items:
            items_html += f"""
                <div style="background:#fff;padding:12px 15px;margin:8px 0;border-left:4px solid #4CAF50;border-radius:3px;">
                    <strong>{item.get('product_name', 'N/A')}</strong><br>
                    Qty: {item.get('quantity', 0)} &times; &#8377;{item.get('price', 0):.2f} = <strong>&#8377;{item.get('total', 0):.2f}</strong>
                </div>"""

        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:0; }}
    .container {{ max-width:600px; margin:30px auto; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1); }}
    .header {{ background:#4CAF50; color:#fff; padding:24px 20px; text-align:center; }}
    .header h1 {{ margin:0; font-size:22px; }}
    .header p {{ margin:4px 0 0; font-size:14px; opacity:0.9; }}
    .body {{ padding:24px 20px; }}
    .section {{ margin-bottom:20px; }}
    .section h3 {{ color:#4CAF50; border-bottom:2px solid #4CAF50; padding-bottom:6px; margin-bottom:10px; font-size:15px; }}
    table {{ width:100%; border-collapse:collapse; }}
    td {{ padding:7px 4px; border-bottom:1px solid #eee; font-size:14px; }}
    .label {{ font-weight:bold; color:#555; width:110px; }}
    .total-box {{ background:#4CAF50; color:#fff; padding:14px; text-align:center; font-size:18px; font-weight:bold; border-radius:5px; margin-top:16px; }}
    .action-box {{ margin-top:16px; padding:12px 15px; background:#e7f3ff; border-left:4px solid #2196F3; border-radius:3px; font-size:14px; }}
    .footer {{ text-align:center; padding:14px; color:#999; font-size:12px; background:#f9f9f9; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>&#128722; New Order Received</h1>
      <p>Akshayam Wellness</p>
    </div>
    <div class="body">
      <div class="section">
        <h3>&#128203; Order Details</h3>
        <table>
          <tr><td class="label">Order ID:</td><td>{order_id}</td></tr>
          <tr><td class="label">Date:</td><td>{formatted_date}</td></tr>
        </table>
      </div>
      <div class="section">
        <h3>&#128100; Customer Information</h3>
        <table>
          <tr><td class="label">Name:</td><td>{user_name}</td></tr>
          <tr><td class="label">Email:</td><td>{user_email}</td></tr>
          <tr><td class="label">Phone:</td><td>{user_phone}</td></tr>
          <tr><td class="label">Address:</td><td>{user_address}</td></tr>
        </table>
      </div>
      <div class="section">
        <h3>&#128717; Order Items</h3>
        {items_html}
      </div>
      <div class="total-box">&#128176; Total Amount: &#8377;{total_amount:.2f}</div>
      <div class="action-box"><strong>&#9889; Action Required:</strong> Please process this order as soon as possible.</div>
    </div>
    <div class="footer">This is an automated notification from Akshayam Wellness System</div>
  </div>
</body>
</html>"""

        return text_body, html_body

    async def send_email(self, to_emails: List[str], subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
        """Send email via Gmail SMTP using TLS."""
        self._initialize_if_needed()

        if not self._sender_password:
            print("❌ SMTP: SENDER_PASSWORD not set in environment variables")
            logger.error("SMTP sender password not configured")
            return False

        try:
            print(f"📧 SMTP: Sending email to {to_emails}")

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self._sender_email
            msg["To"] = ", ".join(to_emails)

            # Attach plain text first, then HTML (email clients prefer last part)
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
            if body_html:
                msg.attach(MIMEText(body_html, "html", "utf-8"))

            # Connect and send — use SSL (port 465) or STARTTLS (port 587)
            if self._smtp_port == 465:
                with smtplib.SMTP_SSL(self._smtp_host, self._smtp_port) as server:
                    server.ehlo()
                    server.login(self._sender_email, self._sender_password)
                    server.sendmail(self._sender_email, to_emails, msg.as_string())
            else:
                with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self._sender_email, self._sender_password)
                    server.sendmail(self._sender_email, to_emails, msg.as_string())

            print(f"✅ SMTP: Email sent successfully to {to_emails}")
            logger.info(f"Email sent successfully via SMTP to {to_emails}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP Authentication failed: {str(e)}")
            print("💡 Make sure you are using a Gmail App Password, not your regular Gmail password.")
            print("   Go to: Google Account → Security → 2-Step Verification → App Passwords")
            logger.error(f"SMTP authentication error: {str(e)}")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP error: {str(e)}")
            logger.error(f"SMTP error: {str(e)}")
            return False
        except Exception as e:
            import traceback
            print(f"💥 SMTP unexpected error: {type(e).__name__}: {str(e)}")
            logger.error(f"SMTP unexpected error: {traceback.format_exc()}")
            return False

    async def send_order_notification(self, order_data: dict) -> bool:
        """Send order notification email to all admin recipients."""
        try:
            self._initialize_if_needed()

            text_body, html_body = self.format_order_details(order_data)

            order_id = order_data.get("_id", "N/A")
            user_name = order_data.get("user_name", "Customer")
            subject = f"New Order #{order_id} from {user_name} - Akshayam Wellness"

            recipients = self.admin_emails
            print(f"🔍 SMTP EMAIL DEBUG - Order {order_id}")
            print(f"📧 Sending to: {recipients}")
            print(f"📝 Subject: {subject}")

            success = await self.send_email(
                to_emails=recipients,
                subject=subject,
                body_text=text_body,
                body_html=html_body
            )

            if success:
                print(f"📬 SMTP: Order notification sent for order {order_id}")
                logger.info(f"Order notification sent via SMTP for order {order_id}")
            else:
                print(f"📭 SMTP: Failed to send order notification for order {order_id}")
                logger.error(f"Failed to send order notification via SMTP for order {order_id}")

            return success

        except Exception as e:
            print(f"💥 SMTP EXCEPTION in send_order_notification: {str(e)}")
            logger.error(f"Error in send_order_notification: {str(e)}")
            return False


# Global SMTP email service instance
smtp_email_service = SMTPEmailService()
