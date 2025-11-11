"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# Example schemas (replace with your own):

class User(BaseModel):
    """
    Users collection schema
    Collection name: "user" (lowercase of class name)
    """
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    address: str = Field(..., description="Address")
    age: Optional[int] = Field(None, ge=0, le=120, description="Age in years")
    is_active: bool = Field(True, description="Whether user is active")

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    in_stock: bool = Field(True, description="Whether product is in stock")

# Translation job schema for persistence
class TranslationOutput(BaseModel):
    language: str = Field(..., description="Target language code, e.g., hi, te, kn")
    translated_text: str = Field(..., description="Translated text content")
    audio_path: str = Field(..., description="Relative path to generated audio file")
    text_path: Optional[str] = Field(None, description="Relative path to translated text file")

class TranslationJob(BaseModel):
    job_name: Optional[str] = Field(None, description="Optional job label from user")
    source_filename: str = Field(..., description="Original uploaded filename")
    source_language: str = Field("en", description="ISO code of source language")
    status: str = Field("completed", description="Processing status")
    outputs: List[TranslationOutput] = Field(default_factory=list)
    error: Optional[str] = Field(None, description="Error message if any")

# Add your own schemas here:
# --------------------------------------------------

# Note: The Flames database viewer will automatically:
# 1. Read these schemas from GET /schema endpoint
# 2. Use them for document validation when creating/editing
# 3. Handle all database operations (CRUD) directly
# 4. You don't need to create any database endpoints!
