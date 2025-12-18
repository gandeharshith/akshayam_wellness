"""
System settings management routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, UTC

from database import get_database, SYSTEM_SETTINGS_COLLECTION
from models import SystemSettingsUpdate
from auth import get_current_admin
from utils.helpers import serialize_doc

router = APIRouter()


@router.get("/settings/{key}")
async def get_system_setting(key: str):
    """Get a system setting by key (public endpoint)."""
    db = await get_database()
    settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
    
    setting = await settings_collection.find_one({"key": key})
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    return serialize_doc(setting)


@router.get("/admin/settings", dependencies=[Depends(get_current_admin)])
async def get_all_system_settings():
    """Get all system settings (admin only)."""
    db = await get_database()
    settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
    
    settings = []
    async for setting in settings_collection.find():
        settings.append(serialize_doc(setting))
    return settings


@router.put("/admin/settings/{key}", dependencies=[Depends(get_current_admin)])
async def update_system_setting(key: str, setting_update: SystemSettingsUpdate):
    """Update a system setting (admin only)."""
    db = await get_database()
    settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
    
    update_data = {
        "value": setting_update.value,
        "updated_at": datetime.now(UTC)
    }
    
    if setting_update.description is not None:
        update_data["description"] = setting_update.description
    
    result = await settings_collection.update_one(
        {"key": key},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    updated_setting = await settings_collection.find_one({"key": key})
    return serialize_doc(updated_setting)
