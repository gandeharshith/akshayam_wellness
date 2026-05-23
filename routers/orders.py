"""
Order management routes.
"""
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from datetime import datetime, UTC
from bson import ObjectId
from typing import Optional

from database import get_database, ORDERS_COLLECTION, USERS_COLLECTION, PRODUCTS_COLLECTION, SYSTEM_SETTINGS_COLLECTION
from models import (
    OrderCreate, OrderStatusUpdate, OrderEditRequest, UserOrderEditRequest, 
    StockValidationRequest, StockValidationResponse, StockValidationItem, UserLogin
)
from auth import get_current_admin, get_password_hash, verify_password
from utils.helpers import serialize_doc
from services.email_service import send_order_email_background

router = APIRouter()


@router.post("/orders")
async def create_order(order_data: OrderCreate, background_tasks: BackgroundTasks):
    """Create a new order."""
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    users_collection = db[USERS_COLLECTION]
    products_collection = db[PRODUCTS_COLLECTION]
    
    # First validate stock availability with detailed error messages
    stock_validation_items = [
        StockValidationItem(product_id=item.product_id, quantity=item.quantity) 
        for item in order_data.items
    ]
    stock_request = StockValidationRequest(items=stock_validation_items)
    
    from routers.products import validate_stock
    validation_result = await validate_stock(stock_request)
    
    if not validation_result.valid:
        error_messages = [item["error"] for item in validation_result.invalid_items]
        raise HTTPException(
            status_code=400, 
            detail={
                "message": validation_result.message,
                "errors": error_messages,
                "invalid_items": validation_result.invalid_items
            }
        )
    
    # Create or get user — only update password if this is a NEW user
    user_data = order_data.user_info.model_dump()
    new_password_hash = get_password_hash(user_data.pop("password"))
    user_data["created_at"] = datetime.now(UTC)
    
    existing_user = await users_collection.find_one({"email": user_data["email"]})
    if existing_user:
        user_id = str(existing_user["_id"])
        # Do NOT overwrite password on every order — only update non-auth fields
        await users_collection.update_one(
            {"_id": existing_user["_id"]},
            {"$set": {
                "name": user_data.get("name", existing_user.get("name")),
                "phone": user_data.get("phone", existing_user.get("phone")),
                "address": user_data.get("address", existing_user.get("address")),
            }}
        )
    else:
        user_data["password_hash"] = new_password_hash
        user_result = await users_collection.insert_one(user_data)
        user_id = str(user_result.inserted_id)
    
    # Calculate total amount
    total_amount = sum(item.total for item in order_data.items)
    
    # Check minimum order value
    settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
    min_order_setting = await settings_collection.find_one({"key": "minimum_order_value"})
    if min_order_setting and total_amount < min_order_setting["value"]:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum order value is ₹{min_order_setting['value']:.0f}. Your cart total is ₹{total_amount:.0f}. Please add more items to meet the minimum order requirement."
        )
    
    # Create order
    order_doc = {
        "user_id": user_id,
        "user_name": order_data.user_info.name,
        "user_email": order_data.user_info.email,
        "user_phone": order_data.user_info.phone,
        "user_address": order_data.user_info.address,
        "items": [item.model_dump() for item in order_data.items],
        "total_amount": total_amount,
        "status": "pending",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    }
    
    result = await orders_collection.insert_one(order_doc)
    
    # Deduct product quantities
    for item in order_data.items:
        await products_collection.update_one(
            {"_id": ObjectId(item.product_id)},
            {"$inc": {"quantity": -item.quantity}}
        )
    
    order_doc["_id"] = str(result.inserted_id)
    
    print(f"📧 Scheduling background email notification for order {order_doc['_id']}")
    background_tasks.add_task(send_order_email_background, order_doc.copy())
    
    print(f"✅ Order {order_doc['_id']} created successfully - email notification scheduled in background")
    return order_doc


@router.post("/orders/user")
async def get_user_orders(user_data: UserLogin):
    """Get orders for a specific user."""
    db = await get_database()
    users_collection = db[USERS_COLLECTION]
    orders_collection = db[ORDERS_COLLECTION]
    
    user = await users_collection.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    orders = []
    async for order in orders_collection.find({"user_email": user_data.email}).sort("created_at", -1):
        orders.append(serialize_doc(order))
    return orders


@router.get("/admin/orders", dependencies=[Depends(get_current_admin)])
async def get_all_orders():
    """Get all orders (admin only)."""
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    
    orders = []
    async for order in orders_collection.find().sort("created_at", -1):
        orders.append(serialize_doc(order))
    return orders


