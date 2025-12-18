"""
Main FastAPI application module.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, UTC
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import database functions
from database import (
    connect_to_mongo, 
    close_mongo_connection, 
    get_database,
    CATEGORIES_COLLECTION,
    PRODUCTS_COLLECTION,
    CONTENT_COLLECTION,
    CONTACT_INFO_COLLECTION,
    ADMINS_COLLECTION,
    SYSTEM_SETTINGS_COLLECTION
)

# Import authentication
from auth import get_password_hash

# Import all routers
from routers.auth import router as auth_router
from routers.categories import router as categories_router
from routers.products import router as products_router
from routers.orders import router as orders_router
from routers.content import router as content_router
from routers.recipes import router as recipes_router
from routers.files import router as files_router
from routers.contact import router as contact_router
from routers.settings import router as settings_router

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

# Include all routers
app.include_router(auth_router, prefix="/api", tags=["Authentication"])
app.include_router(categories_router, prefix="/api", tags=["Categories"])
app.include_router(products_router, prefix="/api", tags=["Products"])
app.include_router(orders_router, prefix="/api", tags=["Orders"])
app.include_router(content_router, prefix="/api", tags=["Content"])
app.include_router(recipes_router, prefix="/api", tags=["Recipes"])
app.include_router(files_router, prefix="/api", tags=["Files"])
app.include_router(contact_router, prefix="/api", tags=["Contact"])
app.include_router(settings_router, prefix="/api", tags=["Settings"])


# Database startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize database and default data on startup."""
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
    """Close database connection on shutdown."""
    await close_mongo_connection()


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "servicesuccessful"}


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now(UTC)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
