from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from datetime import datetime, timedelta, UTC
import os
import io
from typing import List, Optional
from bson import ObjectId
import json
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from database import (
    connect_to_mongo, 
    close_mongo_connection, 
    get_database,
    CATEGORIES_COLLECTION,
    PRODUCTS_COLLECTION,
    ORDERS_COLLECTION,
    CONTENT_COLLECTION,
    CONTACT_INFO_COLLECTION,
    ADMINS_COLLECTION,
    USERS_COLLECTION,
    SYSTEM_SETTINGS_COLLECTION
)

# Define recipes collection constant
RECIPES_COLLECTION = "recipes"
from models import (
    Category, CategoryCreate, CategoryUpdate,
    Product, ProductCreate, ProductUpdate,
    Order, OrderCreate, OrderStatusUpdate, OrderItem, OrderEditRequest, OrderItemUpdate,
    Content, ContentCreate, ContentUpdate,
    ContactInfo, ContactInfoUpdate,
    Recipe, RecipeCreate, RecipeUpdate,
    Admin, AdminLogin,
    User, UserCreate, UserLogin,
    StockValidationRequest, StockValidationResponse, StockValidationItem,
    SystemSettings, SystemSettingsUpdate,
    ReorderRequest, ReorderItem, UserOrderEditRequest
)
from auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_admin, ACCESS_TOKEN_EXPIRE_MINUTES, ADMIN_TOKEN_EXPIRE_HOURS
)
from sendgrid_email_service import sendgrid_email_service