# ── Static admin routes MUST come before /{order_id} dynamic routes ──────────

@router.get("/admin/orders/analytics", dependencies=[Depends(get_current_admin)])
async def get_order_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: Optional[str] = "product"
):
    """Get order analytics with optional date filtering and grouping."""
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    
    match_stage = {}
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = datetime.fromisoformat(start_date.replace('Z', '+00:00')).replace(tzinfo=UTC)
        if end_date:
            date_filter["$lte"] = datetime.fromisoformat(end_date.replace('Z', '+00:00')).replace(tzinfo=UTC)
        match_stage["created_at"] = date_filter
    
    if group_by == "week":
        pipeline = [
            {"$match": match_stage},
            {"$unwind": "$items"},
            {"$group": {
                "_id": {"year": {"$year": "$created_at"}, "week": {"$week": "$created_at"}},
                "order_count": {"$addToSet": "$_id"},
                "total_quantity": {"$sum": "$items.quantity"},
                "total_revenue": {"$sum": "$items.total"},
                "total_items": {"$sum": 1}
            }},
            {"$project": {
                "_id": 1,
                "order_count": {"$size": "$order_count"},
                "total_quantity": 1,
                "total_revenue": 1,
                "total_items": 1
            }},
            {"$sort": {"_id.year": -1, "_id.week": -1}},
            {"$limit": 52}
        ]
        analytics = []
        async for result in orders_collection.aggregate(pipeline):
            year = result["_id"]["year"]
            week = result["_id"]["week"]
            analytics.append({
                "product_id": f"week-{year}-{week}",
                "product_name": f"Week {week}, {year}",
                "period": f"Week {week}, {year}",
                "total_quantity": result["total_quantity"],
                "total_revenue": result["total_revenue"],
                "order_count": result["order_count"]
            })
        return analytics

    elif group_by == "month":
        pipeline = [
            {"$match": match_stage},
            {"$unwind": "$items"},
            {"$group": {
                "_id": {"year": {"$year": "$created_at"}, "month": {"$month": "$created_at"}},
                "order_count": {"$addToSet": "$_id"},
                "total_quantity": {"$sum": "$items.quantity"},
                "total_revenue": {"$sum": "$items.total"},
                "total_items": {"$sum": 1}
            }},
            {"$project": {
                "_id": 1,
                "order_count": {"$size": "$order_count"},
                "total_quantity": 1,
                "total_revenue": 1,
                "total_items": 1
            }},
            {"$sort": {"_id.year": -1, "_id.month": -1}},
            {"$limit": 24}
        ]
        month_names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        analytics = []
        async for result in orders_collection.aggregate(pipeline):
            year = result["_id"]["year"]
            month = result["_id"]["month"]
            analytics.append({
                "product_id": f"month-{year}-{month}",
                "product_name": f"{month_names[month]} {year}",
                "period": f"{month_names[month]} {year}",
                "total_quantity": result["total_quantity"],
                "total_revenue": result["total_revenue"],
                "order_count": result["order_count"]
            })
        return analytics

    else:
        # Product analytics (default)
        pipeline = [
            {"$match": match_stage},
            {"$unwind": "$items"},
            {"$group": {
                "_id": "$items.product_id",
                "product_name": {"$first": "$items.product_name"},
                "total_quantity": {"$sum": "$items.quantity"},
                "total_revenue": {"$sum": "$items.total"},
                "order_count": {"$sum": 1},
                "avg_quantity_per_order": {"$avg": "$items.quantity"},
                "avg_revenue_per_order": {"$avg": "$items.total"}
            }},
            {"$sort": {"total_revenue": -1}}
        ]
        analytics = []
        async for result in orders_collection.aggregate(pipeline):
            analytics.append({
                "product_id": result["_id"],
                "product_name": result["product_name"],
                "total_quantity": result["total_quantity"],
                "total_revenue": result["total_revenue"],
                "order_count": result["order_count"],
                "avg_quantity_per_order": result.get("avg_quantity_per_order", 0),
                "avg_revenue_per_order": result.get("avg_revenue_per_order", 0)
            })
        return analytics


