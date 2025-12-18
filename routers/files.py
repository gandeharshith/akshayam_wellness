"""
File upload and management routes.
"""
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from datetime import datetime, UTC
from bson import ObjectId
import io

from database import get_database
from auth import get_current_admin

router = APIRouter()


@router.get("/images/{file_id}")
async def get_image(file_id: str):
    """Serve images from MongoDB GridFS."""
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


@router.get("/pdfs/{file_id}")
async def get_pdf(file_id: str):
    """Serve PDFs from MongoDB GridFS."""
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


@router.post("/admin/upload", dependencies=[Depends(get_current_admin)])
async def upload_file(file: UploadFile = File(...)):
    """Upload file to MongoDB GridFS."""
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


async def _upload_and_update_image(entity_id: str, collection_name: str, file: UploadFile, url_field: str = "image_url"):
    """Helper function to upload image and update entity."""
    # Upload file to GridFS
    upload_result = await upload_file(file)
    
    # Update entity with image URL
    db = await get_database()
    collection = db[collection_name]
    
    await collection.update_one(
        {"_id": ObjectId(entity_id)},
        {"$set": {url_field: upload_result["url"]}}
    )
    
    return upload_result


@router.post("/admin/categories/{category_id}/image", dependencies=[Depends(get_current_admin)])
async def upload_category_image(category_id: str, file: UploadFile = File(...)):
    """Upload category image to GridFS."""
    from database import CATEGORIES_COLLECTION
    return await _upload_and_update_image(category_id, CATEGORIES_COLLECTION, file)


@router.post("/admin/products/{product_id}/image", dependencies=[Depends(get_current_admin)])
async def upload_product_image(product_id: str, file: UploadFile = File(...)):
    """Upload product image to GridFS."""
    from database import PRODUCTS_COLLECTION
    return await _upload_and_update_image(product_id, PRODUCTS_COLLECTION, file)


@router.post("/admin/content/{page}/logo", dependencies=[Depends(get_current_admin)])
async def upload_logo(page: str, file: UploadFile = File(...)):
    """Upload content logo to GridFS."""
    # Upload file to GridFS
    upload_result = await upload_file(file)
    
    # Update content with logo URL
    db = await get_database()
    from database import CONTENT_COLLECTION
    content_collection = db[CONTENT_COLLECTION]
    
    await content_collection.update_one(
        {"page": page},
        {"$set": {"logo_url": upload_result["url"], "updated_at": datetime.now(UTC)}}
    )
    
    return upload_result


@router.post("/admin/recipes/{recipe_id}/image", dependencies=[Depends(get_current_admin)])
async def upload_recipe_image(recipe_id: str, file: UploadFile = File(...)):
    """Upload recipe image to GridFS."""
    from routers.recipes import RECIPES_COLLECTION
    return await _upload_and_update_image(recipe_id, RECIPES_COLLECTION, file)


@router.post("/admin/recipes/{recipe_id}/pdf", dependencies=[Depends(get_current_admin)])
async def upload_recipe_pdf(recipe_id: str, file: UploadFile = File(...)):
    """Upload recipe PDF to GridFS."""
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
        from routers.recipes import RECIPES_COLLECTION
        recipes_collection = db[RECIPES_COLLECTION]
        await recipes_collection.update_one(
            {"_id": ObjectId(recipe_id)},
            {"$set": {"pdf_url": pdf_result["url"], "updated_at": datetime.now(UTC)}}
        )
        
        return pdf_result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload PDF: {str(e)}")
