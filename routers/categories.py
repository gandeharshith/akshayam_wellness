"""
Category management routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, UTC
from bson import ObjectId
from typing import List

from database import get_database, CATEGORIES_COLLECTION, PRODUCTS_COLLECTION
from models import CategoryCreate, CategoryUpdate, ReorderRequest
from auth import get_current_admin
from utils.helpers import serialize_doc

router = APIRouter()


@router.get("/categories")
async def get_categories():
    """Get all categories sorted by order."""
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    categories = []
    async for category in categories_collection.find().sort("order", 1):
        categories.append(serialize_doc(category))
    return categories


@router.post("/admin/categories", dependencies=[Depends(get_current_admin)])
async def create_category(category: CategoryCreate):
    """Create a new category."""
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    
    # Get the next order number
    last_category = await categories_collection.find_one({}, sort=[("order", -1)])
    next_order = (last_category.get("order", 0) + 1) if last_category else 1
    
    category_data = {
        "name": category.name,
        "description": category.description,
        "image_url": None,
        "order": next_order,
        "created_at": datetime.now(UTC)
    }
    
    result = await categories_collection.insert_one(category_data)
    category_data["_id"] = str(result.inserted_id)
    return category_data


@router.put("/admin/categories/reorder", dependencies=[Depends(get_current_admin)])
async def reorder_categories(reorder_request: ReorderRequest):
    """Reorder categories by updating their order field."""
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    
    # Update each category's order
    for item in reorder_request.items:
        await categories_collection.update_one(
            {"_id": ObjectId(item.id)},
            {"$set": {"order": item.order}}
        )
    
    return {"message": "Categories reordered successfully"}


@router.put("/admin/categories/{category_id}", dependencies=[Depends(get_current_admin)])
async def update_category(category_id: str, category: CategoryUpdate):
    """Update a category."""
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    
    update_data = {k: v for k, v in category.dict().items() if v is not None}
    if update_data:
        await categories_collection.update_one(
            {"_id": ObjectId(category_id)}, 
            {"$set": update_data}
        )
    
    updated_category = await categories_collection.find_one({"_id": ObjectId(category_id)})
    return serialize_doc(updated_category)


@router.delete("/admin/categories/{category_id}", dependencies=[Depends(get_current_admin)])
async def delete_category(category_id: str):
    """Delete a category if it has no products."""
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    products_collection = db[PRODUCTS_COLLECTION]
    
    # Check if category has products
    products_count = await products_collection.count_documents({"category_id": category_id})
    if products_count > 0:
        raise HTTPException(status_code=400, detail="Cannot delete category with existing products")
    
    result = await categories_collection.delete_one({"_id": ObjectId(category_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    
    return {"message": "Category deleted successfully"}
