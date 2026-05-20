"""
Background email service for handling order notifications.
"""
import asyncio
from datetime import datetime, UTC
from typing import Dict, Any

from database import get_database, ORDERS_COLLECTION
from bson import ObjectId


async def send_order_email_background(order_doc: Dict[str, Any]):
    """Background task to send order notification email without blocking the API response."""
    try:
        print(f"🚀 Background: Attempting to send email notification for order {order_doc['_id']}")
        
        # Import here to avoid circular imports
        from smtp_email_service import smtp_email_service
        
        # Add retry logic for email sending
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                email_success = await smtp_email_service.send_order_notification(order_doc)
                if email_success:
                    print(f"✅ Background: Email notification sent successfully for order {order_doc['_id']} (attempt {attempt + 1})")
                    return
                else:
                    print(f"❌ Background: Email service returned False for order {order_doc['_id']} (attempt {attempt + 1})")
            except Exception as e:
                print(f"❌ Background: Email attempt {attempt + 1} failed for order {order_doc['_id']}: {str(e)}")
                if attempt < max_retries - 1:  # Don't sleep on the last attempt
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
        
        # If all retries failed, log the final failure
        print(f"❌ Background: All email attempts failed for order {order_doc['_id']} after {max_retries} retries")
        
        # Update the order document in the database to flag email failure
        try:
            db = await get_database()
            orders_collection = db[ORDERS_COLLECTION]
            await orders_collection.update_one(
                {"_id": ObjectId(order_doc['_id'])},
                {"$set": {"email_notification_failed": True, "email_failure_timestamp": datetime.now(UTC)}}
            )
        except Exception as db_e:
            print(f"❌ Background: Failed to update order email failure status: {str(db_e)}")
            
    except Exception as e:
        # Log any unexpected errors in the background task
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Background: Critical error in email background task for order {order_doc['_id']}: {str(e)}")
        print(f"📋 Background: Full error traceback: {error_details}")
