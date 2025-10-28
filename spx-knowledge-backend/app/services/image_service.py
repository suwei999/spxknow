"""
Image Service
"""

from typing import List, Optional
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.models.image import DocumentImage
from app.schemas.image import ImageResponse
from app.services.base import BaseService
from app.utils.image_utils import get_image_info, is_valid_image
import os
import shutil

class ImageService(BaseService[DocumentImage]):
    """图片服务"""
    
    def __init__(self, db: Session):
        super().__init__(db, DocumentImage)
    
    async def get_images(
        self, 
        skip: int = 0, 
        limit: int = 100,
        document_id: Optional[int] = None
    ) -> List[DocumentImage]:
        """获取图片列表"""
        filters = {}
        if document_id:
            filters["document_id"] = document_id
        
        return await self.get_multi(skip=skip, limit=limit, **filters)
    
    async def get_image(self, image_id: int) -> Optional[DocumentImage]:
        """获取图片详情"""
        return await self.get(image_id)
    
    async def upload_image(
        self, 
        file: UploadFile, 
        document_id: int
    ) -> DocumentImage:
        """上传图片"""
        # 检查图片有效性
        if not is_valid_image(file.filename):
            raise ValueError("无效的图片文件")
        
        # 保存图片
        upload_dir = f"uploads/images/{document_id}"
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 获取图片信息
        image_info = get_image_info(file_path)
        
        # 创建图片记录
        image_data = {
            "document_id": document_id,
            "image_path": file_path,
            "image_type": file.content_type,
            "width": image_info.get("width") if image_info else None,
            "height": image_info.get("height") if image_info else None,
            "status": "uploaded"
        }
        
        return await self.create(image_data)
    
    async def get_image_info(self, image_path: str) -> Optional[dict]:
        """获取图片信息"""
        return get_image_info(image_path)
    
    async def extract_ocr_text(self, image_path: str) -> str:
        """提取OCR文本"""
        # 这里应该实现OCR识别逻辑
        # 暂时返回空字符串
        return ""
    
    async def process_image(self, image_id: int) -> bool:
        """处理图片"""
        image = await self.get(image_id)
        if not image:
            return False
        
        try:
            # 更新状态为处理中
            image.status = "processing"
            self.db.commit()
            
            # 获取图片信息
            image_info = await self.get_image_info(image.image_path)
            if image_info:
                image.width = image_info.get("width")
                image.height = image_info.get("height")
            
            # OCR识别
            ocr_text = await self.extract_ocr_text(image.image_path)
            if ocr_text:
                image.ocr_text = ocr_text
            
            # 更新状态为完成
            image.status = "completed"
            self.db.commit()
            
            return True
            
        except Exception as e:
            # 更新状态为失败
            image.status = "failed"
            image.error_message = str(e)
            self.db.commit()
            return False