# Create FastAPI app
app = FastAPI(title="Akshayam Wellness API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "https://akshayam-frontend.vercel.app",  # New Vercel deployment
        "https://akshayam-frontend-fvqbhywgn-harshiths-projects-5e70bbde.vercel.app",  # Old Vercel deployment
        "*"  # Allow all origins for now (you can restrict this later)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GridFS will be initialized in startup event

# Database startup and shutdown events
@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    # Create default admin user if doesn't exist
    db = await get_database()
    admin_collection = db[ADMINS_COLLECTION]
    
    # Get admin credentials from environment variables
    admin_username = os.getenv("ADMIN_USERNAME", "admin@akshayamwellness.com")
    admin_password = os.getenv("ADMIN_PASSWORD", "DefaultPassword123!")
    admin_email = os.getenv("ADMIN_EMAIL_LOGIN", admin_username)
    
    existing_admin = await admin_collection.find_one({"username": admin_username})
    if not existing_admin:
        admin_data = {
            "username": admin_username,
            "password_hash": get_password_hash(admin_password),
            "email": admin_email,
            "created_at": datetime.now(UTC)
        }
        await admin_collection.insert_one(admin_data)
        print(f"Default admin user created: username={admin_username}")
        print("⚠️ IMPORTANT: Change the default admin credentials in .env file for security!")
    
    # Initialize order field for existing categories that don't have it
    categories_collection = db[CATEGORIES_COLLECTION]
    categories_without_order = []
    async for category in categories_collection.find({"order": {"$exists": False}}):
        categories_without_order.append(category)
    
    if categories_without_order:
        for i, category in enumerate(categories_without_order, 1):
            await categories_collection.update_one(
                {"_id": category["_id"]},
                {"$set": {"order": i}}
            )
        print(f"Initialized order field for {len(categories_without_order)} categories")
    
    # Initialize order field for existing products that don't have it
    products_collection = db[PRODUCTS_COLLECTION]
    products_without_order = []
    async for product in products_collection.find({"order": {"$exists": False}}):
        products_without_order.append(product)
    
    if products_without_order:
        for i, product in enumerate(products_without_order, 1):
            await products_collection.update_one(
                {"_id": product["_id"]},
                {"$set": {"order": i}}
            )
        print(f"Initialized order field for {len(products_without_order)} products")
    
    # Create default content if doesn't exist
    content_collection = db[CONTENT_COLLECTION]
    home_content = await content_collection.find_one({"page": "home"})
    if not home_content:
        home_data = {
            "page": "home",
            "title": "Welcome to Akshayam Wellness",
            "content": "Your trusted partner in organic wellness products. We provide high-quality, natural products to enhance your healthy lifestyle.",
            "updated_at": datetime.now(UTC)
        }
        await content_collection.insert_one(home_data)
    
    about_content = await content_collection.find_one({"page": "about"})
    if not about_content:
        about_data = {
            "page": "about",
            "title": "About Akshayam Wellness",
            "content": "Founded with a mission to provide pure, organic products, Akshayam Wellness has been serving customers with premium quality natural products. Our commitment to sustainability and health drives everything we do.",
            "updated_at": datetime.now(UTC)
        }
        await content_collection.insert_one(about_data)
    
    # Create default delivery schedule content if doesn't exist
    delivery_content = await content_collection.find_one({"page": "delivery", "section": "schedule"})
    if not delivery_content:
        delivery_data = {
            "page": "delivery",
            "section": "schedule",
            "title": "Delivery Schedule",
            "content": "Orders should be placed before every Wednesday 6 PM and the shipment will be delivered on Sunday",
            "order": 1,
            "updated_at": datetime.now(UTC)
        }
        await content_collection.insert_one(delivery_data)
    
    # Create default system settings if they don't exist
    settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
    min_order_setting = await settings_collection.find_one({"key": "minimum_order_value"})
    if not min_order_setting:
        min_order_data = {
            "key": "minimum_order_value",
            "value": 500.0,
            "description": "Minimum order value required for checkout",
            "updated_at": datetime.now(UTC)
        }
        await settings_collection.insert_one(min_order_data)

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

# Helper function to convert ObjectId to string
def serialize_doc(doc):
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

# Background task for sending email notifications
async def send_order_email_background(order_doc: dict):
    """Background task to send order notification email without blocking the API response"""
    try:
        print(f"🚀 Background: Attempting to send email notification for order {order_doc['_id']}")
        
        # Add retry logic for email sending
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                email_success = await sendgrid_email_service.send_order_notification(order_doc)
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
        
        # Optionally, you could update the order document in the database to flag email failure
        # This would allow admins to see which orders didn't get email notifications
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

# Authentication endpoints
@app.post("/api/admin/login")
async def admin_login(admin_data: AdminLogin):
    db = await get_database()
    admin_collection = db[ADMINS_COLLECTION]
    
    admin = await admin_collection.find_one({"username": admin_data.username})
    if not admin or not verify_password(admin_data.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Use 10 hours expiry for admin tokens
    access_token_expires = timedelta(hours=ADMIN_TOKEN_EXPIRE_HOURS)
    access_token = create_access_token(
        data={"sub": admin["username"]}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# Category endpoints
@app.get("/api/categories")
async def get_categories():
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    categories = []
    async for category in categories_collection.find().sort("order", 1):
        categories.append(serialize_doc(category))
    return categories

# Reorder endpoint must come before the generic {category_id} endpoint
@app.put("/api/admin/categories/reorder", dependencies=[Depends(get_current_admin)])
async def reorder_categories(reorder_request: ReorderRequest):
    """Reorder categories by updating their order field"""
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    
    # Update each category's order
    for item in reorder_request.items:
        await categories_collection.update_one(
            {"_id": ObjectId(item.id)},
            {"$set": {"order": item.order}}
        )
    
    return {"message": "Categories reordered successfully"}

@app.post("/api/admin/categories", dependencies=[Depends(get_current_admin)])
async def create_category(category: CategoryCreate):
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

@app.put("/api/admin/categories/{category_id}", dependencies=[Depends(get_current_admin)])
async def update_category(category_id: str, category: CategoryUpdate):
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

@app.delete("/api/admin/categories/{category_id}", dependencies=[Depends(get_current_admin)])
async def delete_category(category_id: str):
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

# Product endpoints
@app.get("/api/products")
async def get_products(category_id: Optional[str] = None):
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    query = {}
    if category_id:
        query["category_id"] = category_id
    
    products = []
    async for product in products_collection.find(query).sort("order", 1):
        products.append(serialize_doc(product))
    return products

@app.get("/api/products/{product_id}")
async def get_product(product_id: str):
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    product = await products_collection.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return serialize_doc(product)

# Reorder endpoint must come before the generic {product_id} endpoint
@app.put("/api/admin/products/reorder", dependencies=[Depends(get_current_admin)])
async def reorder_products(reorder_request: ReorderRequest):
    """Reorder products by updating their order field"""
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    # Update each product's order
    for item in reorder_request.items:
        await products_collection.update_one(
            {"_id": ObjectId(item.id)},
            {"$set": {"order": item.order}}
        )
    
    return {"message": "Products reordered successfully"}

@app.post("/api/admin/products", dependencies=[Depends(get_current_admin)])
async def create_product(product: ProductCreate):
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

@app.put("/api/admin/products/{product_id}", dependencies=[Depends(get_current_admin)])
async def update_product(product_id: str, product: ProductUpdate):
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

@app.delete("/api/admin/products/{product_id}", dependencies=[Depends(get_current_admin)])
async def delete_product(product_id: str):
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    result = await products_collection.delete_one({"_id": ObjectId(product_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {"message": "Product deleted successfully"}


# Stock validation endpoint
@app.post("/api/validate-stock")
async def validate_stock(stock_request: StockValidationRequest):
    """Validate stock availability for cart items before checkout"""
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

# Order endpoints
@app.post("/api/orders")
async def create_order(order_data: OrderCreate, background_tasks: BackgroundTasks):
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
    validation_result = await validate_stock(stock_request)
    
    if not validation_result.valid:
        # Return detailed stock validation errors
        error_messages = [item["error"] for item in validation_result.invalid_items]
        raise HTTPException(
            status_code=400, 
            detail={
                "message": validation_result.message,
                "errors": error_messages,
                "invalid_items": validation_result.invalid_items
            }
        )
    
    # Create or get user with password hash
    user_data = order_data.user_info.model_dump()
    user_data["password_hash"] = get_password_hash(user_data.pop("password"))
    user_data["created_at"] = datetime.now(UTC)
    
    existing_user = await users_collection.find_one({"email": user_data["email"]})
    if existing_user:
        user_id = str(existing_user["_id"])
        # Update password hash if user exists
        await users_collection.update_one(
            {"_id": existing_user["_id"]}, 
            {"$set": {"password_hash": user_data["password_hash"]}}
        )
    else:
        user_result = await users_collection.insert_one(user_data)
        user_id = str(user_result.inserted_id)
    
    # Calculate total amount (products already validated above)
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
        "items": [item.dict() for item in order_data.items],
        "total_amount": total_amount,
        "status": "pending",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    }
    
    result = await orders_collection.insert_one(order_doc)
    
    # Update product quantities
    for item in order_data.items:
        await products_collection.update_one(
            {"_id": ObjectId(item.product_id)},
            {"$inc": {"quantity": -item.quantity}}
        )
    
    order_doc["_id"] = str(result.inserted_id)
    
    # Add email notification as background task to avoid blocking order creation
    print(f"📧 Scheduling background email notification for order {order_doc['_id']}")
    background_tasks.add_task(send_order_email_background, order_doc.copy())
    
    # Return order immediately without waiting for email
    print(f"✅ Order {order_doc['_id']} created successfully - email notification scheduled in background")
    return order_doc

@app.post("/api/user/login")
async def user_login(user_data: UserLogin):
    db = await get_database()
    users_collection = db[USERS_COLLECTION]
    
    user = await users_collection.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return {"message": "Authentication successful", "user_id": str(user["_id"])}

@app.post("/api/orders/user")
async def get_user_orders(user_data: UserLogin):
    db = await get_database()
    users_collection = db[USERS_COLLECTION]
    orders_collection = db[ORDERS_COLLECTION]
    
    # Verify user credentials
    user = await users_collection.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Get user orders
    orders = []
    async for order in orders_collection.find({"user_email": user_data.email}).sort("created_at", -1):
        orders.append(serialize_doc(order))
    return orders

@app.get("/api/admin/orders", dependencies=[Depends(get_current_admin)])
async def get_all_orders():
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    
    orders = []
    async for order in orders_collection.find().sort("created_at", -1):
        orders.append(serialize_doc(order))
    return orders

@app.put("/api/admin/orders/{order_id}/status", dependencies=[Depends(get_current_admin)])
async def update_order_status(order_id: str, status_update: OrderStatusUpdate):
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

@app.put("/api/orders/{order_id}/edit")
async def edit_order(order_id: str, user_order_edit: UserOrderEditRequest):
    """Edit order items for orders with status 'pending' or 'confirmed' - user authentication included in request"""
    try:
        db = await get_database()
        orders_collection = db[ORDERS_COLLECTION]
        users_collection = db[USERS_COLLECTION]
        products_collection = db[PRODUCTS_COLLECTION]
        
        # Verify order exists and get current order
        order = await orders_collection.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Check if order can be edited (only pending or confirmed)
        if order["status"] not in ["pending", "confirmed"]:
            raise HTTPException(status_code=400, detail=f"Cannot edit order with status '{order['status']}'. Orders can only be edited when status is 'pending' or 'confirmed'.")
        
        # Verify user credentials (user must own the order)
        user = await users_collection.find_one({"email": user_order_edit.email})
        if not user or not verify_password(user_order_edit.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Check if user owns this order
        if order["user_email"] != user_order_edit.email:
            raise HTTPException(status_code=403, detail="You can only edit your own orders")
        
        # Validate all products exist and have sufficient stock
        for item in user_order_edit.items:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if not product:
                raise HTTPException(status_code=400, detail=f"Product {item.product_name} not found")
        
        # Restore stock from original order items
        for original_item in order["items"]:
            await products_collection.update_one(
                {"_id": ObjectId(original_item["product_id"])},
                {"$inc": {"quantity": original_item["quantity"]}}
            )
        
        # Check stock availability for new quantities
        for item in user_order_edit.items:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if product["quantity"] < item.quantity:
                # Restore the original order if stock validation fails
                for original_item in order["items"]:
                    await products_collection.update_one(
                        {"_id": ObjectId(original_item["product_id"])},
                        {"$inc": {"quantity": -original_item["quantity"]}}
                    )
                raise HTTPException(
                    status_code=400, 
                    detail=f"{product['name']} has only {product['quantity']} items available, but you requested {item.quantity}"
                )
        
        # Deduct stock for new quantities
        for item in user_order_edit.items:
            await products_collection.update_one(
                {"_id": ObjectId(item.product_id)},
                {"$inc": {"quantity": -item.quantity}}
            )
        
        # Calculate new total amount
        new_total_amount = sum(item.total for item in user_order_edit.items)
        
        # Check minimum order value
        settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
        min_order_setting = await settings_collection.find_one({"key": "minimum_order_value"})
        if min_order_setting and new_total_amount < min_order_setting["value"]:
            # Restore the original order if min order validation fails
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
        
        # Update order with new items and user info if provided
        update_data = {
            "items": [item.dict() for item in user_order_edit.items],
            "total_amount": new_total_amount,
            "updated_at": datetime.now(UTC)
        }
        
        # Update user info if provided
        if user_order_edit.user_info:
            update_data.update({
                "user_name": user_order_edit.user_info.name,
                "user_email": user_order_edit.user_info.email,
                "user_phone": user_order_edit.user_info.phone,
                "user_address": user_order_edit.user_info.address
            })
            
            # Update user record - only hash password if it's actually being changed
            user_update_data = {
                "name": user_order_edit.user_info.name,
                "email": user_order_edit.user_info.email,
                "phone": user_order_edit.user_info.phone,
                "address": user_order_edit.user_info.address
            }
            
            # Only update password if it's different from current password
            if not verify_password(user_order_edit.user_info.password, user["password_hash"]):
                user_update_data["password_hash"] = get_password_hash(user_order_edit.user_info.password)
            
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": user_update_data}
            )
        
        # Update the order
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
        # Log error and return generic error message
        print(f"Error editing order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to edit order")

@app.put("/api/admin/orders/{order_id}/edit", dependencies=[Depends(get_current_admin)])
async def admin_edit_order(order_id: str, order_edit: OrderEditRequest):
    """Admin version of order editing - no authentication required for user"""
    try:
        db = await get_database()
        orders_collection = db[ORDERS_COLLECTION]
        products_collection = db[PRODUCTS_COLLECTION]
        users_collection = db[USERS_COLLECTION]
        
        # Verify order exists and get current order
        order = await orders_collection.find_one({"_id": ObjectId(order_id)})
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        # Check if order can be edited (only pending or confirmed)
        if order["status"] not in ["pending", "confirmed"]:
            raise HTTPException(status_code=400, detail=f"Cannot edit order with status '{order['status']}'. Orders can only be edited when status is 'pending' or 'confirmed'.")
        
        # Validate all products exist
        for item in order_edit.items:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if not product:
                raise HTTPException(status_code=400, detail=f"Product {item.product_name} not found")
        
        # Restore stock from original order items
        for original_item in order["items"]:
            await products_collection.update_one(
                {"_id": ObjectId(original_item["product_id"])},
                {"$inc": {"quantity": original_item["quantity"]}}
            )
        
        # Check stock availability for new quantities
        for item in order_edit.items:
            product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
            if product["quantity"] < item.quantity:
                # Restore the original order if stock validation fails
                for original_item in order["items"]:
                    await products_collection.update_one(
                        {"_id": ObjectId(original_item["product_id"])},
                        {"$inc": {"quantity": -original_item["quantity"]}}
                    )
                raise HTTPException(
                    status_code=400, 
                    detail=f"{product['name']} has only {product['quantity']} items available, but you requested {item.quantity}"
                )
        
        # Deduct stock for new quantities
        for item in order_edit.items:
            await products_collection.update_one(
                {"_id": ObjectId(item.product_id)},
                {"$inc": {"quantity": -item.quantity}}
            )
        
        # Calculate new total amount
        new_total_amount = sum(item.total for item in order_edit.items)
        
        # Update order with new items and user info if provided
        update_data = {
            "items": [item.dict() for item in order_edit.items],
            "total_amount": new_total_amount,
            "updated_at": datetime.now(UTC)
        }
        
        # Update user info if provided
        if order_edit.user_info:
            update_data.update({
                "user_name": order_edit.user_info.name,
                "user_email": order_edit.user_info.email,
                "user_phone": order_edit.user_info.phone,
                "user_address": order_edit.user_info.address
            })
            
            # Update user record but DO NOT update password from admin edit
            # Admin editing should not change user's authentication credentials
            user = await users_collection.find_one({"email": order["user_email"]})
            if user:
                user_update_data = {
                    "name": order_edit.user_info.name,
                    "email": order_edit.user_info.email,
                    "phone": order_edit.user_info.phone,
                    "address": order_edit.user_info.address
                    # Deliberately not updating password_hash to preserve user's original password
                }
                await users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$set": user_update_data}
                )
        
        # Update the order
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
        # Log error and return generic error message
        print(f"Error editing order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to edit order")

@app.delete("/api/admin/orders/{order_id}", dependencies=[Depends(get_current_admin)])
async def delete_order(order_id: str):
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    
    result = await orders_collection.delete_one({"_id": ObjectId(order_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {"message": "Order deleted successfully"}

@app.get("/api/admin/orders/analytics", dependencies=[Depends(get_current_admin)])
async def get_order_analytics():
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    
    # Aggregate total quantity per product
    pipeline = [
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.product_id",
            "product_name": {"$first": "$items.product_name"},
            "total_quantity": {"$sum": "$items.quantity"},
            "total_revenue": {"$sum": "$items.total"}
        }}
    ]
    
    analytics = []
    async for result in orders_collection.aggregate(pipeline):
        analytics.append({
            "product_id": result["_id"],
            "product_name": result["product_name"],
            "total_quantity": result["total_quantity"],
            "total_revenue": result["total_revenue"]
        })
    
    return analytics

# Content endpoints
@app.get("/api/content/{page}")
async def get_content(page: str):
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    content = await content_collection.find_one({"page": page})
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    return serialize_doc(content)

@app.put("/api/admin/content/{page}", dependencies=[Depends(get_current_admin)])
async def update_content(page: str, content_update: ContentUpdate):
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

# Enhanced Content Management endpoints
@app.get("/api/content")
async def get_all_content():
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    content = []
    async for item in content_collection.find().sort("order", 1):
        content.append(serialize_doc(item))
    return content

@app.get("/api/content/{page}/{section}")
async def get_content_section(page: str, section: str):
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    content = await content_collection.find_one({"page": page, "section": section})
    if not content:
        raise HTTPException(status_code=404, detail="Content section not found")
    
    return serialize_doc(content)

@app.post("/api/admin/content", dependencies=[Depends(get_current_admin)])
async def create_content(content: ContentCreate):
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

@app.put("/api/admin/content/id/{content_id}", dependencies=[Depends(get_current_admin)])
async def update_content_by_id(content_id: str, content_update: ContentUpdate):
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

@app.delete("/api/admin/content/{content_id}", dependencies=[Depends(get_current_admin)])
async def delete_content(content_id: str):
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    result = await content_collection.delete_one({"_id": ObjectId(content_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Content not found")
    
    return {"message": "Content deleted successfully"}

# Contact Information endpoints
@app.get("/api/contact-info")
async def get_contact_info():
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

@app.put("/api/admin/contact-info", dependencies=[Depends(get_current_admin)])
async def update_contact_info(contact_update: ContactInfoUpdate):
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

# Recipe endpoints (public read, admin write)
@app.get("/api/recipes")
async def get_recipes():
    """Get all recipes - public endpoint"""
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    recipes = []
    async for recipe in recipes_collection.find().sort("created_at", -1):
        recipes.append(serialize_doc(recipe))
    return recipes

@app.get("/api/recipes/{recipe_id}")
async def get_recipe(recipe_id: str):
    """Get single recipe - public endpoint"""
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    recipe = await recipes_collection.find_one({"_id": ObjectId(recipe_id)})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    return serialize_doc(recipe)

@app.post("/api/admin/recipes", dependencies=[Depends(get_current_admin)])
async def create_recipe(recipe: RecipeCreate):
    """Create recipe - admin only"""
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    recipe_data = {
        "name": recipe.name,
        "description": recipe.description,
        "image_url": None,
        "pdf_url": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC)
    }
    
    result = await recipes_collection.insert_one(recipe_data)
    recipe_data["_id"] = str(result.inserted_id)
    return recipe_data

@app.put("/api/admin/recipes/{recipe_id}", dependencies=[Depends(get_current_admin)])
async def update_recipe(recipe_id: str, recipe: RecipeUpdate):
    """Update recipe - admin only"""
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    update_data = {k: v for k, v in recipe.dict().items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await recipes_collection.update_one(
            {"_id": ObjectId(recipe_id)}, 
            {"$set": update_data}
        )
    
    updated_recipe = await recipes_collection.find_one({"_id": ObjectId(recipe_id)})
    return serialize_doc(updated_recipe)

@app.delete("/api/admin/recipes/{recipe_id}", dependencies=[Depends(get_current_admin)])
async def delete_recipe(recipe_id: str):
    """Delete recipe - admin only"""
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    result = await recipes_collection.delete_one({"_id": ObjectId(recipe_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    return {"message": "Recipe deleted successfully"}

# GridFS File Storage endpoints
@app.get("/api/images/{file_id}")
async def get_image(file_id: str):
    """Serve images from MongoDB GridFS"""
    try:
        db = await get_database()
        fs = AsyncIOMotorGridFSBucket(db)
        
        # Download entire file to BytesIO to avoid streaming Unicode issues
        file_bytes = io.BytesIO()
        await fs.download_to_stream(ObjectId(file_id), file_bytes)
        file_bytes.seek(0)
        
        # Use default content type
        content_type = "image/jpeg"
        
        # Stream from BytesIO
        def generate_stream():
            while True:
                chunk = file_bytes.read(8192)
                if not chunk:
                    break
                yield chunk
        
        return StreamingResponse(
            generate_stream(),
            media_type=content_type,
            headers={"Content-Disposition": "inline"}
        )
        
    except Exception as e:
        print(f"Error retrieving image {file_id}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=404, detail=f"Image not found: {str(e)}")

@app.post("/api/admin/upload", dependencies=[Depends(get_current_admin)])
async def upload_file(file: UploadFile = File(...)):
    """Upload file to MongoDB GridFS"""
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    
    try:
        db = await get_database()
        fs = AsyncIOMotorGridFSBucket(db)
        
        # Create unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        
        # Read file content
        file_content = await file.read()
        
        # Store in GridFS
        file_id = await fs.upload_from_stream(
            filename,
            io.BytesIO(file_content),
            metadata={
                "content_type": file.content_type,
                "upload_date": datetime.now(UTC),
                "original_filename": file.filename
            }
        )
        
        return {
            "file_id": str(file_id),
            "filename": filename,
            "url": f"/api/images/{file_id}"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.post("/api/admin/categories/{category_id}/image", dependencies=[Depends(get_current_admin)])
async def upload_category_image(category_id: str, file: UploadFile = File(...)):
    """Upload category image to GridFS"""
    # Upload file to GridFS
    upload_result = await upload_file(file)
    
    # Update category with image URL
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    
    await categories_collection.update_one(
        {"_id": ObjectId(category_id)},
        {"$set": {"image_url": upload_result["url"]}}
    )
    
    return upload_result

@app.post("/api/admin/products/{product_id}/image", dependencies=[Depends(get_current_admin)])
async def upload_product_image(product_id: str, file: UploadFile = File(...)):
    """Upload product image to GridFS"""
    # Upload file to GridFS
    upload_result = await upload_file(file)
    
    # Update product with image URL
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    
    await products_collection.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"image_url": upload_result["url"]}}
    )
    
    return upload_result

@app.post("/api/admin/content/{page}/logo", dependencies=[Depends(get_current_admin)])
async def upload_logo(page: str, file: UploadFile = File(...)):
    """Upload content logo to GridFS"""
    # Upload file to GridFS
    upload_result = await upload_file(file)
    
    # Update content with logo URL
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    await content_collection.update_one(
        {"page": page},
        {"$set": {"logo_url": upload_result["url"], "updated_at": datetime.now(UTC)}}
    )
    
    return upload_result

@app.post("/api/admin/recipes/{recipe_id}/image", dependencies=[Depends(get_current_admin)])
async def upload_recipe_image(recipe_id: str, file: UploadFile = File(...)):
    """Upload recipe image to GridFS"""
    # Upload file to GridFS
    upload_result = await upload_file(file)
    
    # Update recipe with image URL
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    await recipes_collection.update_one(
        {"_id": ObjectId(recipe_id)},
        {"$set": {"image_url": upload_result["url"], "updated_at": datetime.now(UTC)}}
    )
    
    return upload_result

@app.post("/api/admin/recipes/{recipe_id}/pdf", dependencies=[Depends(get_current_admin)])
async def upload_recipe_pdf(recipe_id: str, file: UploadFile = File(...)):
    """Upload recipe PDF to GridFS"""
    if not file.content_type == 'application/pdf':
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    try:
        db = await get_database()
        fs = AsyncIOMotorGridFSBucket(db)
        
        # Create unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        
        # Read file content
        file_content = await file.read()
        
        # Store in GridFS
        file_id = await fs.upload_from_stream(
            filename,
            io.BytesIO(file_content),
            metadata={
                "content_type": file.content_type,
                "upload_date": datetime.now(UTC),
                "original_filename": file.filename
            }
        )
        
        pdf_result = {
            "file_id": str(file_id),
            "filename": filename,
            "url": f"/api/pdfs/{file_id}"
        }
        
        # Update recipe with PDF URL
        recipes_collection = db[RECIPES_COLLECTION]
        await recipes_collection.update_one(
            {"_id": ObjectId(recipe_id)},
            {"$set": {"pdf_url": pdf_result["url"], "updated_at": datetime.now(UTC)}}
        )
        
        return pdf_result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload PDF: {str(e)}")

@app.get("/api/pdfs/{file_id}")
async def get_pdf(file_id: str):
    """Serve PDFs from MongoDB GridFS"""
    try:
        db = await get_database()
        fs = AsyncIOMotorGridFSBucket(db)
        
        # Get file from GridFS
        file_data = await fs.open_download_stream(ObjectId(file_id))
        
        # Get file info
        content_type = file_data.metadata.get("content_type", "application/pdf") if file_data.metadata else "application/pdf"
        filename = file_data.filename or "recipe.pdf"
        
        # Stream the file
        async def generate_stream():
            async for chunk in file_data:
                yield chunk
        
        return StreamingResponse(
            generate_stream(),
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=404, detail="PDF not found")

# System Settings endpoints
@app.get("/api/settings/{key}")
async def get_system_setting(key: str):
    """Get a system setting by key (public endpoint)"""
    db = await get_database()
    settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
    
    setting = await settings_collection.find_one({"key": key})
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    return serialize_doc(setting)

@app.get("/api/admin/settings", dependencies=[Depends(get_current_admin)])
async def get_all_system_settings():
    """Get all system settings (admin only)"""
    db = await get_database()
    settings_collection = db[SYSTEM_SETTINGS_COLLECTION]
    
    settings = []
    async for setting in settings_collection.find():
        settings.append(serialize_doc(setting))
    return settings

@app.put("/api/admin/settings/{key}", dependencies=[Depends(get_current_admin)])
async def update_system_setting(key: str, setting_update: SystemSettingsUpdate):
    """Update a system setting (admin only)"""
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

# Root endpoint
@app.get("/")
async def root():
    return {"message": "servicesuccessful"}

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(UTC)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
