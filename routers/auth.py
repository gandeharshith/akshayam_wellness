"""
Authentication related routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import timedelta

from database import get_database, ADMINS_COLLECTION, USERS_COLLECTION
from models import AdminLogin, UserLogin
from auth import verify_password, create_access_token, ADMIN_TOKEN_EXPIRE_HOURS

router = APIRouter()


@router.post("/admin/login")
async def admin_login(admin_data: AdminLogin):
    """Admin login endpoint."""
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


@router.post("/user/login")
async def user_login(user_data: UserLogin):
    """User login endpoint."""
    db = await get_database()
    users_collection = db[USERS_COLLECTION]
    
    user = await users_collection.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return {"message": "Authentication successful", "user_id": str(user["_id"])}
