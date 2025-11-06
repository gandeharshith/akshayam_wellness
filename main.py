from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from datetime import datetime, timedelta
import os
import io
from typing import List, Optional
from bson import ObjectId
import json

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
    USERS_COLLECTION
)
from models import (
    Category, CategoryCreate, CategoryUpdate,
    Product, ProductCreate, ProductUpdate,
    Order, OrderCreate, OrderStatusUpdate, OrderItem,
    Content, ContentCreate, ContentUpdate,
    ContactInfo, ContactInfoUpdate,
    Admin, AdminLogin,
    User, UserCreate, UserLogin
)
from auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_admin, ACCESS_TOKEN_EXPIRE_MINUTES
)

# Create FastAPI app
app = FastAPI(title="Akshayam Wellness API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React app URL
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
    existing_admin = await admin_collection.find_one({"username": "vivek1995m@gmail.com"})
    if not existing_admin:
        admin_data = {
            "username": "vivek1995m@gmail.com",
            "password_hash": get_password_hash("Vivek@1995"),
            "email": "vivek1995m@gmail.com",
            "created_at": datetime.utcnow()
        }
        await admin_collection.insert_one(admin_data)
        print("Default admin user created: username=vivek1995m@gmail.com, password=Vivek@1995")
    
    # Create default content if doesn't exist
    content_collection = db[CONTENT_COLLECTION]
    home_content = await content_collection.find_one({"page": "home"})
    if not home_content:
        home_data = {
            "page": "home",
            "title": "Welcome to Akshayam Wellness",
            "content": "Your trusted partner in organic wellness products. We provide high-quality, natural products to enhance your healthy lifestyle.",
            "updated_at": datetime.utcnow()
        }
        await content_collection.insert_one(home_data)
    
    about_content = await content_collection.find_one({"page": "about"})
    if not about_content:
        about_data = {
            "page": "about",
            "title": "About Akshayam Wellness",
            "content": "Founded with a mission to provide pure, organic products, Akshayam Wellness has been serving customers with premium quality natural products. Our commitment to sustainability and health drives everything we do.",
            "updated_at": datetime.utcnow()
        }
        await content_collection.insert_one(about_data)

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

# Helper function to convert ObjectId to string
def serialize_doc(doc):
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

# Authentication endpoints
@app.post("/api/admin/login")
async def admin_login(admin_data: AdminLogin):
    db = await get_database()
    admin_collection = db[ADMINS_COLLECTION]
    
    admin = await admin_collection.find_one({"username": admin_data.username})
    if not admin or not verify_password(admin_data.password, admin["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
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
    async for category in categories_collection.find():
        categories.append(serialize_doc(category))
    return categories

@app.post("/api/admin/categories", dependencies=[Depends(get_current_admin)])
async def create_category(category: CategoryCreate):
    db = await get_database()
    categories_collection = db[CATEGORIES_COLLECTION]
    
    category_data = {
        "name": category.name,
        "description": category.description,
        "image_url": None,
        "created_at": datetime.utcnow()
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
    async for product in products_collection.find(query):
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

@app.post("/api/admin/products", dependencies=[Depends(get_current_admin)])
async def create_product(product: ProductCreate):
    db = await get_database()
    products_collection = db[PRODUCTS_COLLECTION]
    categories_collection = db[CATEGORIES_COLLECTION]
    
    # Verify category exists
    category = await categories_collection.find_one({"_id": ObjectId(product.category_id)})
    if not category:
        raise HTTPException(status_code=400, detail="Invalid category ID")
    
    product_data = {
        "name": product.name,
        "description": product.description,
        "category_id": product.category_id,
        "price": product.price,
        "quantity": product.quantity,
        "image_url": None,
        "created_at": datetime.utcnow()
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

# Order endpoints
@app.post("/api/orders")
async def create_order(order_data: OrderCreate):
    db = await get_database()
    orders_collection = db[ORDERS_COLLECTION]
    users_collection = db[USERS_COLLECTION]
    products_collection = db[PRODUCTS_COLLECTION]
    
    # Create or get user with password hash
    user_data = order_data.user_info.model_dump()
    user_data["password_hash"] = get_password_hash(user_data.pop("password"))
    user_data["created_at"] = datetime.utcnow()
    
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
    
    # Validate products and calculate total
    total_amount = 0
    for item in order_data.items:
        product = await products_collection.find_one({"_id": ObjectId(item.product_id)})
        if not product:
            raise HTTPException(status_code=400, detail=f"Product {item.product_id} not found")
        if product["quantity"] < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for product {product['name']}")
        total_amount += item.total
    
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
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await orders_collection.insert_one(order_doc)
    
    # Update product quantities
    for item in order_data.items:
        await products_collection.update_one(
            {"_id": ObjectId(item.product_id)},
            {"$inc": {"quantity": -item.quantity}}
        )
    
    order_doc["_id"] = str(result.inserted_id)
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
        {"$set": {"status": status_update.status, "updated_at": datetime.utcnow()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    
    updated_order = await orders_collection.find_one({"_id": ObjectId(order_id)})
    return serialize_doc(updated_order)

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
    update_data["updated_at"] = datetime.utcnow()
    
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
        "updated_at": datetime.utcnow()
    }
    
    result = await content_collection.insert_one(content_data)
    content_data["_id"] = str(result.inserted_id)
    return content_data

@app.put("/api/admin/content/{content_id}", dependencies=[Depends(get_current_admin)])
async def update_content_by_id(content_id: str, content_update: ContentUpdate):
    db = await get_database()
    content_collection = db[CONTENT_COLLECTION]
    
    update_data = {k: v for k, v in content_update.dict().items() if v is not None}
    update_data["updated_at"] = datetime.utcnow()
    
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
    update_data["updated_at"] = datetime.utcnow()
    
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
            "updated_at": datetime.utcnow()
        }
        contact_data.update(update_data)
        
        result = await contact_collection.insert_one(contact_data)
        updated_contact = await contact_collection.find_one({"_id": result.inserted_id})
    
    return serialize_doc(updated_contact)

# GridFS File Storage endpoints
@app.get("/api/images/{file_id}")
async def get_image(file_id: str):
    """Serve images from MongoDB GridFS"""
    try:
        db = await get_database()
        fs = AsyncIOMotorGridFSBucket(db)
        
        # Get file from GridFS
        file_data = await fs.open_download_stream(ObjectId(file_id))
        
        # Get file info
        file_info = await fs.find({"_id": ObjectId(file_id)}).to_list(1)
        if not file_info:
            raise HTTPException(status_code=404, detail="Image not found")
        
        content_type = file_info[0].metadata.get("content_type", "image/jpeg")
        
        # Stream the file
        async def generate_stream():
            async for chunk in file_data:
                yield chunk
        
        return StreamingResponse(
            generate_stream(),
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename={file_info[0].filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=404, detail="Image not found")

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
                "upload_date": datetime.utcnow(),
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
        {"$set": {"logo_url": upload_result["url"], "updated_at": datetime.utcnow()}}
    )
    
    return upload_result

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
