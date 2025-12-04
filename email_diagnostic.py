#!/usr/bin/env python3
"""
Comprehensive Email Diagnostic Tool for Production Issues
Run this to diagnose email delivery problems in production vs local environments
"""

import asyncio
import os
import sys
import socket
import ssl
import smtplib
from datetime import datetime
from dotenv import load_dotenv
import logging

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

async def check_network_connectivity():
    """Test network connectivity to Gmail SMTP server"""
    print("🌐 Testing Network Connectivity...")
    print("=" * 50)
    
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    
    try:
        # Test basic TCP connection
        sock = socket.create_connection((smtp_server, smtp_port), timeout=10)
        sock.close()
        print(f"✅ TCP connection to {smtp_server}:{smtp_port} - SUCCESS")
        return True
    except Exception as e:
        print(f"❌ TCP connection to {smtp_server}:{smtp_port} - FAILED: {e}")
        return False

def check_ssl_certificates():
    """Check SSL certificate validity"""
    print("\n🔒 Testing SSL Certificates...")
    print("=" * 50)
    
    try:
        context = ssl.create_default_context()
        with socket.create_connection(("smtp.gmail.com", 587), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname="smtp.gmail.com") as ssock:
                cert = ssock.getpeercert()
                print(f"✅ SSL Certificate - VALID")
                print(f"   Subject: {dict(x[0] for x in cert['subject'])}")
                print(f"   Issuer: {dict(x[0] for x in cert['issuer'])}")
                print(f"   Valid until: {cert['notAfter']}")
                return True
    except Exception as e:
        print(f"❌ SSL Certificate check - FAILED: {e}")
        return False

def test_smtp_auth():
    """Test SMTP authentication without sending email"""
    print("\n🔐 Testing SMTP Authentication...")
    print("=" * 50)
    
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    
    if not sender_email or not sender_password:
        print("❌ Missing email credentials in environment variables")
        return False
    
    try:
        # Test synchronous SMTP connection
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.quit()
        print(f"✅ SMTP Authentication - SUCCESS")
        print(f"   Email: {sender_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication - FAILED: {e}")
        print("   Possible causes:")
        print("   1. Invalid email/password combination")
        print("   2. App Password not generated or incorrect")
        print("   3. 2-Factor Authentication not enabled")
        print("   4. Account security settings blocking access")
        return False
    except Exception as e:
        print(f"❌ SMTP Connection - FAILED: {e}")
        return False

async def test_async_email():
    """Test async email sending (same as production)"""
    print("\n📧 Testing Async Email Sending...")
    print("=" * 50)
    
    try:
        from email_service import email_service
        
        # Create a simple test email
        test_result = await email_service.send_email(
            to_emails=[os.getenv("ADMIN_EMAIL", "akshayamwellness@gmail.com")],
            subject="🧪 Production Email Test - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            body_text=f"""
This is a test email from your production email diagnostic tool.

Environment Details:
- Python Version: {sys.version}
- Server Time: {datetime.now()}
- Environment: {'LOCAL' if os.path.exists('.env') else 'PRODUCTION'}

If you received this email, your email service is working correctly in this environment.
""",
            body_html=f"""
<html>
<body>
<h2>🧪 Production Email Test</h2>
<p>This is a test email from your production email diagnostic tool.</p>

<h3>Environment Details:</h3>
<ul>
<li><strong>Python Version:</strong> {sys.version}</li>
<li><strong>Server Time:</strong> {datetime.now()}</li>
<li><strong>Environment:</strong> {'LOCAL' if os.path.exists('.env') else 'PRODUCTION'}</li>
</ul>

<p>If you received this email, your email service is working correctly in this environment.</p>
</body>
</html>
"""
        )
        
        if test_result:
            print("✅ Async Email Test - SUCCESS")
            print(f"   Test email sent to: {os.getenv('ADMIN_EMAIL')}")
            return True
        else:
            print("❌ Async Email Test - FAILED")
            return False
            
    except Exception as e:
        print(f"❌ Async Email Test - ERROR: {e}")
        import traceback
        print(f"   Full traceback: {traceback.format_exc()}")
        return False

def check_environment_variables():
    """Check all required environment variables"""
    print("\n⚙️ Checking Environment Variables...")
    print("=" * 50)
    
    required_vars = [
        "SMTP_SERVER",
        "SMTP_PORT", 
        "SENDER_EMAIL",
        "SENDER_PASSWORD",
        "ADMIN_EMAIL"
    ]
    
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if var == "SENDER_PASSWORD":
                # Don't show password, just indicate it's set
                print(f"✅ {var}: [SET - {len(value)} characters]")
            else:
                print(f"✅ {var}: {value}")
        else:
            missing_vars.append(var)
            print(f"❌ {var}: NOT SET")
    
    if missing_vars:
        print(f"\n⚠️ Missing environment variables: {missing_vars}")
        return False
    
    return True

def check_production_specific_issues():
    """Check for common production deployment issues"""
    print("\n🏭 Checking Production-Specific Issues...")
    print("=" * 50)
    
    issues_found = []
    
    # Check if running in containerized environment
    if os.path.exists('/.dockerenv'):
        print("🐳 Running in Docker container")
        issues_found.append("docker")
    
    # Check for firewall/port restrictions
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex(("smtp.gmail.com", 587))
        sock.close()
        
        if result == 0:
            print("✅ Port 587 (SMTP) - ACCESSIBLE")
        else:
            print("❌ Port 587 (SMTP) - BLOCKED")
            issues_found.append("port_blocked")
    except Exception as e:
        print(f"❌ Port check failed: {e}")
        issues_found.append("port_check_failed")
    
    # Check DNS resolution
    try:
        import socket
        ip = socket.gethostbyname("smtp.gmail.com")
        print(f"✅ DNS Resolution for smtp.gmail.com: {ip}")
    except Exception as e:
        print(f"❌ DNS Resolution failed: {e}")
        issues_found.append("dns_failed")
    
    return issues_found

def provide_production_solutions():
    """Provide solutions for common production issues"""
    print("\n🛠️ Production Email Setup Solutions...")
    print("=" * 70)
    
    solutions = {
        "environment_vars": """
1. ENVIRONMENT VARIABLES SETUP:
   
   For most cloud platforms, set these environment variables:
   
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SENDER_EMAIL=akshayamwellnessorders@gmail.com
   SENDER_PASSWORD=gugshsluihzdxdac
   ADMIN_EMAIL=akshayamwellness@gmail.com
   
   Platform-specific instructions:
   
   📱 Vercel:
   - Go to project settings → Environment Variables
   - Add each variable individually
   
   ☁️ Heroku:
   heroku config:set SENDER_EMAIL=akshayamwellnessorders@gmail.com
   
   🐳 Docker:
   docker run -e SENDER_EMAIL=your-email ...
   
   🚀 Railway/Render:
   - Use the dashboard to set environment variables
""",
        
        "gmail_security": """
2. GMAIL SECURITY SETUP:
   
   ✅ Verify these Gmail account settings:
   
   a) Enable 2-Factor Authentication:
      - Go to Google Account → Security
      - Enable 2-Step Verification
   
   b) Generate App Password:
      - Google Account → Security → App passwords
      - Select "Mail" and generate password
      - Use this 16-character password (not your regular password)
   
   c) Less Secure Apps (if needed):
      - This is deprecated, use App Passwords instead
