"""
Helper utility functions used across the application.
"""
from typing import Dict, Any


def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert MongoDB ObjectId to string for JSON serialization.
    
    Args:
        doc: MongoDB document dictionary
        
    Returns:
        Document with _id converted to string, or None if doc is None
    """
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc
