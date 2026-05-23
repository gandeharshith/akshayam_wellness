"""
Subscription router — weekly auto-order feature.

A subscription stores:
  - user credentials (email + password) for authentication
  - product to order, quantity
  - delivery address
  - day_of_week (stored for reference, but orders are always placed on the configured day)
  - active flag

The background scheduler fires on the day/time configured in .env:
  SUBSCRIPTION_ORDER_DAY    — 0=Mon … 6=Sun  (default 3 = Thursday)
  SUBSCRIPTION_ORDER_HOUR   — 24-hour IST    (default 9)
  SUBSCRIPTION_ORDER_MINUTE — minute IST     (default 40)

To change the schedule, edit ONLY those three lines in .env and restart the server.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, UTC, timedelta, timezone
from zoneinfo import ZoneInfo
from bson import ObjectId
import asyncio
import os

from utils.helpers import serialize_doc as _serialize_doc

from database import get_database, SUBSCRIPTIONS_COLLECTION, ORDERS_COLLECTION, USERS_COLLECTION, PRODUCTS_COLLECTION
from auth import verify_password, get_current_admin

router = APIRouter()

# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────

class SubscriptionItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    price: float

class SubscriptionCreate(BaseModel):
    # User auth
    email: str
    password: str
    # Delivery info
    user_name: str
    user_phone: str
    user_address: str
    # Subscription config
    items: List[SubscriptionItem]
    day_of_week: int          # 0=Monday … 6=Sunday
    notes: Optional[str] = ""

class SubscriptionUpdate(BaseModel):
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_address: Optional[str] = None
    items: Optional[List[SubscriptionItem]] = None
    day_of_week: Optional[int] = None
    active: Optional[bool] = None
    notes: Optional[str] = None

class SubscriptionLogin(BaseModel):
    email: str
    password: str

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _serialize(doc: dict) -> dict:
    """Convert ObjectId and datetime fields for JSON serialisation (delegates to shared helper)."""
    return _serialize_doc(doc)


async def _authenticate_user(db, email: str, password: str) -> dict:
    """Return user doc if credentials are valid, else raise 401."""
    user = await db[USERS_COLLECTION].find_one({"email": email})
    if not user or not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return user


# ─────────────────────────────────────────────
# Public endpoints
# ─────────────────────────────────────────────

@router.post("/subscriptions")
async def create_subscription(data: SubscriptionCreate):
    """Create a new weekly subscription after verifying user credentials."""
    db = await get_database()
    user = await _authenticate_user(db, data.email, data.password)

    if data.day_of_week not in range(7):
        raise HTTPException(status_code=400, detail="day_of_week must be 0 (Mon) – 6 (Sun)")

    # Validate products exist and build items with current prices
    items = []
    total = 0.0
    for item in data.items:
        if not ObjectId.is_valid(item.product_id):
            raise HTTPException(status_code=400, detail=f"Invalid product_id: {item.product_id}")
        product = await db[PRODUCTS_COLLECTION].find_one({"_id": ObjectId(item.product_id)})
        if not product:
            raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")
        price = product["price"]
        line_total = price * item.quantity
        total += line_total
        items.append({
            "product_id": item.product_id,
            "product_name": product["name"],
            "quantity": item.quantity,
            "price": price,
            "total": line_total,
        })

    doc = {
        "user_id": str(user["_id"]),
        "user_email": data.email,
        "user_name": data.user_name,
        "user_phone": data.user_phone,
        "user_address": data.user_address,
        "items": items,
        "total_amount": total,
        "day_of_week": data.day_of_week,
        "day_name": DAY_NAMES[data.day_of_week],
        "notes": data.notes or "",
        "active": True,
        "last_processed_week": None,   # ISO week string e.g. "2024-W21"
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    result = await db[SUBSCRIPTIONS_COLLECTION].insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


@router.post("/subscriptions/my")
async def get_my_subscriptions(credentials: SubscriptionLogin):
    """Return all subscriptions for the authenticated user."""
    db = await get_database()
    user = await _authenticate_user(db, credentials.email, credentials.password)

    cursor = db[SUBSCRIPTIONS_COLLECTION].find({"user_id": str(user["_id"])}).sort("created_at", -1)
    subs = await cursor.to_list(length=None)
    return [_serialize(s) for s in subs]


@router.put("/subscriptions/{subscription_id}")
async def update_subscription(subscription_id: str, data: SubscriptionUpdate, credentials: SubscriptionLogin):
    """Update a subscription (user must own it)."""
    db = await get_database()
    user = await _authenticate_user(db, credentials.email, credentials.password)

    if not ObjectId.is_valid(subscription_id):
        raise HTTPException(status_code=400, detail="Invalid subscription ID")

    sub = await db[SUBSCRIPTIONS_COLLECTION].find_one({
        "_id": ObjectId(subscription_id),
        "user_id": str(user["_id"])
    })
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    update_fields: dict = {"updated_at": datetime.now(UTC)}

    if data.user_name is not None:
        update_fields["user_name"] = data.user_name
    if data.user_phone is not None:
        update_fields["user_phone"] = data.user_phone
    if data.user_address is not None:
        update_fields["user_address"] = data.user_address
    if data.notes is not None:
        update_fields["notes"] = data.notes
    if data.active is not None:
        update_fields["active"] = data.active
    if data.day_of_week is not None:
        if data.day_of_week not in range(7):
            raise HTTPException(status_code=400, detail="day_of_week must be 0–6")
        update_fields["day_of_week"] = data.day_of_week
        update_fields["day_name"] = DAY_NAMES[data.day_of_week]
    if data.items is not None:
        items = []
        total = 0.0
        for item in data.items:
            product = await db[PRODUCTS_COLLECTION].find_one({"_id": ObjectId(item.product_id)})
            if not product:
                raise HTTPException(status_code=404, detail=f"Product not found: {item.product_id}")
            price = product["price"]
            line_total = price * item.quantity
            total += line_total
            items.append({
                "product_id": item.product_id,
                "product_name": product["name"],
                "quantity": item.quantity,
                "price": price,
                "total": line_total,
            })
        update_fields["items"] = items
        update_fields["total_amount"] = total

    await db[SUBSCRIPTIONS_COLLECTION].update_one(
        {"_id": ObjectId(subscription_id)},
        {"$set": update_fields}
    )
    updated = await db[SUBSCRIPTIONS_COLLECTION].find_one({"_id": ObjectId(subscription_id)})
    return _serialize(updated)


@router.delete("/subscriptions/{subscription_id}")
async def cancel_subscription(subscription_id: str, credentials: SubscriptionLogin):
    """Cancel (delete) a subscription."""
    db = await get_database()
    user = await _authenticate_user(db, credentials.email, credentials.password)

    if not ObjectId.is_valid(subscription_id):
        raise HTTPException(status_code=400, detail="Invalid subscription ID")

    result = await db[SUBSCRIPTIONS_COLLECTION].delete_one({
        "_id": ObjectId(subscription_id),
        "user_id": str(user["_id"])
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"message": "Subscription cancelled successfully"}


# ─────────────────────────────────────────────
# Admin endpoints
# ─────────────────────────────────────────────

@router.get("/admin/subscriptions", dependencies=[Depends(get_current_admin)])
async def admin_get_all_subscriptions():
    """Admin: list all subscriptions."""
    db = await get_database()
    cursor = db[SUBSCRIPTIONS_COLLECTION].find({}).sort("created_at", -1)
    subs = await cursor.to_list(length=None)
    return [_serialize(s) for s in subs]


@router.post("/admin/subscriptions/process", dependencies=[Depends(get_current_admin)])
async def admin_trigger_processing(background_tasks: BackgroundTasks):
    """Admin: manually trigger subscription processing (for testing)."""
    background_tasks.add_task(process_due_subscriptions)
    return {"message": "Subscription processing triggered in background"}


# ─────────────────────────────────────────────
# Scheduler logic
# ─────────────────────────────────────────────

IST = ZoneInfo("Asia/Kolkata")

# ── Schedule config — edit ONLY in .env ─────────────────────────────────────
# SUBSCRIPTION_ORDER_DAY    : 0=Mon … 6=Sun  (default 3 = Thursday)
# SUBSCRIPTION_ORDER_HOUR   : 24-hour IST    (default 9)
# SUBSCRIPTION_ORDER_MINUTE : minute IST     (default 40)
ORDER_DAY_IST    = int(os.getenv("SUBSCRIPTION_ORDER_DAY",    "3"))
ORDER_HOUR_IST   = int(os.getenv("SUBSCRIPTION_ORDER_HOUR",   "9"))
ORDER_MINUTE_IST = int(os.getenv("SUBSCRIPTION_ORDER_MINUTE", "40"))
# ─────────────────────────────────────────────────────────────────────────────


async def process_due_subscriptions():
    """
    Called by the background scheduler on the configured day/time (IST).
    Places orders for ALL active subscriptions that haven't been
    processed this ISO week yet.
    """
    try:
        db = await get_database()
        now = datetime.now(UTC)
        iso_week = now.strftime("%Y-W%W")  # e.g. "2024-W21"

        # Fetch all active subscriptions (no day_of_week filter — all run on Thursday)
        cursor = db[SUBSCRIPTIONS_COLLECTION].find({"active": True})
        subs = await cursor.to_list(length=None)

        placed = 0
        for sub in subs:
            # Skip if already processed this week
            if sub.get("last_processed_week") == iso_week:
                continue

            # Build order document
            # Deduct stock for each subscription item (skip if out of stock)
            stock_ok = True
            for item in sub["items"]:
                try:
                    product = await db[PRODUCTS_COLLECTION].find_one({"_id": ObjectId(item["product_id"])})
                    if not product or product.get("quantity", 0) < item["quantity"]:
                        print(f"[Subscriptions] Skipping sub {sub['_id']} — insufficient stock for {item['product_name']}")
                        stock_ok = False
                        break
                except Exception:
                    stock_ok = False
                    break

            if not stock_ok:
                continue

            order_doc = {
                "user_id": sub["user_id"],
                "user_name": sub["user_name"],
                "user_email": sub["user_email"],
                "user_phone": sub["user_phone"],
                "user_address": sub["user_address"],
                "items": sub["items"],
                "total_amount": sub["total_amount"],
                "status": "pending",
                "source": "subscription",
                "subscription_id": str(sub["_id"]),
                "created_at": now,
                "updated_at": now,
            }
            await db[ORDERS_COLLECTION].insert_one(order_doc)

            # Decrement product quantities
            for item in sub["items"]:
                await db[PRODUCTS_COLLECTION].update_one(
                    {"_id": ObjectId(item["product_id"])},
                    {"$inc": {"quantity": -item["quantity"]}}
                )

            # Mark subscription as processed for this week
            await db[SUBSCRIPTIONS_COLLECTION].update_one(
                {"_id": sub["_id"]},
                {"$set": {
                    "last_processed_week": iso_week,
                    "last_order_placed_at": now,
                    "updated_at": now,
                }}
            )
            placed += 1
            print(f"[Subscriptions] Placed order for {sub['user_email']} (sub {sub['_id']})")

        print(f"[Subscriptions] Processing done — {placed} order(s) placed for week {iso_week}")
    except Exception as e:
        print(f"[Subscriptions] Error during processing: {e}")


async def subscription_scheduler():
    """
    Runs forever in the background.
    Fires every week on ORDER_DAY_IST at ORDER_HOUR_IST:ORDER_MINUTE_IST IST.
    All three values are read from .env at startup — change them there.

    On startup: if today is the configured day AND we are already past the
    scheduled time, runs once immediately (handles server restarts).
    Then sleeps until the next occurrence of that day/time.
    """
    day_name = DAY_NAMES[ORDER_DAY_IST]
    schedule_str = f"{day_name} at {ORDER_HOUR_IST:02d}:{ORDER_MINUTE_IST:02d} IST"
    print(f"[Subscriptions] Scheduler started — will run every {schedule_str}")

    now_ist = datetime.now(IST)

    # If today is the configured day and we're already past the scheduled time,
    # run once immediately (handles server restarts after the scheduled time)
    if now_ist.weekday() == ORDER_DAY_IST:
        scheduled_today = now_ist.replace(
            hour=ORDER_HOUR_IST, minute=ORDER_MINUTE_IST, second=0, microsecond=0
        )
        if now_ist >= scheduled_today:
            print(f"[Subscriptions] Server started after scheduled time on {day_name} — running immediately")
            await process_due_subscriptions()

    while True:
        now_ist = datetime.now(IST)

        # Find the next occurrence of ORDER_DAY_IST at ORDER_HOUR_IST:ORDER_MINUTE_IST
        days_until_order_day = (ORDER_DAY_IST - now_ist.weekday()) % 7
        next_order_day = now_ist + timedelta(days=days_until_order_day)
        next_run = next_order_day.replace(
            hour=ORDER_HOUR_IST, minute=ORDER_MINUTE_IST, second=0, microsecond=0
        )

        # If that time is already past (or right now), push to next week
        if next_run <= now_ist:
            next_run += timedelta(weeks=1)

        sleep_seconds = (next_run - now_ist).total_seconds()
        print(f"[Subscriptions] Next run at {next_run.strftime('%Y-%m-%d %H:%M IST')} "
              f"(in {sleep_seconds/3600:.1f} hours)")
        await asyncio.sleep(sleep_seconds)
        await process_due_subscriptions()
