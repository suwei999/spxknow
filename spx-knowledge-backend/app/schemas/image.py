"""
Image Schemas
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.schemas.base import BaseResponseSchema
from app.schemas.image_search import ImageSearchRequest, ImageSearchResponse

class ImageResponse(BaseResponseSchema):
    """图片响应模式"""
    document_id: int
    image_path: str
    image_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    ocr_text: Optional[str] = None
    metadata: Optional[dict] = None
