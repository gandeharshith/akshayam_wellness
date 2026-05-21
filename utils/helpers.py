"""
Helper utility functions used across the application.
"""
from typing import Dict, Any
from datetime import datetime, timezone


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert MongoDB document fields for JSON serialization:
      - ObjectId  → string
      - datetime  → UTC ISO-8601 string ending in 'Z'
                    (so the browser always parses it as UTC, not local time)

    MongoDB stores datetimes as UTC internally. When PyMongo returns them they
    are timezone-aware (UTC) in recent versions, but older documents or certain
    drivers may return naive datetimes. We normalise both cases to a UTC 'Z'
    string so the frontend can reliably convert to IST.
    """
    if not doc:
        return doc

    doc["_id"] = str(doc["_id"])

    for key, value in doc.items():
        if isinstance(value, datetime):
            # Make sure it's treated as UTC regardless of whether it's naive or aware
            if value.tzinfo is None:
                # Naive datetime — assume UTC (MongoDB always stores UTC)
                value = value.replace(tzinfo=timezone.utc)
            else:
                # Convert to UTC in case it's some other tz
                value = value.astimezone(timezone.utc)
            # Produce "2026-05-21T04:10:00Z" — always UTC, always has Z suffix
            doc[key] = value.strftime("%Y-%m-%dT%H:%M:%SZ")

    return doc
