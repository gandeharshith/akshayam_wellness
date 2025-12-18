"""
Content management routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, UTC
from bson import ObjectId
from typing import Optional

from database import get_database, CONTENT_COLLECTION
from models import ContentCreate, ContentUpdate
from auth import get_current_admin
from utils.helpers import serialize_doc

router = APIRouter()


@router.get("/content/{page}")
async def get_content(page: str):
    """Get content for a specific page."""
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    content = await content_collection.find_one({"page": page})
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    return serialize_doc(content)


@router.get("/content")
async def get_all_content():
    """Get all content items sorted by order."""
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    content = []
    async for item in content_collection.find().sort("order", 1):
        content.append(serialize_doc(item))
    return content


@router.get("/content/{page}/{section}")
async def get_content_section(page: str, section: str):
    """Get content for a specific page section."""
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    content = await content_collection.find_one({"page": page, "section": section})
    if not content:
        raise HTTPException(status_code=404, detail="Content section not found")
    
    return serialize_doc(content)


@router.post("/admin/content", dependencies=[Depends(get_current_admin)])
async def create_content(content: ContentCreate):
    """Create new content."""
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    # Check if content already exists for this page/section
    existing = await content_collection.find_one({"page": content.page, "section": content.section})
    if existing:
        raise HTTPException(status_code=400, detail="Content for this page/section already exists")
    
    content_data = {
        "page": content.page,
        "section": content.section,
        "title": content.title,
        "content": content.content,
        "order": content.order,
        "logo_url": None,
        "updated_at": datetime.now(UTC)
    }
    
    result = await content_collection.insert_one(content_data)
    content_data["_id"] = str(result.inserted_id)
    return content_data


@router.put("/admin/content/{page}", dependencies=[Depends(get_current_admin)])
async def update_content(page: str, content_update: ContentUpdate):
    """Update content for a specific page."""
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    update_data = {k: v for k, v in content_update.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(UTC)
    
    result = await content_collection.update_one(
        {"page": page},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Content not found")
    
    updated_content = await content_collection.find_one({"page": page})
    return serialize_doc(updated_content)


@router.put("/admin/content/id/{content_id}", dependencies=[Depends(get_current_admin)])
async def update_content_by_id(content_id: str, content_update: ContentUpdate):
    """Update content by ID."""
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    update_data = {k: v for k, v in content_update.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now(UTC)
    
    result = await content_collection.update_one(
        {"_id": ObjectId(content_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Content not found")
    
    updated_content = await content_collection.find_one({"_id": ObjectId(content_id)})
    return serialize_doc(updated_content)


@router.delete("/admin/content/{content_id}", dependencies=[Depends(get_current_admin)])
async def delete_content(content_id: str):
    """Delete content by ID."""
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    result = await content_collection.delete_one({"_id": ObjectId(content_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Content not found")
    
    return {"message": "Content deleted successfully"}
