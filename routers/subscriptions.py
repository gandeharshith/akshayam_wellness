"""
Subscription router — weekly auto-order feature.

A subscription stores:
  - user credentials (email + password) for authentication
  - product to order, quantity
  - delivery address
  - day_of_week: the day the user chose (0=Mon … 6=Sun)
  - active flag

The background scheduler checks every minute. On each user's selected
day_of_week at 18:00 IST (6:00 PM), it creates a single order for that
subscription for the current week (idempotent via last_processed_week).

No environment variables are needed for scheduling — each subscription
uses its own day_of_week field chosen by the user.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, UTC, timedelta
from zoneinfo import ZoneInfo
from bson import ObjectId
import asyncio

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

# Fixed order time: 18:00 IST (6:00 PM) — no env variables needed.
# Each subscription fires on its own day_of_week at this time.
ORDER_HOUR_IST = 18
ORDER_MINUTE_IST = 0


async def process_due_subscriptions():
    """
    Called by the background scheduler every minute.
    Checks if the current IST time is 18:00 (6 PM) and if today's weekday
    matches any active subscription's day_of_week. If so, places an order
    for that subscription (once per week, idempotent via last_processed_week).
    """
    try:
        db = await get_database()
        now_utc = datetime.now(UTC)
        now_ist = datetime.now(IST)
        today_weekday = now_ist.weekday()  # 0=Mon … 6=Sun
        iso_week = now_ist.strftime("%Y-W%W")  # e.g. "2024-W21"

        # Only process subscriptions whose day_of_week matches today
        cursor = db[SUBSCRIPTIONS_COLLECTION].find({
            "active": True,
            "day_of_week": today_weekday,
        })
        subs = await cursor.to_list(length=None)

        if not subs:
            return

        placed = 0
        for sub in subs:
            # Skip if already processed this week
            if sub.get("last_processed_week") == iso_week:
                continue

            # Check stock for each subscription item
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

            # Build and insert order document
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
                "notes": sub.get("notes", ""),
                "created_at": now_utc,
                "updated_at": now_utc,
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
                    "last_order_placed_at": now_utc,
                    "updated_at": now_utc,
                }}
            )
            placed += 1
            print(f"[Subscriptions] Placed order for {sub['user_email']} (sub {sub['_id']}) — {DAY_NAMES[today_weekday]} 18:00 IST")

        if placed:
            print(f"[Subscriptions] Processing done — {placed} order(s) placed for week {iso_week}")
    except Exception as e:
        print(f"[Subscriptions] Error during processing: {e}")


async def subscription_scheduler():
    """
    Runs forever in the background. Every day at 18:00 IST (6:00 PM),
    it processes all active subscriptions whose day_of_week matches today.

    No environment variables are needed — each subscription uses its own
    day_of_week field selected by the user at creation time.

    Idempotency: each subscription has a `last_processed_week` field
    (e.g. "2026-W21"). If it matches the current week, the subscription
    is skipped — so redeployments/restarts never create duplicate orders.

    On startup: if it's already past 18:00 IST today, runs once immediately
    to catch up (but idempotency prevents duplicates).
    """
    print(f"[Subscriptions] Scheduler started — orders fire at 18:00 IST on each subscription's selected day")

    now_ist = datetime.now(IST)
    scheduled_time_today = now_ist.replace(hour=ORDER_HOUR_IST, minute=ORDER_MINUTE_IST, second=0, microsecond=0)

    # On startup: if we're already past 18:00 today, process immediately
    # (handles server restarts/redeploys after the scheduled time).
    # The idempotency check inside process_due_subscriptions() ensures
    # no duplicate orders — if last_processed_week matches this week, it skips.
    if now_ist >= scheduled_time_today:
        print(f"[Subscriptions] Server started after 18:00 IST on {DAY_NAMES[now_ist.weekday()]} — checking for missed orders (idempotent)")
        await process_due_subscriptions()

    while True:
        now_ist = datetime.now(IST)

        # Calculate seconds until next 18:00 IST
        target_today = now_ist.replace(hour=ORDER_HOUR_IST, minute=ORDER_MINUTE_IST, second=0, microsecond=0)

        if now_ist >= target_today:
            # Already past 18:00 today, wait until 18:00 tomorrow
            target = target_today + timedelta(days=1)
        else:
            target = target_today

        sleep_seconds = (target - now_ist).total_seconds()
        print(f"[Subscriptions] Next check at {target.strftime('%Y-%m-%d %H:%M IST')} "
              f"(in {sleep_seconds/3600:.1f} hours)")
        await asyncio.sleep(sleep_seconds)
        await process_due_subscriptions()
