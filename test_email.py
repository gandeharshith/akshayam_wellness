#!/usr/bin/env python3
"""
Test script for email notification functionality
Run this to test if email notifications are working correctly
"""

import asyncio
import os
from datetime import datetime, UTC
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from email_service import email_service

async def test_email_notification():
    """Test the email notification system"""
    
    print("Testing Email Notification System...")
    print("=" * 50)
    
    # Check if email configuration is set up
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    admin_email = os.getenv("ADMIN_EMAIL", "akshayamwellness@gmail.com")
    
    print(f"Sender Email: {sender_email}")
    print(f"Admin Email: {admin_email}")
    print(f"Password Set: {'Yes' if sender_password else 'No'}")
    print()
    
    if not sender_email or not sender_password:
        print("❌ ERROR: Email configuration incomplete!")
        print("Please update the .env file with:")
        print("  SENDER_EMAIL=your-gmail@gmail.com")
        print("  SENDER_PASSWORD=your-app-password")
        print("\nFor Gmail:")
        print("1. Enable 2-Factor Authentication")
        print("2. Generate App Password: https://support.google.com/accounts/answer/185833")
        print("3. Use the App Password (not your regular password)")
        return False
    
    # Create a sample order for testing
    sample_order = {
        "_id": "test_order_123456",
        "user_name": "Test Customer",
        "user_email": "test@example.com",
        "user_phone": "+91-9876543210",
        "user_address": "123 Test Street, Test City, Test State - 123456",
        "items": [
            {
                "product_name": "Organic Turmeric Powder",
                "quantity": 2,
                "price": 150.0,
                "total": 300.0
            },
            {
                "product_name": "Herbal Tea Blend",
                "quantity": 1,
                "price": 250.0,
                "total": 250.0
            }
        ],
        "total_amount": 550.0,
        "created_at": datetime.now(UTC)
    }
    
    print("📧 Sending test order notification...")
    print("Sample Order Details:")
    print(f"  Order ID: {sample_order['_id']}")
    print(f"  Customer: {sample_order['user_name']}")
    print(f"  Total: ₹{sample_order['total_amount']}")
    print(f"  Items: {len(sample_order['items'])} products")
    print()
    
    try:
        # Send the test email
        success = await email_service.send_order_notification(sample_order)
        
        if success:
            print("✅ SUCCESS: Test email sent successfully!")
            print(f"📬 Check your inbox at: {admin_email}")
            print("\nThe email notification system is working correctly.")
            print("When customers place orders, you will receive notifications automatically.")
        else:
            print("❌ FAILED: Could not send test email")
            print("Please check your email configuration and try again.")
        
        return success
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        print("Please check your email configuration and internet connection.")
        return False

if __name__ == "__main__":
    print("🚀 Akshayam Wellness - Email Notification Test")
    print()
    
    # Run the test
    success = asyncio.run(test_email_notification())
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 Email system is ready for production!")
        print("\nNext steps:")
        print("1. Update .env with your actual email credentials")
        print("2. Start your backend server: python main.py")
        print("3. Test order placement from frontend")
        print("4. You'll receive email notifications at akshayamwellness@gmail.com")
    else:
        print("⚠️  Please fix the configuration and try again.")
        print("\nNeed help? Check the setup instructions in .env file")
    
    print("\n📧 Email notifications will be sent to: akshayamwellness@gmail.com")