""",
        
        "firewall_ports": """
3. NETWORK/FIREWALL CONFIGURATION:
   
   🔥 Ensure these ports are open in production:
   
   - Port 587 (STARTTLS) - Primary
   - Port 465 (SSL/TLS) - Alternative
   - Port 25 (Plain) - Usually blocked by ISPs
   
   For cloud platforms:
   - Most allow outbound SMTP by default
   - Check security groups/firewall rules if needed
""",
        
        "alternative_services": """
4. ALTERNATIVE EMAIL SERVICES:
   
   If Gmail doesn't work in production, consider:
   
   📧 SendGrid:
   SMTP_SERVER=smtp.sendgrid.net
   SMTP_PORT=587
   SENDER_EMAIL=your-verified-email@domain.com
   SENDER_PASSWORD=your-sendgrid-api-key
   
   📮 AWS SES:
   SMTP_SERVER=email-smtp.us-east-1.amazonaws.com
   SMTP_PORT=587
   SENDER_EMAIL=your-verified-email@domain.com
   SENDER_PASSWORD=your-ses-smtp-password
   
   📬 Mailgun:
   SMTP_SERVER=smtp.mailgun.org
   SMTP_PORT=587
   SENDER_EMAIL=postmaster@your-domain.mailgun.org
   SENDER_PASSWORD=your-mailgun-password
""",
        
        "debugging": """
5. DEBUGGING IN PRODUCTION:
   
   🔍 Add logging to your production app:
   
   import logging
   logging.basicConfig(level=logging.DEBUG)
   
   📊 Monitor logs for errors:
   - SMTP authentication failures
   - Network timeouts
   - SSL certificate issues
   
   🧪 Test email sending:
   - Run this diagnostic script in production
   - Check application logs for detailed errors
"""
    }
    
    for title, solution in solutions.items():
        print(solution)
        print("=" * 70)

async def main():
    """Run comprehensive email diagnostic"""
    print("🚀 Akshayam Wellness - Email Production Diagnostic")
    print("=" * 70)
    print("This tool will help diagnose email delivery issues in production")
    print("=" * 70)
    
    # Track test results
    results = {
        "network": False,
        "ssl": False,
        "auth": False,
        "env_vars": False,
        "async_email": False
    }
    
    # Run all diagnostic tests
    results["env_vars"] = check_environment_variables()
    results["network"] = await check_network_connectivity()
    results["ssl"] = check_ssl_certificates()
    results["auth"] = test_smtp_auth()
    
    if all([results["env_vars"], results["network"], results["ssl"], results["auth"]]):
        results["async_email"] = await test_async_email()
    
    production_issues = check_production_specific_issues()
    
    # Summary
    print("\n📊 DIAGNOSTIC SUMMARY")
    print("=" * 70)
    
    passed_tests = sum(results.values())
    total_tests = len(results)
    
    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test.replace('_', ' ').title():<20} {status}")
    
    print(f"\nOverall: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\n🎉 All tests passed! Email service should work in production.")
    else:
        print(f"\n⚠️ {total_tests - passed_tests} test(s) failed. Email delivery may not work.")
        print("See solutions below to fix the issues.")
    
    if production_issues:
        print(f"\n🏭 Production issues detected: {production_issues}")
    
    # Always provide solutions
    provide_production_solutions()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⏹️ Diagnostic interrupted by user")
    except Exception as e:
        print(f"\n\n💥 Diagnostic failed with error: {e}")
        import traceback
        print(traceback.format_exc())