@router.get("/admin/orders/summary", dependencies=[Depends(get_current_admin)])
async def get_orders_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get overall orders summary with optional date filtering."""
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    
    match_stage = {}
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = datetime.fromisoformat(start_date.replace('Z', '+00:00')).replace(tzinfo=UTC)
        if end_date:
            date_filter["$lte"] = datetime.fromisoformat(end_date.replace('Z', '+00:00')).replace(tzinfo=UTC)
        match_stage["created_at"] = date_filter
    
    pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": None,
            "total_orders": {"$sum": 1},
            "total_revenue": {"$sum": "$total_amount"},
            "avg_order_value": {"$avg": "$total_amount"},
            "total_items_sold": {"$sum": {"$sum": "$items.quantity"}},
            "status_breakdown": {"$push": "$status"},
            "min_order_value": {"$min": "$total_amount"},
            "max_order_value": {"$max": "$total_amount"}
        }}
    ]
    
    result = None
    async for doc in orders_collection.aggregate(pipeline):
        result = doc
        break
    
    if not result:
        return {
            "total_orders": 0, "total_revenue": 0, "avg_order_value": 0,
            "total_items_sold": 0, "min_order_value": 0, "max_order_value": 0,
            "status_counts": {}
        }
    
    status_counts = {}
    for status in result.get("status_breakdown", []):
        status_counts[status] = status_counts.get(status, 0) + 1
    
    return {
        "total_orders": result.get("total_orders", 0),
        "total_revenue": result.get("total_revenue", 0),
        "avg_order_value": result.get("avg_order_value", 0),
        "total_items_sold": result.get("total_items_sold", 0),
        "min_order_value": result.get("min_order_value", 0),
        "max_order_value": result.get("max_order_value", 0),
        "status_counts": status_counts
    }


# ── Dynamic /{order_id} routes AFTER static routes ───────────────────────────

@router.put("/admin/orders/{order_id}/status", dependencies=[Depends(get_current_admin)])
async def update_order_status(order_id: str, status_update: OrderStatusUpdate):
    """Update order status (admin only)."""
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    
    result = await orders_collection.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": status_update.status, "updated_at": datetime.now(UTC)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    
    updated_order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return serialize_doc(updated_order)


@router.put("/orders/{order_id}/edit")
async def edit_order(order_id: str, user_order_edit: UserOrderEditRequest):
    """Edit order items for orders with status 'pending' or 'confirmed'."""
    try:
        db = await get_database()
        orders_collection = db[ORDERS_COLLECTION]
        users_collection = db[USERS_COLLECTION]
        products_collection = db[PRODUCTS_COLLECTION]
        
        order = await orders_collection.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order["status"] not in ["pending", "confirmed"]:
            raise HTTPException(status_code=400, detail=f"Cannot edit order with status '{order['status']}'. Orders can only be edited when status is 'pending' or 'confirmed'.")
        
        user = await users_collection.find_one({"email": user_order_edit.email})
        if not user or not verify_password(user_order_edit.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        if order["user_email"] != user_order_edit.email:
            raise HTTPException(status_code=403, detail="You can only edit your own orders")
        
        for item in user_order_edit.items:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if not product:
                raise HTTPException(status_code=400, detail=f"Product {item.product_name} not found")
        
        # Restore stock from original order
        for original_item in order["items"]:
            await products_collection.update_one(
                {"_id": ObjectId(original_item["product_id"])},
                {"$inc": {"quantity": original_item["quantity"]}}
            )
        
        # Check new stock availability
        for item in user_order_edit.items:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if product["quantity"] < item.quantity:
                for original_item in order["items"]:
                    await products_collection.update_one(
                        {"_id": ObjectId(original_item["product_id"])},
                        {"$inc": {"quantity": -original_item["quantity"]}}
                    )
                raise HTTPException(
                    status_code=400,
                    detail=f"{product['name']} has only {product['quantity']} items available, but you requested {item.quantity}"
                )
        
        # Deduct new stock
        for item in user_order_edit.items:
            await products_collection.update_one(
                {"_id": ObjectId(item.product_id)},
                {"$inc": {"quantity": -item.quantity}}
            )
        
        new_total_amount = sum(item.total for item in user_order_edit.items)
        
        settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
        min_order_setting = await settings_collection.find_one({"key": "minimum_order_value"})
        if min_order_setting and new_total_amount < min_order_setting["value"]:
            for item in user_order_edit.items:
                await products_collection.update_one(
                    {"_id": ObjectId(item.product_id)},
                    {"$inc": {"quantity": item.quantity}}
                )
            for original_item in order["items"]:
                await products_collection.update_one(
                    {"_id": ObjectId(original_item["product_id"])},
                    {"$inc": {"quantity": -original_item["quantity"]}}
                )
            raise HTTPException(
                status_code=400,
                detail=f"Minimum order value is ₹{min_order_setting['value']:.0f}. Your updated cart total is ₹{new_total_amount:.0f}. Please add more items to meet the minimum order requirement."
            )
        
        update_data = {
            "items": [item.model_dump() for item in user_order_edit.items],
            "total_amount": new_total_amount,
            "updated_at": datetime.now(UTC)
        }
        
        if user_order_edit.user_info:
            update_data.update({
                "user_name": user_order_edit.user_info.name,
                "user_email": user_order_edit.user_info.email,
                "user_phone": user_order_edit.user_info.phone,
                "user_address": user_order_edit.user_info.address
            })
            user_update_data = {
                "name": user_order_edit.user_info.name,
                "email": user_order_edit.user_info.email,
                "phone": user_order_edit.user_info.phone,
                "address": user_order_edit.user_info.address
            }
            if not verify_password(user_order_edit.user_info.password, user["password_hash"]):
                user_update_data["password_hash"] = get_password_hash(user_order_edit.user_info.password)
            await users_collection.update_one({"_id": user["_id"]}, {"$set": user_update_data})
        
        result = await orders_collection.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Order not found")
        
        updated_order = await orders_collection.find_one({"_id": ObjectId(order_id)})
        return serialize_doc(updated_order)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error editing order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to edit order")


@router.put("/admin/orders/{order_id}/edit", dependencies=[Depends(get_current_admin)])
async def admin_edit_order(order_id: str, order_edit: OrderEditRequest):
    """Admin version of order editing."""
    try:
        db = await get_database()
        orders_collection = db[ORDERS_COLLECTION]
        products_collection = db[PRODUCTS_COLLECTION]
        users_collection = db[USERS_COLLECTION]
        
        order = await orders_collection.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        if order["status"] not in ["pending", "confirmed"]:
            raise HTTPException(status_code=400, detail=f"Cannot edit order with status '{order['status']}'. Orders can only be edited when status is 'pending' or 'confirmed'.")
        
        for item in order_edit.items:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if not product:
                raise HTTPException(status_code=400, detail=f"Product {item.product_name} not found")
        
        # Restore stock from original order
        for original_item in order["items"]:
            await products_collection.update_one(
                {"_id": ObjectId(original_item["product_id"])},
                {"$inc": {"quantity": original_item["quantity"]}}
            )
        
        # Check new stock availability
        for item in order_edit.items:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if product["quantity"] < item.quantity:
                for original_item in order["items"]:
                    await products_collection.update_one(
                        {"_id": ObjectId(original_item["product_id"])},
                        {"$inc": {"quantity": -original_item["quantity"]}}
                    )
                raise HTTPException(
                    status_code=400,
                    detail=f"{product['name']} has only {product['quantity']} items available, but you requested {item.quantity}"
                )
        
        # Deduct new stock
        for item in order_edit.items:
            await products_collection.update_one(
                {"_id": ObjectId(item.product_id)},
                {"$inc": {"quantity": -item.quantity}}
            )
        
        new_total_amount = sum(item.total for item in order_edit.items)
        
        update_data = {
            "items": [item.model_dump() for item in order_edit.items],
            "total_amount": new_total_amount,
            "updated_at": datetime.now(UTC)
        }
        
        if order_edit.user_info:
            update_data.update({
                "user_name": order_edit.user_info.name,
                "user_email": order_edit.user_info.email,
                "user_phone": order_edit.user_info.phone,
                "user_address": order_edit.user_info.address
            })
            # Admin edit does NOT change user password
            user = await users_collection.find_one({"email": order["user_email"]})
            if user:
                await users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": {
                        "name": order_edit.user_info.name,
                        "email": order_edit.user_info.email,
                        "phone": order_edit.user_info.phone,
                        "address": order_edit.user_info.address
                    }}
                )
        
        result = await orders_collection.update_one(
            {"_id": ObjectId(order_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Order not found")
        
        updated_order = await orders_collection.find_one({"_id": ObjectId(order_id)})
        return serialize_doc(updated_order)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error editing order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to edit order")


@router.delete("/admin/orders/{order_id}", dependencies=[Depends(get_current_admin)])
async def delete_order(order_id: str):
    """Delete an order (admin only)."""
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    
    result = await orders_collection.delete_one({"_id": ObjectId(order_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {"message": "Order deleted successfully"}
