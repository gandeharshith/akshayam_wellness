"""
Product management routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, UTC
from bson import ObjectId
from typing import Optional

from database import get_database, PRODUCTS_COLLECTION, CATEGORIES_COLLECTION
from models import ProductCreate, ProductUpdate, ReorderRequest, StockValidationRequest, StockValidationResponse, StockValidationItem
from auth import get_current_admin
from utils.helpers import serialize_doc

router = APIRouter()


@router.get("/products")
async def get_products(category_id: Optional[str] = None):
    """Get all products, optionally filtered by category."""
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    query = {}
    if category_id:
        query["category_id"] = category_id
    
    products = []
    async for product in products_collection.find(query).sort("order", 1):
        products.append(serialize_doc(product))
    return products


@router.get("/products/{product_id}")
async def get_product(product_id: str):
    """Get a specific product by ID."""
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return serialize_doc(product)


@router.post("/admin/products", dependencies=[Depends(get_current_admin)])
async def create_product(product: ProductCreate):
    """Create a new product."""
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    categories_collection = db[CATEGORIES_COLLECTION]
    
    # Verify category exists
    category = await categories_collection.find_one({"_id": ObjectId(product.category_id)})
    if not category:
        raise HTTPException(status_code=400, detail="Invalid category ID")
    
    # Get the next order number
    last_product = await products_collection.find_one({}, sort=[("order", -1)])
    next_order = (last_product.get("order", 0) + 1) if last_product else 1
    
    product_data = {
        "name": product.name,
        "description": product.description,
        "category_id": product.category_id,
        "price": product.price,
        "quantity": product.quantity,
        "image_url": None,
        "order": next_order,
        "created_at": datetime.now(UTC)
    }
    
    result = await products_collection.insert_one(product_data)
    product_data["_id"] = str(result.inserted_id)
    return product_data


@router.put("/admin/products/reorder", dependencies=[Depends(get_current_admin)])
async def reorder_products(reorder_request: ReorderRequest):
    """Reorder products by updating their order field."""
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    # Update each product's order
    for item in reorder_request.items:
        await products_collection.update_one(
            {"_id": ObjectId(item.id)},
            {"$set": {"order": item.order}}
        )
    
    return {"message": "Products reordered successfully"}


@router.put("/admin/products/{product_id}", dependencies=[Depends(get_current_admin)])
async def update_product(product_id: str, product: ProductUpdate):
    """Update a product."""
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    update_data = {k: v for k, v in product.dict().items() if v is not None}
    if update_data:
        await products_collection.update_one(
            {"_id": ObjectId(product_id)}, 
            {"$set": update_data}
        )
    
    updated_product = await products_collection.find_one({"_id": ObjectId(product_id)})
    return serialize_doc(updated_product)


@router.delete("/admin/products/{product_id}", dependencies=[Depends(get_current_admin)])
async def delete_product(product_id: str):
    """Delete a product."""
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    result = await products_collection.delete_one({"_id": ObjectId(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {"message": "Product deleted successfully"}


@router.post("/validate-stock")
async def validate_stock(stock_request: StockValidationRequest):
    """Validate stock availability for cart items before checkout."""
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    invalid_items = []
    
    for item in stock_request.items:
        try:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if not product:
                invalid_items.append({
                    "product_id": item.product_id,
                    "requested_quantity": item.quantity,
                    "available_quantity": 0,
                    "error": "Product not found"
                })
                continue
                
            if product["quantity"] <= 0:
                invalid_items.append({
                    "product_id": item.product_id,
                    "product_name": product["name"],
                    "requested_quantity": item.quantity,
                    "available_quantity": product["quantity"],
                    "error": f"{product['name']} is out of stock"
                })
            elif product["quantity"] < item.quantity:
                invalid_items.append({
                    "product_id": item.product_id,
                    "product_name": product["name"],
                    "requested_quantity": item.quantity,
                    "available_quantity": product["quantity"],
                    "error": f"{product['name']} has only {product['quantity']} items available, but you requested {item.quantity}"
                })
        except Exception as e:
            invalid_items.append({
                "product_id": item.product_id,
                "requested_quantity": item.quantity,
                "available_quantity": 0,
                "error": "Invalid product ID"
            })
    
    if invalid_items:
        return StockValidationResponse(
            valid=False,
            message="Some items in your cart are not available in the requested quantities",
            invalid_items=invalid_items
        )
    
    return StockValidationResponse(
        valid=True,
        message="All items are available in stock",
        invalid_items=[]
    )
