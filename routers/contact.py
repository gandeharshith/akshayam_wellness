"""
Contact information management routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, UTC

from database import get_database, CONTACT_INFO_COLLECTION
from models import ContactInfoUpdate
from auth import get_current_admin
from utils.helpers import serialize_doc

router = APIRouter()


@router.get("/contact-info")
async def get_contact_info():
    """Get contact information."""
    db = await get_database()
    contact_collection = db[CONTACT_INFO_COLLECTION]
    
    contact = await contact_collection.find_one()
    if not contact:
        # Return default contact info if none exists
        return {
            "company_name": "Akshayam Wellness",
            "company_description": "Your trusted partner in organic wellness products.",
            "email": "info@akshayamwellness.com",
            "phone": "+91-9876543210",
            "address": "123 Wellness Street, Organic City"
        }
    
    return serialize_doc(contact)


@router.put("/admin/contact-info", dependencies=[Depends(get_current_admin)])
async def update_contact_info(contact_update: ContactInfoUpdate):
    """Update contact information."""
    db = await get_database()
    contact_collection = db[CONTACT_INFO_COLLECTION]
    
    update_data = {k: v for k, v in contact_update.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(UTC)
    
    # Check if contact info exists
    existing = await contact_collection.find_one()
    if existing:
        result = await contact_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": update_data}
        )
        updated_contact = await contact_collection.find_one({"_id": existing["_id"]})
    else:
        # Create new contact info document
        contact_data = {
            "company_name": "Akshayam Wellness",
            "company_description": "Your trusted partner in organic wellness products.",
            "email": "info@akshayamwellness.com",
            "phone": "+91-9876543210",
            "address": "123 Wellness Street, Organic City",
            "updated_at": datetime.now(UTC)
        }
        contact_data.update(update_data)
        
        result = await contact_collection.insert_one(contact_data)
        updated_contact = await contact_collection.find_one({"_id": result.inserted_id})
    
    return serialize_doc(updated_contact)
