from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Annotated
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")

class User(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    email: str
    phone: str
    address: str
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Category(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: Optional[str] = ""
    image_url: Optional[str] = None
    order: int = 0  # For ordering categories
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Product(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: Optional[str] = ""
    category_id: str
    price: float
    quantity: int
    image_url: Optional[str] = None
    order: int = 0  # For ordering products
    created_at: datetime = Field(default_factory=datetime.utcnow)

class OrderItem(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    price: float
    total: float

class Order(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    user_name: str
    user_email: str
    user_phone: str
    user_address: str
    items: List[OrderItem]
    total_amount: float
    status: str = "pending"  # pending, confirmed, shipped, delivered, cancelled
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Content(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    page: str  # "home", "about", "contact", "features", etc.
    section: str  # "main", "hero", "features", "mission", "values", etc.
    title: str
    content: str
    logo_url: Optional[str] = None
    order: Optional[int] = 0  # For ordering sections
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class ContactInfo(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    company_name: str = "Akshayam Wellness"
    company_description: str
    email: str
    phone: str
    address: str
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Recipe(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    description: str  # Short description for listing
    image_url: Optional[str] = None
    pdf_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class Admin(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    username: str
    password_hash: str
    email: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Request/Response models
class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = ""

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    category_id: str
    price: float
    quantity: int

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[int] = None

class UserCreate(BaseModel):
    name: str
    email: str
    phone: str
    address: str
    password: str

class OrderCreate(BaseModel):
    user_info: UserCreate
    items: List[OrderItem]

class StockValidationItem(BaseModel):
    product_id: str
    quantity: int

class StockValidationRequest(BaseModel):
    items: List[StockValidationItem]

class StockValidationResponse(BaseModel):
    valid: bool
    message: str
    invalid_items: List[dict] = []

class OrderStatusUpdate(BaseModel):
    status: str

class OrderItemUpdate(BaseModel):
    product_id: str
    product_name: str
    quantity: int
    price: float
    total: float

class OrderEditRequest(BaseModel):
    items: List[OrderItemUpdate]
    user_info: Optional[UserCreate] = None  # Allow updating user info

class ContentCreate(BaseModel):
    page: str
    section: str
    title: str
    content: str
    order: Optional[int] = 0

class ContentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    page: Optional[str] = None
    section: Optional[str] = None
    order: Optional[int] = None

class ContactInfoUpdate(BaseModel):
    company_name: Optional[str] = None
    company_description: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None

class UserLogin(BaseModel):
    email: str
    password: str

class RecipeCreate(BaseModel):
    name: str
    description: str

class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class AdminLogin(BaseModel):
    username: str
    password: str

class SystemSettings(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    key: str  # e.g., "minimum_order_value"
    value: float  # The actual value
    description: str  # Description of what this setting does
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class SystemSettingsUpdate(BaseModel):
    value: float
    description: Optional[str] = None

class ReorderItem(BaseModel):
    id: str
    order: int

class ReorderRequest(BaseModel):
    items: List[ReorderItem]

class UserOrderEditRequest(BaseModel):
    """Combined model for user order editing that includes both order data and authentication"""
    items: List[OrderItemUpdate]
    user_info: Optional[UserCreate] = None
    email: str  # User email for authentication
    password: str  # User password for authentication
