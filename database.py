import os
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB connection URL from environment
MONGODB_URL = os.getenv("MONGODB_URI")
DATABASE_NAME = "akshayam_wellness"

class Database:
    client: Optional[AsyncIOMotorClient] = None
    database = None

db = Database()

async def get_database() -> AsyncIOMotorClient:
    return db.client[DATABASE_NAME]

async def connect_to_mongo():
    """Create database connection"""
    db.client = AsyncIOMotorClient(MONGODB_URL)
    db.database = db.client[DATABASE_NAME]
    print("Connected to MongoDB!")

async def close_mongo_connection():
    """Close database connection"""
    if db.client:
        db.client.close()
        print("Disconnected from MongoDB!")

# Collection names
USERS_COLLECTION = "users"
CATEGORIES_COLLECTION = "categories" 
PRODUCTS_COLLECTION = "products"
ORDERS_COLLECTION = "orders"
CONTENT_COLLECTION = "content"
CONTACT_INFO_COLLECTION = "contact_info"
ADMINS_COLLECTION = "admins"
SYSTEM_SETTINGS_COLLECTION = "system_settings"
