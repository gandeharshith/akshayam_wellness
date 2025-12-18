"""
Recipe management routes.
"""
from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, UTC
from bson import ObjectId

from database import get_database
from models import RecipeCreate, RecipeUpdate
from auth import get_current_admin
from utils.helpers import serialize_doc

# Define recipes collection constant
RECIPES_COLLECTION = "recipes"

router = APIRouter()


@router.get("/recipes")
async def get_recipes():
    """Get all recipes - public endpoint."""
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    recipes = []
    async for recipe in recipes_collection.find().sort("created_at", -1):
        recipes.append(serialize_doc(recipe))
    return recipes


@router.get("/recipes/{recipe_id}")
async def get_recipe(recipe_id: str):
    """Get single recipe - public endpoint."""
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    recipe = await recipes_collection.find_one({"_id": ObjectId(recipe_id)})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    return serialize_doc(recipe)


@router.post("/admin/recipes", dependencies=[Depends(get_current_admin)])
async def create_recipe(recipe: RecipeCreate):
    """Create recipe - admin only."""
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


@router.put("/admin/recipes/{recipe_id}", dependencies=[Depends(get_current_admin)])
async def update_recipe(recipe_id: str, recipe: RecipeUpdate):
    """Update recipe - admin only."""
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


@router.delete("/admin/recipes/{recipe_id}", dependencies=[Depends(get_current_admin)])
async def delete_recipe(recipe_id: str):
    """Delete recipe - admin only."""
    db = await get_database()
    recipes_collection = db[RECIPES_COLLECTION]
    
    result = await recipes_collection.delete_one({"_id": ObjectId(recipe_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    return {"message": "Recipe deleted successfully"}
